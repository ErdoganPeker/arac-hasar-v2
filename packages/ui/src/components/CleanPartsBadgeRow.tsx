import type { Part } from '@arac-hasar/types';
import { Check } from 'lucide-react';
import { cn } from '../utils/cn';

interface Props {
  parts: Part[];
  className?: string;
  maxVisible?: number;
}

export function CleanPartsBadgeRow({ parts, className, maxVisible = 12 }: Props) {
  const clean = parts.filter((p) => p.status === 'clean');
  if (clean.length === 0) return null;
  const visible = clean.slice(0, maxVisible);
  const hidden = clean.length - visible.length;

  return (
    <div className={cn('rounded-xl bg-emerald-50/60 ring-1 ring-inset ring-emerald-200 p-4', className)}>
      <div className="mb-2 flex items-center gap-2">
        <Check className="h-4 w-4 text-emerald-700" aria-hidden />
        <h3 className="text-sm font-semibold text-emerald-900">
          Hasarsız parçalar ({clean.length})
        </h3>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {visible.map((p) => (
          <span
            key={p.name}
            className="inline-flex items-center gap-1 rounded-full bg-white px-2.5 py-1 text-xs font-medium text-emerald-800 ring-1 ring-inset ring-emerald-200"
          >
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden />
            {p.name_tr}
          </span>
        ))}
        {hidden > 0 && (
          <span className="inline-flex items-center rounded-full bg-emerald-100 px-2.5 py-1 text-xs font-medium text-emerald-900">
            +{hidden} daha
          </span>
        )}
      </div>
    </div>
  );
}
