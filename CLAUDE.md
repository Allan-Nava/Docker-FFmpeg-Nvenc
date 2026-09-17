# CLAUDE.md — Docker-FFmpeg-Nvenc

Repository that builds container images of **FFmpeg compiled with NVIDIA NVENC support** (`github.com/Allan-Nava/Docker-FFmpeg-Nvenc`). It publishes to **GHCR** (`ghcr.io/allan-nava/docker-ffmpeg-nvenc`) through GitHub Actions and exposes a reusable **GitHub Action** (`action.yml`).

```
Dockerfile              → SINGLE source, multi-stage, parameterised
                          ARG FFMPEG_VERSION / NVCODEC_BRANCH / DEBIAN_VERSION
tests/smoke.sh          → 17 assertions, no GPU needed (gate for CI and for publishing)
tests/gpu.sh            → real NVENC encoding, needs an NVIDIA host
tests/build-matrix.sh   → builds + smoke-tests every variant, matrix read from the workflow
tests/run-all.sh        → every local gate that needs no docker (pre-commit)
tests/test_*.py         → stdlib unittest for the Python tooling and the page generator
action.yml              → GitHub Action on the prebuilt GHCR image
.github/workflows/ci.yml              → lint + tests + build&test matrix + scan; push/PR + weekly
.github/workflows/docker-publish.yml  → build → test → push to GHCR; on v* tags or dispatch
.github/workflows/release.yml         → every commit on main: version, CHANGELOG, tag, Release
.github/workflows/backlog.yml         → backlog lint + issue/milestone sync (schedule + dispatch)
.github/workflows/pages.yml           → builds and deploys the project page
docs/backlog.md         → SINGLE source of todos (stable ids → GitHub issues)
docs/roadmap.md         → GENERATED from docs/backlog.md (never edit by hand)
docs/scripts/           → backlog and release tooling — runbook in docs/scripts/README.md
docs/audit/             → project audits
docs/interventions/     → what was changed, why, and the verification output
site/                   → page generator (build.py) + assets; output in site/dist/ (committed)
logs/                   → raw logs attached to the docs (evidence, not regenerable)
```

The variants are a **matrix in the workflows**, not duplicated files:

| FFmpeg | `NVCODEC_BRANCH` | min NVIDIA driver | default |
|---|---|---|---|
| 9.0.1 | `sdk/12.1` | ≥ 530 | yes (`latest`) |
| 7.1.5 | `sdk/12.1` | ≥ 530 | no |
| 6.1.6 | `sdk/12.1` | ≥ 530 | no |
| 5.1.10 | `sdk/11.0` | ≥ 470 | no |

Every variant is the **latest maintenance release** of its branch, on the **lowest** `sdk/*` branch its `configure` accepts. Measured on every maintained branch (2026-09-17): `ffnvcodec >=` is 9.1.23.1 for 5.1, 12.0.16.0 for 6.0, and **12.1.14.0 from 6.1 through 9.0** — so a newer FFmpeg does not raise the host's driver floor, and one `sdk/12.1` covers everything above 6.1. `sdk/12.2` and `sdk/13.0` exist upstream and are deliberately unused (they would only raise that floor). 6.0 was dropped in favour of 6.1, which is the maintained 6.x line.

⛔ **Delivery status as of 2026-09-17: v2.0.0 has never been tagged.** The `CHANGELOG` has a `[2.0.0]` section, but the latest tag is `v1.0.1` (2023) and `:latest` on GHCR is still **the 2023-01-16 image** (root, `ENTRYPOINT /bin/bash`, `NVIDIA_REQUIRE_CUDA … driver<471` → it does not start on recent drivers). Never describe the published image as if it were the one on `main`: until the tag exists, the README and `action.yml` point at a broken artefact. Details and plan: `docs/audit/2026-09-17-state-and-automation-audit.md`, item `publish-v2-0-0`.

## Working rules (ALWAYS)

