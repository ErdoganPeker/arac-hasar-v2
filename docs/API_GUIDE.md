# API Guide

Complete REST + WebSocket reference for the Hasarİ backend, with runnable `curl` examples for every endpoint.

> Interactive Swagger UI: `http://localhost:8000/docs` — auto-generated from the FastAPI app.

---

## Base URL & versioning

- **Local development**: `http://localhost:8000`
- **Pilot production** (Render.com): `https://hasari-api.onrender.com`
- **API version prefix**: `/api/v1/*` for inspection endpoints. Auth and health are at the root.

All examples below assume the env var `BASE` is set:

```bash
export BASE=http://localhost:8000
```

PowerShell:

```powershell
$env:BASE = "http://localhost:8000"
```

---

## Authentication

The API accepts two auth schemes:

1. **JWT Bearer (preferred)** — obtained via `/auth/login` or `/auth/register`, sent as `Authorization: Bearer <access_token>`.
2. **Legacy API key (fallback)** — `X-API-Key: <key>` header, used for service-to-service.

In `ENVIRONMENT=dev` only, an unauthenticated request is accepted and treated as a `dev` client. Never run a public deployment with `ENVIRONMENT=dev`.

Tokens:
- **Access token**: TTL 30 min (configurable via `ACCESS_TOKEN_MINUTES`)
- **Refresh token**: TTL 7 days (configurable via `REFRESH_TOKEN_DAYS`)
- **Algorithm**: HS256 by default. Secret loaded from `JWT_SECRET_KEY` (≥32 chars required in non-dev).

See [AUTH_FLOW.md](AUTH_FLOW.md) for the full register → login → refresh → use sequence and per-platform token storage guidance.

---

## Standard responses

### Success
- `200 OK` — synchronous result inline
- `201 Created` — auth registration succeeded
- `202 Accepted` — async job queued

### Errors
All errors share this envelope:

```json
{
  "detail": "Human-readable Turkish or English message"
}
```

Common HTTP codes:

| Code | Meaning | Typical cause |
|---|---|---|
| 400 | Bad Request | malformed request, missing files, oversized image |
| 401 | Unauthorized | missing/expired/invalid token |
| 403 | Forbidden | authenticated but not the owner of the resource |
| 404 | Not Found | inspection ID does not exist |
| 409 | Conflict | registering with an existing email |
| 413 | Payload Too Large | image exceeds `MAX_IMAGE_SIZE_MB` |
| 415 | Unsupported Media Type | non-image MIME |
| 422 | Unprocessable Entity | Pydantic validation failed |
| 429 | Too Many Requests | per-IP or per-account rate limit |
| 500 | Internal Server Error | unhandled exception (logged) |
| 503 | Service Unavailable | Celery/Redis down |

---

## Auth endpoints

### POST `/auth/register` — Create a new user

Creates an account and returns an access + refresh token pair.

**Request body**

```json
{
  "email": "user@example.com",
  "password": "MyStrongPassword123",
  "full_name": "Ahmet Yılmaz"
}
```

| Field | Type | Constraints |
|---|---|---|
| `email` | string | RFC 5322 email |
| `password` | string | 8–128 chars |
| `full_name` | string\|null | ≤120 chars, optional |

**Response 201**

```json
{
  "access_token": "eyJhbGciOi…",
  "refresh_token": "eyJhbGciOi…",
  "token_type": "bearer",
  "expires_in": 1800
}
```

**Curl**

```bash
curl -X POST "$BASE/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "MyStrongPassword123",
    "full_name": "Ahmet Yılmaz"
  }'
```

**Errors**: `409 Bu email zaten kayitli` if duplicate; `422` if password too short.

---

### POST `/auth/login` — Sign in

Returns a fresh access + refresh token pair.

**Request body**

```json
{ "email": "user@example.com", "password": "MyStrongPassword123" }
```

**Response 200**: same `TokenPair` shape as `/auth/register`.

**Curl**

```bash
curl -X POST "$BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"MyStrongPassword123"}'
```

**Errors**: `401 Email veya parola hatali` (timing-safe — invalid users still incur a bcrypt cost).

---

### POST `/auth/refresh` — Rotate access token

**Request body**

```json
{ "refresh_token": "eyJhbGciOi…" }
```

