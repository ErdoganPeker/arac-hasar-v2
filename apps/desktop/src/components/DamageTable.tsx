/**
 * DamageTable — denser-than-cards damage list with sortable columns.
 */
import { useMemo, useState } from 'react';
import { ArrowDown, ArrowUp } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import SeverityBadge, { type Severity } from './SeverityBadge';

interface DamageRow {
  id?: number;
  part?: string;
  type?: string;
  severity?: Severity;
  confidence?: number;
  recommended_action?: string;
  cost_midpoint_tl?: number;
}

type SortKey = keyof Pick<DamageRow, 'part' | 'type' | 'severity' | 'confidence' | 'cost_midpoint_tl'>;

const SEVERITY_RANK: Record<Severity, number> = {
  minor: 1,
  hafif: 1,
  moderate: 2,
  orta: 2,
  severe: 3,
  agir: 3,
  total_loss: 4,
};

export function DamageTable({
  damages,
  onRowHover,
}: {
  damages: DamageRow[];
  onRowHover?: (id: number | null) => void;
}) {
  const { t } = useTranslation();
  const [sortKey, setSortKey] = useState<SortKey>('severity');
  const [dir, setDir] = useState<'asc' | 'desc'>('desc');

  const sorted = useMemo(() => {
    const copy = [...damages];
    copy.sort((a, b) => {
      let av: number | string | undefined;
      let bv: number | string | undefined;
      if (sortKey === 'severity') {
        av = a.severity ? SEVERITY_RANK[a.severity] : 0;
        bv = b.severity ? SEVERITY_RANK[b.severity] : 0;
      } else {
        av = a[sortKey];
        bv = b[sortKey];
      }
      if (av === undefined) return 1;
      if (bv === undefined) return -1;
      if (av < bv) return dir === 'asc' ? -1 : 1;
      if (av > bv) return dir === 'asc' ? 1 : -1;
      return 0;
    });
    return copy;
  }, [damages, sortKey, dir]);

  function header(key: SortKey, label: string) {
    const active = sortKey === key;
    return (
      <th
        className="cursor-pointer select-none px-3 py-2 hover:text-slate-700 dark:hover:text-slate-200"
        onClick={() => {
          if (active) setDir(dir === 'asc' ? 'desc' : 'asc');
          else {
            setSortKey(key);
            setDir('desc');
          }
        }}
      >
        <span className="inline-flex items-center gap-1">
          {label}
          {active &&
            (dir === 'asc' ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
        </span>
      </th>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500 dark:bg-slate-900/40 dark:text-slate-400">
          <tr>
            {header('part', t('inspections.parts'))}
            {header('type', t('common.status'))}
            {header('severity', 'Şiddet')}
            {header('confidence', 'Güven')}
            <th className="px-3 py-2">Aksiyon</th>
            {header('cost_midpoint_tl', t('inspections.cost'))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((d, i) => (
            <tr
              key={d.id ?? i}
              onMouseEnter={() => onRowHover?.(d.id ?? null)}
              onMouseLeave={() => onRowHover?.(null)}
              className="border-t border-slate-200 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800"
            >
              <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">
                {d.part ?? '—'}
              </td>
              <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{d.type ?? '—'}</td>
              <td className="px-3 py-2">
                {d.severity ? <SeverityBadge severity={d.severity} size="sm" /> : '—'}
              </td>
              <td className="px-3 py-2 tabular-nums text-slate-600 dark:text-slate-300">
                {d.confidence !== undefined ? `${Math.round(d.confidence * 100)}%` : '—'}
              </td>
              <td className="px-3 py-2 text-slate-600 dark:text-slate-300">
                {d.recommended_action ?? '—'}
              </td>
              <td className="px-3 py-2 text-right tabular-nums text-slate-700 dark:text-slate-200">
                {d.cost_midpoint_tl?.toLocaleString('tr-TR') ?? '—'} ₺
              </td>
            </tr>
          ))}
          {sorted.length === 0 && (
            <tr>
              <td colSpan={6} className="px-3 py-6 text-center text-sm text-slate-500">
                {t('inspections.empty')}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export default DamageTable;
