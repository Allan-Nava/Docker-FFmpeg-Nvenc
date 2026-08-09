# CLAUDE.md — Docker-FFmpeg-Nvenc

Repo di build di immagini container con **FFmpeg compilato con supporto NVIDIA NVENC** (`github.com/Allan-Nava/Docker-FFmpeg-Nvenc`). Pubblica su **GHCR** (`ghcr.io/allan-nava/docker-ffmpeg-nvenc`) via GitHub Actions, ed espone una **GitHub Action** riusabile (`action.yml`).

```
Dockerfile              → sorgente UNICA, multi-stage, parametrizzata
                          ARG FFMPEG_VERSION / NVCODEC_BRANCH / DEBIAN_VERSION
tests/smoke.sh          → 17 asserzioni, nessuna GPU richiesta (gate di CI e di publish)
tests/gpu.sh            → encoding NVENC reale, richiede host con GPU NVIDIA
action.yml              → GitHub Action su immagine pre-buildata da GHCR
.github/workflows/ci.yml              → lint + build&test matrice + scan; push/PR + settimanale
.github/workflows/docker-publish.yml  → build → test → push su GHCR; solo su tag v*
docs/audit/             → audit del progetto
```

Le varianti sono una **matrice nei workflow**, non file duplicati:

| FFmpeg | `NVCODEC_BRANCH` | driver NVIDIA min | default |
|---|---|---|---|
| 7.1.1 | `sdk/12.1` | ≥ 530 | sì (`latest`) |
| 6.0 | `sdk/12.0` | ≥ 530 | no |
| 5.1.2 | `sdk/11.0` | ≥ 470 | no |

## Regole di lavoro (SEMPRE)

- **Un tag = una pubblicazione immagine.** Il workflow di publish gira **solo** su push di tag `v*`: ogni tag builda, testa e pubblica tutte e tre le varianti su GHCR. Non taggare "per igiene". Bump `major` per cambi non retrocompatibili nell'uso dell'immagine (ENTRYPOINT, utente, path), `minor` per novità sostanziali (nuova variante FFmpeg, nuova base image), `patch` per fix.
- **Ogni release taggata = sezione in `CHANGELOG.md`** (Keep a Changelog, in italiano) + `git tag -a vX.Y.Z -m "Release X.Y.Z"`.
- **MAI `git push`** — lo fa sempre l'utente (qui vale doppio: un push di tag pubblica immagini pubbliche su GHCR). **MAI `Co-Authored-By`** nei commit.
- **Documentare SEMPRE** audit, interventi, debug di build: doc `.md` in `docs/` (audit in `docs/audit/`, incident in `docs/incidents/`), **senza chiederlo**. Ogni doc: **schema/diagramma ASCII**, log allegati in `logs/`, riga nel CHANGELOG.
- **Allineare tutto**: ogni modifica fattuale va propagata a `Dockerfile`, `README.md`, `action.yml`, workflow, `tests/`, `CHANGELOG.md`, e a questo file + `AGENTS.md` (che vanno tenuti allineati fra loro).
- **Nessuna modifica dichiarata "fatta" senza build verificata.** L'unica prova che un cambio al Dockerfile funzioni è `docker build` seguito da `./tests/smoke.sh`. Riportare l'output reale, non l'intenzione.
- **Attenzione a leggere l'exit code giusto**: in `docker build ... > log; echo $?; tail log` l'exit riportato è quello di `tail`. Verificare l'assenza di `ERROR: failed to solve` nel log, non solo il codice finale.
- **Ogni nuova capability va coperta da un'asserzione in `tests/smoke.sh`.** Se una regressione non è rilevabile dai test, il test è incompleto.

## Pattern per interventi sulle immagini

1. **Preflight**: base image ancora supportata (repo APT raggiungibili) e pacchetti esistenti in quella suite — `https://api.ftp-master.debian.org/madison?package=<pkg>&s=<suite>`. Per FFmpeg, il vincolo `ffnvcodec` si legge dal `configure` della release: `curl -s https://raw.githubusercontent.com/FFmpeg/FFmpeg/n<ver>/configure | grep "ffnvcodec >="`.
2. **Build locale**: `docker build --build-arg FFMPEG_VERSION=… --build-arg NVCODEC_BRANCH=… -t ffmpeg-nvenc:test .` con log su file; run lunghi in background.
3. **Smoke test**: `./tests/smoke.sh ffmpeg-nvenc:test <versione-attesa>` — deve chiudere 17/17.
4. **Lint**: `hadolint` (via container), `shellcheck tests/*.sh`, `actionlint` **dalla root del repo** (fuori dal repo esce 3 "no project was found").
5. **Su GPU**: `./tests/gpu.sh` su un host con NVIDIA prima di promuovere un tag.
6. **Chiusura**: doc `.md` + log in `logs/` + CHANGELOG + README allineato + tag (solo se va pubblicata).

## Trappole note / regole tecniche

