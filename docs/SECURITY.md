# SECURITY — arac-hasar-v2

Owner: Security Engineer
Scope: pilot-production. Stores customer PII (vehicle images, user emails) and produces damage / cost estimates that may flow into invoice / claim workflows.

---

## 1. Threat Model

### 1.1 System overview

| Layer | Component | Notes |
|---|---|---|
| Edge | TLS terminator (Render / Cloudflare / nginx) | HTTPS only; no plaintext listener in prod |
| API | FastAPI (`services/backend`) | JWT-authenticated REST + WebSocket; this document covers it |
| ML | YOLO inference service (`services/ml`) | Internal; reachable only from backend |
| Storage | PostgreSQL (managed), Redis (rate-limit + pubsub), S3/MinIO (images) | Network-isolated; no public exposure |
| Clients | Next.js web, Tauri 2 desktop, React Native mobile | All consume the same API |

### 1.2 Trust boundaries

```
Public Internet
   |  (TLS)
[Edge / CDN]
   |  (private network)
[FastAPI]
   |  (private network, IAM)
[Postgres]  [Redis]  [S3]  [ML service]
```

Every arrow crossing a boundary is an authentication checkpoint.

### 1.3 Sensitive data inventory

| Data | Classification | Where it lives | Controls |
|---|---|---|---|
| User email | PII | Postgres `users.email`, access logs (redacted on auth paths) | TLS in transit; encrypted-at-rest (managed Postgres) |
| Password | secret | Postgres `users.password_hash` (bcrypt cost 12) | Never logged; never returned |
| Vehicle images | PII (may contain plates, faces, location via EXIF) | S3 bucket | EXIF stripped on upload; private bucket; signed URLs only |
| JWT access/refresh | secret | Client-held; never persisted server-side | Short TTL (30 min / 7 d); HS256 signed |
| API keys (pilot integrations) | secret | Postgres `api_keys.key_hash` (sha256) | Shown plaintext once on issue; revocable |
| ML inference results / cost estimates | business data | Postgres + S3 reports | Tenant isolation enforced at handler |

### 1.4 STRIDE summary

| Threat | Vector | Risk | Mitigation |
|---|---|---|---|
| Spoofing | Stolen credentials, token replay | High | Bcrypt cost 12, short access-token TTL, refresh rotation (TODO: backend wire), per-route rate limits on `/auth/login` |
| Tampering | Modified upload, tampered cost estimate | Med | Server-side decode + revalidation of images; cost computed server-side from `cost_table.yaml`; never trust client-supplied totals |
| Repudiation | "I never uploaded that" / "I never approved that estimate" | Med | Structured JSON access log w/ request_id, user_id, sha256 of uploaded image |
| Information disclosure | IDOR on `/api/v1/inspect/{id}`, EXIF GPS leak | High | Mandatory ownership check pattern (section 3); EXIF stripped before storage |
| Denial of Service | Image bomb, hot loop on `/inspect`, brute-force login | High | 20 MB cap, decompression-bomb guard (`Image.MAX_IMAGE_PIXELS`), slowapi limits |
| Elevation of privilege | `role` claim tampering, missing admin check | Crit | JWT signature verification; `require_admin` dependency; role re-read from DB on refresh |

### 1.5 Out of scope (for now)

- Multi-region failover
- DDoS at the transport layer (delegated to CDN)
- Hardware security modules / KMS-managed JWT signing keys (flagged for production-scale)
- SSO / SAML (pilot uses local accounts + API keys)

---

## 2. OWASP Top 10 (2021) — Mitigations

### A01 — Broken Access Control

- Every protected route depends on `require_user` (or `require_admin`).
- IDOR pattern is mandatory; see section 3.
- WebSocket connections must authenticate within 5 s of `accept()` (Backend Architect owns the WS handler — flagged in section 6).
- Default policy is deny: a route without an explicit auth dependency is treated as a review failure.

### A02 — Cryptographic Failures

- Passwords: bcrypt (passlib), cost factor 12, `BCRYPT_ROUNDS` env-tunable.
- JWT: HS256 (acceptable for monolithic backend; migrate to RS256 if signing moves to a separate service).
- API keys: 256 bits of entropy, prefixed `ahv2_`, stored as sha256 hash, compared with `hmac.compare_digest`.
- Secrets exclusively via env vars; `.env` is gitignored.
- TLS terminated at edge; HSTS sent in staging/prod by `SecurityHeadersMiddleware`.
- No custom crypto. Period.

