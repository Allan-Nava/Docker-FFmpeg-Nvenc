# Initial audit — Docker-FFmpeg-Nvenc (2026-08-09)

Static audit of the `github.com/Allan-Nava/Docker-FFmpeg-Nvenc` repository at commit `b536c4d` (branch `main`, clean working tree).

> **Status: resolved in v2.0.0 (2026-08-09).** This document is the snapshot of the repository **before** that work and should be read in the past tense: the files it mentions (`Containerfile`, `Dockerfile-ffmpeg6`, `module.defs`, `scripts/`, `docker-publish-ffmpeg6.yml`) no longer exist. What was done for each point: `CHANGELOG.md`, section `[2.0.0]`. Post-fix verification: all three variants (FFmpeg 5.1.2 / 6.0 / 7.1.1) build and pass 17/17 assertions of `tests/smoke.sh`.
>
> **Caveat added on 2026-09-17**: that release was never tagged, so nothing of it was ever published. See [the follow-up audit](2026-09-17-state-and-automation-audit.md).

**Summary: neither of the images this repository publishes can still be built.** The main `Dockerfile` dies on `apt-get update` (Debian buster out of the archive), `Dockerfile-ffmpeg6` dies installing its dependencies (the `python` package does not exist in bullseye). The `Containerfile` is broken by construction. Detail and priorities below.

> Checks marked **[verified]** were run against the real upstream repositories on 2026-08-09. No `docker build` was run in this audit: the breakages are deduced from verified facts about the package repositories, not from a build run.

## 1. Repository layout and publication flow

```
                          push tag v*  ──────────────────────────────┐
                                                                     │
  ┌──────────────────────────────────────────────────────────────┐   │
  │ .github/workflows/docker-publish.yml                         │◄──┤
  │   checkout@v3 → github-script@v4 → prep (::set-output)        │   │
  │   → buildx → login ghcr → build-push-action@v4               │   │
  │        file: ./Dockerfile        platform: linux/amd64       │   │
  └───────────────────────────┬──────────────────────────────────┘   │
                              │ push                                 │
                              ▼                                      │
        ghcr.io/allan-nava/docker-ffmpeg-nvenc:<tag>-ffmpeg5.1.2      │
                                                                     │
  ┌──────────────────────────────────────────────────────────────┐   │
  │ .github/workflows/docker-publish-ffmpeg6.yml                 │◄──┘
  │   (same flow)      file: ./Dockerfile-ffmpeg6                │
  └───────────────────────────┬──────────────────────────────────┘
                              │ push
                              ▼
        ghcr.io/allan-nava/docker-ffmpeg-nvenc:<tag>-ffmpeg6.0

  Connected to no flow at all:
    Containerfile   (UBI8 + apt-get → impossible build)
    module.defs     (HandBrake-contribs fragment)
    scripts/*.sh    (out-of-Docker build, never invoked)
    action.yml      (public Action; rebuilds the Dockerfile on every use)
```

Anatomy of an image (identical in the two theoretically-working Dockerfiles):

```
  debian:10.10-slim / debian:11-slim
    │
    ├─ RUN apt-get update                       ← separate layer (stale cache)
    ├─ RUN apt-get install <build tools>        ← ~40 packages, incl. build-essential
    ├─ RUN git clone nv-codec-headers → make install
    ├─ RUN wget ffmpeg-<ver>.tar.xz → tar -xf   ← sources left in /app
    ├─ RUN ./configure ... && make install      ← single layer, ~1 GB of objects
    ├─ RUN apt-get update
    ├─ RUN apt-get install <runtime + yad, expect, tcl, git, wget>
    └─ RUN apt-get install <libav*, libgtk-3, libgstreamer, ...>   ← distro ffmpeg
       CMD ["/bin/bash"]

  ⚠ No multi-stage: build toolchain, sources and objects all stay in the final image.
```

## 2. Blockers (the artefact cannot be produced)

### B1 — `Dockerfile`: the Debian 10 base is out of the archive → `apt-get update` fails **[verified]**

`Dockerfile:2` uses `debian:10.10-slim`. Buster is EOL and its indexes moved to `archive.debian.org`:

| URL | HTTP |
|---|---|
| `http://deb.debian.org/debian/dists/buster/Release` | **404** |
| `http://security.debian.org/debian-security/dists/buster/updates/Release` | **404** |
| `http://archive.debian.org/debian/dists/buster/Release` | 200 |
| `http://deb.debian.org/debian/dists/bullseye/Release` | 200 |

