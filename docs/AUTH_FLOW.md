# Authentication Flow

How users authenticate with Hasarİ — token lifecycle, sequence diagrams, per-platform storage, and security guarantees.

---

## At a glance

- **Standard**: OAuth 2.0-style bearer tokens, signed JWT (HS256 by default).
- **Two token types**: short-lived access (30 min), long-lived refresh (7 days).
- **Three platforms, three storage strategies**: httpOnly cookie or localStorage (web), `expo-secure-store` (mobile), Tauri Stronghold / encrypted store (desktop).
- **Fallback**: legacy `X-API-Key` header for service-to-service calls until v1.0.

---

## Sequence: register → use API → refresh

```
┌──────────┐                       ┌──────────────┐               ┌────────────┐
│  Client  │                       │   Backend    │               │  Postgres  │
└────┬─────┘                       └──────┬───────┘               └─────┬──────┘
     │                                    │                              │
     │  POST /auth/register               │                              │
     │  { email, password, full_name }    │                              │
     │───────────────────────────────────►│                              │
     │                                    │  bcrypt(password) → hash     │
     │                                    │  INSERT user                 │
     │                                    │─────────────────────────────►│
     │                                    │◄─────── user_id ─────────────│
     │                                    │                              │
     │                                    │  jwt.encode(sub=user_id,     │
     │                                    │             type='access')   │
     │                                    │  jwt.encode(sub=user_id,     │
     │                                    │             type='refresh')  │
     │                                    │                              │
     │  201 { access_token, refresh_token, expires_in: 1800 }            │
     │◄───────────────────────────────────│                              │
     │                                    │                              │
     │  store tokens (see "Storage" §)    │                              │
     │                                    │                              │
     │                                    │                              │
     │  GET /api/v1/inspect/abc           │                              │
     │  Authorization: Bearer <access>    │                              │
     │───────────────────────────────────►│                              │
     │                                    │  jwt.decode → verify sig,    │
     │                                    │  exp, type=='access'         │
     │                                    │  SELECT inspection           │
     │                                    │─────────────────────────────►│
     │                                    │◄─────── row ─────────────────│
     │  200 { inspection details }        │                              │
     │◄───────────────────────────────────│                              │
     │                                    │                              │
     │  ... 30 minutes later ...          │                              │
     │                                    │                              │
     │  GET /api/v1/inspect/xyz           │                              │
     │  Authorization: Bearer <access>    │                              │
     │───────────────────────────────────►│                              │
     │                                    │  jwt.decode → ExpiredError   │
     │  401 "Token süresi doldu"          │                              │
     │◄───────────────────────────────────│                              │
     │                                    │                              │
     │  POST /auth/refresh                │                              │
     │  { refresh_token }                 │                              │
     │───────────────────────────────────►│                              │
     │                                    │  jwt.decode(type='refresh')  │
     │                                    │  SELECT user (is_active?)    │
     │                                    │─────────────────────────────►│
     │                                    │◄─────── user ────────────────│
     │  200 { access_token, refresh_token (new), expires_in: 1800 }      │
     │◄───────────────────────────────────│                              │
     │                                    │                              │
     │  store new tokens, retry           │                              │
     │  the original request              │                              │
     │                                    │                              │
```

---

## Sequence: login

```
┌──────────┐                       ┌──────────────┐               ┌────────────┐
│  Client  │                       │   Backend    │               │  Postgres  │
└────┬─────┘                       └──────┬───────┘               └─────┬──────┘
     │                                    │                              │
     │  POST /auth/login                  │                              │
     │  { email, password }               │                              │
     │───────────────────────────────────►│                              │
     │                                    │  SELECT user WHERE email     │
     │                                    │─────────────────────────────►│
     │                                    │◄────── user or null ─────────│
     │                                    │                              │
     │                                    │  if user: hash = user.hash   │
     │                                    │  else:    hash = dummy_hash  │
     │                                    │  bcrypt.verify(password,hash)│
     │                                    │  ↑ runs even if user is null │
     │                                    │  (timing-safe)               │
     │                                    │                              │
     │                                    │  if invalid:                 │
     │  401 "Email veya parola hatali"    │                              │
     │◄───────────────────────────────────│                              │
     │                                    │                              │
     │                                    │  if valid + active:          │
     │                                    │  build TokenPair             │
     │  200 { access_token, refresh_token }                              │
     │◄───────────────────────────────────│                              │
     │                                    │                              │
```

