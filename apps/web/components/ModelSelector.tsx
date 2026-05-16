'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Check, ChevronDown, Cpu, Sparkles } from 'lucide-react';
import {
  DEFAULT_MODEL_ID,
  fetchAvailableModels,
  getSelectedModelId,
  setSelectedModelId,
  subscribeSelectedModel,
  type ModelOption,
} from '@/lib/models';

/**
 * Header-mounted model picker. Drives the `?model=<id>` param appended to
 * every `POST /api/v1/inspect` call (see lib/api.ts).
 *
 * - Loads the catalog from `GET /api/v1/models`; falls back to a hardcoded
 *   list when the endpoint is offline (parallel backend work).
 * - Selection persists in localStorage.
 * - A subtle "demo" badge on the trigger makes this prominent on stage.
 */
export function ModelSelector() {
  const t = useTranslations('nav.modelSelector');
  const [models, setModels] = useState<ModelOption[]>([]);
  const [selectedId, setSelectedId] = useState<string>(() =>
    getSelectedModelId(),
  );
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const rootRef = useRef<HTMLDivElement>(null);

  // Initial catalog fetch + react to cross-tab changes.
  useEffect(() => {
    const ac = new AbortController();
    (async () => {
      const items = await fetchAvailableModels({ signal: ac.signal });
      setModels(items);
      setLoading(false);
      // If our cached id isn't in the catalog, fall back to the first item
      // (preferring `recommended`) and persist the correction.
      const current = getSelectedModelId();
      if (!items.find((m) => m.id === current)) {
        const next =
          items.find((m) => m.recommended)?.id ?? items[0]?.id ?? DEFAULT_MODEL_ID;
        setSelectedModelId(next);
        setSelectedId(next);
      }
    })();
    const unsub = subscribeSelectedModel((id) => setSelectedId(id));
    return () => {
      ac.abort();
      unsub();
    };
  }, []);

  // Close on outside click / Esc.
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onClick);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onClick);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const selected = useMemo<ModelOption | null>(
    () => models.find((m) => m.id === selectedId) ?? null,
    [models, selectedId],
  );

  function pick(id: string) {
    setSelectedModelId(id);
    setSelectedId(id);
    setOpen(false);
  }

  const triggerLabel = selected
    ? selected.kind === 'pretrained'
      ? t('pretrained')
      : t('custom')
    : t('label');

  const TriggerIcon = selected?.kind === 'pretrained' ? Cpu : Sparkles;

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={t('label')}
        className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-sm transition-colors hover:border-slate-300 hover:text-slate-900 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
        title={selected?.description ?? t('label')}
      >
        <TriggerIcon className="h-3.5 w-3.5 text-brand-600" aria-hidden />
        <span className="hidden sm:inline text-[11px] uppercase tracking-wider text-slate-400">
          {t('label')}:
        </span>
        <span className="max-w-[120px] truncate">{triggerLabel}</span>
        {selected?.recommended && (
          <span
            className="ml-0.5 hidden rounded-full bg-brand-100 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-brand-800 sm:inline"
            aria-label={t('recommended')}
          >
            {t('demoBadge')}
          </span>
        )}
        <ChevronDown
          className={`h-3.5 w-3.5 text-slate-400 transition-transform ${
            open ? 'rotate-180' : ''
          }`}
          aria-hidden
        />
      </button>

      {open && (
        <div
          role="listbox"
          aria-label={t('label')}
          className="absolute right-0 z-40 mt-1.5 w-72 origin-top-right overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg ring-1 ring-black/5"
        >
          <div className="border-b border-slate-100 px-3 py-2">
            <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              {t('heading')}
            </p>
            <p className="mt-0.5 text-xs text-slate-500">{t('hint')}</p>
          </div>
          <ul className="max-h-80 overflow-y-auto py-1">
            {loading && models.length === 0 && (
              <li className="px-3 py-2 text-xs text-slate-400">
                {t('loading')}
              </li>
            )}
            {models.map((m) => {
              const active = m.id === selectedId;
              const Icon = m.kind === 'pretrained' ? Cpu : Sparkles;
              return (
                <li key={m.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={active}
                    onClick={() => pick(m.id)}
                    className={`flex w-full items-start gap-2.5 px-3 py-2 text-left transition-colors ${
                      active
                        ? 'bg-brand-50 text-brand-900'
                        : 'text-slate-700 hover:bg-slate-50'
                    }`}
                  >
                    <span
                      className={`mt-0.5 flex h-7 w-7 flex-none items-center justify-center rounded-lg ${
                        active
                          ? 'bg-brand-600 text-white'
                          : 'bg-slate-100 text-slate-500'
                      }`}
                    >
                      <Icon className="h-3.5 w-3.5" aria-hidden />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-1.5">
                        <span className="text-sm font-medium">{m.label}</span>
                        {m.recommended && (
                          <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider text-amber-800">
                            {t('recommended')}
                          </span>
                        )}
                      </span>
                      <span className="mt-0.5 block text-[11px] text-slate-500">
                        {m.description ?? m.id}
                      </span>
                    </span>
                    {active && (
                      <Check className="mt-1 h-4 w-4 flex-none text-brand-600" aria-hidden />
                    )}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
