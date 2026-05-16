import { cn } from '../utils/cn';

interface Props {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
  label?: string;
}

export function Spinner({ size = 'md', className, label }: Props) {
  return (
    <div className={cn('inline-flex items-center gap-2', className)}>
      <span
        className={cn(
          'inline-block animate-spin rounded-full border-2 border-slate-300 border-t-brand-600',
          size === 'sm' && 'h-3 w-3',
          size === 'md' && 'h-5 w-5',
          size === 'lg' && 'h-8 w-8 border-[3px]',
        )}
        role="status"
        aria-label={label || 'Yükleniyor'}
      />
      {label && <span className="text-sm text-slate-700">{label}</span>}
    </div>
  );
}
