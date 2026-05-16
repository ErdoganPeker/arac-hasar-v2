# TRACKING_POLLING — Frontend Hata Izleme + Backend Log Korelasyonu

**Scope:** Tasarim dokumani. Bu dalgada KOD DEGISTIRILMEDI / SDK KURULMADI. Bu dosya, polling
ve multi-foto upload akislarinda kullanici-yonlu hata gozlemlenebilirligini
acmak icin **onerilen** sema, kod ornekleri ve event taxonomisidir.

**Sorun ifadesi.** Polling timeout / 5xx / network-blip senaryolarinda kullanici
"bir seyler bozuk" yazisi gorur, fakat:
- Frontend, backend log satirina baglanmaz (request_id frontend tarafinda yok)
- Hangi `inspection_id`'nin kac kez denendigi, hangi sebeple dustugu
  client-side'da hicbir yerde toplanmaz (Sentry yok, GA4 yok)
- Backend `access_log` zaten `request_id`, `user_id`, `duration_ms` yayinliyor
  (`services/backend/middleware.py` `AccessLogMiddleware`), ama frontend `console.error`
  cikinca o request_id'yi ekrana ya da clipboard'a basmiyor — destek
  surecinde "ekran goruntusu yollayin" yerine "su id'yi yollayin" demek
  imkansiz.

Bu doc ucunu birden kapatmak icin yapilmasi gerekenleri tarif eder.

---

## 0. Mevcut Durumun Hizli Envanteri