### A03 — Injection

- **SQL**: SQLAlchemy ORM + parameterized `text()` for any raw SQL. Never f-string user input into queries. Reviewed in PR template.
- **Command**: no `subprocess` with `shell=True`. Image processing stays in-process (PIL).
- **Path**: `sanitize_filename` strips `..`, backslashes, control chars, and prefixes a uuid4. S3 keys are never user-supplied raw.
- **Header**: request IDs whitelisted to `[A-Za-z0-9_-]`, capped at 128 chars (CRLF injection guard).

### A04 — Insecure Design

- Threat model (section 1) reviewed before each release.
- Cost estimates computed server-side from `cost_table.yaml`; clients cannot override.
- Refresh tokens carry `role="user"` by design — privilege is re-derived from the DB on refresh so a leaked refresh token cannot escalate.

### A05 — Security Misconfiguration

- `_validate_config()` hard-fails at import time if `JWT_SECRET_KEY` is < 32 chars in staging/production.
- Default-deny CSP (`default-src 'none'`) on all API responses.
- CORS allowlist (`ALLOWED_ORIGINS`); `allow_credentials=False` because we use bearer tokens, not cookies.
- `Server` header stripped.
- Debug / docs (`/docs`, `/redoc`) must be disabled in production (flagged for Backend Architect — see section 6).

### A06 — Vulnerable & Outdated Components

- `requirements.txt` is the canonical lock; CI must run `pip-audit` (or `trivy fs`) on every PR.
- Renovate / Dependabot recommended for weekly updates.

### A07 — Identification & Authentication Failures

- `/auth/login` rate-limited to **5/min per IP** via slowapi.
- Generic error messages on bad credentials ("invalid email or password") — no user enumeration.
- Access tokens: 30 min. Refresh tokens: 7 d, single-use rotation (Backend Architect to implement `jti` blocklist in Redis — section 6).
- Password requirements (length / complexity) are owned by the user model layer (Database Optimizer) — flagged.

### A08 — Software & Data Integrity Failures

- Pinned dependencies in `requirements.txt`.
- Container images built from pinned base + reproducible build.
- ML model weights checksummed at load time (Backend Architect owns `ml_service.py` — flagged in section 6).

### A09 — Security Logging & Monitoring Failures

- `AccessLogMiddleware` emits structured JSON: `ts, method, path, status, duration_ms, user_id, request_id, ip, ua`.
- Auth paths (`/auth/*`, `/login`, `/token`, `/refresh`, `/password`) suppress query string from logs.
- Request bodies are never logged.
- Bcrypt / JWT failures log at INFO with **reason class only**, never the input.
- Recommend shipping access log to a SIEM / log aggregator (Loki / CloudWatch) with retention >= 90 days.

### A10 — Server-Side Request Forgery (SSRF)

- The backend never fetches user-supplied URLs.
- Image uploads are received as multipart bytes — no fetch-by-URL path exists.
- If a "fetch from URL" feature is added later, it MUST:
  1. Resolve DNS server-side once and reject private / link-local ranges.
  2. Disallow redirects to private ranges.
  3. Run in a dedicated egress-restricted network namespace.

---

## 3. Authorization pattern (mandatory)

Every endpoint that touches a tenant-scoped resource MUST follow this shape:

```python
from fastapi import APIRouter, Depends, HTTPException, status
from security import require_user, TokenPayload

router = APIRouter()

@router.get("/api/v1/inspect/{inspection_id}")
async def get_inspection(
    inspection_id: UUID,
    user: TokenPayload = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(Inspection, inspection_id)
    if row is None:
        # 404, not 403, to avoid leaking existence
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if row.user_id != user.user_id and user.role != "admin":
        # IDOR check. Same 404 to prevent enumeration.
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return row
```

Rules:
1. **Always** check ownership before returning a row.
2. **Always** return `404`, never `403`, when the user isn't the owner (no existence oracle).
3. Admin override goes through `user.role == "admin"`, never a query param.
4. Bulk endpoints (e.g. `GET /api/v1/inspect`) MUST filter `WHERE user_id = :uid` in the query — never in Python.

---

## 4. File upload pipeline

