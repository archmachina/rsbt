"""Tests for rsbt's subprocess helpers: exec_cmd, bash, pwsh, shell."""

import pytest

import rsbt


class TestValArg:
    """Exercises the val_arg validation helper used throughout rsbt."""

    def test_passes_on_truthy_value(self):
        """A truthy value does not raise."""
        rsbt.val_arg(True, "unused")
        rsbt.val_arg("non-empty", "unused")

    def test_raises_on_falsy_value(self):
        """A falsy value raises ArgumentException with the given message."""
        with pytest.raises(rsbt.ArgumentException, match="boom"):
            rsbt.val_arg(False, "boom")

        with pytest.raises(rsbt.ArgumentException, match="empty"):
            rsbt.val_arg("", "empty")


class TestExecCmdValidation:
    """Exercises exec_cmd's upfront argument validation."""

    def test_cmd_must_be_list_or_str(self):
        """A non-list/str cmd raises ArgumentException."""
        with pytest.raises(rsbt.ArgumentException):
            rsbt.exec_cmd(123)

    def test_cmd_list_members_must_be_str(self):
        """A list cmd with a non-str member raises ArgumentException."""
        with pytest.raises(rsbt.ArgumentException):
            rsbt.exec_cmd(["echo", 1])

    def test_shell_must_be_bool(self):
        """A non-bool shell argument raises ArgumentException."""
        with pytest.raises(rsbt.ArgumentException):
            rsbt.exec_cmd("echo hi", shell="yes")

    def test_capture_must_be_bool(self):
        """A non-bool capture argument raises ArgumentException."""
        with pytest.raises(rsbt.ArgumentException):
            rsbt.exec_cmd("echo hi", capture="yes")

    def test_interpreter_must_be_str_or_none(self):
        """A non-str/None interpreter argument raises ArgumentException."""
        with pytest.raises(rsbt.ArgumentException):
            rsbt.exec_cmd("echo hi", interpreter=123)

    def test_env_must_be_dict_of_str(self):
        """A non-dict env, or one with non-str keys/values, raises ArgumentException."""
        with pytest.raises(rsbt.ArgumentException):
            rsbt.exec_cmd("echo hi", env="not-a-dict")

        with pytest.raises(rsbt.ArgumentException):
            rsbt.exec_cmd("echo hi", env={1: "a"})

        with pytest.raises(rsbt.ArgumentException):
            rsbt.exec_cmd("echo hi", env={"a": 1})

    def test_allowed_rc_must_be_list_of_int(self):
        """A non-list allowed_rc, or one with non-int members, raises ArgumentException."""
        with pytest.raises(rsbt.ArgumentException):
            rsbt.exec_cmd("echo hi", allowed_rc="0")

        with pytest.raises(rsbt.ArgumentException):
            rsbt.exec_cmd("echo hi", allowed_rc=["0"])

    def test_ignore_rc_must_be_bool(self):
        """A non-bool ignore_rc argument raises ArgumentException."""
        with pytest.raises(rsbt.ArgumentException):
            rsbt.exec_cmd("echo hi", ignore_rc="yes")


class TestExecCmdExecution:
    """Exercises exec_cmd actually running processes."""

    def test_list_cmd_capture(self):
        """A list cmd runs directly and its stdout can be captured."""
        result = rsbt.exec_cmd(["echo", "hello"], capture=True)

        assert result.returncode == 0
        assert "hello" in result.stdout

    def test_string_cmd_is_split_with_shlex(self):
        """A string cmd (not shell, not interpreter) is split into argv with shlex."""
        result = rsbt.exec_cmd("echo 'hello world'", capture=True)

        assert result.returncode == 0
        assert result.stdout.strip() == "hello world"

    def test_shell_true_runs_via_system_shell(self):
        """shell=True lets the command use shell features like pipes."""
        result = rsbt.exec_cmd("echo hello | tr a-z A-Z", shell=True, capture=True)

        assert result.returncode == 0
        assert result.stdout.strip() == "HELLO"

    def test_env_overlay(self):
        """Extra env vars passed via env= are visible to the child process."""
        result = rsbt.exec_cmd(
            "echo $RSBT_TEST_VAR", shell=True, env={"RSBT_TEST_VAR": "marker"}, capture=True
        )

        assert result.stdout.strip() == "marker"

    def test_default_allowed_rc_raises_on_nonzero(self):
        """A nonzero exit code raises CommandException by default."""
        with pytest.raises(rsbt.CommandException):
            rsbt.exec_cmd("exit 3", shell=True)

    def test_allowed_rc_permits_specific_codes(self):
        """An exit code listed in allowed_rc does not raise."""
        result = rsbt.exec_cmd("exit 3", shell=True, allowed_rc=[0, 3])

        assert result.returncode == 3

    def test_ignore_rc_suppresses_the_exception(self):
        """ignore_rc=True never raises, regardless of the exit code."""
        result = rsbt.exec_cmd("exit 7", shell=True, ignore_rc=True)

        assert result.returncode == 7

    def test_interpreter_feeds_cmd_as_stdin(self):
        """An interpreter runs cmd as a script piped to its stdin."""
        result = rsbt.bash("echo interpreter-ran", capture=True)

        assert result.returncode == 0
        assert result.stdout.strip() == "interpreter-ran"


class TestShortformHelpers:
    """Exercises the bash/pwsh/shell shortform wrappers around exec_cmd."""

    def test_bash_uses_bash_interpreter(self, monkeypatch):
        """bash() calls exec_cmd with interpreter='bash'."""
        captured = {}

        def fake_exec_cmd(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            return rsbt.ExecStatus()

        monkeypatch.setattr(rsbt, "exec_cmd", fake_exec_cmd)

        rsbt.bash("echo hi", capture=True)

        assert captured["cmd"] == "echo hi"
        assert captured["kwargs"] == {"interpreter": "bash", "capture": True}

    def test_pwsh_uses_pwsh_interpreter(self, monkeypatch):
        """pwsh() calls exec_cmd with the expected non-interactive pwsh invocation."""
        captured = {}

        def fake_exec_cmd(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            return rsbt.ExecStatus()

        monkeypatch.setattr(rsbt, "exec_cmd", fake_exec_cmd)

        rsbt.pwsh("Write-Output hi")

        assert captured["cmd"] == "Write-Output hi"
        assert captured["kwargs"] == {"interpreter": "pwsh -noni -c -"}

    def test_shell_sets_shell_true(self, monkeypatch):
        """shell() calls exec_cmd with shell=True."""
        captured = {}

        def fake_exec_cmd(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            return rsbt.ExecStatus()

        monkeypatch.setattr(rsbt, "exec_cmd", fake_exec_cmd)

        rsbt.shell("echo hi | cat")

        assert captured["cmd"] == "echo hi | cat"
        assert captured["kwargs"] == {"shell": True}
