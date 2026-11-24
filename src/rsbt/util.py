"""Util: assorted helpers for failing a build, git metadata, GitHub releases, and HTTP requests."""

import json
import time

import requests

from .exceptions import BuildFailure, val_arg
from .exec import bash, exec_cmd
from .log import logger

# Number of attempts, and the backoff schedule between them, for Util.url_request's
# retry of transient HTTP failures (connection errors, timeouts, 5xx/429 responses)
_URL_REQUEST_MAX_ATTEMPTS = 4
_URL_REQUEST_INITIAL_BACKOFF_SECONDS = 1.0
_URL_REQUEST_BACKOFF_MULTIPLIER = 2.0

# Status codes that are treated as transient (worth retrying) when they are
# not already an explicitly accepted status_check value
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class Util:
    """Assorted helpers: failing a build, git metadata, GitHub releases, HTTP requests."""

    @classmethod
    def fail(cls, message):
        """Raise BuildFailure(message)."""
        raise BuildFailure(message)

    @classmethod
    def git_sha(cls, *, ignore_merges=False):
        """Return the current commit's abbreviated SHA.

        ignore_merges: when True, skip back past any leading merge commits
            and return the most recent non-merge commit's SHA instead.
        """
        val_arg(isinstance(ignore_merges, bool), "Invalid ignore_merges parameter. Must be bool")

        cmd = "git log -1 --no-merges --format=%h" if ignore_merges else "git log -1 --format=%h"

        return exec_cmd(cmd, capture=True).stdout

    @classmethod
    def git_latest_tag(cls):
        """Return the most recent tag reachable from HEAD, or "" if there is none."""
        return bash('git describe --tags --abbrev=0 2>/dev/null || echo ""', capture=True).stdout

    @classmethod
    def git_list_tags(cls):
        """Return every tag in the repo, sorted by version."""
        return exec_cmd("git tag --sort v:refname", capture=True)

    @classmethod
    def git_notes_since_tag(cls, tag=None):
        """Return every non-merge commit subject since tag (the whole history if tag is empty)."""
        if tag is None or tag == "":
            return bash("git log --no-merges --format=%s HEAD", capture=True).stdout

        return bash(f'git log --no-merges --format=%s HEAD "^{tag}"', capture=True).stdout

    @classmethod
    def url_request(
        cls, url, method="get", headers=None, body=None, verify=True, status_check=None
    ):
        """Make an HTTP request, retrying transient failures with backoff.

        url/method/headers/body/verify: passed through to requests.request.
        status_check: an int or list of ints that are the only acceptable
            response status codes. Defaults to requests' own
            raise_for_status() behaviour (anything 4xx/5xx raises).

        A connection error, timeout, or a 5xx/429 response that is not
        itself an accepted status_check value is retried up to
        _URL_REQUEST_MAX_ATTEMPTS times with exponential backoff; any other
        failure (e.g. a 404, or a 4xx that status_check didn't accept) is
        not retried, since a retry would not change the outcome.
        """
        val_arg(isinstance(url, str), "Invalid url. Must be string")
        val_arg(isinstance(method, str), "Invalid method. Must be string")
        val_arg(isinstance(body, (str, type(None))), "Invalid body. Must be None or str")
        val_arg(isinstance(verify, bool), "Invalid verify parameter. Must be bool")
        val_arg(
            isinstance(status_check, (list, int, type(None))),
            "Invalid status_check parameter. Must be list, int or None",
        )

        # Wrap a single int in a list, so the rest of this method only has
        # to deal with one shape
        if isinstance(status_check, int):
            status_check = [status_check]

        if status_check is not None:
            val_arg(
                all(isinstance(x, int) for x in status_check),
                "Invalid values in status check. Must be int",
            )

        if headers is None:
            headers = {}

        val_arg(isinstance(headers, dict), "Invalid headers. Must be dict type")

        for key, value in headers.items():
            val_arg(isinstance(key, str), "Invalid keys in headers. Must be string")
            val_arg(isinstance(value, str), "Invalid values in headers. Must be string")

        request_args = {
            "method": method,
            "url": url,
            "timeout": (10, 30),
            "headers": headers,
            "verify": verify,
        }

        if body is not None:
            request_args["data"] = body

        backoff_seconds = _URL_REQUEST_INITIAL_BACKOFF_SECONDS
        last_exception = None

        for attempt in range(1, _URL_REQUEST_MAX_ATTEMPTS + 1):
            try:
                response = requests.request(**request_args)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                # A connection-level failure is always worth retrying
                last_exception = e
                logger.warning(
                    "Request attempt %d/%d failed: %s", attempt, _URL_REQUEST_MAX_ATTEMPTS, e
                )
            else:
                logger.debug("Response code: %s", response.status_code)
                logger.debug("Response text: %s", response.text)

                # An explicitly accepted status is never retried, even if it
                # would otherwise look like a transient failure (e.g. a 409
                # from an already-open PR)
                if status_check is not None and response.status_code in status_check:
                    return response

                if response.status_code not in _RETRYABLE_STATUS_CODES:
                    # Not retryable - resolve via status_check or the
                    # library's default raise_for_status() handling
                    if status_check is None:
                        response.raise_for_status()
                        return response

                    raise requests.HTTPError(
                        f"Status code ({response.status_code}) not in {status_check}"
                    )

                last_exception = requests.HTTPError(
                    f"Transient status code: {response.status_code}"
                )
                logger.warning(
                    "Request attempt %d/%d got retryable status %d",
                    attempt,
                    _URL_REQUEST_MAX_ATTEMPTS,
                    response.status_code,
                )

            # Out of attempts - propagate whatever the last failure was
            if attempt == _URL_REQUEST_MAX_ATTEMPTS:
                raise last_exception

            time.sleep(backoff_seconds)
            backoff_seconds *= _URL_REQUEST_BACKOFF_MULTIPLIER

        # Unreachable: the loop above always returns or raises
        raise last_exception

    @classmethod
    def github_release(cls, tag_name, *, name, prerelease, github_token, repo):
        """Create a GitHub release for tag_name."""
        val_arg(isinstance(tag_name, str), "Invalid tag name parameter. Must be str")
        val_arg(isinstance(name, str), "Invalid name parameter. Must be str")
        val_arg(isinstance(prerelease, bool), "Invalid prerelease parameter. Must be bool")
        val_arg(isinstance(github_token, str), "Invalid github token parameter. Must be str")
        val_arg(isinstance(repo, str), "Invalid repo parameter. Must be str")

        val_arg(tag_name != "", "Empty tag name supplied")
        val_arg(name != "", "Empty name supplied")
        val_arg(github_token != "", "Empty github token")
        val_arg(repo != "", "Empty repo parameter")

        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {github_token}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        body = json.dumps(
            {
                "tag_name": tag_name,
                "name": name,
                "draft": False,
                "prerelease": prerelease,
                "generate_release_notes": True,
            }
        )

        args = {
            "url": f"https://api.github.com/repos/{repo}/releases",
            "method": "post",
            "body": body,
            "headers": headers,
            "status_check": [201],
        }

        logger.debug("Url args: %s", args)
        Util.url_request(**args)
