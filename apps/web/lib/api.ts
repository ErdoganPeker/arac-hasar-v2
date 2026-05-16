import axios, {
  AxiosError,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from 'axios';
import type {
  HealthResponse,
  InspectionCreateResponse,
  InspectionStatusResponse,
  SyncInspectionResponse,
  InspectionListResponse,
  InspectionStatus,
} from '@arac-hasar/types';
import { isJwtExpired } from './jwt';
import { getSelectedModelId } from './models';

const API_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, '') ?? 'http://localhost:8000';

export const API_BASE_URL = API_URL;
export const TOKEN_STORAGE_KEY = 'arac_hasar_access_token';
export const REFRESH_STORAGE_KEY = 'arac_hasar_refresh_token';
export const TOKEN_COOKIE = 'access_token';
// Cross-tab coordination for refresh-token rotation. Each tab attempts to
// acquire a short-lived lock; if another tab is already refreshing, the
// follower waits for the new access token to land in localStorage instead
// of hitting /auth/refresh in parallel (refresh tokens are single-use, so
// the loser of the race would otherwise invalidate the winner).
const REFRESH_LOCK_KEY = 'arac_hasar_refresh_lock';
const REFRESH_LOCK_TTL_MS = 10_000;
const REFRESH_FOLLOWER_TIMEOUT_MS = 8_000;

/* ---------- token storage helpers ---------- */

function isBrowser(): boolean {
  return typeof window !== 'undefined';
}

export function setStoredTokens(access: string, refresh?: string) {
  if (!isBrowser()) return;
  localStorage.setItem(TOKEN_STORAGE_KEY, access);
  if (refresh) localStorage.setItem(REFRESH_STORAGE_KEY, refresh);
  // Cookie for SSR middleware (decode-only). 7 days; renew on each login.
  const maxAge = 60 * 60 * 24 * 7;
  document.cookie = `${TOKEN_COOKIE}=${encodeURIComponent(
    access,
  )}; path=/; max-age=${maxAge}; samesite=lax`;
}

export function clearStoredTokens() {
  if (!isBrowser()) return;
  localStorage.removeItem(TOKEN_STORAGE_KEY);
  localStorage.removeItem(REFRESH_STORAGE_KEY);
  document.cookie = `${TOKEN_COOKIE}=; path=/; max-age=0; samesite=lax`;
}