```
multipart bytes
   -> validate_image_upload(buf)
        size cap (20 MB)
        magic-byte MIME sniff (jpeg / png / webp only)
        PIL decode + verify()
        decompression-bomb guard
        EXIF orientation applied
        EXIF metadata stripped (PII: GPS, camera serial, timestamps)
        dimension cap (10000 x 10000)
   -> sanitize_filename(orig_name)
   -> upload to S3 with server-generated key
        Content-Type forced to sniffed MIME
        bucket policy: private, no public-read
        served via short-lived presigned URLs
```

Hard rules:
- Never trust client-supplied `Content-Type`.
- Never store the raw user-supplied filename as the S3 key.
- Never serve images from a domain that can execute scripts (use a separate static / signed-URL domain).
- S3 bucket policy must deny `*:GetObject` to the public.

---

## 5. CSRF

The API is bearer-token only (`Authorization: Bearer <jwt>`). Browsers do **not** automatically attach `Authorization` headers cross-origin, so the classic CSRF vector (auto-submit a form, browser attaches cookie) does not apply.

This is enforced by:
- `allow_credentials=False` on CORS.
- No `Set-Cookie` issued anywhere in the backend.
- Tight `ALLOWED_ORIGINS`.

If cookie-based sessions are ever introduced (e.g. SSR Next.js with httponly cookies), CSRF tokens become mandatory — flagged in section 6.

---

## 6. Open items for follow-up (NOT owned by Security)

Items below are flagged for the corresponding owner; Security has not modified those files.

| # | Item | Owner | Severity |
|---|---|---|---|
| 1 | Refresh-token rotation: persist used `jti` in Redis with TTL = refresh lifetime; reject reuse | Backend Architect | High |
| 2 | Disable `/docs` and `/redoc` in production (`docs_url=None` when `ENVIRONMENT=production`) | Backend Architect | Med |
| 3 | WebSocket auth: enforce JWT within 5 s of `accept()`, close 4401 otherwise | Backend Architect (`ws.py`) | High |
| 4 | Password policy (min 12 chars, breach check via HIBP k-anonymity) at registration | Database Optimizer (`models.py`) + Backend Architect (handler) | Med |
| 5 | ML weights integrity: sha256 manifest verified before load in `ml_service.py` | Backend Architect | Med |
| 6 | S3 bucket policy review: confirm `BlockPublicAcls`, `IgnorePublicAcls`, `BlockPublicPolicy`, `RestrictPublicBuckets` all true; encryption at rest enabled | Backend Architect (`storage.py`) + Infra | High |
| 7 | Audit log: separate immutable stream for security events (login success/failure, role change, api-key issue/revoke) | Backend Architect | Med |
| 8 | Secret rotation runbook (JWT key, DB password, S3 keys) | Infra / Ops | Med |
| 9 | Penetration test before GA (target: OWASP ASVS L2) | External | High |
| 10 | KMS-managed JWT signing (migrate HS256 -> RS256/EdDSA) at scale | Backend Architect | Low (deferred) |
| 11 | CI security gates: `pip-audit`, `gitleaks`, `semgrep` on every PR | DevOps | High |
| 12 | Brute-force / credential-stuffing detection beyond simple rate limit (e.g. account lockout after N failures with cool-down) | Backend Architect | Med |

---

## 7. Deploy checklist

Before tagging a release that goes to staging or production:

- [ ] `JWT_SECRET_KEY` is set, >= 32 chars, unique per environment.
- [ ] `ENVIRONMENT` set to `staging` or `production` (enables HSTS + strict config validation).
- [ ] `ALLOWED_ORIGINS` populated with the exact production origins.
- [ ] `RATE_LIMIT_REDIS_URL` points to a managed Redis (not memory://).
- [ ] `BCRYPT_ROUNDS=12` (or higher; benchmark target ~250 ms per hash on prod CPU).
- [ ] `/docs` and `/redoc` disabled.
- [ ] Postgres / Redis / S3 reachable only over private network.
- [ ] S3 bucket: private, encryption-at-rest, lifecycle rule to purge after retention window.
- [ ] TLS cert valid; HSTS preload submitted if appropriate.
- [ ] `pip-audit` and `gitleaks` green on the build SHA.
- [ ] Access log is shipping to the aggregator and is searchable by `request_id`.
- [ ] Incident-response runbook (who to page, how to revoke a leaked JWT secret, how to rotate API keys) is current.
- [ ] Backup + restore tested in the last 30 days.

---

## 8. Reporting a vulnerability

Send to security@ (mailbox TBD). Include reproduction, impact, and a sane timeline. We commit to acknowledging within 72 h and patching critical issues within 7 days.
