import type { InspectionSummary as Summary } from '@arac-hasar/types';
import { cn } from '../utils/cn';

interface Props {
  summary: Summary;
  className?: string;
}

export function InspectionSummary({ summary, className }: Props) {
  const items: { label: string; value: string; emphasis?: boolean }[] = [
    { label: 'Toplam parça', value: summary.total_parts_inspected.toString() },
    { label: 'Hasarlı parça', value: summary.damaged_parts_count.toString(), emphasis: summary.damaged_parts_count > 0 },
    { label: 'Hasarsız parça', value: summary.clean_parts_count.toString() },
    { label: 'Toplam hasar', value: summary.total_damage_count.toString() },
  ];
  if (summary.multi_part_damages_count > 0) {
    items.push({ label: 'Çoklu parça', value: summary.multi_part_damages_count.toString() });
  }
  return (
    <div className={cn('grid grid-cols-2 gap-3 sm:grid-cols-4', className)}>
      {items.map((item) => (
        <div
          key={item.label}
          className={cn(
            'rounded-lg border bg-white p-3',
            item.emphasis ? 'border-orange-300 bg-orange-50/50' : 'border-slate-200',
          )}
        >
          <div className="text-[10px] uppercase tracking-wider text-slate-500">{item.label}</div>
          <div
            className={cn(
              'mt-1 text-2xl font-bold tabular-nums',
              item.emphasis ? 'text-orange-700' : 'text-slate-900',
            )}
          >
            {item.value}
          </div>
        </div>
      ))}
    </div>
  );
}
