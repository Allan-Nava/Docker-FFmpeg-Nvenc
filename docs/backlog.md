# Operational backlog — source of truth for the GitHub issues

This file is the **single source of truth** for the repository's todos. An idempotent script
([`scripts/sync-backlog-to-issues.py`](scripts/sync-backlog-to-issues.py)) reads it and
**opens, updates and closes** one GitHub issue per item, **creating the missing milestones**,
scheduled by [`.github/workflows/backlog.yml`](../.github/workflows/backlog.yml).

## How it works

```
  docs/backlog.md  ──parse(id)──▶  sync-backlog-to-issues.py  ──GitHub API──▶  Issues + Milestones
   ### `id` — Title                  (idempotent)                              (label backlog-sync
   - status / labels / milestone     fingerprint                                + fingerprint in the body)
   - priority / ref                  <!-- backlog-id: id | hash: … -->

   item open  + no issue          → CREATE   (milestone created if missing)
   item open  + open issue, hash= → SKIP     (no duplicates: matched by `id`)
   item open  + open issue, hash≠ → UPDATE   (title/body/labels/milestone realigned)
   item open  + closed issue      → REOPEN   (the backlog decides, not the UI)
   item done / removed            → CLOSE    (with a comment and the reason)

                 │
                 └─▶ generate-roadmap.py ──▶ docs/roadmap.md   (GENERATED page, committed,
                                                                `generated-pages` gate in CI)
```

Re-running is safe: the match is by stable `id` (fingerprint in the issue body), **not** by text, so
editing a title or a description never creates a duplicate.

## How to write an item

- An item starts with `### \`<stable-id>\` — <Title>` (the `id` is in backticks, kebab-case, **never change it**).
- Metadata as `- **key**: value` bullets:
  - **status**: `open` (default) | `done` → `done` closes the issue.
  - **labels**: comma-separated (`backlog-sync` is added automatically; labels added by hand on the
    issue are **not** removed — the script unions them).
  - **priority**: `low` | `medium` | `high` (optional).
  - **milestone**: the title of a GitHub milestone (optional). The script looks it up by **exact
    title and creates it if missing**, then assigns the issue. Items in the same milestone must use
    the same title, character for character.
  - **owner**: GitHub username (optional, becomes the assignee).
  - **ref**: link or path to the doc or audit (optional).
- Everything else in the block (prose) becomes the issue **body**.

> To "close" a todo: set `status: done` (keeps the history) **or** remove the item. Either way the
> issue is closed on the next sync. Prefer `done` for items **already synced** (the issue closes with
> the reason attached); removal is fine only for items that were never synced.

> Before opening a new item, **look for the duplicate by artefact**, not by the words of the problem:
> the path (`grep -i action.yml docs/backlog.md`), the GHCR tag, the workflow name, the FFmpeg
> variant. Two items written weeks apart about the same action use different words.

Local validation (the same commands CI runs):

```shell
python3 docs/scripts/backlog-lint.py
python3 docs/scripts/generate-roadmap.py            # regenerate docs/roadmap.md (commit it)
python3 docs/scripts/sync-backlog-to-issues.py      # dry-run: prints the plan, writes nothing
```

---

## Active items

### `publish-v2-0-0` — The whole v2.0.0 repair is on main but unpublished: `:latest` on GHCR is the 2023 image

- **status**: open
- **priority**: high
- **labels**: release, docker, bug
- **milestone**: Ship v2.0.0
- **ref**: [audit/2026-09-17-state-and-automation-audit.md](audit/2026-09-17-state-and-automation-audit.md)

`CHANGELOG.md` has a `[2.0.0] - 2026-08-09` section but **the `v2.0.0` tag does not exist** (latest tag:
`v1.0.1`, May 2023). The publish workflow only fires on `v*` tag pushes, so **nothing was ever published**.
Verified against the registry on 2026-09-17: `ghcr.io/allan-nava/docker-ffmpeg-nvenc:latest` is a manifest
**created on 2023-01-16**, labelled `org.opencontainers.image.version=v0.1.2`, with an empty `User`
(**runs as root**), `ENTRYPOINT ["/bin/bash"]`, 10 layers (no multi-stage) and
`NVIDIA_REQUIRE_CUDA=… driver>=470,driver<471`: on a host with a modern driver (535/550/570) the container
**does not start at all** (`requirement error: unsatisfied condition`).

