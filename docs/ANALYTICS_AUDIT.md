# Analytics & Observability Audit — apps/web

Tarih: 2026-05-16
Kapsam: Sadece web app (`apps/web/`). READ-ONLY audit, kod degisikligi yapilmadi.
Hedef: Hangi event'lar takip ediliyor, hangileri eksik — vendor-neutral oneriler.

---

## 1. Mevcut Durum — Ne Var Ne Yok

### 1.1 Frontend analytics / product analytics

| Katman | Durum | Kanit |
|---|---|---|
| GA4 (gtag.js) | YOK | `apps/web/package.json` icinde `gtag`, `@next/third-parties` yok; `app/layout.tsx` icinde `<Script>` veya `gtag` cagrisi yok. |
| Plausible | YOK | Dependency yok, layout'ta script tag'i yok. |
| PostHog | YOK | `posthog-js` / `posthog-node` dependency yok. |
| Mixpanel / Amplitude / Segment | YOK | Hicbir SDK referansi yok. |
| Google Tag Manager | YOK | GTM container snippet yok (`<noscript>` iframe, `dataLayer` push yok). |
| `dataLayer` array | YOK | Hicbir yerde init edilmiyor; event push edilmiyor. |

Sonuc: **Sifirdan baslayan temiz bir sayfa.** Hicbir kullanici davranis verisi toplanmiyor.

### 1.2 Frontend error tracking / observability

| Katman | Durum | Kanit |
|---|---|---|
| Sentry (web) | YOK | `@sentry/nextjs` veya `@sentry/react` dependency yok; `sentry.client.config.ts` yok. |
| Datadog RUM | YOK | `@datadog/browser-rum` yok. |
| LogRocket / FullStory | YOK | Dependency yok. |
| Web Vitals reporting | YOK | `reportWebVitals` veya `next/web-vitals` exporter kullanilmiyor. |
| Browser console error capture | YOK | Global `window.onerror` / `unhandledrejection` handler yok. |

`docs/OBSERVABILITY_SETUP.md` dosyasi backend + React Native icin Sentry plani onermis, ancak **web app icin Sentry plani belirtilmemis**. Backend Prometheus + Grafana plani var; bunlar SRE tarafi, urun analytics'i degil.

### 1.3 X-Request-ID propagation (backend <-> frontend)

Backend tarafi **dogru kurulmus**:
- `services/backend/middleware.py:99` — `RequestIDMiddleware` header'i kabul ediyor; yoksa UUID minting yapiyor.
- `services/backend/middleware.py:123` — `request.state.request_id` set ediliyor.
- `services/backend/middleware.py:178` — Yapisal access log `request_id` field'i ile yaziliyor.
- `services/backend/middleware.py:265-266` — CORS `allow_headers: ["X-Request-ID"]` ve `expose_headers: ["X-Request-ID"]` her ikisi de var. **Tarayicidan gonderim ve okuma teknik olarak mumkun.**
- `services/backend/main.py:374, 403` — Hata response'larinda `request_id` log'a yaziliyor.

Frontend tarafi **eksik**:
- `apps/web/lib/api.ts` icindeki axios request interceptor (line 75-81) **`X-Request-ID` set etmiyor.**
- Response interceptor (line 83-103) **`X-Request-ID` okumuyor, log'a yazmiyor, hata mesaji ile birlikte yuzeye cikartmiyor.**
- `classifyApiError()` (line 443+) `request_id`'yi `ApiErrorInfo` icine almiyor; kullaniciya hata gosterildiginde request_id gozukmuyor.

**Sonuc:** Kullanici "X" hatasini gordugunde, support'a yazip "Y zamani Z yaptim" disinda bilgi veremiyor. Backend log'larini grep'lemek icin kullanici ID'si + timestamp ile yaklasik eslesme yapmak gerekiyor — kirilgan. Bu **P0 bos**.

### 1.4 Cookie consent / KVKK uyum

| Katman | Durum |
|---|---|
| Cookie consent banner | YOK |
| Consent Mode v2 | YOK (zaten Google tag yok) |
| `NEXT_LOCALE` cookie | VAR (`middleware.ts`), strictly functional, KVKK kapsaminda "essential" — banner gerekmez. |
| Auth cookie (`access_token`) | VAR, essential. |

