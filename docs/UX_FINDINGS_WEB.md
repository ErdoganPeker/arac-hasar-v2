# Web App UX Audit — Findings

**Scope:** `apps/web/` Next.js 15 app. Heuristic evaluation (Nielsen 10) of the user flows: anonymous demo, returning user (auth), multi‑photo upload, error states, mobile responsive, i18n, trust signals, onboarding.

**Method:** Static code review of the pages, shared components and i18n message catalogues. No runtime testing. Severity scale: **1 = cosmetic**, **2 = minor**, **3 = major**, **4 = critical**, **5 = catastrophic / blocks task completion**.

**Files reviewed (key):**
- `apps/web/app/page.tsx` (home)
- `apps/web/app/inspect/page.tsx` (anonymous demo upload)
- `apps/web/app/(app)/inspect/new/page.tsx` (authenticated upload, with progress bar)
- `apps/web/app/(app)/dashboard/page.tsx`
- `apps/web/app/(auth)/login/page.tsx`, `apps/web/app/(auth)/register/page.tsx`, `apps/web/app/(auth)/layout.tsx`
- `apps/web/app/history/page.tsx`
- `apps/web/app/results/[id]/page.tsx`
- `apps/web/components/Header.tsx`, `Footer.tsx`, `LanguageSwitcher.tsx`, `AuthGuard.tsx`, `FormField.tsx`, `ToastProvider.tsx`, `InspectionStatusBadge.tsx`
- `apps/web/middleware.ts`, `apps/web/i18n.ts`, `apps/web/lib/api.ts`, `apps/web/lib/use-inspection-polling.ts`
- `packages/ui/src/components/UploadDropzone.tsx`
- `apps/web/messages/tr.json`

---

## H1 — Visibility of System Status

### F1.1 — Anonymous /inspect has no upload progress feedback — Severity 4
**Location:** `apps/web/app/inspect/page.tsx` (lines 53‑66, `handleSubmit`).
**Observation:** The authenticated `app/(app)/inspect/new/page.tsx` wires `onUploadProgress` and renders a percentage bar (lines 156‑169). The anonymous `app/inspect/page.tsx` calls `createInspection(files, { mode: effectiveMode })` with no `onUploadProgress` handler — the demo user only sees a spinner with the word "Yükleniyor…". With 5–20 images on a 4G connection this can stall the perceived UI for tens of seconds.
**Fix proposal:** Reuse the same `onUploadProgress` + progress bar JSX that exists in `(app)/inspect/new/page.tsx`. The hook already supports it (`apps/web/lib/api.ts` line 211, 254‑259).

### F1.2 — Async inspection polling has no granular phase text — Severity 3
**Location:** `apps/web/app/results/[id]/page.tsx` (`PendingState`, lines 308‑334); `use-inspection-polling.ts`.
**Observation:** The polling state only differentiates `queued` ("Kuyrukta") vs `processing` ("İşleniyor"). The i18n catalogue (`tr.json` `inspect.progress.*`, lines 273‑283) already defines a rich vocabulary: "Hasar tespiti yapılıyor…", "Araç parçaları algılanıyor…", "Maliyet hesaplanıyor…", "Neredeyse bitti…". These strings exist but are never used. With a 60 s polling window the user sees the same "İşleniyor…" message for the whole minute — feels stuck.
**Fix proposal:** Wire the existing `inspect.progress.*` strings to backend progress field (already shipped) or, as a minimum, rotate placeholder messages every ~5 s so the screen does not feel frozen. Strings already exist — no new copy needed.

### F1.3 — Polling timeout state is misleading — Severity 3
**Location:** `apps/web/app/results/[id]/page.tsx` lines 81‑96.
**Observation:** When `timedOut` fires after 60 s, the screen shows `t('processing')` (title) + `tCommon('errorGeneric')` ("Bir hata oluştu…") as description. But the inspection is **not** failed — backend is still processing. Telling the user something errored when nothing errored is wrong status communication; the "Yenile" CTA is correct but the framing is mixed‑message.
**Fix proposal:** Replace the description with a dedicated string like "İşlem tahmininden uzun sürüyor. Sayfayı yenile veya birkaç dakika sonra Geçmiş'ten kontrol et." (add to `tr.json`). Suggest linking to `/history` so user does not lose the inspection.

### F1.4 — No live region for async status transitions — Severity 2
**Location:** `app/results/[id]/page.tsx` `StatusBadge` (line 288).
**Observation:** Status badge updates from "İşleniyor" → "Tamamlandı" silently. Screen reader users are not announced when results become available. `ToastProvider` already implements `aria-live="polite"` correctly (lines 73‑77); the same pattern is missing for status transitions.
**Fix proposal:** Wrap `StatusBadge` (or emit a hidden `aria-live="polite"` region) so the transition is announced. Optionally fire a toast on terminal status.

