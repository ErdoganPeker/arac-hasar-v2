# AUTH / Refresh Token Review — Polling "İnternet Yok" Root-Cause Analysis

**Wave**: Security Engineer (read-only)
**Date**: 2026-05-16
**Scope**: JWT refresh flow vs. 20-minute async inspection polling that fails
after 7 attempts with a network-style "internet down" error.
**Sibling agents**: Frontend Developer (apps/web), Backend Architect
(services/backend) — they will apply the fixes. This document is recommendation-only.

---

## 1. Executive Summary

The polling hook stops after 8 **consecutive** errors (config
`MAX_CONSECUTIVE_ERRORS = 8` in `apps/web/lib/use-inspection-polling.ts:111`)
and surfaces a translated `errors.network.offline` message — the user reads
that as "internet yok". Reproduction reports say it hits the wall after
~7 attempts. That count matches a single failure mode:

> **A refresh-token rotation race burned the user's refresh token between
> polling ticks, and every subsequent tick gets a hard 401 that the
> interceptor cannot recover from. After 1–2 ticks the request bubbles up
> as 401 → `info.kind === 'unauthorized'` → counted as a consecutive error.
> Eight of those = pause + "no internet" message.**

Three auth-side root causes plausibly produce that pattern. They can also
**stack**: e.g. JWT_SECRET_KEY being random per-process makes every restart
look like a refresh race to the client.

---

## 2. Top 3 Auth Root Causes (Ranked)

### Cause #1 — Refresh-token rotation race (Critical, highest probability)

**Pattern.** Each successful `/auth/refresh` issues a *new* access **and a
new refresh token** (`services/backend/auth.py:433` returns
`_build_token_pair(...)` which calls `create_refresh_token` again at
`services/backend/auth.py:328`). The web client overwrites the refresh in
localStorage at `apps/web/lib/api.ts:215`:

```ts
setStoredTokens(access_token, refresh_token ?? refresh);
```

Backend currently does **not** maintain a refresh-token allowlist /
revocation table — `verify_token(..., expected_type="refresh")` only checks
signature + expiry + type. Practically that means rotation is *implicit*:
any in-flight request still carrying the previous refresh token is accepted
as long as it hasn't expired. So today the rotation is forgiving on the
backend.

**But the failure mode is on the client.** Two writers can stomp on
localStorage between tabs / between in-tab restarts:

1. Tab A starts polling. Access expires at minute 15. Interceptor catches a
   401, calls `runRefresh()`.
2. Tab B (e.g. inspection list page open in a second tab) hits its own 401
   in the same window. It enters `runRefresh()` independently.
3. The lock in `tryAcquireRefreshLock()` (api.ts:123–144) is a
   **non-atomic check-then-write** on `localStorage` — explicitly
   acknowledged in the inline comment at api.ts:135–140. Both tabs can
   declare themselves leader if their writes interleave; both then POST
   `/auth/refresh` with the same refresh token.
