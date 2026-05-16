import type { SeverityLevel } from '@arac-hasar/types';
import { SEVERITY_TR } from '@arac-hasar/types';
import { Check, AlertTriangle, XCircle, type LucideIcon } from 'lucide-react';
import { cn } from '../utils/cn';

interface Props {
  level: SeverityLevel;
  size?: 'sm' | 'md';
  className?: string;
  showDot?: boolean;
  /** Show severity icon alongside dot/label — pairs color with shape for color-blind users. */
  showIcon?: boolean;
}

const STYLES: Record<SeverityLevel, string> = {
  // hafif lifted to emerald — matches the "ok / mild" semantic and clears WCAG AA
  hafif: 'bg-emerald-50 text-emerald-900 ring-emerald-300',
  orta: 'bg-amber-100 text-amber-900 ring-amber-300',
  agir: 'bg-red-100 text-red-900 ring-red-300',
};

const DOT_COLORS: Record<SeverityLevel, string> = {
  hafif: 'bg-emerald-500',
  orta: 'bg-amber-500',
  agir: 'bg-red-500',
};

const ICONS: Record<SeverityLevel, LucideIcon> = {
  hafif: Check,
  orta: AlertTriangle,
  agir: XCircle,
};

const ICON_COLORS: Record<SeverityLevel, string> = {
  hafif: 'text-emerald-700',
  orta: 'text-amber-700',
  agir: 'text-red-700',
};

export function SeverityBadge({
  level,
  size = 'sm',
  className,
  showDot = false,
  showIcon = true,
}: Props) {
  const Icon = ICONS[level];
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full ring-1 ring-inset font-medium',
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-sm',
        STYLES[level],
        className,
      )}
    >
      {showDot && (
        <span className={cn('h-1.5 w-1.5 rounded-full', DOT_COLORS[level])} aria-hidden />
      )}
      {showIcon && (
        <Icon
          className={cn(size === 'sm' ? 'h-3 w-3' : 'h-3.5 w-3.5', ICON_COLORS[level])}
          aria-hidden
        />
      )}
      {SEVERITY_TR[level]}
    </span>
  );
}