### F1.5 — Header logo "MVP" badge is informative but only visible ≥sm — Severity 1
**Location:** `apps/web/components/Header.tsx` line 38‑40 (`hidden ... sm:inline`).
**Observation:** The "MVP" label that contextualizes maturity is hidden on mobile, where most demo users will land.
**Fix proposal:** Show as a small chip on mobile too, or move the disclaimer to the result page (see F7 trust signals).

---

## H2 — Match Between System and the Real World

### F2.1 — Anonymous demo result currency / disclaimer absent at first sight — Severity 3
**Location:** `app/page.tsx` line 110 hard‑codes `3.500 – 5.200 ₺` in the preview card; `app/results/[id]/page.tsx` shows cost via `CostDisplay`.
**Observation:** The home preview shows a precise TL range with no caveat — sets expectation that cost is exact. The actual result page does carry a disclaimer (`inspect.result.disclaimer` in `tr.json` line 349) but I cannot confirm `CostDisplay` from `@arac-hasar/ui` surfaces it next to the number. The disclaimer text exists in messages; whether it is rendered prominently with the cost is unclear from the audited file alone.
**Fix proposal:** Add a small "Tahmini — kesin değil" footnote directly under the hero preview card's "3.500 – 5.200 ₺" line. Verify `CostDisplay` renders `inspect.result.disclaimer` adjacent to the headline number on the results page; if not, expose it as a visible micro‑copy under the price.

### F2.2 — "Kuyruğa al" vs "Anında işle" — jargon for a B2C audience — Severity 3
**Location:** `app/(app)/inspect/new/page.tsx` (and anonymous twin) lines 130‑145; messages `inspect.modeAsync`, `inspect.modeSync` in `tr.json` lines 245‑248.
**Observation:** "Kuyruğa al (önerilen)" is engineering vocabulary. The driver doesn't think in queues; they think in "hızlı / yavaş", "şimdi / sonra". The descriptive sub‑text ("Arka planda işlenir") is better but the primary label still leads with the technical word.
**Fix proposal:** Rename labels (copy‑only, no code change) to user‑mental‑model wording:
- `modeAsync` → "Detaylı analiz" / "Tüm fotoğraflar (önerilen)"
- `modeSync` → "Hızlı önizleme (maks. 3 foto)"

### F2.3 — History filter dropdown lists raw status codes — Severity 3
**Location:** `app/history/page.tsx` lines 161‑165.
**Observation:** The status filter `<option>` renders the raw status value (`queued`, `processing`, `completed`, `failed`) without running it through `useTranslations('status')`. Compare with `InspectionStatusBadge` (line 27) which correctly uses `t(status)` to render "Kuyrukta" / "Tamamlandı" etc. Users see English internal codes in a Turkish dropdown.
**Fix proposal:** Wrap the option label with the `status` translator: `<option key={s} value={s}>{tStatus(s)}</option>`.

### F2.4 — Damage area shown as % only, no human metric — Severity 2
**Location:** `app/results/[id]/page.tsx` line 223.
**Observation:** "Toplam hasarlı alan: %3.4" — the percentage is mathematically precise but unintuitive. A driver doesn't have a frame of reference for "3.4% of the vehicle".
**Fix proposal:** Add a contextual hint: "%3.4 (≈ avuç içi büyüklüğünde)" or map to `hafif / orta / yoğun`. Copy can live in `tr.json`.

---

## H3 — User Control and Freedom

### F3.1 — No "Cancel inspection" or "Stop polling" — Severity 2
**Location:** `app/results/[id]/page.tsx` + `use-inspection-polling.ts`.
**Observation:** `inspect.cancelInspection` and `inspect.cancelConfirm` strings exist in `tr.json` (lines 296‑297) but there is no Cancel CTA wired into the pending state. Once a user submits 20 photos they are committed to waiting up to 60 s with no exit.
**Fix proposal:** Render a "İptal et" `btn-secondary` next to the spinner in `PendingState`. On click, navigate back to `/history` or `/inspect`. Backend cancel endpoint is out of scope — at minimum the UI should let the user leave without losing the page.

### F3.2 — Submit button does not survive an upload failure — Severity 3
**Location:** `app/(app)/inspect/new/page.tsx` lines 67‑74; same pattern in `app/inspect/page.tsx`.
**Observation:** On `catch`, `setSubmitting(false)` runs, but the selected files remain — good. However the progress bar's last value (`progress`) is not reset, so the next attempt briefly shows the stale percentage before re‑starting. Minor regression for the user trying to retry.
**Fix proposal:** Reset `setProgress(0)` inside the catch.

