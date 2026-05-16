# Deploy Guide — Render.com

End-to-end walkthrough for deploying Hasarİ to Render.com using `render.yaml`. Covers prerequisites, infra setup, environment configuration, the first deploy, smoke tests, monitoring, rollback, and cost.

> Target audience: anyone with shell access and a Render account, no prior Render experience required.

---

## Prerequisites

Before you start, you need:

| Item | Why | How to get it |
|---|---|---|
| **Render account** | Hosts the API + worker | [render.com](https://render.com) — free tier ok for the web service; Postgres/Redis are paid |
| **GitHub access to the repo** | Render builds from git | `arac-hasar-v2` repo permissions |
| **AWS S3 bucket** (or compatible) | Image storage (uploads + visualizations) | Or use Cloudflare R2 / Backblaze B2 — anything S3-compatible |
| **AWS IAM access key** with `s3:GetObject`, `s3:PutObject`, `s3:DeleteObject` on the bucket | Backend uploads/signs URLs | AWS console → IAM |
| **Custom domain** (optional) | Branded URL | Any registrar, point CNAME at Render |
| **A strong `JWT_SECRET_KEY`** | Signs auth tokens | `openssl rand -base64 48` |
| **Sentry DSN** (optional) | Error tracking | [sentry.io](https://sentry.io) |

**Time estimate**: 45–90 minutes for the first deploy. Subsequent deploys are git-push fast.

---

## Step 1 — Provision infrastructure

The `render.yaml` at the repo root declares all services. Render reads it on first connect and creates everything in one go.

### 1a. Create the Postgres database

In the Render dashboard:

1. **New +** → **PostgreSQL**
2. **Name**: `hasari-db`
3. **Database**: `hasari`
4. **User**: `hasari`
5. **Region**: pick the one nearest your users (Frankfurt for EU/TR, Oregon for US)
6. **Plan**: **Starter** ($7/month) is sufficient for the pilot. Free tier expires after 90 days — do not use it for production.
7. **Create database**.

Copy the **Internal Database URL** (format: `postgres://hasari:…@…/hasari`). You'll paste it as `DATABASE_URL` in step 2.

### 1b. Create the Redis instance

1. **New +** → **Redis**
2. **Name**: `hasari-redis`
3. **Region**: same as Postgres
4. **Plan**: **Starter** ($10/month). Free tier has no persistence; do not use for production.
5. **Maxmemory policy**: `allkeys-lru`
6. **Create Redis**.

Copy the **Internal Redis URL** — you'll use it as `REDIS_URL`.

### 1c. Create the S3 bucket

In the AWS console:

1. S3 → **Create bucket** → `hasari-uploads-prod` (or your name), region matching the API for low latency
2. **Block all public access** — yes, keep all four boxes checked. The backend serves presigned URLs; no public listing.
3. **Versioning**: disabled (uploads are immutable; no need for revisions)
4. **Server-side encryption**: SSE-S3 (default) is fine
5. After creation: **Permissions** → **CORS** → add:

```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["GET", "PUT", "POST"],
    "AllowedOrigins": ["https://hasari.app", "https://hasari-api.onrender.com"],
    "ExposeHeaders": ["ETag", "x-amz-request-id"],
    "MaxAgeSeconds": 3000
  }
]
```

Replace the origins with your actual web app URL.

6. IAM → create an IAM user `hasari-backend`, attach an inline policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::hasari-uploads-prod/*"
    },
    {
      "Effect": "Allow",
      "Action": "s3:ListBucket",
      "Resource": "arn:aws:s3:::hasari-uploads-prod"
    }
  ]
}
```

Create an access key for this user — save both halves now, you cannot retrieve the secret again.

---

## Step 2 — Configure the backend service

### 2a. Connect the repo

1. Render dashboard → **New +** → **Blueprint**
2. Connect your GitHub account, pick `arac-hasar-v2`
3. Render detects `render.yaml` and shows the services it will create:
   - `hasari-api` — web service (FastAPI)
   - `hasari-worker` — background worker (Celery)
4. Click **Apply** to create both.

### 2b. Set environment variables

For **each** of `hasari-api` and `hasari-worker`, go to **Environment** and add:

#### Required

| Name | Example | Description | Security note |
|---|---|---|---|
| `ENVIRONMENT` | `production` | Disables dev auth fallback | Never set to `dev` here |
| `DATABASE_URL` | `postgres://…` | From step 1a | Internal URL only; no external traffic |
| `REDIS_URL` | `redis://…` | From step 1b | Internal URL only |
| `JWT_SECRET_KEY` | (32+ char random string) | Signs JWTs | Generate fresh: `openssl rand -base64 48`. Rotating invalidates all existing sessions. |
| `S3_BUCKET` | `hasari-uploads-prod` | Bucket name | — |
| `S3_REGION` | `eu-central-1` | AWS region | — |
| `S3_ACCESS_KEY` | `AKIA…` | From step 1c | Use a dedicated IAM user, not your root key |
| `S3_SECRET_KEY` | `…` | From step 1c | Mark this var as "secret" in Render UI |
| `S3_ENDPOINT_URL` | (blank for AWS) | Set only for R2/MinIO/B2 | — |
| `CORS_ORIGINS` | `https://hasari.app,https://www.hasari.app` | Comma-separated allowed web origins | Never use `*` in production |

#### Recommended

| Name | Default | Description |
|---|---|---|
| `ACCESS_TOKEN_MINUTES` | `30` | Short access TTL — keeps damage from a stolen token bounded |
| `REFRESH_TOKEN_DAYS` | `7` | Refresh TTL — balance UX vs. risk |
| `MAX_IMAGE_SIZE_MB` | `12` | Per-image upload limit |
| `MAX_IMAGES_SYNC` | `5` | Sync mode cap |
| `MAX_IMAGES_ASYNC` | `20` | Async mode cap |
| `SENTRY_DSN` | (blank) | Enable Sentry error tracking |
| `LOG_LEVEL` | `INFO` | `DEBUG` for troubleshooting; keep `INFO` in prod |

#### ML service

| Name | Default | Description |
|---|---|---|
| `ML_MODEL_DIR` | `/app/models` | Path to YOLO `.pt` weight files inside the container |
| `ML_DEVICE` | `cpu` | `cuda` requires a GPU instance (Render does not offer GPU — keep CPU on Render and offload heavy ML to a separate GPU host or external service for production) |

> **GPU note**: Render does not currently offer GPU instances. For the pilot, the backend runs YOLO on CPU — slower (~5–10× CPU vs. GPU). For production loads above ~50 inspections/hour, host the ML service separately on a GPU VPS (Hetzner, RunPod, etc.) and point `ML_SERVICE_URL` at it. Architecture diagram in [README.md](../README.md#architecture).

### 2c. Build & start commands

If `render.yaml` is missing these, set them manually:

**hasari-api** (web service):
- Build: `pip install -r services/backend/requirements.txt`
- Start: `cd services/backend && alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port $PORT`

**hasari-worker** (background worker):
- Build: same
- Start: `cd services/backend && celery -A worker worker --loglevel=info --concurrency=2`

---

## Step 3 — First deploy

1. Both services auto-deploy on push to `main`. Trigger the first deploy:
   - Go to **hasari-api** → **Manual Deploy** → **Deploy latest commit**.
2. Watch the build log. Expected duration: 8–15 minutes (downloads PyTorch, YOLO weights).
3. The first start runs `alembic upgrade head` — DB schema is created.
4. Once "Your service is live" appears, hit the health endpoint:

```bash
curl https://hasari-api.onrender.com/health
```

Expected:

```json
{"status":"ok","ml_loaded":true,"timestamp":"2026-05-15T...","version":"0.1.0"}
```

If `ml_loaded` is `false`, check the start log for "ML pipeline init failed" — usually means model weights are missing from the container. Run a one-off SSH session and run `python -c "from ml_service import ml_pipeline; print(ml_pipeline.is_loaded())"`.

---

## Step 4 — Create the admin user

The first admin must be created out-of-band — there is no admin-registration UI. SSH into the API container via the Render dashboard (**Shell** tab) and run:

```bash
cd services/backend
python -c "
from database import init_db
from auth import _repo
from security import hash_password
init_db()
user = _repo.create(
    email='admin@yourcompany.com',
    password_hash=hash_password('CHANGE_ME_now_strong_password'),
    full_name='Admin',
)
# Promote
import psycopg
with psycopg.connect('$DATABASE_URL') as conn:
    conn.execute('UPDATE users SET role=%s WHERE id=%s', ('admin', user['id']))
    conn.commit()
print('Admin user created:', user['email'])
"
```

Sign in immediately at `https://hasari.app/login` and rotate the password through the UI.

---

## Step 5 — Smoke test checklist

Before announcing the deploy is "done", run through this list. Each item should pass on the first try.

- [ ] `GET /health` returns 200 with `ml_loaded: true`
- [ ] `GET /api/v1/version` returns expected git SHA and build time
- [ ] `POST /auth/register` with a new email returns 201 + token pair
- [ ] `POST /auth/login` with that email returns 200 + new token pair
- [ ] `GET /auth/me` with the access token returns the user
- [ ] `POST /auth/refresh` with the refresh token returns a new token pair
- [ ] `POST /api/v1/inspect/sync` with a 1MB JPG returns 200 with parts/damages JSON within 15 seconds
- [ ] `GET /api/v1/inspect` returns the inspection in the list
- [ ] `GET /api/v1/inspect/{id}/visualization/annotated` redirects to a presigned S3 URL that returns a PNG
- [ ] `DELETE /api/v1/inspect/{id}` removes it (subsequent GET returns 404)
- [ ] Web app loads at custom domain, language defaults to TR
- [ ] Sign in via web app, complete one inspection end-to-end
- [ ] Open Render logs — no `ERROR` or `CRITICAL` entries in the past hour
- [ ] Postgres connection count < 20 (visible in Render → hasari-db → Metrics)

If any item fails, **do not** announce the launch. See [Troubleshooting](#troubleshooting).

---

## Monitoring & log access

### Logs

- **Render dashboard**: hasari-api → **Logs** tab — live tail.
- **CLI**: `render logs --service hasari-api --tail` (install [render-cli](https://render.com/docs/cli)).
- **Structured JSON**: every log line is `{"time":..., "level":..., "logger":..., "msg":...}` — pipe to `jq` for filtering.

### Metrics

- **Render built-in**: CPU, memory, response time, throughput visible per service in the dashboard.
- **Prometheus**: scrape `https://hasari-api.onrender.com/metrics` (requires `Authorization: Bearer <admin token>`). See `observability/` for a Grafana dashboard JSON to import.

### Alerts

Configure in Render → service → **Notifications**:
- **Deploy failed** → Slack/email
- **Service crashed** → on-call rotation
- **Disk usage > 80%** → Slack

For app-level alerts (error rate > 1%, p95 latency > 3s), set up Sentry alerts on the `SENTRY_DSN` project.

---

## Rolling back a bad deploy

If the latest deploy is broken:

1. Render dashboard → **hasari-api** → **Events** tab.
2. Find the last known-good deploy (green checkmark).
3. Click **Rollback to this deploy**.
4. Confirm. Render redeploys the previous Docker image — takes ~30 seconds.

For database migrations that cannot be rolled back automatically:

```bash
# In the Render shell:
cd services/backend
alembic downgrade -1
```

**Important**: never `alembic downgrade` a migration that dropped a column with live data — you will lose data. Pre-launch, test every migration's `downgrade()` against a copy of production data.

---

## Cost estimate (monthly, pilot scale)

| Item | Plan | Cost |
|---|---|---|
| Render web service (`hasari-api`) | Starter (512 MB) | $7 |
| Render background worker (`hasari-worker`) | Starter (512 MB) | $7 |
| Render Postgres | Starter | $7 |
| Render Redis | Starter | $10 |
| AWS S3 (10 GB storage, 100k req/month) | Pay-as-you-go | ~$1 |
| AWS data transfer (out) | Pay-as-you-go | ~$2 |
| Custom domain | (you own it) | $0 |
| Sentry (free tier) | Developer | $0 |
| **Total** | | **~$34/month** |

Scaling beyond ~500 inspections/day will require:
- Larger Render plans (Standard: $25/service)
- Moving ML to a GPU VPS (Hetzner GPU: $80/month)
- S3 storage growth: $0.023/GB/month

---

## Troubleshooting

### `ml_loaded: false` at startup

**Cause**: model weights missing or wrong path.
**Fix**: ensure `services/ml/yolo11m-seg.pt`, `yolo11s-seg.pt`, `yolo11n-cls.pt` are committed to the repo or downloaded in the build step. Check `ML_MODEL_DIR` env var.

### 503 "Is kuyrugu su an kullanilamiyor"

**Cause**: Celery worker can't reach Redis.
**Fix**: confirm `REDIS_URL` is set on **hasari-worker** (not just api). Restart worker.

### Postgres connection limit exceeded

**Cause**: too many open connections — usually a long-running query or leaked sessions.
**Fix**: check Render → Postgres → Metrics → "Active connections". Restart API service to drop them. Add `pool_pre_ping=True` and `pool_recycle=300` to SQLAlchemy engine config.

### S3 403 on upload

**Cause**: IAM policy doesn't grant `s3:PutObject`, or bucket name typo, or wrong region.
**Fix**: run `aws s3 ls s3://your-bucket-name --region eu-central-1` from anywhere with the same credentials to verify.

### Web app CORS error

**Cause**: `CORS_ORIGINS` doesn't include the actual origin (don't forget `https://`, no trailing slash).
**Fix**: update env var, redeploy API.

### Health check passing but inspections always fail with 500

**Cause**: usually an unhandled exception in the ML pipeline (corrupt model, OOM, missing class).
**Fix**: enable `LOG_LEVEL=DEBUG`, reproduce, read the traceback in logs. If it's OOM, upgrade to Standard plan or move ML off-box.

### Migration locked / `alembic upgrade head` hangs

**Cause**: a previous migration left a lock in the `alembic_version` table.
**Fix**: in psql, `DELETE FROM alembic_locks;` (table name varies — check your alembic config) or set `LOCK_TIMEOUT` and retry.

---

## Post-launch monitoring (first 48 hours)

Watch these metrics every 4 hours for the first two days:

- **Error rate** (Sentry): target < 0.5% of requests
- **API latency p95** (Render metrics): target < 1.5 s for non-inspection endpoints
- **Inspection latency p95**: target < 12 s end-to-end for 4-photo batches
- **Database active connections**: target < 50% of pool max
- **Redis memory**: target < 80% of plan limit
- **Failed inspection rate**: target < 2% of jobs reaching `failed`

If any metric exceeds target for 30+ minutes, treat as a P1 incident.

---

## Related docs

- [API_GUIDE.md](API_GUIDE.md) — REST contract for smoke tests
- [AUTH_FLOW.md](AUTH_FLOW.md) — token lifecycle (env vars relevant)
- [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md) — pre-go-live sign-off gates
- [OBSERVABILITY_SETUP.md](OBSERVABILITY_SETUP.md) — Prometheus + Grafana wiring
