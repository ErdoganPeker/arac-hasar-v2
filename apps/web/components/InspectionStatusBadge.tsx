'use client';

import { useTranslations } from 'next-intl';
import type { InspectionStatus } from '@arac-hasar/types';

const CLASSES: Record<InspectionStatus, string> = {
  queued: 'bg-slate-100 text-slate-700',
  processing: 'bg-amber-100 text-amber-800',
  completed: 'bg-emerald-100 text-emerald-800',
  failed: 'bg-red-100 text-red-800',
};

interface InspectionStatusBadgeProps {
  status: InspectionStatus;
  className?: string;
}

export function InspectionStatusBadge({
  status,
  className = '',
}: InspectionStatusBadgeProps) {
  const t = useTranslations('status');
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${CLASSES[status]} ${className}`}
    >
      {t(status)}
    </span>
  );
}
