"""Tests for rsbt.Util: git metadata, HTTP requests with retry, GitHub releases."""

import pytest
import requests

import rsbt


class FakeResponse:
    """Minimal stand-in for requests.Response, enough for Util.url_request's needs."""

    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        """Raise requests.HTTPError if this response's status code is an error."""
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


class TestFail:
    """Exercises Util.fail."""

    def test_raises_build_failure(self):
        """fail(message) always raises BuildFailure(message)."""
        with pytest.raises(rsbt.BuildFailure, match="boom"):
            rsbt.Util.fail("boom")


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    """A throwaway git repo with one commit, as the current working directory."""
    monkeypatch.chdir(tmp_path)
    rsbt.exec_cmd(["git", "init"])
    (tmp_path / "file.txt").write_text("content\n")
    rsbt.exec_cmd(["git", "add", "file.txt"])
    rsbt.exec_cmd(["git", "commit", "-m", "Initial commit"])

    return tmp_path


def _create_merge_commit(git_repo):
    """Branch, commit, and merge (--no-ff) into git_repo; return the merge commit's short SHA."""
    rsbt.exec_cmd(["git", "checkout", "-b", "feature"])
    (git_repo / "feature.txt").write_text("feature\n")
    rsbt.exec_cmd(["git", "add", "feature.txt"])
    rsbt.exec_cmd(["git", "commit", "-m", "Feature commit"])

    # Back to the branch we started from, then force a merge commit even
    # though this merge could have fast-forwarded
    rsbt.exec_cmd(["git", "checkout", "-"])
    rsbt.exec_cmd(["git", "merge", "--no-ff", "feature", "-m", "Merge commit"])

    return rsbt.exec_cmd(["git", "log", "-1", "--format=%h"], capture=True).stdout.strip()


class TestGitHelpers:
    """Exercises Util's git metadata helpers against a real throwaway repo."""

    def test_git_sha_matches_head(self, git_repo):
        """git_sha() returns the same short SHA git itself reports for HEAD."""
        sha = rsbt.Util.git_sha().strip()
        expected = rsbt.exec_cmd(
            ["git", "rev-parse", "--short", "HEAD"], capture=True
        ).stdout.strip()

        assert sha == expected
        assert sha != ""

    def test_git_sha_rejects_non_bool_ignore_merges(self, git_repo):
        """A non-bool ignore_merges argument raises ArgumentException."""
        with pytest.raises(rsbt.ArgumentException):
            rsbt.Util.git_sha(ignore_merges="yes")

    def test_git_sha_with_ignore_merges_false_returns_head_even_if_a_merge(self, git_repo):
        """With ignore_merges=False (the default), HEAD's own SHA is returned, merge or not."""
        merge_sha = _create_merge_commit(git_repo)

        assert rsbt.Util.git_sha().strip() == merge_sha
        assert rsbt.Util.git_sha(ignore_merges=False).strip() == merge_sha

    def test_git_sha_with_ignore_merges_true_skips_a_leading_merge_commit(self, git_repo):
        """With ignore_merges=True, a merge commit at HEAD is skipped for the commit before it."""
        _create_merge_commit(git_repo)

        non_merge_sha = rsbt.exec_cmd(
            ["git", "log", "-1", "--no-merges", "--format=%h"], capture=True
        ).stdout.strip()

        assert rsbt.Util.git_sha(ignore_merges=True).strip() == non_merge_sha

    def test_git_latest_tag_empty_when_untagged(self, git_repo):
        """git_latest_tag() returns an empty string when the repo has no tags."""
        assert rsbt.Util.git_latest_tag().strip() == ""

    def test_git_latest_tag_after_tagging(self, git_repo):
        """git_latest_tag() returns the tag once one has been created."""
        rsbt.exec_cmd(["git", "tag", "v1.0.0"])

        assert rsbt.Util.git_latest_tag().strip() == "v1.0.0"

    def test_git_notes_since_tag_with_no_tag(self, git_repo):
        """With tag=None, every commit subject in the history is returned."""
        (git_repo / "file2.txt").write_text("more\n")
        rsbt.exec_cmd(["git", "add", "file2.txt"])
        rsbt.exec_cmd(["git", "commit", "-m", "Second commit"])

        notes = rsbt.Util.git_notes_since_tag()

        assert "Initial commit" in notes
        assert "Second commit" in notes

    def test_git_notes_since_tag_excludes_commits_up_to_the_tag(self, git_repo):
        """With a tag given, only commits after that tag are returned."""
        rsbt.exec_cmd(["git", "tag", "v1.0.0"])

        (git_repo / "file2.txt").write_text("more\n")
        rsbt.exec_cmd(["git", "add", "file2.txt"])
        rsbt.exec_cmd(["git", "commit", "-m", "Second commit"])

        notes = rsbt.Util.git_notes_since_tag("v1.0.0")

        assert "Second commit" in notes
        assert "Initial commit" not in notes


