#!/usr/bin/env bash
#
# Commit with the CHANGELOG entry filed automatically.
#
# Usage:
#   ./docs/scripts/commit.sh "fix: the tagging regex never matched"
#   ./docs/scripts/commit.sh "feat: 9.0 variant" --entry "FFmpeg 9.0.1 is now the default, same driver floor"
#   ./docs/scripts/commit.sh "docs: reword the README" --no-changelog
#   ./docs/scripts/commit.sh "chore: tidy" --no-gates          # skip the local gates
#
# What it does, in order:
#   1. checks the subject is a conventional commit (the release tooling reads the bump from it);
#   2. adds a bullet under `## [Unreleased]` in CHANGELOG.md, in the section the type implies —
#      `--entry` is the text you actually want there, and it is almost always worth writing;
#   3. runs ./tests/run-all.sh (everything that does not need docker);
#   4. `git add -A` and commits.
#
# It does NOT push and does NOT tag: tagging is release.yml's job, pushing is yours.

set -euo pipefail

cd "$(dirname "$0")/../.."

usage() { sed -n '3,20p' "$0" | sed 's/^# \{0,1\}//'; }

if [[ $# -eq 0 || "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

MESSAGE="$1"; shift
ENTRY=""
RUN_GATES=1
WRITE_CHANGELOG=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --entry) ENTRY="${2:?--entry needs a text}"; shift 2 ;;
    --no-changelog) WRITE_CHANGELOG=0; shift ;;
    --no-gates) RUN_GATES=0; shift ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

echo "=== subject"
if [[ "$WRITE_CHANGELOG" -eq 1 ]]; then
  echo "=== CHANGELOG"
  if [[ -n "$ENTRY" ]]; then
    python3 docs/scripts/changelog-add.py --message "$MESSAGE" --entry "$ENTRY"
  else
    python3 docs/scripts/changelog-add.py --message "$MESSAGE"
  fi
else
  # Still validate the subject even when no entry is filed.
  python3 docs/scripts/changelog-add.py --message "$MESSAGE" --dry-run > /dev/null
  echo "=== CHANGELOG skipped (--no-changelog)"
fi

if [[ "$RUN_GATES" -eq 1 ]]; then
  echo "=== gates"
  ./tests/run-all.sh
else
  echo "=== gates skipped (--no-gates)"
fi

echo "=== commit"
git add -A
git commit -m "$MESSAGE"
echo
echo "Committed. Nothing was pushed or tagged: release.yml tags on push to main."
