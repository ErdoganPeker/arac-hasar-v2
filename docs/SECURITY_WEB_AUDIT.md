# Web Frontend Security Audit — arac-hasar-v2

**Scope:** `apps/web` (Next.js 15.1.3 app router) + shared `packages/ui` components consumed by web.
**Mode:** Read-only audit. No code changes.
**Date:** 2026-05-16
**Auditor:** Security Engineer (paralel görev)
**Predecessor:** Önceki dalga backend audit (4 CRITICAL + 4 HIGH bulundu, çoğu fix edildi).

---

## TL;DR

`dangerouslySetInnerHTML`, `target="_blank"` veya source-tree `console.log` **yok**. React'ın default escape'i çalışıyor. **Asıl risk dependency tarafında**: `pnpm audit` 2 CRITICAL + 19 HIGH bildiriyor. En kritik olan **CVE-2025-29927 — Next.js middleware authorization bypass** (`next@15.1.3` etkilenmiş; patch ≥15.2.3). Bu, `apps/web/middleware.ts` içindeki rol bazlı (`/users` admin) ve auth bazlı (`/dashboard`, `/inspect/new`, `/settings`) korumayı `x-middleware-subrequest` header'ı ile atlama imkanı veriyor. Belt+suspenders olarak `AuthGuard` istemci tarafında aynı koruma vermeye çalışıyor ama hassas verilerin backend tarafından korunduğu varsayılmalı.

İkincil bulgular: localStorage JWT depolama (XSS varsa token sızar — XSS yüzeyi şu an dar), prod CSP başlığı eksik, blob URL leak (`FilePreview`), `next.config.ts` `metadataBase` hardcoded `localhost:3000`, prod'da `NEXT_PUBLIC_API_URL` default `http://localhost:8000` (cleartext HTTP).

---

## Severity Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 2     |
| HIGH     | 5     |
| MEDIUM   | 6     |
| LOW      | 3     |

---

## CRITICAL

### C-1 — Next.js middleware authorization bypass (CVE-2025-29927)
**Konum:** `apps/web/package.json` (`next@15.1.3`) + `apps/web/middleware.ts:32-86`
**Kaynak:** `pnpm audit` — GHSA-f82v-jwr5-mffw, "Authorization Bypass in Next.js Middleware", vulnerable `>=15.0.0 <15.2.3`
**Açıklama:** `next@<15.2.3` sürümlerinde özel `x-middleware-subrequest` header değeri ile gönderilen istekler middleware'i tamamen atlatabiliyor. Bu projedeki middleware:
- `/dashboard`, `/inspect/new`, `/settings`, `/users` için JWT cookie kontrolü yapıyor (satır 67-83)
- `/users` admin rolü zorunlu kılıyor (satır 74-82)
- Geçerli token ile `/login`'a giden kullanıcıyı `/dashboard`'a yönlendiriyor (satır 60-65)

Bypass durumunda saldırgan, oturumsuz halde admin/dashboard sayfalarının HTML'ine erişebilir. Backend her API endpoint'i için JWT doğrulaması yaptığı sürece sızıntı **render edilen sayfa kabuğu + meta + intl mesajları** ile sınırlı kalır; ancak admin sayfaları için bu, listelenen kullanıcı/sırlar açısından kritik kabul edilmeli.
**Fix önerisi:** Web app paketinde `next` upgrade ≥ `15.5.16` (en güncel patch dalgası). Bu aynı zamanda aşağıdaki diğer HIGH/LOW next bulgularını da kapatır (SSRF, cache poisoning, DoS, middleware/proxy bypass).
```bash
# apps/web altında:
pnpm add next@^15.5.16
pnpm install
pnpm build  # standalone output bozulmadığını doğrula
```
**Belt+suspenders durumu:** `AuthGuard` (`apps/web/components/AuthGuard.tsx`) `(app)` ve `(admin)` grup layout'larında render-time client guard sağlıyor, dolayısıyla sayfa render'ında oturumsuz kullanıcı sonunda redirect oluyor. Yine de SSR çıktısı saldırgana bilgi sızdırabilir.

### C-2 — Next.js RCE in React Server flight protocol
**Konum:** `apps/web/package.json` (`next@15.1.3`)
**Kaynak:** `pnpm audit` — GHSA-4342-x723-ch2f, "Next.js is vulnerable to RCE in React flight protocol", vulnerable `>=15.1.0-canary.0 <15.1.9`
**Açıklama:** Crafted RSC istekleri server tarafında remote code execution'a yol açabilir. Bu deployment için spesifik exploit gerekleri patch notes'ta gizli tutulmuş; saldırı yüzeyi RSC kullanan tüm route'lar.
**Fix önerisi:** C-1 ile aynı upgrade kapsar (`next@^15.5.16`).

