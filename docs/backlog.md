# Backlog operativo — sorgente di verita per le issue GitHub

Questo file e l'**unica sorgente di verita** dei todo del repo. Uno script idempotente
([`scripts/sync-backlog-to-issues.py`](scripts/sync-backlog-to-issues.py)) lo legge e
**apre/aggiorna/chiude automaticamente** una issue GitHub per ogni item, **creando le milestone
mancanti**, schedulato da [`.github/workflows/backlog.yml`](../.github/workflows/backlog.yml).

## Come funziona (flusso)

```
  docs/backlog.md  ──parse(id)──▶  sync-backlog-to-issues.py  ──API GitHub──▶  Issues + Milestone
   ### `id` — Titolo                  (idempotente)                            (label backlog-sync
   - status / labels / milestone      fingerprint                               + fingerprint nel corpo)
   - priority / ref                   <!-- backlog-id: id | hash: … -->

   item open  + nessuna issue       → CREATE   (milestone creata se manca)
   item open  + issue aperta  hash= → SKIP     (nessun duplicato: match per `id`)
   item open  + issue aperta  hash≠ → UPDATE   (titolo/corpo/labels/milestone riallineati)
   item open  + issue chiusa        → REOPEN   (il backlog comanda, non la UI)
   item done / rimosso              → CLOSE    (con commento + estratto del motivo)

                 │
                 └─▶ generate-roadmap.py ──▶ docs/roadmap.md   (pagina GENERATA, committata,
                                                                gate `generated-pages` in CI)
```

Re-run sicuro: il match e per `id` stabile (fingerprint nel corpo issue), **non** per testo →
editare titolo/descrizione non crea doppioni.

## Convenzione di scrittura di un item

