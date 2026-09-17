# docs/scripts — tooling del backlog

Tre script + una libreria condivisa. Nessuna dipendenza esterna: **solo stdlib Python 3**
(gli `ubuntu-latest` di Actions hanno `python3` preinstallato, non serve `setup-python`).

```
  docs/backlog.md ─────────┐
                           │  lib/backlog.py   (parsing + regole di lint: FONTE UNICA)
                           ▼
      ┌────────────────────┴─────────────────────┬──────────────────────────┐
      │                                          │                          │
  backlog-lint.py                      generate-roadmap.py         sync-backlog-to-issues.py
  (valida: id, status,                 (scrive docs/roadmap.md,    (API GitHub: issue +
   priority, chiavi meta,               --check in CI)              milestone, idempotente)
   milestone coerenti)                          │                          │
      │                                          ▼                          ▼
      └──────────── gate `lint` ──────────▶ docs/roadmap.md         Issues + Milestone
                    (.github/workflows/backlog.yml)                  (label backlog-sync)
```

## Uso locale

```shell
python3 docs/scripts/backlog-lint.py              # exit 1 se il backlog e malformato
python3 docs/scripts/backlog-lint.py --strict      # anche i warning bloccano
python3 docs/scripts/generate-roadmap.py           # rigenera docs/roadmap.md (da COMMITTARE)
python3 docs/scripts/generate-roadmap.py --check   # come la CI: exit 1 se diverge
python3 docs/scripts/sync-backlog-to-issues.py     # dry-run (default). Senza token: piano offline
GITHUB_TOKEN=... python3 docs/scripts/sync-backlog-to-issues.py          # dry-run CONFRONTATO col repo
GITHUB_TOKEN=... python3 docs/scripts/sync-backlog-to-issues.py --apply  # scrive davvero
```

Token locale: uno PAT con scope `issues: write` sul repo, oppure `--token-file <path>`.
`gh auth token` va bene per i dry-run.

## Regole che non sono ovvie dal codice

- **Il backlog comanda, non la UI.** Un item `status: open` la cui issue e stata chiusa a mano
  viene **riaperto** al sync successivo (con un commento che lo spiega). Per chiudere davvero:
  `status: done` sull'item.
- **`id` immutabile.** Il match issue↔item e il fingerprint `<!-- backlog-id: … -->` nel corpo:
  cambiare l'`id` non rinomina la issue, ne crea una nuova e chiude la vecchia.
- **GitHub sostituisce il set di label su `PATCH`**: lo script fa l'**unione** con quelle presenti,
  cosi le label messe a mano sopravvivono. Le label mancanti nel repo vengono create da GitHub
  al primo uso.
- **`/issues` include le pull request**: sono filtrate (`pull_request` nella risposta). Senza quel
  filtro una PR con la label `backlog-sync` verrebbe letta come item fantasma e chiusa.
- **Le milestone si creano da sole**, cercate per **titolo esatto**. Un titolo scritto con case o
  spazi diversi crea una *seconda* milestone: per questo `backlog-lint` avvisa sulle varianti.
- **`docs/roadmap.md` e generata e committata**: se cambi `backlog.md` e non la rigeneri, il gate
  `generated-pages` va rosso.
