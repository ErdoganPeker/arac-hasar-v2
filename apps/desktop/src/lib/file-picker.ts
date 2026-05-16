/**
 * Native file picker — delegates to the Rust `pick_files` / `pick_folder` commands
 * so the dialog is consistent with the rest of the desktop UX. Falls back to an
 * HTML `<input type="file">` when running outside Tauri (Vite web dev).
 *
 * Files larger than `MAX_FILE_SIZE_MB` are silently dropped from the result and
 * surfaced through `hasarui:file-size-rejected` so the UI can toast a warning
 * without each call site re-implementing size logic.
 */
import { pickFilesNative, pickFolderNative, pathToFile } from './commands';

export interface PickedFile {
  path: string;
  name: string;
  data: Uint8Array;
}

/** Mirrors backend FastAPI limit (kept in sync with UploadDropzone default). */
export const MAX_FILE_SIZE_MB = 12;
const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

function filterBySize(files: File[]): File[] {
  const accepted: File[] = [];
  const rejected: { name: string; size: number }[] = [];
  for (const f of files) {
    if (f.size > MAX_FILE_SIZE_BYTES) rejected.push({ name: f.name, size: f.size });
    else accepted.push(f);
  }
  if (rejected.length && typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent('hasarui:file-size-rejected', {
        detail: { rejected, maxMb: MAX_FILE_SIZE_MB },
      }),
    );
  }
  return accepted;
}

export async function pickImages(opts: { multiple?: boolean } = {}): Promise<File[]> {
  if (!('__TAURI_INTERNALS__' in window)) {
    const picked = await webFallback(opts.multiple ?? true);
    return filterBySize(picked);
  }
  const paths = await pickFilesNative();
  if (!paths.length) return [];
  const limited = opts.multiple === false ? paths.slice(0, 1) : paths;
  const files = await Promise.all(limited.map((p) => pathToFile(p)));
  return filterBySize(files);
}

export async function pickFolder(): Promise<string | null> {
  if (!('__TAURI_INTERNALS__' in window)) {
    alert('Klasör seçimi yalnızca masaüstü uygulamasında çalışır.');
    return null;
  }
  return pickFolderNative();
}

function webFallback(multiple: boolean): Promise<File[]> {
  return new Promise((resolve) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.multiple = multiple;
    input.onchange = () => {
      resolve(input.files ? Array.from(input.files) : []);
    };
    input.click();
  });
}
