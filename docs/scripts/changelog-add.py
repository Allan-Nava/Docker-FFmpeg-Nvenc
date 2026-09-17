#!/usr/bin/env python3
"""
changelog-add.py — file an entry under `## [Unreleased]` in CHANGELOG.md.

The section is derived from the commit subject (`feat:` → Added, `fix:` → Fixed, …) so nobody has to
remember Keep a Changelog's vocabulary; the wording is yours: `--entry` writes the sentence you want
instead of the commit subject, which is almost always the better text.

Usage:
  python3 docs/scripts/changelog-add.py --message "fix: the tagging regex never matched"
  python3 docs/scripts/changelog-add.py --message "feat: 9.0 variant" --entry "FFmpeg 9.0.1 is now the default variant, at the same driver floor"
  python3 docs/scripts/changelog-add.py --section Changed --entry "explicit section, no commit subject"
  python3 docs/scripts/changelog-add.py --from-commits        # draft from the commits since the last tag
  python3 docs/scripts/changelog-add.py --message "…" --dry-run
Requires: stdlib only (plus `git` for --from-commits).
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, "lib"))
import changelog as C  # noqa: E402


def _git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, check=True, text=True,
                              capture_output=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def main(argv=None):
    ap = argparse.ArgumentParser(description="Add an entry under [Unreleased] in CHANGELOG.md.")
    ap.add_argument("--changelog", default=os.path.join(ROOT, "CHANGELOG.md"))
    ap.add_argument("--message", help="commit subject; decides the section")
    ap.add_argument("--entry", help="the bullet text (defaults to the commit description)")
    ap.add_argument("--section", choices=C.SECTION_ORDER, help="force the section")
    ap.add_argument("--from-commits", action="store_true",
                    help="draft entries from the commits since the last tag (release fallback)")
    ap.add_argument("--dry-run", action="store_true", help="print the result, write nothing")
    args = ap.parse_args(argv)

    with open(args.changelog, encoding="utf-8") as f:
        text = f.read()

    if args.from_commits:
        tag = _git("describe", "--tags", "--abbrev=0", "--match", "v*")
        log = _git("log", "--format=%B%x00", f"{tag}..HEAD" if tag else "HEAD")
        subjects = [s.strip() for s in log.split("\0") if s.strip()]
        drafted = C.entries_from_commits(subjects)
        if not drafted:
            print("nothing to draft: no conventional commits since the last tag")
            return 0
        new = C.apply_drafted(text, subjects)
        added = sum(len(v) for v in drafted.values())
        print(f"drafted {added} entry/entries from {len(subjects)} commit(s)")
    else:
        section, entry = args.section, args.entry
        if args.message:
            commit = C.parse_subject(args.message)
            if commit is None:
                print(f"not a conventional commit subject: {args.message!r}\n"
                      f"expected `<type>[(scope)][!]: description`, type in "
                      f"{sorted(C.TYPE_SECTION)}", file=sys.stderr)
                return 1
            section = section or C.section_for(commit)
            entry = entry or C.entry_for(commit)
        if not section or not entry:
            print("need --message, or --section with --entry", file=sys.stderr)
            return 2
        new = C.add_entry(text, section, entry)
        print(f"[Unreleased] ▸ {section}: {entry}")

    if args.dry_run:
        return 0
    if new != text:
        with open(args.changelog, "w", encoding="utf-8") as f:
            f.write(new)
    return 0


if __name__ == "__main__":
    sys.exit(main())
