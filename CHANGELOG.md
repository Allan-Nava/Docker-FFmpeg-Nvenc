# Changelog

All notable changes to this project are documented here.
Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/).

## [Unreleased]

### Fixed

- `test_the_real_changelog_has_unreleased_entries` asserted that `## [Unreleased]` had entries — true while writing them, false the moment `release.yml` folded them into `[2.0.0]`. It turned CI, Pages and the next Release red on the push right after v2.0.0 shipped. Replaced with structural checks (the file parses, a released version exists, `[Unreleased]` sits above it when present, an entry can always be filed), and the page test that looked for one README sentence now checks that no README notice is dropped.

## [2.0.0] - 2026-09-17

### Added

- **State-of-the-repository audit**: `docs/audit/2026-09-17-state-and-automation-audit.md`, with raw logs in
  `logs/2026-09-17-audit/`. Blocking finding: **v2.0.0 was never tagged**, so `:latest` on GHCR is still the
  2023-01-16 manifest (root, `ENTRYPOINT /bin/bash`, `NVIDIA_REQUIRE_CUDA` with `driver<471` → it does not
  start on hosts with recent drivers), and `action.yml`/`README.md` point their users at that image. CI is
  green every week: it builds and tests an artefact nobody publishes. Thirteen findings in total, each one
  tracked by a backlog item.
- **`docs/backlog.md`**: single source of truth for todos (13 items, 4 milestones), with stable `id`s and
  documented writing conventions.
- **Backlog → GitHub issues/milestones sync**: `docs/scripts/sync-backlog-to-issues.py` (idempotent,
  `<!-- backlog-id: … | hash: … -->` fingerprint in the issue body, creates missing milestones),
  `docs/scripts/backlog-lint.py`, `docs/scripts/generate-roadmap.py`, shared library
  `docs/scripts/lib/backlog.py`, runbook `docs/scripts/README.md`. Python stdlib only.
- **`docs/roadmap.md`**: per-milestone view, **generated** from the backlog and committed (`--check` gate in CI).
- The backlog was synced for real on 2026-09-17: milestones *Ship v2.0.0*, *Image & upstream maintenance*,
  *Repository automation*, *Supply chain & security*, and issues `#24`-`#34`. Re-running produced
  `SKIP 11` (idempotence) and, after an item edit, `UPDATE 1 · SKIP 10`.
- **Release automation**: `docs/scripts/next-version.py` plus `.github/workflows/release.yml` — every commit on
  main gets a version (a CHANGELOG section above the latest tag is a *pending release* and is tagged as-is;
  otherwise the latest tag is bumped by the strongest conventional-commit marker), the `[Unreleased]` section is
  folded into it, and a tag plus a GitHub Release are created. It deliberately does **not** publish images: the
  tag is created with the `GITHUB_TOKEN`, which does not trigger other workflows.
- **`docker-publish.yml` can be dispatched**: `workflow_dispatch` with a `version` input, passed to
  `docker/metadata-action` as `value=` (`type=semver` only yields tags from a tag event). Publishing images is
  now an explicit act rather than a side effect of tagging.
- **Project page**: `site/build.py` generates `site/dist/` (a single page, dark mode, JSON-LD, Open Graph) from
  `README.md` plus the files that actually decide things — the publish matrix, the `Dockerfile`, `tests/smoke.sh`
  — so the page cannot claim something the repository does not do. Deployed by `.github/workflows/pages.yml`.
- **Tests for the tooling**: `tests/test_backlog.py`, `tests/test_site_build.py`, `tests/test_release.py`
  (52+ assertions, stdlib `unittest`), run by a new `tests` job in `ci.yml` and as a gate before releasing and
  before deploying the page.
- **`tests/build-matrix.sh`** (builds and smoke-tests every variant, reading the matrix from the publish
  workflow through the new `site/build.py --print-variants`, so it cannot drift from what CI publishes) and
  **`tests/run-all.sh`** (every local gate that needs no docker: unit tests, backlog lint, generated pages,
  hadolint/shellcheck/actionlint, skipping the ones not installed). Both covered by `tests/test_scripts.py`.
- Lint rule for **repeated meta keys** in a backlog item: the last one wins and the first is lost in silence.
  Added after making that exact mistake while writing the first backlog (a duplicated `- **labels**:`).
