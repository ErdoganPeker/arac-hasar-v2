/**
 * Aggregate token export — single import point for all design tokens.
 */

import { colors, colorsDark } from './colors';
import { spacing, spacingPx } from './spacing';
import {
  fontFamily,
  fontSize,
  fontSizePx,
  lineHeightPx,
  fontWeight,
  letterSpacing,
} from './typography';
import { radii, radiiPx } from './radii';
import { shadows, shadowsRN } from './shadows';
import { zIndex } from './z-index';

export const tokens = {
  colors,
  colorsDark,
  spacing,
  spacingPx,
  fontFamily,
  fontSize,
  fontSizePx,
  lineHeightPx,
  fontWeight,
  letterSpacing,
  radii,
  radiiPx,
  shadows,
  shadowsRN,
  zIndex,
} as const;

export type Tokens = typeof tokens;

/** Default breakpoints (mobile-first) — px-based for media queries */
export const breakpoints = {
  sm: 640,
  md: 768,
  lg: 1024,
  xl: 1280,
  '2xl': 1536,
} as const;

export type Breakpoint = keyof typeof breakpoints;

/** Motion / transition tokens */
export const motion = {
  duration: {
    fast: 150,
    normal: 300,
    slow: 500,
  },
  easing: {
    standard: 'cubic-bezier(0.4, 0, 0.2, 1)',
    decelerate: 'cubic-bezier(0, 0, 0.2, 1)',
    accelerate: 'cubic-bezier(0.4, 0, 1, 1)',
  },
} as const;
