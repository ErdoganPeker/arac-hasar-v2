# Arac Hasar Tespit — Backend

Multi-platform (Web + Mobile + Desktop) icin FastAPI tabanli hasar tespit API'si.

- **Web**: Next.js 15 (`apps/web`) — `http://localhost:3000`
- **Mobile**: Expo / React Native (`apps/mobile`) — `http://localhost:8081`
- **Desktop**: Tauri (`apps/desktop`) — `http://localhost:1420` (dev), `tauri://localhost` (prod)

---

## Hizli Baslangic — Docker (onerilen)

```bash
cd services/backend
cp .env.example .env   # yoksa
docker compose up --build
```

Ardindan:

| Servis          | URL                                       |
| --------------- | ----------------------------------------- |
| API             | http://localhost:8000                     |
| Swagger UI      | http://localhost:8000/docs                |
| ReDoc           | http://localhost:8000/redoc               |
| OpenAPI JSON    | http://localhost:8000/openapi.json        |
| MinIO Console   | http://localhost:9001 (minioadmin:minioadmin) |
| Postgres        | localhost:5432 (postgres:postgres)        |
| Redis           | localhost:6379                            |

Health check: `curl http://localhost:8000/health`

---

## Yerel gelistirme (Docker'siz)

```bash
cd services/backend
python -m venv .venv && source .venv/bin/activate   # Win: .venv\Scripts\activate
pip install -r requirements.txt

# Postgres + Redis + MinIO'yu ayri ayri ayaga kaldir veya yalniz API icin:
docker compose up db redis minio minio-init

# API'yi local'de cevir
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Worker (ayri terminal)
celery -A worker.celery_app worker --loglevel=info --concurrency=1
```

---

## Environment degiskenleri

`.env` dosyasi root'tan yuklenir (yoksa default'lar kullanilir).

| Var                  | Default                                   | Aciklama |
| -------------------- | ----------------------------------------- | -------- |
| `API_KEYS`           | (bos = dev mode)                          | Virgulle ayrilmis gecerli API key'ler |
| `ENVIRONMENT`        | `development`                             | `development` / `production` |
| `API_VERSION`        | `0.2.0`                                   | Version response icin |
| `GIT_SHA`            | `dev`                                     | CI'da git rev-parse ile doldur |
| `BUILD_TIME`         | `unknown`                                 | CI'da ISO timestamp |
| `CORS_ORIGINS`       | localhost:3000,1420,8081,tauri://*        | Acik origin listesi |
| `CORS_ORIGIN_REGEX`  | `*.vercel.app` + Tauri schemes            | Regex tabanli ek origin'ler |
| `DATABASE_URL`       | `postgresql://postgres:postgres@db:5432/arac_hasar` | |
| `REDIS_URL`          | `redis://redis:6379/0`                    | Celery broker + pubsub |
| `S3_ENDPOINT`        | `http://minio:9000`                       | Container icinden MinIO |
| `S3_PUBLIC_ENDPOINT` | `http://localhost:9000`                   | Browser/mobile'in erisecegi MinIO |
| `S3_BUCKET`          | `inspections`                             | |
| `DAMAGE_WEIGHTS`     | `models/damage_best.pt`                   | YOLO weights |
| `PARTS_WEIGHTS`      | `models/parts_best.pt`                    | |
| `SEVERITY_WEIGHTS`   | (bos)                                     | Opsiyonel |
| `ML_DEVICE`          | `cuda`                                    | `cuda` / `cpu` / `mps` |
| `MAX_IMAGE_SIZE_MB`  | `10`                                      | |
| `MAX_IMAGES_SYNC`    | `5`                                       | |
| `MAX_IMAGES_ASYNC`   | `20`                                      | |

---

## Endpoint listesi

### Health & meta

| Method | Path                  | Auth | Aciklama                       |
| ------ | --------------------- | ---- | ------------------------------ |
| GET    | `/health`             | -    | Saglik check + ml_loaded       |
| GET    | `/api/v1/version`     | -    | Versiyon + git sha + build time |

