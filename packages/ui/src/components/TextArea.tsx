import { forwardRef, useId, type TextareaHTMLAttributes } from 'react';
import { cn } from '../utils/cn';

interface Props extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  hint?: string;
  error?: string;
  containerClassName?: string;
}

export const TextArea = forwardRef<HTMLTextAreaElement, Props>(function TextArea(
  { label, hint, error, className, containerClassName, id, required, rows = 4, ...rest },
  ref,
) {
  const generatedId = useId();
  const taId = id || generatedId;
  const describedBy = error
    ? `${taId}-error`
    : hint
      ? `${taId}-hint`
      : undefined;

  return (
    <div className={cn('flex flex-col gap-1.5', containerClassName)}>
      {label && (
        <label htmlFor={taId} className="text-sm font-medium text-slate-800">
          {label}
          {required && (
            <span className="ml-0.5 text-red-600" aria-hidden>
              *
            </span>
          )}
        </label>
      )}
      <textarea
        ref={ref}
        id={taId}
        rows={rows}
        aria-invalid={!!error || undefined}
        aria-describedby={describedBy}
        required={required}
        className={cn(
          'block w-full rounded-md border bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400',
          'transition-colors focus:outline-none focus:ring-2',
          'resize-y',
          error
            ? 'border-red-400 focus:border-red-500 focus:ring-red-200'
            : 'border-slate-300 focus:border-brand-500 focus:ring-brand-200',
          'disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400',
          className,
        )}
        {...rest}
      />
      {hint && !error && (
        <p id={`${taId}-hint`} className="text-xs text-slate-500">
          {hint}
        </p>
      )}
      {error && (
        <p id={`${taId}-error`} className="text-xs font-medium text-red-600">
          {error}
        </p>
      )}
    </div>
  );
});