### F3.3 — Login `next=` redirect — partial trust — Severity 2
**Location:** `app/(auth)/login/page.tsx` line 27 (`search.get('next') || '/dashboard'`).
**Observation:** The page reads `next` and pushes the user there — but never validates that it is a same‑origin relative path. While `middleware.ts` lines 67‑73 set the `next` correctly, a hand‑crafted `?next=https://evil/...` from a phishing email would redirect after a real login. Minor UX/security overlap; user expects to land where they wanted to go, not somewhere unexpected.
**Fix proposal:** Guard: `const next = (raw && raw.startsWith('/') && !raw.startsWith('//')) ? raw : '/dashboard';`. No new copy.

### F3.4 — `Remove all` is destructive without confirmation — Severity 2
**Location:** `app/(app)/inspect/new/page.tsx` lines 103‑109 ("Hepsini kaldır").
**Observation:** After selecting 18 photos, one accidental click on the underlined text and the entire selection is gone. There is no undo and no confirmation.
**Fix proposal:** Either confirm via the existing `ConfirmDialog` (already in `@arac-hasar/ui`) when ≥3 files are selected, or use a 5 s undo toast (`useToast` is available).

---

## H4 — Consistency and Standards

### F4.1 — Two near‑identical /inspect pages drift — Severity 4
**Location:** `app/inspect/page.tsx` (anonymous) vs `app/(app)/inspect/new/page.tsx` (auth).
**Observation:** Both pages are ~270 lines, share the same headline, dropzone, mode selector, tips sidebar. But:
- Only the authenticated page has the upload progress bar.
- Only the authenticated page calls `toast.error` on failure (anonymous shows the error banner only).
- The error message reset path differs (anonymous never resets progress because it has none).
- The user's mental model of "submitting photos" is identical in both; the divergence is purely accidental.
**Fix proposal:** Extract a shared `<InspectUploadFlow />` component in `components/`. The page files become thin wrappers that pass a redirect URL and a flag for "auth required to save". This is a refactor (not a feature), explicitly within scope.

### F4.2 — Header "Hasarİ" wordmark uses dotted‑capital‑I — Severity 1
**Location:** `Header.tsx` line 37, `metadata.title` in `layout.tsx`, `tr.json` `common.appName`.
**Observation:** "Hasarİ" mixes Turkish capital I with dot. Looks intentional and culturally on‑brand but breaks copy‑paste and search; in `en.json` (not opened but inferable) it may render as garbled in English contexts. Verify EN string falls back to "Hasari" or "HasarAI".
**Fix proposal:** Confirm `en.json` `common.appName` is ASCII‑safe; if it currently mirrors TR, switch EN to "HasarAI" or similar.

### F4.3 — Status badge palette inconsistent between pages — Severity 2
**Location:** `components/InspectionStatusBadge.tsx` vs `app/results/[id]/page.tsx` line 288 (`StatusBadge` local function).
**Observation:** `results/[id]/page.tsx` defines its **own** local `StatusBadge` with a slightly different style (`px-3 py-1`, `rounded-full`, includes spinner) instead of importing the shared `InspectionStatusBadge` (`px-2 py-0.5`, no spinner). Users see the same status with different visual weight on `/history` vs `/results/{id}`.
**Fix proposal:** Either extend `InspectionStatusBadge` with a `size` and `withSpinner` prop, or drop the local copy in favour of the shared component.

### F4.4 — Anonymous submit lands on `/results/{id}` but user can't see it after page refresh — Severity 3
**Location:** `app/inspect/page.tsx` line 60 (`router.push(/results/${targetId})`); `middleware.ts` lines 4‑9 (PROTECTED_PREFIXES does NOT include `/results`).
**Observation:** Good — `/results/{id}` is public, so the anonymous user reaches the result. But on refresh, the `useInspectionPolling` hook calls `GET /api/v1/inspect/{id}`, and without an auth token the backend may 401 (depends on the inspection endpoint policy — not auditable from frontend alone). If the backend allows anonymous reads with an opaque ID this is fine; if not, the anonymous user loses access to their own result on refresh.
**Fix proposal:** Verify backend policy. If anonymous lookup requires an unguessable token, ensure the URL contains it. Otherwise add a banner on the anonymous result page: "Bu sonuca daha sonra erişebilmek için hesap oluştur" with a register CTA (conversion opportunity using existing copy).

### F4.5 — `Tarih` / `Hasar` / `Maliyet` table headers are hardcoded Turkish in Dashboard — Severity 3
**Location:** `app/(app)/dashboard/page.tsx` lines 131‑134.
**Observation:** The table headers `<th>Tarih</th>`, `<th>Hasar</th>`, `<th>Maliyet</th>` are plain strings, not `t('...')`. Other parts of the page use `th(...)` and `t(...)` correctly. On `/?lang=en` the page will mix English UI with three Turkish columns.
**Fix proposal:** Move strings into `dashboard` or `history.table.*` namespace (already exists at `tr.json` lines 385‑392) and call `tHistory('table.date')` etc.

---

## H5 — Error Prevention

