# Audit iniziale — Docker-FFmpeg-Nvenc (2026-08-09)

Audit statico del repository `github.com/Allan-Nava/Docker-FFmpeg-Nvenc` allo stato del commit `b536c4d` (branch `main`, working tree pulito).

> **Stato: risolto in v2.0.0 (2026-08-09).** Questo documento e la fotografia del repo **prima** degli interventi e va letto al passato: i file che cita (`Containerfile`, `Dockerfile-ffmpeg6`, `module.defs`, `scripts/`, `docker-publish-ffmpeg6.yml`) non esistono piu. Cosa e stato fatto per ciascun punto: `CHANGELOG.md`, sezione `[2.0.0]`. Verifica post-fix: le tre varianti (FFmpeg 5.1.2 / 6.0 / 7.1.1) buildano e passano 17/17 asserzioni di `tests/smoke.sh`.

**Esito sintetico: entrambe le immagini pubblicate dal repo non sono più costruibili.** Il `Dockerfile` principale muore su `apt-get update` (Debian buster fuori archivio), `Dockerfile-ffmpeg6` muore sull'installazione delle dipendenze (pacchetto `python` inesistente in bullseye). Il `Containerfile` è rotto per costruzione. Sotto, dettaglio e priorità.

> Le verifiche marcate **[verificato]** sono state eseguite con richieste reali ai repository upstream in data 2026-08-09. Nessuna `docker build` è stata lanciata in questo audit: le rotture sono dedotte da fatti verificati sui repository di pacchetti, non da un run di build.

## 1. Schema del repository e flusso di pubblicazione

```
                          push tag v*  ──────────────────────────────┐
                                                                     │
  ┌──────────────────────────────────────────────────────────────┐   │
  │ .github/workflows/docker-publish.yml                         │◄──┤
  │   checkout@v3 → github-script@v4 → prep (::set-output)        │   │
  │   → buildx → login ghcr → build-push-action@v4               │   │
  │        file: ./Dockerfile        platform: linux/amd64       │   │
  └───────────────────────────┬──────────────────────────────────┘   │
                              │ push                                 │
                              ▼                                      │
        ghcr.io/allan-nava/docker-ffmpeg-nvenc:<tag>-ffmpeg5.1.2      │
                                                                     │
  ┌──────────────────────────────────────────────────────────────┐   │
  │ .github/workflows/docker-publish-ffmpeg6.yml                 │◄──┘
  │   (stesso flusso)  file: ./Dockerfile-ffmpeg6                │
  └───────────────────────────┬──────────────────────────────────┘
                              │ push
                              ▼
        ghcr.io/allan-nava/docker-ffmpeg-nvenc:<tag>-ffmpeg6.0

  NON collegati ad alcun flusso:
    Containerfile   (UBI8 + apt-get → build impossibile)
    module.defs     (frammento HandBrake-contribs)
    scripts/*.sh    (build out-of-Docker, mai invocati)
    action.yml      (Action pubblica; builda il Dockerfile ad ogni uso)
```

Anatomia di una immagine (identica nei due Dockerfile funzionanti-in-teoria):

```
  debian:10.10-slim / debian:11-slim
    │
    ├─ RUN apt-get update                       ← layer separato (cache stantia)
    ├─ RUN apt-get install <tool di build>      ← ~40 pacchetti, incl. build-essential
    ├─ RUN git clone nv-codec-headers → make install
    ├─ RUN wget ffmpeg-<ver>.tar.xz → tar -xf   ← sorgenti lasciati in /app
    ├─ RUN ./configure ... && make install      ← singolo layer, ~1 GB di oggetti
    ├─ RUN apt-get update
    ├─ RUN apt-get install <runtime + yad, expect, tcl, git, wget>
    └─ RUN apt-get install <libav*, libgtk-3, libgstreamer, ...>   ← ffmpeg di distro
       CMD ["/bin/bash"]

  ⚠ Nessun multi-stage: toolchain di build + sorgenti + oggetti restano nell'immagine finale.
```

## 2. Blocchi (l'artefatto non si produce)

### B1 — `Dockerfile`: base Debian 10 fuori archivio → `apt-get update` fallisce **[verificato]**

