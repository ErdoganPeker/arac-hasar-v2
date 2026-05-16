import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { History as HistoryIcon } from 'lucide-react';
import { EmptyState, Spinner } from '@arac-hasar/ui';
import type { InspectionListItem } from '@arac-hasar/types';
import { api } from '@/lib/api';

export default function HistoryPage() {
  const [items, setItems] = useState<InspectionListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listInspections()
      .then((res) => setItems(res.items))
      .catch((e) => setError(e instanceof Error ? e.message : 'Hata'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spinner size="lg" label="Geçmiş yükleniyor..." />;
  if (error) {
    return (
      <EmptyState
        icon={<HistoryIcon className="h-12 w-12" />}
        title="Geçmiş yüklenemedi"
        description={error}
      />
    );
  }
  if (items.length === 0) {
    return (
      <EmptyState
        icon={<HistoryIcon className="h-12 w-12" />}
        title="Henüz inceleme yok"
        description="Ana sayfadan yeni bir inceleme başlat."
      />
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <h1 className="text-2xl font-bold text-slate-900">Geçmiş incelemeler</h1>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((it) => (
          <Link
            key={it.inspection_id}
            to={`/results/${it.inspection_id}`}
            className="group rounded-xl border border-slate-200 bg-white p-4 transition-shadow hover:shadow-md"
          >
            <div className="font-mono text-[10px] uppercase tracking-wider text-slate-400">
              {it.inspection_id.slice(0, 8)}
            </div>
            <div className="mt-2 text-sm text-slate-700">
              {new Date(it.created_at).toLocaleString('tr-TR')}
            </div>
            <div className="mt-3 flex items-center justify-between text-sm">
              <span className="text-slate-600">{it.damage_count} hasar</span>
              {it.total_cost_midpoint_tl !== undefined && (
                <span className="font-semibold tabular-nums">
                  {it.total_cost_midpoint_tl.toLocaleString('tr-TR')} ₺
                </span>
              )}
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
