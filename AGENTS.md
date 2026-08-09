# AGENTS.md — Docker-FFmpeg-Nvenc

Repo di build di immagini container con **FFmpeg compilato con supporto NVIDIA NVENC** (`github.com/Allan-Nava/Docker-FFmpeg-Nvenc`). Pubblica su **GHCR** (`ghcr.io/allan-nava/docker-ffmpeg-nvenc`) via GitHub Actions ed espone una **GitHub Action** riusabile (`action.yml`).

Questo file definisce le regole operative per gli agent (Copilot, Claude, altri tool AI) quando lavorano in questo repository. Contenuto allineato a `CLAUDE.md`: se modifichi uno, aggiorna l'altro.

Struttura:

```
Dockerfile            -> FFmpeg 5.1.2 su debian:10.10-slim + nv-codec-headers sdk/11.0   (workflow docker-publish.yml)
Dockerfile-ffmpeg6    -> FFmpeg 6.0   su debian:11-slim   + nv-codec-headers master      (workflow docker-publish-ffmpeg6.yml)
Containerfile         -> variante UBI8 (NON referenziata da nessun workflow, rotta)
action.yml            -> GitHub Action "docker" che builda il Dockerfile e passa `command` come arg
module.defs           -> frammento make di HandBrake-contribs (NON usato dalla build)
scripts/              -> build ffmpeg "from source" fuori da Docker (NON usati dai Dockerfile)
.github/workflows/    -> build+push su GHCR, trigger SOLO su push di tag
```

## Regole di lavoro (SEMPRE)

- **Un tag = una pubblicazione immagine.** I workflow girano **solo** su `push` di tag (`tags: ['*']`): ogni tag `vX.Y.Z` fa partire due build e pubblica su GHCR. Non taggare "per igiene": si taggano solo cambi che devono produrre un'immagine nuova. Bump `minor` per novita sostanziali (nuova versione FFmpeg, nuova base image, nuovo target), `patch` per fix.
- **Ogni release taggata = sezione in `CHANGELOG.md`** (Keep a Changelog, in italiano) + `git tag -a vX.Y.Z -m "Release X.Y.Z"`. ATTENZIONE: il `CHANGELOG.md` **non esiste ancora**; alla prima release va creato ricostruendo lo storico dai tag esistenti (`v0.1.0`, `v0.1.1`, `v0.1.2`, `v1.0.0`, `v1.0.1`).
- **MAI `git push`**: lo fa sempre l'utente (qui vale doppio, un push di tag pubblica un'immagine pubblica su GHCR). **MAI `Co-Authored-By`** nei commit.
- **Documentare SEMPRE** audit, interventi, debug di build: doc `.md` in `docs/` (audit in `docs/audit/`, incident in `docs/incidents/`), senza chiederlo. Ogni doc: **schema/diagramma ASCII**, log allegati in `logs/`, riga nel CHANGELOG.
- **Allineare tutto**: ogni modifica fattuale va propagata a `Dockerfile`, `Dockerfile-ffmpeg6`, `Containerfile`, `README.md`, `action.yml`, workflow, CHANGELOG. I tre file di build sono **quasi-cloni**: un fix in uno va valutato per gli altri due o esplicitamente motivato.
- **Nessuna modifica dichiarata "fatta" senza build verificata.** Il repo non ha test: l'unica prova che un cambio al Dockerfile funzioni e `docker build`. Prima di dire che un fix funziona, buildare e riportare l'output reale.
- **Verificare la disponibilita reale dei pacchetti** prima di asserire che una base image funzioni: le base Debian usate qui sono EOL e i repo si spostano su `archive.debian.org`.

## Pattern per interventi sulle immagini

1. **Preflight**: verificare che la base image sia ancora supportata (repo APT raggiungibili) e che i pacchetti citati esistano in quella suite (`https://api.ftp-master.debian.org/madison?package=<pkg>&s=<suite>`).
2. **Build locale**: `docker build -f <Dockerfile> -t ffmpeg-nvenc:test .` con log su file (`| tee logs/build-<data>.log`); run lunghi in background.
3. **Smoke test funzionale** (non basta che la build passi):
   ```
   docker run --rm ffmpeg-nvenc:test ffmpeg -version
   docker run --rm ffmpeg-nvenc:test ffmpeg -hide_banner -encoders | grep nvenc   # attesi h264_nvenc, hevc_nvenc
   ```
   e, su host con GPU, una transcodifica reale con `--gpus all`.
4. **Dimensione**: `docker images`, annotare la size prima/dopo. L'immagine attuale porta dentro tutto il toolchain di build.
5. **Chiusura**: doc `.md` + log in `logs/` + CHANGELOG + tag (solo se va pubblicata) + README allineato.

