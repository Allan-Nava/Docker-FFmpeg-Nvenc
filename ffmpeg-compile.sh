#!/bin/bash
# Automatically compile and install FFMPEG with NVIDIA hardware acceleration on Debian 11
# Includes cuvid, cuda, nvenc, nvdec, and non-free libnpp
# Based on:
#  https://www.tal.org/tutorials/ffmpeg_nvidia_encode
#  https://developer.nvidia.com/blog/nvidia-ffmpeg-transcoding-guide/
#
# Abort on error
set -e
#
#apt-get update && apt-get install -y --no-install-recommends apt-utils
#apt-get install -y git-all
#apt-get install git
#
git clone https://git.videolan.org/git/ffmpeg/nv-codec-headers.git

cd nv-codec-headers &&  make install && cd -

git clone https://git.ffmpeg.org/ffmpeg.git ffmpeg/
#
apt-get install -y build-essential yasm cmake libtool libc6 libc6-dev unzip wget libnuma1 libnuma-dev 
#
pwd 
ls -l
#
./configure --enable-nonfree --enable-cuda-nvcc --enable-libnpp --extra-cflags=-I/usr/local/cuda/include --extra-ldflags=-L/usr/local/cuda/lib64 --disable-static --enable-shared
#
make -j 8
#
make install