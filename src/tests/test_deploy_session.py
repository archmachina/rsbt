"""Tests for rsbt.DeploySession: environment chains and promotion PRs."""

import json

import pytest

import rsbt


class TestEnvironmentChain:
    """Exercises define_env/get_env's bookkeeping."""

    def test_get_env_returns_the_defined_environment(self):
        """get_env() returns the DeployEnvironment created by define_env()."""
        ds = rsbt.DeploySession()
        ds.define_env("dev", next_env="test")

        env = ds.get_env("dev")

        assert env.name == "dev"
        assert env.next_env == "test"

    def test_get_env_defaults_next_env_to_empty(self):
        """define_env() without next_env leaves it as "" (end of the chain)."""
        ds = rsbt.DeploySession()
        ds.define_env("prod")

        assert ds.get_env("prod").next_env == ""

    def test_get_env_raises_for_unknown_environment(self):
        """get_env() on a name that was never defined raises DeployError."""
        ds = rsbt.DeploySession()

        with pytest.raises(rsbt.DeployError):
            ds.get_env("does-not-exist")


@pytest.fixture
def no_git_fetch(monkeypatch):
    """Stub out the "git fetch --all" call promote_* makes before opening a PR."""
    monkeypatch.setattr(rsbt, "bash", lambda cmd, **kwargs: rsbt.ExecStatus())


@pytest.fixture
def captured_url_request(monkeypatch):
    """Replace Util.url_request with a recorder, returning the captured kwargs dict."""
    captured = {}

    def fake_url_request(**kwargs):
        captured.update(kwargs)

        class FakeResponse:  # pylint: disable=too-few-public-methods
            """Stand-in response, only status_code is used by the callers under test."""

            status_code = 201

        return FakeResponse()

    monkeypatch.setattr(
        rsbt.Util, "url_request", classmethod(lambda cls, **kwargs: fake_url_request(**kwargs))
    )

    return captured


class TestPromoteForgejo:
    """Exercises promote_forgejo's request construction."""

    def test_no_next_env_skips_the_request(self, no_git_fetch, captured_url_request):
        """With no next environment, promote_forgejo() does nothing."""
        ds = rsbt.DeploySession()
        ds.define_env("prod")

        ds.promote_forgejo(
            "prod", server_url="https://forgejo.invalid", repo="org/repo", promote_token="tok"
        )

        assert captured_url_request == {}

    def test_opens_a_pr_to_the_next_environment(self, no_git_fetch, captured_url_request):
        """promote_forgejo() posts the expected PR body/headers to the Forgejo API."""
        ds = rsbt.DeploySession()
        ds.define_env("dev", next_env="test")

        ds.promote_forgejo(
            "dev", server_url="https://forgejo.invalid", repo="org/repo", promote_token="tok"
        )

        assert captured_url_request["url"] == "https://forgejo.invalid/api/v1/repos/org/repo/pulls"
        assert captured_url_request["method"] == "post"
        assert captured_url_request["status_check"] == [201, 409]
        assert captured_url_request["headers"]["Authorization"] == "token tok"

        body = json.loads(captured_url_request["body"])
        assert body["base"] == "test"
        assert body["head"] == "dev"

    def test_validates_required_arguments(self, no_git_fetch):
        """An empty required argument raises ArgumentException before any request is made."""
        ds = rsbt.DeploySession()
        ds.define_env("dev", next_env="test")

        with pytest.raises(rsbt.ArgumentException):
            ds.promote_forgejo("dev", server_url="", repo="org/repo", promote_token="tok")


class TestPromoteGithub:
    """Exercises promote_github's request construction."""

    def test_no_next_env_skips_the_request(self, no_git_fetch, captured_url_request):
        """With no next environment, promote_github() does nothing."""
        ds = rsbt.DeploySession()
        ds.define_env("prod")

        ds.promote_github("prod", repo="org/repo", promote_token="tok")

        assert captured_url_request == {}

    def test_opens_a_pr_to_the_next_environment(self, no_git_fetch, captured_url_request):
        """promote_github() posts the expected PR body/headers to the GitHub API."""
        ds = rsbt.DeploySession()
        ds.define_env("dev", next_env="test")

        ds.promote_github("dev", repo="org/repo", promote_token="tok")

        assert captured_url_request["url"] == "https://api.github.com/repos/org/repo/pulls"
        assert captured_url_request["status_check"] == [201, 422]
        assert captured_url_request["headers"]["Authorization"] == "token tok"

        body = json.loads(captured_url_request["body"])
        assert body["base"] == "test"
        assert body["head"] == "dev"
