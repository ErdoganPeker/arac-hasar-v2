# PERFORMANCE NOTES — arac-hasar-v2

Statik kod analizi ile cikarilmis darbogazlar ve **tahmini** kazanim listesi.
Bu dosya hicbir benchmark calistirilmadan, sadece kaynak okuma uzerinden uretildi —
sayilar gercek olculmedi, mantik tabanli tahminlerdir. Hedef metrikler README'den
alindi: end-to-end < 8s / 4 foto, damage ~45ms, parts ~30ms, severity ~12ms / image.

Hedef bandi su an SADECE GPU + warmup + 1 image varsaymina dayaniyor; bu dosyadaki
darbogazlar duzeltilmezse 4-foto end-to-end realistik tahminim 12-25s arasinda.

---

## 1) Backend — `main.py`, `ml_service.py`, `worker.py`, `ws.py`, `database.py`

### 1.1 [KRITIK] Sync endpoint event-loop'u bloklar — async def icinde senkron `ml_pipeline.analyze`

**Konum:** `services/backend/main.py:593-628` (`_process_sync`)

```python
async def _process_sync(files, auth):
    for i, f in enumerate(files):
        content, url = await _store_upload(f, inspection_id, i)
        img = _decode_image(content, i)
        r = ml_pipeline.analyze(img)   # <-- BLOKLAR! Senkron 100-500ms GPU isi
```

`ml_pipeline.analyze` icinde `_infer_lock` ve YOLO `predict()` cagrilari **senkron**;
async route icinde dogrudan cagrilirsa uvicorn worker'inin event-loop'u tum yaglar
boyunca bloke olur — baska istekler queue'lanir. `ml_service.py` icinde zaten
`_analyze_one_async` -> `asyncio.to_thread` helper'i var ama `_process_sync` onu
**kullanmiyor**, dogrudan blocking call yapiyor.

Ayni dosyadaki `_decode_image` (cv2.imdecode) de senkron — kucuk ama bloklayici.

**Tahmini etki:** 1 uvicorn worker'da concurrent 4 sync request -> her biri
sirayla iclendigi icin p95 latency 4x artar. Fix sonrasi: aci p95 ayni ama
diger endpoint'ler (history, status) bloklanmaz; throughput 1.5-2x.

**Onerilen fix (kod degisikligi yok, sadece not):**
```python
r = await asyncio.to_thread(ml_pipeline.analyze, img)
```
Hatta tum sync loop'u `asyncio.gather` ile parallelize edilebilir (asagiya bak).

---

### 1.2 [KRITIK] Sync mode coklu goruntu — seri islem, paralellestirilebilir

**Konum:** `main.py:598-606`

Sync moda 5 goruntuye kadar izin var (`max_images_sync`) ve hepsi sirayla isleniyor:
upload (S3 await) -> decode -> analyze -> sonraki. Upload S3 ve decode CPU; ML
GPU. Bunlari pipelining ile orterek wall-clock 30-40% kisaltilabilir.

**Tahmini etki:** 5-foto sync mod 5*1.5s ~= 7.5s -> ~4.5-5.5s. Single-foto
icin etki yok.

**NOT:** GPU paylasimi `_infer_lock` ile serialize edildigi icin `analyze`
calls'i gercekten paralel calismaz (tek GPU/lock). Ama upload+decode `gather`
edilince ML adimindan **once** is yapilmis olur.

---

### 1.3 [KRITIK] ML pipeline: 3 model SERI calisiyor — README ile celiskili

**Konum:** `services/ml/pipeline.py:534-554` (`analyze` icindeki timing bloku)

```python
damages = self._detect_damages(image)       # ~45ms
parts = self._detect_parts(image)           # ~30ms
self._assign_parts_to_damages(...)          # CPU, ~5-15ms (mask IoU)
self._classify_severities(damages, image)   # her hasar icin ~12ms (CNN)
```

README.md:153: *"All three models run in parallel per image"* — **YANLIS**.
`_detect_damages` ve `_detect_parts` art arda cagriliyor; severity bunlardan
sonra geliyor cunku `primary_part`'a ihtiyaci var.

