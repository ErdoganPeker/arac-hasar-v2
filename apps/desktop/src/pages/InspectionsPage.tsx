/**
 * InspectionsPage — denser table view with sort + filter + CSV/PDF export.
 *
 * - Paginated through `api.listInspections` (page_size 50).
 * - Client-side: text search (id), date filter (today / 7d / 30d / all), sort by date / cost / damages.
 * - Export entire current view as CSV via `saveReport` (CSV is generated client-side).
 */
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { ArrowDown, ArrowUp, Download, Search, X } from 'lucide-react';
import type { InspectionListItem } from '@arac-hasar/types';
import { api } from '@/lib/api';
import { inspectionsToCsv } from '@/lib/export';
import { saveReport } from '@/lib/commands';

type SortKey = 'created_at' | 'damage_count' | 'total_cost_midpoint_tl';
type DateFilter = 'all' | 'today' | '7d' | '30d';

export default function InspectionsPage() {
  const { t } = useTranslation();
  const [items, setItems] = useState<InspectionListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [dateFilter, setDateFilter] = useState<DateFilter>('all');
  const [sortKey, setSortKey] = useState<SortKey>('created_at');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const res = await api.listInspections(page, 50);
        if (cancelled) return;
        setItems((cur) => (page === 1 ? res.items : [...cur, ...res.items]));
        setHasMore(res.items.length >= 50);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Error');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [page]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const now = Date.now();
    const cutoff =
      dateFilter === 'today'
        ? new Date(new Date().setHours(0, 0, 0, 0)).getTime()
        : dateFilter === '7d'
          ? now - 7 * 86400_000
          : dateFilter === '30d'
            ? now - 30 * 86400_000
            : 0;
    let arr = items.filter((it) => {
      if (q && !it.inspection_id.toLowerCase().includes(q)) return false;
      if (cutoff && new Date(it.created_at).getTime() < cutoff) return false;
      return true;
    });
    arr = [...arr].sort((a, b) => {
      const av =
        sortKey === 'created_at'
          ? new Date(a.created_at).getTime()
          : (a as unknown as Record<SortKey, number>)[sortKey] ?? 0;
      const bv =
        sortKey === 'created_at'
          ? new Date(b.created_at).getTime()
          : (b as unknown as Record<SortKey, number>)[sortKey] ?? 0;
      if (av === bv) return 0;
      return sortDir === 'asc' ? (av < bv ? -1 : 1) : av > bv ? -1 : 1;
    });
    return arr;
  }, [items, search, dateFilter, sortKey, sortDir]);

  function header(key: SortKey, label: string) {
    const active = sortKey === key;
    return (
      <th
        className="cursor-pointer select-none px-3 py-2 hover:text-slate-700 dark:hover:text-slate-200"
        onClick={() => {
          if (active) setSortDir(sortDir === 'asc' ? 'desc' : 'asc');
          else {
            setSortKey(key);
            setSortDir('desc');
          }
        }}
      >
        <span className="inline-flex items-center gap-1">
          {label}
          {active &&
            (sortDir === 'asc' ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
        </span>
      </th>
    );
  }

  async function exportCsv() {
    const csv = inspectionsToCsv(filtered);
    await saveReport({
      inspectionId: `inspections_${new Date().toISOString().slice(0, 10)}`,
      format: 'csv',
      content: csv,
    });
  }

  return (
    <div className="mx-auto max-w-7xl space-y-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
            {t('inspections.title')}
          </h1>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
            {t('inspections.subtitle')}
          </p>
        </div>
        <button
          type="button"
          onClick={exportCsv}
          disabled={filtered.length === 0}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
        >
          <Download className="h-4 w-4" />
          {t('inspections.exportCsv')}
        </button>
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap gap-2 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-800">
        <div className="relative flex-1">
          <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('inspections.search')}
            className="w-full rounded-md border border-slate-300 bg-white py-1.5 pl-8 pr-2 text-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
          />
          {search && (
            <button
              type="button"
              onClick={() => setSearch('')}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
        <select
          value={dateFilter}
          onChange={(e) => setDateFilter(e.target.value as DateFilter)}
          className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
        >
          <option value="all">{t('common.all')}</option>
          <option value="today">{t('dashboard.today')}</option>
          <option value="7d">{t('dashboard.week')}</option>
          <option value="30d">{t('dashboard.month')}</option>
        </select>
      </div>

      {/* Table */}
      <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wider text-slate-500 dark:bg-slate-900/40 dark:text-slate-400">
            <tr>
              <th className="px-3 py-2">{t('inspections.id')}</th>
              {header('created_at', t('inspections.date'))}
              {header('damage_count', t('inspections.damages'))}
              {header('total_cost_midpoint_tl', t('inspections.cost'))}
              <th className="px-3 py-2 text-right">{t('inspections.actions')}</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((it) => (
              <tr
                key={it.inspection_id}
                className="border-t border-slate-200 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800"
              >
                <td className="px-3 py-2 font-mono text-xs text-slate-700 dark:text-slate-300">
                  {it.inspection_id.slice(0, 12)}…
                </td>
                <td className="px-3 py-2 text-slate-700 dark:text-slate-200">
                  {new Date(it.created_at).toLocaleString()}
                </td>
                <td className="px-3 py-2 tabular-nums text-slate-700 dark:text-slate-200">
                  {it.damage_count}
                </td>
                <td className="px-3 py-2 tabular-nums text-slate-700 dark:text-slate-200">
                  {it.total_cost_midpoint_tl?.toLocaleString('tr-TR') ?? '—'} ₺
                </td>
                <td className="px-3 py-2 text-right">
                  <Link
                    to={`/inspection/${it.inspection_id}`}
                    className="rounded-md px-2 py-1 text-xs font-medium text-brand-600 hover:bg-brand-50 dark:hover:bg-brand-900/30"
                  >
                    {t('common.open')} →
                  </Link>
                </td>
              </tr>
            ))}
            {!loading && filtered.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-10 text-center text-sm text-slate-500">
                  {t('inspections.empty')}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {error && <div className="text-sm text-red-600">{error}</div>}

      {hasMore && (
        <div className="text-center">
          <button
            type="button"
            onClick={() => setPage((p) => p + 1)}
            disabled={loading}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
          >
            {loading ? t('common.loading') : t('inspections.loadMore')}
          </button>
        </div>
      )}
    </div>
  );
}