Su an tracking olmadigi icin **KVKK acidan temiz** — ancak analytics ekleyince banner zorunlu olur. Hazirlikli olunmali.

---

## 2. Page View Tracking — Next.js 15 App Router Tuzaklari

### 2.1 Otomatik mi manuel mi?

Next.js 15 App Router'da **otomatik page view yok.** Pages Router'da `router.events` vardi; App Router'da bu API yok. Manuel olarak yapilir:
- `usePathname()` + `useSearchParams()` degistiginde event push edilir.
- Genellikle bir `<AnalyticsListener />` client component'i `app/layout.tsx`'e mount edilir.

### 2.2 Locale prefix problemi — bu projede YOK ama

Bu proje `next-intl`'i **path prefix'siz** mod ile kullaniyor:
- `apps/web/i18n.ts` — locale `NEXT_LOCALE` cookie veya `Accept-Language` header'dan cozulur, URL'de **/tr/ veya /en/ prefix YOK**.
- Yani `/inspect` URL'i hem TR hem EN icin ayni; locale ayri bir dimension olarak event'a eklenmeli (custom property: `locale: 'tr' | 'en'`).

**Avantaj:** Cift sayim problemi yok.
**Dezavantaj:** Locale bilgisi event'a manuel eklenmedikce funnel analizinde gorulemez. Oneri: tum event'lara `locale` property'si push edilsin.

### 2.3 SPA navigation problemi

`router.push('/results/${id}')` ile gecisler full page reload yapmaz. Otomatik gtag/posthog config'i bunu yakalamayabilir. **Manuel `page_view` event'i pathname degisiminde firlatilmali.**

---

## 3. Funnel & Kritik Event'lar

### 3.1 Soft funnel adimlari (URL bazli)

```
/  (Anasayfa)
  -> /inspect          (Foto secimi / upload form)
    -> /results/[id]   (Sonuc bekleme + render)
      -> /inspect      (Tekrar — "yeni inceleme" CTA)
```

Auth funnel:
```
/  -> /login | /register  -> /dashboard  -> /inspect  -> /results
```

### 3.2 Eksik event listesi — P0 / P1 / P2

#### P0 (lansman oncesi mutlaka)

