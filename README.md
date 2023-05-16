# Docker-ffmpeg-nvenc
[![Docker FFmpeg 5.1.2 Nvenc 11.0](https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/actions/workflows/docker-publish.yml)
[![Docker FFmpeg6.0](https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/actions/workflows/docker-publish-ffmpeg6.yml/badge.svg)](https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/actions/workflows/docker-publish-ffmpeg6.yml)

Docker-FFmpeg-Nvenc is a repository that provides a Docker image for FFmpeg with NVIDIA NVENC support. It enables hardware-accelerated video encoding using NVIDIA GPUs and allows you to perform high-performance video transcoding tasks.

## Features

- Docker image with FFmpeg and NVIDIA NVENC integration.
- GPU-accelerated video encoding and transcoding.
- Support for a wide range of input and output video formats.
- Customizable parameters and encoding settings.
- Easy integration with existing Docker-based workflows.

## Prerequisites

To use Docker-FFmpeg-Nvenc, ensure that you have the following:

- A machine with an NVIDIA GPU that supports NVENC.
- Docker installed on the machine.
- NVIDIA Docker runtime installed (for GPU support).

## Usage
To utilize Docker-FFmpeg-Nvenc, follow these steps:

1. Pull the Docker-FFmpeg-Nvenc image from Docker Hub:

```shell
Copy code
docker pull allannava/docker-ffmpeg-nvenc:latest
```

2. Run the Docker container with your desired FFmpeg command. For example:


```shell
Copy code
docker run --gpus all \
  --volume /path/to/input:/data/input \
  --volume /path/to/output:/data/output \
  allannava/docker-ffmpeg-nvenc:latest \
  ffmpeg -i /data/input/input.mp4 -c:v h264_nvenc -preset fast /data/output/output.mp4

```
Customize the input and output paths and the FFmpeg command as per your requirements. This example uses ffmpeg with the h264_nvenc codec to encode an input video (input.mp4) to an output video (output.mp4) using the "fast" preset.

3. Monitor the video encoding process and retrieve the encoded video from the output directory.

For more detailed usage examples and additional information, please refer to the documentation.

## Contributing
Contributions to Docker-FFmpeg-Nvenc are welcome! If you have any suggestions, improvements, or bug fixes, feel free to open an issue or submit a pull request.

## License
This project is licensed under the MIT License.