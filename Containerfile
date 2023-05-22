FROM registry.access.redhat.com/ubi8/ubi:latest
#
MAINTAINER Allan-Nava
#
ENV NVIDIA_VISIBLE_DEVICES all
ENV NVIDIA_DRIVER_CAPABILITIES all
ENV DEBIAN_FRONTEND noninterac1tive
#
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
#
WORKDIR /app
#
## Prepare
RUN apt-get update
RUN apt-get install -y \
    curl diffutils file coreutils m4 xz-utils nasm python3 python3-pip appstream

## Install dependencies
RUN apt-get install -y \
    autoconf automake build-essential cmake git libass-dev libbz2-dev libfontconfig1-dev libfreetype6-dev libfribidi-dev libharfbuzz-dev libjansson-dev liblzma-dev libmp3lame-dev libnuma-dev libogg-dev libopus-dev libsamplerate-dev libspeex-dev libtheora-dev libtool libtool-bin libturbojpeg0-dev libvorbis-dev libx264-dev libxml2-dev libvpx-dev m4 make nasm ninja-build patch pkg-config python tar zlib1g-dev autopoint imagemagick gsfonts wget
    
## Intel CSV dependencies
#RUN apt-get install -y libva-dev libdrm-dev
#   
#
#RUN git clone https://git.videolan.org/git/ffmpeg/nv-codec-headers.git \
	#&& cd nv-codec-headers \
RUN git clone -b sdk/11.0 https://github.com/FFmpeg/nv-codec-headers.git \
	&& cd nv-codec-headers \
	&& make \
	&& make install
#

RUN wget https://ffmpeg.org/releases/ffmpeg-5.1.2.tar.xz \
 && tar -xf ffmpeg-5.1.2.tar.xz \
 && rm ffmpeg-5.1.2.tar.xz
#
# Configure and build ffmpeg with nvenc support
RUN cd ffmpeg-5.1.2 \
 && ./configure --prefix=/usr/local \ 
    --enable-nonfree\
    --enable-nvenc\ 
    --enable-gpl\ 
    --enable-version3\ 
    --enable-static\ 
    --disable-debug\ 
    --disable-ffplay\ 
    --disable-indev=sndio\ 
    --disable-outdev=sndio\ 
    --cc=gcc\ 
    --enable-fontconfig\ 
    --enable-gray\ 
    --enable-libmp3lame\ 
    --enable-libopus\ 
    --enable-libvpx\ 
    --enable-libx264  \
    --extra-cflags=-I/usr/local/cuda/include \
    --extra-ldflags=-L/usr/local/cuda/lib64 \
 && make install \
 && cd ..
#
## Runtime dependencies
RUN apt-get update
RUN apt-get install -y --no-install-recommends \
    # For optical drive listing:
    lsscsi \
    # For watchfolder
    bash \
    coreutils \
    yad \
    findutils \
    expect \
    tcl8.6 \
    wget \
    git
#
## Docker dependencies
RUN apt-get install -y \
    libass9 \
    libavcodec-extra58 \
    libavfilter-extra7 \
    libavformat58 \
    libavutil56 \
    libbluray2 \
    libc6 \
    libcairo2 \
    libdvdnav4 \
    libgdk-pixbuf2.0-0 \
    libglib2.0-0 \
    libgstreamer-plugins-base1.0-0 \
    libgstreamer1.0-0 \
    libgtk-3-0 \
    libgudev-1.0-0 \
    libjansson4 \
    libpango-1.0-0 \
    libsamplerate0 \
    libswresample3 \
    libswscale5 \
    libtheora0 \
    libvorbis0a \
    libvorbisenc2 \
    libxml2 \
    libturbojpeg0 \
    libdvdread4 \
    libx264-155 \
    libx265-165 
#
#
#   
#RUN echo "Compiled ffmpeg nvenc..."
#
######################################################################
#
CMD ["/bin/bash"]