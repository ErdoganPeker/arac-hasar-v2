# SEO Checklist — Hasarİ (arac-hasar-v2)

Last updated: 2026-05-16
Default locale: **tr** (Turkish) — Secondary: **en** (English)
Site URL env var: `NEXT_PUBLIC_SITE_URL` (fallback `https://hasari.app`)

---

## 1. IMPLEMENTED (in repo)

### Meta tags & Metadata API (Next.js 15 App Router)
- [x] Root `metadata` in `apps/web/app/layout.tsx`
  - title template (`%s · Hasarİ`), default TR title
  - description (TR, 150-160 chars)
  - keywords array (TR-priority: "araç hasar tespit", "yapay zeka oto ekspertiz", "hasar fiyat hesaplama", "fotoğrafla hasar", "kasko hasar tahmin", "tampon çizik tamir fiyatı", "göçük tamir maliyeti", + EN secondary)
  - authors, creator, publisher, applicationName, category
  - canonical + hreflang (`tr-TR`, `en-US`, `x-default`)
  - robots directives (index/follow, googleBot max-image-preview=large)
  - icons (favicon, apple-touch-icon)
  - formatDetection disabled (email/telephone/address)
- [x] Per-page metadata:
  - `app/page.tsx` — Home (Server Component, direct export)
  - `app/inspect/layout.tsx` — Inspect page (wrapper for client child)
  - `app/(auth)/login/layout.tsx` — Login
  - `app/(auth)/register/layout.tsx` — Register

