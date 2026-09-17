#!/usr/bin/env python3
"""
Tests for the backlog tooling (docs/scripts/). Stdlib only: `python3 -m unittest discover -s tests`.

They cover the rules that would break the GitHub issues silently if they regressed: item parsing,
linting, hash stability (= the sync's idempotence) and the two GitHub-API-specific rules (label
union, pull-request filter).
"""
import importlib.util
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "docs", "scripts")
sys.path.insert(0, os.path.join(SCRIPTS, "lib"))
import backlog as B  # noqa: E402


def _load(name, path):
    """Import a script whose filename contains a dash (not importable as a module)."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SYNC = _load("sync_backlog", os.path.join(SCRIPTS, "sync-backlog-to-issues.py"))


def parse_text(text):
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(text)
        path = f.name
    try:
        return B.parse_backlog(path)
    finally:
        os.unlink(path)


ITEM = """### `my-item` — Title with `code`

- **status**: open
- **priority**: high
- **labels**: docker, ci
- **milestone**: Ship v2.0.0
- **ref**: [doc](audit/x.md)

First line of prose.

- **note**: unknown key, ends up in the body
"""


class TestParse(unittest.TestCase):
    def test_fields_and_body(self):
        it, = parse_text(ITEM)
        self.assertEqual(it["id"], "my-item")
        self.assertEqual(it["title"], "Title with `code`")
        self.assertEqual(it["status"], "open")
        self.assertEqual(it["priority"], "high")
        self.assertEqual(it["labels"], ["docker", "ci"])
        self.assertEqual(it["milestone"], "Ship v2.0.0")
        self.assertIn("First line of prose.", "\n".join(it["body"]))

    def test_unknown_key_ends_up_in_the_body(self):
        it, = parse_text(ITEM)
        self.assertIn("unknown key", "\n".join(it["body"]))

    def test_status_defaults_to_open(self):
        it, = parse_text("### `x` — T\n\nprosa\n")
        self.assertEqual(it["status"], "open")

    def test_several_items(self):
        items = parse_text("### `a` — A\n- **status**: done\n\n### `b` — B\n")
        self.assertEqual([i["id"] for i in items], ["a", "b"])
        self.assertEqual(items[0]["status"], "done")


class TestLint(unittest.TestCase):
    def _errs(self, text):
        return B.lint(parse_text(text))

    def test_the_repository_backlog_is_valid(self):
        items = B.parse_backlog(os.path.join(ROOT, "docs", "backlog.md"))
        errors, _ = B.lint(items)
        self.assertEqual(errors, [], f"docs/backlog.md does not pass the lint: {errors}")

    def test_duplicate_id(self):
        errors, _ = self._errs("### `a` — A\n\n### `a` — di nuovo A\n")
        self.assertTrue(any("duplicate id" in e for e in errors))

    def test_invalid_status(self):
        errors, _ = self._errs("### `a` — A\n- **status**: chiuso\n")
        self.assertTrue(any("status" in e for e in errors))

    def test_invalid_priority(self):
        errors, _ = self._errs("### `a` — A\n- **priority**: urgentissima\n")
        self.assertTrue(any("priority" in e for e in errors))

    def test_unknown_meta_key(self):
        errors, _ = self._errs("### `a` — A\n- **lables**: x\n")
        self.assertTrue(any("unknown meta key" in e for e in errors))

    def test_repeated_meta_key(self):
        errors, _ = self._errs("### `a` — A\n- **labels**: x\n- **labels**: y\n")
        self.assertTrue(any("repeated" in e for e in errors), errors)

    def test_id_must_be_kebab_case(self):
        errors, _ = self._errs("### `My_Item!` — A\n")
        self.assertTrue(any("invalid id" in e for e in errors))

    def test_milestone_spelled_two_ways_is_only_a_warning(self):
        errors, warnings = self._errs(
            "### `a` — A\n- **milestone**: Alfa Beta\n\n### `b` — B\n- **milestone**: alfa  beta\n")
        self.assertEqual(errors, [])
        self.assertTrue(any("different ways" in w for w in warnings))


class TestHash(unittest.TestCase):
    def test_stable_for_the_same_content(self):
        a, = parse_text(ITEM)
        b, = parse_text(ITEM)
        self.assertEqual(B.item_hash(a), B.item_hash(b))

    def test_changes_when_the_milestone_changes(self):
        a, = parse_text(ITEM)
        b, = parse_text(ITEM.replace("Ship v2.0.0", "Repository automation"))
        self.assertNotEqual(B.item_hash(a), B.item_hash(b))

    def test_changes_when_the_body_changes(self):
        a, = parse_text(ITEM)
        b, = parse_text(ITEM.replace("First line of prose.", "First line of prose, edited."))
        self.assertNotEqual(B.item_hash(a), B.item_hash(b))


class TestSyncHelpers(unittest.TestCase):
    def test_issue_body_carries_the_fingerprint_and_hash(self):
        it, = parse_text(ITEM)
        body = SYNC.build_body(it, "https://example.test/backlog.md")
        self.assertRegex(body, r"<!-- backlog-id: my-item \| hash: [0-9a-f]{12} -->")
        self.assertEqual(B.FP_RE.search(body).group(1), "my-item")
        self.assertEqual(B.HASH_RE.search(body).group(1), B.item_hash(it))

    def test_labels_added_by_hand_survive(self):
        # GitHub REPLACES the label set on PATCH: the desired set must be the union.
        it, = parse_text(ITEM)
        issue = {"labels": [{"name": "added-by-hand"}, {"name": "docker"}]}
        self.assertEqual(SYNC.desired_labels(it, issue),
                         ["added-by-hand", "backlog-sync", "ci", "docker"])

    def test_labels_without_an_issue_are_the_items_plus_sync(self):
        it, = parse_text(ITEM)
        self.assertEqual(SYNC.desired_labels(it), ["backlog-sync", "ci", "docker"])

    def test_pull_requests_are_not_items(self):
        # GET /issues also returns PRs: without the filter, a PR carrying the sync label would be
        # read as a phantom item and CLOSED.
        self.assertTrue(SYNC.is_issue({"number": 1, "title": "issue"}))
        self.assertFalse(SYNC.is_issue({"number": 2, "title": "pr", "pull_request": {"url": "..."}}))

    def test_closing_note_prefers_the_blockquote(self):
        it, = parse_text("### `a` — A\n- **status**: done\n\n- [ ] checklist\n\n> Fixed like this.\n")
        self.assertEqual(SYNC.close_note(it), "Fixed like this.")

    def test_closing_note_skips_checklists(self):
        it, = parse_text("### `a` — A\n\n- [ ] one\n- [x] two\n\nThe real reason.\n")
        self.assertEqual(SYNC.close_note(it), "The real reason.")

    def test_no_note_when_the_item_was_removed(self):
        self.assertIsNone(SYNC.close_note(None))


if __name__ == "__main__":
    unittest.main()
