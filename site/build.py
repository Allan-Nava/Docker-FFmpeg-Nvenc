#!/usr/bin/env python3
"""
build.py — generate the repository's GitHub Page into site/dist/ (stdlib only).

The page has **no content of its own**: the words come from `README.md`, the facts from the files
that actually decide things —

    .github/workflows/docker-publish.yml  →  which variants get published (the matrix)
    Dockerfile                            →  which codecs are enabled (--enable-*)
    tests/smoke.sh                        →  how many assertions act as the gate

— so the page cannot tell a different story from the one CI publishes. Only the design lives here.
Tests: `tests/test_site_build.py`.

Usage:
  python3 site/build.py                 # writes site/dist/
  python3 site/build.py --out DIR
  python3 site/build.py --check         # exit 1 if the output differs from what is on disk
"""
import argparse
import html as _html
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

REPO = "https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc"
BLOB = REPO + "/blob/main"
SITE = "https://allan-nava.github.io/Docker-FFmpeg-Nvenc/"
IMAGE = "ghcr.io/allan-nava/docker-ffmpeg-nvenc"

# Minimum NVIDIA driver per nv-codec-headers branch. Deliberately an explicit table rather than a
# heuristic on the number: a new branch must force a decision (and a check), not inherit a
# plausible-looking number. See `driver_floor`.
DRIVER_FLOOR = {"sdk/11.0": 470, "sdk/12.0": 530, "sdk/12.1": 530}


def escape(s):
    return _html.escape(s, quote=True)


# --------------------------------------------------------------------------- markdown (sottoinsieme)
_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def _inline(text):
    """Inline markdown of text that still needs escaping: code spans, bold, links.

    Code spans are stashed behind \\x00 sentinels before the other substitutions, so `**` or
    `[..](..)` inside code stays text. The sentinels avoid braces on purpose: the page must not
    contain `{{` (an unresolved placeholder would be indistinguishable)."""
    slots = []

    def stash(m):
        slots.append(escape(m.group(1)))
        return f"\x00{len(slots) - 1}\x00"

    text = _CODE_RE.sub(stash, text)
    text = escape(text)
    text = _BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = _LINK_RE.sub(lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', text)
    for i, code in enumerate(slots):
        text = text.replace(f"\x00{i}\x00", f"<code>{code}</code>")
    return text


def _table(rows):
    head, body = rows[0], rows[2:]          # rows[1] is the |---| separator
    out = ["<table>", "<thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in head) + "</tr></thead>",
           "<tbody>"]
    for r in body:
        out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>")
    out += ["</tbody>", "</table>"]
    return "\n".join(out)


def _cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def md_to_html(text):
    """Render the markdown subset used by this repository's .md files: headings, paragraphs, lists,
    tables, blockquotes, fences. All text is escaped; inside a fence markdown is not interpreted."""
    lines = text.split("\n")
    out, i = [], 0
    para, ul, ol, quote = [], [], [], []

    def flush():
        if para:
            out.append(f"<p>{_inline(' '.join(para))}</p>"); para.clear()
        if ul:
            out.append("<ul>\n" + "\n".join(f"<li>{_inline(x)}</li>" for x in ul) + "\n</ul>"); ul.clear()
        if ol:
            out.append("<ol>\n" + "\n".join(f"<li>{_inline(x)}</li>" for x in ol) + "\n</ol>"); ol.clear()
        if quote:
            out.append(f"<blockquote><p>{_inline(' '.join(quote))}</p></blockquote>"); quote.clear()

    while i < len(lines):
        line = lines[i]

        if line.startswith("```"):
            lang = line[3:].strip()
            i += 1
            block = []
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i]); i += 1
            i += 1
            flush()
            cls = f' class="lang-{escape(lang)}"' if lang else ""
            out.append(f"<pre><code{cls}>{escape(chr(10).join(block))}</code></pre>")
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush()
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{_inline(m.group(2).strip())}</h{lvl}>")
            i += 1
            continue

        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|?\s*$", lines[i + 1]):
            flush()
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append(_cells(lines[i])); i += 1
            out.append(_table(rows))
            continue

        m = re.match(r"^\s*[-*]\s+(.*)$", line)
        if m:
            if para or ol or quote:
                flush()
            ul.append(m.group(1)); i += 1
            continue

        m = re.match(r"^\s*\d+[.)]\s+(.*)$", line)
        if m:
            if para or ul or quote:
                flush()
            ol.append(m.group(1)); i += 1
            continue

        if line.startswith(">"):
            if para or ul or ol:
                flush()
            quote.append(line.lstrip("> ").rstrip()); i += 1
            continue

        if not line.strip():
            flush(); i += 1
            continue

        if ul or ol or quote:
            flush()
        para.append(line.strip()); i += 1

    flush()
    return "\n".join(out)


