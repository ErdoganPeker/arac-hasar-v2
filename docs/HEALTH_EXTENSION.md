# Health Endpoint Extension Proposal

**Owner request:** Backend Agent
**Filed by:** DevOps Automator
**Status:** Proposal — non-blocking, no breaking change to existing `/health`

## Why

Mevcut `GET /health` (services/backend/main.py:519):

```json
{ "status": "ok", "ml_loaded": true, "timestamp": "...", "version": "..." }
```

Render/Compose üzerinde container "healthy" görünebilirken DB/Redis/S3
bağımlılıklarından biri sessizce çökmüş olabiliyor. Liveness yeterli, ama
readiness yok. Şu an dış bağımlılık sorunlarını ancak ilk request 500
attığında görüyoruz.

Hedef: `/health` (liveness) **dokunulmaz** kalsın, yeni
`GET /api/v1/health/ready` (readiness) eklensin. Compose `depends_on`
ve Render readiness probe bu endpoint'i çekebilsin.

## Önerilen Sözleşme

`GET /api/v1/health/ready` (auth gerektirmez, rate-limit muaf)

200 OK gövdesi:
```json
{
  "status": "ready",
  "ml_loaded": true,
  "db_connected": true,
  "redis_connected": true,
  "s3_connected": true,
  "version": "0.X.Y",
  "checks": {
    "db":    { "ok": true, "latency_ms": 4 },
    "redis": { "ok": true, "latency_ms": 1 },
    "s3":    { "ok": true, "latency_ms": 22 },
    "ml":    { "ok": true, "latency_ms": 0 }
  },
  "timestamp": "..."
}
```

Herhangi biri `ok=false` ise **HTTP 503** dönsün, body aynı şema. Bu
sayede orchestrator (k8s/Render) traffic çekmeyi durdurur.

## Implementation İpuçları

- DB: `SELECT 1` `database.py` içindeki engine ile, 500ms timeout.
- Redis: `redis.ping()`, `REDIS_URL`'den client.
- S3: `s3_client.head_bucket(Bucket=settings.s3_bucket)`, 1s timeout.
- ML: mevcut `ml_pipeline.is_loaded()`.
- Her probe `asyncio.wait_for(..., timeout=1.0)` ile koruma altında olsun;
  toplam endpoint latency 1.5 saniyeyi geçmemeli.
- Cache: 5 saniyelik in-memory cache (TTL) ile k8s readiness probe başına
  DB hit'ini engelle.

## Mevcut `/health` Davranışı

Değişmiyor. Sadece liveness — process ayakta ve event loop dönüyor mu
sorusuna cevap veriyor. Compose `healthcheck.test` mevcut haliyle
kalmaya devam etsin.

## Compose / Render Sonrası Adım

DevOps tarafında bu endpoint eklendikten sonra:

- `docker-compose.yml` backend `healthcheck` → `/api/v1/health/ready`'e
  taşınacak (start_period 90s).
- `render.yaml` `healthCheckPath: /api/v1/health/ready`.
- Worker readiness için ayrı bir Celery `inspect ping` probe'u zaten var,
  değişmesin.

## Out of Scope

- Prometheus `/metrics` endpoint (ayrı iş, observability dalgası).
- Auth korumalı detaylı diagnostics (`/health/full`) — gerekirse sonra.
