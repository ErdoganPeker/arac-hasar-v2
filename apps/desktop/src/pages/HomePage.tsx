import { Link } from 'react-router-dom';
import { Upload, FolderOpen, History, Activity } from 'lucide-react';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { Spinner } from '@arac-hasar/ui';

export default function HomePage() {
  const [health, setHealth] = useState<'loading' | 'ok' | 'down'>('loading');
  const [mlLoaded, setMlLoaded] = useState(false);

  useEffect(() => {
    api
      .health()
      .then((h) => {
        setHealth(h.status === 'ok' ? 'ok' : 'down');
        setMlLoaded(h.ml_loaded);
      })
      .catch(() => setHealth('down'));
  }, []);

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Hasarİ Desktop</h1>
        <p className="mt-1 text-slate-600">
          Araç hasar tespit ve maliyet tahmini — parça-merkezli görünüm.
        </p>
      </div>

      <StatusCard health={health} mlLoaded={mlLoaded} />

      <div className="grid gap-4 sm:grid-cols-2">
        <ActionCard
          to="/inspect"
          icon={Upload}
          title="Tek inceleme"
          description="1-10 görüntü yükle, anında raporla."
        />
        <ActionCard
          to="/batch"
          icon={FolderOpen}
          title="Toplu işleme"
          description="Tüm bir klasörü tara, CSV/PDF olarak dışa aktar."
        />
        <ActionCard
          to="/history"
          icon={History}
          title="Geçmiş incelemeler"
          description="Önceki raporları aç, karşılaştır."
        />
        <ActionCard
          to="/settings"
          icon={Activity}
          title="Ayarlar"
          description="API adresi, anahtar, model tercihi."
        />
      </div>
    </div>
  );
}

function StatusCard({ health, mlLoaded }: { health: 'loading' | 'ok' | 'down'; mlLoaded: boolean }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
        Sistem durumu
      </div>
      <div className="mt-2 flex items-center gap-4 text-sm">
        {health === 'loading' ? (
          <Spinner size="sm" label="Backend kontrol ediliyor..." />
        ) : (
          <>
            <span className="inline-flex items-center gap-1.5">
              <span
                className={`h-2 w-2 rounded-full ${health === 'ok' ? 'bg-emerald-500' : 'bg-red-500'}`}
              />
              Backend: {health === 'ok' ? 'aktif' : 'kapalı'}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span
                className={`h-2 w-2 rounded-full ${mlLoaded ? 'bg-emerald-500' : 'bg-amber-500'}`}
              />
              ML modeli: {mlLoaded ? 'yüklendi' : 'yüklenmedi'}
            </span>
          </>
        )}
      </div>
    </div>
  );
}

interface ActionCardProps {
  to: string;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
}

function ActionCard({ to, icon: Icon, title, description }: ActionCardProps) {
  return (
    <Link
      to={to}
      className="group rounded-xl border border-slate-200 bg-white p-5 transition-shadow hover:shadow-md"
    >
      <div className="mb-3 inline-flex h-10 w-10 items-center justify-center rounded-lg bg-brand-100 text-brand-700 group-hover:bg-brand-200">
        <Icon className="h-5 w-5" />
      </div>
      <h3 className="font-semibold text-slate-900">{title}</h3>
      <p className="mt-1 text-sm text-slate-600">{description}</p>
    </Link>
  );
}
