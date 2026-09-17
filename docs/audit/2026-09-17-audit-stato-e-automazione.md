# Audit dello stato del repo e introduzione del backlog automatizzato — Docker-FFmpeg-Nvenc (2026-09-17)

Audit del repository `github.com/Allan-Nava/Docker-FFmpeg-Nvenc` allo stato del commit `62357b5`
(branch `main`, working tree pulito, allineato con `origin/main`), piu introduzione del tooling di
backlog → issue/milestone GitHub.

Segue l'[audit iniziale del 2026-08-09](2026-08-09-audit-iniziale.md), che fotografava un repo in cui
**nessuna delle immagini pubblicate era piu costruibile** e che si e chiuso con la riparazione
descritta nella sezione `[2.0.0]` del `CHANGELOG.md`.

> **Esito in una riga: la riparazione funziona ma non e mai arrivata a destinazione.** La CI builda e
> testa le tre varianti ogni lunedi e passa; il tag `v2.0.0` non e mai stato creato, quindi su GHCR
> `:latest` e ancora **l'immagine del 16 gennaio 2023** — root, `ENTRYPOINT /bin/bash`, single-stage e
> con un `NVIDIA_REQUIRE_CUDA` che ne impedisce l'avvio su qualunque host con driver recente.

Tutte le verifiche di questo audit sono **misurate**, non dedotte: registry GHCR interrogato via API,
release upstream lette da `ffmpeg.org`, vincoli `ffnvcodec` estratti dal `configure` di ogni release,
pacchetti Debian verificati su `api.ftp-master.debian.org`, stato PR/run letti con `gh`. Log integrali
in [`logs/2026-09-17-audit/`](../../logs/2026-09-17-audit/). **Nessuna `docker build` e stata lanciata
in questo audit**: sul funzionamento della build parla lo schedule settimanale della CI, verde
l'ultima volta il 2026-09-14.

## 1. Schema: dove si rompe la catena

```
   repo (main, 62357b5)                                 registry GHCR
   ────────────────────                                 ─────────────
   Dockerfile parametrizzato          ┌───────────────┐
   tests/smoke.sh  (17 asserzioni)    │ ci.yml        │  push/PR + lunedi 04:17
   tests/gpu.sh    (mai invocato) ✗   │ lint+build+   │  ─── VERDE il 14/09/2026
                                      │ test+trivy    │      (nessun artefatto pubblicato:
                                      └───────────────┘       `load: true`, niente push)
                                              │
                                              │
   CHANGELOG.md  [2.0.0] - 2026-08-09         │        ┌──────────────────────────────┐
                                              │        │ docker-publish.yml           │
   git tag:  v1.0.1  v1.0.0  v0.1.2 …         │        │ on: push tags v*             │
             └── NESSUN v2.0.0  ✗ ────────────┼───✗───▶│ build→smoke→push GHCR        │
                     (mai creato)             │        └──────────────────────────────┘
                                              │                    │ mai eseguito dal 2023
                                              ▼                    ▼
   README.md  →  :latest ─────────────────────────────────▶  :latest = manifest 2023-01-16
   action.yml →  docker://…:latest ───────────────────────▶  v0.1.2 · root · /bin/bash
   README.md  →  uses: …@v2  ✗ (ref inesistente)             NVIDIA_REQUIRE_CUDA driver<471
                                                             → non parte su driver 535/550/570
   tag residui sul registry: main, pr-2, pr-3, pr-4, pr-5, v0.1.1, v0.1.2,
                             v1.0.1-ffmpeg5.1.2, v1.0.1-ffmpeg6.0
                             (pubblicati da workflow che non esistono piu)
```

Il punto di rottura non e tecnico ma **di processo**: l'unico atto che pubblica (`git tag` + push del
tag) e l'unico che in questo repo non e automatizzabile per scelta — il push lo fa l'utente. Dal
09/08/2026 il repo e quindi in uno stato stabile e silenzioso: CI verde, artefatto pubblico rotto.

## 2. Verifiche eseguite (evidenze)

### 2.1 Che cosa e davvero pubblicato su GHCR

`GET /v2/allan-nava/docker-ffmpeg-nvenc/tags/list` (log `ghcr-tags-e-manifest.log`):

```
main, pr-2, pr-3, pr-4, pr-5, v0.1.1, v0.1.2, latest, v1.0.1-ffmpeg5.1.2, v1.0.1-ffmpeg6.0
```