`apt-get update` at `Dockerfile:16` fails to fetch the indexes → non-zero exit → build aborted. **This is the image the README badge presents as the main one.**

Possible fixes, in order of preference:
1. bump the base to `debian:12-slim` (bookworm) or `debian:13-slim`, adjusting the versioned package names (`libx264-*`, `libx265-*`, `libavcodec-extra*`);
2. an `nvidia/cuda:<ver>-devel-ubuntu22.04` base if the CUDA toolkit is ever genuinely needed (`--enable-cuda-nvcc`, `--enable-libnpp`);
3. (stopgap) rewrite `sources.list` to `archive.debian.org` plus `Acquire::Check-Valid-Until "false"` — not advisable: no security patches.

### B2 — `Dockerfile-ffmpeg6`: the `python` package does not exist in Debian 11 → install fails **[verified]**

`Dockerfile-ffmpeg6:23` includes `python` in the dependency list. The `python` metapackage was removed in bullseye:

```
madison?package=python&s=bullseye   → (empty, the package does not exist)
madison?package=python2&s=bullseye  → python2 | 2.7.18-3 | oldoldstable | amd64, arm64, ...
```

`apt-get install -y ... python ...` → `E: Unable to locate package python` → build aborted. Replace it with `python3` (already on the previous line, so it can probably just be dropped).

### B3 — `Containerfile`: package manager incompatible with the base

`Containerfile:1` starts from `registry.access.redhat.com/ubi8/ubi:latest` and then, at lines 15-21 and 64-107, uses `apt-get` with Debian package names (`build-essential`, `libass-dev`, `libx264-155`, …). On UBI8 the package manager is `dnf`/`microdnf` and `apt-get` does not exist → it fails on the first `RUN`. The file is to all intents a copy-paste of the `Dockerfile` with only the `FROM` changed (commit `1f14723 added containerfile`, then `0c0aec1 removed podman`).

No workflow references it: **either port it to `dnf` + EPEL/RPMFusion (not trivial: many `-dev` packages have no direct equivalent), or delete it.** Keeping it as is, is pure debt and misleads whoever reads it.

## 3. Functional defects (the artefact builds, but does not do what is documented)

### F1 — The `:latest` tag is never published

In both workflows (`docker-publish.yml:28-46`, `docker-publish-ffmpeg6.yml:37-55`) `VERSION` is always built with the FFmpeg suffix appended:

```
VERSION=${GITHUB_REF#refs/tags/}-ffmpeg5.1.2      # e.g. "v1.0.1-ffmpeg5.1.2"
...
if [[ $VERSION =~ ^v[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then    # NEVER matches
  TAGS="$TAGS,...:${MINOR},...:${MAJOR},...:latest"
fi
```

The suffix makes the semver regex structurally unsatisfiable: the branch that adds `:latest`, `:MAJOR` and `:MINOR` is **dead code**. Practical consequence: anyone following the README and pulling `...:latest` finds nothing.

Fix: apply the regex to `${GITHUB_REF#refs/tags/}` before appending the suffix, and use distinct per-variant tags (`latest-ffmpeg5.1.2`, `latest-ffmpeg6.0`) plus, optionally, a `latest` pointing at the reference variant.

### F2 — README pointing at the wrong registry

`README.md:30` and `README.md:41` instruct `docker pull allannava/docker-ffmpeg-nvenc:latest` and use that reference in the `docker run` example. CI publishes to `ghcr.io/allan-nava/docker-ffmpeg-nvenc` instead. No workflow in this repository logs in or pushes to Docker Hub. Combined with F1, the documented install instruction **works on neither registry**.

To fix together with F1, pointing at the real tag (e.g. `ghcr.io/allan-nava/docker-ffmpeg-nvenc:v1.0.1-ffmpeg6.0`).

### F3 — `action.yml`: the GitHub Action cannot work

```yaml
runs:
  using: 'docker'
  image: 'Dockerfile'
  args:
    - ${{ inputs.command }}
```

Two independent problems:
- `image: 'Dockerfile'` rebuilds FFmpeg from source **on every invocation** of the Action (tens of minutes per job, for every user of it). It should be `image: 'docker://ghcr.io/allan-nava/docker-ffmpeg-nvenc:<tag>'`.
- The image defines no `ENTRYPOINT`, only `CMD ["/bin/bash"]`. The `args` of a docker Action **replace the CMD**: the string `-i` (or the whole command line the user passed) is interpreted as the **executable**, not as arguments to `ffmpeg`. It needs `ENTRYPOINT ["ffmpeg"]` in the image (or `entrypoint:` in the action) and the arguments split properly.