### F5.1 — UploadDropzone validates all‑or‑nothing, no per‑file feedback — Severity 3
**Location:** `packages/ui/src/components/UploadDropzone.tsx` lines 28‑45.
**Observation:** If a user drops 20 files and one of them is 15 MB, `validate()` returns `{ ok: [], error: "Dosya çok büyük: foo.jpg (>12MB)" }` — **all 20 files are rejected**. The user must remove the offending file from their OS file picker and retry. This is hostile when one bad file ruins a batch upload of 19 good photos.
**Fix proposal:** Split the validator into "accept good, surface bad" — return `{ ok: File[], rejected: {file, reason}[] }`, then list the rejected files inline with their reason while keeping the good ones. Strings exist (`inspect.errors.fileTooLarge`, `invalidFormat` lines 287‑288).

### F5.2 — UploadDropzone hard‑codes Turkish strings — Severity 3
**Location:** `packages/ui/src/components/UploadDropzone.tsx` lines 22, 31, 36, 39, 89, 91, 111, 147.
**Observation:** The component (in shared `@arac-hasar/ui`) hard‑codes Turkish: "Görüntüleri sürükle bırak veya tıkla", "JPG, PNG, WEBP — maks. 12MB / dosya", "En fazla {n} dosya yükleyebilirsin.", "Dosya çok büyük", "Görüntü değil", "kapat", "{name} kaldır". An English user lands on the home page and the dropzone reads Turkish. The web app already passes localized labels through `inspect.errors.*` and `inspect.dragOrClick` but the shared UI ignores them.
**Fix proposal:** Either accept all strings as props (label, hint, dragText, errorTexts) and pass `t(...)` from the page, or move the strings into the message file under `inspect.dropzone.*` and let the consumer pass a `labels` object. No new strings — they all exist already.

### F5.3 — Password rule communicated only after submit — Severity 2
**Location:** `app/(auth)/register/page.tsx` lines 17‑22, FormField hint slot unused.
**Observation:** Password schema requires ≥8 chars, the placeholder says "En az 8 karakter" — good. But there is no live validity indicator (no green check at 8 chars, no "şifre güçlü mü?" meter). The `auth.passwordWeak` message exists ("büyük harf, küçük harf ve rakam içermeli") but is never wired.
**Fix proposal:** Pass a `hint` to `<FormField>` with the rules, or compute live `valid` state and show a checkmark when the rule is met. Copy already exists.

### F5.4 — Drag and drop dropzone is rendered as a `<button>` — Severity 2
**Location:** `packages/ui/src/components/UploadDropzone.tsx` lines 64‑93.
**Observation:** The outer element is `<button type="button" onDragOver onDrop>`. Buttons inside buttons (the X "remove" button on file previews lives outside but still — a `<button>` should not be a drop target semantically). On Safari iOS / some assistive tech this can be confusing.
**Fix proposal:** Change to `<div role="button" tabIndex={0} onKeyDown=...>` with explicit Enter/Space handling, or split into a wrapping `<div>` that hosts dnd events and an inner `<button>` for click‑to‑open.

### F5.5 — No client‑side warning when the user has selected 0 photos and presses Submit — Severity 1
**Location:** `app/(app)/inspect/new/page.tsx` line 48 `canSubmit = files.length > 0 && !submitting`.
**Observation:** Button is disabled, but disabled buttons are silent. New users wonder why they cannot click "İncelemeyi başlat". String exists: `inspect.errors.noFiles` "En az bir fotoğraf seç".
**Fix proposal:** Show a small helper text under the disabled button explaining why it's disabled.

---

## H6 — Recognition Rather Than Recall

### F6.1 — `/history` card shows only first 12 chars of UUID — Severity 2
**Location:** `app/history/page.tsx` line 257 and `dashboard/page.tsx` line 145 (`inspection_id.slice(0, 12)…`).
**Observation:** Users have no way to recognize past inspections — every card looks the same except a date and a damage count. The thumbnail (`it.thumbnail_url`) helps when present, but the camera placeholder dominates when it isn't.
**Fix proposal:** Show the first damage type as a chip ("Çizik", "Göçük") plus the part name ("Ön Tampon") next to the date — both already in the data model (`damage_count`, severity, parts on detail). The list endpoint may not return part labels yet — if so, surface the dominant damage type using the chip pattern from the home preview card.

### F6.2 — Dashboard "Recent inspections" duplicates `/history` work — Severity 1
**Location:** `app/(app)/dashboard/page.tsx`.
**Observation:** The dashboard table is a poor cousin of the history grid: text‑only, no thumbnail, truncated UUID. Returning users go to `/dashboard` and then re‑navigate to `/history` for the rich view. Consistency would be reusing the card grid (first 3‑6 items) directly.
**Fix proposal:** Replace the table with the same card grid from `/history`, capped at 3 items. Same component, same mental model.

