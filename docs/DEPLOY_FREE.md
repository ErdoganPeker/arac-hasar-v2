# DEPLOY_FREE.md — Zero-Cost Production Deploy (arac-hasar-v2)

Bu rehber projeyi **tamamen ücretsiz** (kredi kartı vermeden) prod ortama
çıkarır. Hiç para harcanmaz; subdomain'ler kullanılır (`*.vercel.app`,
`*.onrender.com`). Demo / sunum / portföy için yeterlidir.

> Para ödemeden ulaşacağın URL'ler:
> - Web   -> `https://hasari.vercel.app`
> - API   -> `https://hasari-api.onrender.com`

---

## 0. Mimari Tablosu

| Katman | Provider | Free limit | URL şeması |
|---|---|---|---|
| Web (Next.js 15) | **Vercel** Hobby | 100 GB/ay bandwidth | `hasari.vercel.app` |
| API (FastAPI) | **Render Free** Web | 512 MB RAM, 15 dk idle uyku | `hasari-api.onrender.com` |
| Worker (Celery) | YOK — sync mode | — | `FORCE_SYNC_INFERENCE=1` |
| Postgres | **Supabase Free** | 500 MB, 7 gün idle pause | `db.<ref>.supabase.co` |
| Redis | **Upstash Free** | 10K cmd/gün, 256 MB | `rediss://...upstash.io` |
| Object Storage | **Cloudflare R2 Free** | 10 GB depo, 10 GB egress | `<acct>.r2.cloudflarestorage.com` |
| CI/CD | **GitHub Actions** | 2000 dk/ay (public sınırsız) | — |
| Uptime ping | **UptimeRobot Free** | 50 monitor, 5 dk aralık | — |

Toplam aylık ücret: **0.00 USD**.

---

## 1. Hesap Açma (sıralı, ~20 dk)

1. **GitHub** — projeyi push'la (zaten varsa atla).
2. **Vercel** — `vercel.com/signup` -> "Continue with GitHub". Kart istemez.
3. **Render** — `render.com` -> "Sign up with GitHub". Free plan kart istemez.
4. **Supabase** — `supabase.com` -> "Start your project" -> GitHub login.
5. **Upstash** — `upstash.com` -> "Sign up" -> GitHub. Kart istemez.
6. **Cloudflare** — `dash.cloudflare.com/sign-up`. R2 için kart **istenir**
   ama free quota'da ücretlendirme tetiklenmez (sadece doğrulama). Kart
   vermek istemiyorsan alternatif: **Backblaze B2 Free** (10 GB, kart yok).
7. **UptimeRobot** — `uptimerobot.com` -> free signup. E-mail yeter.

---

## 2. Supabase (Postgres) Kurulumu

1. `app.supabase.com/projects` -> **New project**.
2. Bilgiler:
   - Name: `hasari`
   - Region: **Frankfurt (eu-central-1)** — Türkiye'ye en yakın free bölge.
   - DB password: **güçlü, 24+ karakter** (kaydet, bir daha gösterilmez).
3. Proje oluştuktan sonra `Project Settings -> Database -> Connection string`.
4. **Connection pooling** sekmesinden **Transaction mode** (port 6543) URL'ini
   kopyala (Render free planında concurrent connection sınırı düşük; pooler
   şart):

   ```
   postgresql://postgres.<ref>:<password>@aws-0-eu-central-1.pooler.supabase.com:6543/postgres?sslmode=require
   ```

5. Bu URL'i bir kenara not et — `DATABASE_URL` olarak Render'a girilecek.

> Uyarı: Supabase Free 7 gün hiç sorgu görmezse projeyi pause eder. UptimeRobot
> ile API'ye dakikalık ping atınca DB de canlı kalır.

---

## 3. Upstash (Redis) Kurulumu

