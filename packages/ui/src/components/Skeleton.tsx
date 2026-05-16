import type { HTMLAttributes } from 'react';
import { cn } from '../utils/cn';

interface Props extends HTMLAttributes<HTMLDivElement> {
  /** Tailwind shape class. Default `rounded-md`. */
  shape?: 'rect' | 'pill' | 'circle';
  /** Render an inline-block so it can sit alongside text. */
  inline?: boolean;
}

/**
 * Generic shimmer placeholder. Use Tailwind sizing utilities on `className`
 * (e.g. `<Skeleton className="h-4 w-32" />`).
 */
export function Skeleton({ shape = 'rect', inline, className, ...rest }: Props) {
  return (
    <div
      aria-hidden
      className={cn(
        inline ? 'inline-block' : 'block',
        'animate-pulse bg-slate-200/80',
        shape === 'rect' && 'rounded-md',
        shape === 'pill' && 'rounded-full',
        shape === 'circle' && 'rounded-full aspect-square',
        className,
      )}
      {...rest}
    />
  );
}

/** Pre-composed skeleton block that mirrors the layout of a `<PartCard />`. */
export function PartCardSkeleton({ className }: { className?: string }) {
  return (
    <div
      role="status"
      aria-label="Yükleniyor"
      className={cn(
        'rounded-xl ring-1 ring-inset ring-slate-200 bg-white p-4',
        className,
      )}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Skeleton shape="circle" className="h-2 w-2" />
          <Skeleton className="h-4 w-32" />
        </div>
        <Skeleton shape="pill" className="h-4 w-16" />
      </div>
      <Skeleton className="mt-2 h-3 w-20" />
      <div className="mt-4 space-y-2">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    </div>
  );
}

/** Skeleton variant for the cost / hero summary block. */
export function CostDisplaySkeleton({ className }: { className?: string }) {
  return (
    <div
      role="status"
      aria-label="Maliyet hesaplanıyor"
      className={cn(
        'rounded-2xl bg-slate-50 p-5 ring-1 ring-inset ring-slate-200',
        className,
      )}
    >
      <Skeleton className="h-3 w-40" />
      <Skeleton className="mt-3 h-9 w-3/4" />
      <Skeleton className="mt-2 h-4 w-1/2" />
      <div className="mt-4 flex gap-3">
        <Skeleton shape="pill" className="h-4 w-24" />
        <Skeleton shape="pill" className="h-4 w-32" />
      </div>
    </div>
  );
}