The dummy bcrypt verify in the user-not-found path is **important**: it equalizes the response time so an attacker cannot enumerate valid emails by measuring how fast the API responds.

---

## Sequence: logout

Logout is client-driven in v0.1 (no server-side revocation list yet — v0.2 backlog):

```
┌──────────┐                       ┌──────────────┐
│  Client  │                       │   Backend    │
└────┬─────┘                       └──────┬───────┘
     │                                    │
     │  1. delete access_token from       │
     │     local storage                  │
     │  2. delete refresh_token from      │
     │     secure storage                 │
     │  3. (optional) call                │
     │     /auth/revoke once implemented  │
     │                                    │
     │  → User redirected to /login       │
     │                                    │
```

**Hardening planned for v0.2**: a `POST /auth/revoke` endpoint that adds the token's `jti` claim to a Redis-backed blocklist with the same TTL as the refresh token. Until then, treat logout as a client-side hygiene step; defense-in-depth comes from the short 30-min access-token lifetime.

---

## JWT structure

Tokens are HS256-signed JSON Web Tokens. **Do not** store sensitive PII in claims — the payload is base64-encoded, not encrypted.

### Access token claims

| Claim | Type | Description |
|---|---|---|
| `sub` | string (UUID) | User ID. **Source of truth** for the request. |
| `email` | string | Cached email (convenience for logging; not authoritative — re-fetch via DB if needed). |
| `role` | `"user"` \| `"admin"` | Authorization scope. |
| `type` | `"access"` | Hard guard: decode rejects if not `access` when access is expected. |
| `iat` | int (epoch s) | Issued-at. |
| `exp` | int (epoch s) | Expires at issued + 30 min. |
| `jti` | string (UUID) | Unique token ID — used for the planned revocation list. |
| `iss` | string | `"hasari-api"`. |

### Refresh token claims

Same shape, but `type: "refresh"` and `exp = iat + 7 days`. Backend **rejects** a refresh token used at endpoints expecting access (and vice-versa) — this prevents a stolen refresh token from being used directly as a bearer credential.

### Verifying claims locally (client-side hint only — never trust)

```javascript
import { jwtDecode } from 'jwt-decode';

const claims = jwtDecode(accessToken);
const expiresAt = claims.exp * 1000; // ms
const isExpired = Date.now() >= expiresAt;

// Refresh proactively 60s before expiry
const needsRefresh = Date.now() >= expiresAt - 60_000;
```

**Critical**: never authorize based on client-decoded claims. The client decodes only for "should I refresh now?" UX timing. Authorization always happens server-side after signature verification.

---

## Token storage — per platform

### Web (Next.js)

**Recommended (production): httpOnly cookies**

- Access token in a `Secure; HttpOnly; SameSite=Lax` cookie, path `/`.
- Refresh token in a `Secure; HttpOnly; SameSite=Strict` cookie, path `/auth/refresh`.
- The cookie is automatically sent with every same-origin request — no manual `Authorization` header needed.
- **Pro**: JavaScript cannot read the token, so XSS cannot exfiltrate it.
- **Con**: requires CSRF protection on every state-changing endpoint (we add a double-submit token).

**Acceptable (dev / SPA): localStorage**

- Access token in `localStorage`, sent manually via `fetch` headers.
- **Pro**: simple, framework-agnostic.
- **Con**: any XSS empties the wallet. Must enforce strict CSP, escape user content, audit dependencies.

The current v0.1 web app uses `localStorage` for fast iteration. **Cookie-based auth is a launch-blocker checklist item** in [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md).

### Mobile (Expo / React Native)

Use `expo-secure-store` (Keychain on iOS, EncryptedSharedPreferences on Android):

```typescript
import * as SecureStore from 'expo-secure-store';

// Save after login
await SecureStore.setItemAsync('accessToken', accessToken, {
  keychainAccessible: SecureStore.WHEN_UNLOCKED,
});
await SecureStore.setItemAsync('refreshToken', refreshToken, {
  keychainAccessible: SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
});

// Read for API calls
const token = await SecureStore.getItemAsync('accessToken');

// Clear on logout
await SecureStore.deleteItemAsync('accessToken');
await SecureStore.deleteItemAsync('refreshToken');
```

