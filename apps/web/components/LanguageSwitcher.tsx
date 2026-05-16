'use client';

import { useLocale, useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { Languages } from 'lucide-react';

const LOCALE_COOKIE = 'NEXT_LOCALE';

export function LanguageSwitcher({ compact = false }: { compact?: boolean }) {
  const locale = useLocale();
  const router = useRouter();
  const tCommon = useTranslations('common');

  function setLocale(next: 'tr' | 'en') {
    if (next === locale) return;
    document.cookie = `${LOCALE_COOKIE}=${next}; path=/; max-age=${60 * 60 * 24 * 365}; samesite=lax`;
    router.refresh();
  }

  return (
    <div
      className="inline-flex items-center gap-1 rounded-lg bg-slate-100 p-1"
      role="group"
      aria-label={tCommon('language')}
    >
      {!compact && (
        <Languages className="ml-1 h-3.5 w-3.5 text-slate-500" aria-hidden />
      )}
      {(['tr', 'en'] as const).map((l) => (
        <button
          key={l}
          type="button"
          onClick={() => setLocale(l)}
          aria-pressed={locale === l}
          className={`rounded-md px-2 py-0.5 text-xs font-semibold uppercase transition-colors ${
            locale === l
              ? 'bg-white text-slate-900 shadow-sm'
              : 'text-slate-500 hover:text-slate-900'
          }`}
        >
          {l}
        </button>
      ))}
    </div>
  );
}
