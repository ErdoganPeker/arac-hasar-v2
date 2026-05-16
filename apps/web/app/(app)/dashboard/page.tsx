'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import {
  ClipboardList,
  Hourglass,
  CheckCircle2,
  Coins,
  ArrowRight,
  Camera,
} from 'lucide-react';
import { Spinner } from '@arac-hasar/ui';
import type { InspectionListItem } from '@arac-hasar/types';
import { listInspections } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';
import { KPICard } from '@/components/KPICard';
import { InspectionStatusBadge } from '@/components/InspectionStatusBadge';

export default function DashboardPage() {
  const t = useTranslations('dashboard');
  const th = useTranslations('history');
  const { user } = useAuth();
  const [items, setItems] = useState<InspectionListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await listInspections({ pageSize: 20 });
        if (cancelled) return;
        setItems(data.items ?? []);
        setTotal(data.total ?? data.items?.length ?? 0);
      } catch {
        if (cancelled) return;
        setItems([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const kpis = useMemo(() => {
    const pending = items.filter(
      (i) => i.status === 'queued' || i.status === 'processing',
    ).length;
    const completed = items.filter((i) => i.status === 'completed').length;
    const costs = items
      .map((i) => i.total_cost_midpoint_tl)
      .filter((v): v is number => typeof v === 'number');
    const avg = costs.length
      ? Math.round(costs.reduce((a, b) => a + b, 0) / costs.length)
      : 0;
    return { total, pending, completed, avg };
  }, [items, total]);

  return (
    <div className="container-page py-10">
      <header className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
          {t('title')}
        </h1>
        <p className="mt-1 text-slate-600">
          {user?.full_name ? `${user.full_name} — ` : ''}
          {t('subtitle')}
        </p>
      </header>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KPICard
          label={t('kpi.total')}
          value={kpis.total}
          icon={ClipboardList}
          tone="primary"
        />
        <KPICard
          label={t('kpi.pending')}
          value={kpis.pending}
          icon={Hourglass}
          tone="warning"
        />
        <KPICard
          label={t('kpi.completed')}
          value={kpis.completed}
          icon={CheckCircle2}
          tone="success"
        />
        <KPICard
          label={t('kpi.avgCost')}
          value={kpis.avg ? `₺${kpis.avg.toLocaleString('tr-TR')}` : '—'}
          icon={Coins}
        />
      </section>

      <section className="mt-10">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900">{t('recent')}</h2>
          <Link
            href="/history"
            className="inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:underline"
          >
            {t('viewAll')} <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          </Link>
        </div>

        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          {loading ? (
            <div className="flex justify-center py-16">
              <Spinner size="lg" />
            </div>
          ) : items.length === 0 ? (
            <div className="flex flex-col items-center gap-3 py-12 text-center">
              <p className="text-sm text-slate-600">{t('noRecent')}</p>
              <Link href="/inspect/new" className="btn-primary">
                <Camera className="h-4 w-4" aria-hidden />
                {t('startFirst')}
              </Link>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="px-4 py-3">ID</th>
                    <th className="px-4 py-3">{th('filterStatus')}</th>
                    <th className="px-4 py-3">Tarih</th>
                    <th className="px-4 py-3">Hasar</th>
                    <th className="px-4 py-3 text-right">Maliyet</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {items.slice(0, 6).map((it) => (
                    <tr key={it.inspection_id} className="hover:bg-slate-50">
                      <td className="px-4 py-3">
                        <Link
                          href={`/results/${it.inspection_id}`}
                          className="font-mono text-xs text-brand-700 hover:underline"
                        >
                          {it.inspection_id.slice(0, 12)}…
                        </Link>
                      </td>
                      <td className="px-4 py-3">
                        <InspectionStatusBadge status={it.status} />
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        {new Date(it.created_at).toLocaleString('tr-TR')}
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        {it.damage_count}
                      </td>
                      <td className="px-4 py-3 text-right font-semibold text-slate-900 tabular-nums">
                        {typeof it.total_cost_midpoint_tl === 'number'
                          ? `₺${it.total_cost_midpoint_tl.toLocaleString('tr-TR')}`
                          : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
