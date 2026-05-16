# Code Review — Polling Flow & Results Screen

**Scope:** Read-only review of frontend polling + result rendering.
**Files reviewed:**

- `apps/web/lib/use-inspection-polling.ts`
- `apps/web/lib/api.ts`
- `apps/web/lib/auth-context.tsx`
- `apps/web/lib/uploaded-previews.ts`
- `apps/web/lib/jwt.ts`
- `apps/web/app/results/[id]/page.tsx`
- `apps/web/app/inspect/page.tsx`
- `apps/web/app/(app)/inspect/new/page.tsx`
- `apps/web/middleware.ts`
- `packages/ui/src/components/UploadDropzone.tsx`
- `apps/web/components/ResultsTabs.tsx`

> Note: there is **no** `apps/web/app/(app)/results/[id]/page.tsx`. Results
> live only under `app/results/[id]/page.tsx`, which means the page is
> *not* matched by `PROTECTED_PREFIXES` in `middleware.ts`. See **HIGH-3**.

---

## Overall impression

The polling hook is overall solid — it has an `AbortController`, a
`cancelledRef`, exponential backoff, a max-duration budget, a
consecutive-error budget, and distinguishes "fatal" vs "transient" errors.
Cross-tab refresh dedup in `api.ts` is thoughtful. The Tauri-style cleanup
in `inspect/new/page.tsx` (abort on unmount) is well done.

