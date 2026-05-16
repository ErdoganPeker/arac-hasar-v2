/**
 * Typed wrappers around Tauri `invoke` commands.
 * On web (Vite dev outside Tauri) these all degrade gracefully so the app stays runnable.
 */
import { invoke } from '@tauri-apps/api/core';

export interface AppInfo {
  name: string;
  version: string;
  platform: string;
}

const isTauri = (): boolean =>
  typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;

export async function appInfo(): Promise<AppInfo> {
  if (!isTauri()) {
    return { name: 'Hasarİ', version: '0.1.0', platform: 'web' };
  }
  return invoke<AppInfo>('app_info');
}

export async function pickFilesNative(): Promise<string[]> {
  if (!isTauri()) return [];
  return invoke<string[]>('pick_files');
}

export async function pickFolderNative(): Promise<string | null> {
  if (!isTauri()) return null;
  const r = await invoke<string | null>('pick_folder');
  return r ?? null;
}

export async function readImageBytes(path: string): Promise<Uint8Array> {
  if (!isTauri()) throw new Error('read_image yalnızca masaüstü uygulamasında çalışır');
  const bytes = await invoke<number[]>('read_image', { path });
  return new Uint8Array(bytes);
}

export async function saveReport(opts: {
  inspectionId: string;
  format: 'csv' | 'pdf' | 'json' | 'txt';
  /** UTF-8 string for csv/json/txt, base64 string for pdf */
  content: string;
}): Promise<string | null> {
  if (!isTauri()) {
    // Web fallback: download via blob
    const blob =
      opts.format === 'pdf'
        ? base64ToBlob(opts.content, 'application/pdf')
        : new Blob([opts.content], {
            type:
              opts.format === 'csv'
                ? 'text/csv'
                : opts.format === 'json'
                  ? 'application/json'
                  : 'text/plain',
          });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `inspection_${opts.inspectionId}.${opts.format}`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return null;
  }
  try {
    return await invoke<string>('save_report', {
      inspectionId: opts.inspectionId,
      format: opts.format,
      content: opts.content,
    });
  } catch (e) {
    if (String(e).includes('İptal')) return null;
    throw e;
  }
}

export async function openInExplorer(path: string): Promise<void> {
  if (!isTauri()) return;
  await invoke('open_in_explorer', { path });
}

export async function showNotification(title: string, body: string): Promise<void> {
  if (!isTauri()) {
    // Web fallback: best-effort native Notification API
    if ('Notification' in window) {
      if (Notification.permission === 'granted') new Notification(title, { body });
      else if (Notification.permission !== 'denied') {
        const r = await Notification.requestPermission();
        if (r === 'granted') new Notification(title, { body });
      }
    }
    return;
  }
  await invoke('show_notification', { title, body });
}

function base64ToBlob(b64: string, type: string): Blob {
  const bin = atob(b64);
  const arr = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
  return new Blob([arr], { type });
}

/** Converts an absolute file path on disk to a File the API client can upload. */
export async function pathToFile(path: string): Promise<File> {
  const bytes = await readImageBytes(path);
  const name = path.split(/[\\/]/).pop() ?? 'image.jpg';
  const ext = name.split('.').pop()?.toLowerCase() ?? 'jpg';
  const type =
    ext === 'png' ? 'image/png' : ext === 'webp' ? 'image/webp' : 'image/jpeg';
  return new File([bytes], name, { type });
}
