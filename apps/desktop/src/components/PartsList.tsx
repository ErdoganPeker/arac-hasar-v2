/**
 * PartsList — compact table of parts and their status.
 * Damaged parts are highlighted; hovering a row emits `onHover(part_name)` so the
 * canvas overlay (ImageAnnotator) can spotlight the corresponding polygon.
 */
import { useTranslation } from 'react-i18next';
import SeverityBadge, { type Severity } from './SeverityBadge';

interface PartLike {
  name: string;
  status: string;
  damages: unknown[];
  part_cost_min_tl?: number;
  part_cost_max_tl?: number;
}

function formatPartCost(p: PartLike): string {
  const lo = p.part_cost_min_tl;
  const hi = p.part_cost_max_tl;
  if (lo === undefined && hi === undefined) return '—';
  if (lo !== undefined && hi !== undefined) {
    return `${lo.toLocaleString('tr-TR')}–${hi.toLocaleString('tr-TR')} ₺`;
  }
  return `${(lo ?? hi)?.toLocaleString('tr-TR')} ₺`;
}

interface DamageLike {
  severity?: { level?: string } | string;
}

function levelOf(d: unknown): string | undefined {
  const sev = (d as DamageLike).severity;
  if (typeof sev === 'string') return sev;
  return sev?.level;
}

function highestSeverity(damages: unknown[]): Severity | null {
  // API levels (`agir/orta/hafif`) ordered most-severe → least.
  const order: string[] = ['total_loss', 'agir', 'severe', 'orta', 'moderate', 'hafif', 'minor'];
  for (const sev of order) {
    if (damages.some((d) => levelOf(d) === sev)) return sev as Severity;
  }
  return null;
}

export function PartsList({
  parts,
  onHover,
  highlightedPart,
}: {
  parts: PartLike[];
  onHover?: (name: string | null) => void;
  highlightedPart?: string | null;
}) {
  const { t } = useTranslation();
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500 dark:bg-slate-900/40 dark:text-slate-400">
          <tr>
            <th className="px-3 py-2">{t('inspections.parts')}</th>
            <th className="px-3 py-2">{t('common.status')}</th>
            <th className="px-3 py-2">{t('inspections.damages')}</th>
            <th className="px-3 py-2">{t('inspections.cost')}</th>
          </tr>
        </thead>
        <tbody>
          {parts.map((p) => {
            const sev = highestSeverity(p.damages);
            const isHi = highlightedPart === p.name;
            return (
              <tr
                key={p.name}
                onMouseEnter={() => onHover?.(p.name)}
                onMouseLeave={() => onHover?.(null)}
                className={`border-t border-slate-200 transition-colors dark:border-slate-700 ${
                  isHi ? 'bg-brand-50 dark:bg-brand-900/20' : 'hover:bg-slate-50 dark:hover:bg-slate-800'
                }`}
              >
                <td className="px-3 py-2 font-medium text-slate-900 dark:text-slate-100">{p.name}</td>
                <td className="px-3 py-2">
                  {sev ? (
                    <SeverityBadge severity={sev} size="sm" />
                  ) : (
                    <span className="text-xs text-slate-500">—</span>
                  )}
                </td>
                <td className="px-3 py-2 text-slate-600 dark:text-slate-300">{p.damages.length}</td>
                <td className="px-3 py-2 text-slate-600 dark:text-slate-300">
                  {formatPartCost(p)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default PartsList;
