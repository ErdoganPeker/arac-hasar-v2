'use client';

import { useTranslations } from 'next-intl';

export function Footer() {
  const t = useTranslations('footer');
  const tCommon = useTranslations('common');
  const year = new Date().getFullYear();
  return (
    <footer className="border-t border-slate-200 bg-white">
      <div className="container-page flex flex-col items-start justify-between gap-3 py-8 text-sm text-slate-500 sm:flex-row sm:items-center">
        <div>
          &copy; {year} {tCommon('appName')} — {t('rights')}.
        </div>
        <div className="flex items-center gap-4">
          <span>v0.1 {tCommon('appVersionLabel')}</span>
          <span aria-hidden>•</span>
          <span>{t('madeWithLove')}</span>
        </div>
      </div>
    </footer>
  );
}
