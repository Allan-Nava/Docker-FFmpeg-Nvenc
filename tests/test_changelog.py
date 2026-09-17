#!/usr/bin/env python3
"""
Tests for the commit/CHANGELOG automation (docs/scripts/lib/changelog.py and its CLI). Stdlib only.

What is automated here is the *plumbing*: which Keep a Changelog section a commit belongs in, where
the bullet goes, and whether a commit subject is shaped so `next-version.py` can read a bump out of
it. The prose stays hand-written — that is the part worth keeping.
"""
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "docs", "scripts")
sys.path.insert(0, os.path.join(SCRIPTS, "lib"))
import changelog as C  # noqa: E402

BASE = """# Changelog

Preamble.

## [Unreleased]

### Added

- an existing entry

## [2.0.0] - 2026-08-09

- old stuff
"""

NO_UNRELEASED = """# Changelog

Preamble.

## [2.0.0] - 2026-08-09

- old stuff
"""


class TestSubjectParsing(unittest.TestCase):
    def test_plain_type(self):
        c = C.parse_subject("feat: add the 9.0 variant")
        self.assertEqual((c.type, c.scope, c.breaking), ("feat", "", False))
        self.assertEqual(c.description, "add the 9.0 variant")

    def test_scope(self):
        self.assertEqual(C.parse_subject("fix(ci): pipefail in the summary step").scope, "ci")

    def test_bang_is_breaking(self):
        self.assertTrue(C.parse_subject("feat!: drop the 6.0 variant").breaking)

    def test_breaking_change_footer(self):
        self.assertTrue(C.parse_subject("refactor: move paths\n\nBREAKING CHANGE: /data moved").breaking)

    def test_rejects_a_non_conventional_subject(self):
        self.assertIsNone(C.parse_subject("fixed the thing"))
        self.assertIsNone(C.parse_subject("Add new variant"))

    def test_rejects_an_unknown_type(self):
        self.assertIsNone(C.parse_subject("banana: something"))

    def test_merge_and_revert_commits_are_accepted_as_is(self):
        self.assertTrue(C.is_acceptable("Merge branch 'main' into feature"))
        self.assertTrue(C.is_acceptable("Revert \"feat: something\""))
        self.assertTrue(C.is_acceptable("release: v2.0.0"))
        self.assertFalse(C.is_acceptable("just some words"))

    def test_subject_must_not_be_empty_or_endless(self):
        self.assertIsNone(C.parse_subject("feat: "))
        self.assertIsNone(C.parse_subject("feat: " + "x" * 200))


class TestSectionMapping(unittest.TestCase):
    def test_feat_is_added(self):
        self.assertEqual(C.section_for(C.parse_subject("feat: x")), "Added")

    def test_fix_is_fixed(self):
        self.assertEqual(C.section_for(C.parse_subject("fix: x")), "Fixed")

    def test_remove_and_revert_are_removed(self):
        self.assertEqual(C.section_for(C.parse_subject("remove: x")), "Removed")
        self.assertEqual(C.section_for(C.parse_subject("revert: x")), "Removed")

    def test_security_has_its_own_section(self):
        self.assertEqual(C.section_for(C.parse_subject("security: bump base image")), "Security")

    def test_everything_else_is_changed(self):
        for subject in ("docs: x", "refactor: x", "perf: x", "ci: x", "build: x", "chore: x", "test: x"):
            self.assertEqual(C.section_for(C.parse_subject(subject)), "Changed", subject)


class TestAddEntry(unittest.TestCase):
    def test_appends_to_an_existing_subsection(self):
        out = C.add_entry(BASE, "Added", "a new entry")
        self.assertIn("- an existing entry\n- a new entry", out)

    def test_creates_a_missing_subsection_under_unreleased(self):
        out = C.add_entry(BASE, "Fixed", "something broken")
        self.assertIn("### Fixed", out)
        unreleased = out[out.index("## [Unreleased]"):out.index("## [2.0.0]")]
        self.assertIn("### Fixed", unreleased)
        self.assertIn("- something broken", unreleased)

    def test_creates_the_unreleased_section_when_missing(self):
        out = C.add_entry(NO_UNRELEASED, "Added", "first entry")
        self.assertIn("## [Unreleased]", out)
        self.assertLess(out.index("## [Unreleased]"), out.index("## [2.0.0]"))
        self.assertIn("- first entry", out)

    def test_keeps_the_released_sections_untouched(self):
        out = C.add_entry(BASE, "Added", "x")
        self.assertIn("## [2.0.0] - 2026-08-09", out)
        self.assertIn("- old stuff", out)

    def test_does_not_duplicate_an_identical_entry(self):
        out = C.add_entry(C.add_entry(BASE, "Added", "same bullet"), "Added", "same bullet")
        self.assertEqual(out.count("- same bullet"), 1)

    def test_subsections_keep_keep_a_changelog_order(self):
        out = C.add_entry(C.add_entry(BASE, "Removed", "r"), "Fixed", "f")
        unreleased = out[out.index("## [Unreleased]"):out.index("## [2.0.0]")]
        self.assertLess(unreleased.index("### Added"), unreleased.index("### Removed"))
        self.assertLess(unreleased.index("### Removed"), unreleased.index("### Fixed"))

    def test_breaking_entries_are_marked(self):
        commit = C.parse_subject("feat!: drop 6.0")
        self.assertTrue(C.entry_for(commit).startswith("**BREAKING**"))
        self.assertIn("drop 6.0", C.entry_for(commit))

    def test_entry_keeps_the_scope(self):
        self.assertIn("`ci`", C.entry_for(C.parse_subject("fix(ci): pipefail")))