- `.github/workflows/backlog.yml`: `lint` (tests + backlog-lint + roadmap `--check`) on pushes/PRs touching the
  backlog paths; `sync` on the Monday schedule and on `workflow_dispatch` (`apply` input), never on pull
  requests — on a fork PR the `GITHUB_TOKEN` is read-only.
- `docs/scripts/commit.sh` does subject validation, the `[Unreleased]` entry, the local gates and the commit in one command; `docs/scripts/changelog-add.py` files a bullet in the Keep a Changelog section the commit type implies (`feat:` → Added, `fix:` → Fixed, `security:` → Security, `remove:`/`revert:` → Removed, the rest → Changed); `.githooks/commit-msg` (installed by `docs/scripts/install-hooks.sh`) rejects a subject `next-version.py` could not turn into a version bump. The prose stays hand-written — the automation picks the section, not the words.

### Changed

- **The published matrix is now FFmpeg 9.0.1 (default) / 7.1.5 / 6.1.6 / 5.1.10.** Measured across every
  maintained FFmpeg branch: the `ffnvcodec` requirement is frozen at 12.1.14.0 from 6.1 through 9.0, so
  making 9.0.1 the default **asks nothing more of the host driver** than 7.1.5 did (≥ 530 either way); 6.0.1
  was replaced by 6.1.6 because 6.0 is superseded inside the same major; 8.0/8.1 were skipped deliberately
  (same driver floor, and every row is a ~90-minute build per tag). FFmpeg 9.0 needed no change to the
  `./configure` line. Native arm64 builds plus smoke tests: **17/17 on all four** (200-205 MB) — see
  `docs/interventions/2026-09-17-matrix-9x.md`.
- **All three variants moved to the latest maintenance release of their branch**: 7.1.1 → **7.1.5**,
  6.0 → **6.0.1**, 5.1.2 → **5.1.10**. The `sdk/*` branches are unchanged, because the `ffnvcodec` constraint
  does not move inside a branch (verified on the `configure` of n5.1.10/n6.0.1/n7.1.5), so **the host's minimum
  driver does not change**: no consumer has to touch their drivers. Native arm64 builds plus smoke tests:
  **17/17 on all three** (200-203 MB) — see `docs/interventions/2026-09-17-ffmpeg-patch-bump.md`.
- **The whole project is now in English**: `README.md`, `CLAUDE.md`, `AGENTS.md`, this CHANGELOG, the audits, the
  docs, the tooling (docstrings, messages, test names), the `Dockerfile` comments, the workflows and the shell
  tests. The historical logs under `logs/` are left as they were: they are evidence, not documentation.
- `CLAUDE.md` / `AGENTS.md` (kept in sync): delivery status at the top, **TDD as a standing rule**, the
  release-versus-publish split, backlog and generated-page rules, `tests/gpu.sh` as a pre-tag gate, and three new
  traps — an Action's `runs.image` does not accept `${{ inputs… }}` (so `inputs.image` in `action.yml` is dead
  code), `PATCH /issues` replaces the entire label set, and `GET /issues` includes pull requests. Plus the
  measured fact that the `ffnvcodec` constraint stays at 12.1.14.0 up to FFmpeg 9.0.1: **moving up a version does
  not raise the minimum NVIDIA driver**.
- `README.md`: an explicit notice about what is actually on GHCR today, the new variant table, and sections for
  the backlog, the tests and the project page.
- `action.yml`: removed the `image` input, which was documented as a way to pin a version but was
  referenced nowhere — `runs.image` is static by specification and does not accept `${{ inputs… }}`. The
  file now says so, and says that pinning is done with `uses: …@vX.Y.Z`. Pinning `runs.image` itself waits
  for the `v2.0.0` tag to exist (item `action-ref-and-image-input`).
- `.dockerignore`: also excludes `logs/` and `site/`.
- `ci.yml` gained a **commit-lint** job on pull requests: it rejects subjects the release tooling could not parse and fails when a PR touches code while `[Unreleased]` is empty (docs-only and log-only PRs are exempt). It imports the same `docs/scripts/lib/changelog.py` as the local hook, so there is one rule rather than three copies.
- `release.yml` now drafts CHANGELOG entries from the conventional commits when `[Unreleased]` is empty, so a release never ships with empty notes. Hand-written entries always win; the draft only fires when there are none.