---

## HIGH

### H-1 — JWT erişim/refresh token'ları localStorage'da
**Konum:** `apps/web/lib/api.ts:30-56`
**Açıklama:**
- `setStoredTokens` access ve refresh tokenları `localStorage`'a yazıyor (`arac_hasar_access_token`, `arac_hasar_refresh_token`).
- Ayrıca middleware'ın decode edebilmesi için access token bir cookie'ye de yazılıyor (`access_token`, `path=/; samesite=lax; max-age=7d`) — **`HttpOnly` ve `Secure` flag'leri yok** (zaten istemci-okuduğu için Http-Only set edilemez bu tasarımda).

Web uygulamasında şu anda **XSS yüzeyi dar** (`dangerouslySetInnerHTML` yok, kullanıcı içeriği React text node olarak escape ediliyor). Ama bir kez XSS bulunursa (örn. ileride bir markdown render eklenirse, ya da ekstra bir 3rd party widget enjekte edilirse), localStorage `script` tarafından okunup hem access hem refresh token sızar — refresh token 7 günlük cookie max-age'iyle uzun ömürlü.
**Fix önerisi (kısa vadeli):**
- Refresh token'ı `HttpOnly + Secure + SameSite=Strict` cookie'ye taşı, sadece access token (15 dk) `sessionStorage` veya in-memory.
- Şu anki `samesite=lax` cookie prod'a giderken `Secure` flag eklenmeli (HTTPS varsayımı): `secure;` eksik (`apps/web/lib/api.ts:37-38`).
- Token'ı saklayan cookie değerini `encodeURIComponent` ile saklaman güzel; ama `path=/` her response'ta gönderiliyor — CSRF değil ama cookie boyutu artıyor.
**Fix önerisi (uzun vadeli):** BFF pattern — auth tokenları sadece backend ↔ Next.js server arasında, browser hiç görmeyecek (proxy route handler içinden upstream çağrısı yapılır). `apps/web/app/api/inspect/route.ts` zaten bunun başlangıcı ama kullanılmıyor.

### H-2 — `axios` interceptor refresh logic'i çoklu sekme race condition'ında token kaybedebilir
**Konum:** `apps/web/lib/api.ts:60-134`
**Açıklama:**
- `_refreshPromise` module-scope singleton, tek sekme için race korumalı.
- Ancak **iki sekme** aynı anda 401 alırsa, her ikisi de bağımsız `runRefresh()` çağırır. Backend refresh endpoint'i rotating refresh token döndürüyorsa (`refresh_token` opsiyonel; satır 124 `refresh_token ?? refresh`), bir sekme yeni refresh token'ı yazar, diğeri eski refresh ile çağırınca **eski reuse → token revoke** ya da **eski refresh ile alınan access** geçerli olur ama localStorage'da yeni access overwrite edilir → silent logout.
- Ayrıca `localStorage` eventleri arasında senkronizasyon yok; bir sekmede logout edilse diğer sekmedeki `client()` hâlâ eski token kullanıyor (until next 401).
**Fix önerisi:**
- `storage` event listener ekle: başka sekme `arac_hasar_access_token` silmişse o sekmede `_onUnauthorized()` tetikle.
- Backend refresh endpoint'inde rotating refresh token kullanılıyorsa, broadcast channel (`BroadcastChannel('auth')`) ile yeni token'ı tüm sekmelere yay.

### H-3 — `next-intl@3.26.5` open redirect + prototype pollution
**Konum:** `apps/web/package.json` (`next-intl@^3.26.3` resolved to 3.26.5)
**Kaynak:** `pnpm audit` — GHSA-8f24-v5vv-gm5j (open redirect, <4.9.1) + prototype pollution advisory.
**Açıklama:** Open redirect, `next-intl` redirect/route helper'ında validated olmayan locale parametresi ile dış domain'e yönlendirme. Bu repo locale routing için cookie tabanlı yaklaşım kullanıyor (`i18n.ts` resolveLocale + middleware cookie set), `next-intl/navigation` direct redirect helper kullanımı görmedim, dolayısıyla impact düşük ama upgrade gerekli.
**Fix önerisi:** `pnpm add next-intl@^4.9.1` (major bump — API breaking değişiklik kontrol edilmeli; `createNextIntlPlugin` ve `NextIntlClientProvider` API'leri 3 → 4'te değişti).

