'use client';

import { useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Layers, Car, AlertOctagon } from 'lucide-react';
import type { Damage, Part } from '@arac-hasar/types';
import { ImageWithOverlay, type OverlayMode } from '@arac-hasar/ui';

interface Props {
  imageUrl: string;
  parts: Part[];
  damages: Damage[];
  highlightedPart?: string | null;
  highlightedDamageId?: number | null;
}

type TabKey = 'overview' | 'parts' | 'damages';

interface TabDef {
  key: TabKey;
  labelKey: 'tabSummary' | 'tabParts' | 'tabDamages';
  mode: OverlayMode;
  icon: React.ComponentType<{ className?: string }>;
}

const TABS: TabDef[] = [
  { key: 'overview', labelKey: 'tabSummary', mode: 'both', icon: Layers },
  { key: 'parts', labelKey: 'tabParts', mode: 'parts', icon: Car },
  { key: 'damages', labelKey: 'tabDamages', mode: 'damages', icon: AlertOctagon },
];

export function ResultsTabs({
  imageUrl,
  parts,
  damages,
  highlightedPart = null,
  highlightedDamageId = null,
}: Props) {
  const t = useTranslations('inspect.result');
  const tSev = useTranslations('severity');
  const [active, setActive] = useState<TabKey>('overview');

  const mode = useMemo<OverlayMode>(
    () => TABS.find((tab) => tab.key === active)?.mode ?? 'both',
    [active],
  );

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div
        role="tablist"
        aria-label={t('viewVisualization')}
        className="mb-4 inline-flex rounded-xl bg-slate-100 p-1"
      >
        {TABS.map((tab) => {
          const isActive = active === tab.key;
          const label = t(tab.labelKey);
          return (
            <button
              key={tab.key}
              role="tab"
              type="button"
              aria-selected={isActive}
              aria-controls={`tab-panel-${tab.key}`}
              id={`tab-${tab.key}`}
              onClick={() => setActive(tab.key)}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-white text-slate-900 shadow-sm'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <tab.icon className="h-4 w-4" aria-hidden />
              <span className="hidden sm:inline">{label}</span>
            </button>
          );
        })}
      </div>

      <div
        id={`tab-panel-${active}`}
        role="tabpanel"
        aria-labelledby={`tab-${active}`}
      >
        <ImageWithOverlay
          imageUrl={imageUrl}
          parts={parts}
          damages={damages}
          mode={mode}
          highlightedPart={highlightedPart}
          highlightedDamageId={highlightedDamageId}
          className="w-full"
        />
        <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-500">
          <LegendDot color="#3b82f6" label={t('tabParts')} />
          <LegendDot color="#f59e0b" label={tSev('hafif')} />
          <LegendDot color="#f97316" label={tSev('orta')} />
          <LegendDot color="#ef4444" label={tSev('agir')} />
        </div>
      </div>
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className="h-2.5 w-2.5 rounded-full ring-1 ring-inset ring-black/10"
        style={{ backgroundColor: color }}
        aria-hidden
      />
      {label}
    </span>
  );
}