# --------------------------------------------------------------------------- README
def parse_readme(source):
    """Split the README into a title (H1), an intro and one section per H2. Fence-aware: a `## `
    inside a code block does not open a section."""
    title, sections = "", []
    current = {"heading": None, "lines": []}
    fenced = False
    for line in source.split("\n"):
        if line.startswith("```"):
            fenced = not fenced
        if not fenced and line.startswith("# "):
            title = line[2:].strip()
            continue
        if not fenced and line.startswith("## "):
            sections.append(current)
            current = {"heading": line[3:].strip(), "lines": []}
            continue
        current["lines"].append(line)
    sections.append(current)
    intro = sections.pop(0)
    return {"title": title,
            "intro": "\n".join(intro["lines"]).strip(),
            "sections": [{"heading": s["heading"], "body": "\n".join(s["lines"]).strip()}
                         for s in sections]}


def lede_of(intro):
    """First prose paragraph of the intro, skipping the badges and the notice blockquotes."""
    for block in re.split(r"\n\s*\n", intro):
        b = block.strip()
        if not b or b.startswith(("[![", ">", "|", "```", "<")):
            continue
        return " ".join(b.split("\n"))
    return ""


# --------------------------------------------------------------------------- fatti dal repo
def parse_variants(workflow):
    """Publish workflow matrix → [{ffmpeg, nvcodec, default}] in declaration order.
    The publish workflow is the source: it is the only file deciding what reaches the registry."""
    variants, cur = [], None
    for line in workflow.split("\n"):
        m = re.match(r"^\s*-\s+ffmpeg:\s*'([^']+)'", line)
        if m:
            if cur:
                variants.append(cur)
            cur = {"ffmpeg": m.group(1), "nvcodec": "", "default": False}
            continue
        if cur is None:
            continue
        m = re.match(r"^\s+nvcodec:\s*'([^']+)'", line)
        if m:
            cur["nvcodec"] = m.group(1)
            continue
        m = re.match(r"^\s+default:\s*(true|false)", line)
        if m:
            cur["default"] = m.group(1) == "true"
            continue
        if re.match(r"^\s*steps:", line):
            break
    if cur:
        variants.append(cur)
    return variants


def driver_floor(nvcodec):
    """nv-codec-headers branch → the host's minimum NVIDIA driver. Raises ValueError for an
    unmapped branch: a red build beats a page promising compatibility nobody verified."""
    if nvcodec not in DRIVER_FLOOR:
        raise ValueError(f"unknown minimum driver for {nvcodec!r}: add it to DRIVER_FLOOR "
                         f"after checking it against the NVIDIA matrix")
    return DRIVER_FLOOR[nvcodec]


def parse_enabled(dockerfile):
    """The `--enable-*` flags of ./configure, skipping comments (where `--enable-nonfree` is only
    mentioned to say not to use it: picking it up from there would make the page advertise a
    non-redistributable binary)."""
    flags = []
    for line in dockerfile.split("\n"):
        if line.lstrip().startswith("#"):
            continue
        for m in re.finditer(r"--enable-([a-z0-9_.-]+)", line):
            if m.group(1) not in flags:
                flags.append(m.group(1))
    return flags


def count_smoke_assertions(script):
    """How many assertions tests/smoke.sh runs: each `ok`/`ko` call counts once per iteration of
    the `for` loop around it (the two codec sections are loops, not repeated lines)."""
    total, stack = 0, []
    for line in script.split("\n"):
        s = line.strip()
        m = re.match(r"^for\s+\w+\s+in\s+(.+?);\s*do\s*$", s)
        if m:
            stack.append(len(m.group(1).split()))
            continue
        if s == "done" and stack:
            stack.pop()
            continue
        if re.match(r"^ok\s+\"", s):
            mult = 1
            for n in stack:
                mult *= n
            total += mult
    return total


# --------------------------------------------------------------------------- pagina
def _slug(s):
    return re.sub(r"\s+", "-", re.sub(r"[^\w\s-]", "", s.lower()).strip())