4. Both succeed (backend doesn't single-use it), each writes a *different*
   `(access, refresh)` pair to localStorage. The interceptor's
   `_refreshPromise` returned to its tab is the access **it** got — but the
   storage now reflects whichever write landed last. The other tab's
   subsequent `Authorization: Bearer …` carries an access that belongs to a
   token-family the user no longer holds the matching refresh for.
5. Next 401 in either tab triggers `runRefresh()` again; both tabs now
   read whichever refresh won the last write. If the backend ever adds
   single-use refresh (recommended below), the loser is immediately
   invalidated and the polling tab gets a permanent 401 stream.

**Evidence in code:**

| File | Line | Issue |
|------|------|-------|
| `apps/web/lib/api.ts` | 28–30 | `REFRESH_LOCK_TTL_MS = 10_000`, but lock is just a localStorage key — no `Web Locks API`, no `BroadcastChannel` ack, no compare-and-swap. |
| `apps/web/lib/api.ts` | 135–140 | Comment admits: "second writer in another tab overwrites us — but we'll detect that when our refresh response either succeeds or fails". This is a TOCTOU race. |
| `apps/web/lib/api.ts` | 193–225 | `runRefresh()` follower path waits via `waitForLeaderRefresh()` with a `REFRESH_FOLLOWER_TIMEOUT_MS = 8_000` fallback poll. If both tabs think they are leader, no follower waits and both call `/auth/refresh`. |
| `apps/web/lib/api.ts` | 215 | `setStoredTokens(access_token, refresh_token ?? refresh)` — the *second* tab to write wins, and the first tab's `_refreshPromise` already resolved against the now-overwritten access. |
| `services/backend/auth.py` | 420–436 | `/auth/refresh` does not blacklist or rotate-out the consumed refresh token — race becomes silent in dev but lethal once revocation is enabled. |

**Why it shows as 7–8 attempts.** Once `original._retry` is set
(api.ts:100), the interceptor will not refresh a second time for that same
in-flight request. So a single 401 on a polling tick can spawn one refresh
attempt; if it produces an invalid access, the *next* polling tick is the
first one that fails outright, the *one after that* triggers another
`runRefresh()` (because `_refreshPromise` is null again), and so on. Each
of those is one increment of `consecutiveErrors`. Eight ticks at the
backed-off interval (1.5× → up to 8s) ≈ 50 s, which lines up with the
~minute-long stall users describe.

**Fix owners**: Frontend Developer (client-side dedup primitives) + Backend
Architect (refresh-token revocation table).

---

### Cause #2 — `JWT_SECRET_KEY` is unset; each backend restart invalidates *all* tokens (Critical, deterministic)

**Pattern.** `security.py:84` reads `JWT_SECRET_KEY` from env; at line 117
the effective secret falls back to **`secrets.token_urlsafe(48)` — a fresh
random value per Python process** when the env var is empty. `_validate_config()`
(lines 97–113) only *warns* in `ENVIRONMENT=development`; it does not
hard-fail.

Verified that `services/backend/.env` **does not contain**
`JWT_SECRET_KEY` (`grep JWT_SECRET_KEY services/backend/.env` returns
empty). So every uvicorn restart (test runs, watchdog reload, container
restart) re-rolls the secret and **every existing access *and* refresh token
becomes signature-invalid simultaneously**.

**Symptom path:**
1. User logs in → tokens issued with secret S1.
2. User starts 20-minute polling.
3. Developer restarts backend (or `--reload` triggers on file save).
4. Polling tick hits backend → 401 ("invalid or expired token").
5. Interceptor calls `/auth/refresh` with old refresh token → also 401
   (signature mismatch).
6. `runRefresh()` returns `null` → `clearStoredTokens()` →
   `_onUnauthorized?.()` → redirect to `/login`.

Wait — the redirect should fire, but it only redirects from protected
paths (`auth-context.tsx:58–66`). On the inspection-detail page it
**does** redirect, so the user sees a login page rather than "no internet".
However, if the redirect is racing with the polling effect (likely), some
ticks fire after `clearStoredTokens()` but before the redirect navigates
away — those ticks throw a generic axios error (no `Authorization` header
set on the new request because `getStoredAccessToken()` returns `null`),
hit a 401, the interceptor sees no refresh token (because we cleared it),
and returns. Polling counts that as a consecutive error. After 8 → pause +
"internet yok".

**Evidence:**

| File | Line | Issue |
|------|------|-------|
| `services/backend/security.py` | 117 | `_EFFECTIVE_JWT_SECRET = JWT_SECRET_KEY or secrets.token_urlsafe(48)` — random fallback. |
| `services/backend/security.py` | 97–113 | `_validate_config()` only warns in dev. |
| `services/backend/.env` | — | Missing `JWT_SECRET_KEY` entirely. |
| `apps/web/lib/api.ts` | 106–108 | After failed refresh: `clearStoredTokens(); _onUnauthorized?.()` — tokens cleared synchronously, redirect navigation is async. |

**This was flagged in the previous Security wave. Restating because it is
the single most likely cause of the polling failure during developer
testing** — the user reported "ben test ederken oluyor", i.e. exactly the
session class where backend restarts are frequent.

**Fix owner**: Backend Architect (DevOps surface).

---

### Cause #3 — Access TTL (15 min) is shorter than polling window (~20 min); refresh is mandatory and unprotected (High)

**Pattern.** `security.py:86`: `ACCESS_TOKEN_MINUTES = 15`. The polling
hook's max duration is `180_000 ms = 3 min` (`use-inspection-polling.ts:30`,
"large enough for 20-image async batches"), but real workloads with 20+
images on a single GPU finish closer to 5–20 minutes (per project notes
about RTX 5050 Laptop and async queue).

