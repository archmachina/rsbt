"""DeploySession: models an environment promotion chain and opens promotion PRs."""

import json
import textwrap

import rsbt

from .exceptions import DeployError, val_arg
from .log import logger
from .util import Util


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
        rsbt.bash("git fetch --all", ignore_rc=True)

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
        rsbt.bash("git fetch --all", ignore_rc=True)

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
