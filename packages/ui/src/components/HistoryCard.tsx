import type { InspectionStatus } from '@arac-hasar/types';
import { InspectionStatusBadge } from './InspectionStatusBadge';
import { cn } from '../utils/cn';

export interface HistoryCardProps {
  /** Inspection id (used in default title) */
  id: string;
  /** ISO timestamp */
  timestamp: string;
  status: InspectionStatus;
  /** Backend thumbnail URL — falls back to default car SVG when null/empty */
  thumbnailUrl?: string | null;
  /** Display title — defaults to short id */
  title?: string;
  /** Cost range [min, max] in TL */
  costRangeTl?: [number, number] | null;
  /** Click handler */
  onClick?: () => void;
  className?: string;
}

function formatDateTr(iso: string): string {
  try {
    return new Intl.DateTimeFormat('tr-TR', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

/**
 * Default car silhouette — used when no thumbnail is available.
 * Inline SVG so it ships with the component (no extra request, no CLS).
 */
function DefaultCarSvg({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 64 40"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="Araç görseli yok"
      className={className}
    >
      <defs>
        <linearGradient id="hc-car-bg" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#dbeafe" />
          <stop offset="100%" stopColor="#bfdbfe" />
        </linearGradient>
      </defs>
      <rect x="0" y="0" width="64" height="40" rx="6" fill="url(#hc-car-bg)" />
      {/* car body */}
      <path
        d="M8 28 L12 18 Q14 14 19 14 H45 Q50 14 52 18 L56 28 Z"
        fill="#1e6ee0"
      />
      {/* roof window */}
      <path
        d="M18 20 Q20 16 24 16 H40 Q44 16 46 20 H18 Z"
        fill="#bfdbfe"
        opacity="0.7"
      />
      {/* wheels */}
      <circle cx="18" cy="29" r="4" fill="#0f172a" />
      <circle cx="18" cy="29" r="1.5" fill="#94a3b8" />
      <circle cx="46" cy="29" r="4" fill="#0f172a" />
      <circle cx="46" cy="29" r="1.5" fill="#94a3b8" />
    </svg>
  );
}

/**
 * Compact card for the history list — single inspection summary.
 *
 * Lighter-weight than `HistoryInspectionCard` and intentionally matches the
 * frontend's history-row thumbnail spec:
 *  - Default car SVG when no thumbnail
 *  - Status badge (tamamlandı / işleniyor / hata)
 *  - Cost range with tabular-nums + ₺
 *  - tr-TR formatted timestamp
 */
export function HistoryCard({
  id,
  timestamp,
  status,
  thumbnailUrl,
  title,
  costRangeTl,
  onClick,
  className,
}: HistoryCardProps) {
  const interactive = !!onClick;
  const displayTitle = title ?? `İnceleme #${id.slice(0, 8)}`;
  const hasThumb = !!thumbnailUrl;

  return (
    <article
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
      onClick={onClick}
      onKeyDown={(e) => {
        if (!interactive) return;
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick?.();
        }
      }}
      aria-label={interactive ? `${displayTitle} aç` : undefined}
      className={cn(
        'group flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-3',
        interactive &&
          'cursor-pointer transition-all hover:border-brand-300 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2',
        className,
      )}
    >
      {/* Thumbnail */}
      <div className="relative h-16 w-16 flex-none overflow-hidden rounded-lg ring-1 ring-inset ring-slate-200 sm:h-20 sm:w-20">
        {hasThumb ? (
          <img
            src={thumbnailUrl!}
            alt=""
            width={80}
            height={80}
            loading="lazy"
            decoding="async"
            className="h-full w-full object-cover"
          />
        ) : (
          <DefaultCarSvg className="h-full w-full" />
        )}
      </div>

      {/* Body */}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="truncate text-sm font-semibold text-slate-900 sm:text-base">
            {displayTitle}
          </h3>
          <InspectionStatusBadge status={status} />
        </div>
        <div className="mt-1 text-xs text-slate-500">{formatDateTr(timestamp)}</div>
        {costRangeTl && costRangeTl[1] > 0 && (
          <div className="mt-1.5 text-sm font-medium text-slate-700 tabular-nums">
            {costRangeTl[0].toLocaleString('tr-TR')} – {costRangeTl[1].toLocaleString('tr-TR')} ₺
          </div>
        )}
      </div>
    </article>
  );
}
