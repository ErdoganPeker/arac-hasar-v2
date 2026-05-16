# Production Launch Checklist — arac-hasar-v2

**Hedef stack:** Vercel (web) + Render (backend, free tier) + Supabase (Postgres free tier) + Cloudflare R2 (storage)

**Bu doküman ne için var?**
Production'a basmadan ÖNCE tek tek tikleyeceğin son güvenlik ve operasyon listesi. Her madde için:

- **P0** = Deploy'u BLOKLAR (yapılmadıysa canlıya çıkma)
- **P1** = İlk hafta içinde bitir (canlı ama yüksek risk)
- **P2** = İlk ay içinde bitir (iyileştirme)

**Sorumlu rolleri:** `dev` = sen / geliştirici · `devops` = altyapı / hosting · `legal` = KVKK / sözleşme

**Tahmini süre = senin için gerçekçi efor (saat).**

---

## TOP 10 MUST-DO (deploy öncesi, P0)

Bu 10 madde TAMAMLANMADAN canlıya çıkma. Hepsi `docs/PROD_LAUNCH_CHECKLIST.md`'nin ilgili bölümünde detaylandırılmıştır.

| #  | Madde                                                                                       | Süre |
|----|---------------------------------------------------------------------------------------------|------|
| 1  | `ROBOFLOW_API_KEY` revoke + yenisini üret (chat geçmişine sızdı)                            | 15dk |
| 2  | `JWT_SECRET_KEY` 48-byte random üret, sadece Render dashboard'da sakla                      | 10dk |
| 3  | Cloudflare R2 bucket-scoped token (account-level token KULLANMA)                            | 30dk |
| 4  | Supabase `DATABASE_URL` pgbouncer pooler portu `:6543` (direct `:5432` DEĞİL)               | 15dk |
| 5  | `ENVIRONMENT=production` set → in-memory fallback HARD FAIL test et                         | 1s   |
| 6  | `CORS_ORIGINS` sadece prod Vercel domain'i (wildcard veya `*` YOK)                          | 10dk |
| 7  | Next.js `15.1.3 → ^15.5.16` upgrade (CVE-2025-29927 middleware bypass)                      | 1s   |
| 8  | WebSocket `/api/v1/inspect/{id}/stream` auth ekle (query param `?token=...` minimum)        | 2s   |
| 9  | `.env*` dosyaları repo'da DEĞİL → `git log --all -p -- .env` ile doğrula                    | 30dk |
| 10 | UptimeRobot ping kur (Render free 15dk sleep'i engelle, `/health` endpoint)                 | 20dk |

**Toplam:** ~7 saat çekirdek iş + test/validation süresi.

---

## 1. Secrets Management (KRİTİK)

> Tüm secret'lar **YALNIZCA** hosting platform'un secret manager'ında (Render Environment, Vercel Environment Variables) saklanır. `.env` dosyası repo'ya **GİRMEZ**. Local dev için `.env.local` (gitignored) kullan.

### 1.1 — Sızdırılmış secret rotation

- [ ] **P0** | dev | 15dk — `ROBOFLOW_API_KEY` Roboflow konsolundan **revoke** + yeni key üret. Önceki chat history'de plain text görüldü.
- [ ] **P0** | dev | 20dk — Tüm `.env*`, `docker-compose*.yml`, `services/backend/*.py` içinde geçen değer ne ise `git log -S "<value>" --all` ile sızıntı yok mu doğrula. Sızdıysa `git filter-repo` veya repo reset.
- [ ] **P0** | dev | 30dk — `git log --all -p -- "**/.env*"` ile herhangi bir `.env` commit'lenmiş mi kontrol et. Commit'lendiyse → BFG Repo Cleaner veya filter-repo + force push + GitHub destek bilet (cache invalidation).
- [ ] **P1** | dev | 20dk — Tüm secret'ları doğal cycle (90 gün) için takvime ekle (Sentry DSN, R2, Supabase service role).

### 1.2 — JWT secret

- [ ] **P0** | devops | 10dk — `openssl rand -base64 48` ile yeni `JWT_SECRET_KEY` üret.
- [ ] **P0** | devops | 5dk — Render dashboard → `hasarui-api` service → Environment → `JWT_SECRET_KEY` ekle (Render `render.yaml`'da zaten `generateValue: true` ile otomatik üretiyor; **manuel override yapacaksan worker da aynı değere bağlı olduğundan emin ol**, render.yaml'da worker `fromService` ile referans veriyor — bu OK).
- [ ] **P0** | dev | 15dk — `services/backend/config.py:139-155` `_jwt_secret_hard_fail` validator çalışıyor mu test et: `ENVIRONMENT=production JWT_SECRET_KEY=short python -c "import config"` → exception fırlatmalı.
- [ ] **P1** | devops | 10dk — 1Password / Vault / Bitwarden gibi bir password manager'a kopya al (recovery için, ASLA Slack/email'de paylaşma).

