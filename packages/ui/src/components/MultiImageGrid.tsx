import type { ReactNode } from 'react';
import { cn } from '../utils/cn';

export interface MultiImageGridItem {
  /** Backend image URL — null/undefined renders default car placeholder */
  url?: string | null;
  /** Alt text for accessibility */
  alt?: string;
  /** Optional badge content rendered top-right (e.g. damage count) */
  badge?: ReactNode;
  /** Optional label rendered bottom (e.g. "Ön sol") */
  label?: string;
}

interface Props {
  items: MultiImageGridItem[];
  className?: string;
  /** Click handler — called with item index */
  onItemClick?: (index: number) => void;
  /**
   * Intrinsic image dimensions hinted to the browser to reserve space
   * and prevent CLS — actual rendered size still follows the aspect ratio.
   * Defaults to 400x300 (4:3).
   */
  intrinsicWidth?: number;
  intrinsicHeight?: number;
  /** Aspect ratio class — defaults to 4:3 (matches default intrinsic dims) */
  aspectRatioClass?: string;
}

/**
 * Responsive multi-image thumbnail grid (spec-aligned).
 *
 * - 3 columns on mobile, 4 on sm (≥640px), 6 on lg (≥1024px)
 * - Fixed aspect ratio per cell (no layout shift)
 * - Every <img> receives explicit width/height attributes so the browser can
 *   reserve space even without next/image — usable in Tauri/RN-web shells.
 * - Falls back to inline car SVG when a URL is missing.
 */
export function MultiImageGrid({
  items,
  className,
  onItemClick,
  intrinsicWidth = 400,
  intrinsicHeight = 300,
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

        const cell = (
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
                <img
                  src={item.url!}
                  alt={alt}
                  width={intrinsicWidth}
                  height={intrinsicHeight}
                  loading="lazy"
                  decoding="async"
                  className="absolute inset-0 h-full w-full object-cover"
                />
              ) : (
                <DefaultCarPlaceholder index={i} />
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
                {cell}
              </button>
            ) : (
              <div>{cell}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function DefaultCarPlaceholder({ index }: { index: number }) {
  return (
    <div
      className="absolute inset-0 flex flex-col items-center justify-center gap-1 bg-gradient-to-br from-slate-50 to-slate-100 text-slate-400"
      aria-hidden
    >
      <svg
        viewBox="0 0 48 30"
        xmlns="http://www.w3.org/2000/svg"
        className="h-7 w-7 sm:h-8 sm:w-8"
        aria-hidden
      >
        <path
          d="M6 22 L9 14 Q10.5 11 14 11 H34 Q37.5 11 39 14 L42 22 Z"
          fill="#94a3b8"
        />
        <path
          d="M13 16 Q14.5 13 17.5 13 H30.5 Q33.5 13 35 16 H13 Z"
          fill="#cbd5e1"
          opacity="0.85"
        />
        <circle cx="14" cy="23" r="3" fill="#0f172a" />
        <circle cx="34" cy="23" r="3" fill="#0f172a" />
      </svg>
      <span className="text-[10px] font-medium uppercase tracking-wider">
        #{index + 1}
      </span>
    </div>
  );
}
