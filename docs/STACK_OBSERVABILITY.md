# Stack Observability Sweep — arac-hasar-v2

**Sweep zamanı:** 2026-05-15 23:00–23:05 UTC (canlı stack üzerinde READ-ONLY)
**Mod:** Sadece okuma. Hiçbir container restart / compose / kod değişikliği yapılmadı.
**Kapsam:** Backend (FastAPI), Worker (Celery), Postgres 16, Redis, MinIO + minio-init.

---

## 1) Servis sağlık özeti (tek satır)

| Servis | Durum | Uptime | Hızlı yorum |
|---|---|---|---|
| `hasarui-backend` | UP / healthy | ~27 dk (watchfiles tetiklemeli sık reload) | `/health` 200, `ml_loaded:true`, ama 5xx üretiyor — DB schema drift |
| `hasarui-worker` | UP / healthy | ~19 dk | Celery `ready`, broker bağlı, görev kuyrukta yok; task çağrısı gözlenmedi |
| `hasarui-postgres` | UP / healthy | ~55 dk | PG 16.13, conn OK, ama uygulama beklenen şemayla uyuşmuyor (drift) |
| `hasarui-redis` | UP / healthy | ~55 dk | 11 connected client, DBSIZE=3, RDB snapshot her ~60s sorunsuz |
| `hasarui-minio` | UP / healthy | ~55 dk | 2 bucket (`inspections`, `models`) hazır, default credential uyarısı var |
| `hasarui-minio-init` | Exited (0) | bir kez koşmuş | **Beklenen davranış** — bucket bootstrap one-shot job, başarılı bitmiş |

Backend → DB / Redis / S3 bağlantı runtime testi (read-only `docker exec` ile):
- Postgres `SELECT 1` → `(1,)` OK
- Redis `PING` → `True` OK
- MinIO `list_buckets` → `[inspections, models]` OK

Yani **alt katman tamamen ayakta**. Sorun upper-layer / şema seviyesinde.

---

## 2) WARNING / ERROR ham listesi (top 10, ağırlık sırasına göre)

> Aynı pattern'ler defalarca tekrar ettiği için dedup edilmiş haldedir.

1. **[CRITICAL] `psycopg2.errors.UndefinedColumn: column "client_id" of relation "inspections" does not exist`**
   `POST /api/v1/inspect/sync` → 500. Boot'ta da `inspections schema bootstrap basarisiz` aynı sebepten. Defalarca tekrarlandı (4868, 4644, 4627, 4604 PID'lerinde).

2. **[CRITICAL] `psycopg2.errors.UndefinedColumn: column "result" does not exist`**
   `GET /api/v1/inspect?page=1&page_size=20` → 500. `main.py:215` `SELECT id, status, created_at, completed_at, result FROM inspections ...` sorgusu canlı şemada hiç olmayan iki sütun (`result`, `client_id`) istiyor.

3. **[WARN] `inspections schema bootstrap basarisiz: column "client_id" does not exist`**
   Backend her boot'ta `CREATE TABLE IF NOT EXISTS inspections (... client_id TEXT ...)` çalıştırıyor; tablo zaten **alembic ile** farklı şemada var (`user_id UUID`, `status inspection_status`, vs.) — `CREATE INDEX ... ON (client_id, created_at)` patlıyor. Idempotent değil, drift kalıcı.

4. **[WARN] `services/backend/cost_table.yaml bulunamadi, sadece hard defaults kullanilacak`**
   Backend ve worker'ın her cold-load'unda görülüyor. `cost_table.yaml` dosyası `/app/cost_table.yaml` olarak mevcut ama kod `services/backend/cost_table.yaml` arıyor — relative-path mismatch. Soft warning, runtime kırmıyor; AI Engineer ajanı veya path düzeltmesi gerekiyor. **Not düşüldü, kalıcı bir konfig sorunu.**

5. **[WARN] `JWT_SECRET_KEY is short or unset; OK only for local dev`**
   Her process startup'ında stderr'e basılıyor. Dev için kabul; stage/prod öncesi 32+ karakter secret enjekte edilmeli.

6. **[WARN] `WARN: Detected default credentials 'minioadmin:minioadmin'` (MinIO)**
   MinIO root user/password default. Dev için OK, ama `.env`/secret yönetimi planına eklenmeli.

7. **[WARN] (Worker) `user config directory '/home/app/.config/Ultralytics' is not writable, using '/tmp/Ultralytics'`**
   Container içi user `app` HOME yazılamıyor. Ultralytics fallback `/tmp` kullanıyor → sorun yok ama her boot'ta yeni settings yazıyor. `YOLO_CONFIG_DIR=/tmp/Ultralytics` env'i set edilirse log temizlenir.

8. **[INFO→Sürtünme] `jwt.verify.fail reason=JWTError` + `HTTPException 401 path=/auth/me|/auth/refresh`**
   Smoke koşusunda beklenen — frontend stale token ile boot oluyor. Anomali değil, ama frontend tarafında refresh akışı doğru çalışıyorsa 401 sayısı düşmeli.

