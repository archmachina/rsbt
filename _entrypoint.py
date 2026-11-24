#!/usr/bin/env python3

import os

import rsbt
from rsbt import action, Util

# BuildSession - tracks/parses the version for this build: a rolling
# pre-release version until a real "v*" tag drives the release action.
bs = rsbt.BuildSession([f"0.1.0-rolling+{Util.git_sha()}"])

# PythonSession - builds/publishes src/rsbt as a PyPI package
pys = rsbt.PythonSession()

# Linting session
ls = rsbt.LintingSession([
    "pylint src",
    "black --diff src",
])

# Testing Session - runs the Dockerfile's "testing" stage via dfbar itself
ts = rsbt.TestingSession([
    "dfbar -f ./src/Dockerfile -m test ./src",
])


@action
def build():
    # BUILD_VERSION is referenced by setup.py
    os.environ["BUILD_VERSION"] = bs.v_mmp
    pys.setup()
    pys.build()


@action
def test():
    ts.run()


@action
def lint():
    ls.run()


@action
def clean():
    pys.clean_venv()
    pys.clean_dist()


@action
def pr_main():
    # Run a build and test for PRs to the main branch
    build()
    test()


@action
def push_main():
    # Run a build and test for pushes to the main branch
    build()
    test()


@action
def release():
    # Make sure we have a github version to base the release on
    ref = os.environ.get("GITHUB_REF", "")
    if ref == "":
        Util.fail("Missing github version reference")

    bs.update_version([ref])

    build()
    test()

    # Publish the package to PyPI
    pys.publish("__token__", os.environ["PYPI_TOKEN"])

    # Create a github release for this tag
    Util.github_release(
        bs.v_stripped,
        name=f"Version {bs.v_full}",
        prerelease=bs.v_is_prerelease,
        github_token=os.environ["GITHUB_TOKEN"],
        repo=os.environ["GITHUB_REPOSITORY"],
    )


# run_action will run the action and also control the exit of
# the process (i.e. does not return)
rsbt.configure_logging(debug=True)
rsbt.run_action()
