# Roadmap — milestone del backlog

<!-- GENERATO da docs/scripts/generate-roadmap.py — NON editare a mano. -->
> Pagina **generata** da [`docs/scripts/generate-roadmap.py`](scripts/generate-roadmap.py) leggendo [`docs/backlog.md`](backlog.md) (unica sorgente). Affianca le [milestone GitHub](https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/milestones), create e popolate dal sync.

_4 milestone · 13 item pianificati (12 open · 1 done)._

## Automazione repo

_2 open · 1 done_

| id | Titolo | Priorita | Status |
|----|--------|----------|--------|
| `backlog-sync-primo-run` | Verificare il primo run reale del sync backlog → issue | medium | open |
| `gpu-gate-prima-del-tag` | `tests/gpu.sh` non e invocato da nessun workflow: il publish e cieco su NVENC | medium | open |
| `doc-drift-asserzioni-smoke` | `CHANGELOG` diceva 18 asserzioni di smoke test, sono 17 | low | done |

## Manutenzione immagine & upstream

_5 open · 0 done_

| id | Titolo | Priorita | Status |
|----|--------|----------|--------|
| `dependabot-pr-arretrate` | 4 PR dependabot major aperte da 5 settimane + 2 PR fossili del 2023 | high | open |
| `ffmpeg-bump-7-1-5` | La variante default e ferma a FFmpeg 7.1.1, upstream e a 7.1.5 | high | open |
| `debian-13-trixie` | La base `debian:12-slim` e oldstable | medium | open |
| `ffmpeg-8-e-9-varianti` | Valutare FFmpeg 8.1.x / 9.0.x nella matrice (e quale diventa default) | medium | open |
| `multiarch-arm64` | Solo `linux/amd64` | low | open |

## Pubblicazione v2.0.0

_3 open · 0 done_

| id | Titolo | Priorita | Status |
|----|--------|----------|--------|
| `action-ref-e-input-image` | La Action pubblica punta a `:latest` mobile, `@v2` non esiste e `inputs.image` e codice morto | high | open |
| `tag-v2-0-0` | Tutta la riparazione v2.0.0 e su main ma NON pubblicata: su GHCR `:latest` e l'immagine del 2023 | high | open |
| `ghcr-tag-igiene` | Sul registry restano `main`, `pr-2`…`pr-5` e le immagini v0.1.x del 2023 | medium | open |

## Supply chain & sicurezza

_2 open · 0 done_

| id | Titolo | Priorita | Status |
|----|--------|----------|--------|
| `trivy-non-e-un-gate` | Lo scan gira su una sola variante e non blocca nulla | medium | open |
| `cosign-firma-immagini` | Le immagini pubblicate non sono firmate | low | open |

## Non pianificati (senza milestone)

_0 item open senza milestone. Assegnane una con `- **milestone**: <titolo>` in [`backlog.md`](backlog.md)._
