import type { Damage } from '@arac-hasar/types';
import { AlertTriangle, HelpCircle } from 'lucide-react';
import { DamageTypeChip } from './DamageTypeChip';
import { SeverityBadge } from './SeverityBadge';
import { cn } from '../utils/cn';

interface Props {
  damages: Damage[];
  className?: string;
  onDamageClick?: (damageId: number) => void;
  /**
   * Helper copy under the title — defaults to standard explanation.
   * Override when context-specific guidance is needed.
   */
  explanation?: string;
}

const DEFAULT_EXPLANATION =
  'Hangi parçaya ait olduğu otomatik belirlenemedi — fotoğraflarda parça net görünmüyor olabilir veya birden fazla parça örtüşüyor olabilir.';

export function UnassignedDamagesPanel({
  damages,
  className,
  onDamageClick,
  explanation = DEFAULT_EXPLANATION,
}: Props) {
  if (!damages || damages.length === 0) return null;

  return (
    <section
      aria-labelledby="unassigned-damages-title"
      className={cn(
        // dashed border + warm amber tint to clearly separate from part-centric cards
        'rounded-2xl border-2 border-dashed border-amber-400 bg-amber-50/70 p-4 sm:p-5',
        className,
      )}
    >
      <header className="flex items-start gap-3">
        <div className="flex h-9 w-9 flex-none items-center justify-center rounded-full bg-amber-200 text-amber-900">
          <AlertTriangle className="h-5 w-5" aria-hidden />
        </div>
        <div className="flex-1 min-w-0">
          <h2
            id="unassigned-damages-title"
            className="flex items-center gap-2 text-base font-semibold text-amber-950"
          >
            Atanamayan hasarlar
            <span
              className="inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-full bg-amber-900 px-1.5 text-xs font-bold text-white tabular-nums"
              aria-label={`${damages.length} hasar`}
            >
              {damages.length}
            </span>
          </h2>
          <p className="mt-1 flex items-start gap-1.5 text-sm text-amber-900/90">
            <HelpCircle className="mt-0.5 h-3.5 w-3.5 flex-none" aria-hidden />
            <span>{explanation}</span>
          </p>
        </div>
      </header>

      <ul className="mt-4 space-y-2">
        {damages.map((d) => {
          const interactive = !!onDamageClick;
          return (
            <li key={d.id}>
              <div
                role={interactive ? 'button' : undefined}
                tabIndex={interactive ? 0 : undefined}
                onClick={interactive ? () => onDamageClick?.(d.id) : undefined}
                onKeyDown={(e) => {
                  if (!interactive) return;
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onDamageClick?.(d.id);
                  }
                }}
                aria-label={
                  interactive
                    ? `${d.type_tr}, ${d.severity.level_tr || d.severity.level}, atanmamış hasar`
                    : undefined
                }
                className={cn(
                  'flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-200 bg-white px-3 py-2.5',
                  interactive &&
                    'cursor-pointer transition-colors hover:border-amber-400 hover:bg-amber-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-1',
                )}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <DamageTypeChip type={d.type} />
                  <SeverityBadge level={d.severity.level} />
                </div>
                <div className="text-right">
                  <div className="text-xs font-medium text-slate-700 tabular-nums">
                    {d.cost.min_tl.toLocaleString('tr-TR')} –{' '}
                    {d.cost.max_tl.toLocaleString('tr-TR')} ₺
                  </div>
                  <div className="text-[10px] uppercase tracking-wider text-amber-800/70">
                    %{Math.round(d.confidence * 100)} güven
                  </div>
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
