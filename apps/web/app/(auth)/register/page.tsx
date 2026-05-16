'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import axios from 'axios';
import { UserPlus } from 'lucide-react';
import { Spinner } from '@arac-hasar/ui';
import { FormField } from '@/components/FormField';
import { useAuth } from '@/lib/auth-context';
import { useToast } from '@/components/ToastProvider';

const schema = z
  .object({
    full_name: z.string().min(2),
    email: z.string().email(),
    password: z.string().min(8),
    confirm: z.string().min(8),
  })
  .refine((v: { password: string; confirm: string }) => v.password === v.confirm, {
    path: ['confirm'],
    message: 'mismatch',
  });

type FormValues = z.infer<typeof schema>;

export default function RegisterPage() {
  const router = useRouter();
  const t = useTranslations('auth');
  const tc = useTranslations('common');
  const { register: registerUser } = useAuth();
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
      await registerUser(values.email, values.password, values.full_name);
      toast.success(t('registerSuccess'));
      router.push('/dashboard');
    } catch (err) {
      if (axios.isAxiosError(err) && err.response?.status === 409) {
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
        {t('registerTitle')}
      </h1>
      <p className="mt-1 text-sm text-slate-600">{t('registerSubtitle')}</p>

      <form onSubmit={handleSubmit(onSubmit)} className="mt-6 space-y-4" noValidate>
        <FormField
          label={t('fullName')}
          autoComplete="name"
          placeholder={t('fullNamePlaceholder')}
          error={errors.full_name ? t('fullNameRequired') : undefined}
          {...register('full_name')}
        />
        <FormField
          label={t('email')}
          type="email"
          autoComplete="email"
          placeholder={t('emailPlaceholder')}
          error={errors.email ? t('emailInvalid') : undefined}
          {...register('email')}
        />
        <FormField
          label={t('password')}
          type="password"
          autoComplete="new-password"
          placeholder={t('passwordPlaceholder')}
          error={errors.password ? t('passwordTooShort') : undefined}
          {...register('password')}
        />
        <FormField
          label={t('passwordConfirm')}
          type="password"
          autoComplete="new-password"
          error={
            errors.confirm
              ? errors.confirm.message === 'mismatch'
                ? t('passwordMismatch')
                : t('passwordTooShort')
              : undefined
          }
          {...register('confirm')}
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
              <UserPlus className="h-4 w-4" aria-hidden /> {t('registerCta')}
            </>
          )}
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-slate-600">
        {t('registerQuestion')}{' '}
        <Link
          href="/login"
          className="font-semibold text-brand-700 hover:underline"
        >
          {t('goToLogin')}
        </Link>
      </p>
    </div>
  );
}
