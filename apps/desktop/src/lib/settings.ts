/**
 * Desktop ayarları — Tauri Store eklentisiyle disk-persistent KV.
 * Tarayıcıda fallback olarak localStorage kullanır.
 *
 * NOTE: auth tokens are kept in a separate store file (`auth.json`, see `auth-store.ts`)
 * so user settings can be backed up/exported independently of secrets.
 */
import { Store } from '@tauri-apps/plugin-store';

let storePromise: Promise<Store> | null = null;

async function getStore(): Promise<Store | null> {
  if (typeof window === 'undefined') return null;
  if (!('__TAURI_INTERNALS__' in window)) return null;
  try {
    if (!storePromise) {
      storePromise = Store.load('settings.json', { autoSave: true, defaults: {} });
    }
    return await storePromise;
  } catch {
    return null;
  }
}

export type UploadMode = 'sync' | 'async';

export interface AppSettings {
  apiUrl: string;
  apiKey: string | null;
  uiLanguage: 'tr' | 'en';
  theme: 'light' | 'dark' | 'system';
  defaultUploadMode: UploadMode;
  sidebarCollapsed: boolean;
}

const DEFAULTS: AppSettings = {
  apiUrl: 'http://localhost:8000',
  apiKey: null,
  uiLanguage: 'tr',
  theme: 'system',
  defaultUploadMode: 'async',
  sidebarCollapsed: false,
};

export async function loadSettings(): Promise<AppSettings> {
  const store = await getStore();
  if (!store) {
    const raw = localStorage.getItem('arac-hasar-settings');
    return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : DEFAULTS;
  }
  const out: AppSettings = { ...DEFAULTS };
  const bag = out as unknown as Record<string, unknown>;
  for (const key of Object.keys(DEFAULTS) as (keyof AppSettings)[]) {
    const v = await store.get(key);
    if (v !== undefined && v !== null) bag[key] = v;
  }
  return out;
}

export async function saveSetting<K extends keyof AppSettings>(
  key: K,
  value: AppSettings[K],
): Promise<void> {
  const store = await getStore();
  if (!store) {
    const raw = localStorage.getItem('arac-hasar-settings');
    const cur = raw ? JSON.parse(raw) : {};
    localStorage.setItem('arac-hasar-settings', JSON.stringify({ ...cur, [key]: value }));
    return;
  }
  await store.set(key as string, value);
  await store.save();
}
