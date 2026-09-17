# Docker-FFmpeg-Nvenc

[![CI](https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/actions/workflows/ci.yml/badge.svg)](https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/actions/workflows/ci.yml)
[![Publish](https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/actions/workflows/docker-publish.yml)

Container image with **FFmpeg built with NVIDIA NVENC support** (`h264_nvenc`, `hevc_nvenc`) for GPU-accelerated transcoding.

Multi-stage build on Debian 12: the final image carries only the binaries and the shared libraries they need — no build toolchain.

## Published images

Registry: **GitHub Container Registry** (`ghcr.io`), not Docker Hub.

```
ghcr.io/allan-nava/docker-ffmpeg-nvenc
```

> ⚠️ **Status on 2026-09-17: the tags below have not been published yet.** The repository's latest tag is
> `v1.0.1` (2023) and `:latest` on GHCR is still the January 2023 image: it runs as **root**, has
> `ENTRYPOINT /bin/bash`, and carries an `NVIDIA_REQUIRE_CUDA` constraint that prevents it from starting on
> hosts with recent drivers. The image described on this page is the one `main` produces, published with the
> first `v2.0.0` tag. Details: [audit 2026-09-17](docs/audit/2026-09-17-state-and-automation-audit.md) —
> tracked as `publish-v2-0-0` in the [backlog](docs/backlog.md).

| Variant | FFmpeg | nv-codec-headers | Minimum NVIDIA driver | Tags |
|---|---|---|---|---|
| default | 7.1.5 | `sdk/12.1` | ≥ 530 | `latest`, `vX.Y.Z`, `latest-ffmpeg7.1.5`, `vX.Y.Z-ffmpeg7.1.5` |
| | 6.0.1 | `sdk/12.0` | ≥ 530 | `latest-ffmpeg6.0.1`, `vX.Y.Z-ffmpeg6.0.1` |
| | 5.1.10 | `sdk/11.0` | ≥ 470 | `latest-ffmpeg5.1.10`, `vX.Y.Z-ffmpeg5.1.10` |

Every variant pins the **latest maintenance release** of its branch. The `sdk/*` branch does not move with
those patches: the `ffnvcodec` constraint in `configure` is identical across a branch, so the host's minimum
driver stays the one in the table.

The `nv-codec-headers` branch is what sets the **minimum NVIDIA driver** on the host: if you get
`This NVENC API is not compatible with the installed driver`, either use a lower variant or update the driver.

## Requirements

- NVIDIA GPU with NVENC ([support matrix](https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new))
- NVIDIA driver (see the table above)
- Docker + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) (for `--gpus`)

## Usage

The image has **`ENTRYPOINT ["ffmpeg"]`**: whatever you pass to `docker run` goes straight to ffmpeg, so you
don't repeat `ffmpeg`.

```shell
docker pull ghcr.io/allan-nava/docker-ffmpeg-nvenc:latest
```

GPU-accelerated transcode:

```shell
docker run --rm --gpus all \
  --user "$(id -u):$(id -g)" \
  -v "$PWD/input:/data/input:ro" \
  -v "$PWD/output:/data/output" \
  ghcr.io/allan-nava/docker-ffmpeg-nvenc:latest \
  -i /data/input/input.mp4 -c:v h264_nvenc -preset p4 /data/output/output.mp4
```

Check that the encoders are there (no GPU needed):

```shell
docker run --rm ghcr.io/allan-nava/docker-ffmpeg-nvenc:latest -hide_banner -encoders | grep nvenc
```

Shell inside the container (for debugging):

```shell
docker run --rm -it --entrypoint /bin/bash ghcr.io/allan-nava/docker-ffmpeg-nvenc:latest
```

### Operational notes

- The container runs as a **non-root** user (uid 1000, `ffmpeg`), working directory `/data`. If the mounted
  volumes belong to another user, pass `--user "$(id -u):$(id -g)"` as in the example above.
- `ffprobe` is included. `ffplay` is not (headless build).
- `NVIDIA_DRIVER_CAPABILITIES` is set to `video,compute,utility` — the minimum needed to transcode.

## Enabled codecs

