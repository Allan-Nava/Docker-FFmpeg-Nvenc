#!/usr/bin/env python3
"""
backlog-lint.py — validate docs/backlog.md WITHOUT touching GitHub (standalone lint for CI/PRs).

Immediate feedback on a push or PR: the validation (unique ids, valid status/priority, known meta
keys, consistent milestone titles) does not wait for the sync to run. The rules live in
`lib/backlog.py` (single source, shared with sync-backlog-to-issues.py and generate-roadmap.py).

Exit codes:
  0 → no errors (warnings are printed but do not block; with --strict they do)
  1 → at least one error (or a warning under --strict)
  2 → usage error (missing file, ...)

Requires: stdlib only.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
import backlog as B   # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Lint docs/backlog.md (standalone, no GitHub).")
    ap.add_argument("--backlog", default=os.path.join(HERE, "..", "backlog.md"))
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors (exit 1)")
    args = ap.parse_args()

    path = os.path.normpath(args.backlog)
    if not os.path.isfile(path):
        print(f"ERROR: backlog not found: {path}", file=sys.stderr)
        return 2

    items = B.parse_backlog(path)
    errors, warnings = B.lint(items)

    n_open = sum(1 for it in items if it["status"].lower() != "done")
    n_ms = len({it["milestone"] for it in items if it["milestone"]})
    print(f"backlog-lint: {len(items)} items ({n_open} open) · {n_ms} distinct milestones")

    for w in warnings:
        print(f"  WARN  {w}")
    for e in errors:
        print(f"  FAIL  {e}")

    fail = bool(errors) or (args.strict and bool(warnings))
    if fail:
        n = len(errors) + (len(warnings) if args.strict else 0)
        print(f"\nbacklog-lint: {n} blocking problem(s).")
        return 1
    print("\nbacklog-lint OK" + (f" ({len(warnings)} non-blocking warning(s))" if warnings else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
