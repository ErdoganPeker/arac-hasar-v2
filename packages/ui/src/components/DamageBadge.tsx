import type { Damage } from '@arac-hasar/types';
import { SeverityBadge } from './SeverityBadge';
import { cn } from '../utils/cn';

interface Props {
  damage: Damage;
  className?: string;
  onClick?: () => void;
}

export function DamageBadge({ damage, className, onClick }: Props) {
  const interactive = !!onClick;
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
      aria-label={
        interactive
          ? `${damage.type_tr}, ${damage.severity.level_tr || damage.severity.level} hasar`
          : undefined
      }
      className={cn(
        'flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2',
        interactive &&
          'cursor-pointer transition-colors hover:border-brand-400 hover:bg-brand-50/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-1',
        className,
      )}
    >
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-slate-800">{damage.type_tr}</span>
        <SeverityBadge level={damage.severity.level} />
        {damage.is_multi_part && (
          <span className="rounded bg-purple-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-purple-700">
            Çoklu parça
          </span>
        )}
        {damage.is_low_confidence_match && (
          <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-slate-600">
            Düşük güven
          </span>
        )}
      </div>
      <div className="text-right">
        <div className="text-xs font-medium text-slate-700 tabular-nums">
          {damage.cost.min_tl.toLocaleString('tr-TR')} – {damage.cost.max_tl.toLocaleString('tr-TR')} ₺
        </div>
        <div className="text-[10px] uppercase tracking-wider text-slate-400">
          %{Math.round(damage.confidence * 100)} güven
        </div>
      </div>
    </div>
  );
}
