#!/usr/bin/env python3
"""Example _entrypoint.py: promote a deploy through a dev -> test -> prod chain with rsbt.

Reference only - see examples/README.md. Not part of the rsbt package and
not run by this repo's own CI.
"""

import os

import rsbt
from rsbt import action

# DeploySession - models the environment promotion chain. Each environment
# is deployed from its own branch; a successful deploy opens a pull request
# promoting that branch's changes into the next environment's branch.
ds = rsbt.DeploySession()
ds.define_env("dev", next_env="test")
ds.define_env("test", next_env="prod")
ds.define_env("prod")


@action
def apply():
    """Deploy the environment named by $DEPLOY_ENV."""
    # The actual deploy step (e.g. running an Ansible playbook against this
    # environment) belongs here. This example only demonstrates the
    # promotion step that follows a successful deploy, below.
    env_name = os.environ["DEPLOY_ENV"]
    rsbt.logger.info("Deployed %s", env_name)


@action
def promote():
    """Open the pull request promoting $DEPLOY_ENV to its next environment."""
    # Open (or no-op past) the PR from this environment's branch to the
    # next one in the chain, via a Forgejo/Gitea server
    env_name = os.environ["DEPLOY_ENV"]
    ds.promote_forgejo(
        env_name,
        server_url=os.environ["FORGEJO_SERVER_URL"],
        repo=os.environ["GITEA_REPOSITORY"],
        promote_token=os.environ["PROMOTE_TOKEN"],
    )


rsbt.configure_logging(debug=True)
rsbt.run_action()
