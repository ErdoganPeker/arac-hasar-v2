# Inclusive Visuals Audit — Hasarİ Web

**Audit Date:** 2026-05-16
**Scope:** `apps/web` + `packages/ui` + `packages/design` (READ-ONLY)
**Audit Type:** Renk, tipografi, ikonografi, lokalizasyon, erişilebilirlik (WCAG AA + color-blind)
**Stance:** Pratik fix odaklı. Kod değiştirilmedi.

---

## 1. Genel Tablo

| # | Bulgu | Severity | Kategori | Konum |
|---|-------|----------|----------|-------|
| F-01 | Severity rengi color-blind için sadece renge bağımlı (ikon yok) | **HIGH** | Renk / a11y | `packages/ui/src/components/SeverityBadge.tsx` |
| F-02 | `Intl.NumberFormat`/`DateTimeFormat` her yerde `tr-TR` hardcoded | **HIGH** | Lokalizasyon | `apps/web/app/**/*.tsx` (5 dosya) |
| F-03 | Shared UI bileşenlerinde TR string hardcoded (EN locale'de TR yazı görünür) | **HIGH** | Lokalizasyon | `packages/ui/src/components/*` |
| F-04 | `<html lang>` doğru ama `dir` attribute yok (LTR varsayılan implicit) | LOW | Yön / a11y | `apps/web/app/layout.tsx:50` |
| F-05 | `PartCard` "hasarsız parça" sadece yeşil ringle gösteriliyor (ikon var ama küçük dot, simgesel ayırt edici zayıf) | MEDIUM | Renk / a11y | `packages/ui/src/components/PartCard.tsx:13-25` |
| F-06 | `CostDisplay` "doğruluk" göstergesi (high/medium/low) sadece renk noktası | MEDIUM | Renk / a11y | `packages/ui/src/components/CostDisplay.tsx:18-22` |
| F-07 | `severity.hafif` = amber-400 (`#fbbf24`) — beyaz arkaplanda 3:1 contrast sınır altında küçük metin için | MEDIUM | Renk / WCAG | `packages/design/src/colors.ts:45` |
| F-08 | `home/page.tsx` Hero "preview card" — kırmızı dot + amber/orange badge sadece renk ile severity ima ediyor | MEDIUM | Renk / a11y | `apps/web/app/page.tsx:88-104, 175-198` |
| F-09 | "Hasarsız parça" yeşil + "ağır hasar" kırmızı → klasik protanopia çakışması | HIGH | Renk / a11y | Genel (severity sistemi) |
| F-10 | Profil ayarlarında telefon alanı i18n'de var ama formda yok (ölü string) | LOW | Form / UX | `apps/web/messages/{tr,en}.json` + `apps/web/app/(app)/settings/page.tsx` |
| F-11 | İsim alanı `min(2)` — Türkçe tek heceli isimler için OK; `maxLength` yok (DB güvenliği zayıf) | LOW | Form | `apps/web/app/(auth)/register/page.tsx:19` |
| F-12 | E-posta validation `z.string().email()` — `+` ve `.` özel karakterleri Zod default destekler ✓ | OK | Form | `apps/web/app/(auth)/register/page.tsx:20` |
| F-13 | Para sembolü hep sonda `1.234 ₺` — TR doğru, EN için de aynı sembol kullanılıyor (tutarlı) | OK | Para birimi | Tüm `*Display` bileşenleri |
| F-14 | EN locale'de tarih `tr-TR` formatında gösterilecek (16 May 2026, 14:32) yerine US format gerekirdi | HIGH | Lokalizasyon | `apps/web/app/history/page.tsx:307-320` |
| F-15 | Logo bir image değil, Lucide `ShieldCheck` ikon — TR/EN tutarlı, kültürel sorun yok | OK | Brand | `apps/web/components/Header.tsx:34-37` |
| F-16 | Anasayfada hero görseli yok (placeholder kart) — "lüks/ekonomik araç" temsil sorunu YOK | OK | Brand / Görsel | `apps/web/public/` (boş) |
| F-17 | Plaka tipi UI'da hiçbir yerde gösterilmiyor — bölgesel önyargı YOK | OK | Brand | — |
| F-18 | Brand adı "Hasarİ" — büyük dotted İ Türkçe karakter; EN locale'de aynen kalıyor (kasıtlı, doğru) | OK | Brand | `apps/web/messages/{tr,en}.json:3` |
| F-19 | Inter font subset `['latin', 'latin-ext']` — ç, ş, ğ, ı, ö, ü destekleniyor ✓ | OK | Tipografi | `apps/web/app/layout.tsx:11-15` |
| F-20 | `tabular-nums` kullanılıyor maliyet/sayı için — sayı hizalama doğru | OK | Tipografi | Genel |

---

## 2. Detaylı Bulgular

### F-01 — Severity ikon eşleştirmesi yok (HIGH)
**Konum:** `packages/ui/src/components/SeverityBadge.tsx`

**Sorun:**
Severity'yi sadece renk ile ayırt ediyor (`hafif`=amber, `orta`=orange, `agir`=red) + küçük renkli dot (`aria-hidden`). Yazılı etiket var (`Hafif`/`Orta`/`Ağır`) — bu kısmi OK. Ancak:
- Protanopia (kırmızı görmeyen) için **orange ve red ayırt edilemez** → "orta" ve "ağır" birbirinden farksız görünür.
- Renkli dot screen reader'a `aria-hidden`, yani sadece görsel ayraç. Eksik kalan **ikon** ayraç.

**Fix önerisi (kod değiştirmeden, plan):**
```tsx
// SeverityBadge.tsx — sadece öneri, kod değişmedi
const ICONS: Record<SeverityLevel, IconComponent> = {
  hafif: Info,       // ⓘ
  orta: AlertTriangle, // ⚠
  agir: AlertOctagon,  // ⛔
};
// dot yerine <Icon className="h-3 w-3" aria-hidden /> ekle
```
Bu, **redundant coding** (renk + ikon + metin) prensibiyle WCAG 1.4.1 "Use of Color" gereksinimini karşılar.

---

### F-02 / F-14 — Hardcoded `tr-TR` locale (HIGH)
**Konum:**
- `apps/web/app/history/page.tsx:268, 310`
- `apps/web/app/(app)/settings/page.tsx:360, 363`
- `apps/web/app/(admin)/users/page.tsx:116`
- `apps/web/app/(app)/dashboard/page.tsx:96, 152, 159`
- `packages/ui/src/components/CostDisplay.tsx:38, 47`
- `packages/ui/src/components/DamageBadge.tsx:53`
- `packages/ui/src/components/PartCard.tsx:87-88`

**Sorun:**
Tüm `toLocaleString('tr-TR')` ve `Intl.DateTimeFormat('tr-TR', …)` çağrıları locale parametresini hardcoded geçiyor. EN locale aktif olduğunda kullanıcı şöyle görür:
- Beklenen (EN): `1,234.56 ₺` ve `5/16/2026, 2:32 PM`
- Gerçekleşen: `1.234,56 ₺` ve `16 May 2026 14:32`

EN locale switching çalışır ama **sayı/tarih formatları TR kalır** — yarım lokalizasyon.

**Fix önerisi:**
```tsx
// next-intl helper kullan
const t = useLocale(); // 'tr' | 'en'
const fmt = new Intl.NumberFormat(t === 'tr' ? 'tr-TR' : 'en-US');
fmt.format(value);
```
Veya `next-intl`'in built-in `useFormatter()` API'sini kullan (`format.number()`, `format.dateTime()`).

---

### F-03 — Shared UI'da TR string sızıntısı (HIGH)
**Konum:**
- `packages/ui/src/components/CleanPartsBadgeRow.tsx:22, 37` — `Hasarsız parçalar`, `daha`
- `packages/ui/src/components/InspectionSummary.tsx:11-17` — `Toplam parça`, `Hasarlı parça`, `Çoklu parça` vb.
- `packages/ui/src/components/PartCard.tsx:62, 84` — `Hasarsız`, `Parça toplam`
- `packages/ui/src/components/DamageBadge.tsx:41-49, 56` — `Çoklu parça`, `Düşük güven`, `güven`
- `packages/ui/src/components/CostDisplay.tsx:13-16, 35, 38, 53, 65` — `Yüksek doğruluk`, `Tahmini onarım maliyeti`, `Orta nokta`, `gün`
- `packages/ui/src/components/InspectionStatusBadge.tsx:5-10` — `Sırada`, `İşleniyor`, `Tamamlandı`, `Başarısız`

**Sorun:**
`@arac-hasar/ui` package'ı **Türkçe stringleri gömülü** olarak ihraç ediyor. Web app'in i18n switcher'ı bu bileşenler için EN'e geçemez → kullanıcı EN seçse de "Hasarsız parça", "Tahmini onarım maliyeti" gibi yazılar TR görür.

**Fix önerisi:**
İki seçenek:
1. **Bileşenleri props'la beslenebilir yap:** `<CleanPartsBadgeRow parts={…} labels={{title: t('cleanParts'), more: t('more')}} />`
2. **Bileşeni i18n-aware yap:** `useTranslations` çağır, sözlüğü `packages/ui` içinde tut (ya da `@arac-hasar/types`'tan re-export et). Mevcut `SEVERITY_TR`, `PART_STATUS_TR` zaten types'ta var; aynı pattern'i diğer label'lara uygula.

---

### F-04 — `<html dir>` hard-coded değil ama eksik (LOW)
**Konum:** `apps/web/app/layout.tsx:50`

**Mevcut:**
```tsx
<html lang={locale} className={inter.variable}>
```

**Sorun:**
`dir` attribute yok → tarayıcı default LTR davranır. Bu **şu an TR/EN için doğru ama** ileride AR/HE locale eklenirse fark edilmeden bozulur. RTL kapsamda değil, ama explicit yazmak best practice.

**Fix önerisi:**
```tsx
<html lang={locale} dir="ltr" className={inter.variable}>
```
Hard-coded `dir="ltr"` şu an kabul edilebilir (kapsamda RTL yok); ileride RTL desteği eklenince locale-aware yapılır.

---

### F-05 — `PartCard` "clean" durumu ikon eksik (MEDIUM)
**Konum:** `packages/ui/src/components/PartCard.tsx:53, 61`

**Sorun:**
"Hasarsız" durumu yeşil dot + yeşil pill ile gösteriliyor. Hasarlı durum siyah pill + sayı (`2 hasar`) ile gösteriliyor. Yeşil/kırmızı ayrımı **clean vs damaged için kritik** ve burada ikon yok.

**Mevcut:** `<span className="bg-emerald-500 h-2 w-2 rounded-full" aria-hidden />` + emerald pill.
**Fix önerisi:** Status indicator olarak ikon ekle:
- `clean` → `<Check />` (yeşil)
- `minor_damage` → `<Info />` (amber)
- `moderate_damage` → `<AlertTriangle />` (orange)
- `severe_damage` → `<AlertOctagon />` (red)

---

### F-06 — `CostDisplay` confidence renge bağımlı (MEDIUM)
**Konum:** `packages/ui/src/components/CostDisplay.tsx:57-62`

**Sorun:**
`high`=emerald, `medium`=amber, `low`=slate. Metin etiketi var (`Yüksek doğruluk` vb.) → kısmen OK. Ancak amber `#f59e0b` ve slate `#94a3b8` color-blind için ayırt edilebilir ama yeşil/sarı (high/medium) tritanopia için sorunlu.

**Fix önerisi:** Metin etiketi yeterli, ancak küçük bir ikon eklenebilir (`<ShieldCheck />` high, `<Shield />` medium, `<ShieldAlert />` low).

---

### F-07 — `severity.hafif` amber-400 kontrast sınırı (MEDIUM)
**Konum:** `packages/design/src/colors.ts:45`

**Mevcut yorum:**
> `amber-400 (mild) — yellow-leaning amber for contrast`

**Doğrulama:**
- `#fbbf24` (amber-400) beyaz üstünde: contrast ratio ~**1.85:1** → AA non-text 3:1 fail.
- WCAG 1.4.11 "Non-text Contrast" → UI components 3:1 ister.
- `SeverityBadge` zaten `bg-amber-100` (açık zemin) + `text-amber-900` (koyu yazı) kullanıyor, **yazı kontrastı OK** (`amber-900` üstünde `amber-100` ~7.5:1). Ancak **`severity.hafif` token'ı doğrudan badge zemini olarak kullanılırsa** sorun olur.

**Fix önerisi:** Token kullanım kuralını dokümante et:
- `severity.hafif` → sadece dot/icon dolgu rengi.
- Badge zemini için `amber-100` + yazı `amber-900` kombinasyonu zorunlu.
- Veya `severity.hafif` değerini `amber-500` (`#f59e0b`) yap → ~2.8:1, hâlâ sınır ama daha iyi. **Önerilen:** `#d97706` (amber-600) → 4.5:1 AA ✓

---

### F-08 — Anasayfa preview kartı sadece renk/dot (MEDIUM)
**Konum:** `apps/web/app/page.tsx:88-104, 175-198`

**Sorun:**
- Satır 90: `<span className="h-2.5 w-2.5 rounded-full bg-red-500" aria-hidden />` → "kırmızı = hasar" sadece renkle ima.
- `Badge` component (satır 175-198) `color` prop alıyor, severity yazısı + renkli zemin var ama **ikon yok**.

**Fix önerisi:**
Preview kart sadece marketing içerikli, ama "feature parity" göstermek için `SeverityBadge`'in ikon-iyileştirilmiş hâlini burada da kullan.

---

### F-09 — Yeşil/kırmızı protanopia çakışması (HIGH, sistemik)
**Konum:** Genel — `severity.clean` (`#22c55e`) + `severity.agir` (`#ef4444`)

**Sorun:**
Klasik problem: protanopia/deuteranopia kullanıcıları için yeşil ve kırmızı **aynı kahverengi/sarımtırak** ton olarak algılanır → "hasarsız" ve "ağır hasar" birbirinden ayırt edilemez. Bu, ürünün ana semantic mesajını (✓ vs ✕) görsel olarak yok eder.

**Fix önerisi (zorunlu, redundancy):**
- ✅ Metin etiketi (`Hasarsız` / `Ağır`) — mevcut, OK.
- ✅ İkon farklılaştırma (`<Check />` vs `<AlertOctagon />`) — eksik (F-01, F-05 ile bağlantılı).
- ✅ Şekil/border farklılaştırma — `clean` pill rounded-full, `severe` rounded-md gibi shape coding.
- ✅ Pattern (örn. ağır hasar için diagonal stripe overlay) — opsiyonel ama power tool.

**Minimum kabul:** ikon + metin + renk = 3 kanal redundancy.

---

### F-10 — Telefon alanı i18n'de var, formda yok (LOW)
**Konum:**
- `apps/web/messages/tr.json:172` — `"phone": "Telefon (opsiyonel)"`
- `apps/web/messages/en.json:172` — `"phone": "Phone (optional)"`
- Hiçbir `.tsx` dosyasında `phone` kullanılmıyor (grep doğrulandı).

**Fix önerisi:** Ya ölü string'leri kaldır, ya da `register/page.tsx` ve `settings/page.tsx`'e telefon alanı ekle. Eklenecekse:
- `+90` prefix **zorlama** — uluslararası destek için `libphonenumber-js` ile validate.
- `inputMode="tel"`, `autoComplete="tel"`, `pattern="[0-9+\s()-]+"`.
- TR placeholder: `+90 5xx xxx xx xx`, EN placeholder: `+1 (555) 123-4567`.

---

### F-11 — İsim alanı `maxLength` yok (LOW)
**Konum:** `apps/web/app/(auth)/register/page.tsx:19`

**Mevcut:** `full_name: z.string().min(2)`

**Sorun:**
- TR isimleri `min(2)` OK (örn. "Ay" gibi nadir kısa adlar).
- `max` yok → DoS/DB satır limiti riski. i18n'de zaten `fullNameTooLong: "İsim en fazla 120 karakter olabilir."` mesajı var ama schema'da kullanılmıyor.

**Fix önerisi:** `z.string().min(2).max(120)`.

---

### F-12 — Email validation OK
Zod `.email()` regex'i `+` ve `.` karakterlerini kabul eder (`user+tag@example.com`, `first.last@domain.com.tr`). **Türkçe karakter** yerel adında sorun olabilir (`çağrı@example.com` → Zod fail). Eğer `.tr` IDN destekliyorsa, `z.string().email()` yetersiz; `punycode` ile pre-process gerekir. **Düşük öncelik** — Türkçe yerel ad e-postaları nadir.

---

### F-13 — Para sembolü pozisyonu
TR norm: `1.234,56 ₺` (sembol sonda, locale-correct). EN ne yapmalı? Endüstri pratiği: TRY için `₺1,234.56` (sembol başta) ya da `1,234.56 TRY`. Mevcut tüm component'lerde sembol sonda (TR style) — EN kullanıcısı için **biraz garip ama anlaşılır**. Tutarlılık için **kabul edilebilir**, opsiyonel iyileştirme: `useFormatter().number(value, { style: 'currency', currency: 'TRY' })` → locale-correct otomatik pozisyon.

---

### F-15 / F-16 / F-17 — Brand / görsel temsil
- **Logo:** Lucide `ShieldCheck` ikon. Hem TR hem EN için aynı. Kültürel önyargı YOK.
- **Hero görseli:** Yok (`public/` boş, hero bölümü sadece text + sentetik card). Bu **kapsayıcılık için iyi haber**: ne lüks Mercedes ne 1995 Şahin temsil edilmemiş, sadece soyut "ön tampon" mock-up var (`Ön tampon` / `Front bumper` text).
- **Plaka tipi:** Hiçbir UI'da plaka örneği yok. Bölgesel önyargı sorunu yok.

**Marketing önerisi (ileride hero görseli eklenirse):**
- Çeşitli araç sınıfı (sedan, hatchback, SUV, ticari) gösteren bir görsel/illustration set.
- TR plakası göstermek istenirse: jenerik `34 XXX 1234` (İstanbul kodu yerine `XX`) veya bulanık plaka.
- Renk: tek renk araç değil — gri, beyaz, kırmızı mix (en yaygın TR pazarı).
- AI generated görsel kullanılacaksa: `clone car` artefaktları, fake plaka karakterleri, lastik şekli bozuklukları için negative prompt zorunlu.

---

### F-18 — `Hasarİ` brand kelimesi
Dotted capital `İ` Türkçeye özgü karakter. EN locale'de de `Hasarİ` olarak korunmuş — bu doğru bir brand kararı (brand adı çevrilmez). Inter font `latin-ext` subset'i bu karakteri render eder ✓.

---

### F-19 — Türkçe karakter desteği
`Inter` font `subsets: ['latin', 'latin-ext']` ile yükleniyor. `latin-ext` subset şunları içerir: ç, Ç, ş, Ş, ğ, Ğ, ı, İ, ö, Ö, ü, Ü — TR karakter seti **tam destek**. Form alanlarında bu karakterler kabul edilir (`<input>` Unicode-by-default).

---

## 3. Top 3 Öncelikli Düzeltme

### 🥇 P1 — Severity ikon eşleştirmesi ekle (F-01, F-05, F-09)
**Etki:** ~%8 erkek nüfusunda görülen kırmızı/yeşil körlüğü için ürünün ana semantic mesajını kurtarır.
**Efor:** ~2 saat.
**Dokunulacak dosyalar:**
- `packages/ui/src/components/SeverityBadge.tsx` — Lucide ikon mapping ekle.
- `packages/ui/src/components/PartCard.tsx` — status icon mapping ekle.
- `apps/web/app/page.tsx` — preview kartı `SeverityBadge` kullanacak şekilde refactor.

**Bonus:** `SeverityBadge`'e `shape="rounded" | "square"` prop'u ekleyerek shape coding ile redundancy katmanı ekle.

---

### 🥈 P2 — Locale-aware sayı/tarih formatting (F-02, F-14)
**Etki:** EN locale şu an yarım çalışıyor — tüm sayılar ve tarihler TR formatında kalıyor.
**Efor:** ~3 saat.
**Yaklaşım:**
1. `apps/web/lib/format.ts` adında yeni helper:
   ```ts
   import { useFormatter, useLocale } from 'next-intl';
   export function useNumberFmt() { … }
   export function useDateTimeFmt() { … }
   ```
2. Tüm `toLocaleString('tr-TR')` çağrılarını helper ile değiştir.
3. `packages/ui` içindeki component'ler için `formatter` prop ya da `next-intl`'i UI package'ında peer-dep yap.

---

### 🥉 P3 — Shared UI'da TR string sızıntısını temizle (F-03)
**Etki:** EN locale switcher gerçek anlamda çalışsın — sadece sayfa içi değil bileşen içi yazılar da çevrilsin.
**Efor:** ~4 saat.
**Yaklaşım:**
1. `packages/ui` içindeki tüm hardcoded TR string'i `labels` prop'una taşı (bileşen i18n-agnostic kalsın).
2. Çağıran sayfalarda `useTranslations` ile beslen.
3. `@arac-hasar/types`'taki mevcut `SEVERITY_TR`, `PART_STATUS_TR` constants'lara karşı `SEVERITY_EN`, `PART_STATUS_EN` ekle (veya tek bir locale-resolver fonksiyon).

---

## 4. Kapsam Dışı / Önemsiz

- **RTL desteği:** Kapsam dışı, ama `dir="ltr"` explicit yazılması önerilir (F-04).
- **Email IDN (`çağrı@…`):** Düşük öncelik, kullanım frekansı düşük (F-12).
- **Para birimi locale-aware format:** Mevcut hâli (sembol sonda) tutarlı ve kabul edilebilir (F-13).
- **Telefon validation:** Şu an form yok, eklenmeden tasarım kararı bekler (F-10).
- **Logo / hero görseli:** Mevcut hâli kapsayıcılık açısından temiz (F-15, F-16, F-17).

---

## 5. Doğrulanmış İyi Pratikler ✓

- `aria-hidden` decorative ikonlarda doğru kullanılmış.
- `tabular-nums` sayı hizalama için tutarlı.
- `Inter latin-ext` ile Türkçe karakter destek tam.
- Logo brand'i hem TR hem EN'de `Hasarİ` — kasıtlı, doğru.
- Hero görseli yok → bölgesel/sınıfsal araç önyargısı yok.
- Plaka kullanılmıyor → bölgesel önyargı yok.
- Form `noValidate` + custom error messages + `aria-invalid` + `aria-describedby` doğru.
- `FormField` label `htmlFor` ile input'a bağlı.
- Focus ring (`focus-visible:ring-2 ring-brand-500`) keyboard navigation için belirgin.
- `CostDisplay` `aria-label` ile screen reader için doğal dil özet sunuyor (`38. satır`).

---

**Audit Ends.**