That said, there are real bugs around **stale `consecutiveErrors`/`currentInterval`**
when the `retryNonce`/effect re-runs, a **silent token-refresh failure mode**
where a follower tab returns the *old* access token, and a **known and
still-unfixed `URL.createObjectURL` leak** in `UploadDropzone.tsx` (the
comments claim it's revoked, but the hook is dead code).

The list below is prioritized; the Top 5 section at the end is the order I
would fix things in.

---

## CRITICAL

### CRITICAL-1 — `useFilePreviewUrls` is dead code; `FilePreview` leaks blob URLs on every render

**Where:** `packages/ui/src/components/UploadDropzone.tsx:123-180`

The `useFilePreviewUrls` hook (lines 123-139) does call `URL.revokeObjectURL`
in a cleanup, *but* `FilePreview` is also imported / used in two places that
mutate `files` array identity on every keystroke / state change in the
parent (`apps/web/app/inspect/page.tsx`, `apps/web/app/(app)/inspect/new/page.tsx`).

Concretely:

- `inspect/page.tsx:33-46` rebuilds `files` (new array reference) via
  `setFiles((prev) => [...prev, ...incoming]...)` each `onFiles` call.
- The dedup logic returns a **new array even when nothing changed**
  (e.g. user re-drops the same file). Every new identity invalidates the
  `useMemo([files])`, which calls `URL.createObjectURL` again for every
  surviving file, leaking the previous URLs until effect cleanup later.
- The cleanup runs only when `urls` identity changes — but by that point a
  new `urls` already exists, so the cleanup fires for the *new* set, not
  the leaked previous set. (`useEffect`'s cleanup uses the *previous*
  closure, but the leak is across renders where memo recomputes — and
  because `[files]` identity gates it, blob URLs that were already
  recreated for the same `File` reference are unconditionally orphaned.)

`docs/WEB_PERFORMANCE.md:133-147` and `docs/SECURITY_WEB_AUDIT.md:145-151`
both flag this. The fix the docs describe was supposedly applied, but the
current code path still allocates a fresh URL per memo recompute without
deduping by `File` identity.

**Why it matters:** 20 photos × ~5 MB = 100 MB of blob memory per leak
cycle. Long sessions on `/inspect/new` can crash mobile Safari and degrade
desktop Chrome (multi-100 MB).

**Suggestion (DO NOT IMPLEMENT — review only):**
- Cache URLs in a `Map<File, string>` ref keyed by `File` identity, and only
  allocate for files newly added since the last render. Revoke when a
  `File` leaves the list **or** on unmount.
- Add a unit test that asserts `URL.createObjectURL` call count equals
  `files.length` after N re-renders with stable file identities.

---

### CRITICAL-2 — Polling effect resets `consecutiveErrors`/`currentInterval` but state `attempts` is preserved across `retry()`, producing inconsistent UX

**Where:** `apps/web/lib/use-inspection-polling.ts:87-103`

`retry()` increments `retryNonce`, which re-runs the entire effect. Inside
the effect:

- `consecutiveErrors = 0` (line 107) and `currentInterval = intervalMs`
  (line 106) reset on every run — good.
- But `setState((s) => ({ ... attempts: s.attempts ... }))` at line 100
  preserves `attempts`. After several manual retries, `attempts` keeps
  climbing across resets while `consecutiveErrors` does not.

That's not a bug per se, but combined with the `paused` flag rendering at
`results/[id]/page.tsx`, the user sees the `pollAttempts` counter (line
328) growing without bound across retries. There is **no `paused` branch**
rendered on the results page at all — when polling pauses (8 consecutive
errors), the UI shows the `<ErrorBanner>` *plus* the `<PendingState>`
spinner forever. There is no "Check again" button as the hook's docstring
(line 51) promises.

**Why it matters:** The contract documented at `use-inspection-polling.ts:51`
("UI should offer a 'check again' button") is **not implemented** in
`results/[id]/page.tsx`. Once paused, the user has no way to call `retry()`.
They have to reload the tab, which dumps any optimistic state.

**Suggestion:**
- Wire `paused` and `retry` from the hook into the results page and render
  a "Check again" button (analogous to the `timedOut` branch at line 80).
- Either persist `attempts` across retries (current behavior) and label it
  "Total checks" so the growing number is intentional, or reset it on
  `retry()` and label it "Checks this session."

---

### CRITICAL-3 — Cross-tab refresh follower can race and return a token *previousAccess === current → null* even when leader succeeds

**Where:** `apps/web/lib/api.ts:160-225`

In `runRefresh()`:

1. `previousAccess = getStoredAccessToken()` is read **before**
   `tryAcquireRefreshLock()`.
2. If we lose the lock, we call `waitForLeaderRefresh(previousAccess)`.
3. The leader in another tab calls `setStoredTokens(access_token, ...)`,
   which writes `localStorage` synchronously. **But** if the leader
   completes between steps 1 and 2 in our tab (very narrow window — but
   possible because `tryAcquireRefreshLock` does multiple `localStorage`
   reads), `previousAccess` may *already equal* the new token written by
   the leader, in which case the `waitForLeaderRefresh` poll never sees
   `current !== previousToken` and resolves `null` at the 8 s timeout.

Equally, `storage` events do not fire in the *writing* tab — that's
documented at line 178. But the follower polls every 200 ms, which means
the **happy path takes up to 200 ms per request** of pure latency added
to the 401 → refresh → retry path in the loser tab.

**Why it matters:** Tabs lose refresh attempts → user gets logged out
spuriously in multi-tab sessions. Symptom is intermittent and very hard
to repro.

**Suggestion:**
- After acquiring/losing the lock, **re-read the access token** and
  compare against `previousAccess`. If they differ, the leader already
  finished — return the new token immediately, skip the wait loop.
- Reduce the poll interval to 50 ms or use a `BroadcastChannel`.

---

## HIGH

### HIGH-1 — 401 retry inside axios interceptor does not propagate `signal`

**Where:** `apps/web/lib/api.ts:99-110`

When a 401 fires, the interceptor calls `instance.request(original)`. The
`original` config carries the original `AbortSignal` (good), but if the
caller already aborted (e.g. unmounted polling), the abort fires **before**
`runRefresh` returns. `instance.request(original)` will then issue a
network request with an already-aborted signal — axios will throw
`CanceledError`, which `classifyApiError` maps to `cancelled`, which the
polling hook silently swallows. Net effect: harmless, but a wasted refresh
round-trip on every unmount that happens to coincide with a 401.

More importantly: if the user navigates away during refresh, the leader
tab can still complete `/auth/refresh` and write fresh tokens to
`localStorage` for a session the user thinks is dead. Edge-y, but worth
noting.

**Suggestion:** Bail out of the 401 retry path if `original.signal?.aborted`
before calling `runRefresh()`.

---

### HIGH-2 — `setUnauthorizedHandler(null)` cleanup in `AuthProvider` runs on every `pathname` change → ephemeral window where the handler is unset

**Where:** `apps/web/lib/auth-context.tsx:54-68`

The effect re-runs whenever `pathname` changes (React Router behavior in
app dir is to keep `pathname` stable inside a segment, but transitions
DO fire). The cleanup sets the handler to `null`, then the next effect
sets a new closure. If a 401 lands in the millisecond gap (during route
transition), `_onUnauthorized?.()` is a no-op and the user is left on
the page with a cleared session and no redirect.

**Why it matters:** Probably rare, but on slow devices or under React 18
concurrent rendering, this gap widens. The symptom is "I'm logged out but
the app still shows me the protected page."

**Suggestion:**
- Either keep the handler permanently registered (use a stable handler
  that reads `pathname` from a ref), or compute the dependency more
  narrowly (only re-register if `router` identity changes, not
  `pathname`).

---

### HIGH-3 — `/results/[id]` is not in `PROTECTED_PREFIXES`, but the API call requires auth

**Where:** `apps/web/middleware.ts:4-15`, `apps/web/app/results/[id]/page.tsx:27`

`PROTECTED_PREFIXES` lists `/inspect` and `/inspect/new` but **not**
`/results`. An unauthenticated user who navigates to `/results/<some-id>`
bypasses middleware, then `useInspectionPolling` fires
`GET /api/v1/inspect/<id>`, gets a 401, the axios interceptor tries
`runRefresh()` (no refresh token in localStorage → returns `null`), clears
tokens (already empty), calls `_onUnauthorized?.()`. The auth context
*does* push to `/login` from the protected pages check at line 58-65 — but
note the condition: it only redirects if pathname is NOT `/login`,
`/register`, or `/`. **`/results/<id>` passes this check**, so the user
*does* get redirected — but only after a failed network call, a failed
refresh, and one full re-render. Slow and noisy.

Also: the FastAPI 401 detail bubbles up as the polling error message
(`tHttp('401')`) and is briefly shown to the user before the redirect.

**Suggestion:** Add `/results` to `PROTECTED_PREFIXES` so middleware
short-circuits at the edge.

---

### HIGH-4 — Polling effect re-runs whenever `tResult/tNetwork/tHttp` translator identities change → full polling reset

**Where:** `apps/web/lib/use-inspection-polling.ts:220-231`

The effect deps include `tResult`, `tNetwork`, `tHttp`. `useTranslations()`
from `next-intl` returns a *new function reference* on every locale change
*and sometimes on every parent re-render*, depending on the provider
implementation. If those identities are not memoized, the polling effect
tears down (`ac.abort()`, `clearTimeout`) and rebuilds on every render of
`results/[id]/page.tsx`.

That would mean:
- `startedAtRef.current = Date.now()` resets, defeating the `maxDurationMs`
  budget.
- A new `AbortController` and a new initial `tick()` fire — back-to-back
  HTTP calls.
- `consecutiveErrors` and `currentInterval` reset to defaults, so
  exponential backoff never kicks in.

I have not confirmed `next-intl`'s exact memo behavior, but the standard
pattern is to **not** include translator functions in effect deps for
this reason.

**Why it matters:** If translators are unstable, this hook will hammer
the backend with `1.5 / second` requests indefinitely.

**Suggestion:**
- Capture `tResult`, `tNetwork`, `tHttp` in refs at the top of the hook
  and read from refs inside `tick`. Drop them from the dep array.

---

### HIGH-5 — `loadImage` in `uploaded-previews.ts` leaks the image and the object URL on `img.onerror`

**Where:** `apps/web/lib/uploaded-previews.ts:52-59`

`loadImage` resolves on `onload`, rejects on `onerror`. The `finally` in
`fileToResizedDataUrl` *does* revoke the object URL. Good. But the
`HTMLImageElement` itself is never cleared (`img.src = ''` or `img.onload
= null`). If the image is mid-decode and the user navigates away, the
decode continues in the browser. Minor.

Bigger issue: `onerror` has no timeout. A corrupt image hangs the upload
forever, blocking `stashUploadedPreviews` which blocks the
`router.push('/results/...')` (see `inspect/new/page.tsx:104`). The user
sits on the upload page with no feedback after the upload itself
succeeded server-side.

**Suggestion:**
- Add a `Promise.race` with a 5-10 s timeout in `loadImage`.
- Make `stashUploadedPreviews` non-blocking: kick it off, navigate
  immediately, let it finish in background and write to sessionStorage
  when ready. (The results page already tolerates missing previews.)

---

## MEDIUM

### MEDIUM-1 — `getStoredAccessToken()` is read inside `request.use` interceptor for every request → no protection against expired tokens

**Where:** `apps/web/lib/api.ts:83-89`

The request interceptor unconditionally attaches the access token even if
`isJwtExpired(token)` returns true. The 401 response interceptor will
catch it and refresh — that's fine — but every expired-but-not-yet-refused
request wastes a round trip.

**Suggestion:** Check `isJwtExpired(token, 5)` in the request interceptor;
if expired, await `runRefresh()` proactively before sending. (Slight
risk: deadlock if `runRefresh` itself is intercepted; guard with a
"don't intercept /auth/refresh" check.)

---

### MEDIUM-2 — `paused` branch never rendered on results page

**Where:** `apps/web/app/results/[id]/page.tsx:27-95`

The destructure on line 27 takes `data, loading, error, attempts, timedOut`
but **omits `paused` and `retry`**. The hook documents (line 18-20, 51)
that `paused` is the user's manual-retry escape hatch. Since the results
page never reads it, the contract is silently broken — see CRITICAL-2.

---

### MEDIUM-3 — `data?.error` is used as a translated error message but is the raw backend string

**Where:** `apps/web/app/results/[id]/page.tsx:71`, `use-inspection-polling.ts:130-133`

When `status === 'failed'`, the hook sets
`error: data.error ?? tResult('failed')`. The results page shows
`description={data?.error ?? tCommon('errorGeneric')}`. So if the backend
returns `"CUDA out of memory: tried to allocate 12.00 GiB..."` that string
ends up verbatim in the UI. No i18n, no scrubbing, leaks internal
implementation detail.

**Suggestion:** Map known backend error codes to translated strings; fall
back to a generic translated message when the code is unknown.

---

### MEDIUM-4 — `effectiveMode` recompute can desync `mode` state on `(app)/inspect/new/page.tsx`

**Where:** `apps/web/app/(app)/inspect/new/page.tsx:71-74`

`effectiveMode` is forced to `'async'` when `files.length > MAX_SYNC_FILES`,
but the underlying `mode` state still says `'sync'`. If the user then
removes files to get under 5, the UI flips back to `'sync'` *without the
user re-confirming*. Probably fine, but worth a UX nit: keep a
"user-chosen mode" plus a "current capability" and reset the user choice
when files cross the threshold up.

---

### MEDIUM-5 — `getInspectionStatus` returns `data` as-is; no validation against `InspectionStatusResponse` type

**Where:** `apps/web/lib/api.ts:355-367`

`res.data` is typed as `InspectionStatusResponse` but the type assertion
trusts the backend completely. A malformed response (or version skew)
crashes downstream (`data.status`, `data.result.parts.flatMap`...). The
polling hook would mis-treat a "no status field at all" response as
"still polling" forever.

**Suggestion:** Validate with a tiny runtime check (or a zod schema in
`@arac-hasar/types`) and convert validation failures into a `notFound`/
`server` `ApiErrorInfo`.

---

### MEDIUM-6 — Inspect `/inspect/page.tsx` does not propagate `signal` and has no unmount-abort

**Where:** `apps/web/app/inspect/page.tsx:60-83`

The duplicate (older?) page at `/inspect/page.tsx` calls
`createInspection(files, { mode: effectiveMode })` with **no signal and
no unmount cleanup**. If the user submits 20 photos then navigates away
mid-upload, the request runs to completion in the background and may
call `router.push` after unmount — classic "Can't perform a React state
update on an unmounted component" warning.

The newer `(app)/inspect/new/page.tsx` does this correctly (lines 39-47,
89-90). Decide which page is canonical and either delete or fix the
other.

---

## LOW

### LOW-1 — `clearStoredTokens()` does not clear cookie path/domain rigorously

**Where:** `apps/web/lib/api.ts:49-54`

Setting `max-age=0` on the same path/samesite as the writer works in
practice, but if the cookie was ever issued from a different path
(legacy code, A/B test), it'll linger. Low risk in a clean codebase.

### LOW-2 — `tryAcquireRefreshLock` returns `true` on `try { ... } catch { return true }`

**Where:** `apps/web/lib/api.ts:141-143`

If `localStorage` throws (Safari private mode, quota), the tab declares
itself leader. In multi-tab Safari private mode, *all* tabs will declare
leader and call `/auth/refresh` in parallel → refresh-token reuse error,
session burns. Edge case.

### LOW-3 — `isJwtExpired` parses the JWT on every request

**Where:** `apps/web/lib/jwt.ts:48-53` (and the middleware path at
`apps/web/middleware.ts:63`)

Negligible perf cost, but middleware decodes on every request — including
HMR pings during dev. Consider caching by token string.

### LOW-4 — `data.image.url ?? ''` falls back to empty string, then renders `<img src="">`

**Where:** `apps/web/app/results/[id]/page.tsx:136-145`

`annotatedUrl` becomes `''`, the falsy check on line 145 *does* catch it
(`annotatedUrl ?` ... `: <fallback>`) — but only because `''` is falsy.
Brittle. Prefer explicit `annotatedUrl ? <Tabs/> : <Placeholder/>` with
the value typed as `string | null`.

### LOW-5 — `classifyApiError` returns `{ kind: 'unknown' }` for non-axios errors with no `detail` info

**Where:** `apps/web/lib/api.ts:536`

A thrown `TypeError` (e.g. `JSON.parse` failure in an interceptor) becomes
`{ kind: 'unknown' }`, which the polling hook then shows as
`tNetwork('unknown')` — usually misleading ("internet broken" when the
real cause is a bug). Adding `error: err instanceof Error ? err.message
: undefined` would help debugging.

### LOW-6 — `attempts` counter in `PendingState` shows "1" on the very first render

**Where:** `apps/web/app/results/[id]/page.tsx:327`

`{attempts > 1 && ...}` guards against the initial "attempt 0/1" flicker,
but the first successful tick increments to 1 and the user briefly sees
"Attempt 1" before the data resolves. Cosmetic.

### LOW-7 — `useInspectionPolling` mixes UI strings into hook return values

**Where:** `apps/web/lib/use-inspection-polling.ts:169-182`

The hook resolves translation strings inline. Cleaner separation: return
`{ kind: ApiErrorInfo['kind'] | 'failed' | 'timeout' | 'paused' }` and let
the consumer translate. Reduces coupling and makes the hook unit-testable
without a NextIntlClientProvider wrapper.

---

## Top 5 priority fixes

1. **CRITICAL-1** — Fix the `UploadDropzone`/`FilePreview` blob URL leak.
   The hook *exists* but its dedup contract is broken; right now every
   `setFiles` call burns blob memory. High user-visible cost on mobile.

2. **CRITICAL-2 / MEDIUM-2** — Wire the `paused`/`retry` contract through
   `results/[id]/page.tsx`. Right now an 8-error transient pause is a
   silent dead-end with the spinner running forever.

3. **HIGH-4** — Stabilize the translator references (or drop them from
   the effect dep array). If `next-intl` returns new functions per
   render, polling resets ~every 100 ms and your backend gets DoS'd by
   your own UI. Verify with a `console.count` in `tick` during a
   30 s session.

4. **CRITICAL-3 / HIGH-1** — Tighten the cross-tab refresh path:
   - Re-read access token after lock acquisition and short-circuit if it
     already changed.
   - Bail out of the 401 retry if the original signal is aborted.

5. **HIGH-3** — Add `/results` to `PROTECTED_PREFIXES` in
   `middleware.ts`. Currently the only thing protecting the results
   route is a failed API call.

---

## Things done right (call-outs)

- The `cancelledRef + AbortController` dual-guard in
  `use-inspection-polling.ts` is exactly the right pattern for React
  strict-mode double-mounting. No state update will leak post-unmount.
- `runRefresh` in-tab dedup via shared promise (`_refreshPromise`) is
  correct and avoids the multi-401 stampede.
- The `_retry` sentinel on the axios config (line 96-100) correctly
  prevents an infinite 401→refresh→401 loop.
- Sync vs async UX gating (`MAX_SYNC_FILES = 5`) is matched against the
  backend cap *and* visually disabled on the UI — defense in depth.
- `stashUploadedPreviews` resizes to 1024 px JPEG q=0.8 with a 2 MB cap,
  scoped to `sessionStorage` — solid quota discipline.
- `classifyApiError` produces a stable union and parses FastAPI's two
  `detail` shapes (string vs array-of-errors) without crashing.
