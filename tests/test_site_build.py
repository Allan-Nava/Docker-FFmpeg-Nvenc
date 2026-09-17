#!/usr/bin/env python3
"""
Tests for the GitHub Page generator (site/build.py). Stdlib only.

The page has no content of its own: the words come from the README and the **facts** from the files
that actually decide things (the matrix from the publish workflow, the codecs from the Dockerfile,
the assertion count from tests/smoke.sh). That is what these tests are for: if the page and the
repository diverge, the test fails before the page tells a user about it.
"""
import importlib.util
import json
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLISH_WF = os.path.join(ROOT, ".github", "workflows", "docker-publish.yml")


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


BUILD = _load("site_build", os.path.join(ROOT, "site", "build.py"))


class TestMarkdown(unittest.TestCase):
    def md(self, text):
        return BUILD.md_to_html(text)

    def test_paragraph_and_inline(self):
        html = self.md("Text **bold**, `code` and a [link](https://example.test).")
        self.assertIn("<p>", html)
        self.assertIn("<strong>bold</strong>", html)
        self.assertIn("<code>code</code>", html)
        self.assertIn('<a href="https://example.test">link</a>', html)

    def test_heading_h3(self):
        self.assertIn("<h3>Title</h3>", self.md("### Title"))

    def test_list(self):
        html = self.md("- one\n- two")
        self.assertIn("<ul>", html)
        self.assertEqual(html.count("<li>"), 2)

    def test_code_fence_keeps_the_text_and_escapes_it(self):
        html = self.md("```shell\ndocker run --rm <img> -version\n```")
        self.assertIn("<pre>", html)
        self.assertIn("docker run --rm &lt;img&gt; -version", html)
        self.assertNotIn("<img>", html)

    def test_markdown_inside_a_fence_is_not_interpreted(self):
        html = self.md("```\n- not a list **nor** bold\n```")
        self.assertNotIn("<li>", html)
        self.assertNotIn("<strong>", html)

    def test_table(self):
        html = self.md("| a | b |\n|---|---|\n| 1 | 2 |")
        self.assertIn("<table>", html)
        self.assertIn("<th>a</th>", html)
        self.assertIn("<td>2</td>", html)

    def test_text_is_escaped(self):
        html = self.md("5 < 7 & <script>alert(1)</script>")
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&amp;", html)

    def test_blockquote(self):
        self.assertIn("<blockquote>", self.md("> careful"))


class TestParseReadme(unittest.TestCase):
    def test_title_intro_and_sections(self):
        r = BUILD.parse_readme("# Title\n\nlede\n\n## One\n\na\n\n## Two\n\nb\n")
        self.assertEqual(r["title"], "Title")
        self.assertIn("lede", r["intro"])
        self.assertEqual([s["heading"] for s in r["sections"]], ["One", "Two"])
        self.assertIn("a", r["sections"][0]["body"])

    def test_h2_inside_a_fence_does_not_open_a_section(self):
        r = BUILD.parse_readme("# T\n\n## Real\n\n```\n## fake\n```\n")
        self.assertEqual([s["heading"] for s in r["sections"]], ["Real"])


class TestFactsFromTheRepository(unittest.TestCase):
    def test_variants_from_the_publish_workflow(self):
        wf = read(".github", "workflows", "docker-publish.yml")
        variants = BUILD.parse_variants(wf)
        self.assertEqual(len(variants), 3)
        self.assertEqual([v["ffmpeg"] for v in variants], ["7.1.5", "6.0.1", "5.1.10"])
        self.assertEqual([v["nvcodec"] for v in variants], ["sdk/12.1", "sdk/12.0", "sdk/11.0"])
        self.assertEqual([v["default"] for v in variants], [True, False, False])

    def test_exactly_one_variant_is_default(self):
        wf = read(".github", "workflows", "docker-publish.yml")
        self.assertEqual(sum(1 for v in BUILD.parse_variants(wf) if v["default"]), 1)

    def test_minimum_driver_per_branch(self):
        self.assertEqual(BUILD.driver_floor("sdk/11.0"), 470)
        self.assertEqual(BUILD.driver_floor("sdk/12.0"), 530)
        self.assertEqual(BUILD.driver_floor("sdk/12.1"), 530)

    def test_an_unknown_branch_does_not_invent_a_driver(self):
        # Adding a new sdk/* must force a decision about the floor, not print a made-up one.
        with self.assertRaises(ValueError):
            BUILD.driver_floor("sdk/99.9")

    def test_codecs_from_the_dockerfile(self):
        df = read("Dockerfile")
        enabled = BUILD.parse_enabled(df)
        for expected in ("nvenc", "libx264", "libx265", "libvpx", "libopus", "gpl"):
            self.assertIn(expected, enabled)

    def test_no_nonfree_among_the_codecs(self):
        # Licence invariant: if it showed up, the image would not be redistributable.
        df = read("Dockerfile")
        self.assertNotIn("nonfree", BUILD.parse_enabled(df))

    def test_smoke_assertion_count(self):
        sh = read("tests", "smoke.sh")
        self.assertEqual(BUILD.count_smoke_assertions(sh), 17)