### F6.3 — Inspection ID is the only identifier on the result page — Severity 2
**Location:** `app/results/[id]/page.tsx` line 53‑55.
**Observation:** Header shows "İnceleme ID: e3a5f‑..." in mono font. There is no human label (no vehicle plate, no nickname, no first photo thumbnail). Users come back to a past inspection by guessing.
**Fix proposal:** Show the first photo thumbnail next to the title and the relative date ("2 saat önce — 3 fotoğraf"). Both data points are already available.

---

## H7 — Flexibility and Efficiency of Use

### F7.1 — No keyboard shortcut to submit upload — Severity 1
**Location:** `app/(app)/inspect/new/page.tsx` `handleSubmit`.
**Observation:** Power users (insurance agents doing batches) cannot Ctrl+Enter to fire the submit. Minor.
**Fix proposal:** Add a `document`-level keydown for `Ctrl/Cmd + Enter` when files are selected.

### F7.2 — History filters don't have a "Clear all" button — Severity 2
**Location:** `app/history/page.tsx` lines 126‑200.
**Observation:** String `history.clearFilters` exists in `tr.json` line 374. Not rendered. After applying status + date range + search, the only way to reset is to manually clear each.
**Fix proposal:** Show a "Filtreleri temizle" button next to the filter row when any filter is active.

### F7.3 — Language switcher hidden on mobile — Severity 3
**Location:** `Header.tsx` line 80 (`hidden sm:block`).
**Observation:** The LanguageSwitcher only renders ≥sm. Mobile visitors who land on the Turkish default cannot switch to English without resizing. For a B2C product targeting Turkey, mobile is the primary surface.
**Fix proposal:** Show a compact (`<LanguageSwitcher compact />`, which the component already supports per line 9) variant in the mobile bar, or move to a dropdown.

### F7.4 — Locale lives in cookie, not URL — Severity 2
**Location:** `i18n.ts` lines 13‑29, `middleware.ts` lines 37‑54.
**Observation:** Locale is cookie‑based, so a Turkish user cannot share a "/?lang=en" link with a foreign colleague — the recipient lands in TR (cookie negotiated from `accept-language`). No locale prefix in the URL (`/tr/`, `/en/`). This makes deep links lossy across users and limits SEO‑per‑locale.
**Fix proposal:** Out of scope for "no new features" but worth flagging: at minimum honour a `?lang=en` query param in `middleware.ts` (set cookie if present). This is a hardening of existing behaviour.

---

## H8 — Aesthetic and Minimalist Design

