# Quickstart Demo — 5 Dakikada Hasarİ / 5-Minute Hasarİ Demo

> Bu rehber tek bir hedef için yazıldı: **yeni bir geliştiricinin ya da değerlendiricinin 5 dakika içinde** çalışan bir Hasarİ demo'su görmesi. Eğitim, üretim deploy veya derin mimari için README ve diğer dokümanlara bak.
>
> This guide has a single goal: **get a new developer or evaluator from zero to a working Hasarİ demo in 5 minutes.** For training, production deployment, or deep architecture, see the README and other guides.

---

## İçindekiler / Table of contents

- [Türkçe](#türkçe)
  - [Önkoşullar](#önkoşullar)
  - [Adımlar](#adımlar)
  - [Beklenen çıktı](#beklenen-çıktı)
  - [Sorun giderme](#sorun-giderme)
- [English](#english)
  - [Prerequisites](#prerequisites)
  - [Steps](#steps)
  - [Expected output](#expected-output)
  - [Troubleshooting](#troubleshooting)

---

## Türkçe

### Önkoşullar

Aşağıdakileri **önceden** kurmuş olmalısın. Toplam disk ~3 GB, RAM ≥ 8 GB öneriyoruz.

| Araç | Sürüm | Doğrulama |
|---|---|---|
| **Docker Desktop** | ≥ 24.0 (Compose v2 dahili) | `docker --version` ve `docker compose version` |
| **Node.js** | 20 LTS ya da üzeri | `node --version` |
| **pnpm** | 9.0+ | `corepack enable && corepack prepare pnpm@9.12.0 --activate` sonra `pnpm --version` |
| **Git** | herhangi yeni sürüm | `git --version` |

**GPU gerekmez.** Bu demo backend'i CPU üzerinde çalıştırır (`ML_DEVICE: cpu`). GPU için bkz. [DOCKER.md](../DOCKER.md).

**Model ağırlıkları**: `services/ml/runs/bundles/` altında en az bir snapshot olmalı. Repo bunu içermiyorsa, bkz. [Sorun giderme — model weights](#sorun-giderme).

### Adımlar

**1. Repo'yu al ve bağımlılıkları kur** (~90 sn)

```powershell
git clone https://github.com/your-org/arac-hasar-v2.git
cd arac-hasar-v2
pnpm install
```

**2. Backend stack'i ayağa kaldır** (~60 sn, ilk açılışta image build için biraz daha)

```powershell
# Repo kökünden — Postgres + Redis + MinIO + FastAPI + Celery worker
docker compose up -d
```

Sağlık kontrolü:

```powershell
docker compose ps                # tüm servisler "running"/"healthy" olmalı
curl http://localhost:8000/health
# {"status":"ok","ml_loaded":true,"version":"0.1.0", ...}
```

**3. Web uygulamasını başlat** (~5 sn) — ayrı terminal

```powershell
pnpm dev:web
```

Çıktıda `▲ Next.js 15.x  - Local: http://localhost:3000` görmelisin.

**4. Tarayıcıdan demoyu aç**

1. `http://localhost:3000` — landing sayfası açılır.
2. Üst menüden **Yeni inceleme** → `/inspect` sayfasına git.
3. Sürükle-bırak alanına bir araç fotoğrafı bırak (JPG/PNG/WebP, < 12 MB). Elinde yoksa CarDD örneklerinden veya açık kaynak `unsplash.com/s/photos/car-damage` görsellerinden indir.
4. **Mod**: "Hızlı (sync)" seç (tek fotoğraf için).
5. **İncelemeyi başlat** → 5–15 saniyede sonuç ekranı açılır.

### Beklenen çıktı

`/results/{id}` ekranında üç sekme görmelisin: **Genel**, **Parçalar**, **Hasarlar**. JSON şeması böyle olur:

```text
+--------------------------------------------------------------+
|  Inspection #8c1f...                       toplam: 5.500 ₺   |
+--------------------------------------------------------------+
|  Genel  |  Parçalar  |  Hasarlar  |  Görselleştirme           |
+--------------------------------------------------------------+
|                                                              |
|  Hasarlı parça:   1   |   Hasarsız parça:   3                |
|  Toplam hasar:    2                                          |
|  Genel şiddet:    Orta                                       |
|  Öneri:           Tamir + boya gerekli                       |
|                                                              |
|  +----------------------------------------------------+      |
|  | ön_tampon                                  Orta    |      |
|  |  - Göçük (orta)         2.500 – 5.500 ₺            |      |
|  |  - Çizik (hafif)          400 – 1.200 ₺            |      |
|  +----------------------------------------------------+      |
|  | kaput                                     Temiz    |      |
|  +----------------------------------------------------+      |
|                                                              |
+--------------------------------------------------------------+
```

**Visualization sekmesi**: 3 maskeli PNG — annotated (damage + part overlay), parts (sadece parça maskeleri), damages (sadece hasar maskeleri). Backend bunları MinIO'da saklar ve presigned URL ile sunar.

API'den aynı sonucu komut satırından da alabilirsin:

```powershell
$env:BASE = "http://localhost:8000"
# Önce hesap oluştur
$tokens = (curl -X POST "$env:BASE/auth/register" `
    -H "Content-Type: application/json" `
    -d '{"email":"demo@local.dev","password":"DemoPass1234"}' | ConvertFrom-Json)
$env:ACCESS_TOKEN = $tokens.access_token

# Sonra sync inceleme
curl -X POST "$env:BASE/api/v1/inspect/sync" `
    -H "Authorization: Bearer $env:ACCESS_TOKEN" `
    -F "file=@path\to\damage.jpg"
```

### Sorun giderme

| Belirti | Sebep | Çözüm |
|---|---|---|
| `bind: address already in use :::5432` | Yerel Postgres çalışıyor | `docker compose down` veya yerel Postgres servisini durdur (`Stop-Service postgresql-x64-16`) |
| `bind: address already in use :::3000` | Başka bir Next.js / Grafana 3000'i tutuyor | `pnpm dev:web -- --port 3100` ile farklı port; ya da çakışan süreci kapat |
| `bind: address already in use :::8000` | Başka FastAPI / uvicorn süreci | `docker compose down` sonra `Get-Process \| Where-Object {$_.ProcessName -eq "python"}` ile kontrol |
| Backend 200 ama `/inspect` sonsuz yükleniyor | Celery worker düşmüş ya da Redis bağlanmamış | `docker compose logs worker redis` |
| `"ml_loaded": false` 5 dakikadan uzun sürer | Model ağırlıkları eksik | `services/ml/runs/bundles/` altına bir snapshot koy ya da `MODEL_SNAPSHOT_DIR` env'i ile yolu göster (bkz. [docker-compose.yml](../docker-compose.yml) yorumları) |
| MinIO console açıldı ama `inspections` bucket yok | `minio-init` container'ı erken kapanmış | `docker compose up minio-init` ile tekrar koştur; idempotent'tir |
| Web `Failed to fetch http://localhost:8000` | Backend henüz hazır değil | 30-60 sn bekle, sonra `curl http://localhost:8000/health` |
| Tarayıcı `Network Error` / CORS | `CORS_ORIGINS` env'inde `http://localhost:3000` yok | `services/backend/.env`'i kontrol; default değer 3000'i içerir |

Daha fazlası: [DEPLOY_GUIDE.md — Troubleshooting](DEPLOY_GUIDE.md#troubleshooting) ve [DOCKER.md](../DOCKER.md).

---

## English

### Prerequisites

You must have these installed beforehand. Plan for ~3 GB disk, RAM ≥ 8 GB.

| Tool | Version | Verify |
|---|---|---|
| **Docker Desktop** | ≥ 24.0 (bundled Compose v2) | `docker --version` and `docker compose version` |
| **Node.js** | 20 LTS or later | `node --version` |
| **pnpm** | 9.0+ | `corepack enable && corepack prepare pnpm@9.12.0 --activate` then `pnpm --version` |
| **Git** | any recent | `git --version` |

**No GPU required.** This demo runs the backend on CPU (`ML_DEVICE: cpu`). For GPU, see [DOCKER.md](../DOCKER.md).

**Model weights**: at least one snapshot must exist under `services/ml/runs/bundles/`. If the repo does not ship one, see [Troubleshooting — model weights](#troubleshooting).

### Steps

**1. Clone and install** (~90 s)

```bash
git clone https://github.com/your-org/arac-hasar-v2.git
cd arac-hasar-v2
pnpm install
```

**2. Bring up the backend stack** (~60 s; longer on first image build)

```bash
# From the repo root — Postgres + Redis + MinIO + FastAPI + Celery worker
docker compose up -d
```

Health check:

```bash
docker compose ps                # all services must be running/healthy
curl http://localhost:8000/health
# {"status":"ok","ml_loaded":true,"version":"0.1.0", ...}
```

**3. Start the web app** (~5 s) — separate terminal

```bash
pnpm dev:web
```

You should see `▲ Next.js 15.x  - Local: http://localhost:3000`.

**4. Open the demo in a browser**

1. Visit `http://localhost:3000` — the landing page loads.
2. From the top menu, click **Yeni inceleme** to reach `/inspect`.
3. Drag-drop a vehicle photo (JPG/PNG/WebP, < 12 MB). No sample? Pull one from `unsplash.com/s/photos/car-damage` or the public CarDD samples.
4. **Mode**: select "Hızlı (sync)" for a single photo.
5. Click **İncelemeyi başlat** — results render in 5–15 s.

### Expected output

The `/results/{id}` view shows three tabs: **Genel** (Overview), **Parçalar** (Parts), **Hasarlar** (Damages):

```text
+--------------------------------------------------------------+
|  Inspection #8c1f...                       total: 5,500 TL   |
+--------------------------------------------------------------+
|  Overview | Parts | Damages | Visualization                  |
+--------------------------------------------------------------+
|                                                              |
|  Damaged parts:  1   |   Clean parts:  3                     |
|  Total damages:  2                                           |
|  Overall:        Moderate                                    |
|  Recommendation: Repair + paint                              |
|                                                              |
|  +----------------------------------------------------+      |
|  | front_bumper                            moderate   |      |
|  |  - dent (moderate)      2,500 – 5,500 TL           |      |
|  |  - scratch (light)        400 – 1,200 TL           |      |
|  +----------------------------------------------------+      |
|  | hood                                       clean   |      |
|  +----------------------------------------------------+      |
|                                                              |
+--------------------------------------------------------------+
```

**Visualization tab**: 3 mask PNGs — `annotated` (damage + part overlay), `parts` (part masks only), `damages` (damage masks only). The backend persists them in MinIO and serves them via presigned URLs.

You can reach the same result from the shell:

```bash
export BASE=http://localhost:8000

# Create an account
TOKENS=$(curl -s -X POST "$BASE/auth/register" \
    -H "Content-Type: application/json" \
    -d '{"email":"demo@local.dev","password":"DemoPass1234"}')
ACCESS_TOKEN=$(echo "$TOKENS" | jq -r .access_token)

# Run a sync inspection
curl -X POST "$BASE/api/v1/inspect/sync" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -F "file=@path/to/damage.jpg"
```

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `bind: address already in use :::5432` | Local Postgres running | `docker compose down`, or stop the local service (`brew services stop postgresql@16` / `sudo systemctl stop postgresql`) |
| `bind: address already in use :::3000` | Another Next.js / Grafana on 3000 | `pnpm dev:web -- --port 3100`, or kill the conflicting process |
| `bind: address already in use :::8000` | Another uvicorn / FastAPI process | `docker compose down`, then `lsof -i :8000` (macOS/Linux) or `Get-NetTCPConnection -LocalPort 8000` (Windows) |
| Backend returns 200 but `/inspect` hangs forever | Celery worker crashed or Redis unreachable | `docker compose logs worker redis` |
| `"ml_loaded": false` for > 5 min | Model weights missing | Drop a snapshot into `services/ml/runs/bundles/`, or set `MODEL_SNAPSHOT_DIR` (see [docker-compose.yml](../docker-compose.yml) comments) |
| MinIO console up but `inspections` bucket missing | `minio-init` container exited too early | `docker compose up minio-init` (idempotent) |
| Web shows `Failed to fetch http://localhost:8000` | Backend still warming up | Wait 30–60 s, retry `curl http://localhost:8000/health` |
| Browser `Network Error` / CORS | `CORS_ORIGINS` env missing `http://localhost:3000` | Check `services/backend/.env`; the default includes port 3000 |

More: [DEPLOY_GUIDE.md — Troubleshooting](DEPLOY_GUIDE.md#troubleshooting) and [DOCKER.md](../DOCKER.md).

---

## Next steps / Sonraki adımlar

- **Run the desktop / mobile apps** — see [README.md → Hızlı başlangıç](../README.md#hızlı-başlangıç).
- **Explore the REST API** — [docs/API_GUIDE.md](API_GUIDE.md).
- **Understand the ML pipeline** — [docs/MODEL_GUIDE.md](MODEL_GUIDE.md).
- **Deploy to Render.com** — [docs/DEPLOY_GUIDE.md](DEPLOY_GUIDE.md).
