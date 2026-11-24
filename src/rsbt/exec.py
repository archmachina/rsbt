"""Subprocess execution: exec_cmd and its bash/pwsh/shell shortform wrappers."""

import os
import shlex
import subprocess
import sys

import rsbt

from .exceptions import CommandException, val_arg
from .log import logger


def bash(cmd, **kwargs):
    """Run cmd as a bash script, via exec_cmd's interpreter mode."""
    # Call through the rsbt namespace (not the exec_cmd name below directly)
    # so that tests patching rsbt.exec_cmd affect this call too.
    return rsbt.exec_cmd(cmd, interpreter="bash", **kwargs)


def pwsh(cmd, **kwargs):
    """Run cmd as a PowerShell script, via exec_cmd's interpreter mode."""
    return rsbt.exec_cmd(cmd, interpreter="pwsh -noni -c -", **kwargs)


def shell(cmd, **kwargs):
    """Run cmd through the system shell (equivalent to subprocess's shell=True)."""
    return rsbt.exec_cmd(cmd, shell=True, **kwargs)


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