**Response 200**: a new `TokenPair`. The old refresh token remains valid until its 7-day TTL expires (no revocation list in v0.1 — planned for v0.2).

**Curl**

```bash
curl -X POST "$BASE/auth/refresh" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"eyJhbGciOi…"}'
```

**Errors**: `401 Refresh token gecersiz` (expired, wrong type, signature mismatch).

---

### GET `/auth/me` — Current user

**Headers**: `Authorization: Bearer <access_token>` (required)

**Response 200**

```json
{
  "id": "8a3c4e2f-…",
  "email": "user@example.com",
  "full_name": "Ahmet Yılmaz",
  "role": "user",
  "is_active": true,
  "created_at": "2026-05-15T14:30:00Z"
}
```

**Curl**

```bash
curl "$BASE/auth/me" -H "Authorization: Bearer $ACCESS_TOKEN"
```

---

## Health & version

### GET `/health` — Service health

No auth required. Used by load balancers and uptime monitors.

**Response 200**

```json
{
  "status": "ok",
  "ml_loaded": true,
  "timestamp": "2026-05-15T14:30:00.000Z",
  "version": "0.1.0"
}
```

**Curl**

```bash
curl "$BASE/health"
```

`/healthz` is an alias preserved for backwards compatibility.

---

### GET `/api/v1/version` — Build info

**Response 200**

```json
{
  "version": "0.1.0",
  "git_sha": "abc1234",
  "build_time": "2026-05-15T10:00:00Z",
  "environment": "production"
}
```

---

## Inspection endpoints

All inspection endpoints require authentication. The user can only see and modify their own inspections.

### POST `/api/v1/inspect` — Create inspection (multi-image)

Accepts 1–20 images via multipart form data. Returns either an async job handle or a synchronous result depending on `mode`.

**Query**: `mode=sync` (max 5 images, blocks until done) or `mode=async` (default, max 20 images, queued).

**Form fields**:
- `files` — one or more files, JPG/PNG/WebP, each ≤ `MAX_IMAGE_SIZE_MB` (default 12 MB)

**Response 202 (async)**

```json
{
  "inspection_id": "8c1f…",
  "status": "queued",
  "status_url": "/api/v1/inspect/8c1f…",
  "created_at": "2026-05-15T14:30:00Z",
  "estimated_completion_seconds": 30
}
```

Headers include `X-Inspection-Id: 8c1f…`.

**Response 200 (sync)**

