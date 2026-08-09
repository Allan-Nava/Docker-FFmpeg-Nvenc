# Changelog

Tutte le modifiche rilevanti a questo progetto sono documentate qui.
Formato basato su [Keep a Changelog](https://keepachangelog.com/it/1.1.0/); versionamento [SemVer](https://semver.org/lang/it/).

## [2.0.0] - 2026-08-09

Release di riparazione: al momento dell'audit **nessuna delle due immagini pubblicate era piu costruibile**. Contiene modifiche non retrocompatibili nell'uso dell'immagine.

### BREAKING

- L'immagine ha ora **`ENTRYPOINT ["ffmpeg"]`**: gli argomenti di `docker run` vanno direttamente a ffmpeg. Il vecchio `docker run <img> ffmpeg -i ...` diventa `docker run <img> -i ...`. Per una shell: `--entrypoint /bin/bash`.
- Il container gira come utente **non root** (`ffmpeg`, uid 1000), working dir `/data`. Su volumi montati appartenenti ad altri utenti serve `--user "$(id -u):$(id -g)"`.
- Base image portata da Debian 10/11 a **Debian 12**.
- Rimossi `Dockerfile-ffmpeg6`, `Containerfile`, `module.defs`, `scripts/` e il workflow `docker-publish-ffmpeg6.yml` (vedi *Rimosso*).
- `NVIDIA_DRIVER_CAPABILITIES` ristretto da `all` a `video,compute,utility`.

### Corretto

- **Base image fuori archivio**: `debian:10.10-slim` non buildava piu, gli indici APT di buster rispondono 404 su `deb.debian.org` (spostati su `archive.debian.org`). Base portata a Debian 12 (bookworm).
- **Pacchetto inesistente**: `Dockerfile-ffmpeg6` installava `python`, rimosso da Debian 11 in poi. La build falliva con `Unable to locate package python`.
- **Tag `:latest` mai pubblicato**: la regex semver del workflow girava su una `VERSION` a cui era gia stato appeso `-ffmpeg5.1.2`, quindi non matchava mai e il ramo che aggiungeva `:latest`/`:MAJOR`/`:MINOR` era codice morto. Il tagging usa ora `docker/metadata-action`.
- **README che puntava al registry sbagliato**: indicava `docker pull allannava/docker-ffmpeg-nvenc:latest` su Docker Hub mentre la CI pubblica su GHCR. Sommato al punto precedente, l'istruzione di installazione documentata non funzionava su nessuno dei due registry.
- **`--enable-nonfree` rimosso**: rendeva il binario FFmpeg **non ridistribuibile** su un registry pubblico, senza che alcuna componente nonfree fosse effettivamente abilitata. L'immagine e ora ridistribuibile sotto GPL-3.0-or-later.
- **`action.yml` inutilizzabile**: ricompilava FFmpeg da sorgente ad ogni invocazione (`image: 'Dockerfile'`) e passava il comando come singolo argomento a un'immagine senza `ENTRYPOINT`. Ora usa l'immagine pre-buildata da GHCR con wrapper shell per lo splitting degli argomenti.
- **`ENV DEBIAN_FRONTEND noninterac1tive`**: typo presente in tutti e tre i file di build, il valore non era valido e il frontend interattivo restava attivo.
- **Flag CUDA fantasma**: `--extra-cflags=-I/usr/local/cuda/include` e `--extra-ldflags=-L/usr/local/cuda/lib64` puntavano a directory inesistenti (nessun CUDA toolkit nell'immagine) e suggerivano capacita non presenti. NVENC richiede solo gli header `ffnvcodec`.
- **`apt-get update` scollegato da `apt-get install`**: causa classica di cache di layer stantia. Ora in un unico `RUN` con `--no-install-recommends` e pulizia di `/var/lib/apt/lists`.
- **`nv-codec-headers` non pinnato** nella variante FFmpeg 6.0 (clone di `master`): build non riproducibile e rischio di header piu recenti del driver installato. Ogni variante pinna ora il branch `sdk/*` minimo compatibile.
- **Dependabot** puntava a una directory `/tests` inesistente.
- Continuazioni di riga `\ ` (backslash + spazio) nei blocchi `./configure`, tollerate da BuildKit ma deprecate.

### Aggiunto

- **Workflow `ci.yml`**: lint (hadolint, shellcheck, actionlint), build + smoke test di tutte e tre le varianti su ogni push/PR, scan vulnerabilita Trivy con upload su code scanning. Include uno **schedule settimanale** per intercettare il marcire delle base image — e' esattamente cosi' che il repo si era rotto in silenzio.
- **`tests/smoke.sh`**: 18 asserzioni senza bisogno di GPU (presenza encoder NVENC, codec di contorno, assenza di `--enable-nonfree`, transcodifica reale end-to-end, non-root, assenza di toolchain e sorgenti nell'immagine finale).
- **`tests/gpu.sh`**: encoding reale `h264_nvenc`/`hevc_nvenc` su host con GPU NVIDIA.
- **Gate NVENC dentro il Dockerfile**: la build fallisce se gli encoder non finiscono nel binario, in entrambi gli stage.
- **Smoke test come gate di pubblicazione**: nessuna immagine viene pushata su GHCR senza aver passato i test.
- **Variante FFmpeg 7.1.1**, che diventa quella di default (`latest`).
- `--enable-libx265`: le librerie runtime di x265 erano installate ma l'encoder non era mai stato abilitato. Aggiunti anche `libass`, `libfreetype`, `libspeex`, `libtheora`, `libvorbis`, `libxml2`.
- **File `LICENSE`** (MIT per il repo) con nota esplicita sulla licenza GPL dell'artefatto, che il README dichiarava MIT.
- SBOM e provenance sulle immagini pubblicate.
- `CLAUDE.md`, `AGENTS.md`, `docs/audit/2026-08-09-audit-iniziale.md`, questo `CHANGELOG.md`.
- `.hadolint.yaml`.

### Modificato

- **Un solo `Dockerfile` parametrizzato** (`FFMPEG_VERSION`, `NVCODEC_BRANCH`, `DEBIAN_VERSION`) al posto di tre file quasi-cloni divergenti; le varianti sono una matrice nei workflow. Idem per i due workflow di publish quasi identici, ora uno solo.
- **Build multi-stage**: l'immagine finale contiene solo i binari e le librerie condivise. Prima portava dentro `build-essential`, `cmake`, `ninja-build`, `imagemagick`, i sorgenti FFmpeg scompattati, gli oggetti di `make`, e — verosimilmente ereditati da un Dockerfile HandBrake — `yad`, `expect`, `tcl8.6`, GTK3 e GStreamer in un'immagine di transcodifica headless.
- Rimossa l'installazione delle librerie `libav*` di distribuzione, inutilizzate dal binario compilato in `/usr/local`.
- Action aggiornate: `checkout@v4`, `setup-buildx-action@v3`, `login-action@v3`, `build-push-action@v6`, `metadata-action@v5`. Eliminati `::set-output` (deprecato) e `github-script@v4`.
- `MAINTAINER` (deprecato) sostituito da label OCI.
- `.dockerignore` esteso: prima escludeva solo `.github`.
- Cache buildx GHA condivisa fra build di test e build di pubblicazione.

### Rimosso

- **`Containerfile`**: base `registry.access.redhat.com/ubi8/ubi` ma comandi `apt-get` e pacchetti Debian — non poteva funzionare, e nessun workflow lo referenziava.
- **`Dockerfile-ffmpeg6`**: sostituito dalla matrice sul Dockerfile parametrizzato.
- **`module.defs`**: frammento del sistema di build di HandBrake, mai valutato da nulla in questo repo.
- **`scripts/`** (`base.sh`, `build-tools.sh`, `build-library.sh`, `build-ffmpeg.sh`): percorso di build parallelo mai invocato e comunque non funzionante — `build-ffmpeg.sh` leggeva `${PREFIX}/ffmpeg_configure_options` e `${PREFIX}/ffmpeg_extra_libs`, file che nessuno script generava.
- **`.github/workflows/docker-publish-ffmpeg6.yml`**: assorbito dalla matrice.

Recuperabili da git: `git checkout v1.0.1 -- scripts/ module.defs Containerfile`.

## [1.0.1] - 2023-05-16

### Aggiunto

- Workflow `docker-publish-ffmpeg6.yml` e `Dockerfile-ffmpeg6` (FFmpeg 6.0 su Debian 11).

## [1.0.0] - 2023-05-16

### Modificato

- Build FFmpeg 5.1.2 con `nv-codec-headers` pinnato a `sdk/11.0`.

## [0.1.2] - 2023-01-16

### Modificato

- `.dockerignore`.

## [0.1.1] - 2023-01-16

### Rimosso

- Trigger `schedule` dal workflow di publish.

## [0.1.0] - 2023-01-16

### Aggiunto

- Prima pubblicazione su GHCR via GitHub Actions.

[2.0.0]: https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/compare/v1.0.1...v2.0.0
[1.0.1]: https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/compare/v0.1.2...v1.0.0
[0.1.2]: https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/releases/tag/v0.1.0
