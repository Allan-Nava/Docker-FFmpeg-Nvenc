# syntax=docker/dockerfile:1

# Sorgente unica di verita per tutte le varianti dell'immagine.
# La matrice (FFmpeg 5.1.2 / 6.0 / 7.1.1) vive nei workflow, non in Dockerfile duplicati.
#
#   docker build --build-arg FFMPEG_VERSION=6.0 --build-arg NVCODEC_BRANCH=sdk/12.0 -t ffmpeg-nvenc:6.0 .
#
# NB: i nomi versionati dei pacchetti runtime (libx264-164, libx265-199, libvpx7) sono
# specifici di Debian 12 (bookworm). Cambiando DEBIAN_VERSION vanno riallineati.

ARG DEBIAN_VERSION=12

##############################################################################
# Stage 1 — builder: toolchain, headers NVENC e compilazione di FFmpeg
##############################################################################
FROM debian:${DEBIAN_VERSION}-slim AS builder

ARG FFMPEG_VERSION=7.1.1

# Deve soddisfare il check pkg-config `ffnvcodec` del configure di FFmpeg:
#   FFmpeg 5.1.x -> ffnvcodec >= 9.1.23.1   (sdk/11.0 = 11.0.10.4.1)
#   FFmpeg 6.0   -> ffnvcodec >= 12.0.16.0  (sdk/12.0 = 12.0.16.3.0)
#   FFmpeg 7.1.x -> ffnvcodec >= 12.1.14.0  (sdk/12.1 = 12.1.14.2.0)
# Branch piu alto = driver NVIDIA minimo piu alto: non alzarlo senza motivo.
ARG NVCODEC_BRANCH=sdk/12.1

ARG DEBIAN_FRONTEND=noninteractive

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# hadolint ignore=DL3008
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
      ca-certificates \
      curl \
      git \
      make \
      nasm \
      pkg-config \
      xz-utils \
      yasm \
      libass-dev \
      libfontconfig1-dev \
      libfreetype6-dev \
      libfribidi-dev \
      libharfbuzz-dev \
      libmp3lame-dev \
      libnuma-dev \
      libopus-dev \
      libspeex-dev \
      libtheora-dev \
      libvorbis-dev \
      libvpx-dev \
      libx264-dev \
      libx265-dev \
      libxml2-dev \
      zlib1g-dev \
 && rm -rf /var/lib/apt/lists/*

# Header NVENC/NVDEC. Non serve il CUDA toolkit: NVENC richiede solo ffnvcodec.
RUN git clone --branch "${NVCODEC_BRANCH}" --depth 1 \
      https://github.com/FFmpeg/nv-codec-headers.git /tmp/nv-codec-headers \
 && make -C /tmp/nv-codec-headers install \
 && rm -rf /tmp/nv-codec-headers

WORKDIR /usr/src/ffmpeg
RUN curl -fsSL --retry 3 --retry-connrefused \
      "https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.xz" -o /tmp/ffmpeg.tar.xz \
 && tar -xf /tmp/ffmpeg.tar.xz -C /usr/src/ffmpeg --strip-components=1 \
 && rm /tmp/ffmpeg.tar.xz

# Niente --enable-nonfree: renderebbe il binario NON ridistribuibile, e nessuna
# componente nonfree e abilitata. Niente -I/-L verso /usr/local/cuda: il toolkit
# CUDA non e installato e NVENC non lo richiede.
RUN ./configure \
      --prefix=/usr/local \
      --enable-gpl \
      --enable-version3 \
      --disable-debug \
      --disable-doc \
      --disable-ffplay \
      --disable-indev=sndio \
      --disable-outdev=sndio \
      --enable-nvenc \
      --enable-fontconfig \
      --enable-gray \
      --enable-libass \
      --enable-libfreetype \
      --enable-libmp3lame \
      --enable-libopus \
      --enable-libspeex \
      --enable-libtheora \
      --enable-libvorbis \
      --enable-libvpx \
      --enable-libx264 \
      --enable-libx265 \
      --enable-libxml2 \
 && make -j"$(nproc)" \
 && make install

# Gate di build: se NVENC non e finito nel binario, l'immagine non deve esistere.
# NB: niente `ffmpeg ... | grep -q` — grep esce al primo match, ffmpeg prende
# SIGPIPE e con `pipefail` la pipeline fallisce con 141 anche quando il test passa.
RUN /usr/local/bin/ffmpeg -hide_banner -encoders > /tmp/encoders.txt \
 && grep -q h264_nvenc /tmp/encoders.txt \
 && grep -q hevc_nvenc /tmp/encoders.txt \
 && rm /tmp/encoders.txt

##############################################################################
# Stage 2 — runtime: solo binari e librerie condivise necessarie
##############################################################################
FROM debian:${DEBIAN_VERSION}-slim AS runtime

ARG DEBIAN_FRONTEND=noninteractive
ARG FFMPEG_VERSION=7.1.1
ARG NVCODEC_BRANCH=sdk/12.1

LABEL org.opencontainers.image.title="Docker-FFmpeg-Nvenc" \
      org.opencontainers.image.description="FFmpeg ${FFMPEG_VERSION} con encoder NVIDIA NVENC (h264_nvenc, hevc_nvenc)" \
      org.opencontainers.image.authors="Allan Nava" \
      org.opencontainers.image.source="https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc" \
      org.opencontainers.image.licenses="GPL-3.0-or-later" \
      media.hiway.ffmpeg.version="${FFMPEG_VERSION}" \
      media.hiway.nvcodec.branch="${NVCODEC_BRANCH}"

# `all` esporrebbe capability non necessarie a una transcodifica.
ENV NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=video,compute,utility \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PATH=/usr/local/bin:$PATH

# hadolint ignore=DL3008
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      ca-certificates \
      fontconfig \
      libass9 \
      libfontconfig1 \
      libfreetype6 \
      libfribidi0 \
      libharfbuzz0b \
      libmp3lame0 \
      libnuma1 \
      libopus0 \
      libspeex1 \
      libtheora0 \
      libvorbis0a \
      libvorbisenc2 \
      libvpx7 \
      libx264-164 \
      libx265-199 \
      libxml2 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 1000 --shell /bin/bash ffmpeg \
 && mkdir -p /data \
 && chown ffmpeg:ffmpeg /data

COPY --from=builder /usr/local/bin/ffmpeg  /usr/local/bin/ffmpeg
COPY --from=builder /usr/local/bin/ffprobe /usr/local/bin/ffprobe

# Gate: il binario deve funzionare con le sole librerie dello stage runtime.
RUN ffmpeg -hide_banner -version \
 && ffmpeg -hide_banner -encoders > /tmp/encoders.txt \
 && grep -q h264_nvenc /tmp/encoders.txt \
 && rm /tmp/encoders.txt

USER ffmpeg
WORKDIR /data

ENTRYPOINT ["ffmpeg"]
CMD ["-version"]
