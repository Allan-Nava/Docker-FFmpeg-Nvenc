#!/usr/bin/env bash
#
# Point git at the hooks tracked in .githooks/.
#
# Usage:
#   ./docs/scripts/install-hooks.sh          # install
#   ./docs/scripts/install-hooks.sh --undo   # back to .git/hooks
#
# Hooks live in the repository (not in .git/hooks, which is not versioned) so that the rule everyone
# is held to is the same file everyone can read and change.

set -euo pipefail

cd "$(dirname "$0")/../.."

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  sed -n '3,10p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
fi

if [[ "${1:-}" == "--undo" ]]; then
  git config --unset core.hooksPath || true
  echo "core.hooksPath unset: git is back to .git/hooks"
  exit 0
fi

git config core.hooksPath .githooks
chmod +x .githooks/*
echo "core.hooksPath = .githooks"
echo "installed: $(find .githooks -maxdepth 1 -type f -exec basename {} \; | sort | tr '\n' ' ')"
