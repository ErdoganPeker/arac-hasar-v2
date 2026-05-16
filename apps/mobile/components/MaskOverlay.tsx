/**
 * MaskOverlay.tsx — Renders normalized parts/damages polygons on top of an image.
 *
 * Polygons are normalized [0..1] coordinates relative to image native size.
 * We rely on the parent to provide the rendered image's pixel width/height.
 */
import React from 'react';
import Svg, { Polygon } from 'react-native-svg';
import { Damage, Part } from '@arac-hasar/types';
import { severityColor } from '../theme';

interface Props {
  width: number;
  height: number;
  parts?: Part[];
  damages?: Damage[];
  showParts?: boolean;
  showDamages?: boolean;
  partOpacity?: number;
  damageOpacity?: number;
}

function toPoints(poly: number[][], w: number, h: number): string {
  if (!poly || poly.length === 0) return '';
  return poly.map(([x, y]) => `${(x * w).toFixed(1)},${(y * h).toFixed(1)}`).join(' ');
}

export default function MaskOverlay({
  width,
  height,
  parts = [],
  damages = [],
  showParts = false,
  showDamages = true,
  partOpacity = 0.18,
  damageOpacity = 0.45,
}: Props) {
  if (width <= 0 || height <= 0) return null;
  return (
    <Svg
      width={width}
      height={height}
      style={{ position: 'absolute', left: 0, top: 0 }}
      pointerEvents="none"
    >
      {showParts &&
        parts.map((p, i) => {
          const pts = toPoints(p.polygon_normalized, width, height);
          if (!pts) return null;
          return (
            <Polygon
              key={`p-${i}`}
              points={pts}
              fill="#3b82f6"
              fillOpacity={partOpacity}
              stroke="#3b82f6"
              strokeOpacity={0.8}
              strokeWidth={1}
            />
          );
        })}
      {showDamages &&
        damages.map((d, i) => {
          const pts = toPoints(d.polygon_normalized, width, height);
          if (!pts) return null;
          const color = severityColor(d.severity?.level ?? 'orta');
          return (
            <Polygon
              key={`d-${i}-${d.id}`}
              points={pts}
              fill={color}
              fillOpacity={damageOpacity}
              stroke={color}
              strokeOpacity={1}
              strokeWidth={2}
            />
          );
        })}
    </Svg>
  );
}
