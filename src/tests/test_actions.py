"""Tests for rsbt's action registration/dispatch: action, run_action, configure_logging."""

import logging

import pytest

import rsbt


@pytest.fixture(autouse=True)
def clean_actions_registry(monkeypatch):
    """Give every test its own empty actions registry, so tests can't see each other's actions."""
    monkeypatch.setattr(rsbt, "actions", {})


class TestActionDecorator:
    """Exercises the @action registration decorator."""

    def test_registers_by_function_name(self):
        """@action registers the function under its own __name__."""

        @rsbt.action
        def sample_action():
            pass

        assert rsbt.actions["sample_action"] is sample_action

    def test_returns_the_original_function(self):
        """@action does not wrap the function - it is still directly callable."""

        @rsbt.action
        def sample_action():
            return "ran"

        assert sample_action() == "ran"


class TestRunAction:
    """Exercises run_action's CLI parsing and dispatch."""

    def test_dispatches_to_a_no_arg_action(self, monkeypatch):
        """A registered action with no parameters is called with no arguments."""
        calls = []

        @rsbt.action
        def noop():
            calls.append(())

        monkeypatch.setattr("sys.argv", ["entrypoint", "noop"])

        with pytest.raises(SystemExit) as exc_info:
            rsbt.run_action()

        assert exc_info.value.code == 0
        assert calls == [()]

    def test_dispatches_to_an_action_with_an_argument(self, monkeypatch):
        """Trailing argv tokens are joined with spaces and passed as the action's one argument."""
        calls = []

        @rsbt.action
        def echo(arg):
            calls.append(arg)

        monkeypatch.setattr("sys.argv", ["entrypoint", "echo", "hello", "world"])

        with pytest.raises(SystemExit) as exc_info:
            rsbt.run_action()

        assert exc_info.value.code == 0
        assert calls == ["hello world"]

    def test_unknown_action_exits_with_failure(self, monkeypatch, capsys):
        """An action name that was never registered exits 1 with an error message."""
        monkeypatch.setattr("sys.argv", ["entrypoint", "does-not-exist"])

        with pytest.raises(SystemExit) as exc_info:
            rsbt.run_action()

        assert exc_info.value.code == 1
        assert "Unknown action" in capsys.readouterr().out

    def test_exception_inside_action_exits_with_failure(self, monkeypatch, capsys):
        """An exception raised by the action itself is caught and exits 1."""

        @rsbt.action
        def boom():
            raise rsbt.BuildFailure("kaboom")

        monkeypatch.setattr("sys.argv", ["entrypoint", "boom"])

        with pytest.raises(SystemExit) as exc_info:
            rsbt.run_action()

        assert exc_info.value.code == 1
        assert "kaboom" in capsys.readouterr().out

    def test_debug_flag_raises_the_log_level(self, monkeypatch):
        """-v (or -d) switches the root logger to DEBUG before the action runs."""

        @rsbt.action
        def noop():
            pass

        monkeypatch.setattr("sys.argv", ["entrypoint", "-v", "noop"])

        with pytest.raises(SystemExit):
            rsbt.run_action()

        assert logging.getLogger().getEffectiveLevel() == logging.DEBUG


class TestConfigureLogging:
    """Exercises configure_logging's level selection."""

    def test_default_is_info(self):
        """With debug=False (the default), the root logger is set to INFO."""
        rsbt.configure_logging()

        assert logging.getLogger().getEffectiveLevel() == logging.INFO

    def test_debug_true_sets_debug_level(self):
        """With debug=True, the root logger is set to DEBUG."""
        rsbt.configure_logging(debug=True)

        assert logging.getLogger().getEffectiveLevel() == logging.DEBUG