CSS = """
:root {
  --bg:#fbfaf8; --panel:#fff; --line:#e6e1d9; --ink:#1b1a18; --muted:#6b665e;
  --accent:#1f7a5a; --accent-soft:#e3f2eb; --warn:#9a4a1f; --warn-soft:#fbeade; --code-bg:#f4f1ec;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace;
  --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root { --bg:#0f100f; --panel:#161817; --line:#282c29; --ink:#e9ece9; --muted:#96a09a;
          --accent:#5ed3a4; --accent-soft:#12251d; --warn:#e8a87c; --warn-soft:#271a12; --code-bg:#181b19; }
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:5rem}
body{margin:0;background:var(--bg);color:var(--ink);font:400 17px/1.65 var(--sans);-webkit-font-smoothing:antialiased}
.wrap{max-width:62rem;margin:0 auto;padding:0 1.5rem}
a{color:var(--accent);text-decoration-thickness:1px;text-underline-offset:2px}
h2,h3{letter-spacing:-.01em;line-height:1.25}
code{font-family:var(--mono);font-size:.88em}
:not(pre)>code{background:var(--code-bg);padding:.12em .38em;border-radius:4px}
pre{background:var(--code-bg);border:1px solid var(--line);border-radius:10px;padding:1rem 1.1rem;overflow-x:auto;font-size:.84rem;line-height:1.6}
pre code{background:none;padding:0}
table{width:100%;border-collapse:collapse;font-size:.93rem;margin:1.2rem 0}
th,td{text-align:left;padding:.6rem .7rem;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:.76rem;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
blockquote{margin:1.4rem 0;padding:.9rem 1.1rem;background:var(--warn-soft);border-left:3px solid var(--warn);border-radius:0 8px 8px 0}
blockquote p{margin:0;color:var(--ink)}
header.top{position:sticky;top:0;z-index:10;backdrop-filter:blur(10px);background:color-mix(in srgb,var(--bg) 86%,transparent);border-bottom:1px solid var(--line)}
header.top .wrap{display:flex;align-items:center;gap:1.5rem;height:3.75rem}
.brand{display:inline-flex;align-items:center;gap:.55rem;font-weight:650;letter-spacing:.04em;color:var(--ink);text-decoration:none}
header.top nav{margin-left:auto;display:flex;gap:1.1rem;flex-wrap:wrap}
header.top nav a{color:var(--muted);text-decoration:none;font-size:.86rem}
header.top nav a:hover{color:var(--ink)}
.hero{padding:4rem 0 1rem}
.eyebrow{display:inline-block;font:600 .72rem/1 var(--mono);letter-spacing:.14em;text-transform:uppercase;color:var(--accent);background:var(--accent-soft);border-radius:99px;padding:.45rem .8rem;margin-bottom:1.4rem}
.hero h1{font-size:clamp(2.4rem,6.5vw,3.9rem);line-height:1.02;margin:0 0 1.1rem;letter-spacing:-.03em}
.lede{font-size:clamp(1.02rem,2.2vw,1.24rem);color:var(--muted);max-width:44rem;margin:0 0 1.6rem}
.lede strong{color:var(--ink);font-weight:600}
.cta{display:flex;gap:.7rem;flex-wrap:wrap;margin-bottom:.5rem}
.btn{display:inline-block;padding:.62rem 1.05rem;border-radius:8px;font-size:.92rem;font-weight:600;text-decoration:none;border:1px solid var(--line)}
.btn-primary{background:var(--accent);color:var(--bg);border-color:transparent}
.btn-ghost{color:var(--ink)}
.pull{display:flex;gap:.6rem;align-items:center;margin:1.6rem 0 0;font-family:var(--mono);font-size:.8rem;color:var(--muted);flex-wrap:wrap}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(11rem,1fr));gap:1rem;margin:2.5rem 0 1rem}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:1rem 1.1rem}
.stat b{display:block;font-size:1.65rem;letter-spacing:-.02em;line-height:1.1}
.stat span{font-size:.8rem;color:var(--muted)}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(16rem,1fr));gap:1rem;margin:1.4rem 0}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:1.1rem 1.15rem}
.card.is-default{border-color:var(--accent)}
.card h3{margin:.1rem 0 .5rem;font-size:1.15rem;font-family:var(--mono)}
.card dl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:.25rem .7rem;font-size:.88rem}
.card dt{color:var(--muted)}
.card dd{margin:0}
.tag{display:inline-block;font-family:var(--mono);font-size:.74rem;background:var(--code-bg);border:1px solid var(--line);border-radius:99px;padding:.18rem .5rem;margin:.2rem .2rem 0 0;color:var(--muted)}
.tag.on{color:var(--accent);border-color:var(--accent);background:var(--accent-soft)}
.badge{display:inline-block;font:600 .7rem/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--accent);background:var(--accent-soft);border-radius:5px;padding:.3rem .45rem;margin-left:.5rem;vertical-align:middle}
section{padding:2.2rem 0;border-top:1px solid var(--line)}
section h2{font-size:clamp(1.4rem,3vw,1.85rem);margin:0 0 1rem}
section h2 a{color:inherit;text-decoration:none}
section h2 a:hover{color:var(--accent)}
footer{border-top:1px solid var(--line);padding:2.5rem 0 3.5rem;color:var(--muted);font-size:.88rem}
footer a{color:var(--muted)}
@media (max-width:640px){ .hero{padding-top:2.5rem} .card dl{grid-template-columns:1fr} }
"""