### H-4 — `@xmldom/xmldom` 5x XML injection + recursion DoS (transitive)
**Konum:** transitive deps (büyük olasılıkla mobile veya Expo zincirinde, web'i de etkileyebilir lockfile bağımlı)
**Kaynak:** `pnpm audit` — GHSA-9pgh-qqpf-7wqj, GHSA-mxf7-f5fr-fjp6 vs. `<0.8.13`
**Açıklama:** Web app SVG/XML parsing yapmıyor (görmedim), ama transitive dep ağırlığı olarak audit'te raporlanıyor. Web bundle'ında SVG path string'leri statik, kullanıcı XML feed'i parse edilmiyor.
**Fix önerisi:** `pnpm.overrides` ile `"@xmldom/xmldom": ">=0.8.13"` zorla, monorepo root `package.json`'a ekle.

### H-5 — `node-tar` zincirinde 6 high (transitive, build-time)
**Konum:** transitive; pnpm/expo/Next.js install zincirinde
**Açıklama:** Path traversal, arbitrary file overwrite, race condition. Runtime exposure web bundle'ında **yok**; sadece `pnpm install` / docker build zamanında, eğer untrusted tarball indiriliyorsa.
**Fix önerisi:** Bilgi olarak not edilsin. Risk: build container'ında supply-chain. Mitigation: `pnpm.overrides` ile `"tar": ">=7.5.10"`.

---

## MEDIUM

### M-1 — `NEXT_PUBLIC_API_URL` prod default `http://localhost:8000` — HTTP cleartext
**Konum:** `apps/web/next.config.ts:19-21`, `apps/web/lib/api.ts:16-17`, `apps/web/app/api/inspect/route.ts:14-16`, `apps/web/.env.local:3`, `apps/web/.env.local.example:2`
**Açıklama:** Üç ayrı dosyada `process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'` fallback'i var. Prod build sırasında env değişkeni set edilmezse bundle'a `http://localhost:8000` gömülür; kullanıcı tarafından çağrıldığında istek browser'dan localhost'a gider (sessizce CORS ile patlar) **veya** istemci LAN'ında bir yere — bilgi sızıntısı ve broken state.

Ayrıca cleartext HTTP — prod'da TLS gerektiren bir backend için cleartext fallback access token Authorization header'ını wire üzerinde dinleyebilen MitM'e açar.
**Fix önerisi:**
- `next.config.ts` içinde `if (process.env.NODE_ENV === 'production' && !process.env.NEXT_PUBLIC_API_URL) throw new Error(...)` ekle (build-time guard).
- Fallback URL'i `https://...` ile ezildiğinden emin ol veya boş bırak ve runtime'da error fırlat.

### M-2 — CSP header'ı yok (web tarafı)
**Konum:** `apps/web/middleware.ts:32-86`, `apps/web/next.config.ts:6-25`
**Açıklama:** Backend tarafı API için CSP `default-src 'none'` set ediyor (önceki dalga). Ama Next.js web sayfaları için **hiç CSP yok**. Bu durumda:
- Inline event handler veya `<script>` injection olursa hiçbir browser-side defence çalışmaz.
- `font-src`, `connect-src`, `frame-ancestors` kısıtı yok → site clickjacking'e açık (`X-Frame-Options` de yok).
**Fix önerisi:** `middleware.ts` veya `next.config.ts` `headers()` callback'i ile aşağıdakileri ekle (CSS-in-JS / tailwind inline style için `'unsafe-inline'` style gerekiyor; Next.js production'da `script-src` için nonce gerekli):
```
Content-Security-Policy:
  default-src 'self';
  script-src 'self' 'nonce-<dynamic>' 'strict-dynamic';
  style-src 'self' 'unsafe-inline';
  img-src 'self' data: blob: https://<S3>;
  font-src 'self' data:;
  connect-src 'self' <API_URL>;
  frame-ancestors 'none';
  base-uri 'self';
  form-action 'self';
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
Permissions-Policy: camera=(), microphone=(), geolocation=()
Strict-Transport-Security: max-age=31536000; includeSubDomains
```
Not: scope dışında bırakılan Cloudflare/Sentry önerilmiyor; bu header'lar Next.js'in kendi middleware'inde verilebilir.

### M-3 — Cookie `Secure` flag eksik (prod risk)
**Konum:** `apps/web/lib/api.ts:36-38` (`access_token` cookie), `apps/web/middleware.ts:49-53` (`NEXT_LOCALE` cookie)
**Açıklama:** `samesite=lax` set edilmiş ama `Secure` yok. Prod'da HTTPS varsayımı altında her cookie `Secure` olmalı; aksi takdirde HTTP downgrade saldırısında sızar (HSTS preload yoksa).
**Fix önerisi:** `process.env.NODE_ENV === 'production'` durumunda `; secure` ekle.