`Dockerfile:2` usa `debian:10.10-slim`. Buster è EOL e i suoi indici sono stati spostati su `archive.debian.org`:

| URL | HTTP |
|---|---|
| `http://deb.debian.org/debian/dists/buster/Release` | **404** |
| `http://security.debian.org/debian-security/dists/buster/updates/Release` | **404** |
| `http://archive.debian.org/debian/dists/buster/Release` | 200 |
| `http://deb.debian.org/debian/dists/bullseye/Release` | 200 |

`apt-get update` in `Dockerfile:16` fallisce a scaricare gli indici → exit non-zero → build interrotta. **Questa è l'immagine che il badge del README indica come principale.**

Fix possibili, in ordine di preferenza:
1. bump della base a `debian:12-slim` (bookworm) o `debian:13-slim`, con adeguamento dei nomi versionati dei pacchetti (`libx264-*`, `libx265-*`, `libavcodec-extra*`);
2. base `nvidia/cuda:<ver>-devel-ubuntu22.04` se in futuro serve davvero il toolkit CUDA (`--enable-cuda-nvcc`, `--enable-libnpp`);
3. (tampone) riscrittura di `sources.list` verso `archive.debian.org` + `Acquire::Check-Valid-Until "false"` — sconsigliato: nessuna patch di sicurezza.

### B2 — `Dockerfile-ffmpeg6`: pacchetto `python` inesistente in Debian 11 → install fallisce **[verificato]**

`Dockerfile-ffmpeg6:23` include `python` nella lista deps. In bullseye il metapacchetto `python` è stato rimosso:

```
madison?package=python&s=bullseye   → (vuoto, il pacchetto non esiste)
madison?package=python2&s=bullseye  → python2 | 2.7.18-3 | oldoldstable | amd64, arm64, ...
```

`apt-get install -y ... python ...` → `E: Unable to locate package python` → build interrotta. Sostituire con `python3` (già presente nella riga precedente, quindi probabilmente si può semplicemente rimuovere).

### B3 — `Containerfile`: gestore pacchetti incompatibile con la base

`Containerfile:1` parte da `registry.access.redhat.com/ubi8/ubi:latest` e alle righe 15-21 e 64-107 usa `apt-get` con nomi di pacchetti Debian (`build-essential`, `libass-dev`, `libx264-155`, …). Su UBI8 il gestore è `dnf`/`microdnf` e `apt-get` non esiste → fallisce alla prima `RUN`. Il file è a tutti gli effetti un copia-incolla del `Dockerfile` con la sola `FROM` cambiata (commit `1f14723 added containerfile`, poi `0c0aec1 removed podman`).

Non è referenziato da nessun workflow: **o si porta a `dnf` + EPEL/RPMFusion (lavoro non banale: molte `-dev` non hanno equivalente diretto), o si elimina.** Tenerlo così è debito puro e induce in errore chi legge.

## 3. Difetti funzionali (l'artefatto si produce, ma non fa ciò che è documentato)

### F1 — Il tag `:latest` non viene mai pubblicato

In entrambi i workflow (`docker-publish.yml:28-46`, `docker-publish-ffmpeg6.yml:37-55`) la `VERSION` viene sempre costruita con il suffisso di versione FFmpeg:

```
VERSION=${GITHUB_REF#refs/tags/}-ffmpeg5.1.2      # es. "v1.0.1-ffmpeg5.1.2"
...
if [[ $VERSION =~ ^v[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then    # non matcha MAI
  TAGS="$TAGS,...:${MINOR},...:${MAJOR},...:latest"
fi
```

Il suffisso rende la regex semver strutturalmente insoddisfacibile: il ramo che aggiunge `:latest`, `:MAJOR` e `:MINOR` è **codice morto**. Conseguenza pratica: chi segue il README e fa `pull ...:latest` non trova nulla.

Fix: applicare la regex a `${GITHUB_REF#refs/tags/}` prima di aggiungere il suffisso, e usare tag distinti per variante (`latest-ffmpeg5.1.2`, `latest-ffmpeg6.0`) più eventualmente un `latest` che punta alla variante di riferimento.

### F2 — README che punta al registry sbagliato

