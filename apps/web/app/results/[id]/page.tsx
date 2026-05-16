'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import { useTranslations } from 'next-intl';
import Link from 'next/link';
import dynamic from 'next/dynamic';
import {
  AlertTriangle,
  ArrowLeft,
  Camera,
  Layers,
  RefreshCw,
} from 'lucide-react';
import type {
  Damage,
  DamageType,
  Inspection,
  InspectionStatus,
} from '@arac-hasar/types';
import {
  InspectionSummary,
  CostDisplay,
  DamageBadge,
  Spinner,
  EmptyState,
} from '@arac-hasar/ui';
import { useInspectionPolling } from '@/lib/use-inspection-polling';
import {
  getUploadedPreviews,
  type UploadedPreview,
} from '@/lib/uploaded-previews';
import { PartList } from '@/components/PartList';

// ResultsTabs ships the heavy ImageWithOverlay (canvas + ResizeObserver).
// Defer it so the pending/queued state ships with a smaller initial chunk;
// the visualization only mounts when a `result` payload exists anyway.
const ResultsTabs = dynamic(
  () => import('@/components/ResultsTabs').then((m) => m.ResultsTabs),
  {
    ssr: false,
    loading: () => (
      <div className="flex h-64 items-center justify-center rounded-2xl border border-slate-200 bg-white">
        <Spinner size="lg" />
      </div>
    ),
  },
);

export default function ResultsPage() {
  const params = useParams<{ id: string }>();
  const inspectionId = params?.id ?? null;
  const t = useTranslations('inspect.result');
  const tNav = useTranslations('nav');
  const tCommon = useTranslations('common');

  const { data, loading, error, attempts, timedOut, paused, retry } =
    useInspectionPolling(inspectionId);

  const [highlightedPart, setHighlightedPart] = useState<string | null>(null);
  const [highlightedDamageId, setHighlightedDamageId] = useState<number | null>(
    null,
  );

  // Read previously-stashed uploaded photo thumbnails (set on the inspect
  // submit page before the redirect). Available even while the backend
  // result is not yet ready.
  const [uploadedPreviews, setUploadedPreviews] = useState<UploadedPreview[]>(
    [],
  );
  useEffect(() => {
    if (!inspectionId) return;
    setUploadedPreviews(getUploadedPreviews(inspectionId));
  }, [inspectionId]);

  const status = data?.status;
  const result = data?.result;

  return (
    <div className="container-page py-10">
      <header className="mb-6 flex items-center justify-between gap-4">
        <div>
          <Link
            href="/inspect"
            className="inline-flex items-center gap-1.5 text-sm text-slate-600 hover:text-slate-900"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden /> {tNav('newInspection')}
          </Link>
          <h1 className="mt-2 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
            {t('title')}
          </h1>
          <p className="mt-1 font-mono text-xs text-slate-500">
            {t('inspectionId')}: {inspectionId}
          </p>
        </div>
        {status && <StatusBadge status={status} />}
      </header>

      {error && status !== 'failed' && !paused && (
        <ErrorBanner message={error} />
      )}

      {!result &&
        (loading || status === 'queued' || status === 'processing') && (
          <PendingState
            attempts={attempts}
            status={status}
            previews={uploadedPreviews}
          />
        )}

      {status === 'failed' && (
        <EmptyState
          icon={<AlertTriangle className="h-8 w-8" />}
          title={t('failed')}
          description={data?.error ?? tCommon('errorGeneric')}
          action={
            <Link href="/inspect" className="btn-primary">
              <RefreshCw className="h-4 w-4" aria-hidden /> {tCommon('tryAgain')}
            </Link>
          }
        />
      )}

      {!result && paused && (
        <EmptyState
          icon={<RefreshCw className="h-8 w-8" />}
          title={t('pollPausedTitle')}
          description={t('pollPausedDesc')}
          action={
            // Pair "check again" (immediate retry) with "go to history" so
            // the user can leave the page without losing the work. Backend
            // keeps cooking either way — the inspection lands in history
            // once it completes.
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-center">
              <button type="button" onClick={retry} className="btn-primary">
                <RefreshCw className="h-4 w-4" aria-hidden />{' '}
                {t('checkAgain')}
              </button>
              <Link href="/history" className="btn-secondary">
                {tNav('history')}
              </Link>
            </div>
          }
        />
      )}

      {!result && timedOut && !paused && (
        <EmptyState
          icon={<AlertTriangle className="h-8 w-8" />}
          title={t('processing')}
          description={t('pollPausedDesc')}
          action={
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-center">
              <button type="button" onClick={retry} className="btn-primary">
                <RefreshCw className="h-4 w-4" aria-hidden />{' '}
                {t('checkAgain')}
              </button>
              <Link href="/history" className="btn-secondary">
                {tNav('history')}
              </Link>
            </div>
          }
        />
      )}

      {result && (
        <ResultsView
          result={result}
          uploadedPreviews={uploadedPreviews}
          highlightedPart={highlightedPart}
          setHighlightedPart={setHighlightedPart}
          highlightedDamageId={highlightedDamageId}
          setHighlightedDamageId={setHighlightedDamageId}
        />
      )}
    </div>
  );
}