class TestPage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = BUILD.render(ROOT)
        cls.readme = read("README.md")

    def test_minimally_well_formed_html(self):
        self.assertTrue(self.html.startswith("<!doctype html>"))
        self.assertIn('<html lang="en">', self.html)
        self.assertIn("</html>", self.html.rstrip()[-20:])

    def test_title_and_canonical(self):
        self.assertRegex(self.html, r"<title>[^<]*FFmpeg[^<]*</title>")
        self.assertIn('<link rel="canonical" href="https://allan-nava.github.io/Docker-FFmpeg-Nvenc/"', self.html)

    def test_social_meta(self):
        for prop in ('og:title', 'og:description', 'og:image', 'twitter:card'):
            self.assertIn(prop, self.html)

    def test_valid_jsonld(self):
        blob = re.search(r'<script type="application/ld\+json">(.*?)</script>', self.html, re.S).group(1)
        data = json.loads(blob)
        self.assertEqual(data["@context"], "https://schema.org")

    def test_every_variant_is_on_the_page_with_its_driver(self):
        wf = read(".github", "workflows", "docker-publish.yml")
        for v in BUILD.parse_variants(wf):
            self.assertIn(v["ffmpeg"], self.html)
            self.assertIn(v["nvcodec"], self.html)
            self.assertIn(str(BUILD.driver_floor(v["nvcodec"])), self.html)

    def test_ghcr_image_on_the_page(self):
        self.assertIn("ghcr.io/allan-nava/docker-ffmpeg-nvenc", self.html)

    def test_assertion_count_on_the_page(self):
        self.assertIn("17", self.html)

    def test_every_readme_section_is_on_the_page(self):
        for s in BUILD.parse_readme(self.readme)["sections"]:
            self.assertIn(BUILD.escape(s["heading"]), self.html,
                          f"section «{s['heading']}» lost on the page")

    def test_no_unresolved_placeholder(self):
        self.assertNotIn("{{", self.html)
        self.assertNotIn("TODO", self.html)

    def test_dark_mode_and_viewport(self):
        self.assertIn("prefers-color-scheme: dark", self.html)
        self.assertIn('name="viewport"', self.html)

    def test_publication_notice_from_the_readme(self):
        # The README warns that the tags are not published yet: the page must not lose that.
        self.assertIn("have not been published yet", self.html)


class TestBuildOnDisk(unittest.TestCase):
    def test_writes_index_sitemap_and_assets(self):
        with tempfile.TemporaryDirectory() as out:
            BUILD.main(["--out", out])
            index = os.path.join(out, "index.html")
            self.assertTrue(os.path.isfile(index))
            self.assertTrue(os.path.isfile(os.path.join(out, "sitemap.xml")))
            self.assertTrue(os.path.isfile(os.path.join(out, "assets", "logo.svg")))
            self.assertTrue(os.path.isfile(os.path.join(out, ".nojekyll")))
            with open(os.path.join(out, "sitemap.xml"), encoding="utf-8") as f:
                sitemap = f.read()
            self.assertIn("https://allan-nava.github.io/Docker-FFmpeg-Nvenc/", sitemap)

    def test_check_writes_nothing_and_reports_alignment(self):
        with tempfile.TemporaryDirectory() as out:
            self.assertEqual(BUILD.main(["--out", out, "--check"]), 1)   # no index → diverged
            BUILD.main(["--out", out])
            self.assertEqual(BUILD.main(["--out", out, "--check"]), 0)   # now aligned


if __name__ == "__main__":
    unittest.main()
