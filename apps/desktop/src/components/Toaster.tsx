/**
 * Toaster — lightweight bottom-right notification stack.
 *
 * Subscribes to two app-level CustomEvents:
 *  - `hasarui:toast`              { kind: 'info'|'success'|'error', message }
 *  - `hasarui:file-size-rejected` { rejected: {name,size}[], maxMb }
 *
 * Pages can fire `window.dispatchEvent(new CustomEvent('hasarui:toast', { detail: ... }))`
 * without importing this module — keeps the toast surface decoupled.
 */
import { useEffect, useState, useCallback } from 'react';
import { AlertTriangle, CheckCircle2, Info, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';

type ToastKind = 'info' | 'success' | 'error';

interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

let nextId = 1;

export default function Toaster() {
  const { t } = useTranslation();
  const [toasts, setToasts] = useState<Toast[]>([]);

  const push = useCallback((kind: ToastKind, message: string) => {
    const id = nextId++;
    setToasts((cur) => [...cur, { id, kind, message }]);
    window.setTimeout(() => {
      setToasts((cur) => cur.filter((x) => x.id !== id));
    }, 5000);
  }, []);

  useEffect(() => {
    function onToast(e: Event) {
      const ev = e as CustomEvent<{ kind?: ToastKind; message: string }>;
      if (!ev.detail?.message) return;
      push(ev.detail.kind ?? 'info', ev.detail.message);
    }
    function onSizeRejected(e: Event) {
      const ev = e as CustomEvent<{
        rejected: { name: string; size: number }[];
        maxMb: number;
      }>;
      const r = ev.detail?.rejected ?? [];
      if (!r.length) return;
      const msg =
        r.length === 1
          ? t('errors.fileTooLargeOne', { name: r[0]?.name ?? '', maxMb: ev.detail.maxMb })
          : t('errors.fileTooLarge', { count: r.length, maxMb: ev.detail.maxMb });
      push('error', msg);
    }
    window.addEventListener('hasarui:toast', onToast as EventListener);
    window.addEventListener('hasarui:file-size-rejected', onSizeRejected as EventListener);
    return () => {
      window.removeEventListener('hasarui:toast', onToast as EventListener);
      window.removeEventListener(
        'hasarui:file-size-rejected',
        onSizeRejected as EventListener,
      );
    };
  }, [push, t]);

  if (toasts.length === 0) return null;

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`pointer-events-auto flex items-start gap-2 rounded-lg border px-3 py-2 text-sm shadow-lg backdrop-blur ${
            toast.kind === 'error'
              ? 'border-red-200 bg-red-50/95 text-red-900 dark:border-red-800 dark:bg-red-900/80 dark:text-red-100'
              : toast.kind === 'success'
                ? 'border-emerald-200 bg-emerald-50/95 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-900/80 dark:text-emerald-100'
                : 'border-slate-200 bg-white/95 text-slate-800 dark:border-slate-700 dark:bg-slate-800/95 dark:text-slate-100'
          }`}
        >
          <span className="mt-0.5 shrink-0">
            {toast.kind === 'error' ? (
              <AlertTriangle className="h-4 w-4" />
            ) : toast.kind === 'success' ? (
              <CheckCircle2 className="h-4 w-4" />
            ) : (
              <Info className="h-4 w-4" />
            )}
          </span>
          <div className="flex-1 leading-snug">{toast.message}</div>
          <button
            type="button"
            onClick={() => setToasts((cur) => cur.filter((x) => x.id !== toast.id))}
            className="rounded p-0.5 opacity-60 hover:opacity-100"
            aria-label="dismiss"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}