def render(root=ROOT):
    """The full page HTML."""
    readme = open(os.path.join(root, "README.md"), encoding="utf-8").read()
    workflow = open(os.path.join(root, ".github", "workflows", "docker-publish.yml"), encoding="utf-8").read()
    dockerfile = open(os.path.join(root, "Dockerfile"), encoding="utf-8").read()
    smoke = open(os.path.join(root, "tests", "smoke.sh"), encoding="utf-8").read()

    doc = parse_readme(readme)
    variants = parse_variants(workflow)
    enabled = parse_enabled(dockerfile)
    assertions = count_smoke_assertions(smoke)
    default = next((v for v in variants if v["default"]), variants[0])
    lede = lede_of(doc["intro"])
    description = (re.sub(r"\*\*|`", "", lede).split(". ")[0] or lede)[:200].strip().rstrip(".") + "."
    headline = f"{doc['title']} — FFmpeg {default['ffmpeg']} with NVENC, on GHCR"

    logo = open(os.path.join(HERE, "assets", "logo.svg"), encoding="utf-8").read()
    favicon = "data:image/svg+xml," + re.sub(r"\n\s*", "", logo).replace("#", "%23").replace('"', "%22")

    nav = "\n".join(f'<a href="#{_slug(s["heading"])}">{escape(s["heading"])}</a>'
                    for s in doc["sections"][:5])

    cards = []
    for v in variants:
        tags = [f"latest-ffmpeg{v['ffmpeg']}", f"vX.Y.Z-ffmpeg{v['ffmpeg']}"]
        if v["default"]:
            tags = ["latest", "vX.Y.Z"] + tags
        cards.append(f"""      <article class="card{' is-default' if v['default'] else ''}">
        <h3>FFmpeg {escape(v['ffmpeg'])}{'<span class="badge">default</span>' if v['default'] else ''}</h3>
        <dl>
          <dt>nv-codec-headers</dt><dd><code>{escape(v['nvcodec'])}</code></dd>
          <dt>driver NVIDIA</dt><dd>&ge; {driver_floor(v['nvcodec'])}</dd>
        </dl>
        <p>{''.join(f'<span class="tag">{escape(t)}</span>' for t in tags)}</p>
      </article>""")

    chips = "".join(
        f'<span class="tag{" on" if f in ("nvenc", "gpl") else ""}">--enable-{escape(f)}</span>'
        for f in enabled)

    stats = f"""    <div class="stats">
      <div class="stat"><b>{len(variants)}</b><span>variants published on every tag</span></div>
      <div class="stat"><b>{assertions}</b><span>smoke-test assertions gating the publish</span></div>
      <div class="stat"><b>{len(enabled)}</b><span><code>--enable-*</code> options in configure</span></div>
      <div class="stat"><b>0</b><span><code>--enable-nonfree</code>: redistributable image</span></div>
    </div>"""

    sections = []
    for s in doc["sections"]:
        sid = _slug(s["heading"])
        sections.append(f"""  <section id="{sid}">
    <h2><a href="#{sid}">{escape(s['heading'])}</a></h2>
{md_to_html(s['body'])}
  </section>""")

    intro_notes = md_to_html("\n\n".join(
        b for b in re.split(r"\n\s*\n", doc["intro"]) if b.strip().startswith(">")))

    json_ld = json.dumps({
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "WebSite", "@id": SITE + "#website", "url": SITE,
             "name": doc["title"], "description": description, "inLanguage": "en"},
            {"@type": "SoftwareSourceCode", "@id": SITE + "#repo", "name": doc["title"],
             "description": description, "url": SITE, "codeRepository": REPO,
             "programmingLanguage": "Dockerfile", "runtimePlatform": "Docker",
             "license": "https://www.gnu.org/licenses/gpl-3.0.html",
             "author": {"@type": "Person", "name": "Allan Nava"}},
        ],
    }, ensure_ascii=False).replace("<", "\\u003c")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(headline)}</title>
