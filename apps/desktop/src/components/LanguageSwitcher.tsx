/**
 * LanguageSwitcher — TR ↔ EN dropdown that persists choice to settings store.
 */
import { useTranslation } from 'react-i18next';
import { Globe } from 'lucide-react';
import { setLanguage, SUPPORTED_LANGUAGES, type SupportedLanguage } from '@/i18n';
import { saveSetting } from '@/lib/settings';

export function LanguageSwitcher({ compact = false }: { compact?: boolean }) {
  const { i18n } = useTranslation();
  const current = (i18n.resolvedLanguage ?? 'tr').slice(0, 2) as SupportedLanguage;

  async function change(lng: SupportedLanguage) {
    await setLanguage(lng);
    await saveSetting('uiLanguage', lng);
  }

  if (compact) {
    return (
      <button
        type="button"
        onClick={() => change(current === 'tr' ? 'en' : 'tr')}
        title="Language"
        className="inline-flex h-8 items-center gap-1 rounded-md px-2 text-xs font-semibold uppercase text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-700"
      >
        <Globe className="h-3.5 w-3.5" />
        {current}
      </button>
    );
  }

  return (
    <select
      value={current}
      onChange={(e) => change(e.target.value as SupportedLanguage)}
      className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
    >
      {SUPPORTED_LANGUAGES.map((l) => (
        <option key={l} value={l}>
          {l.toUpperCase()}
        </option>
      ))}
    </select>
  );
}

export default LanguageSwitcher;
