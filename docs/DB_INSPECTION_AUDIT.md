# DB Inspection Audit — Read-Only

**Tarih:** 2026-05-16
**Ortam:** Docker compose, `hasarui-postgres` (Postgres 16 healthy), `hasarui-backend` (healthy), `hasarui-redis`, `hasarui-minio`, `hasarui-worker`
**Database:** `arac_hasar`
**Migration head:** `20260516_idx` (Alembic, başarıyla uygulandı)
**Kapsam:** Sadece okuma. Schema değişikliği, veri silme, migration yazma yok.

---

## 1. TL;DR — Kritik Bulgu

**Schema çakışması canlı sistemde production blocker seviyesinde.**

- Alembic migration `0001_initial` çalıştı ve `inspections` tablosunu **ORM şemasıyla** oluşturdu (`user_id UUID FK users.id`, `image_count INT`, `status inspection_status ENUM`, `mode inspection_mode ENUM`, `model_versions JSONB`, hayır `client_id` / `image_urls` / `result` / `error` / `updated_at` yok).
- `services/backend/main.py` içindeki `_PgInspectionsAdapter` ve `save_inspection / update_inspection` fonksiyonları hâlâ **eski raw-SQL şemasını** (pilot-interim, `client_id TEXT`, `image_urls JSONB`, `result JSONB`, `error TEXT`) varsayıyor.
- `CREATE TABLE IF NOT EXISTS inspections (...)` deyimi sessizce skipliyor (tablo zaten var), bu yüzden boot başarılı görünüyor; ama ilk `INSERT/UPDATE/SELECT` request'inde `psycopg2.errors.UndefinedColumn` patlıyor.
- **Backend logundan teyit:**
  ```
  File "/app/main.py", line 212, in list
    cur.execute(...)
  psycopg2.errors.UndefinedColumn: column "result" does not exist
  LINE 1: SELECT id, status, created_at, completed_at, result
  ```
- Sonuç: `GET /v1/inspections` (history listesi), `POST /v1/inspections` (oluşturma), `PATCH /v1/inspections/{id}`, `DELETE /v1/inspections/{id}` endpoint'lerinin **hepsi DB modunda 500 dönüyor**. In-memory fallback DB available döndüğü için devreye girmiyor.

İkincil bulgu: Backend her DB çağrısında `psycopg2.connect()` ile yeni TCP bağlantısı açıyor; pool yok. Şu an `pg_stat_activity` tek bağlantı gösteriyor çünkü yukarıdaki hata yüzünden inspection trafiği oluşmuyor — pool problemi henüz tetiklenmedi, ama yük gelince patlayacak.

---

## 2. Tablo Envanteri (canlı `\dt`)

```
 Schema |       Name        | Type
--------+-------------------+------
 public | alembic_version   | table
 public | api_keys          | table
 public | audit_log         | table
 public | damages           | table
 public | inspection_images | table
 public | inspections       | table
 public | parts             | table
 public | users             | table
```

