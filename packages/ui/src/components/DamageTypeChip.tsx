import type { DamageType } from '@arac-hasar/types';
import { DAMAGE_TYPE_TR } from '@arac-hasar/types';
import {
  Wrench,
  Slash,
  Zap,
  Square,
  Lightbulb,
  Disc,
  AlertCircle,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '../utils/cn';

const ICONS: Record<DamageType, LucideIcon> = {
  dent: Wrench,
  scratch: Slash,
  crack: Zap,
  glass_shatter: Square,
  lamp_broken: Lightbulb,
  tire_flat: Disc,
};

const COLORS: Record<DamageType, string> = {
  dent: 'bg-orange-50 text-orange-800 ring-orange-200',
  scratch: 'bg-amber-50 text-amber-800 ring-amber-200',
  crack: 'bg-red-50 text-red-800 ring-red-200',
  glass_shatter: 'bg-sky-50 text-sky-800 ring-sky-200',
  lamp_broken: 'bg-yellow-50 text-yellow-800 ring-yellow-200',
  tire_flat: 'bg-slate-100 text-slate-800 ring-slate-300',
};

interface Props {
  type: DamageType;
  size?: 'sm' | 'md';
  showIcon?: boolean;
  className?: string;
}

export function DamageTypeChip({ type, size = 'sm', showIcon = true, className }: Props) {
  const Icon = ICONS[type] ?? AlertCircle;
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full ring-1 ring-inset font-medium',
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-sm',
        COLORS[type],
        className,
      )}
    >
      {showIcon && <Icon className={size === 'sm' ? 'h-3 w-3' : 'h-4 w-4'} aria-hidden />}
      {DAMAGE_TYPE_TR[type]}
    </span>
  );
}
