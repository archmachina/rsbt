"""LintingSession: runs a list of shell commands and fails the build if any of them fail."""

import rsbt

from .exceptions import val_arg
from .util import Util


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
        results = [rsbt.bash(x, ignore_rc=True) for x in self.linting_commands]

        # Report exactly which commands failed, not just that something did
        failed_commands = [
            cmd for cmd, result in zip(self.linting_commands, results) if result.returncode
        ]

        if failed_commands:
            Util.fail(f"Linting commands failed: {failed_commands}")