`README.md:30` e `README.md:41` istruiscono `docker pull allannava/docker-ffmpeg-nvenc:latest` e usano quel riferimento nell'esempio `docker run`. La CI pubblica invece su `ghcr.io/allan-nava/docker-ffmpeg-nvenc`. Nessun workflow in questo repo fa login o push verso Docker Hub. Sommato a F1, l'istruzione di installazione documentata **non funziona su nessuno dei due registry**.

Da correggere insieme a F1, indicando il tag reale (es. `ghcr.io/allan-nava/docker-ffmpeg-nvenc:v1.0.1-ffmpeg6.0`).

### F3 — `action.yml`: la GitHub Action non può funzionare

```yaml
runs:
  using: 'docker'
  image: 'Dockerfile'
  args:
    - ${{ inputs.command }}
```

Due problemi indipendenti:
- `image: 'Dockerfile'` ricompila FFmpeg da sorgente **ad ogni invocazione** della Action (decine di minuti per job, per ogni utente che la usa). Va sostituito con `image: 'docker://ghcr.io/allan-nava/docker-ffmpeg-nvenc:<tag>'`.
- L'immagine non definisce `ENTRYPOINT`, solo `CMD ["/bin/bash"]`. Gli `args` di una Action docker **sostituiscono il CMD**: la stringa `-i` (o l'intera command line passata dall'utente) viene interpretata come **eseguibile**, non come argomenti di `ffmpeg`. Serve `ENTRYPOINT ["ffmpeg"]` nell'immagine (o `entrypoint:` nell'action) e il passaggio degli argomenti splittato.

Inoltre l'input `token` è dichiarato ma non usato da nulla.

### F4 — I badge del README non riflettono i trigger

`README.md:2` usa `docker-publish.yml/badge.svg?branch=main`, ma il workflow gira **solo su push di tag**, mai su `main`. Il badge riporta quindi uno stato non collegato al branch indicato.

### F5 — `--extra-cflags`/`--extra-ldflags` CUDA verso path inesistenti

`Dockerfile:59-60`, `Dockerfile-ffmpeg6:57-58`, `Containerfile:58-59` passano `-I/usr/local/cuda/include` e `-L/usr/local/cuda/lib64`. Nell'immagine **non è installato alcun CUDA toolkit**: quelle directory non esistono. NVENC via `--enable-nvenc` richiede solo `nv-codec-headers` (pkg-config `ffnvcodec`), che è installato — quindi la build non si rompe, ma i flag sono fuorvianti e suggeriscono una capacità (CUDA/NPP/scale_npp) che l'immagine **non ha**. Da rimuovere, oppure installare davvero CUDA e abilitare `--enable-cuda-nvcc --enable-libnpp --enable-nvdec --enable-cuvid` (come fa `scripts/build-ffmpeg.sh`, che però è morto — vedi D3).

### F6 — Nessuna verifica funzionale nella pipeline

I workflow buildano e pushano senza alcun test. Un'immagine in cui NVENC non è stato compilato (per esempio perché `configure` ha silenziosamente disabilitato l'encoder) verrebbe pubblicata comunque. Manca il gate minimo:

```
docker run --rm $IMAGE ffmpeg -hide_banner -encoders | grep -q h264_nvenc
```