- **Test first, always (TDD).** Every new capability starts with a test that **fails**, then the code that makes it pass — tooling included (page generator, linters, parsers, version logic). Report the real output of both phases, never "it should work". If a regression would not be caught by the tests, the test is incomplete.
- **Every commit on main becomes a tagged release.** `release.yml` computes the version with `docs/scripts/next-version.py` (a CHANGELOG section above the latest tag is a *pending release* and gets tagged as-is; otherwise the latest tag is bumped by the strongest conventional-commit marker), folds `## [Unreleased]` into the version section, tags, and creates the GitHub Release. Write commits as conventional commits (`feat:`, `fix:`, `docs:`, `feat!:`) — that is what decides the bump.
- **Releasing is not publishing.** The tag is created with the `GITHUB_TOKEN`, which by design does not trigger other workflows, so images reach GHCR only through an explicit act: push a tag by hand or run `Publish` (`workflow_dispatch`, input `version: vX.Y.Z`). Publishing means three ~90-minute builds and public artefacts; it stays a decision.
- **Work in progress goes under `## [Unreleased]`** in `CHANGELOG.md` (Keep a Changelog): the release workflow turns it into the version section.
- **NEVER `git push`** — the user always does that (doubly so here: pushing a tag publishes public images to GHCR). **NEVER `Co-Authored-By`** in commits.
- **ALWAYS document** audits, interventions and build debugging: a `.md` in `docs/` (audits in `docs/audit/`, interventions in `docs/interventions/`, incidents in `docs/incidents/`), **without being asked**. Every doc: an **ASCII diagram/schema**, raw logs in `logs/<date>-<slug>/`, a line in the CHANGELOG.
- **Todos → `docs/backlog.md`** (single source, stable `id`s, idempotent sync to GitHub issues). Do not scatter TODOs through the code or the docs: an audit finding is closed by a row in the findings table **and** an item in the backlog. Hardening/cleanup items get the `cleanup` label; do not present them as "next".
- **Change `docs/backlog.md` → regenerate `docs/roadmap.md`** (`python3 docs/scripts/generate-roadmap.py`) and commit it; same for the page (`python3 site/build.py`). The `generated-pages` gates run both with `--check` and go red when they diverge. Before committing the backlog: `python3 docs/scripts/backlog-lint.py`.
- **Keep everything aligned**: every factual change has to reach `Dockerfile`, `README.md`, `action.yml`, the workflows, `tests/`, `CHANGELOG.md`, `docs/backlog.md`, and this file + `AGENTS.md` (which are kept in sync with each other).
- **Nothing is "done" without a verified build.** The only proof that a Dockerfile change works is `docker build` followed by `./tests/smoke.sh`. Report the real output, not the intent.
- **Read the right exit code**: in `docker build ... > log; echo $?; tail log` the reported exit status belongs to `tail`. Check that `ERROR: failed to solve` is absent from the log, not just the final code.
- **Every new capability needs an assertion in `tests/smoke.sh`.**
- **`tests/gpu.sh` before promoting a tag.** No GitHub-hosted runner has a GPU: the smoke test proves NVENC is *compiled in*, not that it *encodes*. It is the only gate covering a driver/`NVCODEC_BRANCH` mismatch, and it is manual (item `gpu-gate-before-tag`).

## Pattern for image work

