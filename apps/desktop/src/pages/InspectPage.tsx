/**
 * InspectPage — single inspection flow (1-10 photos → sync/async submit).
 *
 * Adds:
 *  - listens for global `hasarui:open-file-shortcut` (Ctrl+O) and triggers the picker
 *  - respects settings.defaultUploadMode (falls back to size-based heuristic)
 *  - drops directly onto the page (Tauri window-level drop)
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { UploadDropzone, FilePreview, Spinner } from '@arac-hasar/ui';
import { FolderOpen, Play } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { pickImages } from '@/lib/file-picker';
import { api } from '@/lib/api';
import { loadSettings } from '@/lib/settings';

export default function InspectPage() {
  const { t } = useTranslation();
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [defaultMode, setDefaultMode] = useState<'sync' | 'async'>('async');
  const navigate = useNavigate();

  useEffect(() => {
    loadSettings().then((s) => setDefaultMode(s.defaultUploadMode));
  }, []);

  useEffect(() => {
    function onShortcut() {
      handleNativePick();
    }
    function onDropped(e: Event) {
      const ev = e as CustomEvent<{ files: File[] }>;
      if (ev.detail?.files?.length) {
        setFiles((cur) => [...cur, ...ev.detail.files]);
      }
    }
    window.addEventListener('hasarui:open-file-shortcut', onShortcut);
    window.addEventListener('hasarui:files-dropped', onDropped as EventListener);
    return () => {
      window.removeEventListener('hasarui:open-file-shortcut', onShortcut);
      window.removeEventListener('hasarui:files-dropped', onDropped as EventListener);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleNativePick() {
    const picked = await pickImages({ multiple: true });
    if (picked.length) setFiles((cur) => [...cur, ...picked]);
  }

  async function handleStart() {
    if (!files.length) return;
    setBusy(true);
    setError(null);
    try {
      const mode = defaultMode === 'sync' && files.length <= 3 ? 'sync' : 'async';
      const res = await api.createInspection(files, mode);
      const id =
        'inspection_id' in res
          ? res.inspection_id
          : (res as { inspection_id: string }).inspection_id;
      navigate(`/inspection/${id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Bilinmeyen hata');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
          {t('inspect.newTitle')}
        </h1>
        <p className="mt-1 text-slate-600 dark:text-slate-400">{t('inspect.newSubtitle')}</p>
      </div>

      <UploadDropzone
        onFiles={(f) => setFiles((cur) => [...cur, ...f])}
        maxFiles={20}
        hint={t('inspect.supportedFormats', { size: 12 })}
      />

      <div className="flex items-center justify-between">
        <button
          type="button"
          onClick={handleNativePick}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
        >
          <FolderOpen className="h-4 w-4" />
          {t('batch.pickFiles')}
        </button>
        <div className="text-sm text-slate-500">
          {t('inspect.filesSelected', { count: files.length })}
        </div>
      </div>

      {files.length > 0 && (
        <FilePreview
          files={files}
          onRemove={(i) => setFiles((cur) => cur.filter((_, idx) => idx !== i))}
        />
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          {error}
        </div>
      )}

      <div className="flex justify-end gap-3">
        <button
          type="button"
          onClick={() => setFiles([])}
          disabled={!files.length || busy}
          className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
        >
          {t('inspect.removeAll')}
        </button>
        <button
          type="button"
          onClick={handleStart}
          disabled={!files.length || busy}
          className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {busy ? <Spinner size="sm" /> : <Play className="h-4 w-4" />}
          {busy ? t('inspect.submitting') : t('inspect.submit')}
        </button>
      </div>
    </div>
  );
}