- **`ffmpeg … | grep -q` fallisce con exit 141 anche quando il test passa.** `grep -q` esce al primo match, ffmpeg riceve SIGPIPE e con `pipefail` la pipeline ritorna 141. Riguarda i gate nel `Dockerfile` (`SHELL … -o pipefail`) **e gli step `run:` dei workflow** (Actions usa `bash -e -o pipefail` di default). Pattern corretto: redirigere su file, poi `grep` sul file. Già costato una build in questo repo.
- **Le base Debian marciscono in silenzio.** buster è fuori da `deb.debian.org` (404, contenuto su `archive.debian.org`) — è così che il repo si è rotto senza che nessuno se ne accorgesse. Bookworm è già `oldstable`. Lo **schedule settimanale in `ci.yml` esiste apposta**: se fallisce di lunedì senza che nessuno abbia toccato il codice, quasi certamente è marcita una base o un repo APT.
- **Verificare che un pacchetto esista nella suite prima di usarlo.** `python` non esiste da bullseye in poi (solo `python2`/`python3`) e questo bloccava la variante FFmpeg 6.0.
- **I nomi versionati dei pacchetti runtime sono legati alla suite**: `libx264-164`, `libx265-199`, `libvpx7` sono bookworm. Cambiando `DEBIAN_VERSION` vanno riallineati o lo stage runtime non installa nulla.
- **`NVCODEC_BRANCH` determina il driver NVIDIA minimo dell'host.** Non alzarlo senza motivo: `sdk/13.0` richiede driver molto recenti. Il vincolo minimo è quello del `configure` di FFmpeg (5.1 → ≥ 9.1.23.1, 6.0 → ≥ 12.0.16.0, 7.1 → ≥ 12.1.14.0); scegliere il branch **più basso** che lo soddisfa. Sintomo di mismatch a runtime: `This NVENC API is not compatible with the installed driver`.
- **NVENC non richiede il CUDA toolkit**, bastano gli header `ffnvcodec`. Non reintrodurre `--extra-cflags=-I/usr/local/cuda/include` / `--extra-ldflags=-L/usr/local/cuda/lib64`: nell'immagine quelle directory non esistono e suggeriscono capacità assenti. Servono solo se si abilita davvero `--enable-cuda-nvcc`/`--enable-libnpp`/`--enable-nvdec`, che richiedono una base `nvidia/cuda:*-devel`.
- **MAI `--enable-nonfree`** su un'immagine pubblicata: rende il binario **non ridistribuibile**. `tests/smoke.sh` ha un'asserzione dedicata. Lo stesso vale per `libfdk-aac`. L'immagine è GPL-3.0-or-later (per libx264/libx265), il repo è MIT: sono due licenze diverse, non confonderle.
- **L'immagine ha `ENTRYPOINT ["ffmpeg"]` e gira come utente non root (uid 1000)**, workdir `/data`. Gli esempi in doc vanno scritti senza ripetere `ffmpeg`; per una shell serve `--entrypoint /bin/bash`; su volumi montati serve `--user "$(id -u):$(id -g)"`.
- **La GitHub Action non può usare NVENC sui runner GitHub-hosted** (nessuna GPU): solo encoding CPU, oppure self-hosted runner con NVIDIA Container Toolkit. `action.yml` passa il comando via wrapper `bash -c` perché con `ENTRYPOINT ffmpeg` un singolo elemento in `args` arriverebbe come **un solo argomento**.
- **Il tagging dei workflow usa `docker/metadata-action`**, con `suffix=-ffmpeg<ver>` per variante più un secondo blocco senza suffisso per la sola variante `default: true`. La versione precedente applicava una regex semver a una stringa che il suffisso rendeva strutturalmente non-matchabile: `:latest` non veniva mai pubblicato. Se si tocca il tagging, verificare i tag effettivi su GHCR dopo il primo tag.
- **`shellcheck` esce 1 anche su finding `info`**: un `SC20xx` informativo basta a rompere la CI. Usare direttive `# shellcheck disable=` mirate e motivate.
- **`hadolint`**: `DL3008` (pin versioni apt) è ignorato in `.hadolint.yaml` — pinnare le versioni Debian bloccherebbe le patch di sicurezza ad ogni point release.
- **Il build context passa dal `.dockerignore`**: `docs/`, `tests/`, `*.md` sono esclusi. Se un file nuovo serve alla build, va tolto dall'ignore.

## Puntatori

- Audit del progetto: `docs/audit/2026-08-09-audit-iniziale.md`
- Registry: `https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/pkgs/container/docker-ffmpeg-nvenc`
- Matrice GPU/NVENC NVIDIA: `https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new`
- `nv-codec-headers`: `https://github.com/FFmpeg/nv-codec-headers` (branch `sdk/<ver>`)
- Codice rimosso in v2.0.0 (recuperabile): `git checkout v1.0.1 -- scripts/ module.defs Containerfile`
