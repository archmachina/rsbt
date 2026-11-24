"""rsbt - Really Simple Build Tool.

A small library of helpers for writing CI/CD build, test, lint, release and
deploy pipelines as plain Python (an ``_entrypoint.py``) instead of large
shell scripts or YAML: a CLI action dispatcher, a subprocess runner, and a
handful of "session" helper classes for the common build/test/release
shapes (Python packages, container images, environment promotion chains).
"""

import argparse
import inspect
import json
import logging
import os
import re
import shlex
import subprocess
import sys
import textwrap
import time

import requests


# Exceptions
class ArgumentException(Exception):
    """Raised when a function is called with an invalid argument."""


class CommandException(Exception):
    """Raised when a subprocess exits with an exit code that was not allowed."""


class DeployError(Exception):
    """Raised for invalid usage of the deployment/promotion helpers."""


class VersionParseError(Exception):
    """Raised when no semver match could be found among the given sources."""


class BuildFailure(Exception):
    """Raised to fail a build, e.g. when a test or lint command fails."""


def val_arg(val, message):
    """Raise ArgumentException(message) if val is falsy."""
    if not val:
        raise ArgumentException(message)


# Logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def configure_logging(debug=False):
    """(Re)configure the root logger's level and format.

    debug: when True, sets the level to DEBUG instead of INFO.
    """
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s", force=True)


# Actions registry, populated by the @action decorator and read by run_action()
actions = {}


def action(func):
    """Register func as a named CLI action, keyed by its function name."""
    actions[func.__name__] = func

    return func


# Shortform functions for particular shells or invocation types
def bash(cmd, **kwargs):
    """Run cmd as a bash script, via exec_cmd's interpreter mode."""
    return exec_cmd(cmd, interpreter="bash", **kwargs)


def pwsh(cmd, **kwargs):
    """Run cmd as a PowerShell script, via exec_cmd's interpreter mode."""
    return exec_cmd(cmd, interpreter="pwsh -noni -c -", **kwargs)


def shell(cmd, **kwargs):
    """Run cmd through the system shell (equivalent to subprocess's shell=True)."""
    return exec_cmd(cmd, shell=True, **kwargs)


class ExecStatus:
    """Placeholder result shape for a subprocess run (returncode, stdout)."""

    def __init__(self):
        self.returncode = None
        self.stdout = None


