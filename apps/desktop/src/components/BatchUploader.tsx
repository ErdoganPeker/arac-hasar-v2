/**
 * BatchUploader — drag-and-drop / picker batch processor.
 *
 * Features:
 *  - Accepts up to 50 images via drop, native picker, or folder import (Tauri).
 *  - Per-file queue with statuses: queued | uploading | processing | done | failed.
 *  - Concurrency: 3 in-flight uploads at a time (configurable).
 *  - Per-file progress bar driven by axios `onUploadProgress`.
 *  - Retry-on-fail on any failed row.
 *  - CSV export of the entire queue when finished.
 *
 * Uses the legacy ApiClient (no auth changes) and routes via `api.createInspection`.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  CheckCircle2,
  CircleAlert,
  FolderOpen,
  Loader2,
  Pause,
  Play,
  RefreshCw,
  Trash2,
  Upload,
  X,
  Download,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';
import { api } from '@/lib/api';
import { pickImages, pickFolder } from '@/lib/file-picker';
import { pathToFile, showNotification } from '@/lib/commands';
import { readDir } from '@tauri-apps/plugin-fs';
import { inspectionsToCsv } from '@/lib/export';
import { saveReport } from '@/lib/commands';
import { MAX_FILE_SIZE_MB } from '@/lib/file-picker';

const MAX_FILES = 50;
const CONCURRENCY = 3;
const IMAGE_EXT = /\.(jpe?g|png|webp)$/i;
const MAX_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

type Status = 'queued' | 'uploading' | 'processing' | 'done' | 'failed';

interface QueueItem {
  id: string;
  file: File;
  preview: string;
  status: Status;
  progress: number; // 0..100
  inspectionId?: string;
  damageCount?: number;
  totalCostMid?: number;
  error?: string;
}

function genId(): string {
  return `q_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

export function BatchUploader() {
  const { t } = useTranslation();
  const [items, setItems] = useState<QueueItem[]>([]);
  const [running, setRunning] = useState(false);
  const [paused, setPaused] = useState(false);
  const pausedRef = useRef(false);
  const stopRef = useRef(false);
  const [dragOver, setDragOver] = useState(false);

  const stats = useMemo(() => {
    const total = items.length;
    const done = items.filter((i) => i.status === 'done').length;
    const failed = items.filter((i) => i.status === 'failed').length;
    return { total, done, failed };
  }, [items]);

  // ───── Add files ─────
  const addFiles = useCallback((files: File[]) => {
    setItems((cur) => {
      const room = MAX_FILES - cur.length;
      if (room <= 0) return cur;
      const newItems: QueueItem[] = files.slice(0, room).map((file) => ({
        id: genId(),
        file,
        preview: URL.createObjectURL(file),
        status: 'queued',
        progress: 0,
      }));
      return [...cur, ...newItems];
    });
  }, []);

  const handlePickFiles = useCallback(async () => {
    const picked = await pickImages({ multiple: true });
    if (picked.length) addFiles(picked);
  }, [addFiles]);

  // Window-level OS drag drops are relayed here as a DOM CustomEvent by
  // <WindowFileDrop /> at the app shell level — pick them up.
  useEffect(() => {
    function onDropped(e: Event) {
      const ev = e as CustomEvent<{ files: File[] }>;
      if (ev.detail?.files?.length) addFiles(ev.detail.files);
    }
    window.addEventListener('hasarui:files-dropped', onDropped as EventListener);
    return () =>
      window.removeEventListener('hasarui:files-dropped', onDropped as EventListener);
  }, [addFiles]);

  const handlePickFolder = useCallback(async () => {
    const folder = await pickFolder();
    if (!folder) return;
    try {
      const entries = await readDir(folder);
      const sep = folder.includes('\\') ? '\\' : '/';
      const imagePaths = entries
        .filter((e) => !e.isDirectory && IMAGE_EXT.test(e.name))
        .map((e) => `${folder}${sep}${e.name}`);
      const files = await Promise.all(imagePaths.map((p) => pathToFile(p)));
      addFiles(files);
    } catch (e) {
      console.error(e);
    }
  }, [addFiles]);

  const removeItem = useCallback((id: string) => {
    setItems((cur) => {
      const out: QueueItem[] = [];
      for (const it of cur) {
        if (it.id === id) URL.revokeObjectURL(it.preview);
        else out.push(it);
      }
      return out;
    });
  }, []);

  const clearQueue = useCallback(() => {
    setItems((cur) => {
      cur.forEach((i) => URL.revokeObjectURL(i.preview));
      return [];
    });
  }, []);

  const setItemStatus = useCallback((id: string, patch: Partial<QueueItem>) => {
    setItems((cur) => cur.map((it) => (it.id === id ? { ...it, ...patch } : it)));
  }, []);

  // ───── Drag-and-drop ─────
  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };
  const onDragLeave = () => setDragOver(false);
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const all = Array.from(e.dataTransfer.files).filter(
      (f) => IMAGE_EXT.test(f.name) || f.type.startsWith('image/'),
    );
    const accepted = all.filter((f) => f.size <= MAX_BYTES);
    const rejected = all
      .filter((f) => f.size > MAX_BYTES)
      .map((f) => ({ name: f.name, size: f.size }));
    if (rejected.length) {
      window.dispatchEvent(
        new CustomEvent('hasarui:file-size-rejected', {
          detail: { rejected, maxMb: MAX_FILE_SIZE_MB },
        }),
      );
    }
    if (accepted.length) addFiles(accepted);
  };

  // ───── Run pipeline ─────
  const runOne = useCallback(
    async (item: QueueItem) => {
      setItemStatus(item.id, { status: 'uploading', progress: 0, error: undefined });
      try {
        const res = await api.createInspection([item.file], 'sync', (pct) => {
          setItemStatus(item.id, { progress: pct });
        });
        const id =
          'inspection_id' in res
            ? (res.inspection_id as string)
            : ((res as { inspection_id: string }).inspection_id ?? '');
        setItemStatus(item.id, { status: 'processing', progress: 100, inspectionId: id });

        // If it's an async create, poll briefly; sync responses already include result.
        if ('result' in res && (res as { result?: unknown }).result) {
          const r = (res as { result: { summary?: { total_cost_midpoint_tl?: number }; parts?: { damages: unknown[] }[] } }).result;
          const dc = (r.parts ?? []).reduce((s, p) => s + (p.damages?.length ?? 0), 0);
          setItemStatus(item.id, {
            status: 'done',
            damageCount: dc,
            totalCostMid: r.summary?.total_cost_midpoint_tl,
          });
          return;
        }

        // Poll
        for (let i = 0; i < 60; i++) {
          if (stopRef.current) return;
          while (pausedRef.current) await sleep(300);
          await sleep(1500);
          const st = await api.getInspection(id);
          if (st.status === 'completed' && st.result) {
            const r = st.result;
            const dc = r.parts.reduce((s, p) => s + p.damages.length, 0);
            setItemStatus(item.id, {
              status: 'done',
              damageCount: dc,
              totalCostMid: r.summary?.total_cost_midpoint_tl,
            });
            return;
          }
          if (st.status === 'failed') {
            setItemStatus(item.id, { status: 'failed', error: st.error || 'failed' });
            return;
          }
        }
        setItemStatus(item.id, { status: 'failed', error: 'timeout' });
      } catch (e) {
        setItemStatus(item.id, {
          status: 'failed',
          error: e instanceof Error ? e.message : String(e),
        });
      }
    },
    [setItemStatus],
  );

  const startBatch = useCallback(async () => {
    if (running) return;
    stopRef.current = false;
    pausedRef.current = false;
    setRunning(true);

    // Worker pool: pick up `queued` items one by one until exhausted.
    const queue = () =>
      // Read latest items from React state via functional setter trick.
      new Promise<QueueItem | null>((resolve) => {
        setItems((cur) => {
          const next = cur.find((i) => i.status === 'queued');
          resolve(next ?? null);
          return cur;
        });
      });

    const worker = async () => {
      while (true) {
        if (stopRef.current) return;
        while (pausedRef.current) await sleep(250);
        const next = await queue();
        if (!next) return;
        // Mark as uploading immediately so other workers don't pick it up.
        setItemStatus(next.id, { status: 'uploading' });
        await runOne(next);
      }
    };

    await Promise.all(Array.from({ length: CONCURRENCY }, () => worker()));
    setRunning(false);
    // Summary toast — fires even when OS notifications are blocked.
    const failedCount = await new Promise<number>((resolve) => {
      setItems((cur) => {
        resolve(cur.filter((i) => i.status === 'failed').length);
        return cur;
      });
    });
    window.dispatchEvent(
      new CustomEvent('hasarui:toast', {
        detail: {
          kind: failedCount > 0 ? 'error' : 'success',
          message:
            failedCount > 0
              ? `${failedCount} ${t('batch.failed')}`
              : t('tray.lastInspection'),
        },
      }),
    );
    await showNotification(t('app.name'), t('tray.lastInspection'));
  }, [running, runOne, setItemStatus, t]);

  const pauseBatch = useCallback(() => {
    pausedRef.current = true;
    setPaused(true);
  }, []);
  const resumeBatch = useCallback(() => {
    pausedRef.current = false;
    setPaused(false);
  }, []);
  const retryItem = useCallback(
    (id: string) => {
      setItemStatus(id, { status: 'queued', progress: 0, error: undefined });
      if (!running) startBatch();
    },
    [running, setItemStatus, startBatch],
  );

  // ───── CSV export ─────
  const exportCsv = useCallback(async () => {
    const rows = items
      .filter((i) => i.status === 'done' && i.inspectionId)
      .map((i) => ({
        inspection_id: i.inspectionId!,
        created_at: new Date().toISOString(),
        status: 'completed' as const,
        damage_count: i.damageCount ?? 0,
        total_cost_midpoint_tl: i.totalCostMid,
      }));
    const csv = inspectionsToCsv(rows);
    await saveReport({
      inspectionId: `batch_${Date.now()}`,
      format: 'csv',
      content: csv,
    });
  }, [items]);

  return (
    <div className="space-y-4">
      <div
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        className={`flex flex-col items-center justify-center rounded-2xl border-2 border-dashed p-10 text-center transition-colors ${
          dragOver
            ? 'border-brand-500 bg-brand-50 dark:bg-brand-900/20'
            : 'border-slate-300 bg-slate-50 hover:border-slate-400 dark:border-slate-700 dark:bg-slate-900/40'
        }`}
      >
        <Upload className="h-10 w-10 text-slate-400" />
        <div className="mt-3 font-semibold text-slate-700 dark:text-slate-200">
          {t('batch.dropHere')}
        </div>
        <div className="text-sm text-slate-500">{t('batch.orClick')}</div>
        <div className="mt-4 flex gap-2">
          <button
            type="button"
            onClick={handlePickFiles}
            className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white hover:bg-brand-700"
          >
            <Upload className="h-4 w-4" />
            {t('batch.pickFiles')}
          </button>
          <button
            type="button"
            onClick={handlePickFolder}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
          >
            <FolderOpen className="h-4 w-4" />
            {t('batch.pickFolder')}
          </button>
        </div>
        <div className="mt-3 text-xs text-slate-400">
          {items.length}/{MAX_FILES}
          {items.length >= MAX_FILES && (
            <span className="ml-2 text-amber-600">{t('batch.limitReached')}</span>
          )}
        </div>
      </div>

      {items.length > 0 && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-sm text-slate-600 dark:text-slate-300">
              {t('batch.completed', { done: stats.done, total: stats.total })}
              {stats.failed > 0 && (
                <span className="ml-2 text-red-600">· {stats.failed} {t('batch.failed')}</span>
              )}
            </div>
            <div className="flex gap-2">
              {!running ? (
                <button
                  type="button"
                  onClick={startBatch}
                  className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white hover:bg-brand-700"
                >
                  <Play className="h-4 w-4" />
                  {t('batch.startBatch')}
                </button>
              ) : paused ? (
                <button
                  type="button"
                  onClick={resumeBatch}
                  className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-3 py-2 text-sm font-semibold text-white hover:bg-brand-700"
                >
                  <Play className="h-4 w-4" />
                  {t('batch.resumeBatch')}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={pauseBatch}
                  className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
                >
                  <Pause className="h-4 w-4" />
                  {t('batch.pauseBatch')}
                </button>
              )}
              <button
                type="button"
                onClick={exportCsv}
                disabled={stats.done === 0}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
              >
                <Download className="h-4 w-4" />
                {t('batch.exportCsv')}
              </button>
              <button
                type="button"
                onClick={clearQueue}
                disabled={running}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
              >
                <Trash2 className="h-4 w-4" />
                {t('batch.clearQueue')}
              </button>
            </div>
          </div>

          <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500 dark:bg-slate-900/40 dark:text-slate-400">
                <tr>
                  <th className="px-3 py-2">#</th>
                  <th className="px-3 py-2">Önizleme</th>
                  <th className="px-3 py-2">Dosya</th>
                  <th className="px-3 py-2 w-44">Durum</th>
                  <th className="px-3 py-2 w-32">Hasar</th>
                  <th className="px-3 py-2 w-24"></th>
                </tr>
              </thead>
              <tbody>
                {items.map((it, i) => (
                  <tr key={it.id} className="border-t border-slate-200 dark:border-slate-700">
                    <td className="px-3 py-2 tabular-nums text-slate-500">{i + 1}</td>
                    <td className="px-3 py-2">
                      <img
                        src={it.preview}
                        alt=""
                        className="h-10 w-14 rounded object-cover"
                      />
                    </td>
                    <td className="max-w-xs truncate px-3 py-2 font-mono text-xs text-slate-700 dark:text-slate-200">
                      {it.file.name}
                    </td>
                    <td className="px-3 py-2">
                      <StatusCell item={it} />
                    </td>
                    <td className="px-3 py-2 tabular-nums">
                      {it.status === 'done' ? (
                        <span className="text-slate-700 dark:text-slate-200">
                          {it.damageCount ?? 0}
                          {it.totalCostMid !== undefined && (
                            <span className="ml-1 text-xs text-slate-500">
                              · {it.totalCostMid.toLocaleString('tr-TR')} ₺
                            </span>
                          )}
                        </span>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex justify-end gap-1">
                        {it.status === 'failed' && (
                          <button
                            type="button"
                            onClick={() => retryItem(it.id)}
                            className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                            title={t('batch.retry')}
                          >
                            <RefreshCw className="h-4 w-4" />
                          </button>
                        )}
                        {it.status === 'done' && it.inspectionId && (
                          <Link
                            to={`/inspection/${it.inspectionId}`}
                            className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                            title={t('batch.view')}
                          >
                            <CheckCircle2 className="h-4 w-4" />
                          </Link>
                        )}
                        <button
                          type="button"
                          onClick={() => removeItem(it.id)}
                          className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-700 dark:hover:text-slate-200"
                          title={t('batch.remove')}
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

function StatusCell({ item }: { item: QueueItem }) {
  const { t } = useTranslation();
  if (item.status === 'queued') {
    return <span className="text-xs text-slate-500">{t('batch.queued')}</span>;
  }
  if (item.status === 'uploading') {
    return (
      <div className="flex items-center gap-2">
        <Loader2 className="h-3.5 w-3.5 animate-spin text-brand-600" />
        <div className="w-full">
          <div className="text-xs text-slate-600 dark:text-slate-300">
            {t('batch.uploading')} {item.progress}%
          </div>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
            <div
              className="h-full bg-brand-500 transition-all"
              style={{ width: `${item.progress}%` }}
            />
          </div>
        </div>
      </div>
    );
  }
  if (item.status === 'processing') {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-amber-600">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        {t('batch.processing')}
      </span>
    );
  }
  if (item.status === 'done') {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-emerald-600">
        <CheckCircle2 className="h-3.5 w-3.5" />
        {t('batch.done')}
      </span>
    );
  }
  return (
    <span
      className="inline-flex items-center gap-1 text-xs text-red-600"
      title={item.error}
    >
      <CircleAlert className="h-3.5 w-3.5" />
      {t('batch.failed')}
    </span>
  );
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

export default BatchUploader;