So today: anyone following the README pulls the broken 2023 image, and the CI that is green every Monday
certifies an artefact nobody can use.

Closing it (the tag push is the user's):
- [ ] `./tests/gpu.sh` on an NVIDIA host for all four variants (never run in CI)
- [x] release `v2.0.0` — done on 2026-09-17: `release.yml` tagged it and published the GitHub Release
      (followed by `v2.1.0`). Releasing is not publishing: the images are still the 2023 ones
- [ ] run `Publish` (workflow_dispatch, `version: v2.0.0`) to put the images on GHCR
- [ ] verify the registry with `./tests/verify-registry.sh vX.Y.Z` — it generates the expected tags from the
      matrix and compares them with GHCR **by digest**, so an alias pointing at the wrong image is caught
      (today it reports 19 of 20 tags missing and `:latest` on the 2023 digest, which is the correct answer)
- [ ] check that `:latest` now has `User=ffmpeg` and `Entrypoint=["ffmpeg"]`
- [ ] follow [the publish runbook](runbooks/publish-release.md) for the whole sequence and the after-steps

### `action-ref-and-image-input` — The published Action pins `:latest`, `@v2` does not exist, and `inputs.image` is dead code

- **status**: open
- **priority**: high
- **labels**: github_actions, documentation, bug
- **milestone**: Ship v2.0.0
- **ref**: [audit/2026-09-17-state-and-automation-audit.md](audit/2026-09-17-state-and-automation-audit.md)

Three problems in one file, `action.yml`:

1. `runs.image: docker://…:latest` — a **moving** tag: the Action changes under its consumers on every
   publish, and today it runs the 2023 image (see `publish-v2-0-0`).
2. `README.md` documents `uses: Allan-Nava/Docker-FFmpeg-Nvenc@v2`, but **no `v2` tag or branch exists**:
   that example does not resolve.
3. `inputs.image` exists and is documented as "override to pin a specific version", but it is
   **referenced nowhere**: `runs.image` is static by GitHub's specification (it does not accept `${{ }}`
   expressions). It is an input that promises something it cannot do.

Decision to take: pin `runs.image` to `vX.Y.Z` (or to the digest) and update it on every release.

> **Partially done on 2026-09-17**: point 3 is closed — `inputs.image` was removed and `action.yml` now
> documents why it cannot exist (`runs.image` is static by specification) and that pinning is done with
> `uses: …@vX.Y.Z`. Points 1 and 2 stay open: they need the `v2.0.0` tag to exist first
> (`publish-v2-0-0`), otherwise pinning `runs.image` would point at nothing.

### `ghcr-tag-hygiene` — `main`, `pr-2`…`pr-5` and the 2023 v0.1.x images are still on the registry

- **status**: open
- **priority**: medium
- **labels**: docker, cleanup
- **milestone**: Ship v2.0.0

Tags on GHCR (2026-09-17): `main`, `pr-2`, `pr-3`, `pr-4`, `pr-5`, `v0.1.1`, `v0.1.2`, `latest`,
`v1.0.1-ffmpeg5.1.2`, `v1.0.1-ffmpeg6.0`. The `pr-*` and `main` tags are leftovers from workflows that
**no longer exist** (nothing publishes on branch or PR events today): 2023 images, running as root, built
with `--enable-nonfree`, pullable by anyone.

To do after `publish-v2-0-0` (not before: deleting `latest` now would leave the README with no image):
delete the `pr-*` and `main` tags, consider package retention, and keep the `v0.1.x`/`v1.0.1-*` tags as
history but **marked** in the README as unsupported.

### `dependabot-backlog-prs` — 4 major Dependabot PRs open for 5 weeks, plus 2 fossils from 2023

- **status**: open
- **priority**: high
- **labels**: dependencies, github_actions
- **milestone**: Image & upstream maintenance

Opened on 2026-08-09 and never touched: `#23` login-action 3→4, `#22` setup-buildx-action 3→4,
`#21` build-push-action 6→7, `#20` metadata-action 5→6. Four **majors** on the actions that build and push:
they want reading together (one green CI across all four, not four blind merges), and `metadata-action` 6
touches exactly the tagging that has already broken once in this repository.

