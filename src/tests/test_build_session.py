"""Tests for rsbt.BuildSession's semver parsing."""

import pytest

import rsbt


class TestDefaultConstruction:
    """Exercises BuildSession's constructor defaults and basic forwarding."""

    def test_no_sources_defaults_to_v0_1_0(self):
        """With no version_sources, the default "v0.1.0" is used."""
        bs = rsbt.BuildSession()

        assert bs.v_mmp == "0.1.0"

    def test_single_string_source_is_wrapped_in_a_list(self):
        """A single string (not a list) is accepted the same as a one-item list."""
        bs = rsbt.BuildSession("v1.2.3")

        assert bs.v_mmp == "1.2.3"


class TestSemverParsing:
    """Exercises update_version's parsing of individual semver components."""

    def test_plain_version(self):
        """A bare major.minor.patch populates every mmp component."""
        bs = rsbt.BuildSession("v1.2.3")

        assert bs.v_major == "1"
        assert bs.v_minor == "2"
        assert bs.v_patch == "3"
        assert bs.v_mmp == "1.2.3"
        assert bs.v_prerelease == ""
        assert bs.v_buildmeta == ""
        assert bs.v_is_prerelease is False

    def test_prerelease_component(self):
        """A -rc1 style suffix is captured as the prerelease component."""
        bs = rsbt.BuildSession("v1.2.3-rc1")

        assert bs.v_prerelease == "rc1"
        assert bs.v_is_prerelease is True
        # Prerelease does not affect the plain major.minor.patch string
        assert bs.v_mmp == "1.2.3"

    def test_buildmetadata_component(self):
        """A +buildmeta suffix is captured separately from the prerelease."""
        bs = rsbt.BuildSession("v1.2.3+abc123")

        assert bs.v_buildmeta == "abc123"
        assert bs.v_is_prerelease is False

    def test_prerelease_and_buildmetadata_together(self):
        """Both a prerelease and buildmetadata suffix can be present at once."""
        bs = rsbt.BuildSession("v0.1.0-rolling+deadbee")

        assert bs.v_major == "0"
        assert bs.v_minor == "1"
        assert bs.v_patch == "0"
        assert bs.v_prerelease == "rolling"
        assert bs.v_buildmeta == "deadbee"
        assert bs.v_is_prerelease is True

    def test_v_full_is_the_whole_matched_version(self):
        """v_full is the complete matched version string, after the ignore_regex strip."""
        bs = rsbt.BuildSession("v1.2.3-rc1+meta")

        assert bs.v_full == "1.2.3-rc1+meta"

    def test_v_stripped_vs_v_base(self):
        """v_stripped only removes discard_regex; v_base also removes ignore_regex."""
        bs = rsbt.BuildSession("refs/tags/v1.2.3")

        assert bs.v_source == "refs/tags/v1.2.3"
        assert bs.v_stripped == "v1.2.3"
        assert bs.v_base == "1.2.3"


class TestSourceSelection:
    """Exercises how update_version picks among multiple candidate sources."""

    def test_first_matching_source_wins(self):
        """Sources are tried in order, and the first semver match is used."""
        bs = rsbt.BuildSession(["not-a-version", "v2.0.0", "v3.0.0"])

        assert bs.v_mmp == "2.0.0"
        assert bs.v_source == "v2.0.0"

    def test_no_match_and_not_required_leaves_state_unset(self):
        """required=False with no matching source does not raise."""
        bs = rsbt.BuildSession("v1.0.0")

        bs.update_version(["not-a-version"], required=False)

        # Nothing raised; the previous match (from the constructor) is left in place
        assert bs.v_mmp == "1.0.0"

    def test_no_match_and_required_raises(self):
        """required=True (the default) with no matching source raises VersionParseError."""
        bs = rsbt.BuildSession("v1.0.0")

        with pytest.raises(rsbt.VersionParseError):
            bs.update_version(["not-a-version"])

    def test_custom_discard_regex(self):
        """A custom discard_regex replaces the default "^refs/tags/" stripping."""
        bs = rsbt.BuildSession()

        bs.update_version(["build-v1.2.3"], discard_regex=["^build-"])

        assert bs.v_stripped == "v1.2.3"
        assert bs.v_mmp == "1.2.3"

    def test_custom_ignore_regex(self):
        """A custom ignore_regex replaces the default "^v" stripping."""
        bs = rsbt.BuildSession()

        bs.update_version(["ver1.2.3"], ignore_regex=["^ver"])

        assert bs.v_base == "1.2.3"
        assert bs.v_mmp == "1.2.3"