export function getStoredAccessToken(): string | null {
  if (!isBrowser()) return null;
  return localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function getStoredRefreshToken(): string | null {
  if (!isBrowser()) return null;
  return localStorage.getItem(REFRESH_STORAGE_KEY);
}

/* ---------- axios instance with interceptors ---------- */

let _client: AxiosInstance | null = null;
let _refreshPromise: Promise<string | null> | null = null;
let _onUnauthorized: (() => void) | null = null;

export function setUnauthorizedHandler(handler: (() => void) | null) {
  _onUnauthorized = handler;
}

function buildClient(): AxiosInstance {
  const instance = axios.create({
    baseURL: API_URL,
    timeout: 60_000,
    withCredentials: false,
  });

  instance.interceptors.request.use((config: InternalAxiosRequestConfig) => {
    const token = getStoredAccessToken();
    if (token) {
      config.headers.set('Authorization', `Bearer ${token}`);
    }
    return config;
  });

  instance.interceptors.response.use(
    (r) => r,
    async (error: AxiosError) => {
      const status = error.response?.status;
      const original = error.config as
        | (InternalAxiosRequestConfig & { _retry?: boolean })
        | undefined;

      if (status === 401 && original && !original._retry) {
        original._retry = true;
        const refreshed = await runRefresh();
        if (refreshed) {
          original.headers?.set?.('Authorization', `Bearer ${refreshed}`);
          return instance.request(original);
        }
        clearStoredTokens();
        _onUnauthorized?.();
      }
      return Promise.reject(error);
    },
  );

  return instance;
}

export function client(): AxiosInstance {
  if (_client) return _client;
  _client = buildClient();
  return _client;
}

/** Try to claim the cross-tab refresh lock. Returns true if we own it. */
function tryAcquireRefreshLock(): boolean {
  if (!isBrowser()) return true;
  try {
    const now = Date.now();
    const raw = localStorage.getItem(REFRESH_LOCK_KEY);
    if (raw) {
      const ts = parseInt(raw, 10);
      // Stale lock (tab crashed) → steal it.
      if (Number.isFinite(ts) && now - ts < REFRESH_LOCK_TTL_MS) {
        return false;
      }
    }
    localStorage.setItem(REFRESH_LOCK_KEY, String(now));
    // Re-read to confirm we won the race (best-effort; localStorage writes
    // are synchronous within a tab, so the second writer in another tab
    // overwrites us — but we'll detect that when our refresh response either
    // succeeds or fails, and in the failure path we fall back to waiting).
    return localStorage.getItem(REFRESH_LOCK_KEY) === String(now);
  } catch {
    return true; // localStorage unavailable: behave as single-tab.
  }
}

function releaseRefreshLock() {
  if (!isBrowser()) return;
  try {
    localStorage.removeItem(REFRESH_LOCK_KEY);
  } catch {
    /* ignore */
  }
}

/**
 * Wait for another tab to publish a fresh access token. Resolves with the
 * new token, or `null` if the leader did not publish within the timeout
 * (caller should then treat the session as dead).
 */
function waitForLeaderRefresh(previousToken: string | null): Promise<string | null> {
  if (!isBrowser()) return Promise.resolve(null);
  return new Promise((resolve) => {
    const start = Date.now();
    let done = false;
    const finish = (token: string | null) => {
      if (done) return;
      done = true;
      window.removeEventListener('storage', onStorage);
      clearInterval(poll);
      resolve(token);
    };
    const onStorage = (e: StorageEvent) => {
      if (e.key === TOKEN_STORAGE_KEY && e.newValue && e.newValue !== previousToken) {
        finish(e.newValue);
      }
    };
    window.addEventListener('storage', onStorage);
    // Fallback poll for same-tab edge cases (storage events do not fire in
    // the writing tab) and for browsers that batch them.
    const poll = setInterval(() => {
      const current = getStoredAccessToken();
      if (current && current !== previousToken) {
        finish(current);
        return;
      }
      if (Date.now() - start >= REFRESH_FOLLOWER_TIMEOUT_MS) {
        finish(null);
      }
    }, 200);
  });
}

async function runRefresh(): Promise<string | null> {
  // In-tab dedup: while one request is refreshing, others await the same
  // promise instead of firing a second /auth/refresh.
  if (_refreshPromise) return _refreshPromise;
  const refresh = getStoredRefreshToken();
  if (!refresh) return null;

  const previousAccess = getStoredAccessToken();
  const isLeader = tryAcquireRefreshLock();

  _refreshPromise = (async () => {
    try {
      if (!isLeader) {
        // Follower: wait for the leader tab to write the new token.
        const token = await waitForLeaderRefresh(previousAccess);
        return token;
      }
      const res = await axios.post<{
        access_token: string;
        refresh_token?: string;
      }>(`${API_URL}/auth/refresh`, { refresh_token: refresh });
      const { access_token, refresh_token } = res.data;
      setStoredTokens(access_token, refresh_token ?? refresh);
      return access_token;
    } catch {
      return null;
    } finally {
      if (isLeader) releaseRefreshLock();
      _refreshPromise = null;
    }
  })();
  return _refreshPromise;
}

/* ---------- auth ---------- */

export interface User {
  id: string;
  email: string;
  full_name?: string;
  role?: 'admin' | 'user' | string;
  created_at?: string;
  is_active?: boolean;
}

export interface AuthTokens {
  access_token: string;
  refresh_token?: string;
}

export interface LoginResponse extends AuthTokens {
  user?: User;
}

export interface RegisterResponse extends AuthTokens {
  user: User;
}

export const auth = {
  async login(email: string, password: string): Promise<LoginResponse> {
    const res = await client().post<LoginResponse>('/auth/login', {
      email,
      password,
    });
    return res.data;
  },
  async register(
    email: string,
    password: string,
    full_name: string,
  ): Promise<RegisterResponse> {
    const res = await client().post<RegisterResponse>('/auth/register', {
      email,
      password,
      full_name,
    });
    return res.data;
  },
  async me(): Promise<User> {
    const res = await client().get<User>('/auth/me');
    return res.data;
  },
  async refresh(): Promise<string | null> {
    return runRefresh();
  },
  async changePassword(current: string, next: string): Promise<void> {
    await client().post('/auth/change-password', {
      current_password: current,
      new_password: next,
    });
  },
  async updateProfile(input: { full_name?: string }): Promise<User> {
    const res = await client().patch<User>('/auth/me', input);
    return res.data;
  },
  hasValidSession(): boolean {
    const t = getStoredAccessToken();
    if (!t) return false;
    return !isJwtExpired(t, 5);
  },
};

/* ---------- inspections ---------- */

export interface CreateInspectionOptions {
  /** sync = inline (max 3 files), async = queued */
  mode?: 'sync' | 'async';
  apiKey?: string;
  signal?: AbortSignal;
  onUploadProgress?: (loaded: number, total: number) => void;
}

export interface ListInspectionsOptions {
  page?: number;
  pageSize?: number;
  status?: InspectionStatus;
  dateFrom?: string; // ISO
  dateTo?: string; // ISO
  query?: string;
  apiKey?: string;
  signal?: AbortSignal;
}

export const inspections = {
  async create(
    files: File[],
    opts: CreateInspectionOptions = {},
  ): Promise<InspectionCreateResponse | SyncInspectionResponse> {
    const { mode = 'async', apiKey, signal, onUploadProgress } = opts;

    if (!files || files.length === 0) {
      throw new Error('NO_FILES');
    }

    const form = new FormData();
    // IMPORTANT:
    // - /api/v1/inspect           expects field name 'files' (List[UploadFile])
    // - /api/v1/inspect/sync      expects field name 'file'  (single UploadFile)
    // Always use the multi-file endpoint so the same code path supports 1..N
    // images. We pass ?mode=sync|async on the query string.
    files.forEach((f) => form.append('files', f, f.name));

    // Append the user-selected model (header dropdown) so the backend can
    // route the request to either the pre-trained weights or the
    // fine-tuned custom checkpoint. Falls back to the documented default
    // when the header has not initialized yet (SSR / first paint).
    const modelId = getSelectedModelId();
    const params = new URLSearchParams();
    params.set('mode', mode === 'sync' ? 'sync' : 'async');
    if (modelId) params.set('model', modelId);
    const path = `/api/v1/inspect?${params.toString()}`;

    // CRITICAL: do NOT set Content-Type manually. axios/the browser must add
    // it automatically so that the multipart boundary token is included in
    // the header. Setting `Content-Type: multipart/form-data` here strips the
    // boundary and the backend rejects the upload as malformed.
    const res = await client().post<
      InspectionCreateResponse | SyncInspectionResponse
    >(path, form, {
      headers: apiKey ? { 'X-API-Key': apiKey } : undefined,
      signal,
      onUploadProgress: (evt) => {
        if (onUploadProgress && evt.total) {
          onUploadProgress(evt.loaded, evt.total);
        }
      },
    });
    return res.data;
  },

  async get(
    inspectionId: string,
    opts: { apiKey?: string; signal?: AbortSignal } = {},
  ): Promise<InspectionStatusResponse> {
    const res = await client().get<InspectionStatusResponse>(
      `/api/v1/inspect/${encodeURIComponent(inspectionId)}`,
      {
        headers: opts.apiKey ? { 'X-API-Key': opts.apiKey } : undefined,
        signal: opts.signal,
      },
    );
    return res.data;
  },

  async list(opts: ListInspectionsOptions = {}): Promise<InspectionListResponse> {
    const {
      page = 1,
      pageSize = 20,
      status,
      dateFrom,
      dateTo,
      query,
      apiKey,
      signal,
    } = opts;
    const res = await client().get<InspectionListResponse>(`/api/v1/inspect`, {
      params: {
        page,
        page_size: pageSize,
        status,
        date_from: dateFrom,
        date_to: dateTo,
        q: query || undefined,
      },
      headers: apiKey ? { 'X-API-Key': apiKey } : undefined,
      signal,
    });
    return res.data;
  },

  async delete(inspectionId: string): Promise<void> {
    await client().delete(`/api/v1/inspect/${encodeURIComponent(inspectionId)}`);
  },

  visualization(
    inspectionId: string,
    type: 'annotated' | 'parts' | 'damages',
  ): string {
    return `${API_URL}/api/v1/inspect/${encodeURIComponent(inspectionId)}/visualization/${type}`;
  },
};

/* ---------- api keys ---------- */

export interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at?: string | null;
  revoked: boolean;
}