Config blob del tag `:latest`:

| campo | valore letto |
|---|---|
| `created` | `2023-01-16T16:52:50Z` |
| `org.opencontainers.image.version` | `v0.1.2` |
| `User` | *(vuoto → root)* |
| `Entrypoint` | `["/bin/bash"]` |
| layer | 10 (nessun multi-stage) |
| `NVIDIA_REQUIRE_CUDA` | `cuda>=11.5 brand=tesla,driver>=470,driver<471 …` |
| `NVIDIA_DRIVER_CAPABILITIES` | `compute,utility,video` |

L'ultima riga e la piu severa: con `NVIDIA_REQUIRE_CUDA` che ammette solo `driver>=470,<471`, il
NVIDIA Container Toolkit **rifiuta di avviare il container** su un host con driver 535/550/570
(`requirement error: unsatisfied condition`). L'immagine che il README dice di scaricare non e
"vecchia": e inavviabile sull'hardware corrente.

Il tag `main` (creato 2023-01-19) e della stessa famiglia. Nessun tag `v2.*` esiste sul registry.

### 2.2 Stato Git/GitHub

`git tag` → `v1.0.1, v1.0.0, v0.1.2, v0.1.1, v0.1.0`. `gh release list` → ultima release `v1.0.1`,
**16/05/2023**. `main` e allineato a `origin/main` (0/0): il codice della v2.0.0 e pushato, manca solo
il tag.

`gh run list` → gli unici run recenti sono lo **schedule settimanale di `ci.yml`** (14/09, 07/09,
31/08, 24/08, 17/08, 10/08: tutti `success`) e il job Dependabot. `docker-publish.yml` non risulta
mai eseguito.

`gh pr list` → **6 PR aperte, 0 issue**:

| PR | data | oggetto | nota |
|---|---|---|---|
| #23 | 09/08/2026 | `docker/login-action` 3→4 | major, ferma da 5 settimane |
| #22 | 09/08/2026 | `docker/setup-buildx-action` 3→4 | major |
| #21 | 09/08/2026 | `docker/build-push-action` 6→7 | major |
| #20 | 09/08/2026 | `docker/metadata-action` 5→6 | major, tocca il tagging **gia rotto una volta** |
| #18 | 13/03/2023 | `nvidia/cuda` base bump | fossile: riguarda `Containerfile`, rimosso in v2.0.0 |
| #5 | 16/01/2023 | `sigstore/cosign-installer` | fossile: il workflow di firma non esiste piu |

### 2.3 Upstream FFmpeg e vincolo `ffnvcodec`

Release presenti su `ffmpeg.org/releases` (coda): `7.1.3, 7.1.4, 7.1.5, 8.0.x, 8.1, 8.1.1, 8.1.2,
9.0, 9.0.1`. Il repo pinna `7.1.1`, `6.0`, `5.1.2`.

`grep 'ffnvcodec >=' configure` per release (log `upstream-ffmpeg-nvcodec.log`):

```
  n5.1.2 → ffnvcodec >= 9.1.23.1      (matrice: sdk/11.0 → driver ≥ 470)
  n6.0   → ffnvcodec >= 12.0.16.0     (matrice: sdk/12.0 → driver ≥ 530)
  n7.1.1 → ffnvcodec >= 12.1.14.0     (matrice: sdk/12.1 → driver ≥ 530)
  n7.1.5 → ffnvcodec >= 12.1.14.0     ── identico
  n8.1.2 → ffnvcodec >= 12.1.14.0     ── identico
  n9.0.1 → ffnvcodec >= 12.1.14.0     ── identico
```

Conseguenza operativa, controintuitiva e utile: **salire a 7.1.5, 8.1.x o perfino 9.0.x non alza il
driver NVIDIA minimo dell'host**, perche il requisito `ffnvcodec` e fermo a 12.1.14.0 dal ramo 7.1.
`sdk/12.1` copre tutto; `sdk/12.2` e `sdk/13.0` esistono ma non servono, e alzerebbero solo il
requisito lato host. Il bump di patch (7.1.1 → 7.1.5) e quindi il cambiamento a rischio piu basso e
valore piu alto della lista.

### 2.4 Base image e pacchetti

`madison` su `bookworm,trixie` (log `debian-pacchetti-bookworm-trixie.log`): bookworm risponde
`oldstable`, trixie `stable`. Per un'eventuale `DEBIAN_VERSION=13` i nomi versionati dello stage
runtime da riallineare sono esattamente tre:

```
  libvpx7      1.12.0  (oldstable)  →  libvpx9      1.15.0  (stable)
  libx265-199  3.5     (oldstable)  →  libx265-215  4.1     (stable)
  libx264-164  ————————— presente in ENTRAMBE (0.164.3095 → 0.164.3108) —————————
```

Tutti gli altri pacchetti runtime (`libass9`, `libfontconfig1`, `libfreetype6`, `libfribidi0`,
`libharfbuzz0b`, `libmp3lame0`, `libnuma1`, `libopus0`, `libspeex1`, `libtheora0`, `libvorbis0a`,
`libvorbisenc2`, `libxml2`) esistono in trixie con lo stesso nome. Nessuna urgenza — bookworm ha
supporto a lungo termine — ma e il vettore di rottura silenziosa noto di questo repo.

### 2.5 Coerenza interna della documentazione

Un solo disallineamento trovato, minore ma indicativo: la sezione `[2.0.0]` del `CHANGELOG.md`
dichiarava **18** asserzioni di `tests/smoke.sh`, mentre `CLAUDE.md`, `AGENTS.md` e il test stesso ne
contano **17** (2 binari + 1 versione attesa + 2 NVENC + 5 codec + 2 licenza + 1 transcodifica +
4 igiene container). Corretto in questo intervento.

## 3. Findings

