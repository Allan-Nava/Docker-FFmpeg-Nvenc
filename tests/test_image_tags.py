#!/usr/bin/env python3
"""
Tests for docs/scripts/image-tags.py — the list of tags each published image gets.

This is the one piece of this repository that has already broken in silence: before v2.0.0 the
workflow ran a semver regex against a string the variant suffix made structurally unmatchable, so
`:latest` was never published and nobody noticed for two years. A pure, tested function beats a
regex buried in YAML.
"""
import importlib.util
import os
import subprocess
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


T = _load("image_tags", os.path.join(SCRIPTS, "image-tags.py"))
IMAGE = "ghcr.io/allan-nava/docker-ffmpeg-nvenc"


class TestBranchAliases(unittest.TestCase):
    def test_three_levels_from_a_patch_version(self):
        self.assertEqual(T.ffmpeg_aliases("9.0.1"), ["9", "9.0", "9.0.1"])

    def test_double_digit_patch(self):
        self.assertEqual(T.ffmpeg_aliases("5.1.10"), ["5", "5.1", "5.1.10"])

    def test_two_component_version_has_no_third_level(self):
        self.assertEqual(T.ffmpeg_aliases("6.0"), ["6", "6.0"])


class TestTagsForADefaultVariant(unittest.TestCase):
    def setUp(self):
        self.tags = T.tags_for(IMAGE, "v2.1.0", "9.0.1", default=True)

    def test_the_floating_branch_pointers_exist(self):
        for t in ("latest-ffmpeg9", "latest-ffmpeg9.0", "latest-ffmpeg9.0.1"):
            self.assertIn(f"{IMAGE}:{t}", self.tags)

    def test_the_exact_release_tag_exists(self):
        self.assertIn(f"{IMAGE}:2.1.0-ffmpeg9.0.1", self.tags)

    def test_the_unsuffixed_repo_tags_exist_only_for_the_default(self):
        for t in ("latest", "2.1.0", "2.1", "2"):
            self.assertIn(f"{IMAGE}:{t}", self.tags)

    def test_every_tag_is_fully_qualified(self):
        for tag in self.tags:
            self.assertTrue(tag.startswith(f"{IMAGE}:"), tag)

    def test_no_duplicates(self):
        self.assertEqual(len(self.tags), len(set(self.tags)))


class TestTagsForANonDefaultVariant(unittest.TestCase):
    def setUp(self):
        self.tags = T.tags_for(IMAGE, "v2.1.0", "7.1.5", default=False)

    def test_it_never_takes_an_unsuffixed_tag(self):
        # This is the invariant that matters: a non-default variant must never claim `:latest`
        # or a bare version, or pulling the default becomes a lottery.
        for tag in self.tags:
            self.assertRegex(tag, r"-ffmpeg\d", tag)

    def test_it_still_gets_its_branch_pointers(self):
        for t in ("latest-ffmpeg7", "latest-ffmpeg7.1", "latest-ffmpeg7.1.5", "2.1.0-ffmpeg7.1.5"):
            self.assertIn(f"{IMAGE}:{t}", self.tags)


class TestReleaseNormalisation(unittest.TestCase):
    def test_the_v_prefix_is_optional(self):
        self.assertEqual(T.tags_for(IMAGE, "2.1.0", "9.0.1", default=True),
                         T.tags_for(IMAGE, "v2.1.0", "9.0.1", default=True))

    def test_a_release_that_is_not_semver_is_refused(self):
        with self.assertRaises(ValueError):
            T.tags_for(IMAGE, "main", "9.0.1", default=True)


class TestMatrixWide(unittest.TestCase):
    """Properties across the whole published matrix, read from the workflow itself."""

    def setUp(self):
        sys.path.insert(0, os.path.join(ROOT, "site"))
        build = _load("site_build_for_tags", os.path.join(ROOT, "site", "build.py"))
        with open(os.path.join(ROOT, ".github", "workflows", "docker-publish.yml"), encoding="utf-8") as f:
            self.variants = build.parse_variants(f.read())
        self.all_tags = [t for v in self.variants
                         for t in T.tags_for(IMAGE, "v2.1.0", v["ffmpeg"], default=v["default"])]

    def test_no_tag_is_claimed_by_two_variants(self):
        # The failure this prevents: two variants both pushing `latest-ffmpeg9`, last write wins.
        self.assertEqual(len(self.all_tags), len(set(self.all_tags)))

    def test_exactly_one_variant_owns_latest(self):
        self.assertEqual(sum(1 for t in self.all_tags if t == f"{IMAGE}:latest"), 1)

    def test_every_variant_is_reachable_by_its_major(self):
        for v in self.variants:
            major = v["ffmpeg"].split(".")[0]
            self.assertIn(f"{IMAGE}:latest-ffmpeg{major}", self.all_tags)


class TestLabels(unittest.TestCase):
    def test_oci_labels_carry_revision_version_and_date(self):
        labels = T.labels_for("v2.1.0", revision="abc1234", created="2026-09-17T10:00:00Z")
        self.assertIn("org.opencontainers.image.version=2.1.0", labels)
        self.assertIn("org.opencontainers.image.revision=abc1234", labels)
        self.assertIn("org.opencontainers.image.created=2026-09-17T10:00:00Z", labels)


class TestCli(unittest.TestCase):
    def _run(self, *args):
        return subprocess.run(["python3", os.path.join(SCRIPTS, "image-tags.py"), *args],
                              cwd=ROOT, text=True, capture_output=True)

    def test_it_prints_one_tag_per_line(self):
        res = self._run("--image", IMAGE, "--release", "v2.1.0", "--ffmpeg", "9.0.1", "--default")
        self.assertEqual(res.returncode, 0, res.stderr)
        lines = res.stdout.strip().split("\n")
        self.assertIn(f"{IMAGE}:latest", lines)
        self.assertIn(f"{IMAGE}:latest-ffmpeg9", lines)

    def test_labels_mode(self):
        res = self._run("--release", "v2.1.0", "--labels", "--revision", "deadbee")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("org.opencontainers.image.revision=deadbee", res.stdout)

    def test_a_bad_release_fails_loudly(self):
        res = self._run("--image", IMAGE, "--release", "nope", "--ffmpeg", "9.0.1")
        self.assertEqual(res.returncode, 1)
        self.assertIn("semver", (res.stdout + res.stderr).lower())


if __name__ == "__main__":
    unittest.main()
