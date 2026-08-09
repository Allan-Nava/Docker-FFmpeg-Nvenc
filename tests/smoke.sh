#!/usr/bin/env bash
#
# Smoke test dell'immagine Docker-FFmpeg-Nvenc.
#
#   ./tests/smoke.sh <immagine> [versione-ffmpeg-attesa]
#
# Non richiede una GPU: verifica che gli encoder NVENC siano COMPILATI nel binario
# e che il binario giri davvero con le sole librerie dello stage runtime.
# La verifica end-to-end su GPU e in tests/gpu.sh (richiede host con NVIDIA).

set -euo pipefail

IMAGE="${1:?uso: $0 <immagine> [versione-ffmpeg-attesa]}"
EXPECTED_VERSION="${2:-}"

PASS=0
FAIL=0

ok()   { printf '  \033[32mOK\033[0m   %s\n' "$1"; PASS=$((PASS + 1)); }
ko()   { printf '  \033[31mFAIL\033[0m %s\n' "$1"; FAIL=$((FAIL + 1)); }
section() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# Esegue un comando dentro l'immagine bypassando l'ENTRYPOINT ffmpeg.
in_image() { docker run --rm --entrypoint /bin/bash "$IMAGE" -c "$1"; }

printf '\033[1mSmoke test\033[0m immagine: %s\n' "$IMAGE"

# ---------------------------------------------------------------------------
section "1. Binari presenti e funzionanti"

if BANNER=$(docker run --rm "$IMAGE" -hide_banner -version 2>&1); then
  ok "ffmpeg -version esce con 0 (ENTRYPOINT ffmpeg attivo)"
else
  ko "ffmpeg -version fallisce"
  echo "$BANNER"
  exit 1
fi

if in_image 'ffprobe -hide_banner -version >/dev/null'; then
  ok "ffprobe presente e funzionante"
else
  ko "ffprobe mancante o rotto"
fi

# ---------------------------------------------------------------------------
section "2. Versione di FFmpeg"

VERSION_LINE=$(printf '%s\n' "$BANNER" | head -n 1)
echo "     $VERSION_LINE"
if [[ -n "$EXPECTED_VERSION" ]]; then
  if [[ "$VERSION_LINE" == *"$EXPECTED_VERSION"* ]]; then
    ok "versione attesa: $EXPECTED_VERSION"
  else
    ko "versione attesa $EXPECTED_VERSION, trovata: $VERSION_LINE"
  fi
fi

# ---------------------------------------------------------------------------
section "3. Encoder NVENC compilati"

ENCODERS=$(docker run --rm "$IMAGE" -hide_banner -encoders 2>/dev/null)
for enc in h264_nvenc hevc_nvenc; do
  if grep -q "\b${enc}\b" <<<"$ENCODERS"; then
    ok "encoder $enc presente"
  else
    ko "encoder $enc MANCANTE — l'immagine non serve al suo scopo"
  fi
done

# ---------------------------------------------------------------------------
section "4. Codec di contorno abilitati"

for enc in libx264 libx265 libvpx-vp9 libmp3lame libopus; do
  if grep -q "\b${enc}\b" <<<"$ENCODERS"; then
    ok "encoder $enc presente"
  else
    ko "encoder $enc mancante"
  fi
done

# ---------------------------------------------------------------------------
section "5. Licenza dell'artefatto"

if grep -q -- '--enable-nonfree' <<<"$BANNER"; then
  ko "build con --enable-nonfree: il binario NON e ridistribuibile"
else
  ok "nessun --enable-nonfree (binario ridistribuibile sotto GPL)"
fi

if grep -q -- '--enable-gpl' <<<"$BANNER"; then
  ok "build GPL (--enable-gpl, richiesto da libx264/libx265)"
else
  ko "--enable-gpl assente ma libx264/libx265 attesi"
fi

# ---------------------------------------------------------------------------
section "6. Transcodifica reale (CPU, senza GPU)"

if in_image 'ffmpeg -hide_banner -loglevel error -f lavfi -i testsrc=size=320x240:rate=10:duration=1 \
    -c:v libx264 -preset ultrafast -f mp4 /tmp/out.mp4 -y \
  && ffprobe -hide_banner -loglevel error -show_entries stream=codec_name -of csv=p=0 /tmp/out.mp4 \
     | grep -q h264'; then
  ok "transcodifica libx264 end-to-end + ffprobe del risultato"
else
  ko "transcodifica libx264 fallita"
fi

# ---------------------------------------------------------------------------
section "7. Igiene del container"

if [[ "$(in_image 'id -u')" != "0" ]]; then
  ok "il container non gira come root (uid $(in_image 'id -u'))"
else
  ko "il container gira come root"
fi

# shellcheck disable=SC2016  # la variabile deve espandersi DENTRO il container
CAPS=$(in_image 'echo "$NVIDIA_DRIVER_CAPABILITIES"')
if [[ "$CAPS" == "video,compute,utility" ]]; then
  ok "NVIDIA_DRIVER_CAPABILITIES limitato a video,compute,utility"
else
  ko "NVIDIA_DRIVER_CAPABILITIES inatteso: $CAPS"
fi

if in_image 'command -v gcc >/dev/null 2>&1'; then
  ko "toolchain di build presente nell'immagine finale (multi-stage non efficace)"
else
  ok "nessun compilatore nell'immagine finale"
fi

if in_image 'test -d /usr/src/ffmpeg'; then
  ko "sorgenti FFmpeg lasciati nell'immagine finale"
else
  ok "nessun sorgente FFmpeg nell'immagine finale"
fi

# ---------------------------------------------------------------------------
printf '\n\033[1mRisultato:\033[0m %d ok, %d fail\n' "$PASS" "$FAIL"
[[ "$FAIL" -eq 0 ]]
