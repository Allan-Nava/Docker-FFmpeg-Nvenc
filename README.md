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

> ⚠️ **Status on 2026-09-17: released, not yet published.** `v2.0.0` and `v2.1.0` are tagged and the
> GitHub Releases exist, but **no image has been pushed to GHCR yet** — releasing and publishing are
> separate acts here, and publishing happens when the `Publish` workflow runs. Until then `:latest` on
> the registry is still the January 2023 build: it runs as **root**, has `ENTRYPOINT /bin/bash`, and
> carries an `NVIDIA_REQUIRE_CUDA` constraint that prevents it from starting on hosts with recent
> drivers. The tags below describe what `main` produces. Details:
> [audit 2026-09-17](docs/audit/2026-09-17-state-and-automation-audit.md) — tracked as `publish-v2-0-0`
> in the [backlog](docs/backlog.md).

| Variant | FFmpeg | nv-codec-headers | Minimum NVIDIA driver | Tags |
|---|---|---|---|---|
| default | 9.0.1 | `sdk/12.1` | ≥ 530 | `latest`, `X.Y.Z`, `X.Y`, `X` + `latest-ffmpeg9`, `latest-ffmpeg9.0`, `latest-ffmpeg9.0.1`, `X.Y.Z-ffmpeg9.0.1` |
| | 7.1.5 | `sdk/12.1` | ≥ 530 | `latest-ffmpeg7`, `latest-ffmpeg7.1`, `latest-ffmpeg7.1.5`, `X.Y.Z-ffmpeg7.1.5` |
| | 6.1.6 | `sdk/12.1` | ≥ 530 | `latest-ffmpeg6`, `latest-ffmpeg6.1`, `latest-ffmpeg6.1.6`, `X.Y.Z-ffmpeg6.1.6` |
| | 5.1.10 | `sdk/11.0` | ≥ 470 | `latest-ffmpeg5`, `latest-ffmpeg5.1`, `latest-ffmpeg5.1.10`, `X.Y.Z-ffmpeg5.1.10` |

`X.Y.Z` is the **repository** release, not the FFmpeg version. Pick a tag by how much movement you want:

| You want | Pull |
|---|---|
| whatever is current | `:latest` (today FFmpeg 9.0.1 — it follows the default variant) |
| the newest 7.x, forever | `:latest-ffmpeg7` |
| the newest 7.1.x | `:latest-ffmpeg7.1` |
| nothing to ever move | `:2.1.0-ffmpeg7.1.5`, or better, the digest |

⚠️ `:latest` follows the **default variant**, which is now FFmpeg 9.0.1 (it was 7.1.x). If you pinned
`:latest` and want to stay on 7.x, move to `:latest-ffmpeg7`.

Every variant pins the **latest maintenance release** of its branch, on the **lowest** `sdk/*` branch its
`configure` accepts. Measured across every maintained FFmpeg branch: the `ffnvcodec` requirement is frozen at
12.1.14.0 from 6.1 all the way to 9.0, so **a newer FFmpeg does not ask more of your driver** — 9.0.1 and
7.1.5 have exactly the same floor. Only 5.1 sits lower (≥ 470), which is why it is still here.

`sdk/12.2` and `sdk/13.0` exist upstream and are deliberately unused: they would only raise the minimum
driver without any variant needing them.

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
- uses: Allan-Nava/Docker-FFmpeg-Nvenc@v2.1.0
  with:
    command: '-i input.mp4 -c:v libx264 -preset fast output.mp4'
```

Pin the action to an exact tag as above: there is no moving `v2` tag, and `runs.image` inside the action is
static by GitHub's specification, so the image it runs cannot be chosen by an input.

⚠️ Until the images are published (see the notice at the top), the action pulls `:latest` from GHCR, which is
still the January 2023 build — it will not do what this page describes.

⚠️ GitHub-hosted runners have **no GPU**: the `*_nvenc` encoders are unusable inside the Action. You need a
self-hosted runner with a GPU and the NVIDIA Container Toolkit.

## Development

A single parameterised `Dockerfile` produces every variant:

```shell
docker build \
  --build-arg FFMPEG_VERSION=6.1.6 \
  --build-arg NVCODEC_BRANCH=sdk/12.1 \
  -t ffmpeg-nvenc:6.1.6 .

./tests/smoke.sh ffmpeg-nvenc:6.1.6 6.1.6   # no GPU required
./tests/gpu.sh   ffmpeg-nvenc:6.1.6         # requires an NVIDIA GPU
```

Two helper scripts do the whole round instead:

```shell
./tests/run-all.sh        # every gate that needs no docker: tests, backlog, generated pages, linters
./tests/build-matrix.sh   # builds and smoke-tests every variant of the publish matrix
./tests/build-matrix.sh 9.0.1   # ...or just one
```

`build-matrix.sh` reads the matrix from the publish workflow (`site/build.py --print-variants`), so it can
never test a different set of variants from the one CI publishes.

CI (`.github/workflows/ci.yml`) runs the linters (hadolint, shellcheck, actionlint), builds and tests all three
variants on every push/PR, and runs **weekly** to catch base images rotting away. Publishing
(`docker-publish.yml`) only fires on `v*` tag pushes and goes through the same smoke tests before pushing.

The Python tooling and the page generator are covered by tests — stdlib `unittest`, no dependencies:

```shell
python3 -m unittest discover -s tests -p 'test_*.py'
```

### Committing

Commit subjects are conventional commits, because the release version is derived from them. One command
validates the subject, files the CHANGELOG entry and runs the gates:

```shell
./docs/scripts/install-hooks.sh                      # once: enables the commit-msg hook
./docs/scripts/commit.sh "fix: the tagging regex never matched"   --entry "the semver regex ran against a string the suffix made unmatchable, so :latest was never published"
```

`--entry` is the sentence that ends up in the release notes; without it the commit description is used.
`python3 docs/scripts/changelog-add.py --message "<subject>"` does the CHANGELOG part on its own. On a pull
request, CI checks both the subjects and that `## [Unreleased]` is not empty when code changed.

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