| Event | Trigger | Properties | Neden P0 |
|---|---|---|---|
| `page_view` | Pathname degisimi | `path`, `locale`, `referrer`, `is_authenticated` | Funnel temeli; bunsuz hicbir analiz yapilamaz. |
| `inspection_started` | `apps/web/app/inspect/page.tsx` — `handleSubmit()` icinde, `createInspection()` cagrilmadan once | `file_count`, `mode` (`sync`/`async`), `total_bytes`, `locale` | Funnel'in kalbi; conversion'in basladigini soyleyen tek sinyal. |
| `inspection_completed` | `apps/web/lib/use-inspection-polling.ts` — polling `status === 'completed'` doner donmez | `inspection_id`, `duration_ms` (started_at'a gore), `damage_count`, `parts_affected`, `cost_estimated_total_tl` (numeric), `locale` | Asil business event; `cost_estimated_total_tl` ARR proxy'si. |
| `inspection_failed` | Polling `status === 'failed'` veya `handleSubmit` catch | `error_kind` (`classifyApiError` cikti), `status_code`, `request_id`, `phase` (`upload`/`processing`) | Drop-off teshisi. |
| `auth_register` | `auth-context.tsx` — `register()` success | `method: 'email'`, `locale` | Acquisition. |
| `auth_login` | `auth-context.tsx` — `login()` success | `method: 'email'`, `locale` | Retention. |
| `auth_logout` | `auth-context.tsx` — `logout()` cagrisinda | (none) | Session uzunlugu. |
| `api_error` | axios response interceptor (reject path) | `endpoint`, `status`, `error_kind`, `request_id` | Frontend hata oranlarini Sentry disinda da olcmek icin. |

#### P1 (lansman + ilk hafta)

| Event | Trigger | Properties |
|---|---|---|
| `language_changed` | `LanguageSwitcher.tsx` — `setLocale()` icinde | `from`, `to` |
| `upload_dropzone_files_added` | `apps/web/app/inspect/page.tsx` `onFiles()` | `file_count_added`, `total_size_bytes`, `mime_types[]` |
| `upload_dropzone_file_removed` | `removeFile()` cagrisi | `remaining_count` |
| `upload_mode_changed` | `ModeOption` tikla | `from`, `to` |
| `results_tab_switched` | `ResultsTabs.tsx` tab tikla | `tab`, `inspection_id` |
| `damage_highlighted` | `PartList` veya badge tikla | `part_id`, `damage_id` |
| `inspection_history_viewed` | `/history` mount | `page`, `page_size`, `result_count` |
| `inspection_deleted` | `inspections.delete()` success | `inspection_id` |

#### P2 (optimizasyon fazinda)

| Event | Trigger | Properties |
|---|---|---|
| `web_vital_lcp` / `_cls` / `_inp` | `reportWebVitals` | `value`, `path` |
| `cta_clicked` | Anasayfa hero/CTA butonlari | `cta_name`, `position` |
| `error_boundary_caught` | React error boundary | `component`, `error_message` |
| `inspection_polling_timeout` | `use-inspection-polling.ts` — `timedOut` true | `inspection_id`, `attempts` |
| `api_key_created` / `revoked` | `apiKeys.create/revoke` | `key_id` |

### 3.3 Drop-off noktalari (event'lar dogru kurulursa)

Su `funnel` PostHog/GA4'te kurulabilir:
1. `page_view path=/inspect` ->
2. `upload_dropzone_files_added` ->
3. `inspection_started` ->
4. `inspection_completed`

Her adim arasi drop-off oraninin (%) ayri kovalarda izlenmesi gerekir. Ozellikle **2 -> 3** arasi (dosya secilmis ama submit edilmemis) yuksek olursa form UX problemi var demektir.

---

## 4. A/B Test Altyapisi

| Vendor | Durum | Tavsiye |
|---|---|---|
| GrowthBook | YOK | Self-hosted, KVKK uyumu kolay — gerektiginde tercih. |
| LaunchDarkly | YOK | Pahali, MVP icin overkill. |
| Vercel Edge Config / Feature Flags | YOK | Eger Vercel'e deploy edilirse en dusuk surtunmeli secim. |
| PostHog Feature Flags | YOK | PostHog secilirse dahili, ekstra entegrasyona gerek yok. |

**Su an oneri: KURMA.** A/B testi sadece istatistiksel anlamli trafikte (haftalik 1K+ kullanici/varyant) ise yarar. MVP'de copy ve buton degisiklikleri elle yapilir; analytics event'lar zaten yeterli ipucu verir. **Trafik 10K MAU'ya ulastiginda yeniden degerlendirilir.**

---

## 5. Vendor-Neutral SDK Onerileri (KURMA, sadece karsilastir)

Asagidaki tablo karar verme aracidir; secimi proje sahibi yapacak.

| Ihtiyac | Aday A | Aday B | KVKK |
|---|---|---|---|
| Product analytics (event + funnel) | **PostHog Cloud EU** (Frankfurt) | Self-host PostHog (Docker, 2-3 GB RAM) | EU region zorunlu; A daha hizli kurulur, B daha temiz veri ikametgahi. |
| Tag manager | **GTM (web)** — tek script, sonradan tag eklenir | dogrudan SDK init (manager yok) | GTM consent mode v2 destegi var; banner ile entegre olabilir. |
| Frontend error tracking | **Sentry SaaS EU (Frankfurt)** | GlitchTip self-hosted (Sentry-compatible OSS) | A hizli; B veri ikamet kontrolu. |
| Cookie banner | **CookieYes / Cookiebot** | Custom UI (3-4 saatlik is) | TR icinde tutarsa custom daha gungormus; KVKK + GDPR ortak ise SaaS. |
| Web vitals | **Next.js `reportWebVitals` -> PostHog/Sentry** | Vercel Analytics | Native, ekstra SDK gerekmez. |

**Onerilen minimum stack (KVKK uyumlu):**
1. **GTM container** layout'a tek script olarak gomulur (consent gated).
2. **PostHog (EU)** GTM uzerinden cookie consent sonrasi yuklenir; tum kritik event'lar `posthog.capture()` ile.
3. **Sentry browser SDK** layout'a `Sentry.init()` ile gomulur — error tracking consent gerektirmez (legitimate interest, PII redact'li), DSN'i .env'den.
4. **Custom cookie banner** (necessary / analytics / marketing 3 kategori) — Turkce/Ingilizce, mevcut next-intl messages dosyalarina eklenir.

