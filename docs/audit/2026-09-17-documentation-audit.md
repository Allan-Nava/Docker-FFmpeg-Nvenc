# Documentation audit — Docker-FFmpeg-Nvenc (2026-09-17, evening)

Audit of **every document in the repository** against what the repository actually does, after a day in
which the matrix changed twice, two releases shipped, the backlog became issues, the page went live and the
tag scheme was rewritten. Docs that describe a fast-moving day are exactly the docs that end up lying.

Scope: `README.md`, `CLAUDE.md`, `AGENTS.md`, `CHANGELOG.md`, `docs/backlog.md`, `docs/roadmap.md`
(generated), `docs/scripts/README.md`, both audits, both intervention notes, and the comments that act as
documentation in `Dockerfile`, `action.yml` and the workflows. `logs/` is evidence and is left untouched.

```
   claim in a doc                     reality                          verdict
   ──────────────                     ───────                          ───────
   "v2.0.0 has never been tagged"  ─▶ v2.0.0 AND v2.1.0 released   ──▶ D1  fixed
   "tags not published yet"        ─▶ true for images only          ──▶ D2  reworded
   "Four scripts and one library"  ─▶ 8 scripts, 2 libraries        ──▶ D3  fixed
   "tagging uses metadata-action"  ─▶ image-tags.py since today     ──▶ D4  fixed
   audit of this morning           ─▶ half of it already actioned   ──▶ D5  status note
   backlog checklists              ─▶ three boxes already true      ──▶ D6  ticked
   entries under `## [2.1.0]`      ─▶ added AFTER the tag           ──▶ D7  moved out
   relative links after renames    ─▶ all resolve                   ──▶ ok
   README table vs publish matrix  ─▶ agree                         ──▶ ok
```

## What was verified, and how

Not by reading: by asking the systems. `gh release list`, `gh run list`, `gh api …/pages`, a `curl` against
the published page, the GHCR tag list through the registry API, `git tag`, and the workflow matrix parsed by
`site/build.py --print-variants`.

| question | answer (2026-09-17, evening) |
|---|---|
| releases | `v2.1.0` (13:43), `v2.0.0` (13:10) |
| workflow runs | CI, Release, Backlog green; the 13:38 Release/Pages failure was the bad test, fixed in v2.1.0 |
| project page | `https://allan-nava.github.io/Docker-FFmpeg-Nvenc/` → **HTTP 200**, built by `pages.yml` |
| images on GHCR | `latest`, `main`, `pr-2…5`, `v0.1.x`, `v1.0.1-*` — **all from 2023**, nothing new |
| issues | 11 created, 1 closed by the sync (`#28`) |
| published matrix | 9.0.1 (default), 7.1.5, 6.1.6, 5.1.10 |

The one that matters: **released ≠ published**. Two GitHub Releases exist and not a single new image byte is
on the registry, because `Publish` has never run. Any sentence that blurs the two is a sentence that sends
someone to pull the 2023 image.

## Findings

| # | Drift | Where | Fix |
|---|---|---|---|
| D1 | "v2.0.0 has never been tagged … until the tag exists" — false since 13:10 | `CLAUDE.md`, `AGENTS.md` | Delivery-status block rewritten: released, **not** published, with the reason the two differ |
| D2 | "the tags below have not been published yet … published with the first `v2.0.0` tag" — the tag now exists | `README.md` | Reworded: releasing and publishing are separate acts; `:latest` on GHCR is still the 2023 build |
| D3 | "Four scripts and one shared library"; `image-tags.py` missing entirely | `docs/scripts/README.md` | Rewritten with a table of all ten files and what each one *decides*, plus the tagging flow in the diagram |
| D4 | "Workflow tagging uses `docker/metadata-action`" — replaced today by `image-tags.py` | `CLAUDE.md`, `AGENTS.md` | Trap rewritten around the generated tag list and the invariants its tests pin |
| D5 | The morning audit reads as current, but half of it has been actioned | `docs/audit/2026-09-17-state-and-automation-audit.md` | Status note at the top, pointing here; F1 marked half-closed |
| D6 | Checklists listed as pending things already verified (Pages live, Release twice, v2.0.0 released); "all three variants" after the matrix went to four | `docs/backlog.md` | Boxes ticked with what was verified and when; count corrected |
| D7 | Two entries landed **inside the released `## [2.1.0]` section** — a rebase merged them there, so the changelog claimed a released version contained work that came after its tag | `CHANGELOG.md` | Moved into a fresh `## [Unreleased]`; `[2.1.0]` left with only what it shipped |

D7 is the interesting one. Everything else is ordinary rot; D7 is a *mechanism*: `git rebase` has no idea
that `## [2.1.0]` is immutable once `v2.1.0` exists, and it merged cleanly into it without a conflict. There
was nothing to notice — no test, no lint, no red build.

## What this audit added rather than just fixed

Three of the four drifts above are mechanical and therefore testable, so `tests/test_docs.py` now pins them:

- **every relative link in every `.md` resolves** — the audits and the intervention note were renamed twice
  today (Italian → English), and a broken link survives a rename in silence;
- **`CLAUDE.md` and `AGENTS.md` keep the same sections**, and `AGENTS.md` stays pure ASCII, which is its
  reason to exist;
- **`docs/scripts/README.md` lists every script and no script that does not exist** — D3 in test form;
- **the README variant table matches the publish matrix**, versions, `sdk/*` branches and driver floors
  included, read from the workflow rather than retyped;
- **no document claims the release is untagged while a `v2.*` tag exists** — D1 in test form, skipped on a
  shallow clone where the tags are not fetched.

Both failing tests were written before the fixes and failed for the right reasons (`image-tags.py` missing
from the runbook; `CLAUDE.md` still claiming an untagged release). The other five passed immediately — which
is the point: they are there for the next rename, not for this one.

## What is deliberately left alone

- **`logs/`** — raw command output attached to the other documents. It is evidence: if it were edited to
  match today's reality it would stop being evidence.
- **Released CHANGELOG sections** — `[2.0.0]` still says "v2.0.0 was never tagged" in the audit entry,
  because that is what was true when the section shipped. Rewriting history in a released section is exactly
  the mistake D7 made by accident.
- **The morning audit's body** — annotated at the top, not edited in place, same as the 2026-08-09 one.
- **`docs/interventions/*`** — they describe a change at a moment; both remain accurate about their own.

## Remaining, tracked elsewhere

`publish-v2-0-0` (the images), `action-ref-and-image-input` (the Action still pins `:latest` and documents a
`@v2` that now *does* exist but points at code, not at a published image), `ghcr-tag-hygiene`,
`automation-first-run` (one box left: the sync run under the workflow's own token).