8 tablo + alembic_version. Hepsi `0001_initial` migration tarafından oluşturulmuş. `inspection_images` ayrı tablo (raw SQL'in beklediği `image_urls JSONB` yerine).

---

## 3. Gerçek Tablo Şemaları (psql `\d` çıktısı)

### 3.1 `inspections` (canlı, ORM şeması)

```
 Column                 | Type                     | Nullable | Default
------------------------+--------------------------+----------+------------------------------
 id                     | uuid                     | not null | gen_random_uuid()
 user_id                | uuid                     | not null |
 status                 | inspection_status        | not null | 'pending'::inspection_status
 mode                   | inspection_mode          | not null | 'async'::inspection_mode
 image_count            | integer                  | not null | 0
 created_at             | timestamptz              | not null | now()
 completed_at           | timestamptz              |          |
 processing_duration_ms | bigint                   |          |
 error_msg              | text                     |          |
 model_versions         | jsonb                    |          |

Indexes:
  inspections_pkey                    PRIMARY KEY (id)
  idx_inspections_user_created        btree (user_id, created_at DESC)
  idx_inspections_status              btree (status)
  idx_inspections_status_active       btree (status) WHERE status IN ('pending','processing')
  idx_inspections_completed_at        btree (completed_at DESC) WHERE status = 'done'
  idx_inspections_model_versions_gin  gin (model_versions)

FK in:  user_id          -> users(id) ON DELETE CASCADE
FK out: inspection_images.inspection_id, damages.inspection_id, parts.inspection_id
```

### 3.2 `inspections` (main.py raw SQL’in beklediği şema, **mevcut DEĞİL**)

```sql
-- services/backend/main.py:98-113 — _INSPECTIONS_SCHEMA_SQL
CREATE TABLE IF NOT EXISTS inspections (
    id UUID PRIMARY KEY,
    client_id TEXT NOT NULL,        -- ⚠ canlıda yok (canlıda user_id UUID)
    status TEXT NOT NULL,           -- ⚠ canlıda inspection_status ENUM
    image_urls JSONB NOT NULL,      -- ⚠ canlıda yok (ayrı inspection_images tablosu)
    result JSONB,                   -- ⚠ canlıda yok
    error TEXT,                     -- ⚠ canlıda error_msg
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()  -- ⚠ canlıda yok
);
CREATE INDEX IF NOT EXISTS idx_inspections_client_created
    ON inspections (client_id, created_at DESC);   -- ⚠ kolon yok, asla yaratılmadı
CREATE INDEX IF NOT EXISTS idx_inspections_status ON inspections (status);  -- ✓ adı aynı, ORM de yaratıyor
```

### 3.3 `users` (canlı)

```
 Column        | Type                | Nullable | Default
---------------+---------------------+----------+-------------------
 id            | uuid                | not null | gen_random_uuid()
 email         | varchar(255)        | not null |
 password_hash | varchar(255)        | not null |
 full_name     | varchar(255)        |          |
 role          | user_role           | not null | 'user'::user_role
 is_active     | boolean             | not null | true
 created_at    | timestamptz         | not null | now()
 updated_at    | timestamptz         | not null | now()
 last_login_at | timestamptz         |          |

Indexes:
  users_pkey         PRIMARY KEY (id)
  users_email_key    UNIQUE (email)
  idx_users_email    btree (email)                ⚠ users_email_key ile redundant
  idx_users_email_ci btree (lower(email))         ✓ case-insensitive lookup
  idx_users_role     btree (role)
```

**Mevcut user verisi (smoke test sonrası):**

```
 id                                   | email                   | role | created_at
--------------------------------------+-------------------------+------+--------------
 9fe19daf-91a6-...-ea40f4b309b4       | smoke@ex.com            | user | 2026-05-15 22:36
 ea8714a7-df89-...-d5cbed5265c4       | erdoganpeker4@gmail.com | user | 2026-05-15 22:50
```

Smoke test kullanıcısı yazıldı, doğrulandı.

### 3.4 `audit_log` (canlı, GIN bug fix sonrası)

```
 Column        | Type                | Nullable | Default
---------------+---------------------+----------+-------------------
 id            | uuid                | not null | gen_random_uuid()
 user_id       | uuid                |          |
 action        | varchar(128)        | not null |
 resource_type | varchar(64)         |          |
 resource_id   | varchar(128)        |          |
 metadata      | jsonb               |          |   -- attr: extra_metadata
 ip_address    | inet                |          |
 user_agent    | text                |          |
 created_at    | timestamptz         | not null | now()

Indexes:
  audit_log_pkey              PRIMARY KEY (id)
  idx_audit_log_user_created  btree (user_id, created_at DESC)
  idx_audit_log_action        btree (action)
  idx_audit_log_resource      btree (resource_type, resource_id)
  idx_audit_log_metadata_gin  gin (metadata)            ✓ migration 20260516_idx
FK: user_id -> users(id) ON DELETE SET NULL
```

GIN index `metadata` kolonu üzerinde başarıyla yaratılmış (önceki migration'da `extra_metadata` attribute adı kullanılarak indeksleme deniyordu, kolon adıyla düzeltildi).

### 3.5 `inspection_images`, `damages`, `parts`, `api_keys`

Hepsi ORM şemasıyla doğru oluşturulmuş, FK ve index tamam. Detay özet:

- `inspection_images`: `(inspection_id, order_idx)` UNIQUE index var, `order_idx >= 0` CHECK var, S3 key `varchar(512)`.
- `damages`: bbox/polygon/secondary_parts JSONB, GIN index on bbox + secondary_parts, confidence ve cost range CHECK constraint'leri var.
- `parts`: aynı pattern, daha basit.
- `api_keys`: partial index `idx_api_keys_active` only `is_active=true` rows.

---

## 4. ENUM Tipleri (canlı)

```
 enum_name         | values
-------------------+--------------------------------
 inspection_status | pending, processing, done, failed
 inspection_mode   | sync, async
 damage_type       | dent, scratch, crack, glass_shatter, lamp_broken, tire_flat
 severity_level    | hafif, orta, agir
 user_role         | admin, user
```

ENUM'lar migration tarafından doğru kurulmuş. main.py raw SQL `status TEXT` kullanıyor — yine uyumsuz (ORM `inspection_status` ENUM bekliyor, plain TEXT INSERT çoğunlukla geçecek ama mode hiç değer almıyor — `mode NOT NULL` constraint patlayacak, default `async` kurtarıyor).

---

## 5. Migration Durumu

```
$ docker exec hasarui-backend alembic current
20260516_idx (head)

$ docker exec hasarui-backend alembic history
0001_initial -> 20260516_idx (head), add GIN indexes on JSONB columns + partial completed_at index
<base> -> 0001_initial, initial schema — users, inspections, images, damages, parts, api_keys, audit_log

$ SELECT * FROM alembic_version;
 version_num
--------------
 20260516_idx
```

- Chain temiz, branch yok, head güncel.
- 2 migration: `0001_initial` (tüm tablolar + ENUM'lar + temel indexler), `20260516_idx` (GIN + partial completed_at index).
- Mismatch yok. ORM ile DB schema senkronize.
- **Sorun:** main.py raw SQL `_INSPECTIONS_SCHEMA_SQL` migration'a paralel ikinci bir schema kaynağı — bunu kullanmıyor olmamız gerekir.

---

## 6. main.py Raw SQL Repo vs ORM Uyumsuzluk Matrisi

| Operation                     | Raw SQL kolonu  | Canlı DB kolonu       | Sonuç |
|-------------------------------|-----------------|------------------------|-------|
| `save_inspection` INSERT      | `client_id`     | `user_id`              | ❌ UndefinedColumn |
| ↳                             | `image_urls`    | _yok_ (FK tablo)       | ❌ UndefinedColumn |
| ↳                             | `result`        | _yok_                  | ❌ UndefinedColumn |
| ↳                             | `error`         | `error_msg`            | ❌ UndefinedColumn |
| ↳                             | `status TEXT`   | `status inspection_status` | ⚠ cast otomatik olabilir |
| `update_inspection` UPDATE    | `result`        | _yok_                  | ❌ |
| ↳                             | `image_urls`    | _yok_                  | ❌ |
| ↳                             | `error`         | `error_msg`            | ❌ |
| ↳                             | `updated_at`    | _yok_                  | ❌ |
| `_PgInspectionsAdapter.list`  | `SELECT result` | _yok_                  | ❌ **Production'da gözlendi** |
| ↳                             | `WHERE client_id` | _yok_                | ❌ |
| `_PgInspectionsAdapter.get`   | `SELECT *`      | farklı kolonlar         | ⚠ döner ama normalize eski anahtarları aramaz |
| `_PgInspectionsAdapter.count` | `WHERE client_id` | _yok_                | ❌ |
| `delete_inspection`           | `DELETE WHERE id` | id var               | ✓ tek çalışan operasyon |
| `CREATE TABLE IF NOT EXISTS`  | -               | tablo zaten var        | ✓ skip (gizleyici) |
| `CREATE INDEX IF NOT EXISTS idx_inspections_client_created` | `client_id` kolonu | yok | ❌ silent fail (Postgres index'i tanımlamayı dener, kolon yok hatası) — log'a düşmüş olabilir |

**Endpoint etkisi:**

- `POST /v1/inspections` (main.py:634, 695) — `save_inspection()` çağrısı → INSERT patlar → 500.
- `GET /v1/inspections` (main.py:865-868) — `db.list()` + `db.count()` → SELECT patlar → 500. **Doğrulandı (log'ta var).**
- `GET /v1/inspections/{id}` (main.py:775, 807) — `db.get()` `SELECT *` döner ama eski anahtarlar (`client_id`, `image_urls`, `result`) olmadığı için sonradan `inspection["client_id"]` access'i KeyError verir → 500.
- `PATCH /v1/inspections/{id}` (main.py:704, 645) — `update_inspection(completed_at=..., status="failed", error=...)` → UPDATE patlar → 500.
- `DELETE /v1/inspections/{id}` (main.py:907) — tek çalışan path, çünkü sadece `id` eşleşmesi.

---

## 7. Index Kapsamı Karşılaştırması

### 7.1 `inspections` indexleri

| Index                              | Yaratan        | Kolon mantığı                          | Durum |
|-------------------------------------|----------------|----------------------------------------|-------|
| `inspections_pkey`                  | ORM + raw      | `id`                                   | ✓ |
| `idx_inspections_user_created`      | ORM (`0001_initial`) | `(user_id, created_at DESC)`     | ✓ canlıda var |
| `idx_inspections_client_created`    | raw SQL        | `(client_id, created_at DESC)`         | ❌ **canlıda YOK** (kolon yok, silent fail) |
| `idx_inspections_status`            | ORM + raw      | `status`                               | ✓ canlıda var (adı aynı, çakışma yok) |
| `idx_inspections_status_active`     | ORM            | partial `WHERE status IN ('pending','processing')` | ✓ |
| `idx_inspections_completed_at`      | ORM (`20260516_idx`) | partial `(completed_at DESC) WHERE status='done'` | ✓ |
| `idx_inspections_model_versions_gin`| ORM (`20260516_idx`) | GIN on `model_versions`           | ✓ |

**Yorum:** Raw SQL'in yaratmaya çalıştığı `idx_inspections_client_created` ve ORM'in `idx_inspections_user_created` farklı kolon (`client_id` vs `user_id`) için DEĞİL — aynı mantıksal sorgu için (user-scoped listing). Raw SQL versiyonu zaten yaratılamadı, çakışma olmadı. Tek geçerli index: `idx_inspections_user_created`. Ek action gereksiz.

### 7.2 `users` redundancy

`users.email` üzerinde **iki overlapping index**:
- `users_email_key` UNIQUE btree (email) — constraint'ten gelen, gerekli.
- `idx_users_email` btree (email) — manuel, **redundant** (UNIQUE zaten lookup için yeterli).
- `idx_users_email_ci` btree (lower(email)) — case-insensitive arama için, gerekli.

ORM `db_models.py` hem `unique=True` (constraint) hem `Index("idx_users_email", "email")` (manuel) tanımladığı için duplicate. Yaklaşık 50 byte/row index overhead × yazma maliyeti. Şu an 2 user var, etki yok ama prod'a önce temizlenmeli.

### 7.3 `audit_log` indexleri (önceki dalga GIN fix sonrası)

Tüm beklenen indexler canlı:
- `idx_audit_log_user_created (user_id, created_at DESC)` ✓
- `idx_audit_log_action (action)` ✓
- `idx_audit_log_resource (resource_type, resource_id)` ✓
- `idx_audit_log_metadata_gin gin (metadata)` ✓ (eski bug — ORM `extra_metadata` attribute adı kullanıyordu, kolon adı `metadata` ile düzeltildi)

### 7.4 Diğer FK indexleri

Tüm foreign key kolonları indexlenmiş (`damages.inspection_id`, `damages.image_id`, `parts.inspection_id`, `parts.image_id`, `inspection_images.inspection_id` via composite, `api_keys.user_id`, `audit_log.user_id`). FK-without-index anti-pattern yok.

---

## 8. Veri Durumu

```sql
SELECT count(*) FROM inspections;  -- 0
SELECT count(*) FROM audit_log;    -- 0
SELECT count(*) FROM users;        -- 2
SELECT count(*) FROM inspection_images; -- 0
SELECT count(*) FROM damages;      -- 0
SELECT count(*) FROM parts;        -- 0
SELECT count(*) FROM api_keys;     -- 0
```

```sql
SELECT status, count(*) FROM inspections GROUP BY status;
-- (0 rows)
```

- **Stuck `processing` inspection yok** (tablo boş zaten).
- **NULL result inspection yok** (tablo boş).
- Cleanup gerekecek bir veri yok.
- `inspections` boş olmasının sebebi büyük ihtimal yukarıdaki schema bug — kullanıcı POST'ladığında 500 alıyor, hiç yazılmıyor.

---

## 9. Connection Pool Durumu

```sql
SELECT count(*) AS total, count(*) FILTER (WHERE state='idle') AS idle,
       count(*) FILTER (WHERE state='active') AS active,
       count(*) FILTER (WHERE state='idle in transaction') AS idle_in_tx
FROM pg_stat_activity WHERE datname='arac_hasar';
```

```
 total | idle | active | idle_in_tx
-------+------+--------+------------
     1 |    0 |      1 |          0   -- (sadece açtığım psql)
```

Backend prosesi şu an idle. Inspection trafiği patlayan endpoint'ler yüzünden test edilmemiş. Server tarafı durum:

```
max_connections = 100
shared_buffers  = 128MB
```

**Backend bağlantı yönetimi (`services/backend/main.py:116-119`):**

```python
def _pg_connect():
    if _psycopg2 is None:
        raise RuntimeError("psycopg2 yuklu degil")
    return _psycopg2.connect(settings.database_url, connect_timeout=3)
```

`save_inspection`, `update_inspection`, `_PgInspectionsAdapter.{get,list,count}`, `delete_inspection`, `init_db` — **her biri her çağrıda yeni TCP/SSL handshake**. `with _pg_connect() as conn:` context manager bağlantıyı close etmiyor (psycopg2'de `with` sadece transaction'ı commit/rollback eder; close değil) ama referans kaybolunca GC ile kapanır. Yine de:

- Per-request handshake latency: ~5-15 ms ekstra
- Postgres'in `max_connections=100` limiti — concurrent yük altında hızla tükenir
- Pgbouncer / SQLAlchemy pool yok (oysa `database.py` ORM session pool'u var; sadece raw SQL pool dışında)

**Auth ve diğer router'lar** muhtemelen `database.py`'deki SQLAlchemy session'ını kullanıyor (orada pool default'ları gelir). main.py'nin raw SQL'i ayrı kanal.

---

## 10. Önerilen Düzeltmeler (uygulama YOK, sadece öneri)

### P0 — Schema uyumsuzluğunu çöz (production blocker)

**Tercih edilen yol: main.py raw SQL repo'sunu sil, ORM session'a geç.**

`services/backend/main.py` içinde:
1. `_INSPECTIONS_SCHEMA_SQL`, `_pg_connect`, `_db_available`, `init_db`, `_MemoryStore`, `_PgInspectionsAdapter`, `_normalize_inspection_row`, `save_inspection`, `update_inspection`, `delete_inspection`, `get_db` — hepsi silinmeli (~250 satır).
2. Endpoint'ler (main.py:634, 645, 695, 704, 775, 807, 865-868, 907) `database.py`'deki SQLAlchemy `SessionLocal` üzerinden `db_models.Inspection` + `db_models.InspectionImage` modellerine yazsın.
3. `client_id` → `user_id` mapping: `auth.client_id` zaten user UUID string'i (auth.py:268). UUID parse + `Inspection.user_id` set et.
4. `image_urls: list[str]` → `image_count` + `InspectionImage` row-per-image (s3_key kolonu).
5. `result: dict` → `Damage` + `Part` row'ları (mevcut tablolar bunun için yapılmış).
6. `error: str` → `error_msg`.
7. `status: str` → `inspection_status ENUM` (zaten 'pending'/'processing'/'done'/'failed' değerleri kullanılıyor).
8. `updated_at` kullanan kod (raw SQL UPDATE) → ihtiyaç yok, ORM `created_at`/`completed_at` yeterli, ya da migration ile ekle.

**Alternatif (hızlı patch, geçici): ORM modeli güncellemeden raw SQL'i ORM şemasına uydur.**

Hızlı ama önerilmez — iki schema kaynağı sorununu çözmüyor, sadece raw SQL'i tekrar yazıyor. Gerçek çözüm tek kaynağa (ORM) inmek.

### P1 — Connection pooling

`database.py`'de zaten SQLAlchemy `engine = create_engine(..., pool_size=N, max_overflow=M)` olmalı; raw SQL kaldırıldıktan sonra tüm DB trafiği pool'dan geçer. Önerilen başlangıç:
```python
create_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=300,
)
```
Production'da PgBouncer ekle (transaction mode), `max_connections=100` limitini aşmamak için.

### P2 — Index temizliği

`idx_users_email` index'i `users_email_key` UNIQUE constraint ile redundant. ORM `db_models.py`:
```python
__table_args__ = (
    Index("idx_users_email", "email"),  # <-- SİL, unique=True yeterli
    Index("idx_users_role", "role"),
)
```
Yeni migration: `DROP INDEX idx_users_email;`. `idx_users_email_ci (lower(email))` korunur.

### P3 — Observability

- `pg_stat_statements` extension aktif et:
  ```sql
  CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
  ```
  `postgresql.conf` veya docker-compose'ta `-c shared_preload_libraries=pg_stat_statements`. Slow query top-N için.
- `pg_stat_activity` snapshot endpoint (admin): aktif/idle bağlantı sayımı.
- Backend `request_id` log'ları zaten var (middleware), DB query'lerine de yansıtmak için SQLAlchemy `before_cursor_execute` event listener.

### P4 — Test verisi temizliği

Şu an gerekli değil (tablolar boş). İlerideki cleanup task'ı için (TTL job, geçici inspection silme):
```sql
-- Stuck processing > 1h
DELETE FROM inspections
WHERE status = 'processing'
  AND created_at < NOW() - INTERVAL '1 hour';
-- partial index idx_inspections_status_active bu sorguyu hızlandırır
```

---

## 11. EXPLAIN ANALYZE

Tablo boş olduğu için query plan testi anlamsız (Seq Scan dönüyor, bütün planner cardinality estimasyonları varsayım). Veri girdikten sonra (P0 fix sonrası) aşağıdaki sorgular için baseline alınmalı:

```sql
-- Listeleme (en sık endpoint)
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, status, image_count, created_at, completed_at
FROM inspections
WHERE user_id = '...'::uuid
ORDER BY created_at DESC
LIMIT 20 OFFSET 0;
-- Beklenen: Index Scan using idx_inspections_user_created

-- Aktif queue
EXPLAIN (ANALYZE, BUFFERS)
SELECT id FROM inspections WHERE status IN ('pending','processing')
ORDER BY created_at LIMIT 10;
-- Beklenen: Bitmap Index Scan on idx_inspections_status_active

-- Detay (join damages + parts)
EXPLAIN (ANALYZE, BUFFERS)
SELECT i.*, json_agg(DISTINCT d.*) AS damages, json_agg(DISTINCT p.*) AS parts
FROM inspections i
LEFT JOIN damages d ON d.inspection_id = i.id
LEFT JOIN parts   p ON p.inspection_id = i.id
WHERE i.id = '...'::uuid
GROUP BY i.id;
-- Beklenen: Nested Loop + Index Scan on idx_damages_inspection, idx_parts_inspection
```

---

## 12. Özet Tablo

| Konu                              | Durum | Aksiyon (önerilen) |
|-----------------------------------|-------|----------------------|
| Alembic head                       | ✓ `20260516_idx` | — |
| ORM şeması canlıda                | ✓ uygulandı | — |
| Raw SQL repo vs ORM çakışması     | ❌ **production blocker** | main.py raw SQL'i sil, ORM session'a geç (P0) |
| `audit_log` GIN index             | ✓ fix uygulanmış | — |
| FK index kapsamı                  | ✓ tam | — |
| `users.email` index duplikasyonu  | ⚠ `users_email_key` + `idx_users_email` redundant | `idx_users_email` drop (P2) |
| Connection pool                   | ⚠ raw SQL per-call connect | ORM pool + PgBouncer (P1) |
| `inspection_status` ENUM          | ✓ canlıda | — |
| Stuck `processing` data           | ✓ yok (tablo boş) | TTL job ileride (P4) |
| `pg_stat_statements`              | ❌ aktif değil | enable (P3) |
| EXPLAIN baseline                  | — veri yok | P0 sonrası |

---

## 13. Doğrulama Komutları (reproducability)

```bash
# Schema
docker exec hasarui-postgres psql -U postgres -d arac_hasar -c "\d inspections"
docker exec hasarui-postgres psql -U postgres -d arac_hasar -c "\d audit_log"
docker exec hasarui-postgres psql -U postgres -d arac_hasar -c "\d users"
docker exec hasarui-postgres psql -U postgres -d arac_hasar -c "\dt"

# Migration
docker exec hasarui-backend alembic current
docker exec hasarui-backend alembic history

# Veri
docker exec hasarui-postgres psql -U postgres -d arac_hasar \
  -c "SELECT id,email FROM users; SELECT count(*) FROM inspections; SELECT count(*) FROM audit_log;"

# Bağlantı
docker exec hasarui-postgres psql -U postgres -d arac_hasar \
  -c "SELECT count(*), state FROM pg_stat_activity WHERE datname='arac_hasar' GROUP BY state;"

# Hata teyidi (backend logu)
docker logs --tail 200 hasarui-backend 2>&1 | grep -i "UndefinedColumn\|result\|client_id"
```

---

**Kaynak dosya referansları:**

- `C:\Users\Erdogan\Desktop\arac-hasar-v2\services\backend\main.py` (raw SQL repo: satır 80-326)
- `C:\Users\Erdogan\Desktop\arac-hasar-v2\services\backend\db_models.py` (ORM modelleri)
- `C:\Users\Erdogan\Desktop\arac-hasar-v2\services\backend\migrations\versions\0001_initial.py`
- `C:\Users\Erdogan\Desktop\arac-hasar-v2\services\backend\migrations\versions\20260516_add_gin_and_partial_indexes.py`
- `C:\Users\Erdogan\Desktop\arac-hasar-v2\services\backend\database.py` (SQLAlchemy session — burası kullanılmalı)
- `C:\Users\Erdogan\Desktop\arac-hasar-v2\services\backend\auth.py` (auth.client_id semantiği: user UUID str)