**Damage + Parts gercekten paralel olabilir** (severity'den onceki adim) cunku
ikisi de input olarak sadece image aliyor. `concurrent.futures` veya CUDA
streams ile paralel kosulursa:
- Mevcut: damage(45) + parts(30) = 75ms model wall-clock
- Paralel: max(45, 30) = 45ms -> **~30ms / image kazanc**, 4 foto icin
  **~120ms / inspection** (kucuk ama bedava).

GPU bound oldugu icin tek GPU uzerinde gercek paralellik sinirli; ama Python
GIL'i serbest birakildigi icin (ultralytics+torch C extension'da release eder)
ThreadPoolExecutor ile sample-level overlap mumkun. CPU device'inda kazanc
buyuk (~20-30ms).

**Severity** her damage icin ayri CNN forward — `_classify_severities` icinde
`for d in damages: severity.predict(...)` (line 481). Bu **N+1 GPU call**.
Birden cok crop tek batch'te yapilirsa **N kez 12ms -> ~1*30ms** (batch
inference). 5 hasarli foto icin: 5*12=60ms -> 25ms, ~35ms/image kazanc.

**Tahmini etki:** Per-image 30-70ms; 4-foto inspection icin **~200-300ms**
toplam. Hedef <8s bandinda kalmasi acisindan kritik.

---

### 1.4 [YUKSEK] ML warmup yapilmis ama yarim — sadece damage+parts

**Konum:** `services/backend/ml_service.py:91-96`

```python
dummy = np.zeros((settings.ml_imgsz, settings.ml_imgsz, 3), dtype=np.uint8)
self._pipeline.analyze(dummy)
```

`analyze` cagrildigi icin tum pipeline asilgar (severity dahil), ama
`pipeline.warmup()` (pipeline.py:312) icin ayri bir method var ki **severity
modeli warm etmiyor** (sadece damage+parts predict). `analyze(dummy)` versiyon
genis ama dummy resimde `damages` listesi bos olacagi icin **severity asla
calismaz** -> ilk gercek isteğin severity adimı cold-start (CUDA kernel JIT,
~300-1000ms ekstra).

**Tahmini etki:** Ilk gercek istek 0.3-1.0s daha yavas. Fix: warmup dummy
icin sahte bir damage ekle veya `severity.predict` ayni anda cagir.

---

### 1.5 [KRITIK] Upload memory load — buyuk fotoda RAM patlar, streaming yok

**Konum:** `main.py:495-501`

```python
async def _store_upload(file, inspection_id, index):
    content = await file.read()   # <-- TUM bytes RAM'e
    _validate_image_file(file, content, index)
    ...
    url = await upload_image(content, key, ...)
```

`file.read()` tum dosyayi RAM'e yukler. `max_image_size_mb=10` * 20 async images
= **200MB / request** bellek. Concurrent 10 istekte 2GB. Render free tier'in
512MB-1GB RAM limitleri ile uyumsuz; OOM kill riski.

**Fix:** `UploadFile.file` chunked iterator + S3 multipart upload, validasyon
icin sadece ilk birkac KB (MIME magic bytes).

**Tahmini etki:** Bellek pik 200MB -> 20-40MB; RAM olum spike'lari ortadan
kalkar. Throughput dogrudan etkilenmez ama autoscale-OOM cycle dururlar.

**Ek:** `storage.download_image` (storage.py:108-126) worker'da indirme yapinca
yine memory load. Worker icin disk-stream + decode-on-fly daha guvenli.

---

### 1.6 [KRITIK] Database — iki paralel sistem, bağlanti pool kullanilmiyor

**Konum:** `main.py:88-324` (psycopg2 raw SQL) + `database.py` (SQLAlchemy async asyncpg)

`database.py` cok guzel async engine + pool (`pool_size=10, max_overflow=20,
pool_pre_ping`) hazirlamis ama `main.py` **bunu kullanmiyor**! Her DB cagrisinda
yeni `psycopg2.connect()` aciliyor:

```python
def _pg_connect():
    return _psycopg2.connect(settings.database_url, connect_timeout=3)
```