### M-4 — Blob URL memory leak (`FilePreview`)
**Konum:** `packages/ui/src/components/UploadDropzone.tsx:131-132`
**Açıklama:** `FilePreview` her render'da `URL.createObjectURL(f)` çağırıyor — `URL.revokeObjectURL` yok. 20 dosya seçildiğinde, her state değişikliğinde 20 blob URL daha allocate ediliyor, bunlar sayfa unmount'a kadar memory'de kalıyor (Chrome bazılarını GC eder ama garanti yok).

Doğrudan güvenlik açığı değil ama uzun seansta browser memory exhaustion DoS potansiyeli. Ayrıca blob URL'leri `<img src>` ile DOM'a yazılıyor — XSS yüzeyi yok çünkü `URL.createObjectURL`'den dönen string güvenli format (`blob:https://...`).
**Fix önerisi:** `useMemo` + `useEffect` cleanup pattern:
```tsx
const urls = useMemo(() => files.map(f => URL.createObjectURL(f)), [files]);
useEffect(() => () => urls.forEach(URL.revokeObjectURL), [urls]);
```

### M-5 — `metadataBase` hardcoded `http://localhost:3000`
**Konum:** `apps/web/app/layout.tsx:24`
**Açıklama:** Prod'da OpenGraph / Twitter / canonical URL'leri `http://localhost:3000/...` üretir; sosyal medya paylaşımında broken link, image preview yok. Güvenlik açısından düşük ama infosec disclosure (host header gönderme yerine hardcoded internal URL = info leak).
**Fix önerisi:** `new URL(process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:3000')` ve prod'da env değişkeni zorla.

### M-6 — Backend `/api/inspect` proxy route yetkilendirme yapmadan API key gönderebiliyor
**Konum:** `apps/web/app/api/inspect/route.ts:18-55`
**Açıklama:** Route handler `BACKEND_API_KEY` env değişkeni varsa otomatik olarak istek başlığına ekliyor. Ancak gelen istemcinin **JWT kimliğini kontrol etmiyor** (sessionId, cookie veya Bearer header doğrulaması yok). Eğer bu route prod'da açıkta kalır ve yetenekli `BACKEND_API_KEY` set edilirse, internet üzerindeki herkes auth gerekmeden inspect endpoint'ini bu key ile tetikleyebilir (rate limit dışı + bypass).

Pozitif: Şu anki frontend kodu (`apps/web/lib/api.ts`) bu route'u kullanmıyor; direkt `client()` ile `${API_URL}/api/v1/inspect` çağırıyor. Yine de dead route prod build'a girer.
**Fix önerisi:** Ya route'u sil (kullanılmıyor), ya da `BACKEND_API_KEY` set edildiğinde route handler'da JWT cookie/Authorization doğrulaması ekle ve yalnızca authenticated kullanıcıya forward et.

---

## LOW

### L-1 — Mock/demo data prod build'a giriyor
**Konum:** `apps/web/app/history/page.tsx:15-36` (`DEMO_ITEMS` array)
**Açıklama:** Demo inspection items prod bundle'a katılıyor; backend boş döndüğünde gösteriliyor. Bilgi sızıntısı değil ama production data quality issue + `usingDemo` state ile karışıklık (kullanıcı gerçek mi demo mu olduğunu bilemeyebilir).
**Fix önerisi:** `process.env.NODE_ENV === 'development'` ile koşullu fallback, prod'da boş state göster.

### L-2 — `jwt.ts` istemci tarafında JWT decode ediyor
**Konum:** `apps/web/lib/jwt.ts:35-46`, `apps/web/middleware.ts:75-77`
**Açıklama:** Comment'te belirtildiği gibi `Signature verification stays server-side. Never trust this for authorization`. Doğru not, ama `middleware.ts:74-82` admin role check'i için `payload.role` kullanıyor. CVE-2025-29927 ile birleşince bu bypass edilebilir; bypass edilmese bile JWT payload manipulate edilirse middleware aldanır (JWT signature backend'de check edildiği için sonuçta API'ler korunur ama HTML kabuğu sızabilir).
**Fix önerisi:** Middleware'da admin route'lara HTML response'unda da sensitive data sızdırmadığından emin ol (örn. `/users` sayfası mount sonrası `/admin/users` API'sini çağırıyor — backend zaten JWT signature doğruluyorsa bu OK).