export interface ApiKeyCreateResponse {
  key: ApiKey;
  /** Plaintext key returned ONCE on creation. */
  secret: string;
}

export const apiKeys = {
  async list(): Promise<ApiKey[]> {
    const res = await client().get<ApiKey[]>('/auth/api-keys');
    return res.data;
  },
  async create(name: string): Promise<ApiKeyCreateResponse> {
    const res = await client().post<ApiKeyCreateResponse>('/auth/api-keys', {
      name,
    });
    return res.data;
  },
  async revoke(id: string): Promise<void> {
    await client().delete(`/auth/api-keys/${encodeURIComponent(id)}`);
  },
};

/* ---------- admin: users ---------- */

export const adminUsers = {
  async list(): Promise<User[]> {
    const res = await client().get<User[]>('/admin/users');
    return res.data;
  },
  async setRole(userId: string, role: 'admin' | 'user'): Promise<User> {
    const res = await client().patch<User>(
      `/admin/users/${encodeURIComponent(userId)}/role`,
      { role },
    );
    return res.data;
  },
  async setActive(userId: string, is_active: boolean): Promise<User> {
    const res = await client().patch<User>(
      `/admin/users/${encodeURIComponent(userId)}/active`,
      { is_active },
    );
    return res.data;
  },
};

/* ---------- misc ---------- */

