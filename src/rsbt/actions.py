"""CLI action dispatch: the @action decorator and run_action.

The actions registry itself (rsbt.actions) lives in rsbt/__init__.py, not
here - action() and run_action() look it up via the rsbt module rather than
holding their own reference, so that replacing rsbt.actions (as the test
suite does, to give each test an empty registry) is also seen here.
"""

import argparse
import inspect
import sys

import rsbt

from .exceptions import ArgumentException
from .log import configure_logging


def action(func):
    """Register func as a named CLI action, keyed by its function name."""
    rsbt.actions[func.__name__] = func

    return func


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

        if args.action not in rsbt.actions:
            raise ArgumentException(f"Unknown action {args.action}")

        # Run the action, passing the joined action argument only if the
        # action function accepts one
        target = rsbt.actions[args.action]
        if len(inspect.signature(target).parameters) > 0:
            target(" ".join(args.action_arg))
        else:
            target()

        sys.exit(0)

    except Exception as e:  # pylint: disable=broad-except
        sys.stdout.flush()
        print(e, flush=True)
        sys.exit(1)
