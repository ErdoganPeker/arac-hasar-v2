/**
 * SeverityBadge — small colored pill for damage severity.
 *
 * Accepts both the API enum (`hafif`/`orta`/`agir`) and the spec's English
 * shorthand (`minor`/`moderate`/`severe`/`total_loss`) so it can render data
 * from any layer without translation glue at the call site.
 */
import { useTranslation } from 'react-i18next';

export type SeverityLevel = 'hafif' | 'orta' | 'agir';
export type Severity = SeverityLevel | 'minor' | 'moderate' | 'severe' | 'total_loss';

const NORMALIZE: Record<Severity, 'minor' | 'moderate' | 'severe' | 'total_loss'> = {
  hafif: 'minor',
  orta: 'moderate',
  agir: 'severe',
  minor: 'minor',
  moderate: 'moderate',
  severe: 'severe',
  total_loss: 'total_loss',
};

const STYLES: Record<'minor' | 'moderate' | 'severe' | 'total_loss', string> = {
  minor:
    'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300 ring-emerald-200/60 dark:ring-emerald-800/40',
  moderate:
    'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300 ring-amber-200/60 dark:ring-amber-800/40',
  severe:
    'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300 ring-red-200/60 dark:ring-red-800/40',
  total_loss:
    'bg-slate-200 text-slate-800 dark:bg-slate-700 dark:text-slate-100 ring-slate-300/60 dark:ring-slate-600/40',
};

export function SeverityBadge({ severity, size = 'md' }: { severity: Severity; size?: 'sm' | 'md' }) {
  const { t } = useTranslation();
  const norm = NORMALIZE[severity];
  const key = norm === 'total_loss' ? 'totalLoss' : norm;
  const sz = size === 'sm' ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-0.5 text-xs';
  return (
    <span
      className={`inline-flex items-center rounded-full ring-1 font-medium ${sz} ${STYLES[norm]}`}
    >
      {t(`severity.${key}`)}
    </span>
  );
}

export default SeverityBadge;
