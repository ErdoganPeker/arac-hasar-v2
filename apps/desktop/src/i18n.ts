/**
 * i18next bootstrap — TR default, EN fallback.
 * On desktop it reads `@tauri-apps/plugin-os` locale; on web it falls back to navigator.language.
 * Saved preference (settings.uiLanguage) wins over auto-detection — applied via `setLanguage()`.
 */
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import tr from './locales/tr.json';
import en from './locales/en.json';

export const SUPPORTED_LANGUAGES = ['tr', 'en'] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      tr: { translation: tr },
      en: { translation: en },
    },
    fallbackLng: 'tr',
    supportedLngs: SUPPORTED_LANGUAGES as unknown as string[],
    interpolation: { escapeValue: false },
    detection: {
      order: ['navigator', 'htmlTag'],
      caches: [],
    },
  });

export async function detectOsLanguage(): Promise<SupportedLanguage | null> {
  try {
    if (typeof window === 'undefined' || !('__TAURI_INTERNALS__' in window)) return null;
    const { locale } = await import('@tauri-apps/plugin-os');
    const code = (await locale())?.split(/[-_]/)[0]?.toLowerCase();
    if (code && (SUPPORTED_LANGUAGES as readonly string[]).includes(code)) {
      return code as SupportedLanguage;
    }
  } catch {
    // ignore
  }
  return null;
}

export async function setLanguage(lng: SupportedLanguage): Promise<void> {
  await i18n.changeLanguage(lng);
  if (typeof document !== 'undefined') {
    document.documentElement.lang = lng;
  }
}

export default i18n;
