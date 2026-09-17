# syntax=docker/dockerfile:1

# Single source of truth for every variant of the image.
# The matrix (FFmpeg 5.1.10 / 6.0.1 / 7.1.5) lives in the workflows, not in duplicated Dockerfiles.
#
#   docker build --build-arg FFMPEG_VERSION=6.0.1 --build-arg NVCODEC_BRANCH=sdk/12.0 -t ffmpeg-nvenc:6.0.1 .
#
# Note: the versioned runtime package names (libx264-164, libx265-199, libvpx7) are specific to
# Debian 12 (bookworm). Changing DEBIAN_VERSION means realigning them.

ARG DEBIAN_VERSION=12

##############################################################################
# Stage 1 — builder: toolchain, NVENC headers, and the FFmpeg build
##############################################################################
FROM debian:${DEBIAN_VERSION}-slim AS builder

ARG FFMPEG_VERSION=7.1.5

# Must satisfy the `ffnvcodec` pkg-config check in FFmpeg's configure:
#   FFmpeg 5.1.x -> ffnvcodec >= 9.1.23.1   (sdk/11.0 = 11.0.10.4.1)
#   FFmpeg 6.0.x -> ffnvcodec >= 12.0.16.0  (sdk/12.0 = 12.0.16.3.0)
#   FFmpeg 7.1.x -> ffnvcodec >= 12.1.14.0  (sdk/12.1 = 12.1.14.2.0)
# The constraint does not move inside a maintenance branch (verified on 5.1.10, 6.0.1, 7.1.5)
# and stays at 12.1.14.0 up to FFmpeg 9.0.1: moving up a patch does NOT raise the minimum driver.
# A higher branch means a higher minimum NVIDIA driver: do not raise it without a reason.
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

# NVENC/NVDEC headers. The CUDA toolkit is not needed: NVENC only requires ffnvcodec.
RUN git clone --branch "${NVCODEC_BRANCH}" --depth 1 \
      https://github.com/FFmpeg/nv-codec-headers.git /tmp/nv-codec-headers \
 && make -C /tmp/nv-codec-headers install \
 && rm -rf /tmp/nv-codec-headers

WORKDIR /usr/src/ffmpeg
RUN curl -fsSL --retry 3 --retry-connrefused \
      "https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.xz" -o /tmp/ffmpeg.tar.xz \
 && tar -xf /tmp/ffmpeg.tar.xz -C /usr/src/ffmpeg --strip-components=1 \
 && rm /tmp/ffmpeg.tar.xz

# No --enable-nonfree: it would make the binary NON-redistributable, and no nonfree component is
# enabled anyway. No -I/-L pointing at /usr/local/cuda either: the CUDA toolkit is not installed
# and NVENC does not need it.
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

# Build gate: if NVENC did not make it into the binary, the image must not exist.
# Note: no `ffmpeg ... | grep -q` — grep exits on the first match, ffmpeg takes SIGPIPE, and with
# `pipefail` the pipeline fails with 141 even when the test passes.
RUN /usr/local/bin/ffmpeg -hide_banner -encoders > /tmp/encoders.txt \
 && grep -q h264_nvenc /tmp/encoders.txt \
 && grep -q hevc_nvenc /tmp/encoders.txt \
 && rm /tmp/encoders.txt

##############################################################################
# Stage 2 — runtime: only the binaries and the shared libraries they need
##############################################################################
FROM debian:${DEBIAN_VERSION}-slim AS runtime

ARG DEBIAN_FRONTEND=noninteractive
ARG FFMPEG_VERSION=7.1.5
ARG NVCODEC_BRANCH=sdk/12.1

LABEL org.opencontainers.image.title="Docker-FFmpeg-Nvenc" \
      org.opencontainers.image.description="FFmpeg ${FFMPEG_VERSION} with NVIDIA NVENC encoders (h264_nvenc, hevc_nvenc)" \
      org.opencontainers.image.authors="Allan Nava" \
      org.opencontainers.image.source="https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc" \
      org.opencontainers.image.licenses="GPL-3.0-or-later" \
      media.hiway.ffmpeg.version="${FFMPEG_VERSION}" \
      media.hiway.nvcodec.branch="${NVCODEC_BRANCH}"

# `all` would expose capabilities a transcode does not need.
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

# Gate: the binary must work with the runtime stage's libraries alone.
RUN ffmpeg -hide_banner -version \
 && ffmpeg -hide_banner -encoders > /tmp/encoders.txt \
 && grep -q h264_nvenc /tmp/encoders.txt \
 && rm /tmp/encoders.txt

USER ffmpeg
WORKDIR /data

ENTRYPOINT ["ffmpeg"]
CMD ["-version"]