So either:
- Polling duration ≤ access TTL → no refresh needed during polling. This is
  the *intended* state for the current 3-minute cap.
- Polling duration > access TTL → at least one refresh occurs mid-poll →
  exposes Cause #1 (race) every single time the user navigates between
  tabs or has a stale `arac_hasar_refresh_lock` from a crashed tab.

The hook's 8-error budget combined with backoff (1.5×, max 8 s) absorbs
~6 ticks before tripping the pause. A single refresh stall ≥ axios timeout
(60 s, api.ts:79) would consume ~7 of those slots back-to-back — matching
the "7 attempts" symptom precisely.

**Secondary concern — refresh endpoint has no rate limit.**
`/auth/refresh` (`services/backend/auth.py:415`) does **not** carry a
`@limiter.limit(...)` decorator. Compare to `/auth/login` at line 369,
which has `@limiter.limit("5/minute", ...)`. Implications:

- **Attacker:** if a refresh token leaks (XSS, log, browser ext), the
  attacker can mint unlimited access tokens silently. There is no
  per-IP/per-token brake.
- **Self-DoS during the race in Cause #1:** if both tabs busy-loop on
  failed refresh (e.g. when single-use rotation lands), they hammer the
  endpoint with no server-side backpressure, masking the root cause in
  load logs.

**Evidence:**

| File | Line | Issue |
|------|------|-------|
| `services/backend/security.py` | 86 | `ACCESS_TOKEN_MINUTES = 15` |
| `apps/web/lib/use-inspection-polling.ts` | 30 | `maxDurationMs = 180_000` — too short for 20-image async, callers likely override upward. |
| `services/backend/auth.py` | 415–436 | `/auth/refresh` has no rate limit decorator. |
| `apps/web/lib/api.ts` | 79 | axios `timeout: 60_000` — single refresh stall consumes one full minute of budget. |

**Fix owners**: Backend Architect (rate limit) + Frontend Developer
(do not force refresh during polling — see prescription below).

---

## 3. Multi-Tab Race Evidence

**File: `apps/web/lib/api.ts`**

The unsafe sequence is in `tryAcquireRefreshLock()`:

```ts
// api.ts:123-144
function tryAcquireRefreshLock(): boolean {
  if (!isBrowser()) return true;
  try {
    const now = Date.now();
    const raw = localStorage.getItem(REFRESH_LOCK_KEY);   // [A] READ
    if (raw) {
      const ts = parseInt(raw, 10);
      if (Number.isFinite(ts) && now - ts < REFRESH_LOCK_TTL_MS) {
        return false;
      }
    }
    localStorage.setItem(REFRESH_LOCK_KEY, String(now));   // [B] WRITE
    return localStorage.getItem(REFRESH_LOCK_KEY) === String(now); // [C] RE-READ
  } catch {
    return true;
  }
}
```

Race timeline (both tabs in the same browser, same origin, same
localStorage partition):

```
t0   TabA: READ  REFRESH_LOCK_KEY  → null
t1   TabB: READ  REFRESH_LOCK_KEY  → null
t2   TabA: WRITE "1000"            (Date.now() ≈ 1000)
t3   TabB: WRITE "1001"            (Date.now() ≈ 1001)
t4   TabA: RE-READ                 → "1001"  ❌ "isLeader = false"  → follower path
t5   TabB: RE-READ                 → "1001"  ✅ "isLeader = true"   → POST /refresh
t6   TabA: waitForLeaderRefresh    → polls TOKEN_STORAGE_KEY for change
```

That's the *good* branch. The *bad* branch:

```
t0   TabA: READ  null
t2   TabA: WRITE "1000"
t3   TabA: RE-READ "1000"          ✅ leader, POST /refresh starts
t4   TabB: READ  "1000"
t5   TabB: now - 1000 < 10_000 → return false  ✅ follower
                                                   (this is the safe case)

…but if TabB runs t4 BEFORE TabA's t2 write is observable across the
same-origin storage partition (which is fully synchronous in practice but
NOT atomic with respect to two parallel JS tasks scheduled across
threads — service worker, web worker, or Chromium's BackForwardCache):

t0   TabA: READ  null
t0'  TabB: READ  null
t1   TabA: WRITE "1000"
t1'  TabB: WRITE "1001"            ← stomps TabA
t2   TabA: RE-READ "1001"  → follower (waits forever for a refresh TabA itself would have done)
t2'  TabB: RE-READ "1001"  → leader, POST /refresh

Outcome: only TabB actually refreshes. TabA's waitForLeaderRefresh
(api.ts:160-191) polls localStorage every 200 ms for up to 8 s. If TabB
finishes in time, TabA gets the token. If TabB crashes mid-refresh (e.g.
the refresh request times out at 60 s, TabA's wait timed out at 8 s
already), TabA returns null → clearStoredTokens → "logged out".
```

**The critical defect:** localStorage writes are synchronous *within a tab*
but the JS engine in TabB has no happens-before relationship to writes in
TabA outside of the `storage` event, which **does not fire in the writing
tab**. So step [C]'s re-read in api.ts:140 is not a true CAS — it cannot
detect a leader/follower flip that happens in the same event-loop tick on a
sibling tab.

**Mitigation:** browsers ship the **Web Locks API** (`navigator.locks`)
specifically for this. It is supported in Chrome 69+, Edge 79+, Firefox 96+,
Safari 15.4+ — i.e. everywhere this app runs.

---

## 4. Multi-Tab Safe Pattern (recommendation snippet)

The fix below is illustrative for Frontend Developer to integrate into
`apps/web/lib/api.ts`. **Do not apply from this document — owner: Frontend
Developer.**

```ts
// apps/web/lib/api.ts — replacement for tryAcquireRefreshLock / runRefresh

const REFRESH_LOCK_NAME = 'arac-hasar:refresh-token';
const REFRESH_BROADCAST = 'arac-hasar:auth';

type RefreshMsg =
  | { type: 'refreshed'; access: string }
  | { type: 'refresh-failed' };

function broadcast(msg: RefreshMsg) {
  try {
    new BroadcastChannel(REFRESH_BROADCAST).postMessage(msg);
  } catch {
    /* old browser — fall back to storage event listeners */
  }
}

async function runRefresh(): Promise<string | null> {
  // In-tab dedup (unchanged).
  if (_refreshPromise) return _refreshPromise;
  const refresh = getStoredRefreshToken();
  if (!refresh) return null;

  _refreshPromise = (async () => {
    // Web Locks API is an exclusive cross-tab mutex on this origin.
    // Only ONE tab in the browser will enter the callback at a time.
    return navigator.locks.request(REFRESH_LOCK_NAME, { mode: 'exclusive' }, async () => {
      // Inside the lock: re-check whether another tab already refreshed
      // while we were queueing for it. If so, use that fresh access token.
      const current = getStoredAccessToken();
      if (current && !isJwtExpired(current, 5)) {
        return current;
      }

      try {
        const res = await axios.post<{ access_token: string; refresh_token?: string }>(
          `${API_URL}/auth/refresh`,
          { refresh_token: getStoredRefreshToken() }, // re-read, may have been rotated
          { timeout: 10_000 }, // shorter than the 60s default to fail fast
        );
        const { access_token, refresh_token } = res.data;
        setStoredTokens(access_token, refresh_token ?? refresh);
        broadcast({ type: 'refreshed', access: access_token });
        return access_token;
      } catch {
        broadcast({ type: 'refresh-failed' });
        return null;
      }
    });
  })().finally(() => {
    _refreshPromise = null;
  });

  return _refreshPromise;
}

// Optional: listen for refreshes done by sibling tabs so we don't have to
// even open /auth/refresh ourselves when an access token is < 1 min old.
if (typeof window !== 'undefined' && 'BroadcastChannel' in window) {
  new BroadcastChannel(REFRESH_BROADCAST).onmessage = (e: MessageEvent<RefreshMsg>) => {
    if (e.data?.type === 'refresh-failed') {
      clearStoredTokens();
      _onUnauthorized?.();
    }
    // 'refreshed' path: setStoredTokens in the leader already wrote
    // localStorage; the storage event in this tab will pick it up.
  };
}
```

