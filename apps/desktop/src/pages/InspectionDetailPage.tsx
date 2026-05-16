/**
 * InspectionDetailPage — single inspection view.
 *
 * Layout:
 *   ┌─ annotated image carousel + overlay toggles ──┐  ┌─ cost summary  ─┐
 *   │ (ImageAnnotator)                              │  │ (CostDisplay)   │
 *   └───────────────────────────────────────────────┘  │ (PartsList)     │
 *                                                      └─────────────────┘
 *   <DamageTable />  — all damages flattened, sortable
 *
 * Header has: "Export rapor" (server PDF → save_report), "CSV" (client),
 * "Klasörde göster" (open_in_explorer), and "Sil".
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  Download,
  FileText,
  Loader2,
  Trash2,
} from 'lucide-react';
import type { Inspection, InspectionStatusResponse } from '@arac-hasar/types';
import { api } from '@/lib/api';
import { saveReport, showNotification } from '@/lib/commands';
import { buildTextPdfBase64, inspectionDetailToCsv } from '@/lib/export';
import ImageAnnotator from '@/components/ImageAnnotator';
import CostDisplay from '@/components/CostDisplay';
import PartsList from '@/components/PartsList';
import DamageTable from '@/components/DamageTable';
import SeverityBadge, { type Severity } from '@/components/SeverityBadge';

type Mode = 'both' | 'parts' | 'damages';

export default function InspectionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const [data, setData] = useState<InspectionStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>('both');
  const [imageIdx, setImageIdx] = useState(0);
  const [hoveredPart, setHoveredPart] = useState<string | null>(null);
  const [hoveredDamage, setHoveredDamage] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    async function tick() {
      try {
        const r = await api.getInspection(id!);
        if (cancelled) return;
        setData(r);
        if (r.status === 'queued' || r.status === 'processing') {
          timer = setTimeout(tick, 2000);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Error');
      }
    }
    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [id]);

  const result = data?.result as Inspection | undefined;

  const damages = useMemo(
    () =>
      (result?.parts ?? []).flatMap((p) =>
        p.damages.map((d, i) => ({
          id: d.id ?? i,
          part: p.name,
          type: d.type,
          severity: d.severity?.level as Severity | undefined,
          confidence: d.confidence,
          recommended_action: undefined as string | undefined,
          cost_midpoint_tl: d.cost?.midpoint_tl,
          bbox: d.bbox,
        })),
      ),
    [result],
  );

  const images = useMemo(() => {
    if (!result) return [] as string[];
    const list: string[] = [];
    const annotated = result.visualization_urls?.annotated;
    if (annotated) list.push(annotated);
    const main = result.image?.url;
    if (main && !list.includes(main)) list.push(main);
    const extra = (result as unknown as { images?: { url: string }[] }).images ?? [];
    for (const im of extra) if (im.url && !list.includes(im.url)) list.push(im.url);
    return list;
  }, [result]);

  async function handleExportPdf() {
    if (!result) return;
    setExporting(true);
    try {
      let b64: string;
      try {
        b64 = await api.exportInspectionPdf(result.inspection_id);
      } catch {
        const lines = [
          `Inspection: ${result.inspection_id}`,
          `Date: ${new Date().toISOString()}`,
          `Damages: ${damages.length}`,
          `Total cost (mid): ${result.summary?.total_cost_midpoint_tl ?? 'n/a'} TL`,
          '',
          'Parts:',
          ...result.parts.map((p) => `  - ${p.name} [${p.status}] x${p.damages.length}`),
        ];
        b64 = buildTextPdfBase64('Hasarİ — İnceleme Raporu', lines);
      }
      const saved = await saveReport({
        inspectionId: result.inspection_id,
        format: 'pdf',
        content: b64,
      });
      if (saved) {
        await showNotification(t('detail.exportReport'), saved);
      }
    } finally {
      setExporting(false);
    }
  }

  async function handleExportCsv() {
    if (!result) return;
    const csv = inspectionDetailToCsv(result);
    await saveReport({ inspectionId: result.inspection_id, format: 'csv', content: csv });
  }

  async function handleDelete() {
    if (!result) return;
    if (!confirm(t('detail.deleteConfirm'))) return;
    await api.deleteInspection(result.inspection_id);
    navigate('/inspections');
  }

  if (error) {
    return (
      <Empty title={t('common.error')} subtitle={error} />
    );
  }
  if (!data) {
    return (
      <div className="flex h-64 items-center justify-center text-slate-500">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
        {t('common.loading')}
      </div>
    );
  }

  if (data.status === 'queued' || data.status === 'processing') {
    return (
      <div className="mx-auto max-w-md py-20 text-center">
        <Loader2 className="mx-auto h-8 w-8 animate-spin text-brand-600" />
        <h2 className="mt-4 text-lg font-semibold text-slate-900 dark:text-white">
          {data.status === 'queued' ? t('detail.queued') : t('detail.processing')}
        </h2>
      </div>
    );
  }

  if (data.status === 'failed' || !result) {
    return <Empty title={t('detail.failed')} subtitle={data.error ?? ''} />;
  }

  // Convert normalized polygons (0..1) to image-pixel coordinates so the
  // ImageAnnotator can draw them on the canvas matching the image's natural size.
  const imgW = result.image?.width ?? 0;
  const imgH = result.image?.height ?? 0;
  const partsForOverlay = result.parts.map((p) => ({
    name: p.name,
    status: p.status,
    points: (p.polygon_normalized ?? []).map(
      (pt) => [(pt[0] ?? 0) * imgW, (pt[1] ?? 0) * imgH] as number[],
    ),
  }));

  const damagesForOverlay = damages
    .filter((d) => Array.isArray(d.bbox) && d.bbox.length === 4)
    .map((d) => ({
      id: d.id,
      bbox: d.bbox as [number, number, number, number],
      label: d.type,
      severity: d.severity,
    }));

  return (
    <div className="mx-auto max-w-7xl space-y-5">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
            {t('detail.title')}
          </h1>
          <p className="mt-1 font-mono text-xs text-slate-500">{result.inspection_id}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={handleExportCsv}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
          >
            <Download className="h-4 w-4" />
            CSV
          </button>
          <button
            type="button"
            onClick={handleExportPdf}
            disabled={exporting}
            className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {exporting ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <FileText className="h-4 w-4" />
            )}
            {t('detail.exportReport')}
          </button>
          <button
            type="button"
            onClick={handleDelete}
            className="inline-flex items-center gap-2 rounded-lg border border-red-200 bg-white px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50 dark:border-red-800 dark:bg-slate-800 dark:hover:bg-red-900/20"
          >
            <Trash2 className="h-4 w-4" />
            {t('detail.delete')}
          </button>
        </div>
      </div>

      {/* Main */}
      <div className="grid gap-5 lg:grid-cols-[1.6fr_1fr]">
        <div className="space-y-3">
          {/* Mode toggle */}
          <div className="flex gap-1 rounded-lg bg-slate-100 p-1 dark:bg-slate-800">
            {(['both', 'parts', 'damages'] as Mode[]).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={`flex flex-1 items-center justify-center rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                  mode === m
                    ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-700 dark:text-white'
                    : 'text-slate-600 hover:text-slate-900 dark:text-slate-300'
                }`}
              >
                {t(`detail.view${m === 'both' ? 'Both' : m === 'parts' ? 'Parts' : 'Damages'}`)}
              </button>
            ))}
          </div>

          {images.length > 0 ? (
            <div className="relative">
              <ImageAnnotator
                imageUrl={images[imageIdx] ?? ''}
                parts={partsForOverlay}
                damages={damagesForOverlay}
                mode={mode}
                highlightedPart={hoveredPart}
                highlightedDamageId={hoveredDamage}
              />
              {images.length > 1 && (
                <>
                  <button
                    type="button"
                    onClick={() => setImageIdx((i) => Math.max(0, i - 1))}
                    disabled={imageIdx === 0}
                    className="absolute left-2 top-1/2 inline-flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-white/80 text-slate-800 shadow disabled:opacity-30 dark:bg-slate-800/80 dark:text-slate-100"
                  >
                    <ChevronLeft className="h-5 w-5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setImageIdx((i) => Math.min(images.length - 1, i + 1))}
                    disabled={imageIdx >= images.length - 1}
                    className="absolute right-2 top-1/2 inline-flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-white/80 text-slate-800 shadow disabled:opacity-30 dark:bg-slate-800/80 dark:text-slate-100"
                  >
                    <ChevronRight className="h-5 w-5" />
                  </button>
                  <div className="absolute bottom-2 left-1/2 -translate-x-1/2 rounded-full bg-black/60 px-2 py-0.5 text-xs text-white">
                    {imageIdx + 1} / {images.length}
                  </div>
                </>
              )}
            </div>
          ) : (
            <Empty title="—" subtitle="" />
          )}
        </div>

        <div className="space-y-4">
          <CostDisplay summary={result.summary ?? {}} />
          <section>
            <h2 className="mb-2 text-sm font-semibold text-slate-800 dark:text-slate-100">
              {t('detail.summary')}
            </h2>
            <div className="rounded-xl border border-slate-200 bg-white p-3 text-sm dark:border-slate-700 dark:bg-slate-800">
              <SummaryFacts result={result} />
            </div>
          </section>
        </div>
      </div>

      {/* Parts */}
      <section>
        <h2 className="mb-3 text-sm font-semibold text-slate-800 dark:text-slate-100">
          {t('detail.damagedParts')}
        </h2>
        <PartsList
          parts={result.parts as unknown as { name: string; status: string; damages: unknown[] }[]}
          onHover={setHoveredPart}
          highlightedPart={hoveredPart}
        />
      </section>

      {/* Damage table */}
      <section>
        <h2 className="mb-3 text-sm font-semibold text-slate-800 dark:text-slate-100">
          {t('inspections.damages')}
        </h2>
        <DamageTable damages={damages} onRowHover={setHoveredDamage} />
      </section>
    </div>
  );
}

