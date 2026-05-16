/**
 * services/auth.ts — Token storage using expo-secure-store.
 *
 * On native: tokens are stored in iOS Keychain / Android EncryptedSharedPreferences.
 * On web (Expo web fallback) SecureStore is unavailable — falls back to memory map.
 */
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const ACCESS_KEY = 'hasari_access_token';
const REFRESH_KEY = 'hasari_refresh_token';
const USER_KEY = 'hasari_user';

const memoryStore: Record<string, string | null> = {};

const isSecureStoreAvailable = Platform.OS !== 'web';

async function read(key: string): Promise<string | null> {
  if (!isSecureStoreAvailable) {
    return memoryStore[key] ?? null;
  }
  try {
    return await SecureStore.getItemAsync(key);
  } catch {
    return null;
  }
}

async function write(key: string, value: string | null): Promise<void> {
  if (!isSecureStoreAvailable) {
    memoryStore[key] = value;
    return;
  }
  try {
    if (value == null) {
      await SecureStore.deleteItemAsync(key);
    } else {
      await SecureStore.setItemAsync(key, value);
    }
  } catch {
    /* swallow */
  }
}

export interface AuthUser {
  id?: string | number;
  email: string;
  full_name?: string;
  company?: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token?: string;
}

// ---- Token primitives -------------------------------------------------------

export async function getAccessToken(): Promise<string | null> {
  return read(ACCESS_KEY);
}

export async function getRefreshToken(): Promise<string | null> {
  return read(REFRESH_KEY);
}

export async function setTokens(pair: TokenPair): Promise<void> {
  await write(ACCESS_KEY, pair.access_token ?? null);
  if (pair.refresh_token !== undefined) {
    await write(REFRESH_KEY, pair.refresh_token ?? null);
  }
}

export async function clearTokens(): Promise<void> {
  await write(ACCESS_KEY, null);
  await write(REFRESH_KEY, null);
  await write(USER_KEY, null);
}

export async function isAuthenticated(): Promise<boolean> {
  const t = await getAccessToken();
  return Boolean(t && t.length > 0);
}

// Aliases requested in spec
export const getToken = getAccessToken;
export const setToken = (token: string) => setTokens({ access_token: token });
export const clearToken = clearTokens;

// ---- Cached user profile ----------------------------------------------------

export async function setCachedUser(user: AuthUser | null): Promise<void> {
  await write(USER_KEY, user ? JSON.stringify(user) : null);
}

export async function getCachedUser(): Promise<AuthUser | null> {
  const raw = await read(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}