def exec_cmd(
    cmd, *, shell=False, env=None, interpreter=None, capture=False, allowed_rc=None, ignore_rc=False
):
    """Run cmd as a subprocess and return the completed subprocess.run() result.

    cmd: a list of argv strings, or a single string (split with shlex unless
        shell=True or an interpreter is given, in which case it is passed
        through as-is - as the shell command line, or as the interpreter's
        stdin, respectively).
    shell: run via the system shell (subprocess's shell=True).
    env: extra environment variables to overlay onto the current environment.
    interpreter: a command (e.g. "bash") to run with cmd piped to its stdin,
        instead of executing cmd directly.
    capture: capture stdout instead of letting it flow through to the
        current process's stdout.
    allowed_rc: exit codes that are not considered a failure. Defaults to [0].
    ignore_rc: when True, never raise CommandException regardless of exit code.
    """
    # Validate all incoming arguments up front, so a bad call fails fast with
    # a clear message rather than partway through building subprocess args.
    val_arg(isinstance(cmd, (list, str)), "Invalid type for cmd. Must be a list or string")
    if isinstance(cmd, list):
        val_arg(
            all(isinstance(x, str) for x in cmd),
            "Invalid value for cmd. Some members are not strings",
        )

    val_arg(isinstance(shell, bool), "Invalid value for shell argument")
    val_arg(isinstance(capture, bool), "Invalid type for capture. Must be bool")
    val_arg(isinstance(interpreter, (str, type(None))), "Invalid interpreter. Must be str or None")
    val_arg(isinstance(env, (dict, type(None))), "Invalid type for env. Must be dict or None")

    envs = os.environ.copy()

    if isinstance(env, dict):
        val_arg(all(isinstance(x, str) for x in env.keys()), "env must be a dict str to str")
        val_arg(all(isinstance(x, str) for x in env.values()), "env must be a dict str to str")

        envs.update(env)

    val_arg(
        isinstance(allowed_rc, (list, type(None))),
        "Invalid type for allowed_rc. Must be list or None",
    )

    if allowed_rc is None:
        allowed_rc = [0]

    if isinstance(allowed_rc, list):
        val_arg(
            all(isinstance(x, int) for x in allowed_rc), "Invalid values in allowed_rc. Must be int"
        )

    val_arg(isinstance(ignore_rc, bool), "Invalid type for ignore_rc. Must be bool")

    # Arguments to subprocess.run
    subprocess_args = {
        "env": envs,
        "stdout": None,
        "stderr": subprocess.STDOUT,
        "shell": shell,
        "text": True,
    }

    # If we're capturing, stdout should come back via pipe instead of
    # flowing through to this process's stdout
    if capture:
        subprocess_args["stdout"] = subprocess.PIPE

    # If an interpreter is defined, run that instead and feed it cmd as
    # stdin; otherwise cmd is the command to execute directly, with no stdin
    if interpreter is not None and interpreter != "":
        call_args = interpreter
        subprocess_args["input"] = cmd
    else:
        call_args = cmd
        subprocess_args["stdin"] = subprocess.DEVNULL

    # If we're not using shell interpretation, split a string command into
    # an argv list
    if not shell:
        call_args = shlex.split(call_args) if isinstance(call_args, str) else call_args

    logger.info("exec_cmd: %s", cmd)
    logger.debug("Call arguments: %s", call_args)
    debug_args = subprocess_args.copy()
    debug_args["env"] = "*hidden*"
    logger.debug("Subprocess args: %s", debug_args)

    # Run the process. Flush stdout first so interleaved output from the
    # child process (when not captured) stays in the right order
    sys.stdout.flush()
    proc = subprocess.run(call_args, check=False, **subprocess_args)

    # Treat the exit code as a failure unless it was explicitly allowed or
    # the caller asked to ignore it entirely
    if not ignore_rc and proc.returncode not in allowed_rc:
        # If output was captured, it would otherwise be lost on failure, so
        # print it before raising
        if subprocess_args["stdout"] is not None:
            print(str(proc.stdout), flush=True)

        raise CommandException(f"Process exited with bad exit code: {proc.returncode}")

    return proc


def run_action():
    """Parse sys.argv as "<action> [action_arg...]" and dispatch to the registered action.

    Exits the process (0 on success, 1 on any exception) rather than
    returning, so this is normally the last call in an _entrypoint.py.
    """
    try:
        parser = argparse.ArgumentParser(
            prog="entrypoint", description="entrypoint", exit_on_error=False
        )

        parser.add_argument(
            "-v", "-d", action="store_true", dest="debug", help="Verbose/debug output"
        )

        parser.add_argument("action", action="store", help="Action to perform")

        parser.add_argument(
            "action_arg",
            action="store",
            help="Optional argument to the action",
            default="",
            nargs=argparse.REMAINDER,
        )

        args = parser.parse_args()

        # Honour -v/-d immediately, so debug-level logging covers the
        # action dispatch below too
        configure_logging(debug=args.debug)

        # Make sure we have an action, and that it is a known one
        if args.action is None or args.action == "":
            raise ArgumentException("Invalid or missing action")

        if args.action not in actions:
            raise ArgumentException(f"Unknown action {args.action}")

        # Run the action, passing the joined action argument only if the
        # action function accepts one
        target = actions[args.action]
        if len(inspect.signature(target).parameters) > 0:
            target(" ".join(args.action_arg))
        else:
            target()

        sys.exit(0)

    except Exception as e:  # pylint: disable=broad-except
        sys.stdout.flush()
        print(e, flush=True)
        sys.exit(1)