Her `save_inspection`, `update_inspection`, `get_inspection`, `list_inspections`,
`count` cagrisi **3-handshake TCP + auth = ~15-50ms ekstra latency / call**.
WS polling fallback (`ws.py:154-191`) saniyede 1 kere bu islemi yapiyor — 600s
boyunca 600 ekstra connection setup, **inanilmaz savurgan**.

**Tahmini etki (en buyuk single-fix):**
- Her DB endpoint icin **15-50ms eklenen baglanti maliyeti** ortadan kalkar.
- WS polling (Redis yoksa) 600 connection -> 1 persistent.
- `GET /api/v1/inspect` (history) suanki tahmin: 100-200ms (count + list = 2
  ayri baglanti). Pool'lu hali: 20-40ms. **~150ms -> 30ms kazanim, 5x.**

Action: `main.py` icindeki repo'yu ORM session'a tasi (yorum yapilmis, henuz
yapilmamis). pgbouncer + asyncpg tek baglanti ile bu darbogazi tamamen kapatir.

---

### 1.7 [YUKSEK] N+1 yok — ama list endpoint count + items 2 ayri query

**Konum:** `main.py:716-743` (`list_inspections`)

```python
raw_items = db.list(client_id=auth.client_id, limit=page_size, offset=offset)
total = db.count(client_id=auth.client_id) if hasattr(db, "count") else len(raw_items)
```