## Trappole note / regole tecniche

- **Debian 10 (buster) e fuori archivio**: `deb.debian.org/debian/dists/buster` risponde **404** (verificato 2026-08-09), il contenuto e su `archive.debian.org`. Il `Dockerfile` principale (`debian:10.10-slim`) **non builda piu**: muore su `apt-get update`.
- **Il pacchetto `python` non esiste in Debian 11 (bullseye)**: rimosso, esistono solo `python2`/`python3`. `Dockerfile-ffmpeg6` lo installa nella lista deps -> **build fallita**. Usare `python3`.
- **`Containerfile` e rotto per costruzione**: base `registry.access.redhat.com/ubi8/ubi` ma usa `apt-get` e pacchetti Debian. Non e referenziato da nessun workflow. O si porta a `dnf` o si elimina.
- **`ENV DEBIAN_FRONTEND noninterac1tive`**: typo presente in **tutti e tre** i file di build; il valore non e valido. Se si tocca un file di build, correggerlo in tutti.
- **`apt-get update` e `apt-get install` in `RUN` separati**: cache di layer stantia. Vanno uniti nello stesso `RUN`, con `--no-install-recommends` e `rm -rf /var/lib/apt/lists/*` in coda.
- **`\` seguito da spazio** a fine riga nei blocchi `./configure`: BuildKit lo accetta ma emette warning; normalizzare quando si tocca quel blocco.
- **`--extra-cflags=-I/usr/local/cuda/include` / `--extra-ldflags=-L/usr/local/cuda/lib64` sono rumore**: nell'immagine **non c'e il CUDA toolkit**. NVENC richiede solo `nv-codec-headers` (pkg-config `ffnvcodec`).
- **`:latest` non viene MAI pubblicato**: la `VERSION` finisce sempre con suffisso `-ffmpeg5.1.2`/`-ffmpeg6.0`, quindi la regex semver `^v[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$` non matcha mai e il ramo che aggiunge `:latest`/`:MAJOR`/`:MINOR` e codice morto.
- **README vs realta del registry**: il README dice `docker pull allannava/docker-ffmpeg-nvenc:latest` (Docker Hub), la CI pubblica su `ghcr.io/allan-nava/docker-ffmpeg-nvenc:<tag>-ffmpeg5.1.2`.
- **`scripts/` e `module.defs` sono codice morto**: nessun Dockerfile/workflow li usa. `scripts/build-ffmpeg.sh` legge `${PREFIX}/ffmpeg_configure_options` e `${PREFIX}/ffmpeg_extra_libs`, file che **nessuno genera** -> fallisce comunque.
- **`nv-codec-headers` non pinnato in `Dockerfile-ffmpeg6`** (clone di `master`): build non riproducibile. Il `Dockerfile` principale e pinnato a `sdk/11.0`, quello e il pattern corretto.
- **Action deprecate nei workflow**: `::set-output`, `actions/github-script@v4` (usa `github.repos.get`, da v5 e `github.rest.repos.get`), `actions/checkout@v3`. Aggiornarle insieme, non a pezzi.
- **`action.yml` non e utilizzabile cosi com'e**: `runs.using: docker` con `image: Dockerfile` ricompila FFmpeg ad ogni invocazione e passa `${{ inputs.command }}` come **singolo argomento** a un'immagine senza `ENTRYPOINT` (`CMD ["/bin/bash"]`). Serve `image: docker://ghcr.io/...` + `ENTRYPOINT`.
- **`.dockerignore` contiene solo `.github`**: `scripts/`, `module.defs`, `README.md` finiscono nel build context inutilmente.
- **Nessun `LICENSE`** benche il README dichiari MIT, e la build usa `--enable-gpl --enable-nonfree` che rende l'**artefatto binario non ridistribuibile**.
- **`MAINTAINER` e deprecato**: usare `LABEL org.opencontainers.image.authors=`.
- **Piattaforma singola**: build `linux/amd64` only.

## Puntatori

- Audit iniziale del progetto: `docs/audit/2026-08-09-audit-iniziale.md`
- Registry immagini: `https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/pkgs/container/docker-ffmpeg-nvenc`
- Workflow: `.github/workflows/docker-publish.yml` (FFmpeg 5.1.2), `.github/workflows/docker-publish-ffmpeg6.yml` (FFmpeg 6.0)
- Riferimenti upstream: `nv-codec-headers` (`github.com/FFmpeg/nv-codec-headers`, branch `sdk/<ver>`), matrice driver/SDK NVENC nella doc NVIDIA Video Codec SDK