class TestUnreleasedState(unittest.TestCase):
    def test_detects_entries(self):
        self.assertTrue(C.has_unreleased_entries(BASE))

    def test_empty_unreleased_has_no_entries(self):
        self.assertFalse(C.has_unreleased_entries("# C\n\n## [Unreleased]\n\n## [1.0.0] - 2020-01-01\n"))

    def test_missing_unreleased_has_no_entries(self):
        self.assertFalse(C.has_unreleased_entries(NO_UNRELEASED))


class TestDraftFromCommits(unittest.TestCase):
    """The fallback: if nobody wrote the prose, the release still ships a readable list."""

    def test_groups_by_section_and_skips_noise(self):
        drafted = C.entries_from_commits([
            "feat: add the 9.0 variant",
            "fix(ci): pipefail in the summary",
            "release: v2.0.0",
            "Merge branch 'main'",
            "not conventional at all",
        ])
        self.assertEqual(drafted["Added"], ["add the 9.0 variant"])
        self.assertEqual(drafted["Fixed"], ["`ci`: pipefail in the summary"])
        self.assertNotIn("Removed", drafted)

    def test_applied_to_a_changelog_it_fills_unreleased(self):
        out = C.apply_drafted(NO_UNRELEASED, ["feat: one", "fix: two"])
        self.assertTrue(C.has_unreleased_entries(out))
        self.assertIn("- one", out)
        self.assertIn("- two", out)


class TestCli(unittest.TestCase):
    def _run(self, path, *args):
        return subprocess.run(["python3", os.path.join(SCRIPTS, "changelog-add.py"),
                               "--changelog", path, *args], cwd=ROOT, text=True, capture_output=True)

    def test_adds_an_entry_from_a_commit_message(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "CHANGELOG.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(BASE)
            res = self._run(path, "--message", "fix: the tagging regex never matched")
            self.assertEqual(res.returncode, 0, res.stderr)
            with open(path, encoding="utf-8") as f:
                out = f.read()
            self.assertIn("### Fixed", out)
            self.assertIn("- the tagging regex never matched", out)

    def test_explicit_text_wins_over_the_subject(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "CHANGELOG.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(BASE)
            self._run(path, "--message", "fix: short", "--entry", "the long explanation of what broke")
            with open(path, encoding="utf-8") as f:
                out = f.read()
            self.assertIn("- the long explanation of what broke", out)
            self.assertNotIn("- short", out)

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "CHANGELOG.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(BASE)
            res = self._run(path, "--message", "feat: x", "--dry-run")
            self.assertEqual(res.returncode, 0, res.stderr)
            with open(path, encoding="utf-8") as f:
                self.assertEqual(f.read(), BASE)

    def test_a_bad_subject_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "CHANGELOG.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write(BASE)
            res = self._run(path, "--message", "fixed stuff")
            self.assertEqual(res.returncode, 1)
            self.assertIn("conventional", (res.stdout + res.stderr).lower())


class TestRepositoryChangelog(unittest.TestCase):
    """Structural checks only.

    An earlier version of this class asserted that the real CHANGELOG *has* unreleased entries. That
    is a transient state, not an invariant: `release.yml` folds `[Unreleased]` into the version
    section on every release, so the assertion was false from the moment v2.0.0 shipped and it took
    CI, Pages and the next Release down with it. A test must pin what is always true.
    """

    def setUp(self):
        with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
            self.text = f.read()

    def test_it_has_at_least_one_released_version(self):
        self.assertTrue(C.VERSION_RE.search(self.text), "no `## [x.y.z]` section in CHANGELOG.md")

    def test_has_unreleased_entries_agrees_with_the_file(self):
        bounds = C._unreleased_bounds(self.text)
        if bounds is None:
            # right after a release: the section is gone, and that is correct
            self.assertFalse(C.has_unreleased_entries(self.text))
        else:
            block = self.text[bounds[0]:bounds[1]]
            self.assertEqual(C.has_unreleased_entries(self.text),
                             any(l.startswith("- ") for l in block.split("\n")))

    def test_unreleased_when_present_sits_above_the_newest_release(self):
        bounds = C._unreleased_bounds(self.text)
        if bounds is None:
            self.skipTest("no [Unreleased] section (the repository is just after a release)")
        self.assertLess(bounds[0], C.VERSION_RE.search(self.text).start())

    def test_an_entry_can_always_be_filed_on_the_real_file(self):
        # The post-release state is the one that broke: adding an entry must recreate the section
        # above the newest release rather than append it at the bottom.
        out = C.add_entry(self.text, "Added", "a probe entry, not written to disk")
        self.assertTrue(C.has_unreleased_entries(out))
        self.assertLess(out.index("## [Unreleased]"), C.VERSION_RE.search(out).start())


if __name__ == "__main__":
    unittest.main()