# Build helpers
class ContainerSession:
    """Builds, tags, logs in to a registry for, and pushes a container image."""

    def __init__(self, container_image, docker_file, container_dir):
        val_arg(isinstance(container_image, str), "Invalid container_image argument. Must be str")
        val_arg(container_image != "", "Empty container_image argument")
        val_arg(isinstance(docker_file, str), "Invalid docker_file argument. Must be str")
        val_arg(docker_file != "", "Empty docker_file argument")
        val_arg(isinstance(container_dir, str), "Invalid container_dir argument. Must be str")
        val_arg(container_dir != "", "Empty container_dir argument")

        self.engine = "docker"
        self.docker_file = docker_file
        self.container_dir = container_dir
        self.container_image = container_image
        self.build_args = []
        self.tags = []
        self.other_build_args = ""

    def build(self):
        """Build the image, tagged with every entry in self.tags."""
        cmd = [f"{self.engine} build -f {self.docker_file} {self.container_dir}"]
        cmd = cmd + [f"--build-arg {x}" for x in self.build_args]
        cmd = cmd + [f"--tag {self.container_image}:{x}" for x in self.tags]
        cmd = cmd + [self.other_build_args]

        bash(" ".join(cmd))

    def login(self, registry, username, password):
        """Log the container engine in to registry with username/password."""
        bash(
            f"{self.engine} login --password-stdin"
            f' -u "{username}"'
            f' "{registry}" <'
            ' <(echo "$REGISTRY_PASSWORD")',
            env={"REGISTRY_PASSWORD": password},
        )

    def push(self):
        """Push every tag in self.tags to the registry."""
        for tag in self.tags:
            bash(f"{self.engine} push {self.container_image}:{tag}")


class PythonSession:
    """Builds and publishes a Python package to PyPI via a dedicated venv."""

    def __init__(self):
        self.venv = "venv"
        self.dist = "dist"
        self.requirements = "requirements.txt"

    def setup(self):
        """Create the venv and install build tooling, plus self.requirements if present."""
        bash(
            f"python3 -m venv {self.venv} && "
            f"source {self.venv}/bin/activate && "
            "python3 -m pip install --upgrade pip && "
            "python3 -m pip install --upgrade setuptools build twine"
        )

        if os.path.isfile(self.requirements):
            bash(
                f"source {self.venv}/bin/activate && "
                f"python3 -m pip install -r {self.requirements}"
            )

    def build(self):
        """Build the sdist/wheel into self.dist."""
        bash(f"source {self.venv}/bin/activate && " "python3 -m build")

    def clean_venv(self):
        """Remove the venv directory."""
        bash(f"rm -rf {self.venv}")

    def clean_dist(self):
        """Remove the dist directory."""
        bash(f"rm -rf {self.dist}")

    def publish(self, username, password):
        """Upload everything in self.dist to PyPI via twine."""
        bash(
            "source ./venv/bin/activate && " f"python3 -m twine upload {self.dist}/*",
            env={"TWINE_USERNAME": username, "TWINE_PASSWORD": password},
        )


class DeployEnvironment:
    """One environment in a DeploySession's promotion chain."""

    def __init__(self, name):
        self.name = name
        self.next_env = ""