che non richiede GPU (l'encoder deve solo risultare compilato) e avrebbe intercettato B1/B2 al primo tag.

## 4. Qualità dell'immagine

### Q1 — Nessun multi-stage: immagine enorme

Le immagini finali contengono `build-essential`, `cmake`, `ninja-build`, `git`, `imagemagick`, i sorgenti FFmpeg scompattati in `/app` (mai rimossi, `Dockerfile:36-38` fa `rm` solo del tarball) e tutti gli oggetti di `make`. A questo si aggiungono `yad`, `expect`, `tcl8.6`, `libgtk-3-0`, `libgstreamer*`, `libcairo2`, `libgdk-pixbuf` — **GUI e GStreamer in un'immagine di transcodifica headless**, verosimilmente ereditati da un Dockerfile HandBrake (coerente con la presenza di `module.defs`).

Stimabile in diversi GB contro le poche centinaia di MB ottenibili con:

```
FROM debian:12-slim AS builder     → toolchain + compilazione
FROM debian:12-slim                → COPY --from=builder /usr/local /usr/local + sole runtime lib
```

### Q2 — `apt-get update` scollegato da `apt-get install`

`Dockerfile:16-22`, `:65-77`, `:80-108` (e omologhi negli altri due file): `update` e `install` in `RUN` distinti. Se il layer di `update` resta in cache mentre quello di `install` viene invalidato, apt lavora su indici stantii → fallimenti "Package not found"/404 non deterministici. Regola standard: un solo `RUN apt-get update && apt-get install -y --no-install-recommends ... && rm -rf /var/lib/apt/lists/*`.

Nota collaterale: le liste apt non vengono mai ripulite → ~40-50 MB inutili per ciascuno dei tre blocchi.

### Q3 — Installazione delle libav\* di distro sopra una build custom

`Dockerfile:81-108` installa `libavcodec-extra58`, `libavfilter-extra7`, `libavformat58`, `libavutil56`, `libswresample3`, `libswscale5`. L'immagine ha appena compilato e installato FFmpeg in `/usr/local` con `--enable-static`. Queste librerie di distro sono la versione **Debian** di FFmpeg (4.1 su buster), non usate dal binario appena costruito: peso e superficie di attacco senza beneficio, oltre a confondere chiunque faccia `ffmpeg -version` dentro il container aspettandosi coerenza.

### Q4 — `ENV DEBIAN_FRONTEND noninterac1tive` (typo, in tutti e tre i file)

`Dockerfile:8`, `Dockerfile-ffmpeg6:8`, `Containerfile:7`. Il valore `noninterac1tive` non è riconosciuto da debconf, quindi il frontend interattivo resta attivo: prompt e warning `debconf: unable to initialize frontend: Dialog` durante le install. Non blocca la build ma è esattamente il tipo di errore che si propaga per copia-incolla — infatti è già in tre file.

### Q5 — Continuazioni di riga fragili nel blocco `./configure`

`Dockerfile:42-58` (e omologhi): quasi tutte le righe terminano con `\` **seguito da uno spazio**. BuildKit tollera (regex `\\[ \t]*$`) ma emette warning di deprecazione; è una configurazione che si rompe al primo editor che normalizza gli spazi in modo diverso. Da riscrivere pulito quando si tocca il blocco.

### Q6 — Riproducibilità: `nv-codec-headers` non pinnato in `Dockerfile-ffmpeg6`

`Dockerfile:30` pinna correttamente `-b sdk/11.0` (e da `github.com/FFmpeg/nv-codec-headers`). `Dockerfile-ffmpeg6:29` clona invece `master` da `git.videolan.org` senza branch né `--depth 1`: la build non è riproducibile e può finire con headers che richiedono un driver NVIDIA più recente di quello installato sugli host di destinazione (errore tipico a runtime: *"This NVENC API is not compatible with the installed driver"*). Da pinnare a un `sdk/<ver>` compatibile con il parco driver.

### Q7 — Igiene container

- `MAINTAINER` (deprecato da Docker 1.13) in tutti e tre i file → `LABEL org.opencontainers.image.authors=`.
- Nessun `USER` non-root: il container gira come root.
- `ENV NVIDIA_DRIVER_CAPABILITIES all` è più ampio del necessario; per transcodifica basta `video,compute,utility`.
- Base image non pinnata per digest (`debian:11-slim` è mobile).
- Nessun `HEALTHCHECK`, nessuna label OCI nel Dockerfile stesso (solo quelle iniettate dal workflow).

## 5. Codice morto e disallineamenti

### D1 — `module.defs` non appartiene a questo repo

File di 212 righe in stile **HandBrake contrib** (`import.MODULE.defs`, `FFMPEG.CONFIGURE.extra`, `FEATURE.qsv`/`vce`/`nvenc`, fetch da `HandBrake/HandBrake-contribs`). Nessun `Makefile`, nessuno script e nessun Dockerfile lo include: non viene valutato da nulla. Contiene anche un errore latente (righe 77-78: `--enable-filter=null \ ` con spazio dopo il backslash, che in make spezzerebbe la continuazione). Da rimuovere, o da isolare in una cartella `reference/` con un README che ne spieghi la provenienza.

### D2 — `.github/dependabot.yml` punta a una directory inesistente

Righe 11-14 registrano un ecosistema `docker` su `/tests`. La directory `tests/` non esiste nel repo → quell'update è inerte (e Dependabot segnala errore di configurazione nella UI). Da rimuovere o da creare i test corrispondenti (che servirebbero comunque, vedi F6).

### D3 — `scripts/` è un percorso di build parallelo, morto e non funzionante

`scripts/base.sh`, `build-tools.sh`, `build-library.sh`, `build-ffmpeg.sh` implementano una build FFmpeg from-source fuori da Docker (cross-compile Linux/Windows/macOS). Nessun Dockerfile, workflow o `action.yml` li invoca; l'unico riferimento incrociato è `source ./base.sh` tra loro.

Oltre ad essere morti, hanno difetti propri:
- `build-ffmpeg.sh:10` e `:16` leggono `${PREFIX}/ffmpeg_configure_options` e `${PREFIX}/ffmpeg_extra_libs`. **Nessuno script genera quei file**: `base.sh:59-60` dichiara gli array `FFMPEG_CONFIGURE_OPTIONS`/`FFMPEG_EXTRA_LIBS` e i vari `build-*.sh` li popolano in memoria, ma non li scrivono mai su disco. Con `set -eu` ereditato da `base.sh`, `cat` su file inesistente termina lo script.
- `source ./base.sh` con path relativo: gli script funzionano solo se la cwd è `scripts/`.
- `build-tools.sh` è una copia degradata di `build-library.sh` in cui il `case "$(uname)"` è stato rimosso lasciando le due righe `cp -r ./bin/.` indentate a vuoto (solo-Linux, senza dirlo).
- `build-ffmpeg.sh` punta a `/usr/local/cuda-11.5` hardcoded.

Decisione da prendere: **eliminarli** (il percorso reale è Docker) oppure ripararli e renderli l'unica sorgente di verità della configurazione FFmpeg, invocandoli dai Dockerfile. Lo stato attuale — due configurazioni FFmpeg divergenti, una nei Dockerfile e una in `scripts/`, con set di feature diversi — è la peggiore delle tre opzioni.

### D4 — Deriva tra i tre file di build

| | `Dockerfile` | `Dockerfile-ffmpeg6` | `Containerfile` |
|---|---|---|---|
| base | debian:10.10-slim | debian:11-slim | ubi8 (con apt!) |
| FFmpeg | 5.1.2 | 6.0 | 5.1.2 |
| nv-codec-headers | `sdk/11.0` pinnato | `master` | `sdk/11.0` pinnato |
| `libdvdread` | `libdvdread4` | `libdvdread8` | `libdvdread4` |
| `libx264`/`libx265` | 155 / 165 | 160 / 192 | 155 / 165 |
| `echo "Compiled..."` | commentato | attivo | commentato |

Tre copie manuali della stessa logica che divergono su dettagli casuali. Con un solo Dockerfile parametrizzato (`ARG FFMPEG_VERSION`, `ARG NVCODEC_BRANCH`, `ARG DEBIAN_VERSION`) e una `strategy.matrix` nei workflow, i due workflow quasi-identici (3258 e 3103 byte, differenza sostanziale: il nome del file e il suffisso di tag) diventerebbero uno.

## 6. Licenza e ridistribuzione

- **Manca il file `LICENSE`** benché `README.md:55` dichiari MIT. Senza file di licenza, GitHub non rileva la licenza e il campo `license.spdx_id` usato nelle label OCI dei workflow (`docker-publish.yml:85-86`) è `null` → la label viene emessa vuota.
- Più rilevante: la build usa **`--enable-gpl --enable-nonfree --enable-version3`** (`Dockerfile:43-46`). Un binario FFmpeg compilato con `--enable-nonfree` **non è legalmente ridistribuibile**, e le immagini vengono pubblicate su un registry pubblico. Nella configurazione attuale `--enable-nonfree` non sembra nemmeno necessario: non è abilitato `libfdk-aac` né altre componenti nonfree — le librerie richieste (`libx264`, `libvpx`, `libmp3lame`, `libopus`) sono coperte da GPL. **Rimuovere `--enable-nonfree` rende l'immagine ridistribuibile sotto GPLv3**, ed è probabilmente un cargo-cult ereditato da guide NVENC.
- Va inoltre dichiarato che l'immagine è GPL, non MIT: MIT copre il Dockerfile, non l'artefatto.

## 7. Supply chain / CI

- `actions/github-script@v4`, `actions/checkout@v3`, `docker/login-action@v2`, `docker/setup-buildx-action@v2`, `docker/build-push-action@v4`: tutte da 2-3 major indietro. `github-script@v4` usa l'API vecchia `github.repos.get` — passando a v5+ va riscritta in `github.rest.repos.get`, quindi l'aggiornamento non è meccanico.
- `::set-output` (`docker-publish.yml:47-49` e omologhe) è deprecato → `echo "name=value" >> $GITHUB_OUTPUT`.
- Action non pinnate a SHA (solo tag mobili): standard di hardening consigliato per workflow che pubblicano artefatti.
- Nessuna scansione vulnerabilità (Trivy/Grype), nessun SBOM, nessuna provenance/attestation, nessuna firma (cosign) — tutte disponibili nativamente in `build-push-action` v5+ (`provenance: true`, `sbom: true`).
- `permissions` correttamente minimizzato (`contents: read`, `packages: write`) — questo è a posto.
- Le due build sono job separati in workflow separati: nessuna cache condivisa, nessun `cache-from`/`cache-to` GHA → ogni tag ricompila FFmpeg due volte da zero.

## 8. Priorità consigliata

| # | Intervento | Perché prima |
|---|---|---|
| 1 | Bump base image + rimozione `python` (B1, B2) | senza questo non esiste alcun artefatto |
| 2 | Smoke test `ffmpeg -encoders \| grep nvenc` in CI (F6) | è il gate che avrebbe evitato 1 |
| 3 | Fix tagging `:latest` + README/registry corretti (F1, F2) | l'istruzione di installazione documentata non funziona |
| 4 | Rimuovere `--enable-nonfree` + aggiungere `LICENSE` (§6) | pubblicazione di binari non ridistribuibili |
| 5 | Unificare in un Dockerfile parametrizzato + matrix (D4) | ogni fix successivo va altrimenti fatto 2-3 volte |
| 6 | Multi-stage + `apt` in un solo `RUN` + pulizia sorgenti (Q1, Q2, Q3) | dimensione immagine e superficie di attacco |
| 7 | Decidere su `Containerfile`, `scripts/`, `module.defs`, `/tests` (B3, D1, D2, D3) | rimozione di debito e di documentazione fuorviante |
| 8 | Aggiornare le action, `$GITHUB_OUTPUT`, SBOM/provenance/scan (§7) | hardening |
| 9 | Riscrivere `action.yml` su immagine pre-buildata + `ENTRYPOINT` (F3) | la Action pubblica è inutilizzabile |

## Log e verifiche

Verifiche eseguite il 2026-08-09 (`logs/` non popolata: l'audit è statico, gli unici comandi di rete sono i seguenti):

```
curl -o /dev/null -w "%{http_code}" http://deb.debian.org/debian/dists/buster/Release                       → 404
curl -o /dev/null -w "%{http_code}" http://security.debian.org/debian-security/dists/buster/updates/Release → 404
curl -o /dev/null -w "%{http_code}" http://deb.debian.org/debian/dists/bullseye/Release                     → 200
curl -o /dev/null -w "%{http_code}" http://archive.debian.org/debian/dists/buster/Release                   → 200
curl "https://api.ftp-master.debian.org/madison?package=python&s=bullseye"                                  → (vuoto)
curl "https://api.ftp-master.debian.org/madison?package=python2&s=bullseye"                                 → python2 | 2.7.18-3 | oldoldstable
```

Non eseguito in questo audit: `docker build` delle tre varianti (che confermerebbe B1/B2 empiricamente e misurerebbe la dimensione reale per Q1), e ispezione dei tag effettivamente presenti su GHCR (che confermerebbe F1 lato registry).
