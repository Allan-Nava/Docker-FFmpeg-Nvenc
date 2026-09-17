#!/usr/bin/env python3
"""
image-tags.py — the tags (and OCI labels) a published image gets.

Two axes that must not be multiplied together:

  * the **repository release** (`v2.1.0`) — an exact, immutable coordinate;
  * the **FFmpeg variant** (`9.0.1`) — which people want to follow *loosely*: "the newest 7.x",
    without chasing patch releases.

So each variant gets one exact tag (`2.1.0-ffmpeg9.0.1`) plus floating pointers at every level of
the FFmpeg version (`latest-ffmpeg9`, `latest-ffmpeg9.0`, `latest-ffmpeg9.0.1`), and only the
default variant additionally takes the unsuffixed repository tags (`latest`, `2.1.0`, `2.1`, `2`).
Combinations like `2-ffmpeg9.0.1` are deliberately absent: they look stable and are not — the next
FFmpeg patch orphans them while the repository major stays put.

This lives in a tested script rather than in workflow YAML because it is the one thing in this
repository that has already broken in silence: before v2.0.0 a semver regex ran against a string the
variant suffix made structurally unmatchable, `:latest` was never published, and nobody noticed for
two years. Tests: tests/test_image_tags.py.

Usage:
  python3 docs/scripts/image-tags.py --image ghcr.io/o/n --release v2.1.0 --ffmpeg 9.0.1 --default
  python3 docs/scripts/image-tags.py --release v2.1.0 --labels --revision "$GITHUB_SHA"
Requires: stdlib only.
"""
import argparse
import datetime
import re
import sys

SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


def normalise_release(release):
    """`v2.1.0` / `2.1.0` → (2, 1, 0). Anything else is refused: a tag derived from a branch name
    would publish garbage next to the real releases."""
    m = SEMVER_RE.match((release or "").strip())
    if not m:
        raise ValueError(f"release {release!r} is not semver (expected vX.Y.Z)")
    return tuple(int(x) for x in m.groups())


def ffmpeg_aliases(version):
    """`9.0.1` → ['9', '9.0', '9.0.1'] — every level someone might reasonably want to follow."""
    parts = version.strip().split(".")
    return [".".join(parts[:i + 1]) for i in range(len(parts))]


def tags_for(image, release, ffmpeg, default=False):
    """Full list of `image:tag` for one matrix row. Deterministic order, no duplicates."""
    major, minor, patch = normalise_release(release)
    version = f"{major}.{minor}.{patch}"
    aliases = ffmpeg_aliases(ffmpeg)
    full = aliases[-1]

    tags = [f"{version}-ffmpeg{full}"]                       # exact: release × variant
    tags += [f"latest-ffmpeg{a}" for a in aliases]           # floating: follow a branch
    if default:
        tags += ["latest", version, f"{major}.{minor}", str(major)]

    seen, out = set(), []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            out.append(f"{image}:{tag}")
    return out


def labels_for(release, revision="", created=""):
    """OCI labels the workflow adds on top of the static ones in the Dockerfile."""
    major, minor, patch = normalise_release(release)
    created = created or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    labels = [f"org.opencontainers.image.version={major}.{minor}.{patch}",
              f"org.opencontainers.image.created={created}"]
    if revision:
        labels.append(f"org.opencontainers.image.revision={revision}")
    return labels


def main(argv=None):
    ap = argparse.ArgumentParser(description="Print the tags (or labels) for a published image.")
    ap.add_argument("--image", help="image name without a tag, e.g. ghcr.io/owner/name")
    ap.add_argument("--release", required=True, help="repository release, e.g. v2.1.0")
    ap.add_argument("--ffmpeg", help="FFmpeg version of this variant, e.g. 9.0.1")
    ap.add_argument("--default", action="store_true", help="this row also takes the unsuffixed tags")
    ap.add_argument("--labels", action="store_true", help="print OCI labels instead of tags")
    ap.add_argument("--revision", default="", help="commit sha for the revision label")
    ap.add_argument("--created", default="", help="RFC3339 build date (defaults to now, UTC)")
    args = ap.parse_args(argv)

    try:
        if args.labels:
            print("\n".join(labels_for(args.release, args.revision, args.created)))
            return 0
        if not args.image or not args.ffmpeg:
            print("--image and --ffmpeg are required unless --labels is used", file=sys.stderr)
            return 2
        print("\n".join(tags_for(args.image, args.release, args.ffmpeg, args.default)))
        return 0
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
