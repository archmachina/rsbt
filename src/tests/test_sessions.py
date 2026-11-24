"""Tests for rsbt's command-list sessions: PythonSession, ContainerSession,
TestingSession, LintingSession."""

import pytest

import rsbt


@pytest.fixture
def captured_bash_calls(monkeypatch):
    """Replace rsbt.bash with a recorder, returning the list of (cmd, kwargs) calls made."""
    calls = []

    def fake_bash(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return rsbt.ExecStatus()

    monkeypatch.setattr(rsbt, "bash", fake_bash)

    return calls


class TestPythonSession:
    """Exercises PythonSession's venv/build/publish command construction."""

    def test_defaults(self):
        """The default venv/dist/requirements paths are conventional, relative names."""
        pys = rsbt.PythonSession()

        assert pys.venv == "venv"
        assert pys.dist == "dist"
        assert pys.requirements == "requirements.txt"

    def test_setup_without_requirements_file(self, captured_bash_calls, tmp_path, monkeypatch):
        """setup() creates the venv and installs build tooling, but skips a missing requirements."""
        monkeypatch.chdir(tmp_path)
        pys = rsbt.PythonSession()

        pys.setup()

        assert len(captured_bash_calls) == 1
        assert "python3 -m venv venv" in captured_bash_calls[0][0]
        assert "setuptools build twine" in captured_bash_calls[0][0]

    def test_setup_with_requirements_file(self, captured_bash_calls, tmp_path, monkeypatch):
        """setup() also installs self.requirements when the file is present."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "requirements.txt").write_text("requests\n")
        pys = rsbt.PythonSession()

        pys.setup()

        assert len(captured_bash_calls) == 2
        assert "pip install -r requirements.txt" in captured_bash_calls[1][0]

    def test_build_runs_python_build_in_the_venv(self, captured_bash_calls):
        """build() activates the venv and runs "python3 -m build"."""
        rsbt.PythonSession().build()

        assert len(captured_bash_calls) == 1
        assert "source venv/bin/activate" in captured_bash_calls[0][0]
        assert "python3 -m build" in captured_bash_calls[0][0]

    def test_clean_venv_removes_the_venv_dir(self, captured_bash_calls):
        """clean_venv() removes self.venv."""
        rsbt.PythonSession().clean_venv()

        assert captured_bash_calls[0][0] == "rm -rf venv"

    def test_clean_dist_removes_the_dist_dir(self, captured_bash_calls):
        """clean_dist() removes self.dist."""
        rsbt.PythonSession().clean_dist()

        assert captured_bash_calls[0][0] == "rm -rf dist"

    def test_publish_passes_credentials_via_env(self, captured_bash_calls):
        """publish() runs twine upload with the given username/password as env vars."""
        rsbt.PythonSession().publish("__token__", "secret")

        cmd, kwargs = captured_bash_calls[0]
        assert "twine upload dist/*" in cmd
        assert kwargs["env"] == {"TWINE_USERNAME": "__token__", "TWINE_PASSWORD": "secret"}


class TestContainerSession:
    """Exercises ContainerSession's argument validation and command construction."""

    def test_rejects_empty_required_arguments(self):
        """Any empty required constructor argument raises ArgumentException."""
        with pytest.raises(rsbt.ArgumentException):
            rsbt.ContainerSession("", "Dockerfile", ".")

    def test_build_includes_build_args_and_tags(self, captured_bash_calls):
        """build() includes every build_arg and every tag in the docker build command."""
        cs = rsbt.ContainerSession("myimage", "Dockerfile", ".")
        cs.build_args = ["FOO=bar"]
        cs.tags = ["latest", "v1.0.0"]

        cs.build()

        cmd = captured_bash_calls[0][0]
        assert "docker build -f Dockerfile ." in cmd
        assert "--build-arg FOO=bar" in cmd
        assert "--tag myimage:latest" in cmd
        assert "--tag myimage:v1.0.0" in cmd

    def test_login_passes_password_via_env_not_argv(self, captured_bash_calls):
        """login() passes the password through an env var, not as a literal command argument."""
        cs = rsbt.ContainerSession("myimage", "Dockerfile", ".")

        cs.login("registry.example.invalid", "user", "secret-password")

        cmd, kwargs = captured_bash_calls[0]
        assert "secret-password" not in cmd
        assert kwargs["env"] == {"REGISTRY_PASSWORD": "secret-password"}
        assert "registry.example.invalid" in cmd

    def test_push_pushes_every_tag(self, captured_bash_calls):
        """push() runs one docker push per tag."""
        cs = rsbt.ContainerSession("myimage", "Dockerfile", ".")
        cs.tags = ["latest", "v1.0.0"]

        cs.push()

        commands = [cmd for cmd, _ in captured_bash_calls]
        assert commands == ["docker push myimage:latest", "docker push myimage:v1.0.0"]


class TestTestingSession:
    """Exercises TestingSession's command execution and failure handling."""

    def test_rejects_non_list_commands(self):
        """A non-list/None testing_commands argument raises ArgumentException."""
        with pytest.raises(rsbt.ArgumentException):
            rsbt.TestingSession("not-a-list")

    def test_runs_every_command(self, captured_bash_calls):
        """run() runs every testing command, ignoring its own exit code until the end."""
        ts = rsbt.TestingSession(["echo one", "echo two"])

        ts.run()

        commands = [cmd for cmd, kwargs in captured_bash_calls]
        assert commands == ["echo one", "echo two"]
        assert all(kwargs["ignore_rc"] for _, kwargs in captured_bash_calls)

    def test_fails_the_build_if_any_command_failed(self, monkeypatch):
        """run() raises BuildFailure if any command's returncode was nonzero."""

        def fake_bash(cmd, **kwargs):
            status = rsbt.ExecStatus()
            status.returncode = 0 if cmd == "pass" else 1
            return status

        monkeypatch.setattr(rsbt, "bash", fake_bash)

        ts = rsbt.TestingSession(["pass", "fail"])

        with pytest.raises(rsbt.BuildFailure):
            ts.run()

    def test_passes_when_every_command_succeeded(self, monkeypatch):
        """run() does not raise when every command's returncode was 0."""

        def fake_bash(cmd, **kwargs):
            status = rsbt.ExecStatus()
            status.returncode = 0
            return status

        monkeypatch.setattr(rsbt, "bash", fake_bash)

        rsbt.TestingSession(["pass", "also pass"]).run()


class TestLintingSession:
    """Exercises LintingSession's command execution/failure handling (mirrors TestingSession)."""

    def test_rejects_non_list_commands(self):
        """A non-list/None linting_commands argument raises ArgumentException."""
        with pytest.raises(rsbt.ArgumentException):
            rsbt.LintingSession("not-a-list")

    def test_fails_the_build_if_any_command_failed(self, monkeypatch):
        """run() raises BuildFailure if any command's returncode was nonzero."""

        def fake_bash(cmd, **kwargs):
            status = rsbt.ExecStatus()
            status.returncode = 1
            return status

        monkeypatch.setattr(rsbt, "bash", fake_bash)

        with pytest.raises(rsbt.BuildFailure):
            rsbt.LintingSession(["pylint src"]).run()
