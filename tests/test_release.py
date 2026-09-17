#!/usr/bin/env python3
"""
Tests for the release tooling (docs/scripts/next-version.py). Stdlib only.

The script decides which version a commit on main becomes, and rewrites the CHANGELOG for it.
Getting that wrong is expensive: a wrong bump publishes a wrong tag, and a tag in this repository
is a public artefact. Hence tests for every branch of the decision.
"""
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "docs", "scripts")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


REL = _load("next_version", os.path.join(SCRIPTS, "next-version.py"))

CHANGELOG = """# Changelog

Some preamble.

## [Unreleased]

### Added

- a new thing
- another thing

## [2.0.0] - 2026-08-09

### BREAKING

- the entrypoint changed

## [1.0.1] - 2023-05-16

### Fixed

- something
"""


class TestBumpKind(unittest.TestCase):
    def test_breaking_marker_wins(self):
        self.assertEqual(REL.bump_kind(["feat!: drop debian 12", "fix: typo"]), "major")

    def test_breaking_change_footer(self):
        self.assertEqual(REL.bump_kind(["refactor: rework\n\nBREAKING CHANGE: paths moved"]), "major")

    def test_feat_is_minor(self):
        self.assertEqual(REL.bump_kind(["docs: readme", "feat: add ffmpeg 9 variant"]), "minor")

    def test_fix_is_patch(self):
        self.assertEqual(REL.bump_kind(["fix: wrong package name"]), "patch")

    def test_anything_else_is_patch(self):
        self.assertEqual(REL.bump_kind(["docs: translate", "chore: tidy"]), "patch")

    def test_no_commits_is_patch(self):
        self.assertEqual(REL.bump_kind([]), "patch")


class TestBump(unittest.TestCase):
    def test_major(self):
        self.assertEqual(REL.bump("2.3.4", "major"), "3.0.0")

    def test_minor(self):
        self.assertEqual(REL.bump("2.3.4", "minor"), "2.4.0")

    def test_patch(self):
        self.assertEqual(REL.bump("2.3.4", "patch"), "2.3.5")

    def test_accepts_a_v_prefix(self):
        self.assertEqual(REL.bump("v1.0.1", "patch"), "1.0.2")


class TestChangelogVersions(unittest.TestCase):
    def test_reads_released_sections_only(self):
        self.assertEqual(REL.changelog_versions(CHANGELOG), ["2.0.0", "1.0.1"])

    def test_unreleased_is_not_a_version(self):
        self.assertNotIn("Unreleased", REL.changelog_versions(CHANGELOG))

    def test_detects_unreleased_section(self):
        self.assertTrue(REL.has_unreleased(CHANGELOG))
        self.assertFalse(REL.has_unreleased("# Changelog\n\n## [1.0.0] - 2020-01-01\n"))


class TestNextVersion(unittest.TestCase):
    def test_a_changelog_section_above_the_latest_tag_is_the_pending_release(self):
        # Exactly this repository's state: CHANGELOG has [2.0.0], the latest tag is v1.0.1.
        version, reason = REL.next_version("v1.0.1", CHANGELOG, ["docs: translate"])
        self.assertEqual(version, "2.0.0")
        self.assertIn("pending", reason)

    def test_otherwise_it_bumps_from_the_latest_tag(self):
        version, reason = REL.next_version("v2.0.0", CHANGELOG, ["feat: add variant"])
        self.assertEqual(version, "2.1.0")
        self.assertIn("minor", reason)

    def test_no_tags_yet_starts_from_the_changelog(self):
        version, _ = REL.next_version("", CHANGELOG, ["fix: x"])
        self.assertEqual(version, "2.0.0")

    def test_no_tags_and_no_changelog_starts_at_0_1_0(self):
        version, _ = REL.next_version("", "# Changelog\n", ["feat: first"])
        self.assertEqual(version, "0.1.0")


class TestFoldUnreleased(unittest.TestCase):
    def test_unreleased_becomes_the_version_section(self):
        out = REL.fold_unreleased(CHANGELOG, "2.0.0", "2026-09-17")
        self.assertIn("## [2.0.0] - 2026-09-17", out)
        self.assertNotIn("## [Unreleased]", out)
        self.assertIn("- a new thing", out)

    def test_it_keeps_the_older_sections(self):
        out = REL.fold_unreleased(CHANGELOG, "2.0.0", "2026-09-17")
        self.assertIn("## [1.0.1] - 2023-05-16", out)

    def test_folding_an_existing_version_merges_into_that_section(self):
        # The pending [2.0.0] case: Unreleased content has to end up inside [2.0.0],
        # not create a second section with the same number.
        out = REL.fold_unreleased(CHANGELOG, "2.0.0", "2026-09-17")
        self.assertEqual(out.count("## [2.0.0]"), 1)
        self.assertIn("the entrypoint changed", out)

    def test_without_an_unreleased_section_it_adds_one_for_the_version(self):
        base = "# Changelog\n\n## [1.0.0] - 2020-01-01\n\n- old\n"
        out = REL.fold_unreleased(base, "1.0.1", "2026-09-17")
        self.assertIn("## [1.0.1] - 2026-09-17", out)
        self.assertLess(out.index("## [1.0.1]"), out.index("## [1.0.0]"))


class TestReleaseNotes(unittest.TestCase):
    def test_extracts_one_section(self):
        notes = REL.release_notes(CHANGELOG, "2.0.0")
        self.assertIn("the entrypoint changed", notes)
        self.assertNotIn("## [1.0.1]", notes)
        self.assertNotIn("## [2.0.0]", notes)

    def test_missing_section_gives_empty_notes(self):
        self.assertEqual(REL.release_notes(CHANGELOG, "9.9.9"), "")


class TestRepositoryChangelog(unittest.TestCase):
    def test_the_real_changelog_parses(self):
        with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
            text = f.read()
        versions = REL.changelog_versions(text)
        self.assertIn("2.0.0", versions)
        self.assertEqual(versions, sorted(versions, key=REL.version_key, reverse=True),
                         "CHANGELOG sections must be newest first")


if __name__ == "__main__":
    unittest.main()
