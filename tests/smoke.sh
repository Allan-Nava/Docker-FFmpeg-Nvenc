#!/usr/bin/env bash
#
# Smoke test for the Docker-FFmpeg-Nvenc image.
#
#   ./tests/smoke.sh <image> [expected-ffmpeg-version]
#
# No GPU required: it checks that the NVENC encoders are COMPILED into the binary and that the
# binary really runs with the runtime stage's libraries alone. The end-to-end check on a GPU is
# tests/gpu.sh (which needs an NVIDIA host).

set -euo pipefail

IMAGE="${1:?usage: $0 <image> [expected-ffmpeg-version]}"
EXPECTED_VERSION="${2:-}"

PASS=0
FAIL=0

ok()   { printf '  \033[32mOK\033[0m   %s\n' "$1"; PASS=$((PASS + 1)); }
ko()   { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAIL=$((FAIL + 1)); }
section() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# Runs a command inside the image, bypassing the ffmpeg ENTRYPOINT.
in_image() { docker run --rm --entrypoint /bin/bash "$IMAGE" -c "$1"; }

printf '\033[1mSmoke test\033[0m image: %s\n' "$IMAGE"

# ---------------------------------------------------------------------------
section "1. Binaries present and working"

if BANNER=$(docker run --rm "$IMAGE" -hide_banner -version 2>&1); then
  ok "ffmpeg -version exits 0 (ffmpeg ENTRYPOINT active)"
else
  ko "ffmpeg -version fails"
  echo "$BANNER"
  exit 1
fi

if in_image 'ffprobe -hide_banner -version >/dev/null'; then
  ok "ffprobe present and working"
else
  ko "ffprobe missing or broken"
fi

# ---------------------------------------------------------------------------
section "2. FFmpeg version"

VERSION_LINE=$(printf '%s\n' "$BANNER" | head -n 1)
echo "     $VERSION_LINE"
if [[ -n "$EXPECTED_VERSION" ]]; then
  if [[ "$VERSION_LINE" == *"$EXPECTED_VERSION"* ]]; then
    ok "expected version: $EXPECTED_VERSION"
  else
    ko "expected version $EXPECTED_VERSION, found: $VERSION_LINE"
  fi
fi

# ---------------------------------------------------------------------------
section "3. NVENC encoders compiled in"

ENCODERS=$(docker run --rm "$IMAGE" -hide_banner -encoders 2>/dev/null)
for enc in h264_nvenc hevc_nvenc; do
  if grep -q "\b${enc}\b" <<<"$ENCODERS"; then
    ok "encoder $enc present"
  else
    ko "encoder $enc MISSING — the image does not serve its purpose"
  fi
done

# ---------------------------------------------------------------------------
section "4. Surrounding codecs enabled"

for enc in libx264 libx265 libvpx-vp9 libmp3lame libopus; do
  if grep -q "\b${enc}\b" <<<"$ENCODERS"; then
    ok "encoder $enc present"
  else
    ko "encoder $enc missing"
  fi
done

# ---------------------------------------------------------------------------
section "5. Licence of the artefact"

if grep -q -- '--enable-nonfree' <<<"$BANNER"; then
  ko "built with --enable-nonfree: the binary is NOT redistributable"
else
  ok "no --enable-nonfree (binary redistributable under GPL)"
fi

if grep -q -- '--enable-gpl' <<<"$BANNER"; then
  ok "GPL build (--enable-gpl, required by libx264/libx265)"
else
  ko "--enable-gpl missing but libx264/libx265 expected"
fi

# ---------------------------------------------------------------------------
section "6. Real transcode (CPU, no GPU)"

if in_image 'ffmpeg -hide_banner -loglevel error -f lavfi -i testsrc=size=320x240:rate=10:duration=1 \
    -c:v libx264 -preset ultrafast -f mp4 /tmp/out.mp4 -y \
  && ffprobe -hide_banner -loglevel error -show_entries stream=codec_name -of csv=p=0 /tmp/out.mp4 \
     | grep -q h264'; then
  ok "end-to-end libx264 transcode + ffprobe of the result"
else
  ko "libx264 transcode failed"
fi

# ---------------------------------------------------------------------------
section "7. Container hygiene"

if [[ "$(in_image 'id -u')" != "0" ]]; then
  ok "the container does not run as root (uid $(in_image 'id -u'))"
else
  ko "the container runs as root"
fi

# shellcheck disable=SC2016  # the variable must expand INSIDE the container
CAPS=$(in_image 'echo "$NVIDIA_DRIVER_CAPABILITIES"')
if [[ "$CAPS" == "video,compute,utility" ]]; then
  ok "NVIDIA_DRIVER_CAPABILITIES limited to video,compute,utility"
else
  ko "unexpected NVIDIA_DRIVER_CAPABILITIES: $CAPS"
fi

if in_image 'command -v gcc >/dev/null 2>&1'; then
  ko "build toolchain present in the final image (multi-stage not effective)"
else
  ok "no compiler in the final image"
fi

if in_image 'test -d /usr/src/ffmpeg'; then
  ko "FFmpeg sources left in the final image"
else
  ok "no FFmpeg sources in the final image"
fi

# ---------------------------------------------------------------------------
printf '\n\033[1mResult:\033[0m %d ok, %d fail\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]]
