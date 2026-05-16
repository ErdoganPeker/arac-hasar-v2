/**
 * CostDisplay — large total-cost block (light/dark aware) plus low/mid/high breakdown.
 */
import { useTranslation } from 'react-i18next';

interface Summary {
  total_cost_range_tl?: [number, number];
  total_cost_midpoint_tl?: number;
}

function fmt(n: number | undefined): string {
  if (n === undefined || n === null) return '—';
  return new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 }).format(n);
}

export function CostDisplay({ summary }: { summary: Summary }) {
  const { t } = useTranslation();
  const mid = summary.total_cost_midpoint_tl;
  const lo = summary.total_cost_range_tl?.[0];
  const hi = summary.total_cost_range_tl?.[1];
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-800">
      <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
        {t('common.total')}
      </div>
      <div className="mt-1 text-3xl font-bold tabular-nums text-slate-900 dark:text-white">
        {fmt(mid)} <span className="text-lg font-normal text-slate-500">₺</span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
        <div className="rounded-md bg-slate-50 px-2.5 py-1.5 dark:bg-slate-900/40">
          <div className="text-[10px] uppercase text-slate-500 dark:text-slate-400">min</div>
          <div className="font-semibold tabular-nums text-slate-700 dark:text-slate-200">
            {fmt(lo)} ₺
          </div>
        </div>
        <div className="rounded-md bg-slate-50 px-2.5 py-1.5 dark:bg-slate-900/40">
          <div className="text-[10px] uppercase text-slate-500 dark:text-slate-400">max</div>
          <div className="font-semibold tabular-nums text-slate-700 dark:text-slate-200">
            {fmt(hi)} ₺
          </div>
        </div>
      </div>
    </div>
  );
}

export default CostDisplay;
