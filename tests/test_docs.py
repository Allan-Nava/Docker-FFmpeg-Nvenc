#!/usr/bin/env python3
"""
Documentation invariants. Stdlib only.

Docs rot in the same three ways every time: a link survives a rename, a list of files stops matching
the directory, and a table stops matching the thing it describes. All three happened in this
repository today (audits renamed, scripts added, the variant matrix changed twice), so they are
pinned here instead of being re-discovered by a reader.
"""
import importlib.util
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {".git", "logs", "site/dist", "node_modules", "__pycache__"}
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def markdown_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        rel = os.path.relpath(dirpath, ROOT)
        if any(part in SKIP_DIRS for part in rel.split(os.sep)) or rel.replace(os.sep, "/") in SKIP_DIRS:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name.endswith(".md"):
                yield os.path.join(dirpath, name)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestLinks(unittest.TestCase):
    def test_every_relative_link_resolves(self):
        broken = []
        for path in markdown_files():
            for target in LINK_RE.findall(read(path)):
                target = target.split(" ")[0].split("#")[0].strip()
                if not target or target.startswith(("http://", "https://", "mailto:", "<")):
                    continue
                resolved = os.path.normpath(os.path.join(os.path.dirname(path), target))
                if not os.path.exists(resolved):
                    broken.append(f"{os.path.relpath(path, ROOT)} → {target}")
        self.assertEqual(broken, [], "broken relative links:\n  " + "\n  ".join(broken))


class TestClaudeAndAgentsStayInSync(unittest.TestCase):
    """They are two renderings of the same rules; drift between them is drift in the rules."""

    def headings(self, name):
        return [l.strip() for l in read(os.path.join(ROOT, name)).split("\n") if l.startswith("## ")]

    def test_same_sections(self):
        claude = [h.replace("—", "-") for h in self.headings("CLAUDE.md")]
        self.assertEqual(claude, self.headings("AGENTS.md"))

    def test_agents_is_ascii(self):
        # It is read by tools that are not all UTF-8 friendly; that is the whole point of the file.
        text = read(os.path.join(ROOT, "AGENTS.md"))
        self.assertEqual([c for c in text if ord(c) > 127], [])


class TestScriptsRunbook(unittest.TestCase):
    def scripts(self):
        d = os.path.join(ROOT, "docs", "scripts")
        return sorted(f for f in os.listdir(d) if f.endswith((".py", ".sh")))

    def test_the_runbook_lists_every_script(self):
        runbook = read(os.path.join(ROOT, "docs", "scripts", "README.md"))
        missing = [s for s in self.scripts() if s not in runbook]
        self.assertEqual(missing, [], f"docs/scripts/README.md does not mention: {missing}")

    def test_the_runbook_mentions_no_script_that_does_not_exist(self):
        runbook = read(os.path.join(ROOT, "docs", "scripts", "README.md"))
        named = {m for m in re.findall(r"\b[\w-]+\.(?:py|sh)\b", runbook)}
        on_disk = set(self.scripts()) | {"backlog.py", "changelog.py"} | {
            f for f in os.listdir(os.path.join(ROOT, "tests")) if f.endswith((".py", ".sh"))}
        phantom = sorted(named - on_disk)
        self.assertEqual(phantom, [], f"docs/scripts/README.md mentions files that do not exist: {phantom}")


class TestReadmeMatchesTheMatrix(unittest.TestCase):
    """The README variant table is the one people act on: it must match what the workflow publishes."""

    def setUp(self):
        build = _load("site_build_for_docs", os.path.join(ROOT, "site", "build.py"))
        with open(os.path.join(ROOT, ".github", "workflows", "docker-publish.yml"), encoding="utf-8") as f:
            self.variants = build.parse_variants(f.read())
        self.build = build
        self.readme = read(os.path.join(ROOT, "README.md"))

    def test_every_published_variant_is_in_the_table(self):
        table = self.readme[self.readme.index("| Variant |"):]
        for v in self.variants:
            self.assertIn(v["ffmpeg"], table, f"FFmpeg {v['ffmpeg']} is published but absent from the README table")
            self.assertIn(v["nvcodec"], table, f"{v['nvcodec']} is published but absent from the README table")

    def test_the_table_lists_no_variant_that_is_not_published(self):
        table = self.readme[self.readme.index("| Variant |"):self.readme.index("`X.Y.Z` is the **repository**")]
        published = {v["ffmpeg"] for v in self.variants}
        listed = set(re.findall(r"\|\s*(\d+\.\d+\.\d+)\s*\|", table))
        self.assertEqual(listed - published, set(), "the README table lists unpublished variants")

    def test_driver_floors_agree_with_the_generator(self):
        for v in self.variants:
            floor = str(self.build.driver_floor(v["nvcodec"]))
            row = next(l for l in self.readme.split("\n") if f"| {v['ffmpeg']} |" in l or f"| default | {v['ffmpeg']} |" in l)
            self.assertIn(floor, row, f"README row for {v['ffmpeg']} does not state driver ≥ {floor}")


class TestDeliveryClaims(unittest.TestCase):
    """Claims about release state must not outlive the state."""

    def test_no_doc_says_v2_was_never_tagged_once_it_is_tagged(self):
        tags = subprocess.run(["git", "tag", "--list", "v*"], cwd=ROOT, text=True,
                              capture_output=True).stdout.split()
        if not any(t.startswith("v2.") for t in tags):
            self.skipTest("no v2 tag in this checkout (shallow clone?)")
        for name in ("CLAUDE.md", "AGENTS.md", "README.md"):
            text = read(os.path.join(ROOT, name))
            for claim in ("never been tagged", "never tagged", "until the tag exists"):
                if claim in text:
                    line = next(l for l in text.split("\n") if claim in l)
                    self.fail(f"{name} still says the release is untagged, but {sorted(tags)[-1]} exists:\n"
                              f"  {line[:160]}…")


if __name__ == "__main__":
    unittest.main()
