'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { useTranslations } from 'next-intl';
import {
  Camera,
  AlertTriangle,
  ImageOff,
  LogIn,
  Search,
} from 'lucide-react';
import type {
  InspectionListItem,
  InspectionStatus,
} from '@arac-hasar/types';
import { EmptyState, Skeleton } from '@arac-hasar/ui';
import { classifyApiError, listInspections } from '@/lib/api';
import { InspectionStatusBadge } from '@/components/InspectionStatusBadge';

const STATUS_OPTIONS: InspectionStatus[] = [
  'queued',
  'processing',
  'completed',
  'failed',
];

const PAGE_SIZE = 12;

export default function HistoryPage() {
  const t = useTranslations('history');
  const tc = useTranslations('common');

  const tAuth = useTranslations('auth');
  const tErrHttp = useTranslations('errors.http');
  const tErrNet = useTranslations('errors.network');

  const [items, setItems] = useState<InspectionListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  /** Distinguish 401 from generic errors so we can prompt re-login. */
  const [sessionLost, setSessionLost] = useState(false);

  const [statusFilter, setStatusFilter] = useState<InspectionStatus | ''>('');
  const [query, setQuery] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setSessionLost(false);
    (async () => {
      try {
        const data = await listInspections({
          page,
          pageSize: PAGE_SIZE,
          status: (statusFilter || undefined) as InspectionStatus | undefined,
          dateFrom: dateFrom || undefined,
          dateTo: dateTo || undefined,
          query: query.trim() || undefined,
        });
        if (cancelled) return;
        setItems(data.items ?? []);
        setTotal(data.total ?? data.items?.length ?? 0);
        setError(null);
      } catch (err) {
        if (cancelled) return;
        // BUG-4: previously fell back to demo data on any failure, which
        // masked an expired session as "the backend is just slow". Surface
        // the real reason so the user can recover (re-login on 401, retry
        // on network blips). Never inject fake rows into the table.
        const info = classifyApiError(err);
        setItems([]);
        setTotal(0);
        if (info.kind === 'unauthorized') {
          setSessionLost(true);
          setError(tAuth('sessionExpired'));
        } else if (info.kind === 'network') {
          setError(tErrNet('offline'));
        } else if (info.kind === 'timeout') {
          setError(tErrNet('timeout'));
        } else if (info.kind === 'server') {
          setError(tErrHttp('500'));
        } else {
          setError(info.detail ?? tc('errorGeneric'));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [page, statusFilter, dateFrom, dateTo, query, tAuth, tErrHttp, tErrNet, tc]);

  const totalPages = useMemo(
    () => Math.max(1, Math.ceil(total / PAGE_SIZE)),
    [total],
  );

  return (
    <div className="container-page py-10">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
            {t('title')}
          </h1>
          <p className="mt-1 text-slate-600">{t('subtitle')}</p>
        </div>
        <Link href="/inspect/new" className="btn-primary">
          <Camera className="h-4 w-4" aria-hidden /> {t('newInspection')}
        </Link>
      </header>

      <div className="mb-5 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400"
              aria-hidden
            />
            <input
              type="search"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPage(1);
              }}
              placeholder={t('searchPlaceholder')}
              aria-label={tc('search')}
              className="block w-full rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>
          <div>
            <label className="sr-only" htmlFor="status-filter">
              {t('filterStatus')}
            </label>
            <select
              id="status-filter"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value as InspectionStatus | '');
                setPage(1);
              }}
              className="block w-full rounded-lg border border-slate-300 bg-white py-2 px-3 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            >
              <option value="">
                {t('filterStatus')} — {tc('all')}
              </option>
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="sr-only" htmlFor="date-from">
              {t('dateFrom')}
            </label>
            <input
              id="date-from"
              type="date"
              value={dateFrom}
              onChange={(e) => {
                setDateFrom(e.target.value);
                setPage(1);
              }}
              aria-label={t('dateFrom')}
              className="block w-full rounded-lg border border-slate-300 bg-white py-2 px-3 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>
          <div>
            <label className="sr-only" htmlFor="date-to">
              {t('dateTo')}
            </label>
            <input
              id="date-to"
              type="date"
              value={dateTo}
              onChange={(e) => {
                setDateTo(e.target.value);
                setPage(1);
              }}
              aria-label={t('dateTo')}
              className="block w-full rounded-lg border border-slate-300 bg-white py-2 px-3 text-sm shadow-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
            />
          </div>
        </div>
      </div>

      {error && !sessionLost && (
        <div
          role="status"
          className="mb-4 flex items-start gap-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-200"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-none" aria-hidden />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        // Skeleton mirrors the card grid layout below so the page doesn't
        // jump when results land. Six cards = ~one screenful at lg.
        <ul
          className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
          aria-hidden="true"
        >
          {Array.from({ length: 6 }).map((_, i) => (
            <li
              key={i}
              className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
            >
              <Skeleton className="aspect-video w-full" />
              <div className="space-y-2 p-4">
                <Skeleton className="h-3 w-24" />
                <Skeleton className="h-4 w-40" />
                <div className="flex justify-between border-t border-slate-100 pt-2">
                  <Skeleton className="h-3 w-16" />
                  <Skeleton className="h-3 w-20" />
                </div>
              </div>
            </li>
          ))}
        </ul>
      ) : sessionLost ? (
        // BUG-4 follow-up: replace the misleading "demo banner" with a
        // recovery CTA that actually fixes the state — re-login.
        <EmptyState
          icon={<LogIn className="h-8 w-8" />}
          title={tAuth('sessionExpired')}
          description={tAuth('tokenExpired')}
          action={
            <Link href="/login?next=/history" className="btn-primary">
              <LogIn className="h-4 w-4" aria-hidden /> {tAuth('loginCtaShort')}
            </Link>
          }
        />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<ImageOff className="h-8 w-8" />}
          title={t('empty')}
          description={t('emptyDesc')}
          action={
            <Link href="/inspect/new" className="btn-primary">
              {t('newInspection')}
            </Link>
          }
        />
      ) : (
        <>
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((it) => (
              <li key={it.inspection_id}>
                <Link
                  href={`/results/${it.inspection_id}`}
                  className="group block overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm transition-shadow hover:shadow-md focus-visible:shadow-md"
                >
                  <div className="relative aspect-video overflow-hidden bg-gradient-to-br from-slate-100 via-slate-50 to-slate-200">
                    {it.thumbnail_url ? (
                      // Remote backend/S3/R2 URL — let next/image generate
                      // an AVIF/WebP srcSet sized to the card grid. Parent
                      // already enforces aspect-video → no CLS.
                      <Image
                        src={it.thumbnail_url}
                        alt=""
                        fill
                        sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
                        loading="lazy"
                        className="object-cover"
                      />
                    ) : (
                      <div
                        className="flex h-full w-full flex-col items-center justify-center gap-1 text-slate-400"
                        aria-hidden
                      >
                        {/* Decorative SVG car silhouette so empty cards
                            still feel like "an inspection" rather than a
                            broken image. */}
                        <svg
                          viewBox="0 0 64 32"
                          className="h-12 w-12 fill-current opacity-70"
                          xmlns="http://www.w3.org/2000/svg"
                        >
                          <path d="M8 22c0-1.7 1.3-3 3-3s3 1.3 3 3-1.3 3-3 3-3-1.3-3-3zm45 0c0-1.7 1.3-3 3-3s3 1.3 3 3-1.3 3-3 3-3-1.3-3-3zM10 18l4-7c.7-1.2 2-2 3.4-2h22c1.2 0 2.3.6 3 1.6L46 18h8c2 0 3 1 3 3v1H7v-1c0-2 1-3 3-3zm9-7l-3 5h32l-3-5c-.4-.6-1.1-1-1.8-1H20.8c-.7 0-1.4.4-1.8 1z" />
                        </svg>
                        <Camera className="h-3.5 w-3.5" aria-hidden />
                      </div>
                    )}
                    <span className="absolute right-2 top-2">
                      <InspectionStatusBadge status={it.status} />
                    </span>
                  </div>
                  <div className="p-4">
                    <div className="font-mono text-[11px] text-slate-500">
                      {it.inspection_id.slice(0, 12)}…
                    </div>
                    <div className="mt-1 text-sm font-medium text-slate-900">
                      {formatDate(it.created_at)}
                    </div>
                    <div className="mt-3 flex items-baseline justify-between border-t border-slate-100 pt-2">
                      <span className="text-xs text-slate-500">
                        {t('damageCount', { count: it.damage_count })}
                      </span>
                      {typeof it.total_cost_midpoint_tl === 'number' && (
                        <span className="text-sm font-semibold text-slate-900 tabular-nums">
                          {it.total_cost_midpoint_tl.toLocaleString('tr-TR')} ₺
                        </span>
                      )}
                    </div>
                  </div>
                </Link>
              </li>
            ))}
          </ul>

          {totalPages > 1 && (
            <div className="mt-6 flex items-center justify-center gap-2">
              <button
                type="button"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="btn-secondary text-xs disabled:opacity-50"
              >
                {t('prev')}
              </button>
              <span className="px-3 text-xs text-slate-600">
                {t('page', { current: page, total: totalPages })}
              </span>
              <button
                type="button"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                className="btn-secondary text-xs disabled:opacity-50"
              >
                {t('next')}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return new Intl.DateTimeFormat('tr-TR', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(d);
  } catch {
    return iso;
  }
}
