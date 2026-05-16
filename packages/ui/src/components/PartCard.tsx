import type { Part } from '@arac-hasar/types';
import { PART_STATUS_TR } from '@arac-hasar/types';
import { DamageBadge } from './DamageBadge';
import { cn } from '../utils/cn';

interface Props {
  part: Part;
  className?: string;
  onDamageClick?: (damageId: number) => void;
  onPartClick?: () => void;
}

const STATUS_RING: Record<Part['status'], string> = {
  clean: 'ring-emerald-200 bg-emerald-50/40',
  minor_damage: 'ring-amber-300 bg-amber-50/30',
  moderate_damage: 'ring-orange-300 bg-orange-50/30',
  severe_damage: 'ring-red-300 bg-red-50/30',
};

const STATUS_DOT: Record<Part['status'], string> = {
  clean: 'bg-emerald-500',
  minor_damage: 'bg-amber-500',
  moderate_damage: 'bg-orange-500',
  severe_damage: 'bg-red-500',
};

export function PartCard({ part, className, onDamageClick, onPartClick }: Props) {
  const isClean = part.status === 'clean';
  const interactive = !!onPartClick;
  return (
    <div
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
      onClick={onPartClick}
      onKeyDown={(e) => {
        if (!interactive) return;
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onPartClick?.();
        }
      }}
      aria-label={interactive ? `${part.name_tr}, ${PART_STATUS_TR[part.status]}` : undefined}
      className={cn(
        'rounded-xl ring-1 ring-inset p-4 transition-shadow',
        STATUS_RING[part.status],
        interactive &&
          'cursor-pointer hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-1',
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className={cn('h-2 w-2 rounded-full', STATUS_DOT[part.status])} aria-hidden />
          <h3 className="font-semibold text-slate-900">{part.name_tr}</h3>
        </div>
        <span
          className={cn(
            'rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide',
            isClean ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-900 text-white',
          )}
        >
          {isClean ? 'Hasarsız' : `${part.damage_count} hasar`}
        </span>
      </div>

      <div className="mt-1 text-[11px] uppercase tracking-wider text-slate-400">
        {PART_STATUS_TR[part.status]}
      </div>

      {!isClean && (
        <>
          <div className="mt-3 space-y-2">
            {part.damages.map((d) => (
              <DamageBadge
                key={d.id}
                damage={d}
                onClick={onDamageClick ? () => onDamageClick(d.id) : undefined}
              />
            ))}
          </div>

          {part.part_cost_max_tl > 0 && (
            <div className="mt-3 flex items-baseline justify-between border-t border-slate-200/70 pt-2">
              <span className="text-xs text-slate-500">Parça toplam</span>
              <span className="text-sm font-semibold text-slate-900 tabular-nums">
                {part.part_cost_min_tl.toLocaleString('tr-TR')} –{' '}
                {part.part_cost_max_tl.toLocaleString('tr-TR')} ₺
              </span>
            </div>
          )}

          {part.cost_note && (
            <p className="mt-1 text-[11px] italic text-slate-500">{part.cost_note}</p>
          )}
        </>
      )}
    </div>
  );
}
