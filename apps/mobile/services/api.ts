/**
 * services/api.ts — Axios-based API client for mobile.
 *
 * Features:
 *  - Base URL from EXPO_PUBLIC_API_URL (with platform-aware fallback).
 *  - Bearer token interceptor (expo-secure-store).
 *  - 401 single-flight refresh-token retry.
 *  - Multipart upload helper for inspection images.
 *  - Endpoints exposed as `api.auth.*`, `api.inspections.*`.
 */
import axios, {
  AxiosError,
  AxiosInstance,
  InternalAxiosRequestConfig,
} from 'axios';
import { Platform } from 'react-native';

import type {
  HealthResponse,
  InspectionCreateResponse,
  InspectionStatusResponse,
  SyncInspectionResponse,
  InspectionListResponse,
} from '@arac-hasar/types';

import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
} from './auth';

// ---- Base URL resolution ----------------------------------------------------

function resolveBaseUrl(): string {
  const fromEnv = process.env.EXPO_PUBLIC_API_URL;
  if (fromEnv && fromEnv.trim().length > 0) {
    return fromEnv.replace(/\/+$/, '');
  }
  // Sensible per-platform defaults for local development.
  if (Platform.OS === 'android') return 'http://10.0.2.2:8000';
  return 'http://localhost:8000';
}

export const API_BASE = resolveBaseUrl();
const DEFAULT_API_KEY = process.env.EXPO_PUBLIC_API_KEY || '';

// ---- Axios instance ---------------------------------------------------------

export const http: AxiosInstance = axios.create({
  baseURL: API_BASE,
  timeout: 30_000,
  headers: { Accept: 'application/json' },
});

// Attach bearer token + optional API key
http.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  const token = await getAccessToken();
  config.headers = config.headers ?? {};
  if (token) {
    (config.headers as Record<string, string>).Authorization = `Bearer ${token}`;
  }
  if (DEFAULT_API_KEY) {
    (config.headers as Record<string, string>)['X-API-Key'] = DEFAULT_API_KEY;
  }
  return config;
});

// Single-flight refresh
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    const refresh = await getRefreshToken();
    if (!refresh) return null;
    try {
      const { data } = await axios.post<{ access_token: string; refresh_token?: string }>(
        `${API_BASE}/auth/refresh`,
        { refresh_token: refresh },
        { timeout: 15_000 },
      );
      if (data?.access_token) {
        await setTokens({
          access_token: data.access_token,
          refresh_token: data.refresh_token ?? refresh,
        });
        return data.access_token;
      }
    } catch {
      /* fall through */
    }
    return null;
  })().finally(() => {
    refreshPromise = null;
  });
  return refreshPromise;
}

http.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined;
    if (
      error.response?.status === 401 &&
      original &&
      !original._retry &&
      !original.url?.includes('/auth/login') &&
      !original.url?.includes('/auth/register') &&
      !original.url?.includes('/auth/refresh')
    ) {
      original._retry = true;
      const newToken = await refreshAccessToken();
      if (newToken) {
        original.headers = original.headers ?? {};
        (original.headers as Record<string, string>).Authorization = `Bearer ${newToken}`;
        return http.request(original);
      }
      // Could not refresh — clear tokens so RootNavigator routes to login.
      await clearTokens();
    }
    return Promise.reject(error);
  },
);

// ---- Helpers ----------------------------------------------------------------

function appendFile(form: FormData, uri: string, name: string, field = 'files'): void {
  // React Native FormData file object — must include uri/name/type.
  // On Android iOS the picker/camera uri is already `file://...` or `content://...`;
  // do not strip the scheme. iOS Simulator returns `file://` paths.
  const lower = uri.toLowerCase();
  const ext = lower.endsWith('.png') ? 'png' : lower.endsWith('.heic') ? 'heic' : 'jpg';
  const mime =
    ext === 'png' ? 'image/png' : ext === 'heic' ? 'image/heic' : 'image/jpeg';
  const finalName = name.includes('.') ? name : `${name}.${ext}`;
  // RN's FormData accepts {uri,name,type}; the typings don't model this so we cast.
  form.append(field, { uri, name: finalName, type: mime } as unknown as Blob);
}

export interface LoginPayload {
  email: string;
  password: string;
}
export interface RegisterPayload {
  email: string;
  password: string;
  full_name?: string;
  company?: string;
}
export interface AuthResponse {
  access_token: string;
  refresh_token?: string;
  user?: {
    id?: string | number;
    email: string;
    full_name?: string;
    company?: string;
  };
}

// ---- API surface ------------------------------------------------------------

interface InspectionApi {
  createAsync: (imageUris: string[]) => Promise<InspectionCreateResponse>;
  createSync: (imageUri: string) => Promise<SyncInspectionResponse>;
  get: (id: string) => Promise<InspectionStatusResponse>;
  list: (opts?: { page?: number; pageSize?: number }) => Promise<InspectionListResponse>;
  visualizationUrl: (id: string, type: 'annotated' | 'parts' | 'damages') => string;
}

interface AuthApi {
  login: (p: LoginPayload) => Promise<AuthResponse>;
  register: (p: RegisterPayload) => Promise<AuthResponse>;
  me: () => Promise<AuthResponse['user']>;
  changePassword: (current: string, next: string) => Promise<void>;
  logout: () => Promise<void>;
}