function SummaryFacts({ result }: { result: Inspection }) {
  const damagedParts = result.parts.filter((p) => p.status !== 'clean');
  const cleanParts = result.parts.filter((p) => p.status === 'clean');
  const sevCounts: Partial<Record<Severity, number>> = {};
  for (const p of result.parts) {
    for (const d of p.damages) {
      const sev = d.severity?.level as Severity | undefined;
      if (sev) sevCounts[sev] = (sevCounts[sev] ?? 0) + 1;
    }
  }
  return (
    <dl className="space-y-1.5">
      <Row label="Hasarlı parça" value={damagedParts.length} />
      <Row label="Hasarsız parça" value={cleanParts.length} />
      <div className="flex flex-wrap items-center gap-1 pt-1">
        {(['agir', 'orta', 'hafif'] as Severity[]).map((s) =>
          sevCounts[s] ? (
            <span key={s} className="inline-flex items-center gap-1">
              <SeverityBadge severity={s} size="sm" />
              <span className="text-xs tabular-nums text-slate-600 dark:text-slate-300">
                ×{sevCounts[s]}
              </span>
            </span>
          ) : null,
        )}
      </div>
    </dl>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-xs text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="font-semibold text-slate-800 dark:text-slate-100">{value}</dd>
    </div>
  );
}

function Empty({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="mx-auto max-w-md py-16 text-center">
      <AlertCircle className="mx-auto h-10 w-10 text-slate-400" />
      <h2 className="mt-3 text-base font-semibold text-slate-800 dark:text-slate-100">{title}</h2>
      {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
    </div>
  );
}
