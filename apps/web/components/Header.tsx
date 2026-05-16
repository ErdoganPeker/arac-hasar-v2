'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { LogIn, LogOut, ShieldCheck, User as UserIcon } from 'lucide-react';
import { useAuth } from '@/lib/auth-context';
import { LanguageSwitcher } from './LanguageSwitcher';
import { ModelSelector } from './ModelSelector';

const PROTECTED_NAV = [
  { href: '/dashboard', key: 'dashboard' },
  { href: '/inspect/new', key: 'newInspection' },
  { href: '/history', key: 'history' },
] as const;

export function Header() {
  const t = useTranslations('nav');
  const tAuth = useTranslations('auth');
  const tCommon = useTranslations('common');
  const pathname = usePathname();
  const { user, isAuthenticated, isAdmin, logout, loading } = useAuth();

  const hideOnAuthPages =
    pathname?.startsWith('/login') || pathname?.startsWith('/register');

  return (
    <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/85 backdrop-blur">
      <div className="container-page flex h-16 items-center justify-between gap-6">
        <Link
          href={isAuthenticated ? '/dashboard' : '/'}
          className="flex items-center gap-2 text-slate-900"
          aria-label={t('goToHome')}
        >
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-600 text-white">
            <ShieldCheck className="h-5 w-5" aria-hidden />
          </span>
          <span className="text-lg font-bold tracking-tight">Hasarİ</span>
          <span className="hidden text-[11px] font-medium uppercase tracking-wider text-slate-400 sm:inline">
            MVP
          </span>
        </Link>

        <nav className="flex items-center gap-1">
          {isAuthenticated && !hideOnAuthPages && (
            <>
              {PROTECTED_NAV.map((item) => {
                const active =
                  pathname === item.href || pathname?.startsWith(`${item.href}/`);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`hidden rounded-lg px-3 py-2 text-sm font-medium transition-colors sm:inline-flex ${
                      active
                        ? 'bg-slate-100 text-slate-900'
                        : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                    }`}
                  >
                    {t(item.key)}
                  </Link>
                );
              })}
              {isAdmin && (
                <Link
                  href="/users"
                  className="hidden rounded-lg px-3 py-2 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 sm:inline-flex"
                >
                  {t('users')}
                </Link>
              )}
              <Link
                href="/settings"
                className="hidden rounded-lg px-3 py-2 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 sm:inline-flex"
              >
                {t('settings')}
              </Link>
            </>
          )}

          {isAuthenticated && !hideOnAuthPages && (
            <div className="ml-2 hidden md:block">
              <ModelSelector />
            </div>
          )}

          <div className="ml-2 hidden sm:block">
            <LanguageSwitcher />
          </div>

          {loading ? null : isAuthenticated ? (
            <div className="ml-2 flex items-center gap-2">
              <span className="hidden items-center gap-1.5 rounded-lg bg-slate-100 px-2.5 py-1.5 text-xs font-medium text-slate-700 sm:inline-flex">
                <UserIcon className="h-3.5 w-3.5" aria-hidden />
                <span className="max-w-[160px] truncate">
                  {user?.full_name || user?.email}
                </span>
              </span>
              <button
                type="button"
                onClick={logout}
                className="btn-ghost"
                aria-label={tCommon('logout')}
                title={tCommon('logout')}
              >
                <LogOut className="h-4 w-4" aria-hidden />
                <span className="hidden sm:inline">{tCommon('logout')}</span>
              </button>
            </div>
          ) : (
            !hideOnAuthPages && (
              <Link
                href="/login"
                className="btn-primary ml-2 inline-flex"
                aria-label={tAuth('loginCtaShort')}
              >
                <LogIn className="h-4 w-4" aria-hidden />
                {tAuth('loginCtaShort')}
              </Link>
            )
          )}
        </nav>
      </div>
    </header>
  );
}
