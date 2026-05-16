import type { InspectionSummary } from '@arac-hasar/types';
import { cn } from '../utils/cn';

interface Props {
  summary: Pick<
    InspectionSummary,
    'total_cost_range_tl' | 'total_cost_midpoint_tl' | 'cost_confidence' | 'repair_recommendation_tr' | 'estimated_repair_days'
  >;
  className?: string;
}

const CONF_LABEL: Record<'high' | 'medium' | 'low', string> = {
  high: 'Yüksek doğruluk',
  medium: 'Orta doğruluk',
  low: 'Tahmini aralık',
};

const CONF_COLOR: Record<'high' | 'medium' | 'low', string> = {
  high: 'bg-emerald-500',
  medium: 'bg-amber-500',
  low: 'bg-slate-400',
};

export function CostDisplay({ summary, className }: Props) {
  const [min, max] = summary.total_cost_range_tl;
  const mid = summary.total_cost_midpoint_tl ?? (min + max) / 2;

  return (
    <div
      className={cn(
        'rounded-2xl bg-gradient-to-br from-brand-50 to-white p-5 ring-1 ring-inset ring-brand-200',
        className,
      )}
    >
      <div className="text-xs uppercase tracking-wider text-brand-700">Tahmini onarım maliyeti</div>
      <div
        className="mt-1 flex items-baseline gap-2"
        aria-label={`Tahmini onarım maliyeti: ${min.toLocaleString('tr-TR')} ila ${max.toLocaleString('tr-TR')} Türk Lirası`}
      >
        <span className="text-3xl font-bold text-slate-900 tabular-nums">
          {min.toLocaleString('tr-TR')}
        </span>
        <span aria-hidden className="text-slate-500">
          –
        </span>
        <span className="text-3xl font-bold text-slate-900 tabular-nums">
          {max.toLocaleString('tr-TR')}
        </span>
        <span aria-hidden className="text-lg font-semibold text-slate-700">
          ₺
        </span>
      </div>
      <div className="mt-1 text-sm text-slate-600">
        Orta nokta: <strong className="tabular-nums">{mid.toLocaleString('tr-TR')} ₺</strong>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs">
        <span className="inline-flex items-center gap-1.5 text-slate-600">
          <span className={cn('h-2 w-2 rounded-full', CONF_COLOR[summary.cost_confidence])} aria-hidden />
          {CONF_LABEL[summary.cost_confidence]}
        </span>
        <span className="text-slate-400">•</span>
        <span className="text-slate-600">{summary.repair_recommendation_tr}</span>
        <span className="text-slate-400">•</span>
        <span className="text-slate-600">~{summary.estimated_repair_days} gün</span>
      </div>
    </div>
  );
}