**Tek vendor cozumu istenirse:** PostHog (analytics + error tracking + session replay + feature flags hepsi tek paket). Tradeoff: session replay'in performans maliyeti ve KVKK acisindan ek ozen.

---

## 6. Backend <-> Frontend Log Korelasyonu — Eylem Plani

Backend hazir, frontend eksik. Onerilen (kod ekleme degil, plan):

1. **`apps/web/lib/api.ts` request interceptor**'da her cagri oncesi `crypto.randomUUID()` ile bir `X-Request-ID` uretilip header'a eklenir. Backend zaten kabul ediyor (`middleware.py:122`).
2. **Response interceptor**'da `response.headers['x-request-id']` okunup `response.config` veya context'e yazilir.
3. **Reject path'inde** `error.response.headers['x-request-id']` `ApiErrorInfo.requestId` field'ina eklenir.
4. **`classifyApiError`** doneren tip'e `requestId?: string` eklenir.
5. **Hata UI'larinda** (ornegin `apps/web/app/results/[id]/page.tsx`'deki `ErrorBanner`, `inspect/page.tsx`'deki alert) request_id kucuk monospace yazi olarak gosterilir: `Hata kodu: a1b2c3d4` — support'a iletilebilir.
6. **`api_error` event'inde** `request_id` property olarak gonderilir; bu sayede analytics dashboard'da hata bir tikla backend log'unda aranabilir.

### Korelasyon zinciri (hedef)

```
Kullanici hata gorur (UI'da request_id: a1b2c3d4)
   |
   v
api_error event PostHog/Sentry'ye gider (request_id: a1b2c3d4)
   |
   v
SRE PostHog'da event'i bulur, request_id kopyalar
   |
   v
Backend log aggregator'da (Loki/CloudWatch) request_id="a1b2c3d4" ile filtre
   |
   v
Tam request trace + stack trace
```

Bu zincir kurulmadan, **production'da gelen "calismadi" sikayetlerinin %70'i teshis edilemeyecek.**

---

## 7. Ozet Karar Listesi (P0 / P1 / P2)

### P0 — Lansman blocker (kurulmadan canli alinmamali)
- [ ] Cookie consent banner (3 kategori: necessary / analytics / marketing) + KVKK/GDPR metni.
- [ ] GTM container layout'a gomulu (henuz tag yok, infra hazir).
- [ ] PostHog (veya secilen analytics) consent-gated yuklenir.
- [ ] Frontend `X-Request-ID` set + read + UI'da goster.
- [ ] Event'lar: `page_view`, `inspection_started`, `inspection_completed`, `inspection_failed`, `auth_register`, `auth_login`, `auth_logout`, `api_error`.
- [ ] Sentry browser SDK (PII scrubbing on).

### P1 — Lansman + ilk hafta
- [ ] `language_changed`, upload UX event'lari, results tab/highlight event'lari.
- [ ] Funnel dashboard'i (anasayfa -> inspect -> results) PostHog/GA4'te kurulu.
- [ ] Crash-free user rate alert (Sentry).

### P2 — Optimizasyon fazinda
- [ ] Web vitals (LCP/CLS/INP) raporlama.
- [ ] Feature flag altyapisi (10K MAU sonrasi).
- [ ] Session replay (eger PostHog secildiyse, KVKK degerlendirmesi sonrasi).

---

## 8. Bulgu Ozeti

- **Web app'te hicbir analytics SDK yok** — temiz sayfa, blank slate.
- **Frontend error tracking yok** — production'a cikilirsa hatalar gormezden gelinir.
- **Backend X-Request-ID propagation hazir, frontend kullanmiyor** — en hizli ROI'li tek dokunus burada.
- **Path-prefixless i18n** sayesinde locale cift sayim problemi yok; ama locale event property olarak gonderilmeli.
- **App Router otomatik page_view yok** — manuel kurulum gerekir.
- **A/B test altyapisi gerek yok** (henuz).
- **KVKK su an temiz, ama analytics girince banner zorunlu olur** — hazirlikli baslanmali.