1. **Preflight**: is the base image still supported (APT repos reachable) and do the packages exist in that suite — `https://api.ftp-master.debian.org/madison?package=<pkg>&s=<suite>`. For FFmpeg, read the `ffnvcodec` constraint from the release's `configure`: `curl -s https://raw.githubusercontent.com/FFmpeg/FFmpeg/n<ver>/configure | grep "ffnvcodec >="`.
2. **Local build**: `./tests/build-matrix.sh [version …]` builds and smoke-tests the variants, reading the matrix from the publish workflow (`site/build.py --print-variants`) so it cannot drift from what CI publishes; logs land in `logs/<date>-build-matrix/`. For a one-off: `docker build --build-arg FFMPEG_VERSION=… --build-arg NVCODEC_BRANCH=… -t ffmpeg-nvenc:test .` with the log in a file; long runs in the background.
3. **Smoke test**: `./tests/smoke.sh ffmpeg-nvenc:test <expected-version>` — it must close 17/17.
4. **Lint**: `./tests/run-all.sh` runs the whole non-docker gate (unit tests, backlog lint, generated pages, `hadolint`, `shellcheck`, `actionlint`; missing linters are skipped with a note). `actionlint` must run **from the repository root** (outside it you get 3 "no project was found").
5. **On a GPU**: `./tests/gpu.sh` on an NVIDIA host before promoting a tag.
6. **Closing**: a `.md` doc + logs in `logs/` + CHANGELOG (`## [Unreleased]`) + README aligned + backlog items updated (`status: done` on the closed ones) + regenerated roadmap and page.

## Known traps / technical rules

