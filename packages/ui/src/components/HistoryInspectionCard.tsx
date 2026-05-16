import type { InspectionStatus, SeverityLevel } from '@arac-hasar/types';
import { Car, Calendar, ChevronRight } from 'lucide-react';
import { InspectionStatusBadge } from './InspectionStatusBadge';
import { SeverityBadge } from './SeverityBadge';
import { cn } from '../utils/cn';

export interface HistoryInspectionCardProps {
  inspectionId: string;
  /** ISO timestamp */
  timestamp: string;
  status: InspectionStatus;
  /** Optional thumbnail — null/empty renders the high-contrast placeholder */
  thumbnailUrl?: string | null;
  /** Display name / shortened id */
  title?: string;
  totalDamages?: number;
  mostSevereLevel?: SeverityLevel | null;
  totalCostRangeTl?: [number, number] | null;
  onClick?: () => void;
  className?: string;
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return new Intl.DateTimeFormat('tr-TR', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(d);
  } catch {
    return iso;
  }
}

export function HistoryInspectionCard({
  inspectionId,
  timestamp,
  status,
  thumbnailUrl,
  title,
  totalDamages,
  mostSevereLevel,
  totalCostRangeTl,
  onClick,
  className,
}: HistoryInspectionCardProps) {
  const interactive = !!onClick;
  const displayTitle = title ?? `İnceleme #${inspectionId.slice(0, 8)}`;
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
        'flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 sm:p-4',
        interactive &&
          'cursor-pointer transition-all hover:border-brand-300 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2',
        className,
      )}
    >
      {/* Thumbnail / placeholder */}
      <div className="relative flex-none">
        {hasThumb ? (
          <img
            src={thumbnailUrl!}
            alt=""
            loading="lazy"
            decoding="async"
            className="h-16 w-16 rounded-lg object-cover ring-1 ring-inset ring-slate-200 sm:h-20 sm:w-20"
          />
        ) : (
          <ThumbnailPlaceholder />
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

        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
          <span className="inline-flex items-center gap-1">
            <Calendar className="h-3 w-3" aria-hidden />
            {formatDate(timestamp)}
          </span>
          {typeof totalDamages === 'number' && (
            <span className="tabular-nums">
              {totalDamages} hasar
            </span>
          )}
        </div>

        {(mostSevereLevel || totalCostRangeTl) && (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {mostSevereLevel && <SeverityBadge level={mostSevereLevel} />}
            {totalCostRangeTl && totalCostRangeTl[1] > 0 && (
              <span className="text-xs font-medium text-slate-700 tabular-nums">
                {totalCostRangeTl[0].toLocaleString('tr-TR')} –{' '}
                {totalCostRangeTl[1].toLocaleString('tr-TR')} ₺
              </span>
            )}
          </div>
        )}
      </div>

      {interactive && (
        <ChevronRight
          className="h-5 w-5 flex-none text-slate-300 transition-transform group-hover:translate-x-0.5"
          aria-hidden
        />
      )}
    </article>
  );
}

/**
 * Brand-colored, high-contrast placeholder used when the inspection has no
 * processed thumbnail yet. Hosts a `title` tooltip for sighted users and
 * a hidden caption for screen readers.
 */
function ThumbnailPlaceholder() {
  const tooltip = 'Görsel hazırlanıyor';
  return (
    <div
      title={tooltip}
      role="img"
      aria-label={tooltip}
      className="relative flex h-16 w-16 items-center justify-center overflow-hidden rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-inner sm:h-20 sm:w-20"
    >
      <Car className="h-8 w-8 drop-shadow-sm sm:h-10 sm:w-10" aria-hidden />
      <span className="sr-only">{tooltip}</span>
      {/* Subtle shimmer dot signals "in-progress" without animating CLS */}
      <span
        className="absolute bottom-1.5 right-1.5 h-1.5 w-1.5 rounded-full bg-white/80 ring-2 ring-brand-600"
        aria-hidden
      />
    </div>
  );
}
