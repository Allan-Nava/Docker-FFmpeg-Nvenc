#!/usr/bin/env bash
#
# Build and smoke-test every variant of the publish matrix, locally.
#
# Usage:
#   ./tests/build-matrix.sh                 # all variants
#   ./tests/build-matrix.sh 9.0.1 7.1.5     # only these FFmpeg versions
#   LOG_DIR=logs/my-run ./tests/build-matrix.sh
#
# The matrix is NOT written here: it is read from .github/workflows/docker-publish.yml through
# `site/build.py --print-variants`, so this script cannot test a different set of variants from the
# one CI publishes.
#
# Each build goes to its own log file; the exit code is non-zero if any build or smoke test failed.
# Note: on a non-amd64 workstation this builds for the host architecture, which proves the sources,
# the configure options and the runtime libraries — not the published amd64 artefact.

set -euo pipefail

cd "$(dirname "$0")/.."

usage() {
  sed -n '3,16p' "$0" | sed 's/^# \{0,1\}//'
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

LOG_DIR="${LOG_DIR:-logs/$(date -u +%Y-%m-%d)-build-matrix}"
mkdir -p "$LOG_DIR"

WANTED=("$@")
want() {
  [[ ${#WANTED[@]} -eq 0 ]] && return 0
  local v
  for v in "${WANTED[@]}"; do [[ "$v" == "$1" ]] && return 0; done
  return 1
}

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found: this script builds images, run it where docker is available" >&2
  exit 2
fi

failed=0
built=0

while read -r version branch default; do
  want "$version" || continue
  slug="${version//./-}"
  tag="ffmpeg-nvenc:test-$version"
  marker=""
  [[ "$default" == "default" ]] && marker=" (default variant)"

  printf '\n\033[1m=== FFmpeg %s — %s%s\033[0m\n' "$version" "$branch" "$marker"
  printf '    build  → %s\n' "$LOG_DIR/build-$slug.log"

  if docker build \
        --build-arg "FFMPEG_VERSION=$version" \
        --build-arg "NVCODEC_BRANCH=$branch" \
        --progress=plain -t "$tag" . > "$LOG_DIR/build-$slug.log" 2>&1 \
     && ! grep -q 'ERROR: failed to solve' "$LOG_DIR/build-$slug.log"; then
    echo "    build  OK"
  else
    echo "    build  FAILED — last lines:"
    tail -n 20 "$LOG_DIR/build-$slug.log" | sed 's/^/      /'
    failed=$((failed + 1))
    continue
  fi

  printf '    smoke  → %s\n' "$LOG_DIR/smoke-$slug.log"
  if ./tests/smoke.sh "$tag" "$version" > "$LOG_DIR/smoke-$slug.log" 2>&1; then
    echo "    smoke  $(tail -n 1 "$LOG_DIR/smoke-$slug.log" | tr -d '\033' | sed 's/\[[0-9;]*m//g')"
  else
    echo "    smoke  FAILED:"
    grep -E 'FAIL' "$LOG_DIR/smoke-$slug.log" | sed 's/^/      /'
    failed=$((failed + 1))
    continue
  fi

  size=$(docker image inspect "$tag" --format '{{.Size}}')
  printf '    image  %s MB (%s)\n' "$((size / 1024 / 1024))" "$tag"
  built=$((built + 1))
done < <(python3 site/build.py --print-variants)

printf '\n\033[1mMatrix:\033[0m %d built and tested, %d failed. Logs in %s\n' "$built" "$failed" "$LOG_DIR"
[[ "$failed" -eq 0 ]]
