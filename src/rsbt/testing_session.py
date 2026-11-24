"""TestingSession: runs a list of shell commands and fails the build if any of them fail."""

import rsbt

from .exceptions import val_arg
from .util import Util


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
        results = [rsbt.bash(x, ignore_rc=True) for x in self.testing_commands]

        # Report exactly which commands failed, not just that something did
        failed_commands = [
            cmd for cmd, result in zip(self.testing_commands, results) if result.returncode
        ]

        if failed_commands:
            Util.fail(f"Testing commands failed: {failed_commands}")
