import type { ReactNode } from 'react';
import { Car, ImageOff } from 'lucide-react';
import { cn } from '../utils/cn';

export interface ThumbnailItem {
  /** Backend image URL — null/undefined renders placeholder */
  url?: string | null;
  /** Alt text for accessibility */
  alt?: string;
  /** Optional badge content rendered top-right (e.g. damage count) */
  badge?: ReactNode;
  /** Optional label rendered bottom (e.g. "Ön sol") */
  label?: string;
}

interface Props {
  items: ThumbnailItem[];
  className?: string;
  /** Click handler — called with item index */
  onItemClick?: (index: number) => void;
  /** Aspect ratio class — defaults to 4:3 for vehicle photos */
  aspectRatioClass?: string;
}

/**
 * Responsive thumbnail grid for multi-photo inspections.
 * - 3 columns on mobile, 4 on sm, 6 on lg
 * - Fixed aspect ratio reserves space (prevents CLS)
 * - Renders car-icon placeholder when image url is missing
 */
export function MultiImageThumbnailGrid({
  items,
  className,
  onItemClick,
  aspectRatioClass = 'aspect-[4/3]',
}: Props) {
  if (!items || items.length === 0) return null;
  return (
    <ul
      role="list"
      className={cn(
        'grid grid-cols-3 gap-2 sm:grid-cols-4 sm:gap-3 lg:grid-cols-6',
        className,
      )}
    >
      {items.map((item, i) => {
        const interactive = !!onItemClick;
        const hasUrl = !!item.url;
        const alt = item.alt ?? `Fotoğraf ${i + 1}`;
        const content = (
          <>
            <div
              className={cn(
                'relative w-full overflow-hidden rounded-lg bg-slate-100 ring-1 ring-inset ring-slate-200',
                aspectRatioClass,
                interactive &&
                  'transition-shadow group-hover:shadow-md group-focus-visible:shadow-md',
              )}
            >
              {hasUrl ? (
                // packages/ui is framework-agnostic — plain <img> with
                // explicit width/height reserves space (parent aspect ratio
                // prevents CLS). Consumer apps can wrap with next/image if
                // they need optimised srcSet.
                <img
                  src={item.url!}
                  alt={alt}
                  width={400}
                  height={300}
                  loading="lazy"
                  decoding="async"
                  className="absolute inset-0 h-full w-full object-cover"
                />
              ) : (
                <ThumbnailPlaceholder index={i} />
              )}
              {item.badge && (
                <span className="absolute right-1.5 top-1.5 inline-flex items-center rounded-full bg-slate-900/85 px-1.5 py-0.5 text-[10px] font-semibold text-white shadow-sm">
                  {item.badge}
                </span>
              )}
            </div>
            {item.label && (
              <div className="mt-1.5 truncate text-center text-[11px] font-medium text-slate-600">
                {item.label}
              </div>
            )}
          </>
        );

        return (
          <li key={i}>
            {interactive ? (
              <button
                type="button"
                onClick={() => onItemClick?.(i)}
                aria-label={item.label ? `${item.label} — ${alt}` : alt}
                className="group block w-full rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2"
              >
                {content}
              </button>
            ) : (
              <div>{content}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function ThumbnailPlaceholder({ index }: { index: number }) {
  return (
    <div
      className="absolute inset-0 flex flex-col items-center justify-center gap-1 bg-gradient-to-br from-slate-50 to-slate-100 text-slate-400"
      aria-hidden
    >
      <Car className="h-6 w-6 sm:h-7 sm:w-7" />
      <span className="text-[10px] font-medium uppercase tracking-wider">
        #{index + 1}
      </span>
    </div>
  );
}

/**
 * Compact placeholder for history rows when no thumbnail is available.
 * Use as standalone (square) icon block.
 */
export function ThumbnailFallback({
  className,
  size = 'md',
}: {
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}) {
  const dimensions =
    size === 'sm' ? 'h-10 w-10' : size === 'lg' ? 'h-20 w-20' : 'h-14 w-14';
  const iconSize =
    size === 'sm' ? 'h-5 w-5' : size === 'lg' ? 'h-9 w-9' : 'h-7 w-7';
  return (
    <div
      className={cn(
        'flex flex-none items-center justify-center rounded-lg bg-gradient-to-br from-brand-50 to-brand-100 text-brand-600 ring-1 ring-inset ring-brand-200',
        dimensions,
        className,
      )}
      role="img"
      aria-label="Görsel hazırlanıyor"
    >
      <ImageOff className={iconSize} aria-hidden />
    </div>
  );
}
