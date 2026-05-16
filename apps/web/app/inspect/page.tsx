'use client';

import { useCallback, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import {
  Camera,
  CheckCircle2,
  Info,
  AlertTriangle,
  Zap,
  Clock,
  ShieldCheck,
} from 'lucide-react';
import { UploadDropzone, FilePreview, Spinner } from '@arac-hasar/ui';
import { classifyApiError, createInspection } from '@/lib/api';
import { stashUploadedPreviews } from '@/lib/uploaded-previews';

// Keep in sync with backend caps (services/backend/main.py).
const MAX_SYNC_FILES = 5;
const MAX_ASYNC_FILES = 20;

export default function InspectPage() {
  const router = useRouter();
  const t = useTranslations('inspect');
  const tCommon = useTranslations('common');
  const tErrHttp = useTranslations('errors.http');
  const tErrNet = useTranslations('errors.network');
  const [files, setFiles] = useState<File[]>([]);
  const [mode, setMode] = useState<'sync' | 'async'>('async');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onFiles = useCallback((incoming: File[]) => {
    setFiles((prev) => {
      const merged = [...prev, ...incoming];
      // Dedupe by name+size
      const seen = new Set<string>();
      return merged.filter((f) => {
        const key = `${f.name}::${f.size}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
    });
    setError(null);
  }, []);

  const removeFile = useCallback((index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const canSubmit = files.length > 0 && !submitting;
  const showSyncOption = files.length <= MAX_SYNC_FILES && files.length > 0;

  const effectiveMode = useMemo<'sync' | 'async'>(
    () => (files.length > MAX_SYNC_FILES ? 'async' : mode),
    [files.length, mode],
  );

  const handleSubmit = useCallback(async () => {
    if (!canSubmit) return;
    setError(null);
    setSubmitting(true);
    try {
      const res = await createInspection(files, { mode: effectiveMode });
      await stashUploadedPreviews(res.inspection_id, files);
      router.push(`/results/${res.inspection_id}`);
    } catch (err) {
      const info = classifyApiError(err);
      let message: string;
      if (info.kind === 'network') message = tErrNet('offline');
      else if (info.kind === 'timeout') message = tErrNet('timeout');
      else if (info.kind === 'badRequest' && info.detail) message = info.detail;
      else if (info.kind === 'validation' && info.detail) message = info.detail;
      else if (info.kind === 'tooLarge') message = tErrHttp('413');
      else if (info.kind === 'unsupportedMedia') message = tErrHttp('415');
      else if (info.kind === 'rateLimited') message = tErrHttp('429');
      else if (info.kind === 'server') message = tErrHttp('500');
      else message = info.detail ?? t('uploadFailed');
      setError(message);
      setSubmitting(false);
    }
  }, [canSubmit, files, effectiveMode, router, t, tErrHttp, tErrNet]);

  const tips = [
    t('tipNetClose'),
    t('tipFullVehicle'),
    t('tipDetail'),
    t('tipLight'),
  ];

  const angles = [
    t('angleLeft'),
    t('angleRight'),
    t('angleFront'),
    t('angleBack'),
  ];

  return (
    <div className="container-page py-10">
      <header className="mb-8">
        <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
          {t('newTitle')}
        </h1>
        <p className="mt-2 max-w-2xl text-slate-600">{t('newSubtitle')}</p>
      </header>

      <div className="grid gap-8 lg:grid-cols-3">
        {/* Main upload column */}
        <section className="lg:col-span-2">
          <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-lg font-semibold text-slate-900">
              {t('uploadStep')}
            </h2>
            <p className="mt-1 text-sm text-slate-500">{t('uploadHint')}</p>

            {/* KVKK / privacy notice — mirrors /inspect/new. */}
            <div
              role="note"
              className="mt-3 flex items-start gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-xs text-emerald-900 ring-1 ring-emerald-200"
            >
              <ShieldCheck className="mt-0.5 h-3.5 w-3.5 flex-none" aria-hidden />
              <span>
                <strong className="font-semibold">{t('kvkkNoticeTitle')}: </strong>
                {t('kvkkNotice')}
              </span>
            </div>

            <div className="mt-4">
              <UploadDropzone
                onFiles={onFiles}
                multiple
                maxFiles={MAX_ASYNC_FILES}
              />
            </div>

            {files.length > 0 && (
              <div className="mt-6">
                <div className="mb-3 flex items-center justify-between">
                  <span className="text-sm font-medium text-slate-700">
                    {t('filesSelected', { count: files.length })}
                  </span>
                  <button
                    type="button"
                    onClick={() => setFiles([])}
                    className="text-xs font-medium text-slate-500 underline-offset-2 hover:underline"
                  >
                    {t('removeAll')}
                  </button>
                </div>
                <FilePreview files={files} onRemove={removeFile} />
              </div>
            )}
          </div>

          {/* Mode selection */}
          {files.length > 0 && (
            <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-lg font-semibold text-slate-900">
                {t('modeStep')}
              </h2>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <ModeOption
                  active={effectiveMode === 'async'}
                  disabled={false}
                  onClick={() => setMode('async')}
                  icon={Clock}
                  title={t('modeAsync')}
                  desc={t('modeAsyncDesc')}
                />
                <ModeOption
                  active={effectiveMode === 'sync'}
                  disabled={!showSyncOption}
                  onClick={() => showSyncOption && setMode('sync')}
                  icon={Zap}
                  title={t('modeSync')}
                  desc={t('modeSyncDesc')}
                />
              </div>
            </div>
          )}

          {/* Submit */}
          <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            {error && (
              <div
                role="alert"
                className="flex flex-1 items-start gap-2 rounded-lg bg-red-50 p-3 text-sm text-red-800 ring-1 ring-red-200"
              >
                <AlertTriangle
                  className="mt-0.5 h-4 w-4 flex-none"
                  aria-hidden
                />
                <span>{error}</span>
              </div>
            )}
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!canSubmit}
              className="btn-primary sm:ml-auto"
              aria-busy={submitting}
            >
              {submitting ? (
                <>
                  <Spinner size="sm" /> {tCommon('uploading')}
                </>
              ) : (
                <>
                  <Camera className="h-4 w-4" aria-hidden />
                  {t('submit')}
                </>
              )}
            </button>
          </div>
        </section>

        {/* Side rail: guidelines */}
        <aside>
          <div className="sticky top-20 space-y-4">
            <div className="rounded-2xl border border-brand-200 bg-brand-50/60 p-5">
              <div className="flex items-center gap-2 text-brand-900">
                <Info className="h-4 w-4" aria-hidden />
                <h3 className="font-semibold">{t('tipsTitle')}</h3>
              </div>
              <ul className="mt-3 space-y-2 text-sm text-slate-700">
                {tips.map((h) => (
                  <li key={h} className="flex items-start gap-2">
                    <CheckCircle2
                      className="mt-0.5 h-4 w-4 flex-none text-brand-600"
                      aria-hidden
                    />
                    <span>{h}</span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-5">
              <h3 className="font-semibold text-slate-900">{t('anglesTitle')}</h3>
              <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-600">
                {angles.map((label) => (
                  <AngleTile key={label} label={label} />
                ))}
              </div>
              <p className="mt-3 text-xs text-slate-500">{t('anglesNote')}</p>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

interface ModeOptionProps {
  active: boolean;
  disabled: boolean;
  onClick: () => void;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  desc: string;
}

function ModeOption({
  active,
  disabled,
  onClick,
  icon: Icon,
  title,
  desc,
}: ModeOptionProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      className={`flex items-start gap-3 rounded-xl border p-4 text-left transition-colors ${
        active
          ? 'border-brand-500 bg-brand-50 ring-1 ring-brand-500'
          : 'border-slate-200 bg-white hover:border-slate-300'
      } ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'}`}
    >
      <span
        className={`flex h-9 w-9 flex-none items-center justify-center rounded-lg ${
          active ? 'bg-brand-600 text-white' : 'bg-slate-100 text-slate-600'
        }`}
      >
        <Icon className="h-4 w-4" aria-hidden />
      </span>
      <span>
        <span className="block font-semibold text-slate-900">{title}</span>
        <span className="mt-0.5 block text-xs text-slate-600">{desc}</span>
      </span>
    </button>
  );
}

function AngleTile({ label }: { label: string }) {
  return (
    <div className="flex aspect-square items-center justify-center rounded-lg bg-slate-100 text-center font-medium text-slate-700">
      {label}
    </div>
  );
}
