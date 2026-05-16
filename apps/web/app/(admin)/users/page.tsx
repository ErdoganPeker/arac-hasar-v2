'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ShieldCheck, ShieldOff, Power } from 'lucide-react';
import { Spinner } from '@arac-hasar/ui';
import { adminUsers, type User } from '@/lib/api';
import { useToast } from '@/components/ToastProvider';

export default function AdminUsersPage() {
  const t = useTranslations('admin');
  const tc = useTranslations('common');
  const toast = useToast();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await adminUsers.list();
        if (!cancelled) setUsers(list);
      } catch {
        if (!cancelled) setUsers([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function toggleRole(u: User) {
    setBusy(u.id);
    try {
      const next = u.role === 'admin' ? 'user' : 'admin';
      const updated = await adminUsers.setRole(u.id, next);
      setUsers((prev) => prev.map((x) => (x.id === u.id ? updated : x)));
    } catch {
      toast.error(tc('errorGeneric'));
    } finally {
      setBusy(null);
    }
  }

  async function toggleActive(u: User) {
    setBusy(u.id);
    try {
      const updated = await adminUsers.setActive(u.id, !(u.is_active ?? true));
      setUsers((prev) => prev.map((x) => (x.id === u.id ? updated : x)));
    } catch {
      toast.error(tc('errorGeneric'));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="container-page py-10">
      <header className="mb-6">
        <h1 className="text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
          {t('usersTitle')}
        </h1>
        <p className="mt-1 text-slate-600">{t('usersSubtitle')}</p>
      </header>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        {loading ? (
          <div className="flex justify-center py-16">
            <Spinner size="lg" />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">
                <tr>
                  <th className="px-4 py-3">{t('table.email')}</th>
                  <th className="px-4 py-3">{t('table.fullName')}</th>
                  <th className="px-4 py-3">{t('table.role')}</th>
                  <th className="px-4 py-3">{t('table.createdAt')}</th>
                  <th className="px-4 py-3 text-right">{t('table.actions')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {users.map((u) => {
                  const isAdmin = u.role === 'admin';
                  const active = u.is_active ?? true;
                  return (
                    <tr key={u.id} className="hover:bg-slate-50">
                      <td className="px-4 py-3 font-medium text-slate-900">
                        {u.email}
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        {u.full_name ?? '—'}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${
                            isAdmin
                              ? 'bg-brand-100 text-brand-800'
                              : 'bg-slate-100 text-slate-700'
                          }`}
                        >
                          {isAdmin ? t('roleAdmin') : t('roleUser')}
                        </span>
                        {!active && (
                          <span className="ml-2 inline-flex items-center rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-red-800">
                            off
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-slate-600">
                        {u.created_at
                          ? new Date(u.created_at).toLocaleDateString('tr-TR')
                          : '—'}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="inline-flex items-center gap-1">
                          <button
                            type="button"
                            disabled={busy === u.id}
                            onClick={() => toggleRole(u)}
                            className="btn-ghost text-xs"
                          >
                            {isAdmin ? (
                              <>
                                <ShieldOff className="h-3.5 w-3.5" aria-hidden />
                                {t('demote')}
                              </>
                            ) : (
                              <>
                                <ShieldCheck
                                  className="h-3.5 w-3.5"
                                  aria-hidden
                                />
                                {t('promote')}
                              </>
                            )}
                          </button>
                          <button
                            type="button"
                            disabled={busy === u.id}
                            onClick={() => toggleActive(u)}
                            className="btn-ghost text-xs"
                          >
                            <Power className="h-3.5 w-3.5" aria-hidden />
                            {active ? t('disable') : t('enable')}
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