Iki ayri DB roundtrip. Postgres'te `count(*) OVER ()` window function ile tek
query'e indirilebilir. Pool olmayan ortamda her biri ayri TCP setup demek
(yukaridaki 1.6'ya ek).

In-memory fallback'te paterns gercek N+1 olmaz cunku `_MemoryStore.list/count`
zaten dict tarama, ama Postgres'te `count(*)` filter index taramasi yapar.

**Tahmini etki:** History endpoint 80-150ms -> 40-80ms. Index'lerin var
oldugu zaten dogrulandi (`idx_inspections_client_created` line 108-110).

---

### 1.8 [ORTA] Celery worker — `asyncio.run` her task icin yeni event loop

**Konum:** `worker.py:113-115`

```python
from ml_service import run_inspection
aggregated = asyncio.run(run_inspection(image_bytes, user_id=inspection_id))
```

`asyncio.run` her task'ta yeni loop kurar/kapatir (~10-20ms setup). Worker
sadece sync ML cagirdigi icin async tum kullanim aslinda gereksiz; ya da
worker bazinda persistent loop kurulabilir. **Marjinal, dusuk oncelik.**

---

### 1.9 [ORTA] WebSocket polling fallback — DB Hammer

**Konum:** `ws.py:154-191`

Redis yoksa her saniyede `_get_inspection` cagrisi (yine pool'suz `psycopg2.connect`).
10 dakika boyunca 600 query.

**Tahmini etki:** 1.6 pool fix'i ile zaten cozulur. Yine de Redis pub/sub
aktif tutmak (`redis_url` set edili) zorunlu olmali — production'da fallback
asla devreye girmemeli.

---

## 2) ML Pipeline — `services/ml/pipeline.py`

### 2.1 [KRITIK] (Yukarida 1.3) Damage + Parts seri; Severity per-damage loop

### 2.2 [ORTA] Image preprocess — resize cv2/PIL roundtrip

**Konum:** `pipeline.py:89-175` (`load_image_bgr`, `_pil_to_bgr`)

PIL'le decode -> numpy convert -> cv2 BGR. YOLO `predict` icine direkt numpy
gonderiliyor ki ultralytics zaten 640x640'a resize ediyor (`imgsz=640`).
Yani 4000x3000 telefon foto:
1. backend `_decode_image` cv2.imdecode -> RAM full-res numpy (~36MB / image)
2. pipeline `load_image_bgr` ayni isi tekrar yapiyor (PIL ile, sonra cv2)
3. YOLO icinde resize 640

Tek goruntu icin **2 kez decode** + tam cozumlu numpy bellekte.

**Tahmini etki:** ~10-30ms / image preprocess kazanc; bellek 36MB -> 4MB
(640x640).

**Fix yonu:** Backend tarafinda decode'u atla (bytes pipeline'a ver) **veya**
pipeline tarafinda ndarray geldiginde PIL'i atlamak icin `_pil_to_bgr`'i
bypass et. Mobile zaten 1600px'e compress ediyor (UploadScreen.tsx:25-39),
bu yuzden web/desktop tarafinda da client-side resize **once** yapilirsa
upload bandwidth + memory'de 5-10x tasarruf.

### 2.3 [DUSUK] `cost_engine.estimate` for-loop — N hasar icin N call

**Konum:** `pipeline.py:491-500`. Cost YAML lookup, hizli (microsec). Marjinal.

### 2.4 [ORTA] Visualization PNG encode — opsiyonel ama default kapali

`generate_visuals=False` default; backend zaten cagirmıyor. Ama `output_formatter`
icindeki polygon serialize Buyuk JSON uretebilir (mask'lar polygon-only,
asagida bayrak).

---

## 3) Web — `apps/web`

### 3.1 [YUKSEK] Tum sayfalar Client Component — Next.js 15 RSC fayda yok

**Konum:** `app/inspect/page.tsx:1`, `app/history/page.tsx:1` (`'use client'`)

Her ikisi de top-level `'use client'`. History sayfasinin **listeyi server'da
fetch edip statik HTML olarak gondermesi** mumkun (en azindan ilk render).
Suanki kurguda:
- Sayfa JS olarak indirilir
- Client mount olur
- useEffect tetiklenir
- Fetch baslar -> spinner
- Sonuc gelir

Server Component yapilirsa: HTML zaten data ile gelir, hydration sadece
filter/pagination icin gerekir. **LCP 200-600ms iyilesir** (kullanicinin
internetine gore).

### 3.2 [DUSUK] Bundle — buyuk dep yok, lucide tree-shake aktif

`package.json` ozellikle hafif: axios, lucide-react (`optimizePackageImports`),
react-dropzone, zod, react-hook-form. **Lodash YOK** (iyi). `next.config.ts`
zaten `optimizePackageImports: ['lucide-react', '@arac-hasar/ui']`.

**Olcum:** Production build sonrasi bundle analyzer eklemek faydali olur ama
mevcut konfigde alarm yok.

### 3.3 [DUSUK] `next/image` kullanilmiyor, raw `<img>` ile lazy

`history/page.tsx:240-245`:
```tsx
<img src={it.thumbnail_url} alt="" loading="lazy" ... />
```
`next/image` olsa otomatik webp/avif + responsive srcset. Thumbnail'lar S3'ten
geldigi icin `next/image` `remotePatterns` ile zaten konfigure edilmis
(`next.config.ts:10-17`). Switch -> **~30-50% bandwidth tasarruf** thumbnail'larda.

### 3.4 [ORTA] Polling 2s interval — WS varken hala polling

**Konum:** `lib/use-inspection-polling.ts:32`

Backend WS `/api/v1/inspect/{id}/stream` var ama web'de kullanilmiyor. Sayfa
acik kalirken her 2s'de `GET /api/v1/inspect/{id}`. 60s maxDuration -> 30 ekstra
istek. WS'e gecirilse: 1 connection, anlik push.

**Tahmini etki:** Sunucu yuku 30x azalir _processing donemi icin_. Kullanici
UX'i ayni veya daha hizli (status anlik). Backend 1.6 fix'i olmazsa
psycopg2 connection hammer azalir.

---

## 4) Mobile — `apps/mobile`

### 4.1 [TAMAM] Image compression upload oncesi yapiliyor

**Konum:** `screens/UploadScreen.tsx:25-39, 89`

```typescript
const MAX_WIDTH = 1600;
const COMPRESS_QUALITY = 0.85;
const compressed = await Promise.all(photos.map((u) => compress(u)));
```

Iyi. 1600px + JPEG 0.85 -> tipik 400-800KB / foto. 8 foto'da ~5MB. **Bayrak: OK**.

NOT: `ImageManipulator.manipulateAsync` her foto icin ayri promise; `Promise.all`
paralel ama mobile cihazda native module thread havuzu kucuk, gercek paralellik
2-4 esis arasi. Cok foto icin chunklamak (4'er) daha guvenli olabilir.
(Marjinal)

### 4.2 [TAMAM] FlatList kullanilmis — ScrollView yok

`HistoryScreen.tsx:99` ve `CameraScreen.tsx:161` `FlatList` ile virtualize.
`UploadScreen.tsx:111` da `FlatList` (horizontal photo strip). **OK**.

### 4.3 [ORTA] CameraScreen `quality: 0.85, skipProcessing: false`

`CameraScreen.tsx:59-62`

`skipProcessing: false` -> Expo orientation/EXIF normalize ediyor (iyi). Ama
`quality:0.85` + sonra ImageManipulator ile bir kez daha resize+compress = **iki
re-encode**. Camera tarafinda direkt resize alternatif yok (Expo limit), ama
quality 1.0 tut + manipulator ile tek encode yapmak biraz daha hizli olur.
(Marjinal, ~50-100ms/foto)

### 4.4 [DUSUK] On-device QC (TFLite) henuz stub

`onDeviceQC.ts:11` "TFLite entegrasyonu icin react-native-fast-tflite kurmak gerek".
TFLite eklenirse upload oncesi reject ile sunucu yuku **40-60% azalabilir**
(kullanici %30-40 hatali fotograf cekiyor varsayim). Bu performance degil ama
cost/throughput acisindan kritik.

---

## 5) Hedef metrikler & gercekci tahmin

README hedefi: **<8s end-to-end / 4 foto**, damage 45ms, parts 30ms, severity 12ms/img.

Mevcut (statik tahmin, GPU + warmup yapilmis varsayim):
- Per image model: damage(45) + parts(30) + match(10) + severity(N*12) + cost(2) ~= **100-150ms**
- 4 foto seri (GPU lock): 4 * 125 = **500ms** ML toplam
- Upload + S3 (4 foto * 1MB): 4 * 100-300ms = **400-1200ms** (HTTP + S3 put)
- Backend orchestration + decode (4x): ~**200-400ms**
- DB write/read: 50-200ms

Theoretical optimum tum bottleneck'ler kapatildiginda: ~**2-3s end-to-end**.
Mevcut darbogazlarla (1.5, 1.6, 1.7 acik) gercek tahminim: **8-15s** (Render free
tier'da daha kotu, OOM riski ile birlikte).

GPU yoksa (CPU) per-image **5-10x daha yavas**, hedef tutmaz; CPU ortamda
batch + parallel kritik.

---

## 6) Tahmini Kazanim Toplami (oncelik sirasiyla)

| # | Bulgu | Kazanim (per request) | Risk/Effort |
|---|---|---|---|
| 1.5 | Streaming upload | RAM 200MB -> 20MB | Orta effort, kod degisikligi |
| 1.6 | DB pool kullan (ORM'e tasi) | History 150ms -> 30ms, WS polling DB hammer cozumu | Yuksek effort (ORM migrasyonu) |
| 1.1 | Sync route `to_thread` | Event-loop bloklamayi cozer, throughput 1.5-2x | Dusuk effort, 1 satir |
| 1.3 | Damage/Parts paralel + Severity batch | Per image 30-70ms, 4-foto 200ms+ | Orta effort, refactor |
| 1.2 | Sync mode upload+ML pipelining | 5-foto 7.5s -> 5s | Orta effort |
| 1.4 | Severity warmup eksigi | Cold-start -300-1000ms | Dusuk effort |
| 3.1 | Web History RSC | LCP -200-600ms | Orta effort |
| 3.3 | next/image | Thumbnail bandwidth -30-50% | Dusuk effort |
| 3.4 | WS yerine polling | Server load -30x processing window | Orta effort |
| 2.2 | Çift decode'u kaldir | Per image -10-30ms, RAM -32MB | Orta effort |

---

*Bu notlar bir kez okuma ile uretildi; gercek profilleme (py-spy, scalene,
Chrome DevTools, lighthouse, RUM) tum tahminleri 2-3x degistirebilir. Once
1.6 ve 1.5 fix'leri ile gerçek darbogazi olcun.*