export async function getHealth(): Promise<HealthResponse> {
  const res = await client().get<HealthResponse>('/health');
  return res.data;
}

/* ---------- backward-compat exports (existing pages still use these) ---------- */

export async function createInspection(
  files: File[],
  opts: CreateInspectionOptions = {},
): Promise<InspectionCreateResponse | SyncInspectionResponse> {
  return inspections.create(files, opts);
}

export async function getInspectionStatus(
  inspectionId: string,
  opts: { apiKey?: string; signal?: AbortSignal } = {},
): Promise<InspectionStatusResponse> {
  return inspections.get(inspectionId, opts);
}

export async function listInspections(
  opts: ListInspectionsOptions = {},
): Promise<InspectionListResponse> {
  return inspections.list(opts);
}

export function inspectionVisualizationUrl(
  inspectionId: string,
  type: 'annotated' | 'parts' | 'damages',
): string {
  return inspections.visualization(inspectionId, type);
}

export function isSyncResponse(
  r: InspectionCreateResponse | SyncInspectionResponse,
): r is SyncInspectionResponse {
  return 'result' in r && 'processed_at' in r;
}

/* ---------- error extraction ---------- */

/**
 * Classify an axios/fetch error into a stable kind plus the first available
 * human-readable detail string. Callers translate the kind via next-intl;
 * `detail` (when present) is the raw server message (e.g. FastAPI HTTPException
 * detail) which is usually already localized server-side.
 */
export interface ApiErrorInfo {
  kind:
    | 'network'
    | 'cancelled'
    | 'timeout'
    | 'badRequest'
    | 'unauthorized'
    | 'forbidden'
    | 'notFound'
    | 'tooLarge'
    | 'unsupportedMedia'
    | 'validation'
    | 'rateLimited'
    | 'server'
    | 'unknown';
  status?: number;
  detail?: string;
  /** Field-level errors from FastAPI 422 (RequestValidationError). */
  fieldErrors?: Array<{ field: string; message: string }>;
}

export function classifyApiError(err: unknown): ApiErrorInfo {
  if (axios.isCancel(err)) return { kind: 'cancelled' };
  if (!axios.isAxiosError(err)) return { kind: 'unknown' };
  if (err.code === 'ECONNABORTED' || err.code === 'ETIMEDOUT') {
    return { kind: 'timeout' };
  }
  if (!err.response) return { kind: 'network' };

  const { status, data } = err.response;
  // FastAPI: { detail: string } or { detail: [{ loc, msg, type }, ...] }
  let detail: string | undefined;
  let fieldErrors: Array<{ field: string; message: string }> | undefined;
  if (data && typeof data === 'object') {
    const d = (data as { detail?: unknown }).detail;
    if (typeof d === 'string') {
      detail = d;
    } else if (Array.isArray(d)) {
      fieldErrors = d
        .map((e) => {
          if (!e || typeof e !== 'object') return null;
          const loc = (e as { loc?: unknown[] }).loc;
          const msg = (e as { msg?: unknown }).msg;
          const field = Array.isArray(loc)
            ? loc.filter((p) => p !== 'body' && p !== 'query').join('.')
            : '';
          return typeof msg === 'string'
            ? { field: field || '_', message: msg }
            : null;
        })
        .filter((x): x is { field: string; message: string } => x !== null);
      detail = fieldErrors[0]?.message;
    }
  }

  const base: ApiErrorInfo = { kind: 'unknown', status, detail, fieldErrors };
  if (status === 400) return { ...base, kind: 'badRequest' };
  if (status === 401) return { ...base, kind: 'unauthorized' };
  if (status === 403) return { ...base, kind: 'forbidden' };
  if (status === 404) return { ...base, kind: 'notFound' };
  if (status === 413) return { ...base, kind: 'tooLarge' };
  if (status === 415) return { ...base, kind: 'unsupportedMedia' };
  if (status === 422) return { ...base, kind: 'validation' };
  if (status === 429) return { ...base, kind: 'rateLimited' };
  if (status && status >= 500) return { ...base, kind: 'server' };
  return base;
}
