#!/usr/bin/env bash
#
# Verify that GHCR carries exactly the tags the publish workflow should have pushed.
#
# Usage:
#   ./tests/verify-registry.sh v2.1.0            # check the tags for that release
#   ./tests/verify-registry.sh v2.1.0 --strict   # also fail on tags nobody expected
#   IMAGE=ghcr.io/other/name ./tests/verify-registry.sh v2.1.0
#
# The expected list is GENERATED, not written here: the matrix comes from the publish workflow via
# `site/build.py --print-variants` and the tags from `docs/scripts/image-tags.py`, the same code the
# workflow itself uses. A hardcoded list here would agree with itself and with nothing else.
#
# No credentials needed: GHCR issues an anonymous pull token for a public package. That is
# deliberate — a check that requires a login is a check nobody runs.
#
# Exit: 0 when every expected tag exists, 1 otherwise (2 on usage error).

set -euo pipefail

cd "$(dirname "$0")/.."

usage() { sed -n '3,18p' "$0" | sed 's/^# \{0,1\}//'; }

if [[ $# -eq 0 || "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

RELEASE="$1"; shift
STRICT=0
[[ "${1:-}" == "--strict" ]] && STRICT=1

IMAGE="${IMAGE:-ghcr.io/allan-nava/docker-ffmpeg-nvenc}"
REPO_PATH="${IMAGE#ghcr.io/}"

echo "Registry : $IMAGE"
echo "Release  : $RELEASE"

# --- what SHOULD be there (generated from the workflow matrix) ---------------
EXPECTED=$(while read -r version branch default; do
  ARGS=(--image "$IMAGE" --release "$RELEASE" --ffmpeg "$version")
  if [[ "$default" == "default" ]]; then
    ARGS+=(--default)
  fi
  python3 docs/scripts/image-tags.py "${ARGS[@]}"
  : "$branch"   # the branch is not part of the tag; read for clarity
done < <(python3 site/build.py --print-variants) | sed "s|^$IMAGE:||" | sort -u)

# --- what IS there ------------------------------------------------------------
TOKEN=$(curl -fsSL "https://ghcr.io/token?scope=repository:${REPO_PATH}:pull&service=ghcr.io" \
        | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')
ACTUAL=$(curl -fsSL -H "Authorization: Bearer $TOKEN" "https://ghcr.io/v2/${REPO_PATH}/tags/list" \
         | python3 -c 'import sys,json; print("\n".join(json.load(sys.stdin).get("tags") or []))' \
         | sort -u)

# A tag existing is not the same as a tag being right: `:latest` on this registry has existed since
# 2023 while pointing at an image that cannot start on a modern driver. So the floating tags are also
# compared BY DIGEST against the exact release tag they are supposed to alias.
digest_of() {
  curl -fsSL -o /dev/null -D - \
    -H "Authorization: Bearer $TOKEN" \
    -H "Accept: application/vnd.oci.image.index.v1+json" \
    -H "Accept: application/vnd.oci.image.manifest.v1+json" \
    -H "Accept: application/vnd.docker.distribution.manifest.list.v2+json" \
    -H "Accept: application/vnd.docker.distribution.manifest.v2+json" \
    "https://ghcr.io/v2/${REPO_PATH}/manifests/$1" 2>/dev/null \
    | tr -d '\r' | awk -F': ' 'tolower($1)=="docker-content-digest" {print $2}'
}

MISSING=$(comm -23 <(echo "$EXPECTED") <(echo "$ACTUAL"))
EXTRA=$(comm -13 <(echo "$EXPECTED") <(echo "$ACTUAL"))

echo
echo "Expected : $(echo "$EXPECTED" | grep -c .) tags"
echo "On GHCR  : $(echo "$ACTUAL" | grep -c .) tags"

fail=0
if [[ -n "$MISSING" ]]; then
  printf '\n\033[31mMISSING\033[0m (generated but not on the registry):\n'
  while IFS= read -r t; do echo "  $t"; done <<< "$MISSING"
  fail=1
else
  printf '\n\033[32mOK\033[0m every expected tag is on the registry\n'
fi

# --- do the aliases point at the same image as the exact tag? -----------------
if [[ -z "$MISSING" ]]; then
  echo
  while read -r version _ default; do
    exact="$RELEASE-ffmpeg$version"
    exact="${exact#v}"
    want=$(digest_of "$exact")
    aliases=("latest-ffmpeg$version")
    if [[ "$default" == "default" ]]; then
      aliases+=("latest" "${RELEASE#v}")
    fi
    for alias in "${aliases[@]}"; do
      got=$(digest_of "$alias")
      if [[ "$got" == "$want" && -n "$want" ]]; then
        printf '\033[32mOK\033[0m   %-24s == %s\n' "$alias" "$exact"
      else
        printf '\033[31mFAIL\033[0m %-24s points at %s, expected %s (%s)\n' \
          "$alias" "${got:-nothing}" "${want:-nothing}" "$exact"
        fail=1
      fi
    done
  done < <(python3 site/build.py --print-variants)
fi

if [[ -n "$EXTRA" ]]; then
  printf '\n\033[33mUNEXPECTED\033[0m (on the registry, not generated for this release):\n'
  while IFS= read -r t; do echo "  $t"; done <<< "$EXTRA"
  echo "  (leftovers from older schemes or other releases — see the ghcr-tag-hygiene backlog item)"
  [[ "$STRICT" -eq 1 ]] && fail=1
fi

exit "$fail"
