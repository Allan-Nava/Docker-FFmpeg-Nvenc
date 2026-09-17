# docs/scripts — backlog, changelog, release and tagging tooling

Six scripts, two shell helpers and two shared libraries. No external dependencies: **Python 3 stdlib
only** (the `ubuntu-latest` runners ship `python3`, so no `setup-python` step is needed).

| file | what it decides |
|---|---|
| `lib/backlog.py` | how a backlog item is parsed and validated |
| `lib/changelog.py` | what a valid commit subject is, and which CHANGELOG section it belongs to |
| `backlog-lint.py` | whether `docs/backlog.md` is well formed (CI gate) |
| `generate-roadmap.py` | `docs/roadmap.md` from the backlog milestones |
| `sync-backlog-to-issues.py` | the GitHub issues and milestones |
| `changelog-add.py` | where a new entry lands under `## [Unreleased]` |
| `next-version.py` | which version the next release gets |
| `image-tags.py` | which tags and OCI labels a published image gets |
| `commit.sh` | subject + entry + local gates + commit, in one command |
| `install-hooks.sh` | points git at `.githooks/` |

```
  docs/backlog.md ─────────┐
                           │  lib/backlog.py   (parsing + lint rules: SINGLE SOURCE)
                           ▼
      ┌────────────────────┴─────────────────────┬──────────────────────────┐
      │                                          │                          │
  backlog-lint.py                      generate-roadmap.py         sync-backlog-to-issues.py
  (ids, status, priority,              (writes docs/roadmap.md,    (GitHub API: issues +
   meta keys, repeated keys,            --check in CI)              milestones, idempotent)
   milestone consistency)                       │                          │
      │                                          ▼                          ▼
      └──────────── `lint` gate ──────────▶ docs/roadmap.md         Issues + Milestones
                    (.github/workflows/backlog.yml)                  (label backlog-sync)

  commit subject ──▶ lib/changelog.py ──▶ changelog-add.py ──▶ `## [Unreleased]` ▸ `### <section>`
       │                    ▲                  (commit.sh does subject + entry + gates + commit)
       │                    │
       └──▶ .githooks/commit-msg  and  the commit-lint job in ci.yml (same rule, one source)

  CHANGELOG.md + git tags ──▶ next-version.py ──▶ version, CHANGELOG section, release notes
                                                  (.github/workflows/release.yml; falls back to
                                                   changelog-add.py --from-commits if nobody wrote
                                                   any entry)

  release + matrix row ──▶ image-tags.py ──▶ tags and OCI labels for one published image
                                             (.github/workflows/docker-publish.yml)
```

## Local usage

```shell
python3 docs/scripts/backlog-lint.py              # exit 1 if the backlog is malformed
python3 docs/scripts/backlog-lint.py --strict      # warnings block too
python3 docs/scripts/generate-roadmap.py           # regenerate docs/roadmap.md (COMMIT it)
python3 docs/scripts/generate-roadmap.py --check   # as CI does: exit 1 if it diverged
python3 docs/scripts/sync-backlog-to-issues.py     # dry-run (default). No token: offline plan
GITHUB_TOKEN=... python3 docs/scripts/sync-backlog-to-issues.py          # dry-run COMPARED with the repo
GITHUB_TOKEN=... python3 docs/scripts/sync-backlog-to-issues.py --apply  # actually writes
python3 docs/scripts/next-version.py --explain     # the version the next release would get, and why
python3 docs/scripts/image-tags.py --image ghcr.io/o/n --release v2.1.0 --ffmpeg 9.0.1 --default
python3 docs/scripts/changelog-add.py --message "fix: x"          # file an entry under [Unreleased]
python3 docs/scripts/changelog-add.py --message "fix: x" --entry "the sentence you want there"
python3 docs/scripts/changelog-add.py --from-commits              # draft from commits (release fallback)
./docs/scripts/install-hooks.sh                                   # enable .githooks/commit-msg
./docs/scripts/commit.sh "feat: thing" --entry "what it means"     # subject + entry + gates + commit
```

Local token: a PAT with `issues: write` on the repository, or `--token-file <path>`. `gh auth token`
is fine for dry-runs.

Tests: `python3 -m unittest discover -s tests -p 'test_*.py'` (`tests/test_backlog.py`,
`tests/test_release.py`). Every rule below is pinned by a test — that is the point of them.

## Rules that are not obvious from the code

- **The backlog decides, not the UI.** An item with `status: open` whose issue was closed by hand is
  **reopened** on the next sync (with a comment saying so). To close it for real: `status: done`.
- **`id` is immutable.** The issue↔item match is the `<!-- backlog-id: … -->` fingerprint in the body:
  changing the `id` does not rename the issue, it creates a new one and closes the old one.
- **GitHub replaces the label set on `PATCH`**: the script unions it with what is already there, so
  labels added by hand survive. Labels missing from the repository are created by GitHub on first use.
- **`/issues` includes pull requests**: they are filtered out (the `pull_request` key in the response).
  Without that filter, a PR carrying the `backlog-sync` label would be read as a phantom item and
  closed — with six PRs open in this repository, that would have happened on the first run.
- **Milestones are created automatically**, looked up by **exact title**. A title spelled with
  different case or spacing creates a *second* milestone — which is why `backlog-lint` warns about
  variants.
- **`docs/roadmap.md` is generated and committed**: change `backlog.md` without regenerating it and the
  `generated-pages` gate goes red.
- **The conventional-commit rule has one home**: `lib/changelog.py`. The hook, the CI job,
  `changelog-add.py` and `next-version.py` import it. Unknown types are rejected rather than treated as a
  `patch` bump, so a typo fails loudly instead of quietly shipping the wrong version.
- **The automation chooses the section, not the words.** `feat:` goes to *Added*, `fix:` to *Fixed*,
  `security:` to *Security*, `remove:`/`revert:` to *Removed*, everything else to *Changed*. What the
  bullet says is still yours to write (`--entry`), and the `--from-commits` draft exists only so a release
  nobody documented still ships a readable list.
- **Tags are computed, not templated.** `image-tags.py` gives every variant floating pointers at each level
  of its FFmpeg version (`latest-ffmpeg7`, `latest-ffmpeg7.1`, `latest-ffmpeg7.1.5`) plus one exact
  `<release>-ffmpeg<full>`; only the default row takes the unsuffixed tags. Two unit tests guard the
  invariants that actually bite: no two variants may claim the same tag, and a non-default variant may never
  take an unsuffixed one.
- **Releasing does not publish images.** `next-version.py` decides the version, `release.yml` tags it
  with the `GITHUB_TOKEN` — which by design does not trigger other workflows — so `docker-publish.yml`
  stays an explicit act. A CHANGELOG section numbered above the latest tag is treated as a *pending
  release* and tagged as-is: that is how the never-shipped `[2.0.0]` gets out of the door.