| Tas | Durum |
|---|---|
| Backend `X-Request-ID` middleware | **VAR** — `services/backend/middleware.py:121` `RequestIDMiddleware`, inbound header'i kabul ediyor; yoksa `uuid4().hex` mintliyor. |
| CORS `expose_headers` `X-Request-ID` icerigi | **VAR** — `middleware.py:271` `expose_headers=["X-Request-ID", ...]`, dolayisiyla browser JS tarafindan `response.headers.get("x-request-id")` okunabilir. |
| Backend `access_log` JSON satiri | **VAR** — `event=http.access` icinde `request_id`, `user_id`, `status`, `duration_ms`, `path`. |
| Frontend axios response interceptor request_id okuma | **YOK** — `apps/web/lib/api.ts:91` interceptor sadece 401 refresh akisini handle ediyor, header okunmuyor. |
| Frontend polling instrumentation | **YOK** — `apps/web/lib/use-inspection-polling.ts` `attempts` sayiyor ama disari yayinlamiyor. |
| Multi-foto upload instrumentation | **YOK** — `inspections.create` `onUploadProgress` callback'i sadece UI progress bar icin kullaniliyor. |
| GA4 / Sentry / Posthog SDK | **YOK** (KVKK consent banner'i da yok). |
| `inspection_unassigned_ratio` backend cikti | **VAR** — `services/backend/output_formatter.py:411` `summary.unassigned_damage_count` ve genel `damages` count'u uzerinden orana cevirilebilir. Frontend henuz okumuyor. |

---

## 1. X-Request-ID Propagation (KOD ORNEGI — uygulanmadi, oneri)

### 1.1 Frontend: axios response interceptor

`apps/web/lib/api.ts` icindeki `buildClient()` icinde response interceptor'a
**asagidaki** ek konabilir. Yalnizca okuma + log. Side-effect yok.

```ts
// apps/web/lib/api.ts — buildClient() icinde,
// response interceptor'in BASARILI dalinda (su anki `(r) => r` yerine):

instance.interceptors.response.use(
  (r) => {
    const rid = r.headers?.['x-request-id'];
    if (rid) {
      // Successful response: log only at debug verbosity so the console
      // is not polluted in production builds. The tag prefix lets support
      // engineers grep the user-shared screenshots.
      if (process.env.NODE_ENV !== 'production') {
        console.debug(`[api] ${r.config.method?.toUpperCase()} ${r.config.url} rid=${rid}`);
      }
      // Stash on the response so call sites (polling, upload) can grab it
      // for event payloads.
      (r as { requestId?: string }).requestId = rid;
    }
    return r;
  },
  async (error: AxiosError) => {
    // Mevcut 401 / refresh akisi degismez. Ek olarak:
    const rid =
      (error.response?.headers as Record<string, string> | undefined)?.['x-request-id'];
    if (rid) {
      // Hata durumu HER ZAMAN logla — destek bilet eslesmesi icin kritik.
      console.error(
        `[api] FAIL ${error.config?.method?.toUpperCase()} ${error.config?.url} ` +
        `status=${error.response?.status ?? 'network'} rid=${rid}`,
      );
      // ApiErrorInfo'ya da dahil et ki UI clipboard'a kopyalayabilsin.
      (error as { requestId?: string }).requestId = rid;
    }
    // ... mevcut refresh / unauthorized logigi aynen kalir.
  },
);
```

### 1.2 `classifyApiError` cikisina `requestId` ekleme

`ApiErrorInfo` arayuzu su an `kind | status | detail | fieldErrors` iceriyor
(`apps/web/lib/api.ts:513`). Asagidaki tek satir genisleme yeterli:

```ts
export interface ApiErrorInfo {
  // ... mevcut alanlar
  /** Backend X-Request-ID, support diagnostics icin. */
  requestId?: string;
}

// classifyApiError govdesi sonunda:
const rid = (err as { requestId?: string })?.requestId
  ?? (axios.isAxiosError(err)
        ? (err.response?.headers as Record<string,string> | undefined)?.['x-request-id']
        : undefined);
return { ...base, requestId: rid };
```

### 1.3 UI'da gosterim ornegi (destek mesajina kopyalama)

Polling failure ya da upload failure error card'i:

```tsx
{info.requestId && (
  <p className="text-xs text-zinc-500 mt-2">
    Destek referansi: <code>{info.requestId}</code>
    <button onClick={() => navigator.clipboard.writeText(info.requestId!)}>
      kopyala
    </button>
  </p>
)}
```

Bu, **Sentry kurulduktan sonra** `Sentry.captureException(err, { tags: { request_id } })`
ile dogrudan backend access log'una linklenecek. Sentry yokken bile kullanici
"rid=ab12cd34..." dedi mi backend `journalctl | grep ab12cd34` ile o exact
istegi 1 saniyede bulur.

---

## 2. Event Semasi

### 2.1 Genel kurallar

- `event_name`: `snake_case`, fiil bitis (`_started`, `_completed`, `_failed`).
- `properties`: dust JSON-serializable (string / number / bool / null).
- **PII yasak**: e-mail, JWT, dosya icerigi, plaka. `inspection_id` UUID
  oldugu icin guvenli; `user_id` GA4 user-id slot'una gider, properties'e degil.
- Zaman damgalari: `*_ms` (number, epoch yerine duration tercih).
- Hata sebebi `reason` enum'u: `timeout | network | unauthorized | forbidden | not_found | server | rate_limited | aborted | unknown`.
  (`classifyApiError.kind` ile birebir eslesmeli — onceki rule mevcut.)

### 2.2 Polling event'leri (`use-inspection-polling.ts` icinde emit edilecek)

| event_name | trigger | properties |
|---|---|---|
| `polling_started` | `tick` ilk kez planlandiginda | `inspection_id` (str), `mode` (`async`\|`sync`), `interval_ms` (number), `max_duration_ms` (number) |
| `polling_attempt` | her `tick` cagrisinin BASLAMASINDA | `inspection_id`, `attempt_n` (1..N), `elapsed_ms`, `current_interval_ms` |
| `polling_failed` | `tick` icinde fatal/exhausted/timedOut/paused setlendiginde | `inspection_id`, `reason` (`timeout`\|`network`\|`unauthorized`\|`forbidden`\|`not_found`\|`server`\|`rate_limited`\|`exhausted`\|`paused`), `attempt_n`, `consecutive_errors`, `elapsed_ms`, `request_id` (varsa) |
| `polling_completed` | `status === 'completed'` doner | `inspection_id`, `attempt_n`, `duration_ms` (elapsed since polling_started), `final_status` (`completed`\|`failed`), `request_id` |
| `polling_retried` | kullanici `retry()` cagirir | `inspection_id`, `previous_attempts`, `was_timed_out` (bool), `was_paused` (bool) |

### 2.3 Multi-foto upload event'leri (`inspections.create` cagrisinin etrafinda)

| event_name | trigger | properties |
|---|---|---|
| `upload_started` | `inspections.create()` cagrildiginda | `file_count` (number), `total_size_mb` (number, 2 ondalik), `mode` (`sync`\|`async`) |
| `upload_progress` | `onUploadProgress` cagrildiginda — **kisilmis** (10/25/50/75/90/100 esikleri, throttle) | `percent` (0..100), `loaded_mb`, `total_mb` |
| `upload_completed` | `inspections.create()` 2xx donerse | `file_count`, `total_size_mb`, `mode`, `duration_ms`, `inspection_id`, `request_id` |
| `upload_failed` | `inspections.create()` reject ederse | `file_count`, `total_size_mb`, `mode`, `reason` (`classifyApiError.kind`), `partial_count` (multi-foto'da basarisiz olan dosya sayisi; tek POST oldugu icin su an her zaman `file_count` veya `0` — gelecekte chunked upload'a hazirlik), `duration_ms`, `request_id` |

### 2.4 Detection quality event'i

| event_name | trigger | properties |
|---|---|---|
| `inspection_quality_observed` | `polling_completed` 'in hemen ardindan, response gelinince | `inspection_id`, `total_damage_count` (number), `unassigned_damage_count` (number — backend zaten `summary.unassigned_damage_count` doruyor: `services/backend/output_formatter.py:411`), `unassigned_ratio` (float, 0..1), `total_part_count`, `processing_time_ms` (backend'den), `image_count` |