9. **[INFO→404] `POST /api/v1/auth/login HTTP/1.1" 404 Not Found`**
   PowerShell smoke testi yanlış path'e çağrı atmış; gerçek route `/auth/login`. Tek seferlik, kod sorunu değil.

10. **[INFO] WatchFiles çok sık reload tetikliyor**
    Son 5 dakikada en az 4 reload (`main.py`, `tests/test_real_inference.py`, `tests/test_edge_cases.py`). ML pipeline her reload'da yeniden cold-load (1–3 sn). Smoke veya test suite koşarken paralel istek atılıyorsa **502/cold-start timing race** yaşanabilir.

---

## 3) Anomali yorumu

### 3.1 ANA BULGU — DB schema drift (backend ↔ alembic uyumsuzluğu)
- **Canlı tablo (`\d inspections`):** `id UUID, user_id UUID, status inspection_status, mode inspection_mode, image_count INT, created_at, completed_at, processing_duration_ms BIGINT, error_msg TEXT, model_versions JSONB`. Alembic migrasyonlarıyla üretilmiş, ilişkili `damages`, `parts`, `inspection_images`, `audit_log`, `users`, `api_keys` tabloları da var. **Bu doğru/güncel şema.**
- **Backend `main.py` kodu** ise **legacy** şema bekliyor: `client_id TEXT`, `result JSONB`, `error TEXT`, `image_urls JSONB`. Bu iki şema arasında dönüşüm/repository katmanı yok.
- Sonuç: `GET /api/v1/inspect` listesi 500, `POST /api/v1/inspect/sync` 500. **Frontend dashboard/inspection listesi web akışında patlayacak.** Login dahi geçse, bir sonraki API çağrısı bu hataya çarpacak.
- Backend boot'taki `CREATE TABLE IF NOT EXISTS ... client_id` bloku zararsız hata atıyor (tablo zaten var, IF NOT EXISTS sebebiyle CREATE TABLE skip ediliyor, ama sonraki `CREATE INDEX ... (client_id)` patladığı için tüm bootstrap fail oluyor). Yani DB'de yan etki yok, sadece WARN log.

> **Bu, Backend Engineer ajanının sorumluluğunda — DevOps tarafı sadece raporlamakta.**

### 3.2 audit_log GIN index bug — DURUM: TEMİZ
- `\d audit_log` sonucu: GIN index `idx_audit_log_metadata_gin` mevcut, `metadata JSONB` sütunu üzerine kurulu.
- Geçmişte raporlanan `extra_metadata` adlandırma sorunu **çözülmüş** — kolon zaten `metadata` ve GIN index sorunsuz duruyor.
- Boot sonrası tekrar gelmedi, restart sonrası temiz.

### 3.3 Worker PYTHONPATH — DURUM: OK
- `docker exec hasarui-worker printenv PYTHONPATH` → `/app`
- `/app` içinde modüller flat (worker.py değil ama Celery `worker.celery_app` referansıyla başarılı boot ettiği görülüyor). Boot logu `Connected to redis://redis:6379/0` + `celery@... ready.` veriyor.
- **Sorun yok, env doğru uygulanmış.**

### 3.4 CORS davranışı — OK
- Backend logunda `OPTIONS /auth/login`, `OPTIONS /auth/me`, `OPTIONS /auth/refresh`, `OPTIONS /api/v1/inspect?page=1&page_size=20` → hepsi **200**.
- `CORS_ORIGINS` env: `http://localhost:3000,http://localhost:1420,http://tauri.localhost,tauri://localhost,http://localhost:8081` — Next web (3000), Tauri (1420 / tauri scheme) ve RN Metro (8081) dahil, preflight tüm istemciler için geçiyor.
- **Anomali yok.**

### 3.5 Health endpoint
- `curl /health` → `{"status":"ok","ml_loaded":true,"timestamp":"...","version":"0.3.0"}`
- **Eksik (öneri):** `db_connected`, `redis_connected`, `s3_connected` alt-sağlık alanları yok. Şu an `/health` "uygulama ayakta + model var" diyor ama DB drift olsa bile 200 dönüyor — yanıltıcı. Yeşil görünüyor, akış patlıyor.

### 3.6 Postgres slow-query log
- `log_min_duration_statement = -1` (kapalı). Brief'te "default 0 yani off" yazılmış ama gerçek değer `-1` (PG'de off karşılığı). Slow query görünürlüğü yok.

### 3.7 Resource
| Servis | CPU% | RAM | Yorum |
|---|---|---|---|
| backend | 0.96% | 908 MiB | Idle'da yüksek değil; ML modelleri RAM'de sıcak |
| worker | 0.10% | 778 MiB | Idle, model bellekte |
| postgres | 0.00% | 60 MiB | Çok hafif |
| redis | 0.34% | 8.6 MiB | Boş |
| minio | 0.00% | 128 MiB | Boş |
| **Toplam** | ~1.4% | **~1.85 GiB / 15.5 GiB** | OOM riski yok, başka ML pipeline koşulabilir |

