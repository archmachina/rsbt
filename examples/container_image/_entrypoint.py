#!/usr/bin/env python3
"""Example _entrypoint.py: build, test, lint and release a container image with rsbt.

Reference only - see examples/README.md. Not part of the rsbt package and
not run by this repo's own CI.
"""

import os

import rsbt
from rsbt import action, Util

# BuildSession - tracks/parses the version for this build
bs = rsbt.BuildSession([f"0.1.0-rolling+{Util.git_sha()}"])

# ContainerSession - builds/tags/pushes src/Dockerfile as a container image
cs = rsbt.ContainerSession("registry.example.invalid/myorg/myimage", "src/Dockerfile", "src")

# Testing Session - runs the Dockerfile's "testing" stage via dfbar itself
ts = rsbt.TestingSession(
    [
        "dfbar -f ./src/Dockerfile -m test ./src",
    ]
)

# Linting session
ls = rsbt.LintingSession(
    [
        "hadolint src/Dockerfile",
    ]
)


@action
def build():
    """Build the container image."""
    cs.build()


@action
def test():
    """Run the testing stage of the Dockerfile."""
    ts.run()


@action
def lint():
    """Lint the Dockerfile."""
    ls.run()


@action
def pr_main():
    """Build and test a PR into main."""
    # A PR into main just needs to build and test cleanly
    build()
    test()


def _login_and_push():
    """Log in to the registry and push every tag in cs.tags."""
    cs.login(
        os.environ["REGISTRY_URL"],
        os.environ["REGISTRY_USERNAME"],
        os.environ["REGISTRY_PASSWORD"],
    )
    cs.push()


@action
def push_main():
    """Build, test and push a rolling release on every push to main."""
    # Rolling release: every push to main updates "main" and "latest"
    cs.tags = ["main", "latest"]
    build()
    test()
    _login_and_push()


@action
def release():
    """Build, test, push and tag a versioned release."""
    # Make sure we have a github version to base the release on
    ref = os.environ.get("GITHUB_REF", "")
    if ref == "":
        Util.fail("Missing github version reference")

    bs.update_version([ref])

    cs.tags = [bs.v_mmp, "latest"]
    build()
    test()
    _login_and_push()

    # Create a github release for this tag
    Util.github_release(
        bs.v_stripped,
        name=f"Version {bs.v_full}",
        prerelease=bs.v_is_prerelease,
        github_token=os.environ["GITHUB_TOKEN"],
        repo=os.environ["GITHUB_REPOSITORY"],
    )


rsbt.configure_logging(debug=True)
rsbt.run_action()
