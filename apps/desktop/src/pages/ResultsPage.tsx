import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  PartCard,
  CleanPartsBadgeRow,
  CostDisplay,
  InspectionSummary as InspectionSummaryUi,
  ImageWithOverlay,
  Spinner,
  EmptyState,
  cn,
} from '@arac-hasar/ui';
import { AlertCircle, FileImage, ScanLine, Wrench } from 'lucide-react';
import type { Inspection, InspectionStatusResponse } from '@arac-hasar/types';
import { api } from '@/lib/api';

type OverlayMode = 'both' | 'parts' | 'damages';

export default function ResultsPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<InspectionStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<OverlayMode>('both');
  const [hoveredPart, setHoveredPart] = useState<string | null>(null);
  const [hoveredDamage, setHoveredDamage] = useState<number | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    let interval: ReturnType<typeof setTimeout> | null = null;

    async function tick() {
      try {
        const res = await api.getInspection(id!);
        if (cancelled) return;
        setData(res);
        if (res.status === 'queued' || res.status === 'processing') {
          interval = setTimeout(tick, 2000);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Hata');
      }
    }
    tick();
    return () => {
      cancelled = true;
      if (interval) clearTimeout(interval);
    };
  }, [id]);

  if (error) {
    return (
      <EmptyState
        icon={<AlertCircle className="h-12 w-12" />}
        title="İnceleme yüklenemedi"
        description={error}
      />
    );
  }
  if (!data) return <Spinner size="lg" label="İnceleme yükleniyor..." />;

  if (data.status === 'queued' || data.status === 'processing') {
    return (
      <div className="mx-auto max-w-lg text-center">
        <Spinner size="lg" />
        <h2 className="mt-4 text-lg font-semibold text-slate-900">
          {data.status === 'queued' ? 'Sırada bekleniyor' : 'İnceleme yapılıyor'}
        </h2>
        <p className="mt-1 text-slate-600">Görüntüler analiz ediliyor, lütfen bekle...</p>
      </div>
    );
  }

  if (data.status === 'failed' || !data.result) {
    return (
      <EmptyState
        icon={<AlertCircle className="h-12 w-12" />}
        title="İnceleme başarısız"
        description={data.error || 'Bilinmeyen hata'}
      />
    );
  }

  const result: Inspection = data.result;
  const allDamages = result.parts.flatMap((p) => p.damages);
  const imgUrl = result.visualization_urls?.annotated ?? result.image.url ?? '';
  const damagedParts = result.parts.filter((p) => p.status !== 'clean');
  const cleanParts = result.parts.filter((p) => p.status === 'clean');

  const tabs: { mode: OverlayMode; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
    { mode: 'both', label: 'Genel görünüm', icon: FileImage },
    { mode: 'parts', label: 'Parçalar', icon: ScanLine },
    { mode: 'damages', label: 'Hasarlar', icon: Wrench },
  ];

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">İnceleme sonucu</h1>
        <p className="mt-1 font-mono text-xs text-slate-400">{result.inspection_id}</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-3">
          <div className="flex gap-1 rounded-lg bg-slate-100 p-1">
            {tabs.map((t) => (
              <button
                key={t.mode}
                type="button"
                onClick={() => setMode(t.mode)}
                className={cn(
                  'flex flex-1 items-center justify-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                  mode === t.mode
                    ? 'bg-white text-slate-900 shadow-sm'
                    : 'text-slate-600 hover:text-slate-900',
                )}
              >
                <t.icon className="h-4 w-4" />
                {t.label}
              </button>
            ))}
          </div>
          {imgUrl ? (
            <ImageWithOverlay
              imageUrl={imgUrl}
              damages={allDamages}
              parts={result.parts}
              mode={mode}
              highlightedDamageId={hoveredDamage}
              highlightedPart={hoveredPart}
            />
          ) : (
            <EmptyState title="Görüntü bulunamadı" />
          )}
        </div>
        <div className="space-y-4">
          <CostDisplay summary={result.summary} />
          <InspectionSummaryUi summary={result.summary} />
        </div>
      </div>

      {damagedParts.length > 0 && (
        <section>
          <h2 className="mb-3 text-lg font-semibold text-slate-900">
            Hasarlı parçalar ({damagedParts.length})
          </h2>
          <div className="grid gap-3 md:grid-cols-2">
            {damagedParts.map((p) => (
              <div
                key={p.name}
                onMouseEnter={() => setHoveredPart(p.name)}
                onMouseLeave={() => setHoveredPart(null)}
              >
                <PartCard
                  part={p}
                  onDamageClick={(damageId) =>
                    setHoveredDamage((cur) => (cur === damageId ? null : damageId))
                  }
                />
              </div>
            ))}
          </div>
        </section>
      )}

      {cleanParts.length > 0 && <CleanPartsBadgeRow parts={cleanParts} />}

      {result.multi_part_damages && result.multi_part_damages.length > 0 && (
        <section>
          <h2 className="mb-3 text-lg font-semibold text-slate-900">Çoklu parça hasarları</h2>
          <p className="text-sm text-slate-600">
            {result.multi_part_damages.length} hasar birden fazla parçaya yayılıyor.
          </p>
        </section>
      )}
    </div>
  );
}
