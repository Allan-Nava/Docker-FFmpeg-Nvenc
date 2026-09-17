# Docker-FFmpeg-Nvenc

[![CI](https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/actions/workflows/ci.yml/badge.svg)](https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/actions/workflows/ci.yml)
[![Publish](https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/actions/workflows/docker-publish.yml)

Immagine container con **FFmpeg compilato con supporto NVIDIA NVENC** (`h264_nvenc`, `hevc_nvenc`) per transcodifica accelerata da GPU.

Build multi-stage su Debian 12: nell'immagine finale ci sono solo i binari e le librerie condivise necessarie, nessun toolchain di compilazione.

## Immagini pubblicate

Registry: **GitHub Container Registry** (`ghcr.io`), non Docker Hub.

> ⚠️ **Stato al 17/09/2026: i tag qui sotto non sono ancora stati pubblicati.** L'ultimo tag del repo e
> `v1.0.1` (2023) e su GHCR `:latest` e ancora l'immagine del gennaio 2023: gira come **root**, ha
> `ENTRYPOINT /bin/bash` e un `NVIDIA_REQUIRE_CUDA` che ne impedisce l'avvio sugli host con driver
> recenti. L'immagine descritta in questa pagina e quella prodotta da `main`, pubblicata al primo tag
> `v2.0.0`. Dettagli: [audit 2026-09-17](docs/audit/2026-09-17-audit-stato-e-automazione.md) - stato:
> item `tag-v2-0-0` del [backlog](docs/backlog.md).

```
ghcr.io/allan-nava/docker-ffmpeg-nvenc
```

| Variante | FFmpeg | nv-codec-headers | Driver NVIDIA minimo | Tag |
|---|---|---|---|---|
| default | 7.1.1 | `sdk/12.1` | ≥ 530 | `latest`, `vX.Y.Z`, `latest-ffmpeg7.1.1`, `vX.Y.Z-ffmpeg7.1.1` |
| | 6.0 | `sdk/12.0` | ≥ 530 | `latest-ffmpeg6.0`, `vX.Y.Z-ffmpeg6.0` |
| | 5.1.2 | `sdk/11.0` | ≥ 470 | `latest-ffmpeg5.1.2`, `vX.Y.Z-ffmpeg5.1.2` |

Il branch di `nv-codec-headers` determina il **driver NVIDIA minimo** dell'host: se ottieni `This NVENC API is not compatible with the installed driver`, usa una variante più bassa o aggiorna il driver.

## Prerequisiti

- GPU NVIDIA con NVENC ([matrice di supporto](https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new))
- Driver NVIDIA (vedi tabella sopra)
- Docker + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html) (per `--gpus`)

## Uso

L'immagine ha **`ENTRYPOINT ["ffmpeg"]`**: gli argomenti che passi a `docker run` vanno direttamente a ffmpeg, non serve ripetere `ffmpeg`.

```shell
docker pull ghcr.io/allan-nava/docker-ffmpeg-nvenc:latest
```

Transcodifica accelerata da GPU:

```shell
docker run --rm --gpus all \
  --user "$(id -u):$(id -g)" \
  -v "$PWD/input:/data/input:ro" \
  -v "$PWD/output:/data/output" \
  ghcr.io/allan-nava/docker-ffmpeg-nvenc:latest \
  -i /data/input/input.mp4 -c:v h264_nvenc -preset p4 /data/output/output.mp4
```

Verifica che gli encoder ci siano (non serve GPU):

```shell
docker run --rm ghcr.io/allan-nava/docker-ffmpeg-nvenc:latest -hide_banner -encoders | grep nvenc
```

Shell dentro il container (per debug):

```shell
docker run --rm -it --entrypoint /bin/bash ghcr.io/allan-nava/docker-ffmpeg-nvenc:latest
```

### Note operative

- Il container gira come utente **non root** (uid 1000, `ffmpeg`), working dir `/data`. Se i volumi montati appartengono a un altro utente, passa `--user "$(id -u):$(id -g)"` come nell'esempio.
- `ffprobe` è incluso. `ffplay` no (build headless).
- `NVIDIA_DRIVER_CAPABILITIES` è impostato a `video,compute,utility` — il minimo per transcodificare.

