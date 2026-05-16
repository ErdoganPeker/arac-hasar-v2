import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { AlertTriangle } from 'lucide-react';
import { Button, type ButtonVariant } from './Button';
import { cn } from '../utils/cn';

export interface ConfirmOptions {
  title: string;
  description?: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: 'default' | 'danger';
  icon?: ReactNode;
}

interface PendingConfirm extends ConfirmOptions {
  resolve: (ok: boolean) => void;
}

/**
 * Mount one <ConfirmDialogProvider /> near the app root. Then anywhere in the
 * tree call `useConfirm()` and `await confirm({ title, description, ... })`.
 *
 * Promise resolves to `true` if confirmed, `false` if cancelled / dismissed.
 */
let pushPending: ((p: PendingConfirm) => void) | null = null;

export function ConfirmDialogProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<PendingConfirm | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    pushPending = (p) => setPending(p);
    return () => {
      pushPending = null;
    };
  }, []);

  const handleClose = useCallback(
    (ok: boolean) => {
      if (!pending) return;
      pending.resolve(ok);
      setPending(null);
    },
    [pending],
  );

  // ESC to cancel, focus trap to first focusable on open
  useEffect(() => {
    if (!pending) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleClose(false);
    };
    window.addEventListener('keydown', onKey);
    // Move focus into the dialog
    const t = setTimeout(() => {
      const btn = dialogRef.current?.querySelector<HTMLButtonElement>(
        'button[data-confirm-primary]',
      );
      btn?.focus();
    }, 0);
    return () => {
      window.removeEventListener('keydown', onKey);
      clearTimeout(t);
    };
  }, [pending, handleClose]);

  if (!pending || typeof document === 'undefined') return <>{children}</>;

  const confirmVariant: ButtonVariant = pending.variant === 'danger' ? 'danger' : 'primary';

  return (
    <>
      {children}
      {createPortal(
        <div
          className="fixed inset-0 z-modal flex items-center justify-center p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="confirm-title"
        >
          {/* backdrop */}
          <div
            className="absolute inset-0 bg-slate-900/60 animate-fade-in"
            onClick={() => handleClose(false)}
            aria-hidden
          />
          <div
            ref={dialogRef}
            className={cn(
              'relative z-10 w-full max-w-md rounded-xl bg-white shadow-xl animate-slide-up',
            )}
          >
            <div className="flex items-start gap-3 p-5">
              <div
                className={cn(
                  'flex h-10 w-10 flex-none items-center justify-center rounded-full',
                  pending.variant === 'danger'
                    ? 'bg-red-100 text-red-700'
                    : 'bg-brand-100 text-brand-700',
                )}
                aria-hidden
              >
                {pending.icon ?? <AlertTriangle className="h-5 w-5" />}
              </div>
              <div className="flex-1">
                <h2 id="confirm-title" className="text-base font-semibold text-slate-900">
                  {pending.title}
                </h2>
                {pending.description && (
                  <div className="mt-1 text-sm text-slate-600">{pending.description}</div>
                )}
              </div>
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-slate-100 px-5 py-3">
              <Button variant="ghost" onClick={() => handleClose(false)}>
                {pending.cancelLabel ?? 'Vazgeç'}
              </Button>
              <Button
                variant={confirmVariant}
                data-confirm-primary
                onClick={() => handleClose(true)}
              >
                {pending.confirmLabel ?? 'Onayla'}
              </Button>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}

/**
 * Hook returning a promise-based `confirm()` function.
 * Requires <ConfirmDialogProvider /> to be mounted higher in the tree.
 */
export function useConfirm() {
  return useCallback((opts: ConfirmOptions): Promise<boolean> => {
    return new Promise<boolean>((resolve) => {
      if (!pushPending) {
        // Provider not mounted — fall back to native confirm()
        if (typeof window !== 'undefined' && typeof window.confirm === 'function') {
          resolve(window.confirm(opts.title));
        } else {
          resolve(false);
        }
        return;
      }
      pushPending({ ...opts, resolve });
    });
  }, []);
}
