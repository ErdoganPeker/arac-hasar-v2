/**
 * Tab-scoped cache of the photos the user just uploaded so the results
 * page can show what they submitted while the backend is still working
 * (and even after, for async inspections where the backend does not
 * return the original image URL).
 *
 * - Storage: sessionStorage (per-tab, cleared on tab close).
 * - Total cap: ~2 MB to stay well under the typical 5 MB browser quota.
 * - Per-image cap: 1024px longest edge, JPEG q=0.8.
 */

const STORAGE_KEY_PREFIX = 'arac_hasar_uploaded_';
const MAX_TOTAL_BYTES = 2 * 1024 * 1024;
const MAX_EDGE_PX = 1024;
const JPEG_QUALITY = 0.8;

export interface UploadedPreview {
  name: string;
  dataUrl: string;
}

function storageKey(inspectionId: string): string {
  return `${STORAGE_KEY_PREFIX}${inspectionId}`;
}

async function fileToResizedDataUrl(file: File): Promise<string | null> {
  if (typeof window === 'undefined') return null;
  if (!file.type.startsWith('image/')) return null;
  const objectUrl = URL.createObjectURL(file);
  try {
    const img = await loadImage(objectUrl);
    const { width, height } = img;
    const longest = Math.max(width, height);
    const scale = longest > MAX_EDGE_PX ? MAX_EDGE_PX / longest : 1;
    const targetW = Math.max(1, Math.round(width * scale));
    const targetH = Math.max(1, Math.round(height * scale));

    const canvas = document.createElement('canvas');
    canvas.width = targetW;
    canvas.height = targetH;
    const ctx = canvas.getContext('2d');
    if (!ctx) return null;
    ctx.drawImage(img, 0, 0, targetW, targetH);
    return canvas.toDataURL('image/jpeg', JPEG_QUALITY);
  } catch {
    return null;
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = reject;
    img.src = src;
  });
}

export async function stashUploadedPreviews(
  inspectionId: string,
  files: File[],
): Promise<void> {
  if (typeof window === 'undefined') return;
  const previews: UploadedPreview[] = [];
  let totalBytes = 0;
  for (const f of files) {
    const dataUrl = await fileToResizedDataUrl(f);
    if (!dataUrl) continue;
    // ~3/4 of base64 length is the decoded byte size; ignore data: prefix.
    const approxBytes = Math.floor((dataUrl.length - 23) * 0.75);
    if (totalBytes + approxBytes > MAX_TOTAL_BYTES) break;
    previews.push({ name: f.name, dataUrl });
    totalBytes += approxBytes;
  }
  try {
    sessionStorage.setItem(storageKey(inspectionId), JSON.stringify(previews));
  } catch {
    // Quota exceeded — drop silently; results page falls back to no
    // preview.
  }
}

export function getUploadedPreviews(inspectionId: string): UploadedPreview[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = sessionStorage.getItem(storageKey(inspectionId));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (p): p is UploadedPreview =>
        p &&
        typeof p === 'object' &&
        typeof p.name === 'string' &&
        typeof p.dataUrl === 'string',
    );
  } catch {
    return [];
  }
}

export function clearUploadedPreviews(inspectionId: string): void {
  if (typeof window === 'undefined') return;
  try {
    sessionStorage.removeItem(storageKey(inspectionId));
  } catch {
    /* ignore */
  }
}