| # | Finding | Gravita | Item di backlog |
|---|---|---|---|
| F1 | `v2.0.0` mai taggata: su GHCR `:latest` e l'immagine del 2023, inavviabile su driver recenti | **bloccante** | `tag-v2-0-0` |
| F2 | `action.yml` pinna `:latest` mobile, il README documenta `@v2` inesistente, `inputs.image` e codice morto | **alta** | `action-ref-e-input-image` |
| F3 | FFmpeg default fermo a 7.1.1 con 7.1.5 disponibile a driver invariato | alta | `ffmpeg-bump-7-1-5` |
| F4 | 4 PR dependabot major ferme da 5 settimane + 2 PR fossili su file rimossi | alta | `dependabot-pr-arretrate` |
| F5 | Tag residui `main`/`pr-*`/v0.1.x pubblici sul registry, nessuna retention | media | `ghcr-tag-igiene` |
| F6 | `tests/gpu.sh` non invocato da alcun workflow: la promozione di un tag e cieca su NVENC | media | `gpu-gate-prima-del-tag` |
| F7 | Trivy gira su una sola variante e non blocca (nessun `exit-code`) | media | `trivy-non-e-un-gate` |
| F8 | Matrice ferma a 7.1.x: 8.1.x/9.0.x non valutate (a costo-driver zero) | media | `ffmpeg-8-e-9-varianti` |
| F9 | Base `debian:12-slim` e oldstable; liste pacchetti non parametriche su `DEBIAN_VERSION` | media | `debian-13-trixie` |
| F10 | Immagini non firmate (provenance/SBOM si, cosign no — il repo la firma l'aveva) | bassa | `cosign-firma-immagini` |
| F11 | Solo `linux/amd64`, ne implementato arm64 ne dichiarato non supportato | bassa | `multiarch-arm64` |
| F12 | Nessun canale per i todo: 0 issue, nessun backlog, nessuna milestone | media | *risolto qui* |
| F13 | `CHANGELOG` diceva 18 asserzioni di smoke test, sono 17 | bassa | `doc-drift-asserzioni-smoke` (done) |

Cosa questo audit **non** ha trovato, e vale dirlo: il `Dockerfile`, i test e i due workflow
introdotti in v2.0.0 reggono. Le tre varianti buildano e passano 17/17 ogni lunedi, i gate NVENC
interni al Dockerfile ci sono, `--enable-nonfree` e assente con un'asserzione dedicata, il container
gira non-root con capability ristrette e il multi-stage e effettivo (nessun compilatore, nessun
sorgente nell'immagine finale). I problemi aperti sono di **consegna e manutenzione**, non di
costruzione.

## 4. Intervento: backlog → issue/milestone automatizzato (F12)

Il repo aveva 13 problemi noti e nessun posto dove viverli. Introdotto lo stesso modello del repo
`devops_hiway`, portato da GitLab a GitHub:

```
  docs/backlog.md  ──parse(id)──▶  sync-backlog-to-issues.py  ──API GitHub──▶  Issues + Milestone
   ### `id` — Titolo                (idempotente, fingerprint             (label backlog-sync,
   - status/priority/labels          <!-- backlog-id: id | hash: … -->)    milestone creata se manca)
   - milestone/ref
        │
        ├──▶ backlog-lint.py        (id univoci, status/priority validi, chiavi meta note,
        │                            chiavi ripetute, titoli milestone coerenti)
        └──▶ generate-roadmap.py ──▶ docs/roadmap.md   (GENERATA e committata; --check in CI)

  .github/workflows/backlog.yml
     lint  : push/PR su docs/backlog.md|docs/scripts/**  → backlog-lint + roadmap --check
     sync  : schedule lunedi 05:42 → --apply ;  workflow_dispatch(apply) ;  push → dry-run
             (mai su PR: su fork il GITHUB_TOKEN e read-only)
```

File aggiunti: `docs/backlog.md` (13 item, 4 milestone), `docs/roadmap.md` (generata),
`docs/scripts/{lib/backlog.py,backlog-lint.py,generate-roadmap.py,sync-backlog-to-issues.py,README.md}`,
`.github/workflows/backlog.yml`.

Differenze rispetto all'originale GitLab, dovute all'API GitHub (documentate anche in
`docs/scripts/README.md`):

- **`PATCH /issues/:n` sostituisce l'intero set di label** (GitLab ha `add_labels`): lo script fa
  l'**unione** con le label presenti, altrimenti ogni sync cancellerebbe le label messe a mano.
- **`GET /issues` include le pull request**: filtrate sulla chiave `pull_request`. Senza il filtro,
  una PR con la label `backlog-sync` verrebbe letta come item fantasma e **chiusa** dal sync — in
  questo repo, con 6 PR aperte, sarebbe successo al primo run.
- Milestone identificate da `number` (non `id`), create con `POST /milestones` se il titolo esatto
  non esiste.
- `state_reason: completed` sulla chiusura, per distinguerla dal "not planned" nella UI.

Verifiche eseguite (log `tooling-backlog-verifica.log`):

- `backlog-lint.py` → `13 item (12 open) · 4 milestone distinte`, OK.
- `generate-roadmap.py --check` → allineata.
- `sync-backlog-to-issues.py` (dry-run offline) → 12 item garantiti open, con milestone e label attese.
- `sync-backlog-to-issues.py` (dry-run **autenticato** contro il repo reale, sola lettura) → piano
  `CREATE 12 · UPDATE 0 · REOPEN 0 · CLOSE 0 · SKIP 0`. Lo zero su `CLOSE` e la risposta che serviva:
  la query per label non ha raccolto nessuna delle 6 PR aperte, quindi il primo `--apply` non chiudera
  niente per sbaglio.
- `actionlint` dalla root → nessun finding.
- Lint messo alla prova su un backlog deliberatamente rotto (id duplicato, `status: bogus`, chiave
  `prioriti`, chiave `labels` ripetuta, milestone `Alfa`/`alfa`): 5 errori + 1 warning, exit 1. La
  regola sulle **chiavi meta ripetute** e stata aggiunta proprio perche il primo draft del backlog
  ne conteneva una e nessun controllo la vedeva (vince l'ultima, la prima si perde in silenzio).

Il primo run reale su GitHub non e stato eseguito: richiede il push, che fa l'utente. La checklist di
verifica e nell'item `backlog-sync-primo-run` (piano → apply → secondo run tutto SKIP).

## 5. Sequenza consigliata

```
  1. push del branch  ──▶ workflow Backlog (dispatch, apply=false) ──▶ leggere il piano
  2. dispatch apply=true  ──▶ 4 milestone + 12 issue ──▶ secondo run: tutto SKIP
  3. ./tests/gpu.sh sulle 3 varianti su host con GPU        [gpu-gate-prima-del-tag]
  4. git tag -a v2.0.0 + push del tag ──▶ publish ──▶ verificare i tag su GHCR   [tag-v2-0-0]
  5. action.yml: pin a v2.0.0, via inputs.image, README allineato   [action-ref-e-input-image]
  6. bump 7.1.1 → 7.1.5 (driver invariato) + merge delle 4 PR dependabot in un colpo
  7. igiene registry (pr-*, main) — DOPO il punto 4, mai prima
```

I punti 1-2 e 5-7 non richiedono GPU. Il punto 3 e l'unico che richiede hardware, e resta il gate piu
importante: e l'unica prova che l'immagine faccia il lavoro per cui esiste.
