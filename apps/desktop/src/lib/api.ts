/**
 * Axios HTTP client with:
 *   - JWT Bearer auth (token loaded from Tauri Store via `auth-store.ts`)
 *   - request interceptor injects `Authorization: Bearer <access>`
 *   - response interceptor on 401: attempts a single refresh, replays the request,
 *     and falls back to a logout callback on hard failure
 *   - base URL & legacy X-API-Key bridged from `settings.ts`
 *
 * The interceptor avoids infinite refresh loops by guarding `_retry` on the request config.
 */
import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import type {
  AuthTokens,
  HealthResponse,
  InspectionCreateResponse,
  InspectionStatusResponse,
  SyncInspectionResponse,
  InspectionListResponse,
  LoginRequest,
  LoginResponse,
  RegisterRequest,
  RefreshTokenResponse,
  User,
} from '@arac-hasar/types';

const DEFAULT_BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';

interface RetryableConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

type TokenGetter = () => AuthTokens | null;
type TokensSetter = (t: AuthTokens) => void | Promise<void>;
type LogoutHandler = () => void | Promise<void>;

class ApiClient {
  private client: AxiosInstance;
  private getTokens: TokenGetter = () => null;
  private setTokens: TokensSetter = () => undefined;
  private onLogout: LogoutHandler = () => undefined;
  private refreshInFlight: Promise<AuthTokens | null> | null = null;

  constructor(baseURL: string = DEFAULT_BASE_URL, apiKey?: string) {
    this.client = axios.create({
      baseURL,
      timeout: 60_000,
      headers: apiKey ? { 'X-API-Key': apiKey } : {},
    });

    this.client.interceptors.request.use((cfg) => {
      const tk = this.getTokens();
      if (tk?.access_token) {
        cfg.headers = cfg.headers ?? {};
        cfg.headers.Authorization = `Bearer ${tk.access_token}`;
      }
      return cfg;
    });

    this.client.interceptors.response.use(
      (r) => r,
      async (err: AxiosError) => {
        const original = err.config as RetryableConfig | undefined;
        if (err.response?.status === 401 && original && !original._retry) {
          original._retry = true;
          const refreshed = await this.tryRefresh();
          if (refreshed) {
            original.headers = original.headers ?? {};
            original.headers.Authorization = `Bearer ${refreshed.access_token}`;
            return this.client.request(original);
          }
          await this.onLogout();
        }
        return Promise.reject(err);
      },
    );
  }

  bindAuth(opts: { getTokens: TokenGetter; setTokens: TokensSetter; onLogout: LogoutHandler }) {
    this.getTokens = opts.getTokens;
    this.setTokens = opts.setTokens;
    this.onLogout = opts.onLogout;
  }

  setApiKey(apiKey: string | null) {
    if (apiKey) this.client.defaults.headers.common['X-API-Key'] = apiKey;
    else delete this.client.defaults.headers.common['X-API-Key'];
  }

  setBaseUrl(url: string) {
    this.client.defaults.baseURL = url;
  }

  private async tryRefresh(): Promise<AuthTokens | null> {
    if (this.refreshInFlight) return this.refreshInFlight;
    const cur = this.getTokens();
    if (!cur?.refresh_token) return null;
    this.refreshInFlight = (async () => {
      try {
        const { data } = await axios.post<RefreshTokenResponse>(
          `${this.client.defaults.baseURL}/api/v1/auth/refresh`,
          { refresh_token: cur.refresh_token },
        );
        const next: AuthTokens = {
          access_token: data.access_token,
          refresh_token: data.refresh_token ?? cur.refresh_token,
        };
        await this.setTokens(next);
        return next;
      } catch {
        return null;
      } finally {
        this.refreshInFlight = null;
      }
    })();
    return this.refreshInFlight;
  }

  // ───── Auth ─────
  async login(payload: LoginRequest): Promise<LoginResponse> {
    const { data } = await this.client.post<LoginResponse>('/api/v1/auth/login', payload);
    return data;
  }

  async register(payload: RegisterRequest): Promise<LoginResponse> {
    const { data } = await this.client.post<LoginResponse>('/api/v1/auth/register', payload);
    return data;
  }

  async me(): Promise<User> {
    const { data } = await this.client.get<User>('/api/v1/auth/me');
    return data;
  }

  async logout(): Promise<void> {
    try {
      await this.client.post('/api/v1/auth/logout');
    } catch {
      // server-side logout best-effort; client clears regardless
    }
  }

  // ───── System ─────
  async health(): Promise<HealthResponse> {
    const { data } = await this.client.get<HealthResponse>('/health');
    return data;
  }

  // ───── Inspections ─────
  async createInspection(
    files: File[] | Blob[],
    mode: 'sync' | 'async' = 'async',
    onProgress?: (pct: number) => void,
  ): Promise<InspectionCreateResponse | SyncInspectionResponse> {
    const form = new FormData();
    files.forEach((f, i) => {
      const name = f instanceof File ? f.name : `image_${i}.jpg`;
      form.append('files', f, name);
    });
    const { data } = await this.client.post(`/api/v1/inspect?mode=${mode}`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (e) => {
        if (onProgress && e.total) onProgress(Math.round((e.loaded / e.total) * 100));
      },
    });
    return data;
  }

  async getInspection(id: string): Promise<InspectionStatusResponse> {
    const { data } = await this.client.get<InspectionStatusResponse>(`/api/v1/inspect/${id}`);
    return data;
  }

  async listInspections(page = 1, pageSize = 20): Promise<InspectionListResponse> {
    const { data } = await this.client.get<InspectionListResponse>('/api/v1/inspect', {
      params: { page, page_size: pageSize },
    });
    return data;
  }

  async deleteInspection(id: string): Promise<void> {
    await this.client.delete(`/api/v1/inspect/${id}`);
  }

  /** Server-rendered PDF report (returned as base64 to forward to `save_report`). */
  async exportInspectionPdf(id: string): Promise<string> {
    const { data } = await this.client.get<ArrayBuffer>(`/api/v1/inspect/${id}/report.pdf`, {
      responseType: 'arraybuffer',
    });
    return arrayBufferToBase64(data);
  }
}

function arrayBufferToBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let bin = '';
  for (let i = 0; i < bytes.byteLength; i++) bin += String.fromCharCode(bytes[i] ?? 0);
  return typeof btoa !== 'undefined' ? btoa(bin) : Buffer.from(bin, 'binary').toString('base64');
}

export const api = new ApiClient();
export default ApiClient;
