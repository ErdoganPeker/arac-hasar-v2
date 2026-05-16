'use client';

import { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import type { Part, SeverityLevel } from '@arac-hasar/types';
import { PartCard, CleanPartsBadgeRow } from '@arac-hasar/ui';

const SEV_RANK: Record<SeverityLevel, number> = {
  agir: 3,
  orta: 2,
  hafif: 1,
};

const STATUS_RANK: Record<Part['status'], number> = {
  severe_damage: 3,
  moderate_damage: 2,
  minor_damage: 1,
  clean: 0,
};

function maxSeverityRank(part: Part): number {
  if (part.damages.length === 0) return 0;
  return Math.max(
    ...part.damages.map((d) => SEV_RANK[d.severity.level] ?? 0),
  );
}

interface Props {
  parts: Part[];
  onHoverPart?: (partName: string | null) => void;
  onDamageClick?: (damageId: number) => void;
}

export function PartList({ parts, onHoverPart, onDamageClick }: Props) {
  const t = useTranslations('inspect.result');
  const { damaged, clean } = useMemo(() => {
    const damagedList = parts.filter((p) => p.status !== 'clean');
    const cleanList = parts.filter((p) => p.status === 'clean');

    damagedList.sort((a, b) => {
      const statusDiff = STATUS_RANK[b.status] - STATUS_RANK[a.status];
      if (statusDiff !== 0) return statusDiff;
      const sevDiff = maxSeverityRank(b) - maxSeverityRank(a);
      if (sevDiff !== 0) return sevDiff;
      return b.damage_count - a.damage_count;
    });

    return { damaged: damagedList, clean: cleanList };
  }, [parts]);

  return (
    <div className="space-y-6">
      {damaged.length > 0 ? (
        <section>
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-lg font-semibold text-slate-900">
              {t('damagedParts')}
            </h2>
            <span className="text-xs text-slate-500">
              {damaged.length} · {t('overallSeverity')}
            </span>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {damaged.map((part) => (
              <div
                key={part.name}
                onMouseEnter={() => onHoverPart?.(part.name)}
                onMouseLeave={() => onHoverPart?.(null)}
                onFocus={() => onHoverPart?.(part.name)}
                onBlur={() => onHoverPart?.(null)}
              >
                <PartCard
                  part={part}
                  onDamageClick={onDamageClick}
                  onPartClick={() => onHoverPart?.(part.name)}
                />
              </div>
            ))}
          </div>
        </section>
      ) : (
        <section className="rounded-2xl border border-emerald-200 bg-emerald-50/60 p-6 text-emerald-900">
          <h2 className="font-semibold">{t('noDamage')}</h2>
          <p className="mt-1 text-sm text-emerald-800">
            {t('noDamageSubtitle')}
          </p>
        </section>
      )}

      {clean.length > 0 && (
        <section>
          <h2 className="mb-3 text-lg font-semibold text-slate-900">
            {t('cleanParts')}
          </h2>
          <CleanPartsBadgeRow parts={clean} />
        </section>
      )}
    </div>
  );
}