Full inspection result in `SyncInspectionResponse` shape — see "Output format" in [README.md](../README.md#output-format-part-centric).

**Curl (async)**

```bash
curl -X POST "$BASE/api/v1/inspect?mode=async" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -F "files=@front.jpg" \
  -F "files=@side.jpg" \
  -F "files=@rear.jpg"
```

**Curl (sync, single image)**

```bash
curl -X POST "$BASE/api/v1/inspect?mode=sync" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -F "files=@damage.jpg"
```

**Errors**:
- `400 En az 1 goruntu gerekli` — empty form
- `400 Sync modda max 5 goruntu` / `Async modda max 20 goruntu` — limit exceeded
- `400 Goruntu N cok buyuk (>12MB)` — file too large
- `400 Goruntu N gecersiz MIME tipi` — wrong content type
- `400 Goruntu N okunamadi` — corrupt or unsupported format
- `503 Is kuyrugu su an kullanilamiyor` — Celery enqueue failed

---

### POST `/api/v1/inspect/sync` — Fast single-image inspection

Optimized for the mobile quick-check flow: one image, latency-sensitive. Identical to `POST /api/v1/inspect?mode=sync` with a single file.

**Curl**

```bash
curl -X POST "$BASE/api/v1/inspect/sync" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -F "file=@damage.jpg"
```

---

### GET `/api/v1/inspect/{id}` — Status + result

Poll this endpoint to track an async job, or read the cached result after completion.

**Response 200**

```json
{
  "inspection_id": "8c1f…",
  "status": "completed",
  "result": { /* part-centric output, see README */ },
  "error": null,
  "created_at": "2026-05-15T14:30:00Z",
  "completed_at": "2026-05-15T14:30:08Z"
}
```

`status` ∈ `queued | running | completed | failed`. When `failed`, `error` contains a human-readable Turkish message.

**Curl**

```bash
curl "$BASE/api/v1/inspect/8c1f…" -H "Authorization: Bearer $ACCESS_TOKEN"
```

**Errors**:
- `404 Inceleme bulunamadi` — wrong ID
- `403 Bu incelemeye erisim yetkiniz yok` — owned by another user

---

### GET `/api/v1/inspect/{id}/visualization/{viz_type}` — Visualization PNG

Returns a 302 redirect to a presigned S3/MinIO URL for the requested visualization.

**Path**: `viz_type` ∈ `annotated | parts | damages`.

**Curl** (follow redirect, save to file)

```bash
curl -L "$BASE/api/v1/inspect/8c1f…/visualization/annotated" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -o annotated.png
```

**Errors**:
- `404 Inceleme bulunamadi`
- `404 annotated gorsel henuz uretilmemis` — render not yet complete
- `403 Yetki yok`

---

### GET `/api/v1/inspect` — List inspections

Paginated history of the authenticated user's inspections, newest first.

**Query**: `page` (≥1, default 1), `page_size` (1–200, default 20)

**Response 200**

```json
{
  "items": [
    {
      "inspection_id": "8c1f…",
      "created_at": "2026-05-15T14:30:00Z",
      "status": "completed",
      "damage_count": 3,
      "total_cost_midpoint_tl": 10650,
      "thumbnail_url": null
    }
  ],
  "total": 47,
  "page": 1,
  "page_size": 20
}
```

**Curl**

```bash
curl "$BASE/api/v1/inspect?page=1&page_size=20" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

---

### DELETE `/api/v1/inspect/{id}` — Delete inspection

Permanent. Removes the DB row; S3 objects are tombstoned by a nightly sweep (planned).

**Response 204**: empty body.

**Curl**

```bash
curl -X DELETE "$BASE/api/v1/inspect/8c1f…" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

**Errors**: `404`, `403` (not owner).

---

### WS `/api/v1/inspect/{id}/stream` — Real-time progress

WebSocket channel that pushes status updates and the final result for an async job.

**Auth**: send the access token as the `token` query parameter (WebSocket clients can't easily set headers in the browser).

**Connection**

```
wss://hasari-api.onrender.com/api/v1/inspect/8c1f…/stream?token=eyJhbGciOi…
```

**Messages** (server → client, JSON):

```json
{ "type": "status", "inspection_id": "8c1f…", "status": "running", "progress": 0.45 }
```

```json
{ "type": "completed", "inspection_id": "8c1f…", "result": { /* part-centric output */ } }
```

```json
{ "type": "failed", "inspection_id": "8c1f…", "error": "ML inference timeout" }
```

The server closes the socket immediately after `completed` or `failed`. Clients should also implement a polling fallback against `GET /api/v1/inspect/{id}` for environments that block WebSockets.

**Wscat example**

```bash
npx wscat -c "ws://localhost:8000/api/v1/inspect/8c1f…/stream?token=$ACCESS_TOKEN"
```

---

## Rate limits

| Endpoint group | Limit | Headers |
|---|---|---|
| `/auth/*` | 10 req / minute / IP | `Retry-After` on 429 |
| `/api/v1/inspect` (POST) | 60 req / hour / account | — |
| Other reads | 1000 req / hour / account | — |

Limits are enforced in middleware; the response on breach is `429 Too Many Requests` with a Turkish `detail` and a `Retry-After` header in seconds.

---

## Pagination conventions

- `page` is 1-based.
- `page_size` is capped at 200 (the backend rejects larger values with 422).
- Always include `total` in responses so the client can render "Sayfa 1 / 5".

---

## Idempotency

`POST /api/v1/inspect` is **not** idempotent — a retry will create a new inspection. To avoid duplicates on flaky networks, the client should track in-flight inspection IDs locally and offer a "view existing" UX if a duplicate is detected.

---

## Need to inspect failures?

- **Backend logs**: structured JSON to stdout. In Docker: `docker compose logs -f backend`. On Render: dashboard → Logs.
- **Sentry**: error events are forwarded when `SENTRY_DSN` is set.
- **Prometheus**: `/metrics` endpoint exposes request count, latency histogram, ML inference duration.

For incident response, see [DEPLOY_GUIDE.md](DEPLOY_GUIDE.md#troubleshooting).
