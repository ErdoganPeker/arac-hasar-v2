import type { ReactNode } from 'react';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { cn } from '../utils/cn';

export interface KPITrend {
  /** Positive = up, negative = down, zero = flat */
  delta: number;
  /** Optional explicit label override (e.g., "+12% bu hafta"); otherwise auto-generated. */
  label?: string;
  /** If true, a positive delta is "bad" (e.g., damage count going up) and colored red. */
  invert?: boolean;
}

interface Props {
  label: string;
  value: ReactNode;
  hint?: string;
  trend?: KPITrend;
  icon?: ReactNode;
  emphasis?: boolean;
  className?: string;
  onClick?: () => void;
}

export function KPICard({
  label,
  value,
  hint,
  trend,
  icon,
  emphasis,
  className,
  onClick,
}: Props) {
  const interactive = !!onClick;
  const trendDir = trend ? (trend.delta > 0 ? 'up' : trend.delta < 0 ? 'down' : 'flat') : null;
  const TrendIcon =
    trendDir === 'up' ? TrendingUp : trendDir === 'down' ? TrendingDown : Minus;

  const trendIsBad = trend?.invert
    ? trend.delta > 0
    : trend
      ? trend.delta < 0
      : false;
  const trendColor =
    trendDir === 'flat'
      ? 'text-slate-500'
      : trendIsBad
        ? 'text-red-600'
        : 'text-emerald-600';

  return (
    <div
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
      className={cn(
        'flex flex-col gap-2 rounded-xl border bg-white p-4 shadow-sm transition-shadow',
        emphasis ? 'border-brand-300 bg-brand-50/40' : 'border-slate-200',
        interactive &&
          'cursor-pointer hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-1',
        className,
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="text-[11px] uppercase tracking-wider text-slate-500">
          {label}
        </span>
        {icon && <span className="text-slate-400">{icon}</span>}
      </div>
      <div className="text-3xl font-bold tabular-nums text-slate-900">{value}</div>
      <div className="flex items-center justify-between gap-2 text-xs">
        {hint && <span className="text-slate-500">{hint}</span>}
        {trend && (
          <span className={cn('inline-flex items-center gap-1 font-medium', trendColor)}>
            <TrendIcon className="h-3.5 w-3.5" aria-hidden />
            {trend.label ?? `${trend.delta > 0 ? '+' : ''}${trend.delta}%`}
          </span>
        )}
      </div>
    </div>
  );
}