Encoders: `h264_nvenc`, `hevc_nvenc`, `libx264`, `libx265`, `libvpx-vp8/vp9`, `libmp3lame`, `libopus`,
`libvorbis`, `libtheora`.
Text filters: `fontconfig`, `libfreetype`, `libass`.

The **CUDA toolkit** is not enabled: no `scale_npp`, `libnpp`, or `nvdec`/`cuvid` hardware decode. NVENC only
needs the `ffnvcodec` headers, which is what the image installs. If you need accelerated decode, that takes an
`nvidia/cuda:*-devel` base plus `--enable-cuda-nvcc --enable-nvdec --enable-cuvid --enable-libnpp`.

## GitHub Action

The repository also ships an Action that runs ffmpeg inside the prebuilt image:

```yaml
- uses: Allan-Nava/Docker-FFmpeg-Nvenc@v2      # available from the v2.0.0 tag (see the notice above)
  with:
    command: '-i input.mp4 -c:v libx264 -preset fast output.mp4'
```

⚠️ GitHub-hosted runners have **no GPU**: the `*_nvenc` encoders are unusable inside the Action. You need a
self-hosted runner with a GPU and the NVIDIA Container Toolkit.

## Development

A single parameterised `Dockerfile` produces every variant:

```shell
docker build \
  --build-arg FFMPEG_VERSION=6.0.1 \
  --build-arg NVCODEC_BRANCH=sdk/12.0 \
  -t ffmpeg-nvenc:6.0.1 .

./tests/smoke.sh ffmpeg-nvenc:6.0.1 6.0.1   # no GPU required
./tests/gpu.sh   ffmpeg-nvenc:6.0.1         # requires an NVIDIA GPU
```

CI (`.github/workflows/ci.yml`) runs the linters (hadolint, shellcheck, actionlint), builds and tests all three
variants on every push/PR, and runs **weekly** to catch base images rotting away. Publishing
(`docker-publish.yml`) only fires on `v*` tag pushes and goes through the same smoke tests before pushing.

The Python tooling and the page generator are covered by tests — stdlib `unittest`, no dependencies:

```shell
python3 -m unittest discover -s tests -p 'test_*.py'
```

See [CLAUDE.md](CLAUDE.md) / [AGENTS.md](AGENTS.md) for working conventions and known traps, and
[docs/audit/](docs/audit/) for the project audits.

### Backlog and roadmap

The repository's todos live in [`docs/backlog.md`](docs/backlog.md), which is the **single source of truth**: an
idempotent script opens, updates and closes one GitHub issue per item (label `backlog-sync`) and creates the
missing milestones, scheduled by [`.github/workflows/backlog.yml`](.github/workflows/backlog.yml).
[`docs/roadmap.md`](docs/roadmap.md) is the per-milestone view, **generated** from the backlog.

```shell
python3 docs/scripts/backlog-lint.py             # validate the backlog (CI gate)
python3 docs/scripts/generate-roadmap.py         # regenerate docs/roadmap.md (commit it)
python3 docs/scripts/sync-backlog-to-issues.py   # dry-run of the issue sync
```

Item conventions and GitHub API traps: [`docs/scripts/README.md`](docs/scripts/README.md).

### Project page

[allan-nava.github.io/Docker-FFmpeg-Nvenc](https://allan-nava.github.io/Docker-FFmpeg-Nvenc/) is generated from
this README plus the files that actually decide things — the publish matrix, the `Dockerfile`, `tests/smoke.sh`:

```shell
python3 site/build.py            # writes site/dist/
python3 site/build.py --check    # CI gate: fails if site/dist is stale
```

## Contributing

Issues and pull requests welcome. Every PR has to pass CI: build plus smoke tests of all variants.

Issues labelled `backlog-sync` are **generated** from [`docs/backlog.md`](docs/backlog.md): to change a title or
a description, edit the backlog, not the issue (the next sync would realign it anyway).

## Licence

The files in this repository are **MIT** (see [LICENSE](LICENSE)).

The **image it produces** is a different matter: FFmpeg is built with `--enable-gpl --enable-version3` and linked
against libx264/libx265, so the binary is distributed under **GPL-3.0-or-later**. The build does not use
`--enable-nonfree`, so the image is redistributable.
