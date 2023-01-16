FROM nvidia/cuda:11.5.0-base-ubuntu20.04
#
#RUN apt update && apt install -y software-properties-common
#RUN add-apt-repository ppa:savoury1/ffmpeg5
#
ARG DEBIAN_FRONTEND=noninteractive
ENV TZ=Europe/Rome
#
WORKDIR /workspace
COPY . . 
RUN apt-get update && apt-get install -y --no-install-recommends apt-utils
RUN apt-get install -y git-all
#
RUN ./ffmpeg-compile.sh
#
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility,video
#