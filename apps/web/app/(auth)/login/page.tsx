'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import axios from 'axios';
import { LogIn } from 'lucide-react';
import { Spinner } from '@arac-hasar/ui';
import { FormField } from '@/components/FormField';
import { useAuth } from '@/lib/auth-context';
import { useToast } from '@/components/ToastProvider';

const schema = z.object({
  email: z.string().email(),
  password: z.string().min(8),
});

type FormValues = z.infer<typeof schema>;

export default function LoginPage() {
  const router = useRouter();
  const search = useSearchParams();
  const next = search.get('next') || '/dashboard';
  const t = useTranslations('auth');
  const tc = useTranslations('common');
  const { login } = useAuth();
  const toast = useToast();
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
  });

  async function onSubmit(values: FormValues) {
    setServerError(null);
    try {
      await login(values.email, values.password);
      toast.success(t('loginSuccess'));
      router.push(next);
    } catch (err) {
      const status = axios.isAxiosError(err) ? err.response?.status : undefined;
      if (status === 401 || status === 400) {
        setServerError(t('invalidCredentials'));
      } else if (axios.isAxiosError(err) && !err.response) {
        setServerError(tc('networkError'));
      } else {
        setServerError(tc('errorGeneric'));
      }
    }
  }

  return (
    <div>
      <h1 className="text-2xl font-bold tracking-tight text-slate-900">
        {t('loginTitle')}
      </h1>
      <p className="mt-1 text-sm text-slate-600">{t('loginSubtitle')}</p>

      <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
        <FormField
          label={t('email')}
          type="email"
          autoComplete="email"
          placeholder={t('emailPlaceholder')}
          error={
            errors.email
              ? errors.email.message === 'Invalid email'
                ? t('emailInvalid')
                : t('emailRequired')
              : undefined
          }
          {...register('email')}
        />
        <FormField
          label={t('password')}
          type="password"
          autoComplete="current-password"
          placeholder={t('passwordPlaceholder')}
          error={
            errors.password
              ? errors.password.message?.includes('8')
                ? t('passwordTooShort')
                : t('passwordRequired')
              : undefined
          }
          {...register('password')}
        />

        {serverError && (
          <div
            role="alert"
            className="rounded-lg bg-red-50 p-3 text-sm text-red-800 ring-1 ring-red-200"
          >
            {serverError}
          </div>
        )}

        <button
          type="submit"
          disabled={isSubmitting}
          className="btn-primary w-full"
        >
          {isSubmitting ? (
            <Spinner size="sm" />
          ) : (
            <>
              <LogIn className="h-4 w-4" aria-hidden /> {t('loginCta')}
            </>
          )}
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-slate-600">
        {t('loginQuestion')}{' '}
        <Link
          href="/register"
          className="font-semibold text-brand-700 hover:underline"
        >
          {t('goToRegister')}
        </Link>
      </p>
    </div>
  );
}
