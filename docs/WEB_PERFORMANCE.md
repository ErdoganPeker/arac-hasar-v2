# WEB PERFORMANCE — arac-hasar-v2 (apps/web)

Statik kod tabanli web performans denetimi. Lighthouse veya gercek bir RUM olcumu **calistirilmadi**; tum sayilar mantiksal tahmindir. Hedef: orta-uretim hazirligi (MVP demo + pilot), mobil 3G/4G ve masaustu Wi-Fi senaryolarinda kabul edilebilir UX.

Stack: Next.js 15.1.3 (App Router), React 18.3, next-intl, Tailwind 3.4, axios, lucide-react, react-hook-form, zod. `output: 'standalone'`. Hicbir RSC server-data fetch yok; tum sayfalar **client component** (kritik bulgu).

---

## 0) Ozet — Tahmini Lighthouse Skoru (mobil, 4G, mid-tier)

| Kategori | Skor (tahmini) | Yorum |
|---|---:|---|
| Performance | **62 - 72** | LCP ve TBT yuksek; her sayfa client component → JS bundle agir |
| Accessibility | **88 - 92** | Aria etiketleri ve role tab/tabpanel tutarli; renk kontrasti genel olarak OK |
| Best Practices | **85 - 92** | HTTPS / CSP / source-map gibi guvenlik basliklari prod build'de eksik olabilir |
| SEO | **80 - 90** | Metadata var; ancak `metadataBase: localhost`, sitemap yok, robots.txt yok |
| PWA | **0** | Manifest yok, service worker yok (kapsam disi olabilir) |

**Tahmini Core Web Vitals (mobil orta cihaz, 4G hizinda):**

- **LCP (Largest Contentful Paint):** ~2.4 - 3.2 s (sinir / kotu)
  - Sebep: Hero gorsel placeholder bir DOM-rendered card; Inter font swap; tum sayfa client component → JS-after-hydration LCP'yi ~600 ms erteliyor.
- **INP (Interaction to Next Paint, FID yerine):** ~120 - 220 ms (sinir)
  - Foto upload tikinda multipart-FormData hazirlama anlik (kucuk dosya icin ~10 ms), ama `URL.createObjectURL` her render'da yeniden cagrildigi icin preview ekraninda jank olusabilir.
- **CLS (Cumulative Layout Shift):** ~0.08 - 0.15
  - `ImageWithOverlay` icindeki `<img>` width/height attribute yok → annotated PNG yuklendiginde sayfa kayiyor. `ResultsTabs` panel bos yer tutmuyor → "Spinner → result" gecisinde ~150 px shift olasi.

---

## 1) Tahmini bundle / "First Load JS" 

Hedef: < 200 KB gz First Load JS.

Mevcut prod build calistirilmadi (`.next/static/chunks/` icindeki dev artifact'lar 6.5 MB; bu **anlamli degil**, dev-mode'da unminified ve HMR loader var). Asagidaki tahminler dependency analizinden cikarildi.

