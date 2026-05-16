import { getRequestConfig } from 'next-intl/server';
import { cookies, headers } from 'next/headers';

export const LOCALES = ['tr', 'en'] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = 'tr';
export const LOCALE_COOKIE = 'NEXT_LOCALE';

function isLocale(value: string | undefined | null): value is Locale {
  return !!value && (LOCALES as readonly string[]).includes(value);
}

async function resolveLocale(): Promise<Locale> {
  const cookieStore = await cookies();
  const cookieLocale = cookieStore.get(LOCALE_COOKIE)?.value;
  if (isLocale(cookieLocale)) return cookieLocale;

  const hdrs = await headers();
  const accept = hdrs.get('accept-language') ?? '';
  const preferred = accept
    .split(',')
    .map((part) => {
      const first = part.split(';')[0] ?? '';
      const lang = first.trim().toLowerCase().split('-')[0] ?? '';
      return lang;
    })
    .find((l): l is Locale => isLocale(l));
  return preferred ?? DEFAULT_LOCALE;
}

export default getRequestConfig(async () => {
  const locale = await resolveLocale();
  return {
    locale,
    messages: (await import(`./messages/${locale}.json`)).default,
  };
});
