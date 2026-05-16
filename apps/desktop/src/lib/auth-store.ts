/**
 * Auth token persistence — Tauri Store (encrypted on disk via plugin-store).
 * Falls back to in-memory object on web (dev mode) so the app is testable from `pnpm dev`.
 *
 * IMPORTANT: never use localStorage for tokens here — Tauri Store is what the spec mandates.
 */
import { Store } from '@tauri-apps/plugin-store';
import type { AuthTokens, User } from '@arac-hasar/types';

let storePromise: Promise<Store> | null = null;

async function getStore(): Promise<Store | null> {
  if (typeof window === 'undefined') return null;
  if (!('__TAURI_INTERNALS__' in window)) return null;
  try {
    if (!storePromise) {
      storePromise = Store.load('auth.json', { autoSave: true, defaults: {} });
    }
    return await storePromise;
  } catch {
    return null;
  }
}

// Web-fallback memory bag (only used when running outside Tauri).
const memBag: Record<string, unknown> = {};

async function rawGet<T>(key: string): Promise<T | null> {
  const s = await getStore();
  if (!s) return (memBag[key] as T) ?? null;
  return ((await s.get(key)) as T) ?? null;
}

async function rawSet(key: string, value: unknown): Promise<void> {
  const s = await getStore();
  if (!s) {
    memBag[key] = value;
    return;
  }
  await s.set(key, value);
  await s.save();
}

async function rawDelete(key: string): Promise<void> {
  const s = await getStore();
  if (!s) {
    delete memBag[key];
    return;
  }
  await s.delete(key);
  await s.save();
}

export interface PersistedAuth {
  user: User;
  tokens: AuthTokens;
}

export async function loadAuth(): Promise<PersistedAuth | null> {
  const tokens = await rawGet<AuthTokens>('tokens');
  const user = await rawGet<User>('user');
  if (!tokens || !user) return null;
  return { tokens, user };
}

export async function saveAuth(data: PersistedAuth): Promise<void> {
  await rawSet('tokens', data.tokens);
  await rawSet('user', data.user);
}

export async function clearAuth(): Promise<void> {
  await rawDelete('tokens');
  await rawDelete('user');
}

export async function updateTokens(tokens: AuthTokens): Promise<void> {
  await rawSet('tokens', tokens);
}