1. `console.upstash.com` -> **Create Database**.
2. Region: **eu-west-1** (Ireland) — Render Frankfurt ile düşük gecikmeli.
3. TLS: **Enabled**. Eviction: **noeviction** (Celery queue için kritik).
4. Oluştuktan sonra **Details** sekmesinden `UPSTASH_REDIS_URL` (rediss://)
   kopyala. Bu `REDIS_URL` olacak.
5. Free quota: 10.000 komut/gün — demo için fazlasıyla yeter; canary
   alert için Upstash'in built-in usage paneline bak.

---

## 4. Cloudflare R2 (S3-Compatible Storage) Kurulumu

1. Cloudflare dashboard -> **R2 Object Storage** -> **Create bucket**.
2. Bucket: `hasari-uploads` (region otomatik, eu-batikli).
3. **Manage R2 API Tokens** -> **Create API Token**:
   - Permission: **Object Read & Write**
   - Bucket: `hasari-uploads` (specific)
   - TTL: forever
4. Aldığın değerler:
   - `S3_ACCESS_KEY` = Access Key ID
   - `S3_SECRET_KEY` = Secret Access Key
   - `S3_ENDPOINT` = `https://<account_id>.r2.cloudflarestorage.com`
   - `S3_BUCKET` = `hasari-uploads`
   - `S3_REGION` = `auto`
5. Public read URL'i (foto preview için) **Settings -> Public Access ->
   r2.dev subdomain'i etkinleştir** (24 saatte aktifleşir). Bu da
   `S3_PUBLIC_ENDPOINT` olur, formu: `https://pub-<hash>.r2.dev`.

> Alternatif: kart vermek istemiyorsan **Backblaze B2** kullan, S3 API uyumlu.

---

## 5. Render (Backend) Deploy

### 5.1 Blueprint ile import

1. GitHub'a `arac-hasar-v2` repo'sunu push'la (private/public fark etmez).
2. `dashboard.render.com` -> **New +** -> **Blueprint**.
3. GitHub repo seç -> `render.yaml` otomatik algılanır.
4. Render servisi adlandırır: `hasari-api`. **Apply** bas.
5. İlk build ~10-15 dk sürer (Docker image yapılır, model embed edilir).

### 5.2 Secrets — Render dashboard'da gir

`Settings -> Environment` altında (her biri `sync: false` ile blueprint'te
listeli):

| Key | Value (örnek) |
|---|---|
| `DATABASE_URL` | (Supabase pooler URL'i — bkz §2) |
| `REDIS_URL` | (Upstash rediss:// URL'i) |
| `API_KEYS` | (32+ karakter random, virgülle çoklu) |
| `S3_ENDPOINT` | `https://abc123.r2.cloudflarestorage.com` |
| `S3_ACCESS_KEY` | (R2 access key) |
| `S3_SECRET_KEY` | (R2 secret key) |
| `S3_BUCKET` | `hasari-uploads` |
| `S3_PUBLIC_ENDPOINT` | `https://pub-xyz.r2.dev` |
| `ADMIN_EMAIL` | `admin@hasari.app` |
| `ADMIN_PASSWORD` | (24+ karakter random, sadece ilk boot için) |
| `SENTRY_DSN` | (opsiyonel) |

`JWT_SECRET_KEY` ve `S3_REGION=auto` zaten `render.yaml` içinde
generate/static olarak işaretli — el ile girme.

### 5.3 İlk health check

```bash
curl https://hasari-api.onrender.com/health
# {"status":"ok"}
```

Cold-start ilk istekte 30-60 sn sürebilir (free plan uyku).

---

## 6. Vercel (Frontend) Deploy

### 6.1 Import

1. `vercel.com/new` -> GitHub repo seç.
2. **Configure Project** ekranında:
   - **Framework Preset**: Next.js (otomatik algılar)
   - **Root Directory**: `apps/web` (Edit ile değiştir — çok kritik)
   - **Build Command**: `cd ../.. && pnpm install --frozen-lockfile && pnpm -r --filter "./packages/*" build && pnpm --filter @arac-hasar/web build`
   - **Install Command**: (boş bırak; root build command zaten kapsıyor)
   - **Output Directory**: `.next`
3. **Environment Variables** (Production scope):

   | Key | Value |
   |---|---|
   | `NEXT_PUBLIC_API_URL` | `https://hasari-api.onrender.com` |
   | `NEXT_PUBLIC_SUPABASE_URL` | (Supabase Project URL — varsa client SDK için) |
   | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | (Supabase anon key) |
   | `NEXT_PUBLIC_SENTRY_DSN` | (opsiyonel) |

4. **Deploy** bas. ~3-5 dk içinde `hasari.vercel.app` canlı.

### 6.2 Custom subdomain (opsiyonel, hala ücretsiz)

Vercel Project Settings -> Domains -> `hasari.vercel.app` zaten verilir.
İstediğin `<isim>.vercel.app` müsaitse ücretsiz bağlayabilirsin.

### 6.3 CORS bağlantısı

Render'da `CORS_ORIGINS=https://hasari.vercel.app` zaten set; PR preview
URL'leri için `CORS_ORIGIN_REGEX=^https://hasari(-[a-z0-9]+)?\.vercel\.app$`
otomatik karşılanır.

---

## 7. GitHub Actions Secrets

`Settings -> Secrets and variables -> Actions -> New repository secret`:

| Secret | Nereden |
|---|---|
| `RENDER_DEPLOY_HOOK_API` | Render -> `hasari-api` -> Settings -> Deploy Hook |

Vercel için **secret eklemeye gerek YOK** — Vercel'in GitHub App'i
otomatik deploy eder. `.github/workflows/deploy-free.yml` sadece
Render'ı tetikler ve Vercel deploy URL'ini summary'e yazar.

(Opsiyonel) Repo variables:

| Variable | Değer |
|---|---|
| `HASARI_API_URL` | `https://hasari-api.onrender.com` |

---

## 8. UptimeRobot — Cold-Start Önleme (opsiyonel, ÖNERİLİR)

Render Free 15 dk idle sonrası servisi uyutuyor; ilk istek 30-60 sn
sürüyor. UptimeRobot ile her 5 dk'da bir `/health` ping atınca uyku
oluşmaz.

1. `uptimerobot.com/dashboard` -> **+ New Monitor**.
2. Type: HTTP(S), URL: `https://hasari-api.onrender.com/health`, interval: 5 dk.
3. Aynısını `https://hasari.vercel.app` için de ekle (opsiyonel — Vercel
   uyku yapmaz ama monitoring iyi olur).

Supabase Free 7 gün pause'unu da bu ping engellemiş olur (her ping DB
sorgusu tetikler).

---

## 9. ML Model Weights — Deploy Stratejisi

**Seçim: (a) Image'a EMBED.** Sebep:

- Render Free disk ephemeral; her restart'ta S3'ten 700 MB indirmek
  Upstash/R2 free egress'ini kemirir.
- 512 MB RAM'e büyük model sığmaz -> küçük varyant şart.
- Image build/deploy süresi tek seferlik; çalışma zamanı cold-start
  saniyelerle değil, S3 latency'siyle değil, sadece process start'la
  sınırlı.

`render.yaml` -> `dockerfilePath: ./services/backend/Dockerfile.embedded`
ve `MODEL_VARIANT=small` ile `yolo11s-seg.pt` (~20 MB) baked. Tahmini
final image: ~600 MB (Render free 10 GB cap'in çok altında).

> Eğer `yolo11n-seg.pt` (~6 MB) yeterli doğruluk veriyorsa
> `MODEL_VARIANT=nano` yap — RAM kullanımı ~150 MB'a iner, cold-start
> hızlanır.

Daha büyük modele geçmek istersen (M plan): `Dockerfile.fetch` + R2'den
boot-time download (entrypoint.sh hazır). Ama Render free RAM'i taşırır;
plan'i `starter` ($7/ay) yap.

---

## 10. Production Env — Mutlaka Set Et

| Key | Required | Notlar |
|---|---|---|
| `JWT_SECRET_KEY` | Evet | Render auto-generate (32 char). |
| `CORS_ORIGINS` | Evet | `https://hasari.vercel.app` |
| `ENVIRONMENT` | Evet | `production` |
| `ML_DEVICE` | Evet | `cpu` (free tier GPU yok) |
| `S3_ENDPOINT` | Evet | R2 endpoint |
| `RUN_MIGRATIONS` | Evet (web'de) | `1` -> alembic ilk boot'ta çalışır |
| `ADMIN_PASSWORD` | İlk boot | 24+ karakter random; sonra rotate et |

`.env` dosyasını **ASLA** repoya koyma — `.gitignore`'da var, kontrol
etmiş ol.

---

## 11. Free-Tier Kısıtları + Workaround Tablosu

| Kısıt | Etki | Workaround |
|---|---|---|
| Render Free 15 dk idle uyku | İlk istek 30-60 s | UptimeRobot 5 dk ping (§8) |
| Render Free worker yok | Async Celery çalışmaz | `FORCE_SYNC_INFERENCE=1` -> /analyze inline |
| Render Free 512 MB RAM | YOLO11m model sığmaz | `yolo11s-seg` embed (§9) |
| Supabase Free 7 gün pause | DB durur, manual unpause | UptimeRobot ping DB'yi de canlı tutar |
| Supabase Free 500 MB | Demo'ya yeter | Eski analysis kayıtlarını cron ile sil |
| Upstash 10K cmd/gün | ~300 req/saat | Cache hit'leri ve session check'leri minimize et |
| R2 10 GB egress/ay | Foto preview egress'i sayar | Vercel'den thumbnail cache; full image lazy load |
| Vercel Hobby ticari kullanım yasak | Müşteriye satılamaz | Pre-revenue MVP'de sorun yok; satış başlarsa Pro ($20/ay) |
| GH Actions 2000 dk/ay | Private repoda CI sınırı | Public yap (sınırsız) ya da minute-light CI |

---

## 12. Domain Bağlamak İstersen (opsiyonel, ücretli ALAN ADI)

Bu rehberin amacı 0 USD; ama bir gün `hasari.app` alırsan:

1. Vercel -> Project -> Settings -> Domains -> **Add** -> `hasari.app`.
   - DNS sağlayıcına: `A 76.76.21.21` veya `CNAME cname.vercel-dns.com`.
2. Render -> `hasari-api` -> Settings -> Custom Domain -> `api.hasari.app`.
   - DNS: `CNAME hasari-api.onrender.com`.
3. SSL: ikisi de Let's Encrypt ile otomatik (ücretsiz).
4. Render'da `CORS_ORIGINS` ekle: `https://hasari.app,https://hasari.vercel.app`.

Subdomain'le bile çalışan sistem olduğu için bu adım acele değil.

---

## 13. Deploy Sıralaması (ilk kez ~60 dk toplam)

1. Hesaplar (§1) — 20 dk
2. Supabase project (§2) — 5 dk
3. Upstash Redis (§3) — 3 dk
4. R2 bucket + token (§4) — 7 dk
5. GitHub push + Render blueprint (§5.1) — 15 dk (build sırası)
6. Render secrets (§5.2) — 5 dk
7. Vercel import (§6) — 5 dk
8. GH Actions secret (§7) — 2 dk
9. UptimeRobot (§8) — 3 dk
10. Smoke test (`curl /health`, web'de upload) — 5 dk

---

## 14. Smoke Test Checklist

```bash
# 1. API health
curl https://hasari-api.onrender.com/health

# 2. API docs
open https://hasari-api.onrender.com/docs

# 3. Web ana sayfa
open https://hasari.vercel.app

# 4. Upload + analyze (cookie/auth varsa Vercel UI'dan)

# 5. Render logs
# dashboard.render.com -> hasari-api -> Logs

# 6. Vercel logs
# vercel.com -> project -> Deployments -> latest -> Logs
```

---

## 15. Yaygın Sorunlar

| Sorun | Çözüm |
|---|---|
| Render build "image too large" | `MODEL_VARIANT=nano` yap, `yolo11n-seg` baked |
| Render "out of memory" | Sentry/observability paketlerini opsiyonel yap; `UVICORN_WORKERS=1` |
| Vercel build fail (pnpm) | Project Settings -> "Build & Development" -> Install Command'ı `pnpm install --frozen-lockfile` ile override et |
| CORS error (web -> api) | `CORS_ORIGINS` tam URL eşleşmeli (sondaki `/` olmayacak) |
| Supabase "too many connections" | Pooler URL'i kullan (port 6543), direct (5432) DEĞİL |
| Upstash command limit aşıldı | Cache TTL artır, polling interval'i çoğalt |

---

**Toplam aylık maliyet: 0.00 USD.** Demo, portföy ve pre-revenue MVP için
bu altyapı yeterli. Trafik artarsa Render starter ($7) + Upstash Pay-as-you-go
ile lineer büyüt.
