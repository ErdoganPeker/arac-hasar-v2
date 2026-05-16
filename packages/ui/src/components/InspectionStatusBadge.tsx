import type { InspectionStatus } from '@arac-hasar/types';
import { Clock, Loader2, CheckCircle2, XCircle } from 'lucide-react';
import { cn } from '../utils/cn';

const STATUS_LABEL: Record<InspectionStatus, string> = {
  queued: 'Sırada',
  processing: 'İşleniyor',
  completed: 'Tamamlandı',
  failed: 'Başarısız',
};

const STATUS_STYLES: Record<InspectionStatus, string> = {
  queued: 'bg-slate-100 text-slate-800 ring-slate-300',
  processing: 'bg-blue-50 text-blue-800 ring-blue-200',
  completed: 'bg-emerald-50 text-emerald-800 ring-emerald-200',
  failed: 'bg-red-50 text-red-800 ring-red-200',
};

const STATUS_ICON: Record<InspectionStatus, React.ComponentType<{ className?: string }>> = {
  queued: Clock,
  processing: Loader2,
  completed: CheckCircle2,
  failed: XCircle,
};

interface Props {
  status: InspectionStatus;
  size?: 'sm' | 'md';
  className?: string;
}

export function InspectionStatusBadge({ status, size = 'sm', className }: Props) {
  const Icon = STATUS_ICON[status];
  const isSpinning = status === 'processing';
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full ring-1 ring-inset font-medium',
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-sm',
        STATUS_STYLES[status],
        className,
      )}
    >
      <Icon
        className={cn(
          size === 'sm' ? 'h-3 w-3' : 'h-4 w-4',
          isSpinning && 'animate-spin',
        )}
        aria-hidden
      />
      {STATUS_LABEL[status]}
    </span>
  );
}