- **`ffmpeg … | grep -q` fails with exit 141 even when the test passes.** `grep -q` exits on the first match, ffmpeg takes SIGPIPE, and with `pipefail` the pipeline returns 141. This applies to the gates in the `Dockerfile` (`SHELL … -o pipefail`) **and to `run:` steps in the workflows** (Actions uses `bash -e -o pipefail` by default). The right pattern: redirect to a file, then `grep` the file. It has already cost this repository a build.
- **Debian bases rot in silence.** buster is gone from `deb.debian.org` (404, content on `archive.debian.org`) — that is how this repository broke without anyone noticing. Bookworm is `oldstable` now that trixie is `stable`. The **weekly schedule in `ci.yml` exists for this**: if it fails on a Monday when nobody touched the code, a base or an APT repo has almost certainly rotted.
- **Check that a package exists in the suite before using it.** `python` does not exist from bullseye onwards (only `python2`/`python3`) and that is what blocked the FFmpeg 6.0 variant.
- **Versioned runtime package names are tied to the suite**: `libx264-164`, `libx265-199`, `libvpx7` are bookworm. Changing `DEBIAN_VERSION` means realigning them or the runtime stage installs nothing. On trixie (verified 2026-09-17): `libvpx7`→`libvpx9`, `libx265-199`→`libx265-215`, `libx264-164` stays.
- **`NVCODEC_BRANCH` sets the host's minimum NVIDIA driver.** Do not raise it without a reason: `sdk/13.0` needs very recent drivers. The floor is whatever FFmpeg's `configure` requires (5.1 → ≥ 9.1.23.1, 6.0 → ≥ 12.0.16.0, 7.1 → ≥ 12.1.14.0); pick the **lowest** branch that satisfies it. ⭐ Verified 2026-09-17: the constraint is **still 12.1.14.0 on 7.1.5, 8.1.2 and 9.0.1** → moving up an FFmpeg version does **not** raise the minimum driver, `sdk/12.1` covers all of it. Runtime symptom of a mismatch: `This NVENC API is not compatible with the installed driver`.
- **NVENC does not need the CUDA toolkit**, only the `ffnvcodec` headers. Do not reintroduce `--extra-cflags=-I/usr/local/cuda/include` / `--extra-ldflags=-L/usr/local/cuda/lib64`: those directories do not exist in the image and they advertise capabilities that are not there. They are only needed if you really enable `--enable-cuda-nvcc`/`--enable-libnpp`/`--enable-nvdec`, which require an `nvidia/cuda:*-devel` base.
- **NEVER `--enable-nonfree`** on a published image: it makes the binary **non-redistributable**. `tests/smoke.sh` has a dedicated assertion, and `site/build.py` reads the enabled flags from the Dockerfile with a test pinning the absence of `nonfree`. The same goes for `libfdk-aac`. The image is GPL-3.0-or-later (because of libx264/libx265) and the repository is MIT: two different licences, do not conflate them.
- **The image has `ENTRYPOINT ["ffmpeg"]` and runs as a non-root user (uid 1000)**, workdir `/data`. Examples in docs must not repeat `ffmpeg`; a shell needs `--entrypoint /bin/bash`; mounted volumes need `--user "$(id -u):$(id -g)"`. ⚠️ That describes the image on `main`, **not** the one currently published on GHCR (see the delivery-status note).
- **The GitHub Action cannot use NVENC on GitHub-hosted runners** (no GPU): CPU encoding only, or a self-hosted runner with the NVIDIA Container Toolkit. `action.yml` passes the command through a `bash -c` wrapper because with `ENTRYPOINT ffmpeg` a single element in `args` would arrive as **one single argument**. ⚠️ `runs.image` is **static by specification**: it does not accept `${{ inputs… }}`, so `action.yml`'s `inputs.image` currently does nothing (item `action-ref-and-image-input`).
- **Workflow tagging uses `docker/metadata-action`**, with `suffix=-ffmpeg<ver>` per variant plus a second block without a suffix for the `default: true` variant only. The previous version applied a semver regex to a string the suffix made structurally unmatchable: `:latest` was never published. `type=semver` only yields tags from a tag event, so the `workflow_dispatch` path passes `value=${{ inputs.version }}`. If you touch the tagging, check the actual tags on GHCR after the first tag.
- **`shellcheck` exits 1 even on `info` findings**: one informational `SC20xx` is enough to break CI. Use targeted, justified `# shellcheck disable=` directives.
- **A comment line starting with `# shellcheck …` is parsed as a directive**, not as prose: a header sentence beginning with that word dies with `SC1072/SC1073 Couldn't parse this shellcheck directive`. Reword it (`# ShellCheck and actionlint …`) — it cost a red run of `tests/run-all.sh` the day it was written.
- **`hadolint`**: `DL3008` (pinning apt versions) is ignored in `.hadolint.yaml` — pinning Debian versions would freeze security patches at every point release. `DL3066` on `USER ffmpeg` is informational and below the failure threshold.
- **The build context goes through `.dockerignore`**: `docs/`, `logs/`, `site/`, `tests/`, `*.md` are excluded. If a new file is needed by the build, take it out of the ignore list.
- **GitHub API rules in the backlog sync** (`docs/scripts/sync-backlog-to-issues.py`): `PATCH /issues/:n` **replaces** the whole label set (unlike GitLab's `add_labels`) → the script unions it with what is already there; do not touch that logic or every sync will wipe labels added by hand. And `GET /issues` **includes pull requests**: they are filtered on the `pull_request` key, otherwise a PR carrying the `backlog-sync` label would be closed as a phantom item. The tooling is **stdlib only** (no `setup-python`, no `requirements.txt`): keep it that way.
- **The backlog decides, not the UI**: an item with `status: open` whose issue was closed by hand is reopened on the next sync. To close it for real, set `status: done` on the item.

## Pointers

- **Audits**: `docs/audit/2026-09-17-state-and-automation-audit.md` (current state + findings + backlog) · `docs/audit/2026-08-09-initial-audit.md` (the pre-repair snapshot, read it in the past tense)
- **Interventions**: `docs/interventions/` — e.g. `2026-09-17-ffmpeg-patch-bump.md`
- **Backlog**: `docs/backlog.md` · **Roadmap by milestone**: `docs/roadmap.md` (generated) · **Tooling runbook**: `docs/scripts/README.md`
- Issues managed by the sync carry the `backlog-sync` label · Milestones: `https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/milestones`
- **Project page**: `https://allan-nava.github.io/Docker-FFmpeg-Nvenc/` — generated by `site/build.py`, deployed by `pages.yml`
- Registry: `https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/pkgs/container/docker-ffmpeg-nvenc`
- NVIDIA GPU/NVENC matrix: `https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new`
- `nv-codec-headers`: `https://github.com/FFmpeg/nv-codec-headers` (`sdk/<ver>` branches)
- Code removed in v2.0.0 (recoverable): `git checkout v1.0.1 -- scripts/ module.defs Containerfile`
