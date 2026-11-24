"""Exceptions raised by rsbt, and the shared argument-validation helper."""


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