### Fixed

- `CHANGELOG` `[2.0.0]`: it claimed **18** assertions in `tests/smoke.sh`; there are **17** (as `CLAUDE.md`,
  `AGENTS.md` and `README.md` already said). The count is now derived rather than written down —
  `site/build.py` computes it from the script and a test pins it.
- `README.md`: the `uses: Allan-Nava/Docker-FFmpeg-Nvenc@v2` example and the tag table described artefacts that
  **are not published yet**.

Repair release: at the time of the audit **neither of the two published images could still be built**. It
contains changes that are not backwards compatible in how the image is used.

### BREAKING

- The image now has **`ENTRYPOINT ["ffmpeg"]`**: arguments to `docker run` go straight to ffmpeg. The old
  `docker run <img> ffmpeg -i ...` becomes `docker run <img> -i ...`. For a shell: `--entrypoint /bin/bash`.
- The container runs as a **non-root** user (`ffmpeg`, uid 1000), working directory `/data`. Volumes owned by
  other users need `--user "$(id -u):$(id -g)"`.
- Base image moved from Debian 10/11 to **Debian 12**.
- Removed `Dockerfile-ffmpeg6`, `Containerfile`, `module.defs`, `scripts/` and the `docker-publish-ffmpeg6.yml`
  workflow (see *Removed*).
- `NVIDIA_DRIVER_CAPABILITIES` narrowed from `all` to `video,compute,utility`.

### Fixed

- **Base image out of the archive**: `debian:10.10-slim` no longer built, buster's APT indexes answer 404 on
  `deb.debian.org` (they moved to `archive.debian.org`). Base moved to Debian 12 (bookworm).
- **Non-existent package**: `Dockerfile-ffmpeg6` installed `python`, removed from Debian 11 onwards. The build
  failed with `Unable to locate package python`.
- **`:latest` never published**: the workflow's semver regex ran against a `VERSION` string that already had
  `-ffmpeg5.1.2` appended, so it never matched and the branch adding `:latest`/`:MAJOR`/`:MINOR` was dead code.
  Tagging now uses `docker/metadata-action`.
- **README pointing at the wrong registry**: it told users to `docker pull allannava/docker-ffmpeg-nvenc:latest`
  from Docker Hub while CI publishes to GHCR. Combined with the previous point, the documented install
  instruction worked on neither registry.
- **`--enable-nonfree` removed**: it made the FFmpeg binary **non-redistributable** on a public registry, without
  any nonfree component actually being enabled. The image is now redistributable under GPL-3.0-or-later.
- **`action.yml` unusable**: it recompiled FFmpeg from source on every invocation (`image: 'Dockerfile'`) and
  passed the command as a single argument to an image without an `ENTRYPOINT`. It now uses the prebuilt GHCR
  image with a shell wrapper for argument splitting.
- **`ENV DEBIAN_FRONTEND noninterac1tive`**: a typo present in all three build files; the value was invalid and
  the interactive frontend stayed active.
- **Phantom CUDA flags**: `--extra-cflags=-I/usr/local/cuda/include` and `--extra-ldflags=-L/usr/local/cuda/lib64`
  pointed at directories that did not exist (no CUDA toolkit in the image) and advertised capabilities that were
  not there. NVENC only needs the `ffnvcodec` headers.
- **`apt-get update` detached from `apt-get install`**: the classic cause of a stale layer cache. Now a single
  `RUN` with `--no-install-recommends` and cleanup of `/var/lib/apt/lists`.
- **`nv-codec-headers` unpinned** in the FFmpeg 6.0 variant (a clone of `master`): a non-reproducible build and a
  risk of headers newer than the installed driver. Every variant now pins the lowest compatible `sdk/*` branch.
- **Dependabot** pointed at a non-existent `/tests` directory.
- Line continuations `\ ` (backslash plus space) in the `./configure` blocks, tolerated by BuildKit but deprecated.

### Added

- **`ci.yml` workflow**: lint (hadolint, shellcheck, actionlint), build plus smoke tests of all three variants on
  every push/PR, Trivy vulnerability scan uploaded to code scanning. Includes a **weekly schedule** to catch base
  images rotting away — which is exactly how this repository broke in silence.