class TestUrlRequestValidation:
    """Exercises url_request's upfront argument validation."""

    def test_url_must_be_str(self):
        """A non-str url raises ArgumentException."""
        with pytest.raises(rsbt.ArgumentException):
            rsbt.Util.url_request(123)

    def test_body_must_be_str_or_none(self):
        """A non-str/None body raises ArgumentException."""
        with pytest.raises(rsbt.ArgumentException):
            rsbt.Util.url_request("https://example.invalid", body=123)

    def test_status_check_must_be_int_list_or_none(self):
        """A status_check that is not an int, list of int, or None raises ArgumentException."""
        with pytest.raises(rsbt.ArgumentException):
            rsbt.Util.url_request("https://example.invalid", status_check="200")

    def test_headers_must_be_str_to_str_dict(self):
        """Non-str header keys/values raise ArgumentException."""
        with pytest.raises(rsbt.ArgumentException):
            rsbt.Util.url_request("https://example.invalid", headers={1: "a"})

        with pytest.raises(rsbt.ArgumentException):
            rsbt.Util.url_request("https://example.invalid", headers={"a": 1})


class TestUrlRequestSuccess:
    """Exercises url_request's happy-path response handling."""

    def test_default_status_check_accepts_2xx(self, monkeypatch):
        """With no status_check, a 2xx response is returned as-is."""
        monkeypatch.setattr(requests, "request", lambda **kwargs: FakeResponse(200))

        response = rsbt.Util.url_request("https://example.invalid")

        assert response.status_code == 200

    def test_default_status_check_raises_on_4xx(self, monkeypatch):
        """With no status_check, a non-retryable 4xx response raises via raise_for_status()."""
        monkeypatch.setattr(requests, "request", lambda **kwargs: FakeResponse(404))

        with pytest.raises(requests.HTTPError):
            rsbt.Util.url_request("https://example.invalid")

    def test_explicit_status_check_accepts_a_normally_bad_code(self, monkeypatch):
        """A status_check list lets through a code that would otherwise be an error (e.g. 409)."""
        monkeypatch.setattr(requests, "request", lambda **kwargs: FakeResponse(409))

        response = rsbt.Util.url_request("https://example.invalid", status_check=[201, 409])

        assert response.status_code == 409

    def test_explicit_status_check_rejects_an_unlisted_code(self, monkeypatch):
        """A non-retryable status code outside status_check raises HTTPError."""
        monkeypatch.setattr(requests, "request", lambda **kwargs: FakeResponse(403))

        with pytest.raises(requests.HTTPError):
            rsbt.Util.url_request("https://example.invalid", status_check=[201])

    def test_int_status_check_is_wrapped_in_a_list(self, monkeypatch):
        """A bare int status_check behaves the same as a single-item list."""
        monkeypatch.setattr(requests, "request", lambda **kwargs: FakeResponse(201))

        response = rsbt.Util.url_request("https://example.invalid", status_check=201)

        assert response.status_code == 201