<meta name="description" content="{escape(description)}">
<link rel="canonical" href="{SITE}">
<meta name="theme-color" content="#1f7a5a" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0f100f" media="(prefers-color-scheme: dark)">
<meta property="og:type" content="website">
<meta property="og:site_name" content="{escape(doc['title'])}">
<meta property="og:locale" content="en_GB">
<meta property="og:url" content="{SITE}">
<meta property="og:title" content="{escape(headline)}">
<meta property="og:description" content="{escape(description)}">
<meta property="og:image" content="{SITE}assets/social-preview.svg">
<meta property="og:image:alt" content="{escape(headline)}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{escape(headline)}">
<meta name="twitter:description" content="{escape(description)}">
<meta name="twitter:image" content="{SITE}assets/social-preview.svg">
<link rel="icon" href="{favicon}">
<link rel="apple-touch-icon" href="assets/logo.svg">
<script type="application/ld+json">{json_ld}</script>
<style>{CSS}</style>
</head>
<body>
<header class="top">
  <div class="wrap">
    <a class="brand" href="#top">{logo.replace('<svg', '<svg width="26" height="26"', 1)} {escape(doc['title'])}</a>
    <nav>
{nav}
      <a href="{REPO}">GitHub</a>
    </nav>
  </div>
</header>

<main class="wrap" id="top">
  <div class="hero">
    <span class="eyebrow">NVENC · GHCR · multi-stage</span>
    <h1>FFmpeg with NVENC,<br>in a container that leaves the compiler behind</h1>
    <p class="lede">{_inline(lede)}</p>
    <div class="cta">
      <a class="btn btn-primary" href="#published-images">Images and tags</a>
      <a class="btn btn-ghost" href="{REPO}">Code on GitHub</a>
      <a class="btn btn-ghost" href="{BLOB}/docs/roadmap.md">Roadmap</a>
    </div>
    <div class="pull"><code>docker pull {IMAGE}:latest</code></div>
{intro_notes}
{stats}
    <div class="cards">
{chr(10).join(cards)}
    </div>
    <p class="lede" style="font-size:.95rem">Codecs and filters compiled into the binary:</p>
    <p>{chips}</p>
  </div>

{chr(10).join(sections)}
</main>

<footer>
  <div class="wrap">
    <p>Page generated by <a href="{BLOB}/site/build.py"><code>site/build.py</code></a> from
    <a href="{BLOB}/README.md"><code>README.md</code></a>, the matrix in
    <a href="{BLOB}/.github/workflows/docker-publish.yml"><code>docker-publish.yml</code></a>, the
    <a href="{BLOB}/Dockerfile"><code>Dockerfile</code></a> and
    <a href="{BLOB}/tests/smoke.sh"><code>tests/smoke.sh</code></a>: when the repository changes, the page changes.</p>
    <p>MIT repository · GPL-3.0-or-later image (libx264/libx265) · &copy; Allan Nava</p>
  </div>
</footer>
</body>
</html>
"""


def sitemap():
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
            f'  <url><loc>{SITE}</loc></url>\n'
            '</urlset>\n')


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate the GitHub Page into site/dist/.")
    ap.add_argument("--out", default=os.path.join(HERE, "dist"))
    ap.add_argument("--root", default=ROOT)
    ap.add_argument("--check", action="store_true",
                    help="writes nothing: exit 1 if the output differs from what is on disk (for CI)")
    ap.add_argument("--print-variants", action="store_true",
                    help="print the publish matrix as `<version> <sdk branch> <default|->` and exit; "
                         "this is how the shell scripts read the matrix instead of copying it")
    args = ap.parse_args(argv)

    if args.print_variants:
        with open(os.path.join(args.root, ".github", "workflows", "docker-publish.yml"),
                  encoding="utf-8") as f:
            for v in parse_variants(f.read()):
                print(f"{v['ffmpeg']} {v['nvcodec']} {'default' if v['default'] else '-'}")
        return 0

    page = render(args.root)
    index = os.path.join(args.out, "index.html")

    if args.check:
        existing = open(index, encoding="utf-8").read() if os.path.isfile(index) else ""
        if existing != page:
            print("site/dist is stale: re-run `python3 site/build.py`")
            return 1
        print("site/dist is up to date.")
        return 0

    os.makedirs(os.path.join(args.out, "assets"), exist_ok=True)
    open(index, "w", encoding="utf-8").write(page)
    open(os.path.join(args.out, "sitemap.xml"), "w", encoding="utf-8").write(sitemap())
    open(os.path.join(args.out, ".nojekyll"), "w", encoding="utf-8").write("")   # Pages: skip Jekyll
    for asset in os.listdir(os.path.join(HERE, "assets")):
        shutil.copyfile(os.path.join(HERE, "assets", asset), os.path.join(args.out, "assets", asset))
    print(f"wrote {os.path.relpath(index)} ({len(page) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
