/**
 * Typography tokens — font families, sizes, weights, line heights.
 * Designed to mirror Tailwind defaults so web/desktop classes stay familiar.
 */

export const fontFamily = {
  sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
  mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
  display: ['Inter', 'system-ui', 'sans-serif'],
} as const;

/** Font sizes — `[fontSize, { lineHeight }]` tuples (Tailwind format) */
export const fontSize = {
  xs: ['0.75rem', { lineHeight: '1rem' }], //   12 / 16
  sm: ['0.875rem', { lineHeight: '1.25rem' }], //   14 / 20
  base: ['1rem', { lineHeight: '1.5rem' }], //   16 / 24
  lg: ['1.125rem', { lineHeight: '1.75rem' }], //   18 / 28
  xl: ['1.25rem', { lineHeight: '1.75rem' }], //   20 / 28
  '2xl': ['1.5rem', { lineHeight: '2rem' }], //   24 / 32
  '3xl': ['1.875rem', { lineHeight: '2.25rem' }], // 30 / 36
  '4xl': ['2.25rem', { lineHeight: '2.5rem' }], //   36 / 40
} as const;

/** Plain pixel mirror for React Native */
export const fontSizePx = {
  xs: 12,
  sm: 14,
  base: 16,
  lg: 18,
  xl: 20,
  '2xl': 24,
  '3xl': 30,
  '4xl': 36,
} as const;

export const lineHeightPx = {
  xs: 16,
  sm: 20,
  base: 24,
  lg: 28,
  xl: 28,
  '2xl': 32,
  '3xl': 36,
  '4xl': 40,
} as const;

export const fontWeight = {
  normal: '400',
  medium: '500',
  semibold: '600',
  bold: '700',
} as const;

export const letterSpacing = {
  tight: '-0.025em',
  normal: '0em',
  wide: '0.025em',
  wider: '0.05em',
  widest: '0.1em',
} as const;

export type FontSize = keyof typeof fontSize;
export type FontWeight = keyof typeof fontWeight;
