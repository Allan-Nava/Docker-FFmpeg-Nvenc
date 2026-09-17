# Bumping all three variants to the latest maintenance release — 2026-09-17

Change to the `Dockerfile` and to the workflow matrix: every variant moves to the **latest patch of its
branch**. Closes the backlog item `ffmpeg-patch-bump`, opened by the
[audit of 2026-09-17](../audit/2026-09-17-state-and-automation-audit.md).

```
                         before             after       branch   ffnvcodec required   host driver
  default (latest)   ┌── 7.1.1      ──▶   7.1.5    ── sdk/12.1 ── >= 12.1.14.0 ──────── >= 530
                     ├── 6.0        ──▶   6.0.1    ── sdk/12.0 ── >= 12.0.16.0 ──────── >= 530
                     └── 5.1.2      ──▶   5.1.10   ── sdk/11.0 ── >=  9.1.23.1 ──────── >= 470
                                                        ▲                                  ▲
                                         DOES NOT ──────┘         unchanged ───────────────┘
                                          change
```

## Why the `sdk/*` branch does not move

FFmpeg's `configure` sets the minimum `ffnvcodec` version, and that constraint **does not change inside a
maintenance branch**. Read straight from the sources of the releases involved:

```
  n5.1.2  -> ffnvcodec >= 9.1.23.1      n5.1.10 -> ffnvcodec >= 9.1.23.1
  n6.0    -> ffnvcodec >= 12.0.16.0     n6.0.1  -> ffnvcodec >= 12.0.16.0
  n7.1.1  -> ffnvcodec >= 12.1.14.0     n7.1.5  -> ffnvcodec >= 12.1.14.0
```

So `NVCODEC_BRANCH` stays `sdk/11.0` / `sdk/12.0` / `sdk/12.1` and **the host's minimum NVIDIA driver does
not rise**: no consumer has to update drivers to take these patches. That is what makes this the
lowest-risk change on the findings list — and why it should be done often rather than left to accumulate
five maintenance releases of lag.

A note from the same check: the constraint stays at `12.1.14.0` all the way to **FFmpeg 9.0.1**. Moving up
a major branch costs no driver (item `ffmpeg-8-and-9-variants`); it costs CI time and a review of the
`--enable-*` options, which is a different decision.

## Verification

**Native `linux/arm64`** builds on macOS (the development host is Apple Silicon and the local builder only
exposes `linux/arm64`; the published images are `linux/amd64` and CI builds those). Raw logs in
[`logs/2026-09-17-bump-ffmpeg/`](../../logs/2026-09-17-bump-ffmpeg/).

| Variant | build | smoke test | size | banner |
|---|---|---|---|---|
| 7.1.5 (`sdk/12.1`) | OK (~2 min) | **17 ok, 0 fail** | 203 MB | `ffmpeg version 7.1.5` |
| 6.0.1 (`sdk/12.0`) | OK (~2 min) | **17 ok, 0 fail** | 201 MB | `ffmpeg version 6.0.1` |
| 5.1.10 (`sdk/11.0`) | OK (~2 min) | **17 ok, 0 fail** | 200 MB | `ffmpeg version 5.1.10` |

```shell
docker build --build-arg FFMPEG_VERSION=7.1.5 --build-arg NVCODEC_BRANCH=sdk/12.1 -t ffmpeg-nvenc:test-7.1.5 .
./tests/smoke.sh ffmpeg-nvenc:test-7.1.5 7.1.5
```

Each build also passed the **gates inside the Dockerfile** (the `h264_nvenc`/`hevc_nvenc` encoders must
appear in `ffmpeg -encoders` in the builder stage, and the binary must work with the runtime stage's
libraries alone), otherwise the image would not exist. `hadolint` on the modified Dockerfile: nothing
beyond the pre-existing informational `DL3066` on `USER ffmpeg`. `actionlint` on the workflows: nothing.

⚠️ **Not verified here**: real NVENC encoding (`tests/gpu.sh`) and the `linux/amd64` build. The first needs
an NVIDIA host, the second is what CI does on `ubuntu-latest`. Both remain mandatory gates before promoting
a tag (item `gpu-gate-before-tag`).

## Files touched

- `Dockerfile` — `ARG FFMPEG_VERSION` in both stages to `7.1.5`; the `ffnvcodec` comment updated with the
  patch-release verification.
- `.github/workflows/ci.yml`, `.github/workflows/docker-publish.yml` — matrix and cache scope.
- `README.md`, `CLAUDE.md`, `AGENTS.md` — variant table and build examples.
- `docs/backlog.md` — `ffmpeg-patch-bump` set to `status: done`; `docs/roadmap.md` regenerated.