## Codec abilitati

Encoder: `h264_nvenc`, `hevc_nvenc`, `libx264`, `libx265`, `libvpx-vp8/vp9`, `libmp3lame`, `libopus`, `libvorbis`, `libtheora`.
Filtri testo: `fontconfig`, `libfreetype`, `libass`.

Non è abilitato il **CUDA toolkit**: niente `scale_npp`, `libnpp`, `nvdec`/`cuvid` hardware-decode. NVENC richiede solo gli header `ffnvcodec`, che è quanto l'immagine installa. Se ti serve il decode accelerato, va aggiunta una base `nvidia/cuda:*-devel` e le opzioni `--enable-cuda-nvcc --enable-nvdec --enable-cuvid --enable-libnpp`.

## GitHub Action

Il repo espone anche una Action che esegue ffmpeg nell'immagine pre-buildata:

```yaml
- uses: Allan-Nava/Docker-FFmpeg-Nvenc@v2      # disponibile dal tag v2.0.0 (vedi avviso sopra)
  with:
    command: '-i input.mp4 -c:v libx264 -preset fast output.mp4'
```

⚠️ I runner GitHub-hosted **non hanno GPU**: dentro la Action gli encoder `*_nvenc` non sono utilizzabili. Serve un self-hosted runner con GPU e NVIDIA Container Toolkit.

## Sviluppo

Un solo `Dockerfile` parametrizzato genera tutte le varianti:

```shell
docker build \
  --build-arg FFMPEG_VERSION=6.0 \
  --build-arg NVCODEC_BRANCH=sdk/12.0 \
  -t ffmpeg-nvenc:6.0 .

./tests/smoke.sh ffmpeg-nvenc:6.0 6.0     # non richiede GPU
./tests/gpu.sh   ffmpeg-nvenc:6.0         # richiede GPU NVIDIA
```

La CI (`.github/workflows/ci.yml`) esegue lint (hadolint, shellcheck, actionlint), builda e testa tutte e tre le varianti su ogni push/PR, e gira **settimanalmente** per intercettare il marcire delle base image. La pubblicazione (`docker-publish.yml`) parte solo su push di tag `v*` e passa dagli stessi smoke test prima del push.

Vedi [CLAUDE.md](CLAUDE.md) / [AGENTS.md](AGENTS.md) per le convenzioni di lavoro e le trappole note, e [docs/audit/](docs/audit/) per l'audit del progetto.

### Backlog e roadmap

I todo del repo stanno in [`docs/backlog.md`](docs/backlog.md), che e la **sorgente unica**: uno script
idempotente apre, aggiorna e chiude una issue GitHub per ogni item (label `backlog-sync`) e crea le
milestone mancanti, schedulato da [`.github/workflows/backlog.yml`](.github/workflows/backlog.yml).
[`docs/roadmap.md`](docs/roadmap.md) e la vista per milestone, **generata** dal backlog.

```shell
python3 docs/scripts/backlog-lint.py             # valida il backlog (gate di CI)
python3 docs/scripts/generate-roadmap.py         # rigenera docs/roadmap.md (da committare)
python3 docs/scripts/sync-backlog-to-issues.py   # dry-run del sync verso le issue
```

Convenzioni degli item e trappole dell'API GitHub: [`docs/scripts/README.md`](docs/scripts/README.md).

## Contribuire

Issue e pull request benvenute. Ogni PR deve passare la CI: build + smoke test di tutte le varianti.

Le issue con label `backlog-sync` sono **generate** da [`docs/backlog.md`](docs/backlog.md): per
modificarne titolo o descrizione si edita il backlog, non la issue (il prossimo sync la riallinea).

## Licenza

I file di questo repository sono **MIT** (vedi [LICENSE](LICENSE)).

L'**immagine prodotta** è un'altra cosa: FFmpeg è compilato con `--enable-gpl --enable-version3` e collegato a libx264/libx265, quindi il binario è distribuito sotto **GPL-3.0-or-later**. La build non usa `--enable-nonfree`, quindi l'immagine è ridistribuibile.