**Never** put tokens in `AsyncStorage` — it's unencrypted on disk and can be read by jailbroken/rooted devices or backup extractions.

### Desktop (Tauri 2)

Two options, in order of preference:

1. **Tauri Stronghold** (recommended): a hardened cryptographic vault that encrypts tokens at rest with a key derived from the user's OS-level credentials (or a passphrase).
2. **`@tauri-apps/plugin-store`** with manual AES encryption: simpler but you own the key management.

Stronghold sketch:

```typescript
import { Stronghold } from '@tauri-apps/plugin-stronghold';

const hold = await Stronghold.load('~/.hasari/vault.hold', 'user-passphrase');
const store = await hold.loadClient('tokens');

await store.insert('accessToken', accessToken);
await hold.save();
```

**Never** use plain `localStorage` in a Tauri webview — the file is unencrypted on disk and accessible to any other process running as the same user.

---

## Refresh strategy (client-side)

Use one of these patterns; do not mix them.

### Pattern A — proactive refresh (preferred for SPAs)

A background task wakes up 60 seconds before the access token expires and silently calls `/auth/refresh`. The user never sees a 401.

```typescript
function scheduleRefresh(expiresInSec: number) {
  const refreshAt = (expiresInSec - 60) * 1000;
  setTimeout(async () => {
    const fresh = await refreshTokens();
    storeTokens(fresh);
    scheduleRefresh(fresh.expires_in);
  }, refreshAt);
}
```

### Pattern B — reactive refresh on 401 (preferred for mobile)

The HTTP client interceptor catches a 401, calls `/auth/refresh`, replays the original request, and only signs the user out if the refresh itself fails.

```typescript
axios.interceptors.response.use(null, async (error) => {
  if (error.response?.status !== 401) throw error;
  if (error.config.__isRetry) throw error; // avoid infinite loop

  try {
    const fresh = await refreshTokens();
    storeTokens(fresh);
    error.config.__isRetry = true;
    error.config.headers.Authorization = `Bearer ${fresh.access_token}`;
    return axios(error.config);
  } catch {
    await logout();
    throw error;
  }
});
```

**Important**: serialize concurrent refresh attempts. Multiple in-flight 401s should trigger **one** refresh, and all waiters should pick up the new token.

---

## Security guarantees & threat model

| Threat | Mitigation |
|---|---|
| Replay of stolen access token | 30-min TTL caps damage window. Token revocation list planned for v0.2. |
| Replay of stolen refresh token | 7-day TTL; HTTPS-only in production; `SameSite=Strict` cookie. Compromise of a long-lived device requires a remote logout (planned). |
| Email enumeration via timing | `/auth/login` runs bcrypt even when the user does not exist. |
| Brute-force password attack | Per-IP rate limit (10 req/min on `/auth/*`); bcrypt cost factor 12 (≈200 ms per attempt). |
| Weak passwords | Pydantic enforces ≥8 chars; client SHOULD enforce composition rules (uppercase/lowercase/number). |
| JWT signature forgery | HS256 with ≥32-char secret; non-dev environments hard-fail if the secret is short or missing. |
| Algorithm-confusion attacks (`alg=none`, RS256→HS256) | Decoder explicitly pins the `algorithms` whitelist; never accepts a token whose alg doesn't match the configured one. |
| XSS exfiltrating tokens | Migrating to httpOnly cookies (v0.2). Strict CSP recommended. |
| CSRF on cookie auth | Double-submit CSRF token on state-changing requests (added when cookie auth ships). |
| Lost device / forgotten logout | Short access TTL + admin "force logout all" (v0.2 backlog). |

---

## Environment variables (auth-relevant)

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `JWT_SECRET_KEY` | yes (non-dev) | (random per-process) | HMAC signing key; must be ≥32 chars in non-dev environments. |
| `JWT_ALGORITHM` | no | `HS256` | Signing algorithm; only HS*/RS*/ES* prefixes accepted. |
| `ACCESS_TOKEN_MINUTES` | no | `30` | Access token TTL. |
| `REFRESH_TOKEN_DAYS` | no | `7` | Refresh token TTL. |
| `ENVIRONMENT` | yes | `dev` | If `dev`, unauthenticated requests are accepted as a `dev` client. Set to `production` or `staging` in any deployment. |

Full env-var matrix is in [DEPLOY_GUIDE.md](DEPLOY_GUIDE.md#environment-variables).
