/**
 * ImageAnnotator — canvas-based overlay renderer for inspection visualizations.
 *
 * - Draws parts (polygons) and damages (boxes) on top of the rendered image.
 * - Mode toggle: 'parts' | 'damages' | 'both'.
 * - Honors hover highlights from PartsList / DamageTable.
 * - Resizes canvas to the image's intrinsic dimensions (via ResizeObserver on container).
 */
import { useEffect, useRef } from 'react';

type Mode = 'parts' | 'damages' | 'both';

interface Polygon {
  name: string;
  points: number[][]; // [[x,y], ...] in image pixel coords
  color?: string;
  status?: string;
}
interface Box {
  id?: number;
  bbox: [number, number, number, number]; // x,y,w,h in image pixel coords
  label?: string;
  severity?: string;
}

const SEVERITY_COLORS: Record<string, string> = {
  minor: '#10b981',
  moderate: '#f59e0b',
  severe: '#ef4444',
  total_loss: '#475569',
};

export function ImageAnnotator({
  imageUrl,
  parts = [],
  damages = [],
  mode = 'both',
  highlightedPart = null,
  highlightedDamageId = null,
}: {
  imageUrl: string;
  parts?: Polygon[];
  damages?: Box[];
  mode?: Mode;
  highlightedPart?: string | null;
  highlightedDamageId?: number | null;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);

  useEffect(() => {
    const draw = () => {
      const canvas = canvasRef.current;
      const img = imgRef.current;
      if (!canvas || !img || !img.complete || !img.naturalWidth) return;
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      if (mode === 'parts' || mode === 'both') {
        for (const p of parts) {
          if (p.points.length < 3) continue;
          const isHi = highlightedPart === p.name;
          ctx.beginPath();
          p.points.forEach((pt, i) => {
            const x = pt[0] ?? 0;
            const y = pt[1] ?? 0;
            if (i) ctx.lineTo(x, y);
            else ctx.moveTo(x, y);
          });
          ctx.closePath();
          ctx.strokeStyle = p.color ?? '#2563eb';
          ctx.lineWidth = isHi ? 5 : 2;
          ctx.fillStyle = isHi
            ? 'rgba(37, 99, 235, 0.25)'
            : p.status === 'clean'
              ? 'rgba(16, 185, 129, 0.10)'
              : 'rgba(37, 99, 235, 0.10)';
          ctx.fill();
          ctx.stroke();
        }
      }

      if (mode === 'damages' || mode === 'both') {
        for (const d of damages) {
          const [x, y, w, h] = d.bbox;
          const isHi = highlightedDamageId === d.id;
          const col = SEVERITY_COLORS[d.severity ?? ''] ?? '#ef4444';
          ctx.strokeStyle = col;
          ctx.lineWidth = isHi ? 5 : 3;
          ctx.fillStyle = isHi ? `${col}55` : `${col}22`;
          ctx.fillRect(x, y, w, h);
          ctx.strokeRect(x, y, w, h);
          if (d.label) {
            ctx.font = 'bold 14px system-ui';
            const pad = 4;
            const tw = ctx.measureText(d.label).width + pad * 2;
            ctx.fillStyle = col;
            ctx.fillRect(x, y - 20, tw, 20);
            ctx.fillStyle = '#fff';
            ctx.fillText(d.label, x + pad, y - 6);
          }
        }
      }
    };

    const img = imgRef.current;
    if (img && img.complete) draw();
    else img?.addEventListener('load', draw, { once: true });
    return () => img?.removeEventListener('load', draw);
  }, [parts, damages, mode, highlightedPart, highlightedDamageId, imageUrl]);

  return (
    <div
      ref={containerRef}
      className="relative w-full overflow-hidden rounded-xl border border-slate-200 bg-slate-100 dark:border-slate-700 dark:bg-slate-900"
    >
      <img
        ref={imgRef}
        src={imageUrl}
        alt="inspection"
        className="block h-auto w-full select-none"
        draggable={false}
      />
      <canvas
        ref={canvasRef}
        className="pointer-events-none absolute left-0 top-0 h-full w-full"
      />
    </div>
  );
}

export default ImageAnnotator;
