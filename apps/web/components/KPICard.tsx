import type { ComponentType } from 'react';

interface KPICardProps {
  label: string;
  value: string | number;
  hint?: string;
  icon?: ComponentType<{ className?: string }>;
  trend?: { direction: 'up' | 'down' | 'flat'; label?: string };
  tone?: 'default' | 'primary' | 'success' | 'warning' | 'danger';
}

const TONE_RING: Record<NonNullable<KPICardProps['tone']>, string> = {
  default: 'bg-slate-50 text-slate-700',
  primary: 'bg-brand-50 text-brand-700',
  success: 'bg-emerald-50 text-emerald-700',
  warning: 'bg-amber-50 text-amber-700',
  danger: 'bg-red-50 text-red-700',
};

export function KPICard({
  label,
  value,
  hint,
  icon: Icon,
  trend,
  tone = 'default',
}: KPICardProps) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          {label}
        </span>
        {Icon && (
          <span
            className={`flex h-8 w-8 items-center justify-center rounded-lg ${TONE_RING[tone]}`}
          >
            <Icon className="h-4 w-4" />
          </span>
        )}
      </div>
      <div className="mt-3 flex items-baseline gap-2">
        <span className="text-3xl font-bold text-slate-900 tabular-nums">
          {value}
        </span>
        {trend && (
          <span
            className={`text-xs font-semibold ${
              trend.direction === 'up'
                ? 'text-emerald-600'
                : trend.direction === 'down'
                  ? 'text-red-600'
                  : 'text-slate-500'
            }`}
          >
            {trend.direction === 'up' ? '↑' : trend.direction === 'down' ? '↓' : '→'}{' '}
            {trend.label}
          </span>
        )}
      </div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}
