# The first publish of v2.4.0 refused by GHCR: an upper-case image name — 2026-11-19

The first run of `Publish` for `v2.4.0` ([run 44503555702](https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/actions/runs/44503555702),
`workflow_dispatch`, `version: v2.4.0`) built and tested all four variants and then failed every push
with the same error. Nothing reached GHCR. Raw log: [`logs/2026-11-19-ghcr-lowercase/`](../../logs/2026-11-19-ghcr-lowercase/).

```
   IMAGE: ghcr.io/${{ github.repository }}       github.repository keeps the owner's case
        │
        ▼
   ghcr.io/Allan-Nava/Docker-FFmpeg-Nvenc
        │  docs/scripts/image-tags.py appends the tags, unchanged
        ▼
   ghcr.io/Allan-Nava/Docker-FFmpeg-Nvenc:2.4.0-ffmpeg9.0.1
        │
        ├── Build for testing   ok   (tag ffmpeg-nvenc:candidate, lower case)
        ├── Smoke test          ok   (all four variants)
        └── Build and push      FAIL invalid tag "...": repository name must be lowercase

   fixed:   image-tags.py lowercases the image        (the tool, unit-tested)
            the workflow lowercases IMAGE too ${IMAGE,,}   (old tags carry the old tool)
```

## Why it never showed before

Every earlier image on GHCR (up to `v1.0.1`, 2023) was published by `docker/metadata-action`, which
lowercases the image name itself. `image-tags.py` replaced it for v2.0.0 and builds the name verbatim,
and no v2 image had been published until this run (see the delivery status in `CLAUDE.md`), so the
first push was the first time the name met the registry.

## The fix, in two places

- **`docs/scripts/image-tags.py`** lowercases the image in `tags_for()`; `tests/test_image_tags.py` has
  two tests for it (an upper-case image comes out lower case; the tag part is untouched).
- **`.github/workflows/docker-publish.yml`** lowercases `IMAGE` before calling the script. The publish
  checks out the tag it publishes and runs *that tag's* script, so without this a tag cut before the fix
  (`v2.4.0` and earlier) could never be published. The workflow itself always comes from `main`.

## State after it

- The four variants of `v2.4.0` compiled and passed the smoke test: the images are good, only the push
  failed, and the build cache of each variant is warm for the next run.
- To publish: run `Publish` again with `version: v2.4.0` (the workflow on `main` now lowercases), or with
  the release this fix becomes.
