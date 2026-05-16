'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import axios from 'axios';
import { Copy, Key, Plus, Trash2, User as UserIcon } from 'lucide-react';
import { Spinner } from '@arac-hasar/ui';
import { useAuth } from '@/lib/auth-context';
import { useToast } from '@/components/ToastProvider';
import { FormField } from '@/components/FormField';
import { LanguageSwitcher } from '@/components/LanguageSwitcher';
import {
  apiKeys as apiKeysApi,
  auth,
  type ApiKey,
  type ApiKeyCreateResponse,
} from '@/lib/api';

type Tab = 'profile' | 'password' | 'apiKeys' | 'preferences';

export default function SettingsPage() {
  const t = useTranslations('settings');
  const tc = useTranslations('common');
  const [tab, setTab] = useState<Tab>('profile');

  return (
    <div className="container-page py-10">
      <header className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
          {t('title')}
        </h1>
        <p className="mt-1 text-slate-600">{t('subtitle')}</p>
      </header>

      <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
        <nav
          aria-label="Settings tabs"
          className="rounded-2xl border border-slate-200 bg-white p-2 shadow-sm lg:sticky lg:top-20 lg:self-start"
        >
          {(
            [
              ['profile', t('tabs.profile'), UserIcon],
              ['password', t('tabs.password'), Key],
              ['apiKeys', t('tabs.apiKeys'), Key],
              ['preferences', t('tabs.preferences'), UserIcon],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key as Tab)}
              className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-medium transition-colors ${
                tab === key
                  ? 'bg-brand-50 text-brand-800'
                  : 'text-slate-700 hover:bg-slate-100'
              }`}
            >
              {label}
            </button>
          ))}
        </nav>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          {tab === 'profile' && <ProfileTab />}
          {tab === 'password' && <PasswordTab />}
          {tab === 'apiKeys' && <ApiKeysTab />}
          {tab === 'preferences' && <PreferencesTab />}
        </div>
      </div>
    </div>
  );
}

function ProfileTab() {
  const t = useTranslations('settings');
  const tc = useTranslations('common');
  const { user, refreshUser } = useAuth();
  const toast = useToast();
  const [fullName, setFullName] = useState(user?.full_name ?? '');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setFullName(user?.full_name ?? '');
  }, [user?.full_name]);

  async function save() {
    if (!fullName.trim()) return;
    setSaving(true);
    try {
      await auth.updateProfile({ full_name: fullName.trim() });
      await refreshUser();
      toast.success(t('profile.saved'));
    } catch {
      toast.error(tc('errorGeneric'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <h2 className="text-lg font-semibold text-slate-900">
        {t('profile.title')}
      </h2>
      <div className="mt-4 space-y-4">
        <FormField
          label={t('profile.fullName')}
          value={fullName}
          onChange={(e) => setFullName(e.target.value)}
        />
        <FormField
          label={t('profile.email')}
          value={user?.email ?? ''}
          disabled
        />
        <FormField
          label={t('profile.role')}
          value={user?.role ?? 'user'}
          disabled
        />
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="btn-primary"
        >
          {saving ? <Spinner size="sm" /> : t('profile.save')}
        </button>
      </div>
    </div>
  );
}

function PasswordTab() {
  const t = useTranslations('settings');
  const tc = useTranslations('common');
  const ta = useTranslations('auth');
  const toast = useToast();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    setError(null);
    if (next.length < 8) {
      setError(ta('passwordTooShort'));
      return;
    }
    if (next !== confirm) {
      setError(ta('passwordMismatch'));
      return;
    }
    setSaving(true);
    try {
      await auth.changePassword(current, next);
      toast.success(t('password.saved'));
      setCurrent('');
      setNext('');
      setConfirm('');
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 401) {
        setError(ta('invalidCredentials'));
      } else {
        setError(tc('errorGeneric'));
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <h2 className="text-lg font-semibold text-slate-900">
        {t('password.title')}
      </h2>
      <div className="mt-4 space-y-4">
        <FormField
          label={t('password.current')}
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
        />
        <FormField
          label={t('password.new')}
          type="password"
          autoComplete="new-password"
          value={next}
          onChange={(e) => setNext(e.target.value)}
        />
        <FormField
          label={t('password.confirm')}
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
        />
        {error && (
          <div
            role="alert"
            className="rounded-lg bg-red-50 p-3 text-sm text-red-800 ring-1 ring-red-200"
          >
            {error}
          </div>
        )}
        <button
          type="button"
          onClick={save}
          disabled={saving || !current || !next}
          className="btn-primary"
        >
          {saving ? <Spinner size="sm" /> : t('password.save')}
        </button>
      </div>
    </div>
  );
}

function ApiKeysTab() {
  const t = useTranslations('settings');
  const tc = useTranslations('common');
  const toast = useToast();
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState('');
  const [creating, setCreating] = useState(false);
  const [revealed, setRevealed] = useState<ApiKeyCreateResponse | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await apiKeysApi.list();
        if (!cancelled) setKeys(list);
      } catch {
        if (!cancelled) setKeys([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function generate() {
    if (!name.trim()) return;
    setCreating(true);
    try {
      const r = await apiKeysApi.create(name.trim());
      setRevealed(r);
      setKeys((prev) => [r.key, ...prev]);
      setName('');
    } catch {
      toast.error(tc('errorGeneric'));
    } finally {
      setCreating(false);
    }
  }

  async function revoke(id: string) {
    if (!window.confirm(t('apiKeys.confirmRevoke'))) return;
    try {
      await apiKeysApi.revoke(id);
      setKeys((prev) => prev.filter((k) => k.id !== id));
    } catch {
      toast.error(tc('errorGeneric'));
    }
  }

  function copy(value: string) {
    navigator.clipboard?.writeText(value);
    toast.success(t('apiKeys.copied'));
  }

  return (
    <div>
      <h2 className="text-lg font-semibold text-slate-900">
        {t('apiKeys.title')}
      </h2>
      <p className="mt-1 text-sm text-slate-600">{t('apiKeys.subtitle')}</p>

      <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex-1">
          <FormField
            label={t('apiKeys.name')}
            placeholder={t('apiKeys.namePlaceholder')}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <button
          type="button"
          onClick={generate}
          disabled={creating || !name.trim()}
          className="btn-primary"
        >
          {creating ? (
            <Spinner size="sm" />
          ) : (
            <>
              <Plus className="h-4 w-4" aria-hidden />
              {t('apiKeys.generate')}
            </>
          )}
        </button>
      </div>

      {revealed && (
        <div className="mt-5 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
          <div className="text-sm font-semibold text-emerald-900">
            {t('apiKeys.newKeyTitle')}
          </div>
          <p className="mt-1 text-xs text-emerald-800">
            {t('apiKeys.newKeyDesc')}
          </p>
          <div className="mt-3 flex items-center gap-2 rounded-lg bg-white p-2 ring-1 ring-emerald-200">
            <code className="flex-1 overflow-x-auto break-all font-mono text-xs text-slate-900">
              {revealed.secret}
            </code>
            <button
              type="button"
              onClick={() => copy(revealed.secret)}
              className="btn-ghost"
              aria-label={t('apiKeys.copy')}
            >
              <Copy className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      <div className="mt-6">
        {loading ? (
          <div className="flex justify-center py-10">
            <Spinner size="lg" />
          </div>
        ) : keys.length === 0 ? (
          <p className="rounded-xl bg-slate-50 p-6 text-center text-sm text-slate-500">
            {t('apiKeys.empty')}
          </p>
        ) : (
          <ul className="divide-y divide-slate-100 rounded-xl border border-slate-200">
            {keys.map((k) => (
              <li
                key={k.id}
                className="flex items-center justify-between gap-3 px-4 py-3"
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-slate-900">
                    {k.name}
                  </div>
                  <div className="mt-0.5 font-mono text-xs text-slate-500">
                    {k.prefix}••••
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    {t('apiKeys.created')}:{' '}
                    {new Date(k.created_at).toLocaleDateString('tr-TR')} —{' '}
                    {t('apiKeys.lastUsed')}:{' '}
                    {k.last_used_at
                      ? new Date(k.last_used_at).toLocaleDateString('tr-TR')
                      : t('apiKeys.never')}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => revoke(k.id)}
                  className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50"
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden />
                  {t('apiKeys.revoke')}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function PreferencesTab() {
  const t = useTranslations('settings');
  return (
    <div>
      <h2 className="text-lg font-semibold text-slate-900">
        {t('preferences.title')}
      </h2>
      <div className="mt-4 space-y-3">
        <div>
          <div className="mb-1 text-sm font-medium text-slate-800">
            {t('preferences.language')}
          </div>
          <LanguageSwitcher />
        </div>
      </div>
    </div>
  );
}
