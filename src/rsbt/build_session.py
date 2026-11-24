"""BuildSession: parses a semver version out of one or more candidate version sources."""

import re

from .exceptions import VersionParseError, val_arg
from .log import logger

# Regex for identifying and splitting semver strings
# Reference: https://semver.org/
_SEMVER_REGEX = (
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)(?:-(?P<prerelease>"
    r"(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+"
    r"(?:\.[0-9a-zA-Z-]+)*))?$"
)


class BuildSession:
    """Parses a semver version out of one or more candidate version sources."""

    def __init__(self, version_sources=None):
        if version_sources is None:
            logger.info("Using default version: v0.1.0")
            version_sources = ["v0.1.0"]
        elif not isinstance(version_sources, list):
            version_sources = [version_sources]

        self.update_version(version_sources)

    def update_version(self, sources, *, required=True, discard_regex=None, ignore_regex=None):
        """Find the first source that semver-matches and populate self.v_* from it.

        sources: candidate version strings to try, in order.
        required: raise VersionParseError if none of them match.
        discard_regex: regexes stripped from a source and *not* considered
            part of the version string (e.g. a "refs/tags/" ref prefix).
            Defaults to ["^refs/tags/"].
        ignore_regex: regexes stripped before the semver check, but still
            considered part of the version string (e.g. a "v" tag prefix).
            Defaults to ["^v"].
        """
        val_arg(isinstance(required, bool), "required parameter must be bool")
        val_arg(isinstance(sources, list), "Sources parameter must be a list of strings")
        val_arg(all(isinstance(x, str) for x in sources), "Some values in source are not strings")
        val_arg(
            isinstance(discard_regex, (list, type(None))),
            "discard_regex parameter must be list of string or None",
        )

        if discard_regex is None:
            discard_regex = ["^refs/tags/"]

        if ignore_regex is None:
            ignore_regex = ["^v"]

        for source in sources:
            logger.info("Checking %s", source)

            # Strip any 'discard' components - these are not part of the
            # version string at all (e.g. a git ref prefix)
            post_discard_source = source
            for regex_item in discard_regex:
                post_discard_source = re.sub(regex_item, "", post_discard_source)

            logger.debug("Source after discard strip: %s", post_discard_source)

            # Strip any 'ignore' components - these are part of the version
            # string, but not part of the semver check itself (e.g. a "v" prefix)
            post_ignore_source = post_discard_source
            for regex_item in ignore_regex:
                post_ignore_source = re.sub(regex_item, "", post_ignore_source)

            logger.debug("Source after ignore strip: %s", post_ignore_source)

            result = re.match(_SEMVER_REGEX, post_ignore_source)
            if result is None:
                logger.debug("Source (%s) is not a match", post_ignore_source)
                continue

            logger.info("Semver match on %s", post_ignore_source)

            # Populate the version components from this match
            self.v_source = source
            self.v_stripped = post_discard_source
            self.v_base = post_ignore_source
            self.v_full = "" if result[0] is None else result[0]
            self.v_major = "" if result[1] is None else result[1]
            self.v_minor = "" if result[2] is None else result[2]
            self.v_patch = "" if result[3] is None else result[3]
            self.v_prerelease = "" if result[4] is None else result[4]
            self.v_buildmeta = "" if result[5] is None else result[5]
            self.v_is_prerelease = result[4] is not None

            # Build the major[.minor[.patch]] string, stopping at the first
            # component that is missing
            self.v_mmp = self.v_major
            if self.v_mmp != "" and self.v_minor != "":
                self.v_mmp = self.v_mmp + f".{self.v_minor}"

                if self.v_patch != "":
                    self.v_mmp = self.v_mmp + f".{self.v_patch}"

            return

        # None of the sources matched
        if required:
            raise VersionParseError("No semver matches found")