- Un item inizia con `### \`<id-stabile>\` — <Titolo>` (l'`id` e in backtick, kebab-case, **non cambiarlo mai**).
- Metadati come bullet `- **chiave**: valore`:
  - **status**: `open` (default) | `done` → `done` chiude la issue.
  - **labels**: lista separata da virgola (`backlog-sync` e aggiunta in automatico; le label
    aggiunte a mano sulla issue **non** vengono rimosse: lo script fa l'unione).
  - **priority**: `low` | `medium` | `high` (opzionale).
  - **milestone**: titolo di una milestone GitHub (opzionale). Lo script la **cerca per titolo
    esatto e la crea se manca**, poi assegna la issue. Item della stessa milestone → titolo
    identico carattere per carattere.
  - **owner**: username GitHub (opzionale, assegnatario).
  - **ref**: link/percorso al doc o all'audit (opzionale).
- Tutto il resto del blocco (prosa) diventa il **corpo** della issue.

> Per "chiudere" un todo: metti `status: done` (storico) **oppure** rimuovi l'item. In entrambi i
> casi la issue viene chiusa al prossimo sync. Preferire `done` per gli item **gia sincronizzati**
> (la issue si chiude con la traccia del perche); la rimozione va bene solo per item mai sincronizzati.

> Prima di aprire un item nuovo **cerca il doppione per artefatto**, non per parole del problema:
> il path (`grep -i action.yml docs/backlog.md`), il tag GHCR, il nome del workflow, la variante
> FFmpeg. Due item scritti in momenti diversi sulla stessa azione usano parole diverse.

Validazione locale (stessi comandi della CI):

```shell
python3 docs/scripts/backlog-lint.py
python3 docs/scripts/generate-roadmap.py            # rigenera docs/roadmap.md (da committare)
python3 docs/scripts/sync-backlog-to-issues.py      # dry-run: mostra il piano, non scrive
```

---

## Item attivi

### `tag-v2-0-0` — Tutta la riparazione v2.0.0 e su main ma NON pubblicata: su GHCR `:latest` e l'immagine del 2023

- **status**: open
- **priority**: high
- **labels**: release, docker, bug
- **milestone**: Pubblicazione v2.0.0
- **ref**: [audit/2026-09-17-audit-stato-e-automazione.md](audit/2026-09-17-audit-stato-e-automazione.md)

`CHANGELOG.md` ha la sezione `[2.0.0] - 2026-08-09` ma **il tag `v2.0.0` non esiste** (ultimo tag:
`v1.0.1`, maggio 2023). Il workflow di publish gira solo su push di tag `v*` → **niente e stato
pubblicato**. Verificato sul registry il 17/09/2026: `ghcr.io/allan-nava/docker-ffmpeg-nvenc:latest`
e un manifest **creato il 2023-01-16**, label `org.opencontainers.image.version=v0.1.2`, `User`
vuoto (**gira come root**), `ENTRYPOINT ["/bin/bash"]`, 10 layer (nessun multi-stage) e
`NVIDIA_REQUIRE_CUDA=… driver>=470,driver<471`: su un host con driver moderno (535/550/570) il
container **non parte affatto** (`requirement error: unsatisfied condition`).

Quindi oggi: chi segue il README scarica l'immagine rotta del 2023, e la CI verde ogni lunedi
certifica un artefatto che nessuno puo usare.

Chiusura (il push del tag lo fa l'utente):
- [ ] `./tests/gpu.sh` su un host con GPU NVIDIA sulle tre varianti (mai eseguito in CI)
- [ ] `git tag -a v2.0.0 -m "Release 2.0.0"` + push del tag
- [ ] verificare i tag effettivi su GHCR dopo il run: `latest`, `v2.0.0`, `v2.0`, `v2` **senza**
      suffisso (variante default) + `latest-ffmpeg{7.1.1,6.0,5.1.2}`
- [ ] verificare che `:latest` abbia `User=ffmpeg` e `Entrypoint=["ffmpeg"]`

### `action-ref-e-input-image` — La Action pubblica punta a `:latest` mobile, `@v2` non esiste e `inputs.image` e codice morto

- **status**: open
- **priority**: high
- **labels**: github_actions, documentation, bug
- **milestone**: Pubblicazione v2.0.0
- **ref**: [audit/2026-09-17-audit-stato-e-automazione.md](audit/2026-09-17-audit-stato-e-automazione.md)

Tre problemi sullo stesso file, `action.yml`:

1. `runs.image: docker://…:latest` — tag **mobile**: la Action cambia comportamento sotto i piedi
   dei consumatori ad ogni publish, e oggi esegue l'immagine del 2023 (vedi `tag-v2-0-0`).
2. `README.md` documenta `uses: Allan-Nava/Docker-FFmpeg-Nvenc@v2`, ma **nessun tag/branch `v2`
   esiste**: quell'esempio non risolve.
3. `inputs.image` esiste, e documentato come "override per pinnare una versione specifica", ma
   **non e referenziato da nessuna parte**: `runs.image` e statico per specifica GitHub (non
   accetta espressioni `${{ }}`). E un input che promette una cosa che non fa.

Decisione da prendere: pinnare `runs.image` a `vX.Y.Z` (o al digest) aggiornandolo ad ogni release,
e **rimuovere** `inputs.image` documentando che per pinnare si usa `uses: …@vX.Y.Z`.

### `ghcr-tag-igiene` — Sul registry restano `main`, `pr-2`…`pr-5` e le immagini v0.1.x del 2023

- **status**: open
- **priority**: medium
- **labels**: docker, cleanup
- **milestone**: Pubblicazione v2.0.0

Tag presenti su GHCR (17/09/2026): `main`, `pr-2`, `pr-3`, `pr-4`, `pr-5`, `v0.1.1`, `v0.1.2`,
`latest`, `v1.0.1-ffmpeg5.1.2`, `v1.0.1-ffmpeg6.0`. I tag `pr-*` e `main` sono residui di workflow
che **non esistono piu** (nessun workflow attuale pubblica su push di branch o PR): sono immagini
del 2023, root, con `--enable-nonfree`, scaricabili da chiunque.

Da fare dopo `tag-v2-0-0` (non prima: cancellare `latest` ora lascerebbe il README senza immagine):
eliminare i tag `pr-*` e `main`, valutare la retention del package (`Package settings ▸ Manage
Actions access / retention`) e lasciare le `v0.1.x`/`v1.0.1-*` come storia ma **marcate** nel README
come non supportate.

### `ffmpeg-bump-7-1-5` — La variante default e ferma a FFmpeg 7.1.1, upstream e a 7.1.5

- **status**: open
- **priority**: high
- **labels**: docker, upgrade, sicurezza
- **milestone**: Manutenzione immagine & upstream

Verificato su `ffmpeg.org/releases` il 17/09/2026: nel ramo 7.1 esistono **7.1.2, 7.1.3, 7.1.4,
7.1.5**. Il repo pinna `7.1.1` → **cinque release di manutenzione indietro**, cioe i fix (inclusi
quelli di sicurezza) di quel ramo non sono nell'immagine.

Il bump e a costo quasi nullo: il vincolo del `configure` resta `ffnvcodec >= 12.1.14.0`
(verificato su `n7.1.2` e `n7.1.5`), quindi `NVCODEC_BRANCH=sdk/12.1` non cambia e **il driver
NVIDIA minimo dell'host non si alza**. Da propagare: matrice in `ci.yml` e `docker-publish.yml`,
tabella nel `README.md`, `CLAUDE.md`/`AGENTS.md`.

### `dependabot-pr-arretrate` — 4 PR dependabot major aperte da 5 settimane + 2 PR fossili del 2023

- **status**: open
- **priority**: high
- **labels**: dependencies, github_actions
- **milestone**: Manutenzione immagine & upstream

Aperte il 09/08/2026 e mai toccate: `#23` login-action 3→4, `#22` setup-buildx-action 3→4,
`#21` build-push-action 6→7, `#20` metadata-action 5→6. Sono **quattro major** sulle action che
fanno la build e il push: vanno lette insieme (una CI verde su tutte e quattro, non quattro merge
ciechi), e `metadata-action` 6 tocca proprio il tagging che in questo repo si e gia rotto una volta.

Fossili da chiudere, riferiti a file che non esistono piu: `#18` "Bump nvidia/cuda …"
(`Containerfile`, rimosso in v2.0.0) e `#5` "Bump sigstore/cosign-installer" (workflow rimosso).

Da fare anche: `groups` in `.github/dependabot.yml` (una PR sola per le action docker/*) per non
riaprire cinque PR ogni settimana. `actions/checkout` e ancora a `v4` ovunque.

### `ffmpeg-8-e-9-varianti` — Valutare FFmpeg 8.1.x / 9.0.x nella matrice (e quale diventa default)

- **status**: open
- **priority**: medium
- **labels**: docker, upgrade
- **milestone**: Manutenzione immagine & upstream

Upstream (17/09/2026) e a **9.0.1**, con il ramo **8.1.2** ancora manutenuto; la matrice del repo
si ferma a 7.1.x. Fatto che rende la valutazione economica: il vincolo `ffnvcodec` di `n8.1.2` e
`n9.0.1` e **identico** a quello di 7.1 (`>= 12.1.14.0`), quindi `sdk/12.1` basta anche per 9.0 e
**il driver minimo dell'host resta ≥ 530** — non c'e il solito tradeoff "versione nuova = driver
nuovo".

Da verificare prima di aggiungerle: i nomi dei pacchetti runtime bookworm reggono, il set di
`--enable-*` e ancora valido (8.x ha rimosso qualche opzione), e **quante varianti si vogliono
mantenere**: ogni riga della matrice e ~una build da 90 minuti su ogni tag. Probabile forma finale:
9.0.x default, 7.1.x come LTS, 5.1.2 per i driver ≥ 470, drop di 6.0.

### `debian-13-trixie` — La base `debian:12-slim` e oldstable

- **status**: open
- **priority**: medium
- **labels**: docker, upgrade
- **milestone**: Manutenzione immagine & upstream

Debian 13 (trixie) e `stable`; bookworm e **oldstable** (verificato via `api.ftp-master.debian.org`,
17/09/2026). Non e un'emergenza (bookworm ha supporto LTS per anni), ma e esattamente la strada per
cui questo repo si e rotto in silenzio una volta: la base marcisce, e lo schedule del lunedi lo
scopre solo quando i repo APT smettono di rispondere.

`DEBIAN_VERSION` e gia un `ARG`, ma **le liste di pacchetti non sono parametriche**: passare a 13
richiede di riallineare i nomi versionati dello stage runtime. Verificato in trixie:
`libvpx7` → **`libvpx9`** (1.15.0), `libx265-199` → **`libx265-215`** (4.1), `libx264-164` **resta**
(0.164.3108). Tutto il resto (`libass9`, `libmp3lame0`, `libopus0`, `libspeex1`, `libtheora0`,
`libvorbis0a`, `libvorbisenc2`, `libnuma1`, `libxml2`, `libfreetype6`, `libfribidi0`,
`libharfbuzz0b`, `libfontconfig1`) esiste con lo stesso nome.

### `gpu-gate-prima-del-tag` — `tests/gpu.sh` non e invocato da nessun workflow: il publish e cieco su NVENC

- **status**: open
- **priority**: medium
- **labels**: ci, test
- **milestone**: Automazione repo

`tests/smoke.sh` verifica che gli encoder NVENC siano **compilati**; che *encodino* lo verifica solo
`tests/gpu.sh`, che nessun workflow chiama (i runner GitHub-hosted non hanno GPU). Oggi la promozione
di un tag e un atto di fede sul funzionamento reale, e il tipo di rottura che non vedremmo e proprio
la piu probabile: mismatch fra `NVCODEC_BRANCH` e driver dell'host (`This NVENC API is not compatible
with the installed driver`).

Due strade: (a) self-hosted runner con GPU + NVIDIA Container Toolkit, job `workflow_dispatch` da
lanciare prima del tag; (b) restare manuali ma renderlo **obbligatorio** in una checklist di release
(vedi `tag-v2-0-0`). Finche non c'e (a), (b) va scritto nel `CLAUDE.md` come gate.

### `trivy-non-e-un-gate` — Lo scan gira su una sola variante e non blocca nulla

- **status**: open
- **priority**: medium
- **labels**: ci, sicurezza
- **milestone**: Supply chain & sicurezza

Il job `scan` di `ci.yml` builda la sola variante di default, gira Trivy con `severity: CRITICAL,HIGH`
e `ignore-unfixed: true`, e carica il SARIF su code scanning: **nessun `exit-code`**, quindi lo step
e verde qualunque cosa trovi. Va bene come inventario, non come gate — e in pratica nessuno apre la
tab Code scanning.

Da decidere: `exit-code: 1` sulle sole CRITICAL (con `ignore-unfixed` mantenuto, altrimenti le CVE
Debian senza patch bloccano tutto per sempre) e scan anche sulle varianti 6.0/5.1.2, che sono le piu
vecchie e quindi le piu esposte.

### `cosign-firma-immagini` — Le immagini pubblicate non sono firmate

- **status**: open
- **priority**: low
- **labels**: sicurezza, supply-chain
- **milestone**: Supply chain & sicurezza

Il publish produce gia `provenance: true` e `sbom: true`, ma niente firma: un consumatore non ha modo
di verificare che l'immagine venga da questa CI. Con `id-token: write` (gia concesso nel job) la firma
keyless cosign e ~10 righe. Nota storica: una PR dependabot su `sigstore/cosign-installer` (`#5`,
2023) e ancora aperta pur riferendosi a un workflow rimosso — il repo aveva la firma e l'ha persa.

### `multiarch-arm64` — Solo `linux/amd64`

- **status**: open
- **priority**: low
- **labels**: docker
- **milestone**: Manutenzione immagine & upstream

Build e publish sono fissi su `platforms: linux/amd64`. NVENC esiste anche su arm64 (Jetson, Grace
Hopper), quindi non e una scelta ovvia: va **o** implementata (build arm64 nativa/emulata, +tempo di
CI) **o** dichiarata nel README come non supportata, con il perche. Oggi non e ne l'una ne l'altra.

### `backlog-sync-primo-run` — Verificare il primo run reale del sync backlog → issue

- **status**: open
- **priority**: medium
- **labels**: ci, documentation
- **milestone**: Automazione repo
- **ref**: [runbook: docs/scripts/README.md](scripts/README.md)

L'automazione (questo file + `docs/scripts/` + `.github/workflows/backlog.yml`) e stata aggiunta il
17/09/2026 ma **non ha ancora girato su GitHub**: il workflow parte solo dopo il push. Il dry-run
locale e verde.

- [ ] push del branch → far girare `Backlog` a mano (`workflow_dispatch`, `apply=false`) e leggere il piano
- [ ] run con `apply=true`: devono nascere le milestone («Pubblicazione v2.0.0», «Manutenzione
      immagine & upstream», «Supply chain & sicurezza», «Automazione repo») e una issue per item
- [ ] secondo run consecutivo: deve essere **tutto SKIP** (prova dell'idempotenza)
- [ ] mettere `status: done` su questo item quando i tre punti sopra sono verdi

## Item chiusi (storico)

### `doc-drift-asserzioni-smoke` — `CHANGELOG` diceva 18 asserzioni di smoke test, sono 17

- **status**: done
- **priority**: low
- **labels**: documentation
- **milestone**: Automazione repo

> Corretto il 17/09/2026 nella sezione `[2.0.0]` del `CHANGELOG.md`. Conteggio reale delle asserzioni
> di `tests/smoke.sh`: 2 (binari) + 1 (versione attesa) + 2 (NVENC) + 5 (codec di contorno) +
> 2 (licenza) + 1 (transcodifica) + 4 (igiene container) = **17** — coerente con `CLAUDE.md`,
> `AGENTS.md` e `README.md`, che dicevano 17. Item tenuto come storico: e il tipo di drift che la
> regola "allineare tutto" deve intercettare.
