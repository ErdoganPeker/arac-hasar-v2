/**
 * i18n/index.ts — i18next initialization for the mobile app.
 *
 * - Namespaces aligned with web: common, auth, dashboard, inspect, history, settings
 * - Persists user-selected locale in AsyncStorage
 * - Defaults to TR; English available as secondary.
 */
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import * as Localization from 'expo-localization';
import AsyncStorage from '@react-native-async-storage/async-storage';

import tr from '../locales/tr.json';
import en from '../locales/en.json';

const LOCALE_KEY = '@hasari/locale';
const NAMESPACES = ['common', 'auth', 'dashboard', 'inspect', 'history', 'settings'];

export const SUPPORTED_LOCALES = ['tr', 'en'] as const;
export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];

function detectDeviceLocale(): SupportedLocale {
  try {
    const locales = Localization.getLocales();
    const primary = locales?.[0]?.languageCode?.toLowerCase() ?? 'tr';
    return (SUPPORTED_LOCALES as readonly string[]).includes(primary)
      ? (primary as SupportedLocale)
      : 'tr';
  } catch {
    return 'tr';
  }
}

export async function getStoredLocale(): Promise<SupportedLocale | null> {
  try {
    const stored = await AsyncStorage.getItem(LOCALE_KEY);
    if (stored && (SUPPORTED_LOCALES as readonly string[]).includes(stored)) {
      return stored as SupportedLocale;
    }
  } catch {
    /* ignore */
  }
  return null;
}

export async function setStoredLocale(locale: SupportedLocale): Promise<void> {
  try {
    await AsyncStorage.setItem(LOCALE_KEY, locale);
  } catch {
    /* ignore */
  }
}

export async function changeLanguage(locale: SupportedLocale): Promise<void> {
  await i18n.changeLanguage(locale);
  await setStoredLocale(locale);
}

export async function initI18n(): Promise<void> {
  const stored = await getStoredLocale();
  const envDefault = process.env.EXPO_PUBLIC_DEFAULT_LOCALE as SupportedLocale | undefined;
  const initialLocale: SupportedLocale =
    stored ??
    (envDefault && (SUPPORTED_LOCALES as readonly string[]).includes(envDefault)
      ? envDefault
      : detectDeviceLocale());

  if (i18n.isInitialized) {
    await i18n.changeLanguage(initialLocale);
    return;
  }

  await i18n.use(initReactI18next).init({
    compatibilityJSON: 'v4',
    resources: {
      tr,
      en,
    },
    lng: initialLocale,
    fallbackLng: 'tr',
    ns: NAMESPACES,
    defaultNS: 'common',
    interpolation: { escapeValue: false },
    returnNull: false,
    react: { useSuspense: false },
  });
}

export default i18n;
