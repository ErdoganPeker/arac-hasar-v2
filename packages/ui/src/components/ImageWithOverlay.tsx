import { useEffect, useRef, useState } from 'react';
import type { Damage, Part } from '@arac-hasar/types';
import { cn } from '../utils/cn';

export type OverlayMode = 'damages' | 'parts' | 'both' | 'none';

interface Props {
  imageUrl: string;
  damages?: Damage[];
  parts?: Part[];
  mode?: OverlayMode;
  highlightedDamageId?: number | null;
  highlightedPart?: string | null;
  /** Click handler for a damage overlay (hit-tested in container coords). */
  onDamageClick?: (id: number) => void;
  /** Click handler for a part overlay. */
  onPartClick?: (name: string) => void;
  /** Accessible alt text for the underlying image. */
  alt?: string;
  className?: string;
}

const SEVERITY_COLORS: Record<string, string> = {
  hafif: '#f59e0b',
  orta: '#f97316',
  agir: '#ef4444',
};

const PART_COLOR = '#3b82f6';

export function ImageWithOverlay({
  imageUrl,
  damages = [],
  parts = [],
  mode = 'both',
  highlightedDamageId = null,
  highlightedPart = null,
  onDamageClick,
  onPartClick,
  alt = 'İnceleme görüntüsü',
  className,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [imgDim, setImgDim] = useState<{ w: number; h: number } | null>(null);
  const [renderSize, setRenderSize] = useState<{ w: number; h: number } | null>(null);

  // Resolve natural image dimensions (also fires via <img onLoad>).
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const img = new window.Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => setImgDim({ w: img.naturalWidth, h: img.naturalHeight });
    img.src = imageUrl;
  }, [imageUrl]);

  // Track rendered container size so the canvas re-paints on layout changes.
  useEffect(() => {
    const container = containerRef.current;
    if (!container || typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const cr = entry.contentRect;
      setRenderSize({ w: cr.width, h: cr.height });
    });
    ro.observe(container);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container || !imgDim) return;

    const size = renderSize ?? {
      w: container.getBoundingClientRect().width,
      h: container.getBoundingClientRect().height,
    };
    if (size.w <= 0 || size.h <= 0) return;
    const dpr = (typeof window !== 'undefined' && window.devicePixelRatio) || 1;
    canvas.width = Math.round(size.w * dpr);
    canvas.height = Math.round(size.h * dpr);
    canvas.style.width = `${size.w}px`;
    canvas.style.height = `${size.h}px`;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, size.w, size.h);

    const sx = size.w;
    const sy = size.h;

    if (mode === 'parts' || mode === 'both') {
      parts.forEach((p) => {
        const isHi = highlightedPart === p.name;
        ctx.strokeStyle = PART_COLOR;
        ctx.lineWidth = isHi ? 3 : 1.5;
        ctx.fillStyle = isHi ? 'rgba(59, 130, 246, 0.18)' : 'rgba(59, 130, 246, 0.05)';
        drawPolygon(ctx, p.polygon_normalized, sx, sy, true);
      });
    }

    if (mode === 'damages' || mode === 'both') {
      damages.forEach((d) => {
        const color = SEVERITY_COLORS[d.severity.level] || '#999';
        const isHi = highlightedDamageId === d.id;
        ctx.strokeStyle = color;
        ctx.lineWidth = isHi ? 4 : 2;
        ctx.fillStyle = isHi ? `${color}55` : `${color}22`;
        if (d.polygon_normalized?.length) {
          drawPolygon(ctx, d.polygon_normalized, sx, sy, true);
        } else {
          drawBbox(ctx, d.bbox, sx, sy, imgDim);
        }
      });
    }
  }, [imgDim, renderSize, damages, parts, mode, highlightedDamageId, highlightedPart]);

  // Hit-test click → first damage/part whose polygon (or bbox) contains the point.
  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!onDamageClick && !onPartClick) return;
    const container = containerRef.current;
    if (!container || !imgDim) return;
    const rect = container.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    const nx = (e.clientX - rect.left) / rect.width;
    const ny = (e.clientY - rect.top) / rect.height;
    if (nx < 0 || nx > 1 || ny < 0 || ny > 1) return;

    if (onDamageClick && (mode === 'damages' || mode === 'both')) {
      for (const d of damages) {
        if (d.polygon_normalized?.length) {
          if (pointInPolygon(nx, ny, d.polygon_normalized)) {
            onDamageClick(d.id);
            return;
          }
        } else if (d.bbox && d.bbox.length >= 4) {
          const [x1, y1, x2, y2] = d.bbox;
          const px = nx * imgDim.w;
          const py = ny * imgDim.h;
          if (px >= x1! && px <= x2! && py >= y1! && py <= y2!) {
            onDamageClick(d.id);
            return;
          }
        }
      }
    }
    if (onPartClick && (mode === 'parts' || mode === 'both')) {
      for (const p of parts) {
        if (p.polygon_normalized?.length && pointInPolygon(nx, ny, p.polygon_normalized)) {
          onPartClick(p.name);
          return;
        }
      }
    }
  };

  const interactive = !!(onDamageClick || onPartClick);

  // Reserve layout space ASAP to prevent CLS. Until we know the image's
  // intrinsic aspect ratio, fall back to 4:3 (typical vehicle photo).
  // packages/ui is framework-agnostic so we keep a plain <img> — consumer
  // apps wrap routes in next/image where they own URLs directly.
  const aspectRatio = imgDim ? `${imgDim.w} / ${imgDim.h}` : '4 / 3';

  return (
    <div
      ref={containerRef}
      onClick={interactive ? handleClick : undefined}
      className={cn(
        'relative overflow-hidden rounded-lg bg-slate-100',
        interactive && 'cursor-pointer',
        className,
      )}
      style={{ aspectRatio }}
    >
      <img
        src={imageUrl}
        alt={alt}
        draggable={false}
        loading="lazy"
        decoding="async"
        className="block h-full w-full select-none object-contain"
        onLoad={(e) => {
          const t = e.currentTarget;
          setImgDim({ w: t.naturalWidth, h: t.naturalHeight });
        }}
      />
      <canvas
        ref={canvasRef}
        className="pointer-events-none absolute inset-0 h-full w-full"
        aria-hidden
      />
    </div>
  );
}

