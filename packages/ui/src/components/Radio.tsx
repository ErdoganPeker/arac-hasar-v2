import { forwardRef, useId, type InputHTMLAttributes, type ReactNode } from 'react';
import { cn } from '../utils/cn';

interface RadioProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type' | 'size'> {
  label?: ReactNode;
  hint?: string;
}

export const Radio = forwardRef<HTMLInputElement, RadioProps>(function Radio(
  { label, hint, className, id, disabled, ...rest },
  ref,
) {
  const generatedId = useId();
  const rId = id || generatedId;
  return (
    <div className="flex flex-col gap-0.5">
      <label
        htmlFor={rId}
        className={cn(
          'inline-flex items-start gap-2 cursor-pointer select-none',
          disabled && 'cursor-not-allowed opacity-60',
        )}
      >
        <span className="relative inline-flex h-5 w-5 flex-none items-center justify-center">
          <input
            ref={ref}
            id={rId}
            type="radio"
            disabled={disabled}
            className={cn(
              'peer h-5 w-5 cursor-pointer appearance-none rounded-full border bg-white transition-colors',
              'focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-1',
              'border-slate-300 checked:border-brand-600',
              'disabled:cursor-not-allowed disabled:bg-slate-100',
              className,
            )}
            {...rest}
          />
          <span className="pointer-events-none absolute h-2.5 w-2.5 rounded-full bg-brand-600 opacity-0 peer-checked:opacity-100" />
        </span>
        {label && <span className="text-sm text-slate-800">{label}</span>}
      </label>
      {hint && <p className="ml-7 text-xs text-slate-500">{hint}</p>}
    </div>
  );
});

export interface RadioGroupOption {
  value: string;
  label: ReactNode;
  hint?: string;
  disabled?: boolean;
}

interface RadioGroupProps {
  name: string;
  value?: string;
  defaultValue?: string;
  onChange?: (value: string) => void;
  options: RadioGroupOption[];
  label?: string;
  error?: string;
  orientation?: 'vertical' | 'horizontal';
  className?: string;
}

export function RadioGroup({
  name,
  value,
  defaultValue,
  onChange,
  options,
  label,
  error,
  orientation = 'vertical',
  className,
}: RadioGroupProps) {
  return (
    <fieldset className={cn('flex flex-col gap-2', className)}>
      {label && (
        <legend className="text-sm font-medium text-slate-800">{label}</legend>
      )}
      <div
        className={cn(
          'flex gap-3',
          orientation === 'vertical' ? 'flex-col' : 'flex-row flex-wrap',
        )}
      >
        {options.map((opt) => (
          <Radio
            key={opt.value}
            name={name}
            value={opt.value}
            checked={value !== undefined ? value === opt.value : undefined}
            defaultChecked={
              defaultValue !== undefined ? defaultValue === opt.value : undefined
            }
            disabled={opt.disabled}
            label={opt.label}
            hint={opt.hint}
            onChange={(e) => onChange?.(e.target.value)}
          />
        ))}
      </div>
      {error && <p className="text-xs font-medium text-red-600">{error}</p>}
    </fieldset>
  );
}
