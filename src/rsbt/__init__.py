"""rsbt - Really Simple Build Tool.

A small library of helpers for writing CI/CD build, test, lint, release and
deploy pipelines as plain Python (an ``_entrypoint.py``) instead of large
shell scripts or YAML: a CLI action dispatcher, a subprocess runner, and a
handful of "session" helper classes for the common build/test/release
shapes (Python packages, container images, environment promotion chains).

This module re-exports the package's public API from its submodules, so
callers can keep using ``import rsbt`` / ``from rsbt import <name>``
without needing to know how the implementation is split across files.
"""

import time

from .actions import action, run_action
from .build_session import BuildSession
from .container_session import ContainerSession
from .deploy_session import DeployEnvironment, DeploySession
from .exceptions import (
    ArgumentException,
    BuildFailure,
    CommandException,
    DeployError,
    VersionParseError,
    val_arg,
)
from .exec import ExecStatus, bash, exec_cmd, pwsh, shell
from .linting_session import LintingSession
from .log import configure_logging, logger
from .python_session import PythonSession
from .testing_session import TestingSession
from .util import Util

# Actions registry, populated by the @action decorator and read by
# run_action() (both in .actions). Those look it up as rsbt.actions rather
# than holding their own reference, so that replacing this attribute
# wholesale (as the test suite does, to give each test an empty registry)
# is seen by them too.
actions = {}

__all__ = [
    "action",
    "actions",
    "run_action",
    "BuildSession",
    "DeployEnvironment",
    "DeploySession",
    "ArgumentException",
    "BuildFailure",
    "CommandException",
    "DeployError",
    "VersionParseError",
    "val_arg",
    "ExecStatus",
    "bash",
    "exec_cmd",
    "pwsh",
    "shell",
    "configure_logging",
    "logger",
    "ContainerSession",
    "LintingSession",
    "PythonSession",
    "TestingSession",
    "Util",
    "time",
]