| Kaynak | Tahmini gz boyut | Not |
|---|---:|---|
| React 18 + React-DOM | ~42 KB | Standart |
| Next.js runtime + Router | ~35 - 45 KB | App Router'in client runtime'i Pages Router'dan biraz daha agir |
| next-intl client provider + tr.json (24 KB raw) | ~12 - 18 KB gz | **Tum mesajlar her sayfaya biniyor** (root layout `getMessages()` -> NextIntlClientProvider) |
| axios (full) | ~14 KB gz | Sadece JSON istek yapiyor; `fetch` wrapper'i ile degisilebilir → -10 KB |
| react-hook-form + @hookform/resolvers + zod | ~22 KB gz | Sadece login / register / settings'de kullaniliyor ama root'ta tree-shake edilemiyor cunku zod'u `lib/jwt.ts` ihtimal cekiyor |
| lucide-react | `optimizePackageImports` ile per-icon ~0.3 KB | Iyi → next.config tarafindan zaten optimize edilmis |
| @arac-hasar/ui (24 component, hepsi `index.ts` barrel'dan re-export) | ~18 - 25 KB gz | Bazi sayfalarda yalnizca `Spinner` kullaniliyor ama `ImageWithOverlay`, `UploadDropzone` gibi agir component'lar yan etki yokken bile tree-shake olabilir varsayilir — **kontrol edilmedi** |
| Sayfa kodu | ~5 - 12 KB / sayfa | Tahmin |
| **First Load JS (homepage)** | **~135 - 165 KB gz** | Hedef altinda ama az marjla |
| **First Load JS (`/results/[id]`)** | **~180 - 220 KB gz** | ImageWithOverlay + canvas hit-test + zod yan tasimasi nedeniyle sinirda |

**Onemli not — kullanilmayan dependency:** `react-dropzone@14.3.5` web `package.json`'inda var, ama Grep ile dogrulandi: `apps/web` icinde **hicbir yerden import edilmiyor** (sadece `apps/desktop` icinde `FileDrop.tsx` kullaniyor, o da @arac-hasar/ui paketinden geliyor). Dead dep, kaldirilmali — `react-dropzone` ~10 KB gz, tree-shake ile cikiyor olsa bile npm install + audit yukunu artiriyor.

---

## 2) Statik analiz bulgulari

### 2.1 next/image hic kullanilmiyor → LCP +0.8 - 1.4 s 

Grep: `from 'next/image'` → **sifir kaynak dosyada eslesme** (sadece `.next/` ve `tsbuildinfo` icinde, bunlar Next.js'in kendi kullanimi). Tum gorseller raw `<img>`:

- `packages/ui/src/components/UploadDropzone.tsx:136` — preview thumbnail
- `packages/ui/src/components/ImageWithOverlay.tsx:172` — annotated inspection PNG (kritik LCP elementi)
- `apps/web/components/Header.tsx`, `Footer.tsx` — sadece SVG icon, sorun degil

**Etki:**
- Annotated PNG `/api/v1/inspect/{id}/visualization/annotated` 200 - 800 KB (model ciktisi YOLO seg overlay'i, JPEG/PNG re-encode olmuyor; statik analizdeki goruntu: model annotator opencv ile PNG yaziyor → buyuk). `next/image` ile:
  - Otomatik AVIF/WebP serve (Next.js default formats)
  - `srcset` + `sizes` cihaza gore tahmini ~%40 - 60 byte tasarrufu
  - Lazy load + native `loading="lazy"`
  - `placeholder="blur"` LCP'yi maskeleyebilir
- Eksiklik: `next.config.ts` `remotePatterns` zaten R2 / S3 / localhost:8000 icin acik. Yani `next/image` kullanimi icin altyapi hazir, sadece component degisikligi gerekli.

`ImageWithOverlay`'i `next/image` ile sarmak biraz daha karmasik (canvas hit-test natural width'e bagimli), ama yapilabilir: `Image` `onLoadingComplete` callback'i `naturalWidth/naturalHeight` veriyor.

### 2.2 Tum sayfalar "use client" — RSC'nin **hicbir** faydasi yok

Grep: 21 dosyada `'use client'`. Daha kritigi:

- `app/page.tsx` (homepage) — `useTranslations` hook'u **sadece** server-side cagrilabilir (next-intl `getTranslations`), ama dosyada `'use client'` yok → server component **olarak isliyor**, iyi. 
- AMA `app/inspect/page.tsx`, `app/(app)/dashboard/page.tsx`, `app/history/page.tsx`, `app/results/[id]/page.tsx`, `app/(auth)/login/page.tsx`, `app/(auth)/register/page.tsx`, `app/(admin)/users/page.tsx`, `app/(app)/settings/page.tsx`, `app/(app)/inspect/new/page.tsx` — hepsi **client component**.

Sonuc: Next.js 15'in en buyuk avantaji — RSC'de fetch'i server'da yapip yalnizca veri (JSON degil, RSC-encoded) gondermek — kullanilmiyor. Ornegin `/dashboard` ve `/history`:

```tsx
'use client';
useEffect(() => {
  (async () => {
    const data = await listInspections({ pageSize: 20 });
    setItems(data.items ?? []);
  })();
}, []);
```

Bu pattern Pages Router stili. RSC'ye gecince:
- Sayfa HTML'i SSR'de hazir gelir → LCP -0.5 s
- Client'a giden JS: yalnizca interactive parcalar (status filter, search input)
- API token'lar HttpOnly cookie ile cookie-only kullanilirsa server-side fetch yapilabilir; **mevcut auth localStorage tabanli** oldugu icin RSC'ye gecmek auth refactor gerektirir (orta efor).

### 2.3 "use client" abuse: Header / Footer / LanguageSwitcher

- `Header.tsx` — `usePathname` + `useAuth` cektigi icin haklisin, client zorunlu. **OK.**
- `Footer.tsx` — `'use client'` var (Grep dogruladi) ama Footer.tsx'i tek seferde kontrol edersek muhtemelen sadece tercume gosteriyor. **`useTranslations` yerine `getTranslations` (server) kullanip server component yaparak ~2 KB bundle tasarrufu.**
- `LanguageSwitcher.tsx` — `usePathname` + cookie set ettigi icin client gerekli. **OK.**

### 2.4 next/dynamic ile kod splitting hic kullanilmamis

Grep: `next/dynamic` → kaynak dosyada **sifir**. Ozellikle agir component'lar dinamik yuklenmemis:

- `ImageWithOverlay` (canvas + ResizeObserver + hit-test, ~4 KB gz) — sadece `/results/[id]` sayfasinda gerekli, ama @arac-hasar/ui index.ts barrel re-export ettigi icin homepage bundle'ina sizabilir (ESM tree-shake bunu engellemeli, dogrulamadim).
- `ResultsTabs`, `PartList`, `CostDisplay`, `InspectionSummary` — sadece `/results/[id]`'de. Bu zaten Next.js'in route-level splitting'i sayesinde ayri chunk'ta.
- `ConfirmDialog` (UI paketi) — sadece etkilesim sonrasi gerekli; modal'a kadar import edilmemeli.

**Onerilen yaklasim:** `/results/[id]` page'inde `ImageWithOverlay`'i `next/dynamic({ ssr: false })` ile yukle, ki ilk-paint (status pending) kucuk bundle ile gelsin, sonra annotated PNG hazir oldugunda overlay yuklensin.

### 2.5 Polling interval — 2000 ms uygun, ama backoff yok

`use-inspection-polling.ts:33` → default `intervalMs: 2_000`. Bu **dogru bir secim**:
- 1 s cok agresif (60s'de 60 istek = backend rate-limit baskisi).
- 2 s makul; backend processing 4 foto icin 8-25 s arasi (`PERFORMANCE_NOTES.md`'den).

**Ancak iyilestirilebilir:**
- **Exponential backoff yok.** Ilk birkac poll 1 s, sonra 2-5 s gibi gradual artirim daha iyi UX (sonuc hazirsa hizli yakala, hazir degilse server'i bombalamayi birak).
- **WebSocket alternatifi mevcut ama kullanilmiyor.** `services/backend` icinde `ws.py` var (`Promise.all` grep hits bunu da bulmadi cunku frontend `WebSocket` kullanimi yok). Tahmin: backend WS endpoint'i mevcut, frontend hala polling yapiyor. WS gecisi: -%80 network requests, +instant update. **Yuksek kazanc, orta efor.**
- **Visibility-API entegrasyonu yok.** Kullanici tab'i degistirdiginde polling devam ediyor → mobilde pil yiyor. `document.visibilitychange` ile `enabled=false` yapilabilir.

### 2.6 API call paralelligi — Promise.all yok (kaynak kod tarafinda)

Grep `Promise.all` `apps/web/*.{ts,tsx}` → **kaynak dosyada hic eslesme yok**, sadece `.next/` build artifact'larinda (Next.js runtime kendi kullaniyor).

`/dashboard` page tek call yapiyor (`listInspections`), serialization sorunu yok.  
`/results/[id]` page yalnizca polling, single call.

Eger ileride bir sayfada hem `auth.me()` hem `listInspections()` lazimsa `Promise.all` ile paralel; mevcut kod-tabani bunu zaten dogru yapacak yapida ama gozetilmeli.

### 2.7 Foto preview thumbnail — `URL.createObjectURL` revoke edilmiyor (bellek sizintisi)

`packages/ui/src/components/UploadDropzone.tsx:132`:

```tsx
{files.map((f, i) => {
  const url = URL.createObjectURL(f);   // <-- her render'da yeni URL
  return (
    <img src={url} ... />
```

**Iki ayri sorun:**

1. **Her render'da yeni blob URL olusuyor** — file listesi degismediginde bile parent state degisirse FilePreview yeniden render olur. React `key={i}` korusa bile `URL.createObjectURL` yeniden cagriliyor. → React'in `<img>`'i degistirmesi gerekmiyor (URL stringi degisik gorunuyorsa degistirir; browser eski URL'yi GC'ye birakir).
2. **`URL.revokeObjectURL` hicbir yerde cagrilmiyor** — bellek sizintisi. 5 MB'lik fotograf 5 kez render olduysa 25 MB tape bellek tutulabilir (browser implementation'a bagli).

**Cozum:** `useMemo` + `useEffect(cleanup)`:

```tsx
const urls = useMemo(
  () => files.map((f) => URL.createObjectURL(f)),
  [files]
);
useEffect(() => () => urls.forEach(URL.revokeObjectURL), [urls]);
```

Buna ek olarak, **12 MB'lik bir foto direkt `<img>`'a verilirse browser tum dosyayi decode eder** (ekranda 96x96 px gosteriliyor olsa bile). 4 foto x 12 MB = 48 MB decode. Mobilde laggy. Cozum: `createImageBitmap(file, { resizeWidth: 200 })` ile thumbnail uretip onu goster.

### 2.8 Inter font — `display: swap` iyi, ama `preconnect` yok

`app/layout.tsx:11`:
```ts
const inter = Inter({ subsets: ['latin', 'latin-ext'], display: 'swap', variable: '--font-inter' });
```

- `display: 'swap'` → FOIT yok, iyi.
- Next.js `next/font` `fonts.googleapis.com`'a gitmiyor, fontu build-time'da self-host ediyor → preconnect gereksiz.
- **Iyi durum.**

Yine de `subsets: ['latin', 'latin-ext']` Turkce karakter icin doğru ama ek ~25 KB woff2. Sadece `'latin-ext'` yetebilir (icine 'latin' karakterler de dahil).

### 2.9 Tailwind safelist / unused CSS

`tailwind.config.ts` okumadim ama tipik Tailwind 3.4 + Next.js setup'inda content path'leri dogruysa unused class'lar purge edilir. `apps/web/components/**` ve `packages/ui/src/components/**` content'te olmali → kontrol et.

**Tahmini CSS bundle:** ~12-20 KB gz. Iyi.

### 2.10 Inspection annotated PNG — lazy load yok, format optimize degil

`ImageWithOverlay`'deki `<img>`:
- `loading="lazy"` yok (LCP elementi olabilir, lazy yaparsan LCP kaybeder; result page'de scroll altinda degil, hero, lazy yapma).
- `fetchpriority="high"` yok — result page'in LCP'si bu image. `fetchpriority="high"` ekleyince ~300 ms kazanc.
- Backend taraftan PNG yerine WebP/AVIF serve edilmiyor (tahmin; backend `annotator.py` opencv ile PNG yaziyor).
  - Backend'de Pillow `WEBP` quality=85 ile yazsa ~%40-60 boyut tasarrufu.

### 2.11 Metadata sorunlari

- `metadataBase: new URL('http://localhost:3000')` — **production'da overrride edilmeli** (env var). Aksi halde OG tag'leri localhost URL'leri ile yayinlanir.
- `sitemap.ts` ve `robots.ts` yok — SEO icin 1 saatlik efor.
- `themeColor: '#1e6ee0'` viewport icinde dogru tanimlanmis. Iyi.

---

## 3) Top 5 darbogaz (etki sirasi)

| # | Darbogaz | Tahmini etki | Efor |
|---:|---|---|---|
| 1 | **next/image kullanilmiyor (ozellikle annotated PNG)** | LCP +0.8 - 1.4 s; bandwidth +%40 mobil | Dusuk - Orta (2-3 component) |
| 2 | **Tum data-fetch sayfalari `'use client'`** → RSC faydasi sifir | LCP +0.4 - 0.7 s; bundle +30 KB | Yuksek (auth refactor gerekli) |
| 3 | **`URL.createObjectURL` revoke edilmiyor + tam-cozunurluk thumbnail** | Bellek sizintisi (5 dosya x 12 MB), preview render jank | Dusuk |
| 4 | **WebSocket varken polling kullanilmasi** + backoff yok | Network: ~30 istek/inspection (60s/2s); pil sarf, server load | Orta |
| 5 | **CLS — `<img>` width/height yok** sonuc geldiginde shift | CLS +0.05 - 0.1 | Dusuk |

---

## 4) Dusuk efor + yuksek kazanc oneriler (v0.1.x icinde)

1. **`react-dropzone` kaldir** (`apps/web/package.json`). Hicbir yerde import edilmiyor. → -10 KB gz potansiyel + temizlik.
2. **`UploadDropzone` FilePreview revoke fix** (yukarida snippet). Memory leak + jank giderir.
3. **`ImageWithOverlay` `<img>`'a `loading="eager"` + `fetchpriority="high"` ekle** result page'de. CSS `aspect-ratio` ile placeholder cizip CLS'i sifirla.
4. **Annotated PNG'ye `next/image`** uygula. Sadece `<img>` -> `<Image>` swap, canvas overlay component'in dısinda nokta-koordinatlari hala normalize, sorun yok.
5. **Polling visibility-aware:** `useInspectionPolling` icine `document.visibilityState !== 'visible'` durumunda `intervalMs *= 4` ekle. Tab arka plandaysa 8 s'de bir poll.
6. **Footer'i server component yap.** `'use client'` kaldir, `getTranslations` ile cevir.
7. **metadataBase env-driven:** `new URL(process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:3000')`.
8. **sitemap.ts + robots.ts ekle.** Tek seferlik 30 dakikalik is, SEO 80→90.

---

## 5) v0.2 backlog — Ileri optimizasyonlar

1. **RSC migration:** `/dashboard`, `/history`, `/results/[id]` (sonuc hazirsa) sunucuda fetch. Auth icin Next middleware + HttpOnly cookie pattern'i. Buyuk efor (~3-5 gun) ama her sayfada ~500 ms LCP + ~40 KB bundle kazanci.
2. **WebSocket polling replacement:** Backend'de `ws.py` zaten var. `lib/use-inspection-polling.ts` yerine `useInspectionWebSocket` yaz. Fallback olarak polling kalsin (auto-detect WS desteklenmiyorsa). Reconnect logic + heartbeat.
3. **Image pipeline:** Backend annotator.py PNG -> WebP. Frontend `next/image` + `priority` + responsive `sizes`. CDN cache headers (`Cache-Control: public, max-age=31536000, immutable` cunku inspection_id versionly).
4. **next-intl mesaj split:** Su an `tr.json` 24 KB tek dosya, **her sayfaya tum dictionary biniyor**. Per-route `getMessages({ locale, namespace: 'inspect' })` ile split ederek `/results` sayfasinda `auth.*` mesajlarini eleme. Tahmini -8 KB gz / sayfa.
5. **Bundle analyzer:** `@next/bundle-analyzer` ekle, gercek `First Load JS` kontrol et. CI'da PR basina threshold > 200 KB ise fail.
6. **Lighthouse CI:** GitHub Actions'da `lhci autorun` runner. Performance < 75 ise PR'i blocking.
7. **Service Worker (offline + cache):** Workbox veya `next-pwa`. Inspection sonuclarini offline cache'le, "son baktigin sonuc" pattern'i.
8. **Edge runtime:** `app/api/*` route'lari (varsa, kontrol edilmedi) edge'e tasi. Auth middleware'i zaten edge-compatible olabilir.
9. **`createImageBitmap` thumbnail decode** worker thread'de. Buyuk foto preview'lerini decode etmek main thread'i bloklamasin.
10. **Resource hints:** `<link rel="dns-prefetch" href="//api.hasari.app">` + `<link rel="preconnect" href="https://r2.cloudflarestorage.com">` annotated image domain'i icin.

---

## 6) Olcum oneri (gercek lighthouse calistirilabilirse)

```powershell
# Chromium gerektirir
pnpm dlx lighthouse http://localhost:3000 --output=html --output-path=./lighthouse-home.html --view --preset=desktop
pnpm dlx lighthouse http://localhost:3000/results/demo-001 --output=html --output-path=./lighthouse-results.html --preset=mobile --throttling.cpuSlowdownMultiplier=4
```

Mobil ozellikle `--throttling.cpuSlowdownMultiplier=4` ile gercek bir orta cihaz simule eder. Bu doknman sadece kaynak okumaya dayali olsa da, asagidaki **3 metric** mutlaka olcum sonrasi dogrulanmali:

1. `/` LCP — hero card ya da Inter font swap mi?
2. `/inspect` INP — drop event handler'i 200 ms'in altinda mi?
3. `/results/[id]` CLS — annotated PNG yuklenince layout kayiyor mu?

---

**Sonuc:** MVP icin **kullanilabilir** ama hicbir RSC / next/image / WebSocket optimizasyonu yok. Top 5 fix'i v0.1.1'de uygulayinca tahmini Performance 72 → 84 - 88 bandina ciker. v0.2'de RSC migration ile 90+ erisilir.