### L-3 — Inspection thumbnail `<img>` URL'leri allowlist yok
**Konum:** `apps/web/app/history/page.tsx:240-245`
**Açıklama:** `it.thumbnail_url` backend'den gelen rastgele URL. Eğer backend storage URL'i compromise olursa veya kötü amaçlı user upload'lar URL injection ile başka kaynağa işaret ederse, browser oradan resim çekmeye çalışır. Modern browser'lar `javascript:` `img src`'yi engelliyor ama `data:` ya da external host hâlâ pixel-tracking yapabilir.
`next.config.ts:11-17` `remotePatterns` allowlist'i sadece `next/image` için var; düz `<img>` için değil (zaten satır 239'da `// eslint-disable-next-line @next/next/no-img-element` var).
**Fix önerisi:** `next/image` kullan + `remotePatterns` allowlist'ine güven. CSP `img-src 'self' https://<known-cdn>` da koruyacak (bkz M-2).

---

## İncelenip Temiz Çıkanlar

| Kontrol | Sonuç |
|---------|-------|
| `dangerouslySetInnerHTML` kullanımı | **Yok** (`apps/web/app/**` + `apps/web/components/**` + `packages/ui/**`) |
| `target="_blank"` link'leri | **Yok** (`rel=noopener` kontrolüne gerek yok) |
| Source-tree'da `console.log` / `console.error` | **Yok** (`apps/web/**/*.{ts,tsx}` temiz) |
| Hardcoded credential / API key string'leri | **Yok** (sadece env değişkenleri) |
| Sentry / Datadog SDK | **Kurulu değil** (scope dışı, OK) |
| Backend `allow_credentials=false` durumu | **Doğrulandı** (`axios.create({ withCredentials: false })`, `apps/web/lib/api.ts:71`) — CSRF yüzeyi düşük çünkü cookie'ler API çağrısında gönderilmiyor; token Authorization header'ında |
| `clearStoredTokens` logout'ta çağrılıyor mu | **Evet** (`apps/web/lib/auth-context.tsx:47-51` `logout` + `apps/web/lib/api.ts:98` 401 sonrası) |
| File MIME client check | `image/*` startsWith + extension allowlist (`packages/ui/src/components/UploadDropzone.tsx:38-41`) — magic byte server-side zaten önceki dalgada eklendi |
| User input render escape | React text node default escape, kullanıcı verisi (`user?.full_name`, `it.inspection_id`, vb.) hep `{}` interpolation içinde — XSS yüzeyi yok |
| `auth/api-keys` plaintext secret bir kez gösteriliyor | **Doğru** (`apps/web/app/(app)/settings/page.tsx:311-333`, `<code>` içinde, copy button) — leak yüzeyi sadece görsel hafıza + clipboard |

---

## Öncelikli Aksiyon Listesi (Top 5)

1. **C-1 + C-2 + H-3 + multiple HIGH next CVE'lerini tek upgrade ile kapat:** `pnpm --filter @arac-hasar/web add next@^15.5.16 next-intl@^4.9.1`. Sonrasında `pnpm build` ile standalone output'un bozulmadığını ve `createNextIntlPlugin` API'sinin v4 imzasıyla uyumlu olduğunu kontrol et.
2. **M-2 — Next.js middleware'a security header'ları ekle:** CSP, X-Frame-Options, Referrer-Policy, Strict-Transport-Security, X-Content-Type-Options, Permissions-Policy. `apps/web/middleware.ts` zaten her response'a dokunuyor; satır 85'teki `res` üzerinden `res.headers.set(...)` ile eklenebilir. Cloudflare/3rd-party gerekmez.
3. **M-1 + M-3 — Prod env hardening:** `next.config.ts`'de `NODE_ENV === 'production'` iken `NEXT_PUBLIC_API_URL` boşsa build-time error fırlat; `apps/web/lib/api.ts:36-38` cookie set'inde prod'da `; secure` ekle.
4. **H-1 — Refresh token'ı `HttpOnly + Secure` cookie'ye taşı:** Access token (15 dk) `sessionStorage`'da kalabilir; refresh token uzun ömürlü olduğu için XSS karşısında en değerli hedef. Backend `/auth/refresh` endpoint'i `Set-Cookie` ile dönüş yapacak şekilde Backend Engineer ile koordine et.
5. **H-2 — Multi-tab token race koruması:** `window.addEventListener('storage', ...)` ile başka sekmedeki logout / token rotation'ı dinle. 5 satır kod, çoklu sekme kullanıcılarında silent logout'u önler.

---

## Önerilmeyen (Scope Dışı — Bilinçli Atlandı)

- Sentry / Datadog / observability SDK ekleme
- Cloudflare WAF / DDoS koruması
- Production altyapı (CDN, load balancer)
- Backend tarafına yeni endpoint önerisi (önceki dalga konusu)
- Sentry'siz error monitoring çözümü
