#!/usr/bin/env bash
#
# End-to-end test on a real NVIDIA GPU.
#
#   ./tests/gpu.sh <image>
#
# Requires: an NVIDIA GPU with NVENC, the driver installed, and the NVIDIA Container Toolkit
# (`docker run --gpus all`). It does NOT run on GitHub-hosted runners: run it on a transcoding
# host before promoting a tag to production.

set -euo pipefail

IMAGE="${1:?usage: $0 <image>}"

if ! docker run --rm --gpus all --entrypoint nvidia-smi "$IMAGE" -L >/dev/null 2>&1; then
  echo "SKIP: no NVIDIA GPU available to the container (needs --gpus all + NVIDIA Container Toolkit)" >&2
  exit 0
fi

echo "GPUs visible to the container:"
docker run --rm --gpus all --entrypoint nvidia-smi "$IMAGE" -L

echo
echo "h264_nvenc transcode on the GPU..."
docker run --rm --gpus all --entrypoint /bin/bash "$IMAGE" -c '
  set -euo pipefail
  ffmpeg -hide_banner -loglevel error \
    -f lavfi -i testsrc=size=1280x720:rate=25:duration=3 \
    -c:v h264_nvenc -preset p4 -f mp4 /tmp/nvenc.mp4 -y
  ffprobe -hide_banner -loglevel error \
    -show_entries stream=codec_name,width,height -of csv=p=0 /tmp/nvenc.mp4
'

echo
echo "hevc_nvenc transcode on the GPU..."
docker run --rm --gpus all --entrypoint /bin/bash "$IMAGE" -c '
  set -euo pipefail
  ffmpeg -hide_banner -loglevel error \
    -f lavfi -i testsrc=size=1280x720:rate=25:duration=3 \
    -c:v hevc_nvenc -preset p4 -f mp4 /tmp/nvenc-hevc.mp4 -y
  ffprobe -hide_banner -loglevel error \
    -show_entries stream=codec_name -of csv=p=0 /tmp/nvenc-hevc.mp4
'

echo
echo "OK: NVENC encoding verified on the GPU."