export interface ApiSurface {
  health: () => Promise<HealthResponse>;
  auth: AuthApi;
  inspections: InspectionApi;
  // Legacy helpers kept for older screens.
  createInspection: (imageUris: string[]) => Promise<string>;
  getInspection: (id: string) => Promise<InspectionStatusResponse>;
  listInspections: (opts?: { page?: number; pageSize?: number }) => Promise<InspectionListResponse>;
  syncInspect: (uri: string) => Promise<SyncInspectionResponse>;
  visualizationUrl: (id: string, type: 'annotated' | 'parts' | 'damages') => string;
}

export const api: ApiSurface = {
  // Health
  async health(): Promise<HealthResponse> {
    const { data } = await http.get<HealthResponse>('/health');
    return data;
  },

  auth: {
    async login(payload: LoginPayload): Promise<AuthResponse> {
      const { data } = await http.post<AuthResponse>('/auth/login', payload);
      if (data?.access_token) {
        await setTokens({
          access_token: data.access_token,
          refresh_token: data.refresh_token,
        });
      }
      return data;
    },

    async register(payload: RegisterPayload): Promise<AuthResponse> {
      const { data } = await http.post<AuthResponse>('/auth/register', payload);
      if (data?.access_token) {
        await setTokens({
          access_token: data.access_token,
          refresh_token: data.refresh_token,
        });
      }
      return data;
    },

    async me(): Promise<AuthResponse['user']> {
      const { data } = await http.get<AuthResponse['user']>('/auth/me');
      return data;
    },

    async changePassword(current_password: string, new_password: string): Promise<void> {
      await http.post('/auth/change-password', {
        current_password,
        new_password,
      });
    },

    async logout(): Promise<void> {
      try {
        await http.post('/auth/logout');
      } catch {
        /* ignore */
      }
      await clearTokens();
    },
  },

  inspections: {
    async createAsync(imageUris: string[]): Promise<InspectionCreateResponse> {
      const form = new FormData();
      imageUris.forEach((uri, i) => appendFile(form, uri, `img_${i}.jpg`));
      // NOTE: do NOT set Content-Type manually here — axios/RN FormData must
      // append the multipart boundary string itself, otherwise FastAPI/Starlette
      // will reject the body with a 400/422.
      const { data } = await http.post<InspectionCreateResponse>(
        '/api/v1/inspect?mode=async',
        form,
        {
          timeout: 60_000,
          transformRequest: (d) => d, // prevent axios from JSON.stringifying FormData
        },
      );
      return data;
    },

    async createSync(imageUri: string): Promise<SyncInspectionResponse> {
      const form = new FormData();
      appendFile(form, imageUri, 'img.jpg');
      const { data } = await http.post<SyncInspectionResponse>(
        '/api/v1/inspect?mode=sync',
        form,
        {
          timeout: 90_000,
          transformRequest: (d) => d,
        },
      );
      return data;
    },

    async get(inspectionId: string): Promise<InspectionStatusResponse> {
      const { data } = await http.get<InspectionStatusResponse>(
        `/api/v1/inspect/${encodeURIComponent(inspectionId)}`,
      );
      return data;
    },

    async list(opts: { page?: number; pageSize?: number } = {}): Promise<InspectionListResponse> {
      const { page = 1, pageSize = 20 } = opts;
      const { data } = await http.get<InspectionListResponse>(
        `/api/v1/inspect?page=${page}&page_size=${pageSize}`,
      );
      return data;
    },

    visualizationUrl(
      inspectionId: string,
      type: 'annotated' | 'parts' | 'damages',
    ): string {
      return `${API_BASE}/api/v1/inspect/${encodeURIComponent(inspectionId)}/visualization/${type}`;
    },
  },

  // Legacy helpers — required by older screens (CaptureFlow / Results / History.tsx).
  async createInspection(imageUris: string[]): Promise<string> {
    const res = await api.inspections.createAsync(imageUris);
    return res.inspection_id;
  },
  async getInspection(id: string): Promise<InspectionStatusResponse> {
    return api.inspections.get(id);
  },
  async listInspections(opts?: { page?: number; pageSize?: number }): Promise<InspectionListResponse> {
    return api.inspections.list(opts);
  },
  async syncInspect(uri: string): Promise<SyncInspectionResponse> {
    return api.inspections.createSync(uri);
  },
  visualizationUrl(id: string, type: 'annotated' | 'parts' | 'damages'): string {
    return api.inspections.visualizationUrl(id, type);
  },
};

// ---- Error helper -----------------------------------------------------------

export function describeError(err: unknown, fallback = 'unknownError'): string {
  if (axios.isAxiosError(err)) {
    if (err.response?.data) {
      const data = err.response.data as { detail?: string; message?: string };
      if (data.detail) return data.detail;
      if (data.message) return data.message;
    }
    if (err.code === 'ECONNABORTED' || err.message?.includes('Network')) {
      return 'networkError';
    }
    return err.message || fallback;
  }
  if (err instanceof Error) return err.message;
  return fallback;
}

// ---- Legacy helpers preserved for existing screens --------------------------

export async function createInspection(imageUris: string[]): Promise<string> {
  const res = await api.inspections.createAsync(imageUris);
  return res.inspection_id;
}

export async function getInspection(
  inspectionId: string,
): Promise<InspectionStatusResponse> {
  return api.inspections.get(inspectionId);
}

export default api;
