# docs/scripts — backlog and release tooling

Four scripts and one shared library. No external dependencies: **Python 3 stdlib only** (the
`ubuntu-latest` runners ship `python3`, so no `setup-python` step is needed).

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

  CHANGELOG.md + git tags ──▶ next-version.py ──▶ version, CHANGELOG section, release notes
                                                  (.github/workflows/release.yml)
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
- **Releasing does not publish images.** `next-version.py` decides the version, `release.yml` tags it
  with the `GITHUB_TOKEN` — which by design does not trigger other workflows — so `docker-publish.yml`
  stays an explicit act. A CHANGELOG section numbered above the latest tag is treated as a *pending
  release* and tagged as-is: that is how the never-shipped `[2.0.0]` gets out of the door.
