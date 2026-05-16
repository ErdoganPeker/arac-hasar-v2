/**
 * DashboardPage — landing page after auth.
 *
 * Shows:
 *  - greeting with the authenticated user's name
 *  - today / this-week / this-month inspection counts
 *  - total damages, average cost
 *  - recent inspections list (links to detail)
 *  - system status (backend health + ML loaded)
 *  - quick action cards to /inspect and /batch
 *
 * All stats are derived client-side from the last 1-2 pages of inspections so we
 * don't depend on a dedicated `/stats` endpoint.
 */
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Activity, Calendar, FolderOpen, Upload, Wrench } from 'lucide-react';
import type { HealthResponse, InspectionListItem } from '@arac-hasar/types';
import { api } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';

function startOfDay(d: Date): Date {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}

export default function DashboardPage() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [items, setItems] = useState<InspectionListItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [h, list] = await Promise.allSettled([api.health(), api.listInspections(1, 50)]);
        if (cancelled) return;
        if (h.status === 'fulfilled') setHealth(h.value);
        if (list.status === 'fulfilled') setItems(list.value.items);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const stats = useMemo(() => {
    const now = new Date();
    const todayStart = startOfDay(now).getTime();
    const weekStart = todayStart - 6 * 86400_000;
    const monthStart = new Date(now.getFullYear(), now.getMonth(), 1).getTime();
    let today = 0;
    let week = 0;
    let month = 0;
    let totalDamages = 0;
    let costSum = 0;
    let costCount = 0;
    for (const it of items) {
      const t = new Date(it.created_at).getTime();
      if (t >= todayStart) today++;
      if (t >= weekStart) week++;
      if (t >= monthStart) month++;
      totalDamages += it.damage_count ?? 0;
      if (it.total_cost_midpoint_tl !== undefined && it.total_cost_midpoint_tl !== null) {
        costSum += it.total_cost_midpoint_tl;
        costCount++;
      }
    }
    return {
      today,
      week,
      month,
      total: items.length,
      totalDamages,
      avgCost: costCount > 0 ? Math.round(costSum / costCount) : 0,
    };
  }, [items]);

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
          {user ? t('dashboard.welcome', { name: user.full_name }) : t('dashboard.title')}
        </h1>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{t('app.tagline')}</p>
      </header>

      {/* Stats grid */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile
          label={t('dashboard.today')}
          value={stats.today}
          icon={Calendar}
          accent="text-brand-600"
        />
        <StatTile label={t('dashboard.week')} value={stats.week} icon={Calendar} />
        <StatTile label={t('dashboard.month')} value={stats.month} icon={Calendar} />
        <StatTile
          label={t('dashboard.totalInspections')}
          value={stats.total}
          icon={Activity}
          accent="text-emerald-600"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        {/* Recent */}
        <section className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-100">
              {t('dashboard.recent')}
            </h2>
            <Link
              to="/inspections"
              className="text-xs font-medium text-brand-600 hover:underline"
            >
              {t('common.all')} →
            </Link>
          </div>
          {loading ? (
            <div className="py-8 text-center text-sm text-slate-500">{t('common.loading')}</div>
          ) : items.length === 0 ? (
            <div className="py-8 text-center text-sm text-slate-500">
              {t('dashboard.noRecent')}
            </div>
          ) : (
            <ul className="divide-y divide-slate-200 dark:divide-slate-700">
              {items.slice(0, 6).map((it) => (
                <li key={it.inspection_id}>
                  <Link
                    to={`/inspection/${it.inspection_id}`}
                    className="flex items-center justify-between gap-2 py-2.5 hover:bg-slate-50 dark:hover:bg-slate-700/40"
                  >
                    <div className="min-w-0">
                      <div className="truncate font-mono text-xs text-slate-500">
                        {it.inspection_id.slice(0, 12)}…
                      </div>
                      <div className="text-sm text-slate-800 dark:text-slate-100">
                        {new Date(it.created_at).toLocaleString()}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-xs text-slate-500">
                        {it.damage_count} {t('inspections.damages')}
                      </div>
                      {it.total_cost_midpoint_tl !== undefined && (
                        <div className="font-semibold tabular-nums text-slate-700 dark:text-slate-200">
                          {it.total_cost_midpoint_tl.toLocaleString('tr-TR')} ₺
                        </div>
                      )}
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Sidebar widgets */}
        <div className="space-y-4">
          <section className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
            <h2 className="mb-3 text-sm font-semibold text-slate-800 dark:text-slate-100">
              {t('dashboard.systemStatus')}
            </h2>
            <div className="space-y-2 text-sm">
              <StatusLine
                ok={health?.status === 'ok'}
                onLabel={t('dashboard.backendOnline')}
                offLabel={t('dashboard.backendOffline')}
              />
              <StatusLine
                ok={!!health?.ml_loaded}
                onLabel={t('dashboard.mlReady')}
                offLabel={t('dashboard.mlNotReady')}
              />
            </div>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
            <h2 className="mb-3 text-sm font-semibold text-slate-800 dark:text-slate-100">
              {t('dashboard.quickActions')}
            </h2>
            <div className="space-y-2">
              <ActionRow to="/inspect" icon={Upload} label={t('dashboard.newInspection')} />
              <ActionRow to="/batch" icon={FolderOpen} label={t('dashboard.batchUpload')} />
            </div>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
            <h2 className="mb-3 text-sm font-semibold text-slate-800 dark:text-slate-100">
              {t('dashboard.totalDamages')}
            </h2>
            <div className="flex items-center gap-2 text-3xl font-bold text-slate-900 dark:text-white">
              <Wrench className="h-7 w-7 text-amber-500" />
              {stats.totalDamages}
            </div>
            <div className="mt-2 text-xs text-slate-500">
              {t('dashboard.avgCost')}:{' '}
              <span className="font-semibold tabular-nums text-slate-700 dark:text-slate-200">
                {stats.avgCost.toLocaleString('tr-TR')} ₺
              </span>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function StatTile({
  label,
  value,
  icon: Icon,
  accent,
}: {
  label: string;
  value: number;
  icon: React.ComponentType<{ className?: string }>;
  accent?: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
      <div className="flex items-start justify-between">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
            {label}
          </div>
          <div className="mt-1 text-2xl font-bold tabular-nums text-slate-900 dark:text-white">
            {value}
          </div>
        </div>
        <Icon className={`h-5 w-5 ${accent ?? 'text-slate-400'}`} />
      </div>
    </div>
  );
}

function StatusLine({ ok, onLabel, offLabel }: { ok: boolean; onLabel: string; offLabel: string }) {
  return (
    <div className="flex items-center gap-2">
      <span className={`h-2 w-2 rounded-full ${ok ? 'bg-emerald-500' : 'bg-red-500'}`} />
      <span className="text-slate-700 dark:text-slate-200">{ok ? onLabel : offLabel}</span>
    </div>
  );
}

function ActionRow({
  to,
  icon: Icon,
  label,
}: {
  to: string;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
}) {
  return (
    <Link
      to={to}
      className="flex items-center gap-3 rounded-lg border border-slate-200 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-700/40"
    >
      <Icon className="h-4 w-4 text-brand-600" />
      {label}
    </Link>
  );
}