`unassigned_ratio = unassigned_damage_count / total_damage_count`. Ornek brief'te
verilen 10/16 = 0.62 anomalisi bu metrigin GA4'e dustugunde dashboard'da
threshold alarm setlemeyi mumkun kilar (model kalibrasyonu icin sinyal).

### 2.5 Hata baglamlarinda standart envelope

Tum `*_failed` event'leri **mutlaka** su alt seti tasimali (sirf bu tanimi
genisletmek "bu hata neden oldu" sorusuna 30 saniyede cevap olur):

```jsonc
{
  "event_name": "polling_failed",
  "properties": {
    "inspection_id": "5f6e...",
    "reason": "server",
    "http_status": 502,
    "request_id": "ab12cd34ef56...",   // backend access_log ile JOIN anahtari
    "attempt_n": 4,
    "elapsed_ms": 9421,
    "consecutive_errors": 3,
    "user_agent_brand": "Chrome",       // navigator.userAgentData.brands[0]
    "connection_type": "4g",            // navigator.connection?.effectiveType
    "session_id": "...",                // GA4 / posthog auto
    "build_sha": "abc1234"              // NEXT_PUBLIC_BUILD_SHA, varsa
  }
}
```

### 2.6 KVKK consent gate'i

Hicbir analytics event'i, kullanici `cookie_consent.analytics === true`
isaretlemedikce **gonderilmemelidir**. Onerilen mimari:

1. `apps/web/lib/analytics.ts` (henuz yok) — `track(event, props)` fonksiyonu
   `localStorage['cookie_consent']` JSON'unu okur; `analytics: true` degilse
   buffer'a yazar (max 200 event), consent verildiginde flush eder, **asla**
   network'e basmaz.
2. Banner kabulune kadar GA4 / Posthog SDK init **edilmez** (sadece stub).
3. Backend `request_id` console'a yazilmaya devam eder — bu PII degil, opex.

Bu dalgada SDK ya da banner kurulmadi; bu sema banner geldigi gun gun
calismaya hazir.

---

## 3. Top 5 Must-Have Event

Once-yapilacaklar siralamasi (etki / efor orani yuksek olandan dusuge):

| # | Event | Niye 1. siniftan |
|---|---|---|
| 1 | `polling_failed` | Tum kullanici sikayetinin **kaynagi**. `reason` + `request_id` ile destek biletlerinin %80'i tek satir log lookup'a duser. SDK gelmeden once **console.error**'a basmasi bile fayda saglar. |
| 2 | `upload_failed` | Multi-foto upload'da kullanici **hangi adimda** dustugunu bilmiyor (network mi, 413 mu, 422 mi). `reason=tooLarge` ile `reason=network` ayrimi UI mesajinin tonunu degistirir. |
| 3 | `inspection_quality_observed` | `unassigned_ratio` model kalibrasyonu icin **business** metrigi. Brief'teki 10/16 = 0.62 ornegi tam olarak burayi gosteriyor; bu olcum olmadan "model nezaman bozuldu" sorusu cevapsiz. |
| 4 | `polling_completed` | Basari yolu olcumu — p50/p95 `duration_ms` SLO panosunun ana metrigi. Hata orani sadece basari hizina karsi anlam kazanir. |
| 5 | `upload_started` | Funnel'in tepe noktasi. `started` olmadan `failed` rate yorumlanamaz (denominator). `file_count` distribution UI tasariminda (1-foto vs 20-foto akislari) gerceklerle dogrulanir. |

---

## 4. Backend ile Korelasyon Akisi (operatif kosesi)

Frontend `polling_failed` event'i emit ettiginde `request_id=ab12cd34` ile.
Backend tarafinda:

```bash
# /var/log/.../backend.access.log ya da journald
grep '"request_id":"ab12cd34"' backend.access.log | jq .
```

donus:

```jsonc
{
  "event": "http.access",
  "method": "GET",
  "path": "/api/v1/inspect/5f6e...",
  "status": 502,
  "duration_ms": 12.4,
  "user_id": "user-uuid",
  "ip": "...",
  "request_id": "ab12cd34..."
}
```

Bu JOIN su an mumkun **degil** cunku frontend `request_id`'yi okumuyor.
Section 1.1 patch'i uygulanir uygulanmaz, **kod degisikligi olmadan** bile
destek susrecindeki MTTR (mean-time-to-resolve) dakikalardan saniyelere iner.

---

## 5. Bu dalgada YAPILMADI (hatirlatma)

- `apps/web/lib/api.ts` interceptor patch'i **kodlanmadi** (sadece ornek).
- `apps/web/lib/use-inspection-polling.ts` `track(...)` cagrilari **eklenmedi**.
- `apps/web/lib/analytics.ts` consent-gated wrapper **olusturulmadi**.
- GA4 / Posthog / Sentry SDK kurulumu **yapilmadi**.
- KVKK cookie consent banner UI **eklenmedi**.

Bu dosya, sonraki dalgalarin `git grep TRACKING_POLLING.md` ile
implementasyon spec'ini tek noktada bulmasi icindir.