class DeploySession:
    """Models an environment promotion chain (e.g. dev -> test -> prod) and opens promotion PRs."""

    def __init__(self):
        self._environments = {}

    def define_env(self, env_name, *, next_env=""):
        """Add env_name to the chain, promoting to next_env (or "" if it is the last)."""
        self._environments[env_name] = DeployEnvironment(env_name)
        self._environments[env_name].next_env = next_env

    def get_env(self, env_name):
        """Look up a previously defined environment by name."""
        if env_name not in self._environments:
            raise DeployError(f"Environment does not exist: {env_name}")

        return self._environments[env_name]

    def promote_forgejo(self, env_name, *, server_url, repo, promote_token):
        """Open a Forgejo/Gitea pull request from env_name's branch to its next environment."""
        val_arg(isinstance(env_name, str), "Invalid env name parameter. Must be str")
        val_arg(isinstance(server_url, str), "Invalid server url parameter. Must be str")
        val_arg(isinstance(repo, str), "Invalid repo parameter. Must be str")
        val_arg(isinstance(promote_token, str), "Invalid promote token parameter. Must be str")

        val_arg(env_name != "", "Empty env name supplied")
        val_arg(server_url != "", "Empty server url")
        val_arg(repo != "", "Empty repo parameter")
        val_arg(promote_token != "", "Empty promote token")

        # Make sure the local repo knows about every branch before we try to
        # open a PR between two of them. Best effort - a stale remote-tracking
        # branch list isn't worth failing the whole promotion over.
        bash("git fetch --all", ignore_rc=True)

        env = self.get_env(env_name)
        next_env = env.next_env

        # Nothing to do if this is the last environment in the chain
        if next_env == "":
            logger.info("No next environment to promote to")
            return

        headers = {
            "Authorization": f"token {promote_token}",
            "Content-Type": "application/json",
        }

        body = textwrap.dedent(f"""\
            {{
                "title": "Promote { env.name } to { next_env }",
                "base": "{ next_env }",
                "head": "{ env.name }",
                "description": "Promote { env.name } to { next_env }"
            }}
            """)

        args = {
            "url": f"{server_url}/api/v1/repos/{repo}/pulls",
            "method": "post",
            "body": body,
            "headers": headers,
            "verify": False,
            # Creating a PR that already exists returns 409, which is fine
            "status_check": [201, 409],
        }

        logger.debug("Url args: %s", args)
        Util.url_request(**args)

    def promote_github(self, env_name, *, repo, promote_token):
        """Open a GitHub pull request from env_name's branch to its next environment."""
        val_arg(isinstance(env_name, str), "Invalid env name parameter. Must be str")
        val_arg(isinstance(repo, str), "Invalid repo parameter. Must be str")
        val_arg(isinstance(promote_token, str), "Invalid promote token parameter. Must be str")

        val_arg(env_name != "", "Empty env name supplied")
        val_arg(repo != "", "Empty repo parameter")
        val_arg(promote_token != "", "Empty promote token")

        # Make sure the local repo knows about every branch before we try to
        # open a PR between two of them. Best effort - a stale remote-tracking
        # branch list isn't worth failing the whole promotion over.
        bash("git fetch --all", ignore_rc=True)

        env = self.get_env(env_name)
        next_env = env.next_env

        # Nothing to do if this is the last environment in the chain
        if next_env == "":
            logger.info("No next environment to promote to")
            return

        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {promote_token}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        body = json.dumps(
            {
                "title": f"Promote {env.name} to {next_env}",
                "base": next_env,
                "head": env.name,
                "body": f"Promote {env.name} to {next_env}",
            }
        )

        args = {
            "url": f"https://api.github.com/repos/{repo}/pulls",
            "method": "post",
            "body": body,
            "headers": headers,
            # Creating a PR that already exists returns 422, which is fine
            "status_check": [201, 422],
        }

        logger.debug("Url args: %s", args)
        Util.url_request(**args)


