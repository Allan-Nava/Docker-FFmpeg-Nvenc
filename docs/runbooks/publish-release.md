# Runbook — publishing a release to GHCR

Releasing and publishing are two separate acts in this repository. `release.yml` tags every commit on main
and writes the GitHub Release; **no image is pushed**. This runbook is the other half: getting those images
onto the registry, and proving they are the right ones.

```
  commit on main ──▶ release.yml ──▶ tag vX.Y.Z + GitHub Release        (automatic, no images)
                                          │
                                          ▼
                              [ you decide to publish ]
                                          │
        ┌─────────────────────────────────┼─────────────────────────────────┐
        ▼                                 ▼                                 ▼
   ./tests/gpu.sh              gh workflow run Publish            ./tests/verify-registry.sh
   (NVIDIA host, manual)       (4 builds, ~90 min each)           (tags + digests on GHCR)
```

## Before

1. **The tag must contain what you think it contains.** `git log --oneline -1 vX.Y.Z` — the publish workflow
   checks out that ref, not `main`.
2. **Run the GPU gate.** No GitHub-hosted runner has a GPU, so this is the only proof that NVENC *encodes*
   rather than merely being compiled in, and the only thing that catches a driver/`NVCODEC_BRANCH` mismatch:

   ```shell
   git checkout vX.Y.Z
   ./tests/build-matrix.sh            # builds the four variants locally
   ./tests/gpu.sh ffmpeg-nvenc:test-9.0.1
   ./tests/gpu.sh ffmpeg-nvenc:test-7.1.5
   ./tests/gpu.sh ffmpeg-nvenc:test-6.1.6
   ./tests/gpu.sh ffmpeg-nvenc:test-5.1.10
   ```

   On a host without an NVIDIA GPU `gpu.sh` exits 0 with `SKIP` — that is not a pass, it is an absence.

## Publish

```shell
gh workflow run docker-publish.yml -f version=vX.Y.Z
gh run watch "$(gh run list --workflow=docker-publish.yml -L1 --json databaseId --jq '.[0].databaseId')"
```

Four variants build in parallel, each one smoke-tested **before** its push: a variant that fails its 17
assertions is never pushed, and the other three still are.

## After — verify, do not assume

```shell
./tests/verify-registry.sh vX.Y.Z
```

It generates the expected tag list from the publish matrix and `docs/scripts/image-tags.py` (the same code
the workflow uses), compares it with what GHCR actually serves, and — the part that matters — checks **by
digest** that every floating alias points at the same image as its exact tag.

Why by digest: `:latest` has existed on this registry since 2023 while pointing at an image that cannot start
on a modern driver. A check that only asks "does the tag exist?" would have called that a pass for two years.

Expected on success, for each variant: `latest-ffmpeg<major>`, `latest-ffmpeg<major>.<minor>`,
`latest-ffmpeg<full>`, `<version>-ffmpeg<full>`; plus `latest`, `<version>`, `<major>.<minor>`, `<major>` for
the default variant only.

Then check the image itself is the new one:

```shell
docker pull ghcr.io/allan-nava/docker-ffmpeg-nvenc:latest
docker image inspect ghcr.io/allan-nava/docker-ffmpeg-nvenc:latest \
  --format '{{.Config.User}} {{.Config.Entrypoint}} {{index .Config.Labels "org.opencontainers.image.version"}}'
# expected: ffmpeg [ffmpeg] X.Y.Z     ← not empty, not /bin/bash, not v0.1.2
```

## If something is wrong

- **A variant failed its smoke test**: nothing of it was pushed; the other variants went out. Fix, release
  again, publish the new tag. Do not re-run the same tag hoping for a different build.
- **A tag is missing on GHCR**: read the `Publish` summary — it prints the exact tag list the generator
  produced for each variant. If the list is wrong, the bug is in `docs/scripts/image-tags.py` and there is a
  test to add; if the list is right but the registry disagrees, the push failed and the run log says why.
- **`:latest` points at the wrong digest**: the default row in the matrix is not the one you think it is
  (`default: true` in `docker-publish.yml`). Only one row may carry it — a unit test enforces that.
- **Rolling back** means publishing an older tag again, not deleting: deleting a published tag breaks
  everyone who pinned it. Registry cleanup is a separate, deliberate act (backlog: `ghcr-tag-hygiene`).

## After the first successful publish

Update, in the same commit:

- `README.md` — remove the "released, not yet published" notice;
- `CLAUDE.md` / `AGENTS.md` — the delivery-status block;
- `action.yml` — pin `runs.image` to the published version (backlog: `action-ref-and-image-input`);
- `docs/backlog.md` — tick `publish-v2-0-0`, then regenerate the roadmap and the page.

`tests/test_docs.py` fails if the first two are forgotten once a `v2.*` tag exists.
