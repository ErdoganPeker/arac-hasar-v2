import { forwardRef, type HTMLAttributes } from 'react';
import { cn } from '../utils/cn';

type DivProps = HTMLAttributes<HTMLDivElement>;

export const Card = forwardRef<HTMLDivElement, DivProps>(function Card(
  { className, ...rest },
  ref,
) {
  return (
    <div
      ref={ref}
      className={cn(
        'rounded-xl border border-slate-200 bg-white shadow-sm transition-shadow',
        className,
      )}
      {...rest}
    />
  );
});

export const CardHeader = forwardRef<HTMLDivElement, DivProps>(function CardHeader(
  { className, ...rest },
  ref,
) {
  return (
    <div
      ref={ref}
      className={cn('flex flex-col gap-1 border-b border-slate-100 px-5 py-4', className)}
      {...rest}
    />
  );
});

export const CardTitle = forwardRef<HTMLHeadingElement, HTMLAttributes<HTMLHeadingElement>>(
  function CardTitle({ className, ...rest }, ref) {
    return (
      <h3
        ref={ref}
        className={cn('text-base font-semibold text-slate-900', className)}
        {...rest}
      />
    );
  },
);

export const CardDescription = forwardRef<HTMLParagraphElement, HTMLAttributes<HTMLParagraphElement>>(
  function CardDescription({ className, ...rest }, ref) {
    return <p ref={ref} className={cn('text-sm text-slate-600', className)} {...rest} />;
  },
);

export const CardBody = forwardRef<HTMLDivElement, DivProps>(function CardBody(
  { className, ...rest },
  ref,
) {
  return <div ref={ref} className={cn('px-5 py-4', className)} {...rest} />;
});

export const CardFooter = forwardRef<HTMLDivElement, DivProps>(function CardFooter(
  { className, ...rest },
  ref,
) {
  return (
    <div
      ref={ref}
      className={cn(
        'flex items-center justify-end gap-2 border-t border-slate-100 px-5 py-3',
        className,
      )}
      {...rest}
    />
  );
});