Fossils to close, referring to files that no longer exist: `#18` "Bump nvidia/cuda …" (`Containerfile`,
removed in v2.0.0) and `#5` "Bump sigstore/cosign-installer" (workflow removed).

Also worth doing: `groups` in `.github/dependabot.yml` (one PR for all the docker/* actions) so five PRs
do not reappear every week. `actions/checkout` is still on `v4` everywhere.

### `ffmpeg-8-and-9-variants` — Evaluate FFmpeg 8.1.x / 9.0.x in the matrix (and which one becomes default)

- **status**: done
- **priority**: medium
- **labels**: docker, upgrade
- **milestone**: Image & upstream maintenance

Every FFmpeg branch that still gets maintenance releases, with its `ffnvcodec` floor (measured from each
release's `configure` on 2026-09-17) and whether this repository ships it:

| branch | latest | `ffnvcodec >=` | needed branch | shipped here |
|---|---|---|---|---|
| 5.1 | 5.1.10 | 9.1.23.1 | `sdk/11.0` | **yes** |
| 6.0 | 6.0.1 | 12.0.16.0 | `sdk/12.0` | **yes** |
| 6.1 | 6.1.6 | 12.1.14.0 | `sdk/12.1` | no |
| 7.0 | 7.0.3 | 12.1.14.0 | `sdk/12.1` | no |
| 7.1 | 7.1.5 | 12.1.14.0 | `sdk/12.1` | **yes** (default) |
| 8.0 | 8.0.3 | 12.1.14.0 | `sdk/12.1` | no |
| 8.1 | 8.1.2 | 12.1.14.0 | `sdk/12.1` | no |
| 9.0 | 9.0.1 | 12.1.14.0 | `sdk/12.1` | no |

Two things fall out of that table:

1. **From 6.1 onwards nothing moves**: one single `sdk/12.1` covers 6.1 through 9.0, so adding 8.x or 9.x
   costs **zero** on the host's driver floor (still ≥ 530). The usual "newer version, newer driver"
   trade-off simply does not exist here.
2. **The 6.x variant is on the wrong branch**: 6.0 is superseded by **6.1**, which is the maintained 6.x
   line. Switching 6.0.1 → 6.1.6 moves that variant from `sdk/12.0` to `sdk/12.1` with the *same* ≥ 530
   floor, so it costs nothing either and gets it back onto a live branch.

To check before adding them: that the bookworm runtime package names still hold, that the `--enable-*` set
is still valid (8.x dropped a few options), and **how many variants are worth maintaining**: each matrix row
is a ~90-minute build on every tag. Likely end state: 9.0.x default, 7.1.x as the conservative choice,
6.1.6 in place of 6.0.1, 5.1.x kept for hosts on drivers ≥ 470.

Separately, on the NVENC side: `nv-codec-headers` has `sdk/12.2` and `sdk/13.0` branches (plus `n13.1.15.0`
tags) that this repository deliberately does not use — the rule is the *lowest* branch that satisfies
`configure`, because a higher one only raises the host's driver floor. That is the right default, but it
also means the newest NVENC features are not exposed; if one is ever needed, the floor for that branch has
to be checked against NVIDIA's support matrix first and documented in the README table.

> **Done on 2026-09-17** ([intervention](interventions/2026-09-17-matrix-9x.md)): the matrix is now
> **9.0.1 (default) / 7.1.5 / 6.1.6 / 5.1.10**. 9.0.1 costs no more driver than 7.1.5 did (≥ 530 both), 6.0.1
> was replaced by 6.1.6 because 6.0 is superseded inside the same major, and 8.0/8.1 were skipped on purpose:
> they sit between two shipped rows at the same driver floor, and each row is a ~90-minute build per tag.
> FFmpeg 9.0 needed **no change to the `./configure` line**. Native arm64 builds + smoke: **17/17 on all
> four** (200-205 MB). Still pending on hardware: `tests/gpu.sh` and the amd64 build in CI.

### `debian-13-trixie` — The `debian:12-slim` base is oldstable

- **status**: open
- **priority**: medium
- **labels**: docker, upgrade
- **milestone**: Image & upstream maintenance

Debian 13 (trixie) is `stable`; bookworm is **oldstable** (verified via `api.ftp-master.debian.org`,
2026-09-17). Not an emergency — bookworm has years of LTS left — but it is exactly the road along which this
repository broke in silence once: the base rots, and the Monday schedule only finds out when the APT repos
stop answering.

`DEBIAN_VERSION` is already an `ARG`, but **the package lists are not parameterised**: moving to 13 means
realigning the versioned names in the runtime stage. Verified in trixie: `libvpx7` → **`libvpx9`** (1.15.0),
`libx265-199` → **`libx265-215`** (4.1), `libx264-164` **stays** (0.164.3108). Everything else (`libass9`,
`libmp3lame0`, `libopus0`, `libspeex1`, `libtheora0`, `libvorbis0a`, `libvorbisenc2`, `libnuma1`, `libxml2`,
`libfreetype6`, `libfribidi0`, `libharfbuzz0b`, `libfontconfig1`) exists under the same name.

### `gpu-gate-before-tag` — No workflow runs `tests/gpu.sh`: publishing is blind to NVENC

- **status**: open
- **priority**: medium
- **labels**: ci, test
- **milestone**: Repository automation

`tests/smoke.sh` proves the NVENC encoders are **compiled in**; that they actually *encode* is only proven by
`tests/gpu.sh`, which no workflow calls (GitHub-hosted runners have no GPU). Promoting a tag is therefore an
act of faith about real behaviour, and the failure we would not see is the most likely one: a mismatch
between `NVCODEC_BRANCH` and the host driver (`This NVENC API is not compatible with the installed driver`).

Two routes: (a) a self-hosted runner with a GPU and the NVIDIA Container Toolkit, plus a `workflow_dispatch`
job to run before tagging; (b) stay manual but make it **mandatory** in the release checklist (see
`publish-v2-0-0`). Until (a) exists, (b) belongs in `CLAUDE.md` as a gate — it is written there now.

### `trivy-not-a-gate` — The scan runs on one variant and blocks nothing

- **status**: open
- **priority**: medium
- **labels**: ci, security
- **milestone**: Supply chain & security

The `scan` job in `ci.yml` builds only the default variant, runs Trivy with `severity: CRITICAL,HIGH` and
`ignore-unfixed: true`, and uploads SARIF to code scanning: **no `exit-code`**, so the step is green whatever
it finds. Fine as an inventory, not as a gate — and in practice nobody opens the Code scanning tab.

To decide: `exit-code: 1` on CRITICAL only (keeping `ignore-unfixed`, otherwise unpatched Debian CVEs block
everything forever) and scanning the 6.0.1/5.1.10 variants too, which are the oldest and therefore the most
exposed.

### `cosign-image-signing` — Published images are not signed

- **status**: open
- **priority**: low
- **labels**: security, supply-chain
- **milestone**: Supply chain & security

Publishing already produces `provenance: true` and `sbom: true`, but no signature: a consumer has no way to
verify an image came from this CI. With `id-token: write` (already granted in the job) keyless cosign signing
is about ten lines. Historical note: a Dependabot PR for `sigstore/cosign-installer` (`#5`, 2023) is still
open although the workflow it refers to was removed — the repository used to sign and lost it.

### `multiarch-arm64` — `linux/amd64` only

- **status**: open
- **priority**: low
- **labels**: docker
- **milestone**: Image & upstream maintenance

Build and publish are fixed on `platforms: linux/amd64`. NVENC also exists on arm64 (Jetson, Grace Hopper),
so this is not an obvious choice: it should either be **implemented** (native or emulated arm64 build, more
CI time) **or declared** unsupported in the README, with the reason. Today it is neither.

### `automation-first-run` — Verify the first real run of the backlog sync, Pages and the release workflow

- **status**: open
- **priority**: medium
- **labels**: ci, documentation
- **milestone**: Repository automation
- **ref**: [runbook: docs/scripts/README.md](scripts/README.md)

The automation (this file, `docs/scripts/`, `site/`, and the `backlog.yml` / `pages.yml` / `release.yml`
workflows) was added on 2026-09-17 but **has never run on GitHub**: the workflows only start after the push.
Everything is green locally (tests, lint, dry-run).

- [x] first `--apply` run (from a workstation, 2026-09-17): four milestones created and one issue per
      active item, `#24`-`#34`
- [x] second consecutive run: `CREATE 0 · UPDATE 0 · CLOSE 0 · SKIP 11` — idempotence proven on the real
      repository, and no open PR was mistaken for an item
- [ ] after the push, run `Backlog` from Actions (`workflow_dispatch`, `apply=false` then `apply=true`) to
      check the same thing happens with the workflow's `GITHUB_TOKEN`
- [x] GitHub Pages enabled and deployed: <https://allan-nava.github.io/Docker-FFmpeg-Nvenc/> answers 200,
      built by the `pages.yml` workflow
- [x] `Release` verified twice on the real repository: `v2.0.0` (13:10) and `v2.1.0` (13:43), both with the
      GitHub Release and **no image publish** — which is the intended split
- [ ] set `status: done` on this item once the remaining box is green

## Closed items (history)

### `ffmpeg-branch-alias-tags` — Variant tags were pinned to the exact patch, with no way to follow a branch

- **status**: done
- **priority**: medium
- **labels**: docker, release
- **milestone**: Ship v2.0.0

The only stable pointer was `:latest`, and it belongs to the default variant alone. The other variants were
reachable only as `:latest-ffmpeg7.1.5` — a tag that **disappears the moment 7.1.6 ships**, leaving whoever
pinned it with a reference that resolves to nothing until they notice. There was no way to say "the newest
7.x" without chasing patch releases by hand.

> **Done on 2026-09-17**: every variant now gets floating pointers at each level of its FFmpeg version
> (`latest-ffmpeg7`, `latest-ffmpeg7.1`, `latest-ffmpeg7.1.5`) plus one exact `X.Y.Z-ffmpeg7.1.5`; only the
> default row keeps the unsuffixed `latest`/`X.Y.Z`/`X.Y`/`X`. Combinations like `2-ffmpeg9.0.1` are left
> out on purpose: they look immutable and are not. The tag list moved out of workflow YAML into
> [`docs/scripts/image-tags.py`](scripts/image-tags.py) with 19 unit tests — including one that no two
> variants can claim the same tag, and one that a non-default variant can never take an unsuffixed tag.
> Verification on the registry is part of `publish-v2-0-0`.

### `ffmpeg-patch-bump` — Variants were pinned to old patch releases of their branch

- **status**: done
- **priority**: high
- **labels**: docker, upgrade, security
- **milestone**: Image & upstream maintenance
- **ref**: [interventions/2026-09-17-ffmpeg-patch-bump.md](interventions/2026-09-17-ffmpeg-patch-bump.md)

The default variant was pinned to FFmpeg 7.1.1 while upstream was at 7.1.5 — five maintenance releases
behind, which means the fixes (security ones included) of that branch were not in the image.

> **Done on 2026-09-17** ([intervention](interventions/2026-09-17-ffmpeg-patch-bump.md)): all three variants
> moved to the latest patch of their branch — 7.1.1 → **7.1.5**, 6.0 → **6.0.1**, 5.1.2 → **5.1.10**. The
> `sdk/*` branches stay as they were, because the `ffnvcodec` constraint does not move inside a branch
> (verified on the `configure` of n5.1.10/n6.0.1/n7.1.5), so **no consumer has to touch their drivers**.
> Native arm64 builds plus smoke tests: **17/17 on all three** (200-203 MB). Still to do on real hardware:
> `tests/gpu.sh` and the amd64 build in CI.

### `doc-drift-smoke-assertions` — The CHANGELOG said 18 smoke-test assertions; there are 17

- **status**: done
- **priority**: low
- **labels**: documentation
- **milestone**: Repository automation

> Fixed on 2026-09-17 in the `[2.0.0]` section of `CHANGELOG.md`. Real count of the assertions in
> `tests/smoke.sh`: 2 (binaries) + 1 (expected version) + 2 (NVENC) + 5 (surrounding codecs) + 2 (licence) +
> 1 (transcode) + 4 (container hygiene) = **17** — consistent with `CLAUDE.md`, `AGENTS.md` and `README.md`,
> which said 17. Kept as history: it is the kind of drift the "keep everything aligned" rule exists to catch.
> The count is now derived, not written: `site/build.py` computes it from the script and a test pins it.