interface ResultsViewProps {
  result: Inspection;
  uploadedPreviews: UploadedPreview[];
  highlightedPart: string | null;
  setHighlightedPart: (p: string | null) => void;
  highlightedDamageId: number | null;
  setHighlightedDamageId: (id: number | null) => void;
}

function ResultsView({
  result,
  uploadedPreviews,
  highlightedPart,
  setHighlightedPart,
  highlightedDamageId,
  setHighlightedDamageId,
}: ResultsViewProps) {
  const t = useTranslations('inspect.result');
  const tDmg = useTranslations('damageTypes');

  const partDamages = useMemo<Damage[]>(
    () => result.parts.flatMap((p) => p.damages),
    [result],
  );
  const multiPartDamages = result.multi_part_damages ?? [];
  const unassignedDamages = result.unassigned_damages ?? [];
  const allDamages = useMemo<Damage[]>(
    () => [...partDamages, ...multiPartDamages, ...unassignedDamages],
    [partDamages, multiPartDamages, unassignedDamages],
  );

  const damagedPartsCount = result.summary.damaged_parts_count ?? 0;
  const totalDamageCount =
    result.summary.total_damage_count ?? allDamages.length;

  // A clean inspection is ONLY when literally nothing was detected — neither
  // damaged parts nor unassigned/multi-part damages. The previous behaviour
  // of trusting `damaged_parts_count` alone hid the unassigned bucket.
  const isFullyClean =
    damagedPartsCount === 0 &&
    unassignedDamages.length === 0 &&
    multiPartDamages.length === 0;
  const hasUnassignedOnly =
    damagedPartsCount === 0 &&
    (unassignedDamages.length > 0 || multiPartDamages.length > 0);
  const isMixed = damagedPartsCount > 0 && unassignedDamages.length > 0;

  const annotatedUrl =
    result.visualization_urls?.annotated ?? result.image.url ?? '';

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      {/* Left: image + tabs */}
      <div className="lg:col-span-2">
        {/* Headline result line for mixed cases so the user immediately
            understands that not every damage was assigned to a part. */}
        {isMixed && (
          <div className="mb-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            <div className="flex items-start gap-2">
              <AlertTriangle
                className="mt-0.5 h-4 w-4 flex-none"
                aria-hidden
              />
              <div>
                <p className="font-semibold">
                  {t('mixedResultTitle', {
                    damagedParts: damagedPartsCount,
                    unassigned: unassignedDamages.length,
                  })}
                </p>
              </div>
            </div>
          </div>
        )}

        {hasUnassignedOnly && (
          <div className="mb-4 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
            <div className="flex items-start gap-2">
              <AlertTriangle
                className="mt-0.5 h-4 w-4 flex-none"
                aria-hidden
              />
              <p className="font-semibold">
                {t('unassignedDamagesAlertTitle')}
              </p>
            </div>
          </div>
        )}

        {annotatedUrl ? (
          <ResultsTabs
            imageUrl={annotatedUrl}
            parts={result.parts}
            damages={allDamages}
            highlightedPart={highlightedPart}
            highlightedDamageId={highlightedDamageId}
          />
        ) : uploadedPreviews.length > 0 ? (
          <UploadedPreviewGrid previews={uploadedPreviews} />
        ) : (
          <div className="flex h-64 items-center justify-center rounded-2xl border border-dashed border-slate-300 bg-white text-sm text-slate-500">
            {t('imageNotAvailable')}
          </div>
        )}

        {/* Show the originals alongside the annotated image when both exist
            (multi-foto async pipeline aggregates everything into one
            annotated view, so the user still benefits from seeing the
            original photos they uploaded). */}
        {annotatedUrl && uploadedPreviews.length > 0 && (
          <div className="mt-6">
            <UploadedPreviewGrid previews={uploadedPreviews} dense />
          </div>
        )}

        {/* Unassigned damages — promoted to a prominent alert when present.
            Previously this was a soft white panel that was easy to miss. */}
        {unassignedDamages.length > 0 && (
          <section className="mt-6 rounded-2xl border border-amber-300 bg-amber-50/70 p-5">
            <div className="flex items-center gap-2">
              <AlertTriangle
                className="h-4 w-4 text-amber-700"
                aria-hidden
              />
              <h2 className="font-semibold text-amber-900">
                {t('unassignedDamagesTitle')}{' '}
                <span className="text-xs font-medium text-amber-700">
                  ({unassignedDamages.length})
                </span>
              </h2>
            </div>
            <p className="mt-1 text-xs text-amber-800">
              {t('unassignedDamagesAlertDesc', {
                total: totalDamageCount,
                unassigned: unassignedDamages.length,
              })}
            </p>
            <div className="mt-3 space-y-2">
              {unassignedDamages.map((d) => (
                <DamageBadge key={d.id} damage={d} />
              ))}
            </div>
          </section>
        )}

        {/* Multi-part damages */}
        {multiPartDamages.length > 0 && (
          <section className="mt-6 rounded-2xl border border-orange-200 bg-orange-50/60 p-5">
            <div className="flex items-center gap-2">
              <Layers className="h-4 w-4 text-orange-700" aria-hidden />
              <h2 className="font-semibold text-orange-900">
                {t('multiPartDamagesTitle')}
              </h2>
            </div>
            <p className="mt-1 text-xs text-orange-800">
              {t('multiPartDamagesDesc')}
            </p>
            <div className="mt-3 space-y-2">
              {multiPartDamages.map((d) => (
                <div
                  key={d.id}
                  onMouseEnter={() => setHighlightedDamageId(d.id)}
                  onMouseLeave={() => setHighlightedDamageId(null)}
                >
                  <DamageBadge damage={d} />
                  {d.affected_parts && d.affected_parts.length > 0 && (
                    <p className="ml-2 mt-1 text-[11px] text-orange-800">
                      {t('affectedParts')}: {d.affected_parts.join(', ')}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

        {isFullyClean && (
          <section className="mt-6 rounded-2xl border border-emerald-200 bg-emerald-50/70 p-5 text-emerald-900">
            <h2 className="font-semibold">{t('noDamage')}</h2>
            <p className="mt-1 text-sm text-emerald-800">
              {t('noDamageSubtitle')}
            </p>
          </section>
        )}
      </div>

      {/* Right: cost + summary + parts */}
      <aside className="space-y-4">
        <CostDisplay summary={result.summary} />
        <InspectionSummary summary={result.summary} />

        <div className="rounded-2xl border border-slate-200 bg-white p-4 text-sm">
          <h3 className="font-semibold text-slate-900">{t('quickSummary')}</h3>
          <dl className="mt-3 space-y-2 text-slate-700">
            <Row
              label={t('overallSeverity')}
              value={result.summary.most_severe_level_tr ?? '—'}
            />
            <Row
              label={t('totalDamageArea')}
              value={`%${(result.summary.total_damage_area_ratio * 100).toFixed(1)}`}
            />
            <Row
              label={t('repairRecommendation')}
              value={result.summary.repair_recommendation_tr}
            />
          </dl>
          {allDamages.length > 0 && (
            <div className="mt-4 border-t border-slate-100 pt-3">
              <div className="text-xs uppercase tracking-wider text-slate-500">
                {t('damageTypesHeading')}
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {Array.from(new Set(allDamages.map((d) => d.type))).map((dt) => (
                  <span
                    key={dt}
                    className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700"
                  >
                    {translateDamageType(dt, tDmg)}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </aside>

      {/* Bottom: parts list spanning full width */}
      <div className="lg:col-span-3">
        <PartList
          parts={result.parts}
          onHoverPart={setHighlightedPart}
          onDamageClick={(id) => setHighlightedDamageId(id)}
        />
      </div>

      {/* AI cost disclaimer — must be visible on every completed report so
          there's no ambiguity about the report's legal weight. */}
      <div className="lg:col-span-3">
        <p
          role="note"
          className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs leading-relaxed text-slate-600"
        >
          <span className="font-semibold text-slate-700">⚠ </span>
          {t('disclaimer')}
        </p>
      </div>
    </div>
  );
}

function UploadedPreviewGrid({
  previews,
  dense = false,
}: {
  previews: UploadedPreview[];
  dense?: boolean;
}) {
  const t = useTranslations('inspect.result');
  return (
    <section
      aria-label={t('uploadedPreviewTitle')}
      className="rounded-2xl border border-slate-200 bg-white p-4"
    >
      <div className="flex items-center justify-between">
        <h2
          className={`font-semibold text-slate-900 ${dense ? 'text-sm' : 'text-base'}`}
        >
          {t('uploadedPreviewTitle')}
          <span className="ml-2 text-xs font-medium text-slate-500">
            ({previews.length})
          </span>
        </h2>
        {!dense && (
          <p className="text-xs text-slate-500">{t('uploadedPreviewDesc')}</p>
        )}
      </div>
      <div
        className={`mt-3 grid gap-2 ${
          dense
            ? 'grid-cols-4 sm:grid-cols-6'
            : 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-4'
        }`}
      >
        {previews.map((p, i) => (
          <div
            key={`${p.name}-${i}`}
            className="relative aspect-square overflow-hidden rounded-lg bg-slate-100"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={p.dataUrl}
              alt={p.name}
              loading="lazy"
              className="h-full w-full object-cover"
            />
          </div>
        ))}
      </div>
    </section>
  );
}

function translateDamageType(
  type: DamageType | string,
  tDmg: (key: string) => string,
): string {
  const KNOWN: ReadonlySet<string> = new Set([
    'dent',
    'scratch',
    'crack',
    'glass_shatter',
    'lamp_broken',
    'tire_flat',
  ]);
  if (KNOWN.has(type)) return tDmg(type);
  return tDmg('unknown');
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-slate-500">{label}</dt>
      <dd className="font-medium text-slate-900">{value}</dd>
    </div>
  );
}

function StatusBadge({ status }: { status: InspectionStatus }) {
  const t = useTranslations('status');
  const CLS: Record<InspectionStatus, string> = {
    queued: 'bg-slate-100 text-slate-700',
    processing: 'bg-amber-100 text-amber-800',
    completed: 'bg-emerald-100 text-emerald-800',
    failed: 'bg-red-100 text-red-800',
  };
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${CLS[status]}`}
    >
      {(status === 'queued' || status === 'processing') && (
        <Spinner size="sm" />
      )}
      {t(status)}
    </span>
  );
}

function PendingState({
  attempts,
  status,
  previews,
}: {
  attempts: number;
  status?: string;
  previews: UploadedPreview[];
}) {
  const t = useTranslations('inspect.result');
  const tStatus = useTranslations('status');
  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-slate-200 bg-white p-10 text-center shadow-sm">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-brand-100">
          <Spinner size="lg" />
        </div>
        <h2 className="mt-4 text-lg font-semibold text-slate-900">
          {t('processing')}
        </h2>
        <p className="mt-1 text-sm text-slate-600">
          {status === 'queued' ? tStatus('queued') : tStatus('processing')}
        </p>
        {attempts > 1 && (
          <p className="mt-2 text-xs text-slate-400">
            {t('pollAttempts', { count: attempts })}
          </p>
        )}
      </div>
      {previews.length > 0 && <UploadedPreviewGrid previews={previews} />}
      {previews.length === 0 && (
        <div className="rounded-2xl border border-dashed border-slate-200 p-4 text-center text-xs text-slate-400">
          <Camera className="mx-auto mb-1 h-5 w-5" aria-hidden />
          {t('loadingImage')}
        </div>
      )}
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="mb-4 flex items-start gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-800 ring-1 ring-red-200"
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 flex-none" aria-hidden />
      <span>{message}</span>
    </div>
  );
}
