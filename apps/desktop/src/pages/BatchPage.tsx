/**
 * BatchPage — thin wrapper around <BatchUploader />.
 * The heavy lifting (queue, concurrency, retries, CSV) lives in the component.
 */
import { useTranslation } from 'react-i18next';
import BatchUploader from '@/components/BatchUploader';

export default function BatchPage() {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">{t('batch.title')}</h1>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{t('batch.subtitle')}</p>
      </div>
      <BatchUploader />
    </div>
  );
}