**Why this is correct:**

- `navigator.locks.request(name, { mode: 'exclusive' }, fn)` is an
  origin-scoped mutex guaranteed by the browser. No TOCTOU.
- Re-read access token *inside* the lock — handles the "we queued for the
  lock, but tab B already refreshed for us" case in O(1) instead of
  re-hitting the server.
- `BroadcastChannel` is for **negative** signals (failure → log out
  everywhere). The positive case still uses the `storage` event because
  that's what the existing `waitForLeaderRefresh` polled.
- 10 s axios timeout on the refresh call so a stalled refresh does not
  consume 60 s of the polling budget.

**Fallback if `navigator.locks` is unavailable**: keep current code path
but gate it behind `if (!('locks' in navigator))`. The few users on
Firefox < 96 / Safari < 15.4 keep today's behavior. No regression.

---

## 5. Polling-Specific Auth Hardening Recommendations

These are independent of the multi-tab fix and reduce the chance of
polling ever hitting the auth layer at all.

### 5a. Long-lived polling token (server-issued, short scope)

When `/api/v1/inspect` returns an `inspection_id`, also issue a *scoped*
JWT bound to that inspection and the user:

```python
# backend pseudo-code — Backend Architect to design
{
  "sub": user_id,
  "scope": "polling:read",
  "inspection_id": "abc-123",
  "exp": now + 30 minutes,  // matches the worst-case wall budget
  "type": "polling"
}
```

The frontend uses this scoped token *instead of* the normal access token
for `GET /api/v1/inspect/{id}` calls. Because the polling token's lifetime
covers the entire job window, **no refresh is needed mid-poll**, eliminating
Cause #1 from the polling path entirely.

### 5b. WebSocket / Server-Sent Events for status updates

Instead of HTTP polling, push status changes over a single long-lived
WebSocket authenticated *once* at connection time (token in `Sec-WebSocket-Protocol`
or as a query param fetched from a single-use ticket endpoint). This
eliminates the refresh problem AND saves a 1.5×–8 s tick on every status
check. Owner: Backend Architect (decision: cost/benefit for 20-min jobs).

### 5c. Hint header from frontend

For polling-class requests, set `X-Poll-Token: 1` so the backend can:
- Skip writing access logs for them (rate-limit budget).
- Rate-limit per-inspection-id rather than per-IP if you ever do limit.

### 5d. Loosen `MAX_CONSECUTIVE_ERRORS` only after fixing the root cause

`use-inspection-polling.ts:111` is set to 8. **Do not raise this without
addressing Causes #1–#3.** A higher number would only hide the failure
longer; the underlying refresh race / restart-secret issue is what should
be fixed.

### 5e. Distinguish 401 from network in error messaging

Right now `info.kind === 'unauthorized'` results in `tHttp('401')` (see
use-inspection-polling.ts:174). But the *interceptor* converts most 401s
into a retried request, and only a 401 that survives refresh bubbles up.
The translation key for the surviving 401 should explicitly point the
user to re-login ("Oturum süreniz doldu, lütfen tekrar giriş yapın"), not
"internet yok". Confirm `errors.network.offline` is not being used for the
exhausted-after-8-errors case — if it is, that copy mislabels an auth
problem as a network problem and worsens debuggability.

---

## 6. Rate Limit on `/auth/refresh`

**Current state**: no decorator on `/auth/refresh` (auth.py:415–436).

**Recommended**: 10 / minute / IP **plus** 60 / hour / `sub` claim.

```python
# services/backend/auth.py — illustrative, Backend Architect to apply
@router.post("/refresh", response_model=TokenPair, summary="…")
@limiter.limit("10/minute", key_func=get_remote_address)
async def refresh(request: Request, payload: RefreshTokenRequest) -> TokenPair:
    ...
```

Why 10/min and not 5: legitimate clients can hit it on every tab open,
SSR hydration, AND a focused-tab reload — five is too tight. 10 is
generous enough for normal usage but tight enough that a credential
stuffer / leak-replayer is throttled.

For per-user (`sub`) limit, decode the JWT *before* full verification and
apply a slow-bucket on the `sub` claim. This catches a single leaked
refresh token spinning across many IPs.

---