### Open Graph + Twitter Card
- [x] OG configured in root layout: type=website, siteName, locale=tr_TR, alternateLocale=en_US
- [x] Twitter card: `summary_large_image`, creator=@hasari_app
- [x] OG image generated at edge via `app/opengraph-image.tsx` (1200×630, PNG)
  - Brand mark "H" + "Hasarİ" wordmark + tagline
  - Headline: "Araç hasarını fotoğraftan tespit et."
  - Feature chips: 20+ parça, 6 hasar sınıfı, < 8 sn analiz, Türkiye fiyat tabanı
  - Gradient background (#0b3aa8 → #4c9fff)
- [x] `app/twitter-image.tsx` re-exports the OG image

### Sitemap & robots
- [x] `app/sitemap.ts` (dynamic) — `/`, `/inspect`, `/login`, `/register` with hreflang alternates
- [x] `app/robots.ts` (dynamic) — Allow `/`, Disallow `/api/`, `/dashboard`, `/admin`, `/inspections/`, `/settings`, `/_next/`, references sitemap, declares host
- [x] Optional block for LLM scraper bots (commented; enable if desired)

### Structured data (JSON-LD)
- [x] `WebApplication` + `Organization` + `WebSite` `@graph` in root layout
- [x] `inLanguage: ['tr-TR', 'en-US']` for bilingual signal
- [x] Offer price 0 TRY (free MVP), applicationCategory: BusinessApplication

### i18n SEO
- [x] hreflang alternates declared (tr, en, x-default)
- [x] `<html lang>` set from runtime locale
- [x] Cookie-based locale switching preserves canonical URL (no per-language URL prefix needed)

---

## 2. MANUAL STEPS (do BEFORE launch / after deploy)

### Required assets — drop into `apps/web/public/`
- [ ] `favicon.ico` (32×32 + 16×16 multi-resolution)
- [ ] `icon.png` (512×512 for schema.org Organization.logo)
- [ ] `apple-touch-icon.png` (180×180)
- [ ] `manifest.webmanifest` if PWA later

### Environment variables (production)
- [ ] Set `NEXT_PUBLIC_SITE_URL=https://hasari.app` (or final domain) in Vercel / hosting
- [ ] Verify `metadataBase` resolves to HTTPS production URL

### Google Search Console
- [ ] Create property at https://search.google.com/search-console (Domain property preferred — covers all subdomains)
- [ ] Verify via DNS TXT record (preferred) or HTML tag (paste verification code into `metadata.verification.google` in `layout.tsx`)
- [ ] Submit sitemap: `https://hasari.app/sitemap.xml`
- [ ] Enable email alerts (Manual Actions, Core Web Vitals regressions)
- [ ] Check Index Coverage report 48h after submit
- [ ] Validate hreflang via "International Targeting" report

### Bing Webmaster Tools
- [ ] Register at https://www.bing.com/webmasters
- [ ] Import from Search Console (one-click) OR verify via meta tag (paste into `metadata.verification.other['msvalidate.01']`)
- [ ] Submit sitemap

### Yandex Webmaster (Turkish market secondary)
- [ ] https://webmaster.yandex.com — register + verify (TR audience uses Yandex marginally)

### Analytics & tag setup
- [ ] Install GA4 (or Plausible/Umami for privacy-first) — track organic landing pages
- [ ] Link GA4 ↔ Search Console for unified reporting
- [ ] Set up GTM if planning multiple tags

### Social & profile setup (E-E-A-T signals)
- [ ] Twitter/X account `@hasari_app` (or update handle in `metadata.twitter.creator`)
- [ ] LinkedIn company page
- [ ] Add real `sameAs` URLs to `Organization` JSON-LD in `layout.tsx`
- [ ] Author entity pages with credentials (when blog launches)

### Performance & Core Web Vitals
- [ ] Run Lighthouse on production URL — target SEO ≥ 95, Performance ≥ 90
- [ ] Validate LCP < 2.5s, INP < 200ms, CLS < 0.1 (mobile + desktop)
- [ ] Audit images: ensure `next/image` everywhere, AVIF/WebP enabled
- [ ] Preconnect to API origin if used above the fold

### Rich Results Test (validation)
- [ ] https://search.google.com/test/rich-results — paste prod URL
- [ ] Confirm WebApplication + Organization + WebSite parsed without errors
- [ ] https://validator.schema.org for structural validation
- [ ] Twitter Card Validator (X): https://cards-dev.twitter.com/validator

### Content roadmap (post-launch — weeks 2-12)
- [ ] Blog/Knowledge base under `/rehber` or `/blog` for topical authority
  - Target clusters: "tampon çizik tamir fiyatı", "kasko hasar süreci", "göçük çıkartma yöntemleri", "ön cam değişim fiyatı"
- [ ] FAQ schema on home + inspect page (use existing copy)
- [ ] HowTo schema on inspect page ("Aracını nasıl çekersin?" steps)
- [ ] Original data study: "2026 Türkiye'de tampon onarım fiyatları" — linkable asset for digital PR

### Penalties / risks to watch
- [ ] Avoid duplicate content if `/dashboard` thin pages get accidentally indexed (robots.ts blocks them but add `noindex` meta on those pages too)
- [ ] Monitor Search Console "Soft 404" and "Crawled — currently not indexed" buckets monthly

---

## 3. NICE-TO-HAVE (not blocking launch)

- [ ] PWA `manifest.webmanifest` + service worker for re-engagement
- [ ] BreadcrumbList schema once `/blog/[slug]` and `/inspections/[id]` exist publicly
- [ ] VideoObject schema if product demo video added to home hero
- [ ] Speakable schema for FAQ (voice search readiness)
- [ ] hreflang verified via Merkle hreflang tester
- [ ] IndexNow integration for Bing/Yandex instant indexing of new pages

---

## 4. FILE INVENTORY (created/edited in this pass)

Edited:
- `apps/web/app/layout.tsx`
- `apps/web/app/page.tsx`

Created:
- `apps/web/app/sitemap.ts`
- `apps/web/app/robots.ts`
- `apps/web/app/opengraph-image.tsx`
- `apps/web/app/twitter-image.tsx`
- `apps/web/app/inspect/layout.tsx`
- `apps/web/app/(auth)/login/layout.tsx`
- `apps/web/app/(auth)/register/layout.tsx`
- `docs/SEO_CHECKLIST.md` (this file)