class TestUrlRequestRetry:
    """Exercises url_request's retry-with-backoff behaviour on transient failures."""

    @pytest.fixture(autouse=True)
    def no_real_sleep(self, monkeypatch):
        """Replace time.sleep so retry tests don't actually wait out the backoff."""
        monkeypatch.setattr(rsbt.time, "sleep", lambda seconds: None)

    def test_retries_connection_errors_then_succeeds(self, monkeypatch):
        """A connection error is retried, and a later successful attempt is returned."""
        attempts = []

        def fake_request(**kwargs):
            attempts.append(1)
            if len(attempts) < 3:
                raise requests.exceptions.ConnectionError("refused")
            return FakeResponse(200)

        monkeypatch.setattr(requests, "request", fake_request)

        response = rsbt.Util.url_request("https://example.invalid")

        assert response.status_code == 200
        assert len(attempts) == 3

    def test_retries_a_5xx_then_succeeds(self, monkeypatch):
        """A 503 response is retried as transient, and a later 200 is returned."""
        attempts = []

        def fake_request(**kwargs):
            attempts.append(1)
            if len(attempts) < 2:
                return FakeResponse(503)
            return FakeResponse(200)

        monkeypatch.setattr(requests, "request", fake_request)

        response = rsbt.Util.url_request("https://example.invalid")

        assert response.status_code == 200
        assert len(attempts) == 2

    def test_exhausting_all_attempts_raises(self, monkeypatch):
        """A connection error on every attempt raises after the last one."""

        def always_fails(**kwargs):
            raise requests.exceptions.ConnectionError("refused")

        monkeypatch.setattr(requests, "request", always_fails)

        with pytest.raises(requests.exceptions.ConnectionError):
            rsbt.Util.url_request("https://example.invalid")

    def test_a_4xx_outside_status_check_is_not_retried(self, monkeypatch):
        """A definitive (non-transient) bad status code fails on the first attempt."""
        attempts = []

        def fake_request(**kwargs):
            attempts.append(1)
            return FakeResponse(403)

        monkeypatch.setattr(requests, "request", fake_request)

        with pytest.raises(requests.HTTPError):
            rsbt.Util.url_request("https://example.invalid", status_check=[201])

        assert len(attempts) == 1

    def test_an_accepted_status_check_code_is_not_retried_even_if_normally_transient(
        self, monkeypatch
    ):
        """A status_check-accepted code (e.g. 429 accepted on purpose) returns immediately."""
        attempts = []

        def fake_request(**kwargs):
            attempts.append(1)
            return FakeResponse(429)

        monkeypatch.setattr(requests, "request", fake_request)

        response = rsbt.Util.url_request("https://example.invalid", status_check=[200, 429])

        assert response.status_code == 429
        assert len(attempts) == 1


class TestGithubRelease:
    """Exercises Util.github_release's argument validation and request construction."""

    def test_validates_required_arguments(self):
        """Empty required string arguments raise ArgumentException."""
        with pytest.raises(rsbt.ArgumentException):
            rsbt.Util.github_release("", name="n", prerelease=False, github_token="t", repo="r")

    def test_posts_expected_request(self, monkeypatch):
        """A release is created via a POST to the releases endpoint, with the expected body."""
        captured = {}

        def fake_url_request(**kwargs):
            captured.update(kwargs)
            return FakeResponse(201)

        monkeypatch.setattr(
            rsbt.Util, "url_request", classmethod(lambda cls, **kwargs: fake_url_request(**kwargs))
        )

        rsbt.Util.github_release(
            "v1.2.3", name="Version 1.2.3", prerelease=False, github_token="tok", repo="org/repo"
        )

        assert captured["url"] == "https://api.github.com/repos/org/repo/releases"
        assert captured["method"] == "post"
        assert captured["status_check"] == [201]
        assert "tok" in captured["headers"]["Authorization"]
        assert '"tag_name": "v1.2.3"' in captured["body"]
        assert '"prerelease": false' in captured["body"]