## 7. Refresh-Token Single-Use (server-side)

Today `/auth/refresh` re-issues a new refresh on every call but does not
revoke the prior one. That's actually what protects against Cause #1
landing as a hard failure today — but it also means:

1. A leaked refresh token is valid for the full 7 days.
2. There is no audit trail of refresh use.
3. We cannot ever tighten the race fix without breaking it further.

**Recommendation** (Backend Architect):

1. Add a `refresh_tokens` table:
   ```
   jti TEXT PRIMARY KEY
   user_id UUID NOT NULL
   issued_at TIMESTAMPTZ
   expires_at TIMESTAMPTZ
   revoked_at TIMESTAMPTZ
   replaced_by TEXT  -- jti of the next token in the chain
   ```
2. On `/auth/refresh`: verify the incoming refresh's `jti` is present and
   not yet revoked. On success, mark the old `jti` revoked and insert the
   new one with `replaced_by`.
3. **Reuse detection**: if a `revoked_at IS NOT NULL` token is presented,
   that is evidence of a clone (theft or race). Burn the entire chain (set
   `revoked_at` on every descendant of that user since last login), force
   the user to re-authenticate, and emit a security event.
4. This makes the Web Locks fix (Section 4) load-bearing — without it,
   multi-tab users would log themselves out constantly.

---

## 8. Five-Item Prioritized Action List

| # | Action | Owner | Severity | Effort | Why now |
|---|--------|-------|----------|--------|---------|
| 1 | **Set `JWT_SECRET_KEY` (32+ char) in `services/backend/.env`** and make `_validate_config()` hard-fail in *all* environments when missing (not just staging/production). | Backend Architect / DevOps | **Critical** | 5 min | Single most likely cause of the user's reported polling failure during dev testing. Until this is fixed, every restart re-rolls tokens and masks all other auth bugs. |
| 2 | **Replace `tryAcquireRefreshLock` with `navigator.locks.request`** + in-lock re-check of access token freshness (see snippet in Section 4). Keep the existing storage-event flow as fallback for legacy browsers. | Frontend Developer | **High** | 1–2 h | Eliminates the multi-tab refresh race that triggers the 7-attempt polling failure when the user has any other tab open on the app. |
| 3 | **Add `@limiter.limit("10/minute")` to `/auth/refresh`** (`services/backend/auth.py:415`). Also add a per-`sub` limit if Redis-backed limiter supports it. | Backend Architect | High | 15 min | Closes the unbounded-refresh-call surface AND backstops the multi-tab race by failing fast on storms. |
| 4 | **Implement scoped polling token** for long-running inspections: when `/api/v1/inspect` accepts a job, return an `inspection_token` (JWT, 30-min TTL, scope=`polling:read`, bound to `inspection_id`). Frontend uses it for `GET /api/v1/inspect/{id}`. Removes the refresh requirement from the polling path entirely. | Backend Architect + Frontend Developer | High | 1 day | Even after the race is fixed, a 20-min job with a 15-min access TTL is structurally fragile. This is the correct long-term shape. |
| 5 | **Server-side refresh-token revocation table with reuse detection** (Section 7). Required *before* enabling single-use rotation on the client; without it, even the Web Locks fix can be defeated by a stolen refresh. | Backend Architect | Medium | 1–2 days | Closes the leaked-refresh window from 7 days to "first reuse after rotation" (≤ TTL of one access token). |

**Read together:** items 1+2+3 fix today's polling failure. Items 4+5 are
the structural follow-on so the same bug class cannot return.

---

## 9. Out of Scope (handed off)

- The polling hook's `MAX_CONSECUTIVE_ERRORS = 8` and `maxDurationMs = 180_000`
  values themselves — those are Frontend Developer's call. The auth-side
  fixes above remove the reason those budgets ever get hit.
- Translation copy for `errors.network.offline` vs. an
  `errors.auth.sessionExpired` key — Frontend Developer (UX).
- WebSocket-vs-polling decision (Section 5b) — Backend Architect (cost).
- Cookie `Secure` / `HttpOnly` / `SameSite=strict` review for the
  `access_token` cookie set at `apps/web/lib/api.ts:44` — covered in the
  previous `SECURITY_WEB_AUDIT.md`, not relevant to this polling issue.