# Regex for identifying and splitting semver strings
# Reference: https://semver.org/
_SEMVER_REGEX = (
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)(?:-(?P<prerelease>"
    r"(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+"
    r"(?:\.[0-9a-zA-Z-]+)*))?$"
)


class BuildSession:
    """Parses a semver version out of one or more candidate version sources."""

    def __init__(self, version_sources=None):
        if version_sources is None:
            logger.info("Using default version: v0.1.0")
            version_sources = ["v0.1.0"]
        elif not isinstance(version_sources, list):
            version_sources = [version_sources]

        self.update_version(version_sources)

    def update_version(self, sources, *, required=True, discard_regex=None, ignore_regex=None):
        """Find the first source that semver-matches and populate self.v_* from it.

        sources: candidate version strings to try, in order.
        required: raise VersionParseError if none of them match.
        discard_regex: regexes stripped from a source and *not* considered
            part of the version string (e.g. a "refs/tags/" ref prefix).
            Defaults to ["^refs/tags/"].
        ignore_regex: regexes stripped before the semver check, but still
            considered part of the version string (e.g. a "v" tag prefix).
            Defaults to ["^v"].
        """
        val_arg(isinstance(required, bool), "required parameter must be bool")
        val_arg(isinstance(sources, list), "Sources parameter must be a list of strings")
        val_arg(all(isinstance(x, str) for x in sources), "Some values in source are not strings")
        val_arg(
            isinstance(discard_regex, (list, type(None))),
            "discard_regex parameter must be list of string or None",
        )

        if discard_regex is None:
            discard_regex = ["^refs/tags/"]

        if ignore_regex is None:
            ignore_regex = ["^v"]

        for source in sources:
            logger.info("Checking %s", source)

            # Strip any 'discard' components - these are not part of the
            # version string at all (e.g. a git ref prefix)
            post_discard_source = source
            for regex_item in discard_regex:
                post_discard_source = re.sub(regex_item, "", post_discard_source)

            logger.debug("Source after discard strip: %s", post_discard_source)

            # Strip any 'ignore' components - these are part of the version
            # string, but not part of the semver check itself (e.g. a "v" prefix)
            post_ignore_source = post_discard_source
            for regex_item in ignore_regex:
                post_ignore_source = re.sub(regex_item, "", post_ignore_source)

            logger.debug("Source after ignore strip: %s", post_ignore_source)

            result = re.match(_SEMVER_REGEX, post_ignore_source)
            if result is None:
                logger.debug("Source (%s) is not a match", post_ignore_source)
                continue

            logger.info("Semver match on %s", post_ignore_source)

            # Populate the version components from this match
            self.v_source = source
            self.v_stripped = post_discard_source
            self.v_base = post_ignore_source
            self.v_full = "" if result[0] is None else result[0]
            self.v_major = "" if result[1] is None else result[1]
            self.v_minor = "" if result[2] is None else result[2]
            self.v_patch = "" if result[3] is None else result[3]
            self.v_prerelease = "" if result[4] is None else result[4]
            self.v_buildmeta = "" if result[5] is None else result[5]
            self.v_is_prerelease = result[4] is not None

            # Build the major[.minor[.patch]] string, stopping at the first
            # component that is missing
            self.v_mmp = self.v_major
            if self.v_mmp != "" and self.v_minor != "":
                self.v_mmp = self.v_mmp + f".{self.v_minor}"

                if self.v_patch != "":
                    self.v_mmp = self.v_mmp + f".{self.v_patch}"

            return

        # None of the sources matched
        if required:
            raise VersionParseError("No semver matches found")


class TestingSession:
    """Runs a list of shell commands and fails the build if any of them fail."""

    def __init__(self, testing_commands=None):
        val_arg(
            isinstance(testing_commands, (list, type(None))),
            "Invalid testing commands argument. Must be list or None",
        )

        self.testing_commands = testing_commands if testing_commands else []

    def run(self):
        """Run every testing command, then fail the build if any of them failed."""
        result = [bash(x, ignore_rc=True) for x in self.testing_commands]

        if any(x.returncode for x in result):
            Util.fail("Some testing commands failed")


class LintingSession:
    """Runs a list of shell commands and fails the build if any of them fail."""

    def __init__(self, linting_commands=None):
        val_arg(
            isinstance(linting_commands, (list, type(None))),
            "Invalid linting commands argument. Must be list or None",
        )

        self.linting_commands = linting_commands if linting_commands else []

    def run(self):
        """Run every linting command, then fail the build if any of them failed."""
        result = [bash(x, ignore_rc=True) for x in self.linting_commands]

        if any(x.returncode for x in result):
            Util.fail("Some linting commands failed")


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
    def git_sha(cls):
        """Return the current commit's abbreviated SHA."""
        return exec_cmd("git log -1 --format=%h", capture=True).stdout

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
