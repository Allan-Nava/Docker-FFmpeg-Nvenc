#!/usr/bin/env bash
#
# Test end-to-end su GPU NVIDIA reale.
#
#   ./tests/gpu.sh <immagine>
#
# Richiede: GPU NVIDIA con NVENC, driver installato e NVIDIA Container Toolkit
# (`docker run --gpus all`). NON gira sui runner GitHub-hosted: eseguirlo su un
# host di transcodifica prima di promuovere un tag in produzione.

set -euo pipefail

IMAGE="${1:?uso: $0 <immagine>}"

if ! docker run --rm --gpus all --entrypoint nvidia-smi "$IMAGE" -L >/dev/null 2>&1; then
  echo "SKIP: nessuna GPU NVIDIA disponibile al container (serve --gpus all + NVIDIA Container Toolkit)" >&2
  exit 0
fi

echo "GPU visibili al container:"
docker run --rm --gpus all --entrypoint nvidia-smi "$IMAGE" -L

echo
echo "Transcodifica h264_nvenc su GPU..."
docker run --rm --gpus all --entrypoint /bin/bash "$IMAGE" -c '
  set -euo pipefail
  ffmpeg -hide_banner -loglevel error \
    -f lavfi -i testsrc=size=1280x720:rate=25:duration=3 \
    -c:v h264_nvenc -preset p4 -f mp4 /tmp/nvenc.mp4 -y
  ffprobe -hide_banner -loglevel error \
    -show_entries stream=codec_name,width,height -of csv=p=0 /tmp/nvenc.mp4
'

echo
echo "Transcodifica hevc_nvenc su GPU..."
docker run --rm --gpus all --entrypoint /bin/bash "$IMAGE" -c '
  set -euo pipefail
  ffmpeg -hide_banner -loglevel error \
    -f lavfi -i testsrc=size=1280x720:rate=25:duration=3 \
    -c:v hevc_nvenc -preset p4 -f mp4 /tmp/nvenc-hevc.mp4 -y
  ffprobe -hide_banner -loglevel error \
    -show_entries stream=codec_name -of csv=p=0 /tmp/nvenc-hevc.mp4
'

echo
echo "OK: encoding NVENC verificato su GPU."
