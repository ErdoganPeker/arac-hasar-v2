import { forwardRef, useId, type InputHTMLAttributes, type ReactNode } from 'react';
import { Check } from 'lucide-react';
import { cn } from '../utils/cn';

interface Props extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type' | 'size'> {
  label?: ReactNode;
  hint?: string;
  error?: string;
}

export const Checkbox = forwardRef<HTMLInputElement, Props>(function Checkbox(
  { label, hint, error, className, id, disabled, ...rest },
  ref,
) {
  const generatedId = useId();
  const cbId = id || generatedId;

  return (
    <div className="flex flex-col gap-1">
      <label
        htmlFor={cbId}
        className={cn(
          'inline-flex items-start gap-2 cursor-pointer select-none',
          disabled && 'cursor-not-allowed opacity-60',
        )}
      >
        <span className="relative inline-flex h-5 w-5 flex-none items-center justify-center">
          <input
            ref={ref}
            id={cbId}
            type="checkbox"
            disabled={disabled}
            aria-invalid={!!error || undefined}
            className={cn(
              'peer h-5 w-5 cursor-pointer appearance-none rounded border transition-colors',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-1',
              'border-slate-300 bg-white',
              'checked:border-brand-600 checked:bg-brand-600',
              'disabled:cursor-not-allowed disabled:bg-slate-100',
              error && 'border-red-400',
              className,
            )}
            {...rest}
          />
          <Check
            className="pointer-events-none absolute h-3.5 w-3.5 text-white opacity-0 peer-checked:opacity-100"
            strokeWidth={3}
            aria-hidden
          />
        </span>
        {label && <span className="text-sm text-slate-800">{label}</span>}
      </label>
      {hint && !error && <p className="ml-7 text-xs text-slate-500">{hint}</p>}
      {error && <p className="ml-7 text-xs font-medium text-red-600">{error}</p>}
    </div>
  );
});