### Inspect (REST)

| Method | Path                                                | Auth | Aciklama |
| ------ | --------------------------------------------------- | ---- | -------- |
| POST   | `/api/v1/inspect?mode=sync|async`                   | Y    | Coklu goruntu (sync max 5, async max 20) |
| POST   | `/api/v1/inspect/sync`                              | Y    | Tek goruntu hizli (mobile/desktop) |
| GET    | `/api/v1/inspect/{id}`                              | Y    | Durum + sonuc |
| GET    | `/api/v1/inspect/{id}/visualization/{type}`         | Y    | `annotated\|parts\|damages` PNG redirect |
| GET    | `/api/v1/inspect?page=1&page_size=20`               | Y    | Liste (paginated) |
| DELETE | `/api/v1/inspect/{id}`                              | Y    | Sil |

### Streaming

| Method | Path                                       | Auth   | Aciklama |
| ------ | ------------------------------------------ | ------ | -------- |
| WS     | `/api/v1/inspect/{id}/stream`              | (MVP'de acik) | Realtime status push |

WS mesaj formatlari:

```json
{"type": "status",    "inspection_id": "...", "status": "processing"}
{"type": "completed", "inspection_id": "...", "result": { /* Inspection */ }}
{"type": "error",     "inspection_id": "...", "error": "..."}
```

---

## Auth nasil calisir?

### Dev mode (varsayilan)

`API_KEYS` env'i bos ise butun istekler `client_id="dev"` olarak kabul edilir.
Startup'ta uyari log'u atilir.

### Production mode

`API_KEYS=key1,key2,key3` set edildiginde:

- Her istek `X-API-Key: <key>` header'i icermek zorunda.
- Header yoksa -> `401 Unauthorized`.
- Header gecersizse -> `403 Forbidden`.

### JWT (v2)

Iskelet `auth.py` icinde yorum olarak hazir. JWT'ye gecisi yaparken
`require_api_key` yerine `require_jwt` kullan.

---

## OpenAPI export

TS client uretmek isteyenler icin:

```bash
cd services/backend
python scripts/export_openapi.py
# -> packages/types/openapi.json
```

> Not: `packages/types/src/*.ts` elle yazilmistir ve Pydantic modelleri ile birebir
> senkronize tutulur. OpenAPI JSON sadece referans amacli.

---

## Test

```bash
cd services/backend
pip install pytest httpx
pytest tests/ -v
```

Testler ML pipeline'i, S3 ve Celery'yi monkey-patch ile mockla calisir;
external bagimlilik gerekmez.

---

## Mimari ozet

```
                          +---------+
   Web (Next)  ---+       |  CORS    |
   Tauri       ---+--->   |  REST    |  ---> Postgres (incelemeler)
   Expo        ---+       |   WS     |  ---> MinIO    (goruntuler)
                          +----+-----+
                               |
                               | (async jobs)
                               v
                          +----+-----+
                          | Celery   |
                          | Worker   |  ---> ML Pipeline (YOLOv8)
                          +----+-----+
                               |
                               | (status pubsub)
                               v
                          +----+-----+
                          |  Redis   |
                          +----------+
```

---

## Breaking change'ler (v0.1 -> v0.2)

- Endpoint prefix `/v1/inspections` -> **`/api/v1/inspect`**. Eski path'ler dusurulmustur.
- `/healthz` hala calisir ama `include_in_schema=False`. Yeni: `/health`.
- `InspectionStatusResponse.result` artik `Inspection` tipinde (parca-merkezli).
  Onceki "damages" listesi ust seviyede yoktu; yeni semaya gore `parts[].damages` icindedir.
- WS endpoint yeni: `/api/v1/inspect/{id}/stream`.
- Auth: `verify_api_key` -> `require_api_key` (auth.py'a tasindi).

Mobile/desktop client'larin v0.1'i kullanmasi durumunda guncellenmeli; ancak
projenin baska commit'inde client yazilmadigi icin gercek kullanici etkisi yok.
