import type { ReactNode } from 'react';
import { Clock, Loader2, History, RefreshCw, AlertCircle } from 'lucide-react';
import { cn } from '../utils/cn';

export type PendingStateVariant = 'polling' | 'queued' | 'timeout' | 'error';

interface Props {
  variant?: PendingStateVariant;
  title?: string;
  description?: string;
  /** Show "Yeniden dene" button — wires `onRetry` callback */
  onRetry?: () => void;
  /** Show "Geçmiş'ten kontrol et" button — wires `onCheckHistory` callback */
  onCheckHistory?: () => void;
  /** Additional content rendered below the actions */
  children?: ReactNode;
  className?: string;
}

const VARIANT_CONFIG: Record<
  PendingStateVariant,
  {
    icon: typeof Clock;
    iconSpin: boolean;
    bg: string;
    ring: string;
    iconBg: string;
    iconColor: string;
    titleColor: string;
    defaultTitle: string;
    defaultDescription: string;
  }
> = {
  polling: {
    icon: Loader2,
    iconSpin: true,
    bg: 'bg-blue-50',
    ring: 'ring-blue-200',
    iconBg: 'bg-blue-100',
    iconColor: 'text-blue-700',
    titleColor: 'text-blue-950',
    defaultTitle: 'İnceleme işleniyor',
    defaultDescription:
      'Fotoğraflar analiz ediliyor. Bu işlem birkaç saniye sürebilir, sayfayı kapatmayın.',
  },
  queued: {
    icon: Clock,
    iconSpin: false,
    bg: 'bg-slate-50',
    ring: 'ring-slate-200',
    iconBg: 'bg-slate-200',
    iconColor: 'text-slate-700',
    titleColor: 'text-slate-900',
    defaultTitle: 'Sırada',
    defaultDescription: 'İncelemeniz sırada bekliyor, kısa süre içinde başlayacak.',
  },
  timeout: {
    icon: Clock,
    iconSpin: false,
    bg: 'bg-amber-50',
    ring: 'ring-amber-200',
    iconBg: 'bg-amber-100',
    iconColor: 'text-amber-800',
    titleColor: 'text-amber-950',
    defaultTitle: 'İnceleme arka planda devam ediyor',
    defaultDescription:
      'Sonuç beklenenden uzun sürdü. İşlem arka planda tamamlanacak — geçmiş ekranınızdan kontrol edebilir veya yeniden deneyebilirsiniz.',
  },
  error: {
    icon: AlertCircle,
    iconSpin: false,
    bg: 'bg-red-50',
    ring: 'ring-red-200',
    iconBg: 'bg-red-100',
    iconColor: 'text-red-700',
    titleColor: 'text-red-950',
    defaultTitle: 'İnceleme başarısız oldu',
    defaultDescription:
      'Sonuç alınırken bir hata oluştu. Lütfen yeniden deneyin.',
  },
};

export function PendingState({
  variant = 'polling',
  title,
  description,
  onRetry,
  onCheckHistory,
  children,
  className,
}: Props) {
  const cfg = VARIANT_CONFIG[variant];
  const Icon = cfg.icon;
  return (
    <section
      role="status"
      aria-live={variant === 'error' ? 'assertive' : 'polite'}
      className={cn(
        'flex flex-col items-center justify-center gap-4 rounded-2xl p-8 text-center ring-1 ring-inset',
        cfg.bg,
        cfg.ring,
        className,
      )}
    >
      <div
        className={cn(
          'flex h-14 w-14 items-center justify-center rounded-full',
          cfg.iconBg,
        )}
      >
        <Icon
          className={cn('h-7 w-7', cfg.iconColor, cfg.iconSpin && 'animate-spin')}
          aria-hidden
        />
      </div>

      <div className="max-w-md space-y-1.5">
        <h2 className={cn('text-lg font-semibold', cfg.titleColor)}>
          {title ?? cfg.defaultTitle}
        </h2>
        <p className="text-sm text-slate-600">
          {description ?? cfg.defaultDescription}
        </p>
      </div>

      {(onRetry || onCheckHistory) && (
        <div className="mt-1 flex flex-wrap items-center justify-center gap-2">
          {onCheckHistory && (
            <button
              type="button"
              onClick={onCheckHistory}
              className="inline-flex items-center gap-1.5 rounded-lg bg-white px-4 py-2 text-sm font-medium text-slate-800 ring-1 ring-inset ring-slate-300 transition-colors hover:bg-slate-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
            >
              <History className="h-4 w-4" aria-hidden />
              Geçmiş'ten kontrol et
            </button>
          )}
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="inline-flex items-center gap-1.5 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-brand-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
            >
              <RefreshCw className="h-4 w-4" aria-hidden />
              Yeniden dene
            </button>
          )}
        </div>
      )}

      {children}
    </section>
  );
}