### F8.1 — Three CTAs side by side on the home hero — Severity 2
**Location:** `app/page.tsx` lines 57‑68.
**Observation:** "Giriş Yap", "Hesap oluştur", "Demo'yu dene" all share the hero. The primary, secondary, ghost hierarchy is correct but cognitive load is high — three roughly equivalent actions for a first‑time visitor. The intent statement of the hero ("Demo'yu dene") is buried under two account CTAs.
**Fix proposal:** Lead with **"Demo'yu dene"** as primary (it's the lowest‑commitment path that proves value), demote login/register to a single "Hesabın var mı? Giriş yap" inline link plus a "Kayıt ol" secondary. The CTA at the bottom of the page (line 162) is already "Demo'yu dene" — make the top consistent.

### F8.2 — Results page sidebar has 4 stacked cards — Severity 2
**Location:** `app/results/[id]/page.tsx` lines 210‑247.
**Observation:** `CostDisplay`, `InspectionSummary`, "Hızlı özet" (`Row`s), damage type chips — four blocks of information one above the other, two of which (InspectionSummary + Hızlı özet) likely overlap in content.
**Fix proposal:** Audit `InspectionSummary` content vs the inline `quickSummary` block; if the same fields appear, collapse to one. No new components.

---

## H9 — Help Users Recognize, Diagnose, and Recover From Errors

### F9.1 — Login distinguishes only 401/400 vs network vs generic — Severity 3
**Location:** `app/(auth)/login/page.tsx` lines 48‑57.
**Observation:** `axios` error handling collapses 401/400 → "invalidCredentials"; everything else (403 account disabled, 429 rate‑limited) → "errorGeneric". The catalogue already defines `auth.accountDisabled`, `auth.rateLimited`, `auth.tokenExpired` (lines 211‑214). The user is left with a vague "Bir hata oluştu" when the server is actually telling them their account is disabled or they're rate limited.
**Fix proposal:** Use the existing `classifyApiError` helper (in `lib/api.ts` line 443) and branch on `kind === 'rateLimited' | 'forbidden'` to render the precise message.

### F9.2 — Backend 500 has no "retry" affordance in upload flow — Severity 3
**Location:** `app/(app)/inspect/new/page.tsx` lines 142‑155 (error banner).
**Observation:** The error banner displays the message but the only retry path is to press "İncelemeyi başlat" again — there is no explicit "Yeniden dene" button inside the banner. Users may interpret a red banner as terminal failure.
**Fix proposal:** Add a "Yeniden dene" button inside the banner (string `common.tryAgain` already exists). Same for `app/inspect/page.tsx`.

### F9.3 — Polling network error wipes prior data — Severity 3
**Location:** `lib/use-inspection-polling.ts` lines 88‑98.
**Observation:** On a transient network blip the hook sets `error` and `loading=false`, but does not retry. The results page then shows `ErrorBanner` even though the inspection has been completing fine for 30 s. The user sees an alarming "Bağlantı hatası" although the work is being done server‑side.
**Fix proposal:** Add exponential‑backoff retry (3 attempts) before bubbling the error. Keep `data` intact; only swap the banner once retries exhaust.

### F9.4 — Inspection `failed` shows only `data?.error ?? errorGeneric` — Severity 2
**Location:** `app/results/[id]/page.tsx` lines 68‑79.
**Observation:** If the backend `data.error` is a raw stack trace or an internal code, it leaks to the user. The page does have a "Tekrar dene" CTA that routes back to `/inspect` (good — provides recovery).
**Fix proposal:** Sanitize the failure message: if `data.error` matches a known prefix, swap for a friendly string; else fall back to `inspect.errors.processingFailed`.

### F9.5 — `history` demo fallback hides real network failures — Severity 3
**Location:** `app/history/page.tsx` lines 92‑100.
**Observation:** When the backend is unreachable the page silently switches to `DEMO_ITEMS` and shows a small amber banner. This is friendly for prospects but for authenticated users it masks real outages: their actual history disappears and they see fabricated demo entries that link to `/results/demo-001`, which will then 404.
**Fix proposal:** Only show demo data when `!isAuthenticated`. Authenticated users on a failed list call should see a proper "Geçmişin yüklenemedi — tekrar dene" empty state with a retry button.

---

## H10 — Help and Documentation

### F10.1 — No first‑time onboarding tour — Severity 3
**Location:** Project‑wide.
**Observation:** No coach marks, no walkthrough modal, no "İlk inceleneni nasıl başlatırsın?" tooltip. The "Tips for better results" sidebar in `/inspect` is the closest thing but it lives on a page the user has to find first.
**Fix proposal:** A single dismissable info banner on the dashboard for first‑time logged‑in users ("Hoş geldin, ilk incelemen için Yeni inceleme'ye tıkla") tied to a `localStorage` flag. Empty state on dashboard already does this implicitly (lines 117‑124, "Henüz inceleme yok — İlk incelemeni başlat") — that pattern is good and could be replicated on `/history` (already done — see line 217‑228, `EmptyState`).

### F10.2 — No KVKK / privacy notice on photo upload — Severity 4
**Location:** Both `/inspect` and `/inspect/new`.
**Observation:** Users upload photos of their cars (potentially with license plates visible) with **zero notice** about data handling, retention, or KVKK compliance. The Footer has a "Gizlilik politikası" link but the upload screen itself shows no notice. For a Turkish B2C product collecting images, this is a compliance + trust concern.
**Fix proposal:** A small text under the dropzone (or next to "İncelemeyi başlat" button): "Fotoğrafların yalnızca analiz için kullanılır ve [Gizlilik politikası]'na göre saklanır." Hyperlink to `/privacy`. Wording can live under a new `inspect.privacyNotice` key.

### F10.3 — Disclaimer "yapay zeka tahmini — kesin değil" buried — Severity 4
**Location:** `tr.json` line 349 (`inspect.result.disclaimer`).
**Observation:** The disclaimer string is excellent ("Bu rapor yapay zeka tahminidir, kesin eksper raporu değildir. Sigorta talebi için yetkili eksper raporu gereklidir."). I could not find it being rendered in `results/[id]/page.tsx` (the file does not call `t('inspect.result.disclaimer')`). If `CostDisplay` from `@arac-hasar/ui` does not surface it, it's effectively dead copy. This is the single most important trust signal for a cost‑estimate product.
**Fix proposal:** Render it directly on the results page (top of the page or directly under the cost number) as a discrete amber‑tinted box. No new copy needed.

### F10.4 — "MVP" badge in header is vague — Severity 1
**Location:** `Header.tsx` line 38; `tr.json` `common.appVersionLabel`.
**Observation:** Non‑technical users don't know what "MVP" means. They may interpret it as the product being incomplete or unreliable, which hurts conversion.
**Fix proposal:** Either remove the badge for end users and surface it only inside `/settings`, or change copy to "Beta" (more familiar) or "Erken erişim".

### F10.5 — No empty state guidance for filtered `/history` that returns zero — Severity 2
**Location:** `app/history/page.tsx` lines 82‑87 + 217‑228.
**Observation:** When filters return zero items, the same `EmptyState` ("Henüz inceleme yok") is shown — but the user might have inspections; they just filtered them out. The empty state is misleading.
**Fix proposal:** Branch the empty state: if any of `statusFilter`, `query`, `dateFrom`, `dateTo` is set, show "Filtre kriterine uyan kayıt yok" + a "Filtreleri temizle" button. Otherwise show the current "Henüz inceleme yok".

---

## Mobile / Responsive (Browser Native, not PWA)

### M1 — Touch target audit — Severity 2
**Location:** `UploadDropzone.tsx` line 144 (X "remove" buttons), `LanguageSwitcher.tsx` line 35.
**Observation:** The remove‑file X button is `p-1` (≈24×24 CSS px) — under the WCAG 2.5.5 / Apple HIG / Material recommended 44×44 px touch target. The language switcher's `px-2 py-0.5` toggles are similarly small. On a thumb‑driven mobile interaction with 20 photo thumbnails, mis‑taps will be frequent.
**Fix proposal:** Bump the X hit area: `p-1.5` with `min-h-9 min-w-9`, and add `before:absolute before:inset-[-8px]` to expand the click area beyond the visible icon. Same hit‑area extension for the language switcher.

### M2 — File picker `accept` is correct, but no `capture` for camera — Severity 2
**Location:** `UploadDropzone.tsx` lines 94‑101.
**Observation:** `accept="image/jpeg,image/png,image/webp"` is fine. There is no `capture="environment"` attribute, so on mobile browsers the file picker opens the gallery — the user has to manually back out and open the camera. Given the core use case is "take a photo of my dented car right now", camera‑first would shorten the flow significantly.
**Fix proposal:** On mobile only (detect via user agent or `(pointer: coarse)` media query), set `capture="environment"`. Or expose two buttons: "Galeriden seç" / "Kamerayı aç" — both routes can drive the same handler. Pure HTML; no JS feature changes.

### M3 — Header nav hides links and shows hamburger? — Severity 3
**Location:** `Header.tsx` lines 43‑78.
**Observation:** Protected nav items use `hidden ... sm:inline-flex` — on mobile the user sees the logo, language switcher (also hidden), user chip, logout. There is **no hamburger / drawer** to access Dashboard, Yeni inceleme, Geçmiş, Settings. Mobile authenticated users can only navigate via the Logo→/dashboard. After landing on the dashboard, they can use the in‑page "Yeni inceleme" / "Tümünü gör" links but not direct nav.
**Fix proposal:** Add a hamburger button on mobile that opens a slide‑down sheet with the same `PROTECTED_NAV` items. No new routes/features — just expose existing nav on small screens.

### M4 — Sticky sidebar on `/inspect` collapses below upload on lg breakpoint — Severity 1
**Location:** `app/(app)/inspect/new/page.tsx` line 85 (`grid gap-8 lg:grid-cols-3`).
**Observation:** Mobile and tablet stack the "Tips" sidebar **after** the dropzone, so the helpful guidelines are below the fold. Users miss them.
**Fix proposal:** On mobile, render a collapsed accordion ("Daha iyi sonuç için ipuçları ▾") **above** the dropzone, or pin a single tip ("İyi aydınlatma kullan") to the dropzone subtitle.

---

## i18n

### i1 — Locale switching does a `router.refresh()` — Severity 2
**Location:** `LanguageSwitcher.tsx` lines 14‑18.
**Observation:** Switch sets cookie + `router.refresh()`. The whole page re‑renders, but form state, scroll position, and unsaved selections (e.g. files in the dropzone) survive only because they live in component state outside the swap. For the `/inspect` page mid‑upload, this is risky — refreshing while files are selected re‑mounts the page and clears them.
**Fix proposal:** Disable the switcher (`disabled` + tooltip "Yükleme sırasında dil değiştirilemez") when `submitting === true`. Cheap, prevents data loss.

### i2 — No URL locale prefix — Severity 2
**Location:** See F7.4 above.

### i3 — `en.json` not opened, parity not verified — Severity 2
**Location:** `messages/en.json`.
**Observation:** Could not verify EN catalogue completeness in this audit. Several flows depend on en/tr parity (`auth.invalidCredentials`, `inspect.progress.*`, `inspect.errors.*`).
**Fix proposal:** Run a key‑diff check between `tr.json` and `en.json`. If any TR keys are missing in EN, the EN user sees `inspect.errors.imageTooBlurry` literally on screen.

---

## Trust Signals

### T1 — KVKK notice on upload — see F10.2 (Severity 4)
### T2 — AI disclaimer on cost — see F10.3 (Severity 4)
### T3 — "MVP" badge — see F10.4 (Severity 1)
### T4 — Anonymous result is shareable but not branded — Severity 2
**Location:** `app/results/[id]/page.tsx`.
**Observation:** "Bağlantıyı paylaş" (`inspect.result.shareLink`) is in the messages catalogue but I do not see a share button rendered. Anonymous users who want to forward the result to their insurance agent have no quick way.
**Fix proposal:** Render a "Bağlantıyı kopyala" button in the header next to the status badge. `useToast` handles the "Kopyalandı" feedback. Copy already exists.

---

## Onboarding

### O1 — No coach marks — see F10.1
### O2 — Empty states are healthy — Severity (positive)
**Location:** `dashboard/page.tsx` lines 117‑124, `history/page.tsx` lines 217‑228.
**Observation:** Both empty states correctly invite the user to `/inspect/new` with a primary button. This is good UX.
**Fix proposal:** Replicate on `/settings` → `apiKeys` empty state (string `settings.apiKeys.empty` exists).

---

## Top 5 Priority Improvements

Ranked by **(severity × audience size × frequency on the critical path)**. All five are *hardening* — they add UI surfaces around copy / flows that already exist, no new features.

| # | Improvement | Severity | Location | Why now |
|---|---|---|---|---|
| **1** | **Render the AI cost disclaimer on `/results/[id]`** — Make `inspect.result.disclaimer` visible directly under the cost number. Add a KVKK micro‑notice under the upload dropzone with a link to `/privacy`. | 4 | `app/results/[id]/page.tsx`, `app/(app)/inspect/new/page.tsx`, `app/inspect/page.tsx` | Single biggest trust gap. Strings already exist (F10.2, F10.3). |
| **2** | **Unify the two `/inspect` pages and add upload progress to the anonymous path.** Extract `<InspectUploadFlow />` shared component. Anonymous demo users currently get an inferior experience (no progress bar, no toast on failure). | 4 | `app/inspect/page.tsx` vs `app/(app)/inspect/new/page.tsx` | Removes the biggest divergence between two near‑identical files (F4.1) and fixes F1.1 in one shot. |
| **3** | **Surface localized status labels and existing progress vocabulary.** Wire `inspect.progress.*` rotation in `PendingState`, localize the history status `<select>` options, and translate the dashboard table headers. | 3 | `app/results/[id]/page.tsx`, `app/history/page.tsx`, `app/(app)/dashboard/page.tsx` | Three independent F2.3/F1.2/F4.5 bugs that all stem from forgetting to call `t()`. Pure copy wiring. |
| **4** | **Mobile: show the language switcher and a hamburger nav; enable camera capture.** Add `<LanguageSwitcher compact />` to the mobile header bar, a `<Sheet>` for protected nav links, and `capture="environment"` on the file input on mobile. | 3 | `Header.tsx`, `UploadDropzone.tsx` | Mobile is the dominant surface for a B2C "snap a photo of your car" product (M2, M3, F7.3). |
| **5** | **Better error recovery in upload and polling.** Reset progress on retry, add inline "Yeniden dene" in error banners, branch login error handling on `classifyApiError` (rate‑limit/account‑disabled), and add backoff to `useInspectionPolling` instead of bailing on first network blip. Distinguish "no items" vs "filtered to zero" on `/history`. | 3 | `app/(app)/inspect/new/page.tsx`, `app/(auth)/login/page.tsx`, `lib/use-inspection-polling.ts`, `app/history/page.tsx` | Frequency on the critical path is high — every transient failure today produces a confusing dead end (F9.1, F9.2, F9.3, F10.5). |

---

## Summary Table

| Heuristic | # Findings | Critical (4‑5) | Major (3) | Minor (1‑2) |
|---|---|---|---|---|
| H1 — Status visibility | 5 | 1 | 2 | 2 |
| H2 — Real‑world match | 4 | 0 | 2 | 2 |
| H3 — User control | 4 | 0 | 1 | 3 |
| H4 — Consistency | 5 | 1 | 2 | 2 |
| H5 — Error prevention | 5 | 0 | 2 | 3 |
| H6 — Recognition | 3 | 0 | 0 | 3 |
| H7 — Flexibility | 4 | 0 | 1 | 3 |
| H8 — Minimalist design | 2 | 0 | 0 | 2 |
| H9 — Error recovery | 5 | 0 | 4 | 1 |
| H10 — Help & docs | 5 | 2 | 1 | 2 |
| Mobile | 4 | 0 | 1 | 3 |
| i18n | 3 | 0 | 0 | 3 |
| Trust | 1 (+3 shared) | 0 | 0 | 1 |
| **Total unique** | **~50** | **4** | **16** | **30** |

The product is **architecturally solid** — `next-intl`, schema validation, auth guard, dropzone validation, results polling, error classification helpers are all in place. The gaps are almost entirely on the *last mile*: copy that exists but isn't rendered, components that diverged between two pages, mobile affordances that were never wired. Hardening (not feature work) closes the bulk of the findings.

---

**Audited:** 2026‑05‑16
**Method:** Static code + i18n catalogue review (no runtime / device testing).
**Next:** Validate the top‑5 priorities against backend capabilities (esp. anonymous result access in F4.4, KVKK retention policy in F10.2, and progress‑phase reporting in F1.2).
