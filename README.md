# Hasarİ — Araç Hasar Tespiti v2

> AI-powered, part-centric vehicle damage detection and cost estimation — web + desktop + mobile + backend + ML, all in one monorepo.

![status](https://img.shields.io/badge/status-pilot--production-orange)
![node](https://img.shields.io/badge/node-20%2B-brightgreen)
![python](https://img.shields.io/badge/python-3.11-blue)
![license](https://img.shields.io/badge/code-MIT-yellow)
![data-license](https://img.shields.io/badge/data-CarDD%20academic-red)

## What it is

Hasarİ is a multi-platform application that detects damage on a car from a photograph, identifies which body part is affected, estimates the severity, and produces a Turkish-Lira repair cost range — in under 8 seconds. It targets minor everyday damage (bumper scratches, small dents, headlight cracks) where the cost of an in-person appraiser is disproportionate to the repair itself.

The system runs three YOLO models in parallel and merges their output with intelligent IoU matching, so every detected damage is anchored to a specific part. Clean (undamaged) parts are reported too, so the user sees the full vehicle view, not just a list of defects.

## Features

- **Three platforms, one codebase**: Next.js 15 web, Tauri 2 desktop (Win/macOS/Linux), React Native + Expo mobile (iOS/Android)
- **Three ML models running in parallel**: damage segmentation (YOLO11m-seg, 6 classes), parts segmentation (YOLO11s-seg, 21 classes), severity classification (YOLO11n-cls, 3 classes)
- **Part-centric output**: every damage is matched to a body part via IoU; every clean part is reported too
- **Turkish-Lira cost engine**: ranges calibrated to local OEM/aftermarket parts and labor rates
- **Sync + async inspection modes**: sync for ≤5 photos with inline results; async with Celery + Redis for batches up to 20 with WebSocket progress
- **JWT auth + legacy API-key fallback**: full register/login/refresh flow, role-based admin
- **Bilingual UI**: Turkish (primary) and English across all three apps via next-intl (web) and i18next (mobile/desktop)
- **Production-grade backend**: FastAPI + Postgres + Redis + S3/MinIO + Alembic migrations + Prometheus metrics
- **Internationalized cost & damage labels**: damage types and 21 part names available in TR/EN

## Tech stack

| Layer | Stack |
|---|---|
| Web | Next.js 15 (App Router), React 18, Tailwind CSS, next-intl |
| Desktop | Tauri 2, Vite, React 18, Tailwind, i18next |
| Mobile | React Native + Expo, i18next, expo-secure-store |
| Backend | FastAPI, Celery, SQLAlchemy, Pydantic v2, Alembic |
| Datastore | Postgres 16, Redis 7, MinIO (S3-compatible) |
| ML | PyTorch 2.4 (CUDA 12.8), Ultralytics YOLO11 (m-seg, s-seg, n-cls) |
| Observability | Prometheus, Grafana, Sentry (planned) |
| Deploy | Docker Compose (dev), Render.com (pilot) |

## Quick start

```powershell
# 1. Clone + install
git clone https://github.com/your-org/arac-hasar-v2.git
cd arac-hasar-v2
pnpm install

# 2. Start backend (Postgres + Redis + MinIO + FastAPI + Celery) — from repo root
docker compose up -d                                         # detached: api on :8000, MinIO on :9000/:9001

# 3. Web (separate terminal, from repo root)
pnpm dev:web                                                 # http://localhost:3000
```

Then visit `http://localhost:3000`. Swagger lives at `http://localhost:8000/docs`. See [Hızlı başlangıç](#hızlı-başlangıç) below for desktop, mobile, ML, and data setup. New to the project? Follow the **[5-minute demo guide → docs/QUICKSTART_DEMO.md](docs/QUICKSTART_DEMO.md)**.

## Architecture

```
                          ┌──────────────────────┐
                          │   FastAPI Backend    │
                          │  + Celery + Redis    │
                          │  + Postgres + MinIO  │
                          └──────────┬───────────┘
                                     │ /api/v1/*  (REST + WebSocket)
        ┌────────────────┬───────────┴─────────────┬───────────────┐
        │                │                         │               │
   ┌────┴─────┐     ┌────┴─────┐             ┌─────┴─────┐    ┌────┴────┐
   │ Next.js  │     │ Tauri 2  │             │ React     │    │  ML     │
   │  Web     │     │ Desktop  │             │ Native    │    │ Pipeline│
   │ (3000)   │     │ (native) │             │ Mobile    │    │ YOLO11  │
   └──────────┘     └──────────┘             └───────────┘    └─────────┘
        └────────── packages/ui (shared React) ───┘
        └────────── packages/types (shared TS contract) ─┘
```

**Inference flow (single image):**

```
upload → S3 → ┬─ damage YOLO11m-seg ──┐
              ├─ parts  YOLO11s-seg ──┼─→ IoU match → severity classifier (per damage crop)
              └─ severity yolo11n-cls─┘                       │
                                                              ▼
                                                  Part-centric output → cost engine → JSON
```

## Repository layout

```
arac-hasar-v2/
├── apps/
│   ├── web/                  # Next.js 15 — public web app
│   │   ├── app/              # App Router pages
│   │   ├── components/       # Header, Footer, PartList, ResultsTabs
│   │   └── messages/         # tr.json, en.json (next-intl)
│   ├── desktop/              # Tauri 2 + Vite — Windows/macOS/Linux
│   │   ├── src/
│   │   │   └── locales/      # tr.json, en.json (i18next)
│   │   └── src-tauri/        # Rust shell
│   └── mobile/               # React Native + Expo — iOS/Android
│       ├── screens/
│       └── locales/          # tr.json, en.json (i18next)
├── packages/
│   ├── ui/                   # Shared React components + Tailwind preset
│   └── types/                # Backend ↔ frontend TS contract
├── services/
│   ├── backend/              # FastAPI + Celery + Postgres + S3/MinIO
│   │   ├── main.py           # routes
│   │   ├── auth.py           # JWT register/login/refresh/me
│   │   ├── ml_service.py     # in-process model wrapper
│   │   ├── worker.py         # Celery tasks
│   │   ├── ws.py             # WebSocket progress channel
│   │   └── migrations/       # Alembic
│   └── ml/                   # YOLO11 training, pipeline, severity, cost engine
│       ├── pipeline.py
│       ├── train_all.py      # orchestrator
│       ├── cost_engine.py
│       └── runs/             # training artifacts (DO NOT TOUCH while training)
├── scripts/                  # Dataset download + verification
├── tools/                    # Model export (TFLite/CoreML/ONNX), regression
├── observability/            # Prometheus + Grafana configs
├── docs/                     # Operational guides (see below)
└── render.yaml               # Render.com deploy spec
```

## Documentation

| Document | Audience | What's inside |
|---|---|---|
| [docs/QUICKSTART_DEMO.md](docs/QUICKSTART_DEMO.md) | First-time evaluators | 5-minute "see the demo working" walkthrough (TR + EN) with troubleshooting |
| [docs/API_GUIDE.md](docs/API_GUIDE.md) | Backend integrators | Every REST endpoint with curl examples, request/response schemas, error codes |
| [docs/AUTH_FLOW.md](docs/AUTH_FLOW.md) | Frontend developers | JWT register/login/refresh sequence diagrams, token TTLs, per-platform storage |
| [docs/DEPLOY_GUIDE.md](docs/DEPLOY_GUIDE.md) | DevOps / operators | Render.com walkthrough, env vars, smoke tests, rollback |
| [docs/USER_GUIDE_TR.md](docs/USER_GUIDE_TR.md) | End users (Turkish) | Adım adım inceleme rehberi — web/mobil/desktop |
| [docs/MODEL_GUIDE.md](docs/MODEL_GUIDE.md) | ML engineers | Model performance, retraining commands, known failure modes |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Engineers | Pipeline internals, IoU matching, part-centric reorganization |
| [DATA.md](DATA.md) | ML / data engineers | Datasets, licenses, training order |
| [services/backend/README.md](services/backend/README.md) | Backend devs | Endpoint list, auth, env vars |
| [docs/PILOT_ONBOARDING.md](docs/PILOT_ONBOARDING.md) | Pilot customers | First-week setup checklist |
| [docs/LAUNCH_CHECKLIST.md](docs/LAUNCH_CHECKLIST.md) | Engineering / PM | Pre-launch sign-off gates |
| [docs/SECURITY.md](docs/SECURITY.md) | Security / compliance | Threat model, KVKK/GDPR notes |

## ML model performance

| Model | Architecture | Classes | Dataset | Epochs | Key metric | Inference (RTX 5050 8GB) |
|---|---|---|---|---|---|---|
| Damage segmentation | YOLO11m-seg | 6 | CarDD (academic, ~4k images) | 120 | mAP50_M = 0.683, mAP50-95_M = 0.509 | ~45 ms/image |
| Parts segmentation | YOLO11s-seg | 21 | Combined parts (Roboflow + CarPartsDB) | 50 | mAP50_M ≈ 0.72 | ~30 ms/image |
| Severity classifier | YOLO11n-cls | 3 (hafif/orta/agir) | Roboflow Severity | 30 | val_acc = 0.742 | ~12 ms/crop |

All three models run in parallel per image; end-to-end (model + IoU match + severity per damage + cost) is well under 8 seconds for typical 4-photo inspections. See [docs/MODEL_GUIDE.md](docs/MODEL_GUIDE.md) for full performance breakdown, known limitations, and retraining instructions.

## Hızlı başlangıç (Türkçe)

### Önkoşullar
- **Node.js 20+** ve **pnpm 9+** (`corepack enable && corepack prepare pnpm@9.12.0 --activate`)
- **Python 3.11** (ML için)
- **Docker + Docker Compose** (backend stack için)
- **Rust 1.77+** (sadece desktop için, `rustup` ile)
- **NVIDIA GPU + CUDA 12.8+** (eğitim için, opsiyonel)

### 1-2. Bağımlılıklar + backend
```powershell
pnpm install
# Repo kökünden — backend stack (FastAPI + Celery + Postgres + Redis + MinIO):
docker compose up -d
# Swagger:       http://localhost:8000/docs
# MinIO console: http://localhost:9001  (minioadmin/minioadmin)
# Postgres:      localhost:5432   Redis: localhost:6379
```

> Alternatif: `services\backend\docker-compose.yml` ML-bundled (GPU) varyantını içerir. Sıradan dev için repo kökündeki compose yeterlidir.

### 3. Web (paralel terminal)
```powershell
pnpm dev:web                                                 # http://localhost:3000
```

### 4. Desktop (paralel terminal)
```powershell
pnpm --filter @arac-hasar/desktop tauri:dev
```

### 5. Mobile (Expo)
```powershell
pnpm --filter @arac-hasar/mobile start
# Expo Go ile QR tara, veya iOS/Android emülatör
```

### 6. ML ortamı (eğitim için)
```powershell
cd services\ml
powershell -ExecutionPolicy Bypass -File setup.ps1
# Linux/macOS/WSL: bash setup.sh
```

### 7. Veri
```powershell
python scripts\download_pretrained.py --all
python scripts\download_data.py --cardd-hf
$env:ROBOFLOW_API_KEY = "..."
python scripts\download_data.py --roboflow-severity
python scripts\verify_data.py
```

## Komut referansı

| Komut | İşlevi |
|---|---|
| `pnpm dev:web` | Next.js dev server (3000) |
| `pnpm --filter @arac-hasar/desktop tauri:dev` | Tauri pencere + Vite HMR |
| `pnpm dev:mobile` | Expo Metro bundler |
| `pnpm backend:docker` | Tüm backend stack |
| `pnpm backend:dev` | Sadece FastAPI (uvicorn reload, host 0.0.0.0:8000 — venv'yi önceden aktive et) |
| `pnpm data:download` | Veri indirme orchestrator |
| `pnpm build` | Tüm uygulamaları derle |
| `pnpm typecheck` | Tüm workspace'te TS kontrolü |

## API contract (summary)

Backend endpoints (full reference: [docs/API_GUIDE.md](docs/API_GUIDE.md)):

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/register` | Create user, returns access + refresh tokens |
| `POST` | `/auth/login` | Email + password → tokens |
| `POST` | `/auth/refresh` | Refresh → new access token |
| `GET`  | `/auth/me` | Current user |
| `GET`  | `/health` | Health check (ml_loaded, status) |
| `GET`  | `/api/v1/version` | Version + build info |
| `POST` | `/api/v1/inspect?mode=sync\|async` | Multi-image inspection |
| `POST` | `/api/v1/inspect/sync` | Single-image fast path |
| `GET`  | `/api/v1/inspect/{id}` | Status + result |
| `GET`  | `/api/v1/inspect/{id}/visualization/{annotated\|parts\|damages}` | Presigned PNG redirect |
| `GET`  | `/api/v1/inspect` | Paginated history |
| `DELETE` | `/api/v1/inspect/{id}` | Delete (owner only) |
| `WS`   | `/api/v1/inspect/{id}/stream` | Async progress push |

## Output format (part-centric)

```json
{
  "inspection_id": "uuid",
  "parts": [
    {
      "name": "front_bumper",
      "name_tr": "Ön Tampon",
      "status": "moderate_damage",
      "damage_count": 2,
      "damages": [
        { "type": "dent", "type_tr": "Göçük", "severity": {"level": "orta"}, "cost": {"min_tl": 2500, "max_tl": 5500} },
        { "type": "scratch", "type_tr": "Çizik", "severity": {"level": "hafif"}, "cost": {"min_tl": 400, "max_tl": 1200} }
      ],
      "part_cost_min_tl": 2900,
      "part_cost_max_tl": 6700
    },
    { "name": "hood", "name_tr": "Kaput", "status": "clean", "damage_count": 0, "damages": [] }
  ],
  "summary": {
    "damaged_parts_count": 3,
    "clean_parts_count": 4,
    "total_cost_range_tl": [6800, 14500],
    "repair_recommendation": "tamir_boya",
    "repair_recommendation_tr": "Tamir + boya gerekli"
  }
}
```

Full schema lives in `packages/types/src/inspection.ts`.

## Yol haritası

**v0.1 (MVP — tamamlandı, pilot-production):**
- [x] Monorepo iskeleti (pnpm workspace), paylaşılan `packages/ui` + `packages/types`
- [x] Backend FastAPI: JWT auth (register/login/refresh/me), `/api/v1/inspect` sync+async, WebSocket progress (`/api/v1/inspect/{id}/stream`), Postgres + Alembic migrations, Redis, S3/MinIO storage, Prometheus `/metrics`
- [x] ML pipeline: YOLO11m-seg (damage, 6 cls) + YOLO11s-seg (parts, 21 cls) + YOLO11n-cls (severity, 3 cls) paralel, IoU-eşleştirme, `cost_table.yaml` tabanlı TL maliyet motoru
- [x] Web (Next.js 15 App Router), Desktop (Tauri 2 + Vite), Mobile (RN + Expo)
- [x] TR/EN i18n her platformda (next-intl web, i18next desktop/mobile)
- [x] Docker Compose dev stack (repo kökü), Render.com pilot deploy spec (`render.yaml`)
- [ ] Web auth cookie-based migration (hâlen localStorage — [LAUNCH_CHECKLIST](docs/LAUNCH_CHECKLIST.md) blok-eden madde)
- [ ] httpOnly cookie + CSRF double-submit

**v0.2 (4-6 hafta):**
- Mobile on-device kalite kontrol (TFLite YOLO11n) — `tools/` altında export iskelet hazır
- Maliyet motoru ML regresyonu (lookup tablo yerine, ~500 etiketli pilot örnekten sonra)
- Refresh token revocation list (Redis-backed `jti` blocklist)
- Türkçe araç markası fine-tune (Egea, Symbol, vb.)
- Sentry release tag + Grafana production panelleri canlı (config zaten `observability/`)

**v1.0 (3-6 ay):**
- VIN/plaka OCR + KVKK otomatik anonimleştirme (yüklemede yüz/plaka blur)
- Fraud detection (deepfake/foto manipülasyon, EXIF tutarlılık)
- B2B partner dashboard (sigorta acentesi, oto-ekspertiz)
- TR yedek parça API'leri ile fiyat motorunun beslenmesi
- Multi-region failover + KMS-managed JWT signing

## License + disclaimer

This codebase is **MIT licensed**. **Dataset licenses differ:** CarDD is **academic non-commercial** — commercial use requires separate permission. See [scripts/DATA_README.md](scripts/DATA_README.md).

**KVKK / GDPR**: License plates and VIN may be visible in raw uploads. Production use **requires** automated blurring / anonymization (v0.2 backlog item).

## Contact

- **Maintainer**: weblineet@gmail.com
- **Issues**: [GitHub issues](https://github.com/your-org/arac-hasar-v2/issues)

---

## Known hardcoded strings — follow-up cleanup

While building locale files, the following hardcoded strings were spotted in source code that should eventually be moved to i18n keys. They are **already covered** by translation keys in `apps/web/messages/{tr,en}.json` (under `home.*`, `nav.*`, `footer.*`), but the components still inline literals:

**Web (`apps/web/`):**
- `app/page.tsx` — hero copy, VALUE_PROPS array (driver-friendly, small-damage, local-pricing), FEATURES stats, preview card labels ("Ön tampon", "2 hasar", "3.500 – 5.200 ₺", "~2 iş günü tamir + boya yeterli"), CTA section. Use `home.*` keys.
- `components/Header.tsx` — `NAV` array ("Yeni inceleme", "Geçmiş"), `Hasarİ` brand, "MVP", "Demo'yu dene", `aria-label="Hasarİ ana sayfa"`. Use `nav.*` keys.
- `components/Footer.tsx` — copyright string, "v0.1 MVP", "Türkiye için tasarlandı". Use `footer.*` keys.
- `app/inspect/page.tsx`, `app/history/page.tsx`, `app/results/[id]/page.tsx` — currently call `useTranslations`, may have residual inline strings worth auditing.

**Mobile (`apps/mobile/screens/*`)** and **Desktop (`apps/desktop/src/**`)** — components were not exhaustively scanned in this pass; recommend grepping for raw Turkish strings (e.g. `rg "[ğüşöçıİĞÜŞÖÇ]" apps/mobile/screens apps/desktop/src`) before pilot launch and replacing with `t('...')` calls referencing the keys already shipped in the locale files.

**Brand decision:** locale files keep `Hasarİ` as the brand in both TR and EN per the existing source code. If a separate English brand is desired (e.g. "DamageAI"), update only `common.appName` in `en.json` files — the rest of the strings reference the namespace, not the literal.