On top of that, the `token` input is declared and used by nothing.

### F4 — The README badges do not reflect the triggers

`README.md:2` uses `docker-publish.yml/badge.svg?branch=main`, but that workflow runs **only on tag pushes**, never on `main`. The badge therefore reports a status unrelated to the branch it names.

### F5 — CUDA `--extra-cflags`/`--extra-ldflags` pointing at non-existent paths

`Dockerfile:59-60`, `Dockerfile-ffmpeg6:57-58`, `Containerfile:58-59` pass `-I/usr/local/cuda/include` and `-L/usr/local/cuda/lib64`. **No CUDA toolkit is installed** in the image: those directories do not exist. NVENC through `--enable-nvenc` only needs `nv-codec-headers` (pkg-config `ffnvcodec`), which is installed — so the build does not break, but the flags are misleading and suggest a capability (CUDA/NPP/scale_npp) the image **does not have**. Remove them, or actually install CUDA and enable `--enable-cuda-nvcc --enable-libnpp --enable-nvdec --enable-cuvid` (as `scripts/build-ffmpeg.sh` does — except it is dead, see D3).

### F6 — No functional verification in the pipeline

The workflows build and push without any test. An image where NVENC was not compiled in (because `configure` silently disabled the encoder, say) would be published anyway. The minimum gate is missing:

```
docker run --rm $IMAGE ffmpeg -hide_banner -encoders | grep -q h264_nvenc
```

which needs no GPU (the encoder only has to be compiled in) and would have caught B1/B2 on the first tag.

## 4. Image quality

### Q1 — No multi-stage: enormous image

The final images contain `build-essential`, `cmake`, `ninja-build`, `git`, `imagemagick`, the FFmpeg sources unpacked in `/app` (never removed; `Dockerfile:36-38` only `rm`s the tarball) and every `make` object. On top of that: `yad`, `expect`, `tcl8.6`, `libgtk-3-0`, `libgstreamer*`, `libcairo2`, `libgdk-pixbuf` — **a GUI and GStreamer inside a headless transcoding image**, presumably inherited from a HandBrake Dockerfile (consistent with the presence of `module.defs`).

Estimated at several GB against the few hundred MB achievable with:

```
FROM debian:12-slim AS builder     → toolchain + build
FROM debian:12-slim                → COPY --from=builder /usr/local /usr/local + runtime libs only
```

### Q2 — `apt-get update` detached from `apt-get install`

`Dockerfile:16-22`, `:65-77`, `:80-108` (and their counterparts in the other two files): `update` and `install` in separate `RUN`s. If the `update` layer stays cached while the `install` layer is invalidated, apt works against stale indexes → non-deterministic "Package not found"/404 failures. The standard rule: a single `RUN apt-get update && apt-get install -y --no-install-recommends ... && rm -rf /var/lib/apt/lists/*`.

Side note: the apt lists are never cleaned → ~40-50 MB of dead weight for each of the three blocks.

### Q3 — Installing the distro libav\* on top of a custom build

`Dockerfile:81-108` installs `libavcodec-extra58`, `libavfilter-extra7`, `libavformat58`, `libavutil56`, `libswresample3`, `libswscale5`. The image has just compiled and installed FFmpeg into `/usr/local` with `--enable-static`. Those distro libraries are **Debian's** FFmpeg (4.1 on buster), unused by the binary just built: weight and attack surface with no benefit, and confusing for anyone running `ffmpeg -version` inside the container expecting consistency.

### Q4 — `ENV DEBIAN_FRONTEND noninterac1tive` (typo, in all three files)

`Dockerfile:8`, `Dockerfile-ffmpeg6:8`, `Containerfile:7`. The value `noninterac1tive` is not recognised by debconf, so the interactive frontend stays active: prompts and `debconf: unable to initialize frontend: Dialog` warnings during installs. It does not block the build, but it is exactly the kind of mistake that propagates by copy-paste — as it already has, into three files.

### Q5 — Fragile line continuations in the `./configure` block

