import type { Metadata } from 'next';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { ArrowRight, Camera, Sparkles, MapPin, Clock } from 'lucide-react';

const VALUE_PROP_ICONS = [Camera, Sparkles, MapPin] as const;

export const metadata: Metadata = {
  title: 'Yapay Zeka ile Araç Hasar Tespiti ve Maliyet Tahmini',
  description:
    'Aracının fotoğrafını yükle, hangi parçada ne tür hasar olduğunu ve tahmini onarım maliyetini saniyeler içinde gör. Türkiye fiyat tabanı, parça bazlı rapor.',
  alternates: { canonical: '/' },
  openGraph: {
    title: 'Hasarİ — Yapay Zeka ile Araç Hasar Tespiti',
    description:
      'Fotoğraf yükle, parça bazlı hasar raporu ve TL bazlı onarım maliyet tahmini al. Eksper ücreti yok.',
    url: '/',
    type: 'website',
  },
};

export default function HomePage() {
  const t = useTranslations('home');
  const tAuth = useTranslations('auth');
  const tNav = useTranslations('nav');
  const tDmg = useTranslations('damageTypes');
  const tSev = useTranslations('severity');

  const valueProps = [
    {
      icon: VALUE_PROP_ICONS[0],
      title: t('valueProps.driverFriendlyTitle'),
      desc: t('valueProps.driverFriendlyDesc'),
    },
    {
      icon: VALUE_PROP_ICONS[1],
      title: t('valueProps.smallDamageTitle'),
      desc: t('valueProps.smallDamageDesc'),
    },
    {
      icon: VALUE_PROP_ICONS[2],
      title: t('valueProps.localPricingTitle'),
      desc: t('valueProps.localPricingDesc'),
    },
  ];

  const features = [
    { label: t('stats.partCentricLabel'), value: t('stats.partCentricValue') },
    { label: t('stats.avgTimeLabel'), value: t('stats.avgTimeValue') },
    { label: t('stats.damageTypesLabel'), value: t('stats.damageTypesValue') },
  ];

  return (
    <>
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 -z-10 bg-gradient-to-br from-brand-50 via-white to-white" />
        <div className="container-page py-16 sm:py-24">
          <div className="grid items-center gap-12 lg:grid-cols-2">
            <div>
              <span className="inline-flex items-center gap-2 rounded-full bg-brand-100 px-3 py-1 text-xs font-semibold text-brand-800">
                <Sparkles className="h-3.5 w-3.5" aria-hidden /> {t('hero.badge')}
              </span>
              <h1 className="mt-4 text-4xl font-bold tracking-tight text-slate-900 sm:text-5xl lg:text-6xl">
                {t('hero.titlePart1')}{' '}
                <span className="text-brand-700">{t('hero.titleHighlight')}</span>{' '}
                {t('hero.titlePart2')}
              </h1>
              <p className="mt-5 max-w-xl text-lg text-slate-600">
                {t('hero.description')}
              </p>
              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <Link href="/login" className="btn-primary text-base">
                  {tAuth('loginCtaShort')}
                  <ArrowRight className="h-4 w-4" aria-hidden />
                </Link>
                <Link href="/register" className="btn-secondary text-base">
                  {tAuth('registerCta')}
                </Link>
                {/* BUG-1: anonymous /inspect now 401s (middleware gates the
                    whole route). Send "Try the demo" through /register so
                    the user lands inside the gate instead of bouncing off
                    it with a login redirect. */}
                <Link href="/register" className="btn-ghost text-base">
                  {tNav('tryDemo')}
                </Link>
              </div>

              <dl className="mt-10 grid grid-cols-3 gap-4 border-t border-slate-200 pt-6">
                {features.map((f) => (
                  <div key={f.label}>
                    <dt className="text-xs uppercase tracking-wider text-slate-500">
                      {f.label}
                    </dt>
                    <dd className="mt-1 text-xl font-bold text-slate-900 tabular-nums">
                      {f.value}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>

            {/* Visual placeholder — parça merkezli özet */}
            <div className="relative">
              <div className="rounded-3xl bg-white p-6 shadow-xl ring-1 ring-slate-200">
                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                  <div className="flex items-center gap-2">
                    <span
                      className="h-2.5 w-2.5 rounded-full bg-red-500"
                      aria-hidden
                    />
                    <h3 className="font-semibold text-slate-900">
                      {t('previewCard.partLabel')}
                    </h3>
                  </div>
                  <span className="rounded-full bg-slate-900 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
                    {t('previewCard.damageCount', { count: 2 })}
                  </span>
                </div>
                <div className="mt-3 space-y-2">
                  <Badge color="orange" label={tDmg('scratch')} sev={tSev('orta')} />
                  <Badge color="amber" label={tDmg('dent')} sev={tSev('hafif')} />
                </div>
                <div className="mt-4 border-t border-slate-100 pt-3 text-right">
                  <div className="text-xs text-slate-500">
                    {t('previewCard.estimatedRepair')}
                  </div>
                  <div className="text-2xl font-bold text-slate-900 tabular-nums">
                    3.500 – 5.200 ₺
                  </div>
                </div>
              </div>

              <div className="mt-4 rounded-2xl bg-emerald-50 p-4 ring-1 ring-inset ring-emerald-200">
                <div className="flex items-center gap-2 text-sm text-emerald-900">
                  <Clock className="h-4 w-4" aria-hidden />
                  <strong>{t('previewCard.durationEstimate')}</strong>
                  <span className="text-emerald-700">
                    {t('previewCard.repairRecommendation')}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Value props */}
      <section className="border-t border-slate-200 bg-white">
        <div className="container-page py-16">
          <h2 className="text-3xl font-bold tracking-tight text-slate-900">
            {t('valueProps.sectionTitle')}
          </h2>
          <p className="mt-2 max-w-2xl text-slate-600">
            {t('valueProps.sectionSubtitle')}
          </p>
          <div className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {valueProps.map((vp) => (
              <div
                key={vp.title}
                className="rounded-2xl border border-slate-200 bg-white p-6 transition-shadow hover:shadow-md"
              >
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-100 text-brand-700">
                  <vp.icon className="h-5 w-5" aria-hidden />
                </div>
                <h3 className="mt-4 font-semibold text-slate-900">{vp.title}</h3>
                <p className="mt-2 text-sm text-slate-600">{vp.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="bg-brand-700">
        <div className="container-page py-14 text-center">
          <h2 className="text-3xl font-bold tracking-tight text-white">
            {t('cta.title')}
          </h2>
          <p className="mt-3 text-brand-100">{t('cta.subtitle')}</p>
          <Link
            href="/register"
            className="mt-6 inline-flex items-center gap-2 rounded-xl bg-white px-6 py-3 text-base font-semibold text-brand-700 shadow-sm transition-colors hover:bg-brand-50"
          >
            {t('cta.button')}
            <ArrowRight className="h-4 w-4" aria-hidden />
          </Link>
        </div>
      </section>
    </>
  );
}

function Badge({
  color,
  label,
  sev,
}: {
  color: 'orange' | 'amber' | 'red';
  label: string;
  sev: string;
}) {
  const map = {
    orange: 'bg-orange-50 text-orange-900 ring-orange-200',
    amber: 'bg-amber-50 text-amber-900 ring-amber-200',
    red: 'bg-red-50 text-red-900 ring-red-200',
  } as const;
  return (
    <div
      className={`flex items-center justify-between rounded-lg px-3 py-2 text-sm ring-1 ring-inset ${map[color]}`}
    >
      <span className="font-medium">{label}</span>
      <span className="text-xs font-semibold uppercase tracking-wide">
        {sev}
      </span>
    </div>
  );
}