- **`tests/smoke.sh`**: 17 assertions with no GPU needed (NVENC encoders present, surrounding codecs, absence of
  `--enable-nonfree`, a real end-to-end transcode, non-root, no toolchain or sources in the final image).
- **`tests/gpu.sh`**: real `h264_nvenc`/`hevc_nvenc` encoding on an NVIDIA host.
- **NVENC gate inside the Dockerfile**: the build fails if the encoders do not make it into the binary, in both
  stages.
- **Smoke tests as a publication gate**: no image reaches GHCR without passing them.
- **FFmpeg 7.1.1 variant**, which becomes the default (`latest`).
- `--enable-libx265`: the x265 runtime libraries were installed but the encoder had never been enabled. Also added
  `libass`, `libfreetype`, `libspeex`, `libtheora`, `libvorbis`, `libxml2`.
- **`LICENSE` file** (MIT for the repository) with an explicit note about the GPL licence of the artefact, which
  the README declared as MIT.
- SBOM and provenance on the published images.
- `CLAUDE.md`, `AGENTS.md`, `docs/audit/2026-08-09-initial-audit.md`, this `CHANGELOG.md`.
- `.hadolint.yaml`.

### Changed

- **A single parameterised `Dockerfile`** (`FFMPEG_VERSION`, `NVCODEC_BRANCH`, `DEBIAN_VERSION`) instead of three
  near-clone files that had drifted apart; the variants are a matrix in the workflows. Same for the two
  almost-identical publish workflows, now one.
- **Multi-stage build**: the final image contains only the binaries and the shared libraries. Before, it carried
  `build-essential`, `cmake`, `ninja-build`, `imagemagick`, the unpacked FFmpeg sources, the `make` objects, and —
  presumably inherited from a HandBrake Dockerfile — `yad`, `expect`, `tcl8.6`, GTK3 and GStreamer, in a headless
  transcoding image.
- Removed the distribution `libav*` libraries, unused by the binary built into `/usr/local`.
- Actions updated: `checkout@v4`, `setup-buildx-action@v3`, `login-action@v3`, `build-push-action@v6`,
  `metadata-action@v5`. Dropped `::set-output` (deprecated) and `github-script@v4`.
- `MAINTAINER` (deprecated) replaced by OCI labels.
- `.dockerignore` extended: it used to exclude only `.github`.
- Shared buildx GHA cache between the test build and the publish build.

### Removed

- **`Containerfile`**: a `registry.access.redhat.com/ubi8/ubi` base with `apt-get` commands and Debian packages —
  it could not work, and no workflow referenced it.
- **`Dockerfile-ffmpeg6`**: replaced by the matrix over the parameterised Dockerfile.
- **`module.defs`**: a fragment of HandBrake's build system, never evaluated by anything in this repository.
- **`scripts/`** (`base.sh`, `build-tools.sh`, `build-library.sh`, `build-ffmpeg.sh`): a parallel build path that
  was never invoked and would not have worked anyway — `build-ffmpeg.sh` read `${PREFIX}/ffmpeg_configure_options`
  and `${PREFIX}/ffmpeg_extra_libs`, files no script ever generated.
- **`.github/workflows/docker-publish-ffmpeg6.yml`**: absorbed into the matrix.

Recoverable from git: `git checkout v1.0.1 -- scripts/ module.defs Containerfile`.

## [1.0.1] - 2023-05-16

### Added

- `docker-publish-ffmpeg6.yml` workflow and `Dockerfile-ffmpeg6` (FFmpeg 6.0 on Debian 11).

## [1.0.0] - 2023-05-16

### Changed

- FFmpeg 5.1.2 build with `nv-codec-headers` pinned to `sdk/11.0`.

## [0.1.2] - 2023-01-16

### Changed

- `.dockerignore`.

## [0.1.1] - 2023-01-16

### Removed

- The `schedule` trigger from the publish workflow.

## [0.1.0] - 2023-01-16

### Added

- First publication to GHCR through GitHub Actions.

[2.0.0]: https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/compare/v1.0.1...v2.0.0
[1.0.1]: https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/compare/v0.1.2...v1.0.0
[0.1.2]: https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/releases/tag/v0.1.0
