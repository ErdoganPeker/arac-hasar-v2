/**
 * Border-radius scale.
 */

export const radii = {
  none: '0px',
  sm: '0.25rem', //  4px
  md: '0.5rem', //  8px
  lg: '0.75rem', // 12px
  xl: '1rem', // 16px
  '2xl': '1.5rem', // 24px
  '3xl': '2rem', // 32px
  full: '9999px',
} as const;

/** Pixel mirror for React Native */
export const radiiPx = {
  none: 0,
  sm: 4,
  md: 8,
  lg: 12,
  xl: 16,
  '2xl': 24,
  '3xl': 32,
  full: 9999,
} as const;

export type RadiusToken = keyof typeof radii;
