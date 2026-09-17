#!/usr/bin/env bash
#
# Every local gate that does not need docker, in the order CI runs them.
#
#   ./tests/run-all.sh
#
# Images are not built here: that is ./tests/build-matrix.sh, which takes minutes rather than
# seconds. This one is meant to be run before every commit.
#
# Linters that are not installed are skipped with a note rather than failing the run: hadolint,
# ShellCheck and actionlint are optional locally and mandatory in CI.
#
# (That capital S is not a typo: a comment line starting with `# shellcheck ...` is parsed as a
# ShellCheck directive and fails with SC1072/SC1073.)

set -euo pipefail

cd "$(dirname "$0")/.."

fail=0
step() { printf '\n\033[1m=== %s\033[0m\n' "$1"; }
ok()   { printf '\033[32mOK\033[0m   %s\n' "$1"; }
ko()   { printf '\033[31mFAIL\033[0m %s\n' "$1"; fail=$((fail + 1)); }
skip() { printf '\033[33mSKIP\033[0m %s (not installed)\n' "$1"; }

step "Unit tests (tooling and page generator)"
if python3 -m unittest discover -s tests -p 'test_*.py'; then ok "unittest"; else ko "unittest"; fi

step "Backlog"
if python3 docs/scripts/backlog-lint.py; then ok "backlog-lint.py"; else ko "backlog-lint.py"; fi

step "Generated pages"
if python3 docs/scripts/generate-roadmap.py --check; then ok "roadmap"; else ko "roadmap (run: python3 docs/scripts/generate-roadmap.py)"; fi
if python3 site/build.py --check; then ok "site/dist"; else ko "site/dist (run: python3 site/build.py)"; fi

step "Commit hooks"
if [[ "$(git config --get core.hooksPath || true)" == ".githooks" ]]; then
  ok "core.hooksPath = .githooks"
else
  printf '\033[33mSKIP\033[0m hooks not installed (run: ./docs/scripts/install-hooks.sh)\n'
fi

step "Release"
printf 'next version: '
if python3 docs/scripts/next-version.py --explain; then ok "next-version.py"; else ko "next-version.py"; fi

step "Linters"
if command -v shellcheck >/dev/null 2>&1; then
  if shellcheck tests/*.sh docs/scripts/*.sh .githooks/*; then ok "shellcheck"; else ko "shellcheck"; fi
else
  skip "shellcheck"
fi

if command -v actionlint >/dev/null 2>&1; then
  if actionlint; then ok "actionlint"; else ko "actionlint"; fi
else
  skip "actionlint"
fi

if command -v hadolint >/dev/null 2>&1; then
  if hadolint Dockerfile; then ok "hadolint"; else ko "hadolint"; fi
elif command -v docker >/dev/null 2>&1; then
  if docker run --rm -i -v "$PWD/.hadolint.yaml:/.hadolint.yaml:ro" hadolint/hadolint hadolint - < Dockerfile; then
    ok "hadolint (container)"
  else
    ko "hadolint (container)"
  fi
else
  skip "hadolint"
fi

printf '\n\033[1mResult:\033[0m %d failing gate(s)\n' "$fail"
[[ "$fail" -eq 0 ]]
