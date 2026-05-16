/**
 * Model selection state for the inspection pipeline.
 *
 * The header dropdown lets a demo user switch between the upstream
 * pre-trained YOLO weights and the custom weights we fine-tuned on
 * Turkish-market vehicles. The chosen model id is:
 *
 *   1. persisted in localStorage so it survives a hard reload, and
 *   2. injected as `?model=<id>` on every `POST /api/v1/inspect` call.
 *
 * Backend exposes `GET /api/v1/models` to enumerate the available models.
 * If that endpoint is not yet live (parallel backend work), we fall back
 * to a hardcoded list so the UI still works in dev.
 */
import axios from 'axios';
import { API_BASE_URL, getStoredAccessToken } from './api';

export type ModelKind = 'pretrained' | 'custom';

export interface ModelOption {
  id: string;
  label: string;
  kind: ModelKind;
  /** Optional secondary line (e.g. "YOLOv8-seg · 80 sınıf"). */
  description?: string;
  /** True when this is the recommended default. */
  recommended?: boolean;
}

const STORAGE_KEY = 'selected_model';

/**
 * Hardcoded fallback used when `/api/v1/models` is unreachable. The first
 * entry of `kind: 'custom'` is the documented MVP default and gets
 * `recommended: true` so the UI badges it.
 */
export const FALLBACK_MODELS: ModelOption[] = [
  {
    id: 'custom-yolo26-seg',
    label: 'Kendi Modelim',
    kind: 'custom',
    description: 'YOLO26-seg · TR araç hasar fine-tune',
    recommended: true,
  },
  {
    id: 'pretrained-yolo26',
    label: 'Pre-trained',
    kind: 'pretrained',
    description: 'YOLO26 · COCO weights',
  },
];

export const DEFAULT_MODEL_ID = FALLBACK_MODELS[0]!.id;

function isBrowser(): boolean {
  return typeof window !== 'undefined';
}

export function getSelectedModelId(): string {
  if (!isBrowser()) return DEFAULT_MODEL_ID;
  try {
    return localStorage.getItem(STORAGE_KEY) || DEFAULT_MODEL_ID;
  } catch {
    return DEFAULT_MODEL_ID;
  }
}

export function setSelectedModelId(id: string): void {
  if (!isBrowser()) return;
  try {
    localStorage.setItem(STORAGE_KEY, id);
    // Broadcast to other listeners in the same tab. The native `storage`
    // event only fires across tabs.
    window.dispatchEvent(new CustomEvent('selected_model_change', { detail: id }));
  } catch {
    /* localStorage unavailable: silently degrade */
  }
}

/**
 * Best-effort fetch of the available models. Never throws — on any
 * failure (network, 401, 404, malformed payload) we return the hardcoded
 * fallback so the dropdown is never empty.
 */
export async function fetchAvailableModels(opts: {
  signal?: AbortSignal;
} = {}): Promise<ModelOption[]> {
  try {
    const token = getStoredAccessToken();
    const res = await axios.get<unknown>(`${API_BASE_URL}/api/v1/models`, {
      timeout: 6_000,
      signal: opts.signal,
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    });
    const parsed = parseModelsPayload(res.data);
    if (parsed.length > 0) return parsed;
    return FALLBACK_MODELS;
  } catch {
    return FALLBACK_MODELS;
  }
}

/**
 * Tolerant parser — backend hasn't pinned the response shape yet, so we
 * accept any of:
 *   - { models: [...] }
 *   - [...]
 *   - { items: [...] }
 * with item shape { id, name?|label?, kind?, description?, recommended? }.
 */
function parseModelsPayload(data: unknown): ModelOption[] {
  if (!data) return [];
  let arr: unknown[] = [];
  if (Array.isArray(data)) {
    arr = data;
  } else if (typeof data === 'object') {
    const d = data as Record<string, unknown>;
    if (Array.isArray(d.models)) arr = d.models;
    else if (Array.isArray(d.items)) arr = d.items;
  }
  const out: ModelOption[] = [];
  for (const raw of arr) {
    if (!raw || typeof raw !== 'object') continue;
    const r = raw as Record<string, unknown>;
    const id = typeof r.id === 'string' ? r.id : null;
    if (!id) continue;
    const label =
      typeof r.label === 'string'
        ? r.label
        : typeof r.name === 'string'
          ? r.name
          : id;
    const kindRaw = typeof r.kind === 'string' ? r.kind.toLowerCase() : '';
    const idLower = id.toLowerCase();
    const kind: ModelKind =
      kindRaw === 'pretrained'
        ? 'pretrained'
        : kindRaw === 'custom'
          ? 'custom'
          : idLower.includes('pretrain') || idLower.includes('coco')
            ? 'pretrained'
            : 'custom';
    out.push({
      id,
      label,
      kind,
      description:
        typeof r.description === 'string' ? r.description : undefined,
      recommended: r.recommended === true,
    });
  }
  return out;
}

/**
 * Subscribe to selected-model changes (both same-tab CustomEvent and
 * cross-tab `storage` events). Returns an unsubscribe function.
 */
export function subscribeSelectedModel(cb: (id: string) => void): () => void {
  if (!isBrowser()) return () => {};
  const onCustom = (e: Event) => {
    const detail = (e as CustomEvent<string>).detail;
    if (typeof detail === 'string') cb(detail);
  };
  const onStorage = (e: StorageEvent) => {
    if (e.key === STORAGE_KEY && typeof e.newValue === 'string') {
      cb(e.newValue);
    }
  };
  window.addEventListener('selected_model_change', onCustom);
  window.addEventListener('storage', onStorage);
  return () => {
    window.removeEventListener('selected_model_change', onCustom);
    window.removeEventListener('storage', onStorage);
  };
}
