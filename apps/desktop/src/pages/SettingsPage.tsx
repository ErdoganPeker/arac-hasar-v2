/**
 * SettingsPage — profile, API config, language, theme, default upload mode,
 * shortcuts reference, and About.
 *
 * All writes go through the Tauri Store; the running `api` and `i18n` are updated
 * inline so changes apply immediately without a reload.
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { LogOut, Save } from 'lucide-react';
import { Spinner } from '@arac-hasar/ui';
import { loadSettings, saveSetting, type AppSettings } from '@/lib/settings';
import { api } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';
import { useTheme } from '@/contexts/ThemeContext';
import { setLanguage } from '@/i18n';
import { appInfo, type AppInfo } from '@/lib/commands';

export default function SettingsPage() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const { mode: themeMode, setMode: setThemeMode } = useTheme();

  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [saved, setSaved] = useState(false);
  const [info, setInfo] = useState<AppInfo | null>(null);

  useEffect(() => {
    loadSettings().then(setSettings);
    appInfo().then(setInfo);
  }, []);

  async function handleSave() {
    if (!settings) return;
    await Promise.all([
      saveSetting('apiUrl', settings.apiUrl),
      saveSetting('apiKey', settings.apiKey),
      saveSetting('uiLanguage', settings.uiLanguage),
      saveSetting('defaultUploadMode', settings.defaultUploadMode),
    ]);
    api.setBaseUrl(settings.apiUrl);
    api.setApiKey(settings.apiKey);
    await setLanguage(settings.uiLanguage);
    setSaved(true);
    setTimeout(() => setSaved(false), 1500);
  }

  if (!settings) return <Spinner size="lg" label={t('common.loading')} />;

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <h1 className="text-2xl font-bold text-slate-900 dark:text-white">{t('settings.title')}</h1>

      {/* Profile */}
      <Card title={t('settings.profile')}>
        {user ? (
          <div className="flex items-center justify-between">
            <div>
              <div className="font-semibold text-slate-900 dark:text-white">{user.full_name}</div>
              <div className="text-xs text-slate-500">{user.email}</div>
              <div className="mt-1 text-xs text-slate-500">{user.role}</div>
            </div>
            <button
              type="button"
              onClick={logout}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200"
            >
              <LogOut className="h-4 w-4" />
              {t('nav.logout')}
            </button>
          </div>
        ) : (
          <div className="text-sm text-slate-500">—</div>
        )}
      </Card>

      {/* API */}
      <Card title={t('settings.api')}>
        <Field label={t('settings.apiUrl')} hint={t('settings.apiUrlHint')}>
          <input
            type="url"
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
            value={settings.apiUrl}
            onChange={(e) => setSettings({ ...settings, apiUrl: e.target.value })}
          />
        </Field>
        <Field label="API key">
          <input
            type="password"
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
            value={settings.apiKey ?? ''}
            onChange={(e) => setSettings({ ...settings, apiKey: e.target.value || null })}
            placeholder="X-API-Key"
          />
        </Field>
      </Card>

      {/* Preferences */}
      <Card title={t('settings.language')}>
        <Field label={t('settings.languageDefault')}>
          <select
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-100"
            value={settings.uiLanguage}
            onChange={(e) =>
              setSettings({
                ...settings,
                uiLanguage: e.target.value as AppSettings['uiLanguage'],
              })
            }
          >
            <option value="tr">Türkçe</option>
            <option value="en">English</option>
          </select>
        </Field>
        <Field label={t('settings.theme')}>
          <div className="flex gap-2">
            {(['light', 'dark', 'system'] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setThemeMode(m)}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
                  themeMode === m
                    ? 'bg-brand-600 text-white'
                    : 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200'
                }`}
              >
                {t(
                  `settings.theme${m === 'light' ? 'Light' : m === 'dark' ? 'Dark' : 'System'}`,
                )}
              </button>
            ))}
          </div>
        </Field>
        <Field label={t('settings.defaultMode')}>
          <div className="flex gap-2">
            {(['sync', 'async'] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setSettings({ ...settings, defaultUploadMode: m })}
                className={`rounded-lg px-3 py-1.5 text-sm font-medium ${
                  settings.defaultUploadMode === m
                    ? 'bg-brand-600 text-white'
                    : 'border border-slate-300 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200'
                }`}
              >
                {t(`settings.mode${m === 'sync' ? 'Sync' : 'Async'}`)}
              </button>
            ))}
          </div>
        </Field>
      </Card>

      {/* Shortcuts */}
      <Card title={t('settings.shortcuts')}>
        <ShortcutRow label={t('settings.shortcutNewInspection')} keys="Ctrl+N" />
        <ShortcutRow label={t('settings.shortcutOpenFile')} keys="Ctrl+O" />
        <ShortcutRow label={t('settings.shortcutSettings')} keys="Ctrl+," />
        <ShortcutRow label={t('settings.shortcutFullscreen')} keys="F11" />
      </Card>

      {/* About */}
      <Card title={t('settings.about')}>
        <div className="grid gap-1 text-sm text-slate-600 dark:text-slate-300">
          <div>
            {t('settings.version')}: <span className="font-mono">{info?.version ?? '—'}</span>
          </div>
          <div>
            Platform: <span className="font-mono">{info?.platform ?? '—'}</span>
          </div>
        </div>
      </Card>

      <div className="flex justify-end">
        <button
          type="button"
          onClick={handleSave}
          className="inline-flex items-center gap-2 rounded-lg bg-brand-600 px-5 py-2 text-sm font-semibold text-white hover:bg-brand-700"
        >
          <Save className="h-4 w-4" />
          {saved ? t('common.saved') : t('common.save')}
        </button>
      </div>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-700 dark:bg-slate-800">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
        {title}
      </h2>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <div className="mb-1 text-sm font-medium text-slate-700 dark:text-slate-200">{label}</div>
      {children}
      {hint && <p className="mt-1 text-xs text-slate-500">{hint}</p>}
    </label>
  );
}

function ShortcutRow({ label, keys }: { label: string; keys: string }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-slate-700 dark:text-slate-200">{label}</span>
      <kbd className="rounded border border-slate-300 bg-slate-50 px-2 py-0.5 font-mono text-xs text-slate-700 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200">
        {keys}
      </kbd>
    </div>
  );
}
