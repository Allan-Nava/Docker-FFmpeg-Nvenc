#!/usr/bin/env python3
"""
next-version.py — decide the version of a commit on main and prepare the CHANGELOG for it.

Used by `.github/workflows/release.yml`: every commit on main becomes a tagged release. The
decision has three inputs — the latest git tag, the CHANGELOG, and the commit subjects since that
tag — and one rule that is easy to get wrong, so it lives here with tests (`tests/test_release.py`)
rather than inline in the workflow:

  1. A CHANGELOG section numbered ABOVE the latest tag is a **pending release**: that version gets
     tagged as-is, no bump. (This repository sat in exactly that state: `[2.0.0]` written in the
     CHANGELOG on 2026-08-09, latest tag `v1.0.1` from 2023 — an entire repair never shipped.)
  2. Otherwise the version is the latest tag bumped by the strongest conventional-commit marker
     found since it: `!`/`BREAKING CHANGE` → major, `feat` → minor, anything else → patch.
  3. No tags and no CHANGELOG sections: start at 0.x.

Releasing does NOT publish images. The tag is created with the `GITHUB_TOKEN`, which by design does
not trigger other workflows, so `docker-publish.yml` stays an explicit act (tag pushed by hand or
its `workflow_dispatch`). That is deliberate: publishing means three 90-minute builds and public
artefacts on GHCR.

Usage:
  python3 docs/scripts/next-version.py                  # print the version it would release
  python3 docs/scripts/next-version.py --explain        # and why
  python3 docs/scripts/next-version.py --apply          # rewrite CHANGELOG.md for that version
  python3 docs/scripts/next-version.py --notes-out FILE # write the release notes for it
Requires: stdlib only (plus `git` on PATH).
"""
import argparse
import datetime
import os
import re
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
CHANGELOG = os.path.join(ROOT, "CHANGELOG.md")

VERSION_RE = re.compile(r"^##\s*\[(\d+\.\d+\.\d+)\](?:\s*-\s*(\S+))?", re.M)
UNRELEASED_RE = re.compile(r"^##\s*\[(?:Unreleased|Non rilasciato)\]\s*$", re.M | re.I)
BREAKING_RE = re.compile(r"^(\w+)(\([^)]*\))?!:|^BREAKING[ -]CHANGE", re.M)
FEAT_RE = re.compile(r"^feat(\([^)]*\))?:", re.M)


def version_key(v):
    return tuple(int(x) for x in str(v).lstrip("v").split(".")[:3])


def bump_kind(subjects):
    """Strongest conventional-commit marker across the given commit messages."""
    blob = "\n".join(subjects)
    if BREAKING_RE.search(blob):
        return "major"
    if FEAT_RE.search(blob):
        return "minor"
    return "patch"


def bump(version, kind):
    major, minor, patch = version_key(version)
    if kind == "major":
        return f"{major + 1}.0.0"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def changelog_versions(text):
    """Released version sections, newest first as they appear in the file."""
    return [m.group(1) for m in VERSION_RE.finditer(text)]


def has_unreleased(text):
    return bool(UNRELEASED_RE.search(text))


def next_version(latest_tag, changelog, subjects):
    """(version, reason) — see the three rules in the module docstring."""
    versions = changelog_versions(changelog)
    base = latest_tag.strip().lstrip("v") if latest_tag and latest_tag.strip() else ""
    pending = [v for v in versions if not base or version_key(v) > version_key(base)]
    if pending:
        top = max(pending, key=version_key)
        return top, (f"pending release: CHANGELOG has [{top}] above the latest tag "
                     f"{'v' + base if base else '(none)'}")
    if base:
        kind = bump_kind(subjects)
        return bump(base, kind), f"{kind} bump from v{base} ({len(subjects)} commit(s) since the tag)"
    kind = bump_kind(subjects)
    return bump("0.0.0", kind), f"first release: {kind} bump from 0.0.0"


def _section_bounds(text, heading_match):
    """Span of a section: from its heading to the next `## ` heading (or EOF)."""
    start = heading_match.start()
    nxt = re.search(r"^##\s", text[heading_match.end():], re.M)
    end = heading_match.end() + nxt.start() if nxt else len(text)
    return start, end


def fold_unreleased(text, version, date):
    """Turn the `[Unreleased]` section into `[version] - date`.

    If a section for that version already exists (the pending-release case), the unreleased content
    is merged into it instead of creating a second section with the same number."""
    um = UNRELEASED_RE.search(text)
    unreleased_body = ""
    if um:
        start, end = _section_bounds(text, um)
        unreleased_body = text[um.end():end].strip("\n")
        text = text[:start] + text[end:]

    vm = re.search(rf"^##\s*\[{re.escape(version)}\].*$", text, re.M)
    if vm:
        line_end = vm.end()
        body = f"\n\n{unreleased_body}" if unreleased_body else ""
        text = (text[:vm.start()] + f"## [{version}] - {date}" + body + text[line_end:])
        return _tidy(text)

    heading = f"## [{version}] - {date}"
    block = heading + (f"\n\n{unreleased_body}" if unreleased_body else "") + "\n"
    first = VERSION_RE.search(text)
    if first:
        return _tidy(text[:first.start()] + block + "\n" + text[first.start():])
    return _tidy(text.rstrip("\n") + "\n\n" + block)


def _tidy(text):
    return re.sub(r"\n{4,}", "\n\n\n", text).rstrip("\n") + "\n"


def release_notes(text, version):
    """Body of one version section, without its heading — the GitHub Release description."""
    m = re.search(rf"^##\s*\[{re.escape(version)}\].*$", text, re.M)
    if not m:
        return ""
    _, end = _section_bounds(text, m)
    return text[m.end():end].strip("\n").strip()


# ----------------------------------------------------------------------------- git
def _git(*args, default=""):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, check=True, text=True,
                              capture_output=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return default


def latest_tag():
    return _git("describe", "--tags", "--abbrev=0", "--match", "v*")


def subjects_since(tag):
    rng = f"{tag}..HEAD" if tag else "HEAD"
    out = _git("log", "--format=%B%x00", rng)
    return [s.strip() for s in out.split("\0") if s.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Decide the next release version and prepare the CHANGELOG.")
    ap.add_argument("--explain", action="store_true", help="also print why that version was chosen")
    ap.add_argument("--apply", action="store_true", help="rewrite CHANGELOG.md for the chosen version")
    ap.add_argument("--notes-out", help="write the release notes for the chosen version to this file")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--changelog", default=CHANGELOG)
    args = ap.parse_args(argv)

    with open(args.changelog, encoding="utf-8") as f:
        text = f.read()
    tag = latest_tag()
    version, reason = next_version(tag, text, subjects_since(tag))

    if args.apply:
        text = fold_unreleased(text, version, args.date)
        with open(args.changelog, "w", encoding="utf-8") as f:
            f.write(text)

    if args.notes_out:
        with open(args.notes_out, "w", encoding="utf-8") as f:
            f.write(release_notes(text, version) + "\n")

    print(version)
    if args.explain:
        print(reason, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