`Dockerfile:42-58` (and counterparts): almost every line ends with `\` **followed by a space**. BuildKit tolerates it (regex `\\[ \t]*$`) but emits a deprecation warning; it is a setup that breaks with the first editor that normalises whitespace differently. Rewrite it cleanly whenever the block is touched.

### Q6 — Reproducibility: `nv-codec-headers` unpinned in `Dockerfile-ffmpeg6`

`Dockerfile:30` correctly pins `-b sdk/11.0` (and from `github.com/FFmpeg/nv-codec-headers`). `Dockerfile-ffmpeg6:29` instead clones `master` from `git.videolan.org` with no branch and no `--depth 1`: the build is not reproducible and can end up with headers requiring a newer NVIDIA driver than the target hosts have (typical runtime error: *"This NVENC API is not compatible with the installed driver"*). Pin it to an `sdk/<ver>` compatible with the driver estate.

### Q7 — Container hygiene

- `MAINTAINER` (deprecated since Docker 1.13) in all three files → `LABEL org.opencontainers.image.authors=`.
- No non-root `USER`: the container runs as root.
- `ENV NVIDIA_DRIVER_CAPABILITIES all` is broader than needed; transcoding only needs `video,compute,utility`.
- Base image not pinned by digest (`debian:11-slim` is a moving tag).
- No `HEALTHCHECK`, no OCI labels in the Dockerfile itself (only the ones the workflow injects).

## 5. Dead code and drift

### D1 — `module.defs` does not belong to this repository

A 212-line file in **HandBrake contrib** style (`import.MODULE.defs`, `FFMPEG.CONFIGURE.extra`, `FEATURE.qsv`/`vce`/`nvenc`, fetching from `HandBrake/HandBrake-contribs`). No `Makefile`, script or Dockerfile includes it: nothing evaluates it. It also carries a latent bug (lines 77-78: `--enable-filter=null \ ` with a space after the backslash, which would break the continuation in make). Remove it, or isolate it under `reference/` with a README explaining where it came from.

### D2 — `.github/dependabot.yml` points at a directory that does not exist

Lines 11-14 register a `docker` ecosystem on `/tests`. The `tests/` directory does not exist in the repository → that update is inert (and Dependabot reports a configuration error in the UI). Remove it, or create the corresponding tests (which are needed anyway, see F6).

### D3 — `scripts/` is a parallel build path: dead and non-functional

`scripts/base.sh`, `build-tools.sh`, `build-library.sh`, `build-ffmpeg.sh` implement a from-source FFmpeg build outside Docker (cross-compiling Linux/Windows/macOS). No Dockerfile, workflow or `action.yml` invokes them; the only cross-reference is `source ./base.sh` between themselves.

Besides being dead, they have defects of their own:
- `build-ffmpeg.sh:10` and `:16` read `${PREFIX}/ffmpeg_configure_options` and `${PREFIX}/ffmpeg_extra_libs`. **No script generates those files**: `base.sh:59-60` declares the `FFMPEG_CONFIGURE_OPTIONS`/`FFMPEG_EXTRA_LIBS` arrays and the various `build-*.sh` populate them in memory, but never write them to disk. With `set -eu` inherited from `base.sh`, `cat` on a missing file ends the script.
- `source ./base.sh` with a relative path: the scripts only work when the cwd is `scripts/`.
- `build-tools.sh` is a degraded copy of `build-library.sh` in which the `case "$(uname)"` was removed, leaving the two `cp -r ./bin/.` lines indented for nothing (Linux-only, without saying so).
- `build-ffmpeg.sh` hardcodes `/usr/local/cuda-11.5`.

Decision to take: **delete them** (the real path is Docker) or repair them and make them the single source of truth for the FFmpeg configuration, invoked from the Dockerfiles. The current state — two diverging FFmpeg configurations, one in the Dockerfiles and one in `scripts/`, with different feature sets — is the worst of the three options.

### D4 — Drift between the three build files

| | `Dockerfile` | `Dockerfile-ffmpeg6` | `Containerfile` |
|---|---|---|---|
| base | debian:10.10-slim | debian:11-slim | ubi8 (with apt!) |
| FFmpeg | 5.1.2 | 6.0 | 5.1.2 |
| nv-codec-headers | `sdk/11.0` pinned | `master` | `sdk/11.0` pinned |
| `libdvdread` | `libdvdread4` | `libdvdread8` | `libdvdread4` |
| `libx264`/`libx265` | 155 / 165 | 160 / 192 | 155 / 165 |
| `echo "Compiled..."` | commented out | active | commented out |

Three manual copies of the same logic, diverging on arbitrary details. With one parameterised Dockerfile (`ARG FFMPEG_VERSION`, `ARG NVCODEC_BRANCH`, `ARG DEBIAN_VERSION`) and a `strategy.matrix` in the workflows, the two near-identical workflows (3258 and 3103 bytes; the substantive difference being the file name and the tag suffix) would become one.

## 6. Licence and redistribution

- **The `LICENSE` file is missing** although `README.md:55` declares MIT. With no licence file, GitHub does not detect the licence and the `license.spdx_id` field used in the workflows' OCI labels (`docker-publish.yml:85-86`) is `null` → the label is emitted empty.
- More importantly: the build uses **`--enable-gpl --enable-nonfree --enable-version3`** (`Dockerfile:43-46`). An FFmpeg binary built with `--enable-nonfree` is **not legally redistributable**, and the images are published to a public registry. In the current configuration `--enable-nonfree` does not even appear necessary: neither `libfdk-aac` nor any other nonfree component is enabled — the libraries in use (`libx264`, `libvpx`, `libmp3lame`, `libopus`) are GPL-covered. **Removing `--enable-nonfree` makes the image redistributable under GPLv3**, and it is most likely cargo-culted from NVENC guides.
- It should also be stated that the image is GPL, not MIT: MIT covers the Dockerfile, not the artefact.

## 7. Supply chain / CI

- `actions/github-script@v4`, `actions/checkout@v3`, `docker/login-action@v2`, `docker/setup-buildx-action@v2`, `docker/build-push-action@v4`: all 2-3 majors behind. `github-script@v4` uses the old `github.repos.get` API — moving to v5+ means rewriting it as `github.rest.repos.get`, so the update is not mechanical.
- `::set-output` (`docker-publish.yml:47-49` and counterparts) is deprecated → `echo "name=value" >> $GITHUB_OUTPUT`.
- Actions not pinned to SHAs (moving tags only): the recommended hardening standard for workflows that publish artefacts.
- No vulnerability scanning (Trivy/Grype), no SBOM, no provenance/attestation, no signature (cosign) — all natively available in `build-push-action` v5+ (`provenance: true`, `sbom: true`).
- `permissions` correctly minimised (`contents: read`, `packages: write`) — this part is fine.
- The two builds are separate jobs in separate workflows: no shared cache, no GHA `cache-from`/`cache-to` → every tag compiles FFmpeg twice from scratch.

## 8. Suggested priority

| # | Work | Why first |
|---|---|---|
| 1 | Bump the base image + drop `python` (B1, B2) | without this there is no artefact at all |
| 2 | Smoke test `ffmpeg -encoders \| grep nvenc` in CI (F6) | it is the gate that would have prevented 1 |
| 3 | Fix `:latest` tagging + correct README/registry (F1, F2) | the documented install instruction does not work |
| 4 | Remove `--enable-nonfree` + add `LICENSE` (§6) | publishing non-redistributable binaries |
| 5 | Unify into a parameterised Dockerfile + matrix (D4) | otherwise every later fix has to be made 2-3 times |
| 6 | Multi-stage + `apt` in a single `RUN` + clean sources (Q1, Q2, Q3) | image size and attack surface |
| 7 | Decide on `Containerfile`, `scripts/`, `module.defs`, `/tests` (B3, D1, D2, D3) | removing debt and misleading documentation |
| 8 | Update the actions, `$GITHUB_OUTPUT`, SBOM/provenance/scan (§7) | hardening |
| 9 | Rewrite `action.yml` on the prebuilt image + `ENTRYPOINT` (F3) | the published Action is unusable |

## Logs and checks

Checks run on 2026-08-09 (`logs/` not populated: the audit is static, and the only network commands are these):

```
curl -o /dev/null -w "%{http_code}" http://deb.debian.org/debian/dists/buster/Release                       → 404
curl -o /dev/null -w "%{http_code}" http://security.debian.org/debian-security/dists/buster/updates/Release → 404
curl -o /dev/null -w "%{http_code}" http://deb.debian.org/debian/dists/bullseye/Release                     → 200
curl -o /dev/null -w "%{http_code}" http://archive.debian.org/debian/dists/buster/Release                   → 200
curl "https://api.ftp-master.debian.org/madison?package=python&s=bullseye"                                  → (empty)
curl "https://api.ftp-master.debian.org/madison?package=python2&s=bullseye"                                 → python2 | 2.7.18-3 | oldoldstable
```

Not done in this audit: `docker build` of the three variants (which would confirm B1/B2 empirically and measure the real size for Q1), and an inspection of the tags actually present on GHCR (which would confirm F1 from the registry side).