### 1.3 — Database credentials (Supabase)

- [ ] **P0** | devops | 15dk — Supabase Project Settings → Database → **Connection Pooling (PgBouncer)** sekmesinden URL al. Port `:6543`, mode `Transaction`. Direct `:5432` URL **KULLANMA** (free tier 60 connection limit, web+worker hızla doldurur).
- [ ] **P0** | devops | 10dk — Render `DATABASE_URL` env'ini Supabase pooler URL ile **manuel override** et (render.yaml'da `fromDatabase` Render-managed DB için, Supabase için manuel set).
- [ ] **P0** | devops | 5dk — Supabase `DATABASE_URL`'in sonuna `?sslmode=require` ekle. SSL olmadan bağlantı reddedilsin.
- [ ] **P1** | devops | 10dk — Supabase Database password'ü ayda 1 rotate planı (calendar reminder).
- [ ] **P2** | dev | 30dk — `database_url_async` (asyncpg) için ayrıca pooler URL test et — asyncpg + pgbouncer transaction mode'da prepared statement sorunu var, `?prepared_statements=false` veya `statement_cache_size=0` gerekebilir.

### 1.4 — Object storage (Cloudflare R2)

- [ ] **P0** | devops | 30dk — Cloudflare R2 dashboard → Manage R2 API Tokens → **Object Read & Write** scope sadece `inspections` bucket için. Account-level token **OLUŞTURMA**.
- [ ] **P0** | devops | 10dk — Token oluştururken **TTL** set et (1 yıl). Süresiz token oluşturma.
- [ ] **P0** | devops | 10dk — Render env: `S3_ENDPOINT=https://<account_id>.r2.cloudflarestorage.com`, `S3_REGION=auto`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET=inspections`.
- [ ] **P0** | devops | 15dk — `S3_PUBLIC_ENDPOINT` ya R2 public bucket URL (custom domain) ya da presigned URL strategy. Bucket public yapacaksan **sadece** `previews/` ve `overlays/` prefix'i için custom CORS rule.
- [ ] **P1** | devops | 20dk — R2 bucket → Settings → **CORS Policy**: `AllowedOrigins: ["https://<vercel-domain>"]`, `AllowedMethods: ["GET","HEAD"]`. Wildcard yok.
- [ ] **P1** | devops | 10dk — R2 → **Object Lifecycle** rule: `tmp/` prefix 7 gün sonra expire (worker geçici dosyalar).
- [ ] **P2** | devops | 30dk — R2 token rotation runbook (90 gün).

### 1.5 — Admin bootstrap

- [ ] **P0** | dev | 15dk — `ADMIN_PASSWORD` için `openssl rand -base64 24` üret. Sadece Render env'de + password manager'da sakla.
- [ ] **P0** | dev | 10dk — `ADMIN_EMAIL` set et (örn. `admin@<domain>`). İlk login sonrası şifreyi web UI'dan değiştir.
- [ ] **P0** | dev | 5dk — `.env.example` dosyasında `ADMIN_PASSWORD=` placeholder'ın boş olduğunu doğrula (örnek değer KOYMA, kullanıcı yanlışlıkla aynısını kullanır).
- [ ] **P1** | dev | 30dk — İlk admin login + şifre değiştirme akışı test edildi.

### 1.6 — Repo hijyen

- [ ] **P0** | dev | 20dk — `.gitignore` içinde: `.env`, `.env.*`, `!.env.example`, `*.pt` (model weights ayrı bucket'tan fetch), `login.json` (repo kökünde duruyor — bu ne? incele!).
- [ ] **P0** | dev | 10dk — **`login.json` dosyası repo kökünde** (`ls` çıktısında görüldü). İçinde credentials var mı? Varsa rotate + sil + .gitignore'a ekle.
- [ ] **P1** | dev | 30dk — Pre-commit hook: `detect-secrets` veya `gitleaks` kur. CI'da da çalışsın.
- [ ] **P2** | dev | 1s — GitHub repo Settings → Secret scanning + Push protection aktif (public repo için ücretsiz).

---

## 2. Backend Hardening (FastAPI / Render)

### 2.1 — Production mode hard-fail

- [ ] **P0** | dev | 1s — `services/backend/main.py:150-163` `_db_available()` in-memory fallback: production'da DB connect fail → `sys.exit(1)`. Şu an `logger.warning` ile geçiyor, sessizce yanlış data döner.
- [ ] **P0** | dev | 30dk — Production'da `init_db()` çağrısı fail olursa app boot fail. Şu anki davranışı `services/backend/main.py:169` test et.
- [ ] **P1** | dev | 1s — `pipeline.py` model load fail → production'da hard fail. Dev'de fake/dummy pipeline'a fallback OK ama prod'da değil.

### 2.2 — CORS

- [ ] **P0** | devops | 10dk — Render env `CORS_ORIGINS=https://<your-vercel-domain>.vercel.app,https://<custom-domain>`. Wildcard / `*` / boş **YOK**.
- [ ] **P0** | dev | 15dk — `services/backend/config.py:71-77` `cors_origin_regex` production'da daraltıldı mı doğrula. Şu an `vercel.app` wildcard subdomain kabul ediyor (preview deploy'larda preview URL'leri eşleşir; OK ama bilinçli karar).
- [ ] **P0** | dev | 5dk — `middleware.py:268` `allow_credentials=False` korundu (Authorization header'da JWT, cookie yok).
- [ ] **P1** | dev | 30dk — `curl -H "Origin: https://evil.com" -I https://<api>/health` → `Access-Control-Allow-Origin` header DÖNMEMELİ.

### 2.3 — Logging / debug

- [ ] **P0** | dev | 15dk — `ENVIRONMENT=production` iken log level `INFO` (DEBUG değil). `services/backend/main.py` `logging.basicConfig` ayarını doğrula.
- [ ] **P0** | dev | 15dk — Exception handler stack trace'i client'a göndermiyor. FastAPI default `{"detail": "Internal Server Error"}` yeterli; custom handler eklediysen mesajda traceback olmadığını test et.
- [ ] **P0** | dev | 10dk — `middleware.py:139` `_SENSITIVE_PATH_FRAGMENTS` listesi `/auth/`, `/login`, `/token`, `/refresh`, `/password` içeriyor (OK). `/inspect` upload body'si zaten log'a girmiyor (sadece query string).
- [ ] **P1** | dev | 20dk — Access log SAMPLE et: prod'da her isteğin tam JSON log'u Render'in 100GB/ay limitini hızlı tüketebilir. Sentry breadcrumb'a ya da error-only log'a düşür.

### 2.4 — JWT validation

- [ ] **P1** | dev | 30dk — `services/backend/security.py:191` JWT encode'a `iss` claim eklenmiş ama `verify_token` (`security.py:226-231`) `iss` doğrulaması yapmıyor. `jwt.decode(..., issuer="arac-hasar-v2")` ekle, options'da `require: ["iss"]`.
- [ ] **P1** | dev | 20dk — `aud` claim ekle (örn. `aud=arac-hasar-v2:api`) ve verify et. WS, web, mobile için farklı audience kullanabilirsin (ileri sürüm).
- [ ] **P2** | dev | 2s — JWT revocation list (jti blacklist) Redis'te. Logout endpoint refresh token'ı invalidate etsin.
- [ ] **P2** | dev | 1s — Refresh token rotation: her refresh'te yeni jti üret, eskisini blacklist'e at.

### 2.5 — Rate limiting

- [ ] **P0** | dev | 30dk — `middleware.py:80-91` `limiter` Redis storage_uri set edilmiş mi prod'da kontrol et. `RATE_LIMIT_REDIS_URL` Render free'de Upstash Redis kullanabilirsin (free tier 10K req/gün).
- [ ] **P0** | dev | 20dk — Endpoint'lerde decorator'lar var mı doğrula: `/auth/login` → `5/minute`, `/api/v1/inspect` → `60/minute`. `grep -n "@limiter" services/backend/main.py`.
- [ ] **P1** | dev | 1s — Test: aynı IP'den 10 hatalı login → 6. attempt 429 dönmeli.
- [ ] **P1** | dev | 30dk — `/auth/register` için de rate limit (`3/hour` per IP).

### 2.6 — Security headers

- [ ] **P0** | dev | 15dk — `middleware.py:209-237` `SecurityHeadersMiddleware` aktif. Prod URL'de `curl -I https://<api>/health` ile şu header'ları doğrula:
  - `X-Content-Type-Options: nosniff`
  - `X-Frame-Options: DENY`
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
  - `Content-Security-Policy: default-src 'none'; ...`
  - `Referrer-Policy: strict-origin-when-cross-origin`
- [ ] **P1** | dev | 10dk — `Permissions-Policy` header'ı `camera=()` engelliyor — mobile/desktop client kamerayı browser üzerinden değil native API ile alıyor, sorun yok.
- [ ] **P1** | devops | 20dk — securityheaders.com'da production API URL test et → A veya A+ skoru.

### 2.7 — WebSocket auth (HIGH bulgu hâlâ açık)

- [ ] **P0** | dev | 2s — `services/backend/main.py:1065-1077` WS endpoint **auth yok**. Saldırgan inspection_id bilse her kullanıcının inspection'ını dinleyebilir. Minimum:
  ```python
  @app.websocket("/api/v1/inspect/{inspection_id}/stream")
  async def inspect_stream(websocket: WebSocket, inspection_id: str, token: str = Query(...)):
      try:
          payload = verify_token(token, expected_type="access")
      except HTTPException:
          await websocket.close(code=1008)  # Policy Violation
          return
      # Ek: bu inspection_id payload.sub'a mı ait?
      await stream_inspection(websocket, inspection_id)
  ```
- [ ] **P0** | dev | 1s — Authorization sonrası: inspection ownership check (`inspection.user_id == payload.sub`). Aksi halde IDOR (Insecure Direct Object Reference).
- [ ] **P1** | dev | 30dk — WS rate limit (per user, max 5 concurrent connection per user).
- [ ] **P1** | dev | 20dk — WS heartbeat / idle disconnect (`ws_max_duration_sec=600` zaten var, doğrula).

### 2.8 — REST IDOR kontrolleri

- [ ] **P0** | dev | 2s — `GET /api/v1/inspect/{id}`, `GET /api/v1/inspect/{id}/result`, `DELETE /api/v1/inspect/{id}` her birinde `inspection.user_id == current_user.sub` check'i VAR mı? `services/backend/main.py:873, 905, 963, 1048` satırlarını oku, ownership check yoksa ekle. Admin role bypass'i ayrı kontrol.
- [ ] **P1** | dev | 1s — Pytest: User A'nın inspection'ını User B token ile çağır → 403 dönmeli.

### 2.9 — Input validation

- [ ] **P0** | dev | 10dk — `services/backend/security.py:369-434` `validate_image_upload` MIME sniff + decompression bomb guard + EXIF strip aktif (iyi).
- [ ] **P1** | dev | 30dk — `max_image_size_mb=10` Render free 512MB RAM'de güvenli mi? 10MB × 5 paralel = 50MB raw + PIL decode amplification (4×) = 200MB. ML model yüklemesi varsa OOM. Limit `5MB`'a düşür veya max_images_sync'i 2-3'e indir.
- [ ] **P2** | dev | 20dk — Filename sanitization (`security.py:442-477`) zaten UUID prefix + whitelist ile güvenli.

### 2.10 — Dependency audit

- [ ] **P1** | dev | 30dk — `cd services/backend && pip-audit -r requirements.txt`. Critical/High CVE varsa pinleri güncelle.
- [ ] **P1** | dev | 20dk — `python-jose`, `bcrypt`, `passlib` (varsa) sürümlerini kontrol et — python-jose'un bilinen CVE'leri var, PyJWT'ye geçişi değerlendir.

---

## 3. Frontend Hardening (Next.js / Vercel)

### 3.1 — Next.js CVE upgrade (KRİTİK)

- [ ] **P0** | dev | 1s — `apps/web/package.json` `next: "15.1.3"` → `next: "^15.5.16"` (CVE-2025-29927 middleware bypass; saldırgan `x-middleware-subrequest` header ile middleware'i atlatabilir, `/dashboard` gibi protected route'lara erişebilir).
- [ ] **P0** | dev | 30dk — Upgrade sonrası `pnpm install`, `pnpm typecheck`, `pnpm build` lokalde geçti.
- [ ] **P0** | dev | 30dk — `apps/web/middleware.ts` upgrade sonrası halen çalışıyor (auth redirect, locale cookie). E2E test.
- [ ] **P0** | dev | 10dk — `eslint-config-next` aynı sürüme bumple (`^15.5.16`).

### 3.2 — Token storage

- [ ] **P1** | dev | 4s — `apps/web/lib/api.ts:20-63` access_token + refresh_token **localStorage**'da. XSS bir kez bulunursa attacker tüm token'ları çalar. **Hedef (v0.2):**
  - Refresh token → `HttpOnly; Secure; SameSite=Lax` cookie (backend `/auth/refresh` cookie'den okusun)
  - Access token → memory'de tut (React Context), reload'da `/auth/refresh` ile yenile
  - Bu değişiklik backend `/auth/refresh` endpoint'inin cookie okumasını da gerektirir.
- [ ] **P1** | dev | 30dk — Şu an için minimum: `apps/web/middleware.ts:24` `TOKEN_COOKIE = 'access_token'` cookie'sinin **HttpOnly olmadığını** doğrula (server-side middleware bu cookie'yi okuduğundan JS'ten set ediliyor → HttpOnly olamaz). En azından `Secure; SameSite=Lax` set edildiğinden emin ol.
- [ ] **P2** | dev | 1s — XSS koruma: tüm user-provided content `dangerouslySetInnerHTML` ile render edilmiyor (`grep -r dangerouslySet apps/web` → 0 sonuç olmalı).

### 3.3 — Axios / API config

- [ ] **P0** | dev | 10dk — `apps/web/lib/api.ts` axios instance `withCredentials: false` (cross-site cookie kullanmıyoruz, JWT Authorization header'da). Doğrula.
- [ ] **P0** | dev | 5dk — `NEXT_PUBLIC_API_URL` Vercel env'de `https://<render-app>.onrender.com` (http değil).
- [ ] **P1** | dev | 20dk — Axios timeout (`timeout: 30000`) set edildi mi — Render free cold start için 60s gerekebilir, ilk istek için ayrı timeout.

### 3.4 — Content Security Policy (frontend)

- [ ] **P1** | dev | 1s — Vercel'de `next.config.ts` `headers()` ile CSP set et:
  ```js
  async headers() {
    return [{ source: '/(.*)', headers: [
      { key: 'Content-Security-Policy', value: "default-src 'self'; img-src 'self' data: https://*.r2.dev https://*.r2.cloudflarestorage.com; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self' https://<render-app>.onrender.com https://*.sentry.io; frame-ancestors 'none';" },
      { key: 'X-Frame-Options', value: 'DENY' },
      { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
    ]}];
  }
  ```
- [ ] **P1** | dev | 30dk — CSP'yi `Report-Only` ile başlat (1 hafta), violation log topla, sonra enforce.
- [ ] **P2** | dev | 20dk — `nonce`-based script CSP (Next 15+ destekliyor) `unsafe-inline`'ı kaldırmak için.

### 3.5 — Vercel project hardening

- [ ] **P0** | devops | 15dk — Vercel project Settings → Deployment Protection → preview deploy'larda password / Vercel auth zorunlu (preview'lar arama motorlarına düşmesin).
- [ ] **P1** | devops | 10dk — Production branch sadece `main`. Preview deploy'lar farklı subdomain (zaten default).
- [ ] **P1** | devops | 20dk — Custom domain bağladıktan sonra `Strict-Transport-Security` preload list'e başvur (https://hstspreload.org).

### 3.6 — `output: 'standalone'` ve sızıntı

- [ ] **P1** | dev | 30dk — `next.config.ts:8` `output: 'standalone'` → `.next/standalone` içinde server-side code; `NEXT_PUBLIC_*` olmayan env'ler client bundle'a sızmamalı. `grep -r "process.env" apps/web/app apps/web/components` ile audit.
- [ ] **P1** | dev | 10dk — `next.config.ts:35` `NEXT_PUBLIC_API_URL` zaten public, OK. Başka server-only env varsa `process.env.X`'i sadece server component / route handler'da kullan.

---

## 4. Database (Supabase)

### 4.1 — Schema / migration

- [ ] **P0** | dev | 30dk — `services/backend/migrations/` Alembic head local'de Supabase'e karşı `alembic upgrade head` ile uygulanabiliyor.
- [ ] **P0** | dev | 15dk — Render `RUN_MIGRATIONS=1` env'i ile boot'ta `entrypoint.sh` migration çalıştırıyor. Worker servisinde `RUN_MIGRATIONS=0` (çift migration race condition önler).

### 4.2 — Connection pooling

- [ ] **P0** | devops | 10dk — Supabase free **direct connections: max 60, pooler connections: 200**. Backend pool: `pool_size=5, max_overflow=10`. Worker pool: `pool_size=3, max_overflow=5`. Toplam < 30.
- [ ] **P0** | dev | 20dk — SQLAlchemy `create_engine(..., pool_pre_ping=True, pool_recycle=300)` — Supabase idle connection'ları kapatır.
- [ ] **P1** | dev | 30dk — Worker idle'da connection bırakmıyor (Celery worker_max_tasks_per_child=100 → periyodik recycle).

### 4.3 — Row-Level Security (RLS)

> **NOT:** Mevcut kod SQLAlchemy ORM kullanıyor, backend kendi auth check'lerini yapıyor. RLS ekstra defense-in-depth katmanı. Sadece Supabase client (`anon` key) kullanan akış varsa zorunlu — bu projede yok, ama yine de aç.

- [ ] **P1** | dev | 2s — Supabase Studio → Authentication → Policies. `inspections` tablosu için RLS aç: `enable row level security`. Policy: `auth.uid()::text = user_id` (Supabase auth kullanmıyorsan policy: `current_setting('app.user_id', true) = user_id::text` + backend her query öncesi `SET app.user_id`).
- [ ] **P1** | dev | 1s — `users` tablosu için RLS: user kendi profilini görür, admin hepsini.
- [ ] **P2** | dev | 1s — Service role key (backend) RLS'i bypass eder. Backend service role kullansa bile her query'de user context'ini geçiriyor mu doğrula.

### 4.4 — Backup ve recovery

- [ ] **P0** | devops | 10dk — Supabase free tier: **7 günlük PITR YOK**, sadece daily logical backup, 7 gün retention. Pilot için **yeterli ama** kritik veri için Pro plan ($25/ay) gerekir.
- [ ] **P0** | devops | 20dk — Manuel haftalık `pg_dump` ile yerel + R2'ye yedek script'i (cron / GitHub Actions). 30 gün retention.
- [ ] **P1** | dev | 1s — Restore drill: staging Supabase'e yedek geri yükle, app boot olduğunu doğrula.
- [ ] **P1** | devops | 15dk — Backup script Sentry'ye fail bildirsin.

### 4.5 — Storage limits

- [ ] **P0** | devops | 5dk — Supabase free **500MB storage**. `inspections` tablosu satır başına ~5KB (sonuç JSON dahil). 100K satır = 500MB. Pilot için OK, 6 ay sonra Pro'ya geçiş takvime.
- [ ] **P1** | devops | 30dk — Eski (60 gün+) `inspections.result` JSON'ını ayrı R2 bucket'a arşivleyen cleanup job. DB'de sadece metadata kalır.

---

## 5. Monitoring & Observability

### 5.1 — Sentry

- [ ] **P0** | dev | 30dk — Sentry hesap aç (free 5K events/ay). Backend project + Frontend project ayrı.
- [ ] **P0** | dev | 20dk — Backend: `services/backend/main.py`'da `sentry_sdk.init(dsn=settings.sentry_dsn, environment="production", traces_sample_rate=0.1)` aktif et. `render.yaml` `SENTRY_DSN` env zaten var.
- [ ] **P0** | dev | 20dk — Frontend: `@sentry/nextjs` paketi ekle, `sentry.client.config.ts` + `sentry.server.config.ts` oluştur. Vercel env'e `NEXT_PUBLIC_SENTRY_DSN`.
- [ ] **P0** | dev | 15dk — Sentry → Issues → Email alerts (admin@<domain>'e) Critical + High severity için.
- [ ] **P1** | dev | 30dk — Backend `before_send` hook'u: PII (email, JWT, password) scrub et.
- [ ] **P1** | dev | 20dk — Frontend `sourcemap` upload (Vercel build hook ile).
- [ ] **P2** | dev | 1s — Sentry sample rate: 5K events/ay limit için `traces_sample_rate=0.05` (5%) prod'da.

### 5.2 — Uptime monitoring

- [ ] **P0** | devops | 20dk — UptimeRobot (free 50 monitor, 5dk interval) → `https://<render-app>.onrender.com/health` ping.
- [ ] **P0** | devops | 10dk — Render free 15dk inactivity sleep → UptimeRobot 5dk ping bunu engeller (warm tutar, cold start önler).
- [ ] **P1** | devops | 10dk — Vercel frontend için ayrı ping monitor.
- [ ] **P1** | devops | 15dk — UptimeRobot → Alert contact: email + (opsiyonel) Telegram bot.

### 5.3 — Web analytics

- [ ] **P1** | devops | 20dk — Cloudflare Web Analytics aktif (cookieless, GDPR/KVKK uyumlu, ücretsiz). Beacon script Vercel'de `_app` veya root layout'a ekle.
- [ ] **P2** | devops | 30dk — Plausible / Umami self-hosted analytics alternatifi (cookie-free).

### 5.4 — Backend metrics

- [ ] **P2** | dev | 1s — `/metrics` Prometheus endpoint (FastAPI `prometheus-fastapi-instrumentator`). Grafana Cloud free (10K series) ile scrape.
- [ ] **P2** | dev | 30dk — ML inference latency histogram (p50/p95/p99 görünür olsun).

### 5.5 — Log aggregation

- [ ] **P1** | devops | 20dk — Render log'ları default 7 gün. Critical log'lar için Better Stack (eski Logtail) free 1GB/ay → Render log drain ayarla.

---

## 6. KVKK Uyumu (Türkiye)

### 6.1 — Bilgilendirme metinleri

- [ ] **P0** | legal | 2s — `/legal/privacy` privacy policy sayfası. Template: KVKK Kurumu sitesinden örnek + bu projeye özel: "Görseller AI işlemesi için Cloudflare R2'de saklanır, X gün sonra silinir, plaka/VIN anonimleştirilir."
- [ ] **P0** | legal | 1s — `/legal/terms` kullanım koşulları.
- [ ] **P0** | dev | 2s — Foto upload öncesi inline notice (modal veya checkbox): "Yüklediğiniz görseller yapay zeka ile analiz edilir. Plaka ve kişisel bilgiler otomatik anonimleştirilir. Detaylar için Gizlilik Politikası."
- [ ] **P0** | dev | 1s — Kayıt formunda KVKK açık rıza checkbox (`required`), link `/legal/privacy`'e gider.

### 6.2 — Veri sahibi hakları

- [ ] **P0** | dev | 30dk — `DELETE /api/v1/inspect/{id}` endpoint kullanıcının kendi inspection'ını silebiliyor mu doğrula (ownership check ile birlikte). DB'den + R2'den orijinal görsel + overlay'i sil.
- [ ] **P0** | dev | 2s — `DELETE /api/v1/users/me` endpoint: hesap silme (soft delete + 30 gün sonra hard delete). Tüm inspection'lar cascade sil veya anonymize.
- [ ] **P1** | dev | 2s — `GET /api/v1/users/me/export` endpoint: kullanıcının tüm verisini JSON olarak indir (KVKK Madde 11 — "verilerinizin bir kopyasını talep etme").
- [ ] **P1** | legal | 30dk — Veri silme talebi prosedürü dokümante et: `kvkk@<domain>` email → 30 gün içinde yanıt.

### 6.3 — Cookie consent

- [ ] **P1** | dev | 2s — Cloudflare Web Analytics cookie kullanmıyor → consent banner gerekmez. Ama GA4 / Hotjar eklersen → cookie consent (örn. `klaro`, `cookieconsent`).
- [ ] **P1** | dev | 15dk — `NEXT_LOCALE` cookie functional (zorunlu) → consent gerekmez, ama privacy policy'de belirt.

### 6.4 — VERBIS

- [ ] **P2** | legal | 4s — Kayıtlı kullanıcı sayısı 100K'yı aşar veya yıllık ciro > 25M TL olursa VERBIS kaydı zorunlu. Pilot için muaf, ama takvime al.

### 6.5 — Veri işleyici sözleşmeleri

- [ ] **P1** | legal | 1s — Cloudflare DPA (Data Processing Agreement) → Cloudflare dashboard'dan kabul.
- [ ] **P1** | legal | 1s — Supabase DPA → Supabase dashboard.
- [ ] **P1** | legal | 1s — Render DPA → Render dashboard / support.
- [ ] **P1** | legal | 1s — Sentry DPA.

### 6.6 — Veri minimizasyonu

- [ ] **P0** | dev | 15dk — `security.py:422-424` EXIF strip aktif (GPS / camera serial / timestamp PII'ı kaldırır). Doğrula.
- [ ] **P1** | dev | 1s — Plaka / VIN anonymization ML pipeline'da var mı? Yoksa `output_formatter.py`'da regex blur (görseli prod'da arşivlemeden önce).
- [ ] **P1** | dev | 30dk — Access log'da IP adresi maskeleme (`/24` subnet'e indir). KVKK için IP kişisel veri sayılır.

---

## 7. Performance

### 7.1 — Render free cold start

- [ ] **P0** | devops | 5dk — **render.yaml `plan: starter`** ($7/ay) önerilse de free tier kullanacaksan: `plan: free` (var mı kontrol et — Render free tier'da Docker desteği sınırlı). **ML model 700MB RAM** + Docker image 600MB → free 512MB RAM'de **çalışmaz**. Minimum `starter` ($7/ay) zorunlu.
- [ ] **P0** | devops | 20dk — UptimeRobot ping yukarıda — Render free 15dk sleep'i engeller, starter plan'da sleep yok ama yine de health check için ping kullan.
- [ ] **P1** | dev | 30dk — Cold start sırasında model load süresi log'la. Sentry'de p95 boot time metric.

### 7.2 — Image storage / cache

- [ ] **P1** | devops | 30dk — Model weights `MODEL_S3_PREFIX=models/full_20260515_044630` boot'ta R2'den fetch. 140MB × 3 model = 420MB indirme. Aynı region (Frankfurt) ise saniyeler. Render restart'ta tekrar fetch (ephemeral disk) — kabul edilebilir.
- [ ] **P2** | devops | 1s — Model weights'i Docker image içine bake et (`Dockerfile.embedded` zaten var) — boot süresi azalır ama image 1GB+ olur, build/push yavaşlar.

### 7.3 — Frontend bundle size

- [ ] **P1** | dev | 30dk — `pnpm build` sonrası `apps/web/.next/standalone` boyut analizi. `lucide-react` icon tree-shake doğru çalışıyor (`optimizePackageImports` aktif).
- [ ] **P1** | dev | 20dk — `next/image` ile lazy load + AVIF/WebP zaten aktif. LCP < 2.5s mobile 4G.

### 7.4 — Database query

- [ ] **P1** | dev | 1s — `inspections` tablosu üzerinde `(user_id, created_at DESC)` index var mı? History listesi için kritik.
- [ ] **P1** | dev | 30dk — `EXPLAIN ANALYZE` ile en sık çalışan 5 query'yi profile et.

### 7.5 — Supabase storage projeksiyonu

- [ ] **P1** | devops | 15dk — 1000 inspection × 5KB metadata = 5MB DB; 1000 × 3 görsel × 200KB = 600MB R2 storage. R2 free 10GB → 16K inspection'a yeter.
- [ ] **P2** | devops | 30dk — Storage budget alert: R2 dashboard'da %80'e gelince email.

---

## 8. Disaster Recovery

### 8.1 — Backup prosedürü

- [ ] **P0** | devops | 30dk — Database: yukarıda 4.4'te ele alındı (Supabase otomatik + manuel weekly `pg_dump`).
- [ ] **P0** | devops | 30dk — Model weights: R2 bucket'ta versioning aktif. Production prefix `models/full_<timestamp>` (immutable). Yeni model deploy'unda eskisini silme — rollback için 3 sürüm tut.
- [ ] **P1** | devops | 20dk — R2 bucket'ta Cross-Region replication (R2 free buna sahip değil — kritik değil, model weights GitHub release'e de yedekle).
- [ ] **P1** | dev | 1s — `services/backend/migrations/` alembic version history → git'te (zaten orada). Rollback için `alembic downgrade -1` test edildi mi.

### 8.2 — Rollback prosedürü

- [ ] **P0** | devops | 20dk — Render → Deploys → her deploy'un `Rollback` butonu var. Önceki successful deploy'a 1 tıkla dönülür. Test et: dummy commit deploy → rollback.
- [ ] **P0** | devops | 15dk — Vercel → Deployments → "Promote to Production" ile eski deploy'a anında dön.
- [ ] **P1** | dev | 30dk — DB migration rollback playbook: yeni migration deploy edip sorun çıkarsa → 1) Render eski sürüme rollback, 2) `alembic downgrade -1`, 3) Sentry'de error rate check.
- [ ] **P1** | dev | 30dk — Model rollback: `MODEL_S3_PREFIX` env'i Render dashboard'dan eski path'e değiştir → redeploy.

### 8.3 — Incident response

- [ ] **P1** | dev | 1s — `docs/INCIDENT_RESPONSE.md` (bu deploy sonrası yaz): kim, ne zaman, hangi karar. Sev1 (down) / Sev2 (degraded) / Sev3 (cosmetic).
- [ ] **P1** | devops | 20dk — Status page (Hyperping / BetterUptime free) → public.

---

## 9. Post-Launch Monitoring (ilk 30 gün)

Bu liste deploy SONRASI haftalık tikleyeceğin checkup.

### Günlük (ilk 1 hafta)

- [ ] Sentry → Issues → 24h içinde yeni Critical / High issue var mı?
- [ ] UptimeRobot → 24h uptime ≥ %99.5
- [ ] Render → Metrics → CPU < %70, Memory < %80
- [ ] Supabase → Database → Active connections < 50
- [ ] R2 → Storage → kullanım trendi
- [ ] Cloudflare Analytics → traffic, error rate

### Haftalık (ilk 30 gün)

- [ ] Sentry events / month → 5K limit'in altında mı (free tier)?
- [ ] DB backup başarılı mı? Restore drill ayda 1.
- [ ] Dependency scan: `pip-audit` + `pnpm audit`
- [ ] R2 storage trend → 80%'e yaklaştı mı?
- [ ] Supabase storage → 500MB free tier'a yaklaştı mı?
- [ ] Log aggregator → ERROR / WARNING en sık 10 kaynak

### Aylık

- [ ] Penetration test: OWASP ZAP baseline scan, Nuclei ile bilinen CVE tarama.
- [ ] Secret rotation: JWT, R2 token, Supabase password takvim kontrolü.
- [ ] User feedback → security/privacy concern var mı?
- [ ] Cost review: Render + Supabase + R2 + Sentry toplam < bütçe?
- [ ] KVKK: silme talebi geldi mi, 30 gün içinde yanıtlandı mı?

---

## Ek — Hızlı validation komutları

```bash
# 1. CORS test
curl -H "Origin: https://evil.com" -I https://<api>/health
# Beklenen: Access-Control-Allow-Origin header DÖNMEMELİ

# 2. Security headers
curl -I https://<api>/health | grep -iE "strict-transport|x-frame|content-security|x-content-type"
# Beklenen: HSTS + CSP + XFO + nosniff

# 3. Rate limit
for i in {1..10}; do curl -X POST https://<api>/auth/login -d '{}' -H "Content-Type: application/json"; done
# Beklenen: 6. istekten sonra 429

# 4. WS unauth (DOĞRULA - şu an FAIL döner çünkü auth yok)
wscat -c "wss://<api>/api/v1/inspect/test-id/stream"
# Hedef: 1008 Policy Violation veya 401

# 5. IDOR test (User A token ile User B inspection)
curl -H "Authorization: Bearer <user_a_token>" https://<api>/api/v1/inspect/<user_b_inspection_id>
# Beklenen: 403 Forbidden

# 6. Secret leak (git history)
git log --all -p -- "**/.env*" | grep -iE "key|secret|password|token"
# Beklenen: boş çıktı

# 7. Next.js CVE-2025-29927 test
curl -H "x-middleware-subrequest: middleware:middleware:middleware:middleware:middleware" https://<vercel-app>/dashboard
# Beklenen: 307 /login redirect (upgrade sonrası)
```

---

## İmza & Tarih

| Rol     | İsim    | Tarih       | İmza   |
|---------|---------|-------------|--------|
| dev     |         |             |        |
| devops  |         |             |        |
| legal   |         |             |        |

**Deploy onayı:** Yukarıdaki tüm P0 maddeleri tikli ve aşağıda imzalanmadan production'a basma.

---

**Doküman sürümü:** v1.0 · **Oluşturuldu:** 2026-05-16 · **Sahibi:** Security Engineer
