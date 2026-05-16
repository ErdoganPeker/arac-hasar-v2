import type { PartName } from '@arac-hasar/types';
import { PART_TR } from '@arac-hasar/types';
import { cn } from '../utils/cn';

/** Abbreviated part labels — shown when there isn't room for the full Turkish name. */
const PART_ABBR: Record<string, string> = {
  front_bumper: 'Ön Tmp',
  back_bumper: 'Ark Tmp',
  hood: 'Kaput',
  front_glass: 'Ön Cam',
  back_glass: 'Ark Cam',
  front_left_door: 'Sol Ön Kp',
  front_right_door: 'Sağ Ön Kp',
  back_left_door: 'Sol Ark Kp',
  back_right_door: 'Sağ Ark Kp',
  back_door: 'Ark Kp',
  front_left_light: 'Sol Ön Far',
  front_right_light: 'Sağ Ön Far',
  front_light: 'Ön Far',
  back_left_light: 'Sol Stop',
  back_right_light: 'Sağ Stop',
  back_light: 'Ark Stop',
  left_mirror: 'Sol Ayna',
  right_mirror: 'Sağ Ayna',
  tailgate: 'Bagaj Kp',
  trunk: 'Bagaj',
  wheel: 'Teker',
  unknown: '???',
};

interface Props {
  part: PartName | string;
  abbreviated?: boolean;
  damaged?: boolean;
  className?: string;
  onClick?: () => void;
}

export function PartChip({ part, abbreviated = false, damaged, className, onClick }: Props) {
  const fullLabel = (PART_TR as Record<string, string>)[part] ?? part;
  const label = abbreviated ? (PART_ABBR[part] ?? fullLabel) : fullLabel;
  const interactive = !!onClick;

  return (
    <span
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
      title={fullLabel}
      aria-label={interactive ? fullLabel : undefined}
      className={cn(
        'inline-flex items-center gap-1 rounded-full ring-1 ring-inset px-2 py-0.5 text-xs font-medium',
        damaged
          ? 'bg-red-50 text-red-800 ring-red-200'
          : 'bg-slate-50 text-slate-700 ring-slate-200',
        interactive &&
          'cursor-pointer transition-colors hover:bg-brand-50/60 hover:ring-brand-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-1',
        className,
      )}
    >
      {label}
    </span>
  );
}
