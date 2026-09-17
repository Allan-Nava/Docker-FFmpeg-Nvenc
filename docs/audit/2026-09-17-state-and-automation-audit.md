# State-of-the-repository audit and the automation it got — Docker-FFmpeg-Nvenc (2026-09-17)

Audit of `github.com/Allan-Nava/Docker-FFmpeg-Nvenc` at commit `62357b5` (branch `main`, clean working
tree, in sync with `origin/main`), plus the tooling introduced afterwards: backlog → GitHub
issues/milestones, versioning and releases, and the project page.

It follows the [initial audit of 2026-08-09](2026-08-09-initial-audit.md), which found a repository where
**none of the published images could still be built** and which closed with the repair described in the
`[2.0.0]` section of `CHANGELOG.md`.

> **Status note added the same evening.** Read this document as the snapshot that triggered the work.
> Since then: `v2.0.0` and `v2.1.0` are tagged and released, the backlog is synced (4 milestones,
> issues #24-#34, one already closed), the project page is live, and the matrix moved to FFmpeg 9.0.1 /
> 7.1.5 / 6.1.6 / 5.1.10. **F1 is only half closed**: the release exists, the images do not — nothing
> has been pushed to GHCR yet. See [the documentation audit](2026-09-17-documentation-audit.md).
>
> **In one line: the repair works, but it never reached anyone.** CI builds and tests the three variants
> every Monday and passes; the `v2.0.0` tag was never created, so `:latest` on GHCR is still **the image
> from 16 January 2023** — root, `ENTRYPOINT /bin/bash`, single-stage, and carrying an
> `NVIDIA_REQUIRE_CUDA` constraint that stops it from starting on any host with a recent driver.

Every check in this audit is **measured**, not inferred: the GHCR registry queried through its API,
upstream releases read from `ffmpeg.org`, `ffnvcodec` constraints extracted from each release's
`configure`, Debian packages verified against `api.ftp-master.debian.org`, PR and run status read with
`gh`. Raw logs in [`logs/2026-09-17-audit/`](../../logs/2026-09-17-audit/). **No `docker build` was run
for this audit**: the weekly CI schedule speaks for the build, and it was green on 2026-09-14.

## 1. Schema: where the chain breaks

```
   repo (main, 62357b5)                                 GHCR registry
   ────────────────────                                 ─────────────
   parameterised Dockerfile           ┌───────────────┐
   tests/smoke.sh  (17 assertions)    │ ci.yml        │  push/PR + Monday 04:17
   tests/gpu.sh    (never invoked) ✗  │ lint+build+   │  ─── GREEN on 2026-09-14
                                      │ test+trivy    │      (nothing published:
                                      └───────────────┘       `load: true`, no push)
                                              │
                                              │
   CHANGELOG.md  [2.0.0] - 2026-08-09         │        ┌──────────────────────────────┐
                                              │        │ docker-publish.yml           │
   git tags: v1.0.1  v1.0.0  v0.1.2 …         │        │ on: push tags v*             │
             └── NO v2.0.0  ✗ ────────────────┼───✗───▶│ build→smoke→push GHCR        │
                     (never created)          │        └──────────────────────────────┘
                                              │                    │ never run since 2023
                                              ▼                    ▼
   README.md  →  :latest ─────────────────────────────────▶  :latest = 2023-01-16 manifest
   action.yml →  docker://…:latest ───────────────────────▶  v0.1.2 · root · /bin/bash
   README.md  →  uses: …@v2  ✗ (ref does not exist)          NVIDIA_REQUIRE_CUDA driver<471
                                                             → will not start on 535/550/570
   leftover registry tags: main, pr-2, pr-3, pr-4, pr-5, v0.1.1, v0.1.2,
                           v1.0.1-ffmpeg5.1.2, v1.0.1-ffmpeg6.0
                           (published by workflows that no longer exist)
```

The break is not technical but **procedural**: the only act that publishes (`git tag` plus a tag push) is
the one act this repository deliberately does not automate — the push is the user's. Since 2026-08-09 the
repository has therefore been in a stable, silent state: green CI, broken public artefact.

## 2. Checks performed (evidence)

### 2.1 What is actually published on GHCR

`GET /v2/allan-nava/docker-ffmpeg-nvenc/tags/list` (log `ghcr-tags-e-manifest.log`):

```
main, pr-2, pr-3, pr-4, pr-5, v0.1.1, v0.1.2, latest, v1.0.1-ffmpeg5.1.2, v1.0.1-ffmpeg6.0
```

Config blob of the `:latest` tag:

| field | value read |
|---|---|
| `created` | `2023-01-16T16:52:50Z` |
| `org.opencontainers.image.version` | `v0.1.2` |
| `User` | *(empty → root)* |
| `Entrypoint` | `["/bin/bash"]` |
| layers | 10 (no multi-stage) |
| `NVIDIA_REQUIRE_CUDA` | `cuda>=11.5 brand=tesla,driver>=470,driver<471 …` |
| `NVIDIA_DRIVER_CAPABILITIES` | `compute,utility,video` |

That last row is the harshest: with `NVIDIA_REQUIRE_CUDA` admitting only `driver>=470,<471`, the NVIDIA
Container Toolkit **refuses to start the container** on a host with driver 535/550/570
(`requirement error: unsatisfied condition`). The image the README tells people to pull is not merely
"old": it is unstartable on current hardware.

The `main` tag (created 2023-01-19) is from the same family. No `v2.*` tag exists on the registry.

### 2.2 Git/GitHub state

`git tag` → `v1.0.1, v1.0.0, v0.1.2, v0.1.1, v0.1.0`. `gh release list` → latest release `v1.0.1`,
**2023-05-16**. `main` is level with `origin/main` (0/0): the v2.0.0 code is pushed, only the tag is missing.

`gh run list` → the only recent runs are the **weekly `ci.yml` schedule** (14/09, 07/09, 31/08, 24/08,
17/08, 10/08: all `success`) and the Dependabot job. `docker-publish.yml` shows no run at all.

`gh pr list` → **6 open PRs, 0 issues**:

| PR | date | subject | note |
|---|---|---|---|
| #23 | 2026-08-09 | `docker/login-action` 3→4 | major, untouched for 5 weeks |
| #22 | 2026-08-09 | `docker/setup-buildx-action` 3→4 | major |
| #21 | 2026-08-09 | `docker/build-push-action` 6→7 | major |
| #20 | 2026-08-09 | `docker/metadata-action` 5→6 | major, touches the tagging that **already broke once** |
| #18 | 2023-03-13 | `nvidia/cuda` base bump | fossil: refers to `Containerfile`, removed in v2.0.0 |
| #5 | 2023-01-16 | `sigstore/cosign-installer` | fossil: the signing workflow no longer exists |

### 2.3 Upstream FFmpeg and the `ffnvcodec` constraint

Releases on `ffmpeg.org/releases` (tail): `7.1.3, 7.1.4, 7.1.5, 8.0.x, 8.1, 8.1.1, 8.1.2, 9.0, 9.0.1`.
At audit time the repository pinned `7.1.1`, `6.0`, `5.1.2`.

`grep 'ffnvcodec >=' configure` per release (log `upstream-ffmpeg-nvcodec.log`):

```
  n5.1.2 → ffnvcodec >= 9.1.23.1      (matrix: sdk/11.0 → driver ≥ 470)
  n6.0   → ffnvcodec >= 12.0.16.0     (matrix: sdk/12.0 → driver ≥ 530)
  n7.1.1 → ffnvcodec >= 12.1.14.0     (matrix: sdk/12.1 → driver ≥ 530)
  n7.1.5 → ffnvcodec >= 12.1.14.0     ── identical
  n8.1.2 → ffnvcodec >= 12.1.14.0     ── identical
  n9.0.1 → ffnvcodec >= 12.1.14.0     ── identical
```

The operational consequence is counter-intuitive and useful: **moving to 7.1.5, 8.1.x or even 9.0.x does
not raise the host's minimum NVIDIA driver**, because the `ffnvcodec` requirement has been frozen at
12.1.14.0 since the 7.1 branch. `sdk/12.1` covers all of it; `sdk/12.2` and `sdk/13.0` exist but buy
nothing and would only raise the host requirement. The patch bump (7.1.1 → 7.1.5) is therefore the
lowest-risk, highest-value change on the list — and it was done the same day (§4).

### 2.4 Base image and packages

`madison` over `bookworm,trixie` (log `debian-pacchetti-bookworm-trixie.log`): bookworm answers
`oldstable`, trixie `stable`. For a future `DEBIAN_VERSION=13`, exactly three versioned names in the
runtime stage need realigning:

```
  libvpx7      1.12.0  (oldstable)  →  libvpx9      1.15.0  (stable)
  libx265-199  3.5     (oldstable)  →  libx265-215  4.1     (stable)
  libx264-164  ————————— present in BOTH (0.164.3095 → 0.164.3108) —————————
```

Every other runtime package (`libass9`, `libfontconfig1`, `libfreetype6`, `libfribidi0`, `libharfbuzz0b`,
`libmp3lame0`, `libnuma1`, `libopus0`, `libspeex1`, `libtheora0`, `libvorbis0a`, `libvorbisenc2`,
`libxml2`) exists in trixie under the same name. No urgency — bookworm has long-term support — but it is
this repository's known silent-breakage vector.

### 2.5 Internal documentation consistency

One mismatch found, minor but telling: the `[2.0.0]` section of `CHANGELOG.md` claimed **18** assertions in
`tests/smoke.sh`, while `CLAUDE.md`, `AGENTS.md` and the script itself counted **17** (2 binaries +
1 expected version + 2 NVENC + 5 codecs + 2 licence + 1 transcode + 4 container hygiene). Fixed here — and
the number is now derived rather than written: `site/build.py` computes it from the script (loops included)
and a test pins it at 17.

## 3. Findings

| # | Finding | Severity | Backlog item |
|---|---|---|---|
| F1 | `v2.0.0` never tagged: `:latest` on GHCR is the 2023 image, unstartable on recent drivers | **blocker** | `publish-v2-0-0` |
| F2 | `action.yml` pins a moving `:latest`, the README documents a non-existent `@v2`, `inputs.image` is dead code | **high** | `action-ref-and-image-input` |
| F3 | Default FFmpeg stuck at 7.1.1 with 7.1.5 available at no driver cost | high | `ffmpeg-patch-bump` (**done**) |
| F4 | 4 major Dependabot PRs idle for 5 weeks + 2 fossils on removed files | high | `dependabot-backlog-prs` |
| F5 | Leftover `main`/`pr-*`/v0.1.x tags public on the registry, no retention | medium | `ghcr-tag-hygiene` |
| F6 | `tests/gpu.sh` invoked by no workflow: promoting a tag is blind to NVENC | medium | `gpu-gate-before-tag` |
| F7 | Trivy runs on one variant and blocks nothing (no `exit-code`) | medium | `trivy-not-a-gate` |
| F8 | Matrix stuck at 7.1.x: 8.1.x/9.0.x not evaluated (at zero driver cost) | medium | `ffmpeg-8-and-9-variants` |
| F9 | `debian:12-slim` base is oldstable; package lists not parameterised on `DEBIAN_VERSION` | medium | `debian-13-trixie` |
| F10 | Images unsigned (provenance/SBOM yes, cosign no — the repository used to sign) | low | `cosign-image-signing` |
| F11 | `linux/amd64` only, neither implemented nor declared unsupported for arm64 | low | `multiarch-arm64` |
| F12 | No channel for todos: 0 issues, no backlog, no milestones | medium | *resolved here* |
| F13 | `CHANGELOG` said 18 smoke assertions; there are 17 | low | `doc-drift-smoke-assertions` (done) |

What this audit did **not** find is worth stating: the `Dockerfile`, the tests and the two workflows
introduced in v2.0.0 hold up. The three variants build and pass 17/17 every Monday, the NVENC gates inside
the Dockerfile are there, `--enable-nonfree` is absent with a dedicated assertion, the container runs
non-root with narrowed capabilities, and the multi-stage split is real (no compiler, no sources in the
final image). The open problems are about **delivery and maintenance**, not construction.

## 4. What was done on 2026-09-17

### 4.1 Backlog → issues/milestones (F12)

The repository had thirteen known problems and nowhere to keep them. The model used in the `devops_hiway`
repository was ported from GitLab to GitHub:

```
  docs/backlog.md  ──parse(id)──▶  sync-backlog-to-issues.py  ──GitHub API──▶  Issues + Milestones
   ### `id` — Title                 (idempotent, fingerprint            (label backlog-sync,
   - status/priority/labels          <!-- backlog-id: id | hash: … -->)  milestone created if missing)
   - milestone/ref
        │
        ├──▶ backlog-lint.py        (unique ids, valid status/priority, known and non-repeated
        │                            meta keys, consistent milestone titles)
        └──▶ generate-roadmap.py ──▶ docs/roadmap.md   (GENERATED and committed; --check in CI)
```

Differences from the GitLab original, forced by the GitHub API (also documented in
`docs/scripts/README.md`):

- **`PATCH /issues/:n` replaces the entire label set** (GitLab has `add_labels`): the script **unions** it
  with the labels already on the issue, otherwise every sync would delete the ones added by hand.
- **`GET /issues` includes pull requests**: filtered on the `pull_request` key. Without the filter, a PR
  carrying the `backlog-sync` label would be read as a phantom item and **closed** — with six open PRs in
  this repository, that would have happened on the very first run.
- Milestones are identified by `number` (not `id`) and created with `POST /milestones` when the exact
  title does not exist.
- `state_reason: completed` on closure, to distinguish it from "not planned" in the UI.

### 4.2 Version and release on every commit

`docs/scripts/next-version.py` + `.github/workflows/release.yml`: every commit on main gets a version, a
CHANGELOG section and a GitHub Release. The rule that matters is the first one, and it exists because of
F1: **a CHANGELOG section numbered above the latest tag is a pending release** and gets tagged as-is —
which is how `[2.0.0]`, written on 2026-08-09 and never shipped, finally goes out.

Releasing deliberately does **not** publish images: the tag is created with the `GITHUB_TOKEN`, which by
design does not trigger other workflows, so `docker-publish.yml` stays explicit (it gained a
`workflow_dispatch` with a `version` input for exactly that). Three ~90-minute builds and public artefacts
should follow a decision, not a commit.

### 4.3 Project page (GitHub Pages)

`site/build.py` generates a single page from `README.md` **plus the files that actually decide things**:
the publish matrix (which variants exist), the `Dockerfile` (which `--enable-*` flags are on), and
`tests/smoke.sh` (how many assertions gate the publish). The page cannot advertise a codec the image does
not have, or a variant that is not published, because it does not hold its own copy of those facts. The
`driver_floor()` table raises on an unmapped `sdk/*` branch instead of printing a plausible number, and a
test pins the absence of `nonfree` among the advertised flags.

### 4.4 Tests first (TDD)

Every piece of tooling above was written test-first: `tests/test_backlog.py`, `tests/test_site_build.py`,
`tests/test_release.py`, stdlib `unittest`, run by `ci.yml`, by `pages.yml` before deploying and by
`release.yml` before tagging.

Two of those tests exist because the code was wrong first:
- the **repeated meta key** lint rule (`- **labels**:` twice in one item): the first draft of the backlog
  contained exactly that, and nothing noticed — the last one silently wins;
- the **pull-request filter** in the sync, whose test documents the phantom-item closure it prevents.

Verifications (log `tooling-backlog-verifica.log`): `backlog-lint` on the real backlog, `--check` on the
generated pages, an **authenticated** dry-run of the sync against the real repository
(`CREATE 12 · UPDATE 0 · REOPEN 0 · CLOSE 0 · SKIP 0` — the zero on `CLOSE` is the answer that mattered:
the label query picked up none of the six open PRs), `actionlint` from the root, `shellcheck` on
`tests/*.sh`.

Then the sync was actually applied against the repository: **4 milestones and 11 issues created**
(`#24`-`#34`, one per active item), a second run reporting `CREATE 0 · UPDATE 0 · CLOSE 0 · SKIP 11`, and a
third — after editing one item — reporting `UPDATE 1 · SKIP 10`. Create, skip and update paths are
therefore proven on the real API, not only in a dry-run. What is still unproven is the same thing running
under the workflow's own `GITHUB_TOKEN`, plus Pages and the release workflow, all of which need the push
(item `automation-first-run`).

### 4.5 FFmpeg patch bump (F3)

All three variants moved to the latest maintenance release of their branch — 7.1.1 → 7.1.5, 6.0 → 6.0.1,
5.1.2 → 5.1.10 — with the `sdk/*` branches unchanged, and therefore no change to the minimum driver.
Native arm64 builds plus smoke tests: 17/17 on all three. Detail and logs:
[`docs/interventions/2026-09-17-ffmpeg-patch-bump.md`](../interventions/2026-09-17-ffmpeg-patch-bump.md).

### 4.6 English

The whole project was translated to English in the same pass: README, `CLAUDE.md`/`AGENTS.md`, CHANGELOG,
audits, tooling (docstrings, messages, test names), `Dockerfile` comments, workflows and shell tests. The
logs under `logs/` were left as they were — they are evidence, not documentation.

## 5. Suggested sequence

```
  1. push the branch  ──▶ Release tags v2.0.0 and publishes the GitHub Release (no images)
  2. Backlog workflow (dispatch, apply=false) ──▶ read the plan ──▶ apply=true ──▶ 4 milestones + 12 issues
  3. Settings ▸ Pages ▸ Source: GitHub Actions ──▶ check the deployed page
  4. ./tests/gpu.sh on the 3 variants on a GPU host                  [gpu-gate-before-tag]
  5. Publish (dispatch, version: v2.0.0) ──▶ check the tags on GHCR  [publish-v2-0-0]
  6. action.yml: pin to v2.0.0, drop inputs.image, align the README  [action-ref-and-image-input]
  7. merge the four Dependabot PRs in one go, close the two fossils  [dependabot-backlog-prs]
  8. registry hygiene (pr-*, main) — AFTER step 5, never before      [ghcr-tag-hygiene]
```

Steps 1-3 and 6-8 need no GPU. Step 4 is the only one that needs hardware, and it remains the most
important gate: it is the only proof that the image does the job it exists for.