Backend image 3.84 GB — dev için OK, prod'da multi-stage + slim base ile düşürülmeli (Önerilere bakınız).

### 3.8 Redis snapshot davranışı
- Her ~60 sn'de `RDB save` çalışıyor (`save 60 1` default). Boş Redis için maliyetsiz, ama prod'da `appendonly yes` (AOF) + tuned save policy daha iyi olur.

### 3.9 minio-init Exited (0) — VURGU
- **Beklenen ve doğru davranış.** One-shot init job — bucket'ları (`inspections`, `models`) yaratıp policy uygulayıp çıkıyor. `Exited (0)` = success. Compose `restart: "no"` veya `depends_on` ile yönetiliyorsa hiç dokunmamak gerekir.

---

## 4) Önerilen iyileştirmeler (infra/config — kod değil)

### Yüksek öncelik
1. **`/health` endpoint'ini derinleştir:** alt-bağımlılık probu ekle (DB/Redis/S3 ping). Şu an "yeşil-yalan" durumu mümkün. Kod değişikliği gerekir ama envanter olarak konfige çekilebilir (opsiyonel timeout env: `HEALTH_DEEP_TIMEOUT_MS=300`).
2. **Postgres slow query log aç:** dev compose'a `command: ["postgres", "-c", "log_min_duration_statement=200"]` ekle → 200 ms üzerini logla. Drift sonrası query analizi kolaylaşır.
3. **`YOLO_CONFIG_DIR=/tmp/Ultralytics`** env'i worker servisine ekle → boot log'unda kalıcı uyarı kaybolur.

### Orta öncelik
4. **WatchFiles reload kapsamını daralt:** `tests/` klasörünü `--reload-exclude` ile dışla. Şu an test dosyası değiştiğinde bile prod-benzeri uvicorn restart oluyor → smoke ile race condition. Compose'da `command: ["uvicorn", ..., "--reload", "--reload-dir", "/app", "--reload-exclude", "tests/*"]`.
5. **MinIO root credential'ları env üzerinden gerçek değerlere çevir** (dev'de bile `.env` ile). `minioadmin:minioadmin` shipped olarak kalmamalı; pilot/staging'e geçişte unutulması kolay.
6. **JWT_SECRET_KEY** için 32+ karakter `.env` default'u commit'le (sadece dev için).

### Düşük öncelik (kozmetik / hijyen)
7. **`cost_table.yaml` path düzeltmesi** — kodda relative `services/backend/cost_table.yaml` aranıyor, dosya `/app/cost_table.yaml`. Env `COST_TABLE_PATH=/app/cost_table.yaml` eklenip kod tarafı onu okursa warning susar. (Backend/AI Engineer ajanı kapsamında.)
8. **Backend image küçültme (3.84 GB → hedef ~1.5 GB):** multi-stage build, `--no-cache-dir`, torch CPU-only wheel, model dosyaları için ayrı volume. Sadece prod hattı için kritik.
9. **Redis persistence stratejisi:** dev için sorun yok; prod öncesi AOF + `save ""` (sadece AOF) veya managed Redis.
10. **Observability stack** (Prometheus + Grafana + Loki) için `observability/` klasörü zaten var — log shipping (promtail) henüz aktif değil. Pilot öncesi mevcut altyapı bağlanmalı (ayrı bir görev).

---

## 5) Web kullanıcı akışı için net çıkarım

Kullanıcı `localhost:3000` üzerinden:
- **Login (`POST /auth/login`)** → 200 çalışıyor, JWT alıyor. OK.
- **`GET /auth/me`** → token geçerliyse 200. OK.
- **`GET /api/v1/inspect?page=1&page_size=20`** (dashboard / liste) → **500 (UndefinedColumn: result)**. Frontend liste boş veya error toast.
- **`POST /api/v1/inspect/sync`** (anında inceleme) → **500 (UndefinedColumn: client_id)**.
- **`POST /api/v1/inspect`** (async) → muhtemelen aynı insert path'inde patlar (kod aynı `db.list`/`db.insert` katmanını kullanıyor). Async testi smoke logunda görünmedi ama eşdeğer risk.

> Backend ile DB arasındaki schema drift, web akışındaki tek **canlı blocker**'dır. Diğer container'lar (worker, redis, minio, postgres) operasyonel ve sağlıklıdır.

---

## 6) DevOps tarafından bu sweep'te yapılan değişiklikler

**HİÇBİRİ.** Hiçbir container restart edilmedi, hiçbir compose/Dockerfile düzenlenmedi, hiçbir env override uygulanmadı. Sadece:
- `docker ps`, `docker stats`, `docker logs --tail`
- `docker exec ... psql / redis-cli / python -c` ile read-only sorgular
- `curl /health`

—

**DevOps Automator — observability sweep tamamlandı.**
**Rapor tarihi:** 2026-05-15
**Sıradaki sahip:** Backend Engineer (schema drift onarımı için).