function pointInPolygon(x: number, y: number, poly: number[][]): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i];
    const b = poly[j];
    if (!a || !b || a.length < 2 || b.length < 2) continue;
    const xi = a[0]!;
    const yi = a[1]!;
    const xj = b[0]!;
    const yj = b[1]!;
    const intersect =
      yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi + 1e-12) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

function drawPolygon(
  ctx: CanvasRenderingContext2D,
  poly: number[][],
  sx: number,
  sy: number,
  fill = false,
) {
  if (!poly || poly.length === 0) return;
  ctx.beginPath();
  poly.forEach((pt, i) => {
    if (!pt || pt.length < 2) return;
    const x = pt[0]!;
    const y = pt[1]!;
    const px = x * sx;
    const py = y * sy;
    if (i === 0) ctx.moveTo(px, py);
    else ctx.lineTo(px, py);
  });
  ctx.closePath();
  if (fill) ctx.fill();
  ctx.stroke();
}

function drawBbox(
  ctx: CanvasRenderingContext2D,
  bbox: number[],
  sx: number,
  sy: number,
  imgDim: { w: number; h: number },
) {
  if (bbox.length < 4) return;
  const x1 = bbox[0]!;
  const y1 = bbox[1]!;
  const x2 = bbox[2]!;
  const y2 = bbox[3]!;
  const rx = (x1 / imgDim.w) * sx;
  const ry = (y1 / imgDim.h) * sy;
  const rw = ((x2 - x1) / imgDim.w) * sx;
  const rh = ((y2 - y1) / imgDim.h) * sy;
  ctx.beginPath();
  ctx.rect(rx, ry, rw, rh);
  ctx.fill();
  ctx.stroke();
}
