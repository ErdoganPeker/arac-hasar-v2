/**
 * Spacing scale — 4px-based.
 * Values are in REM for web/desktop and PIXELS for mobile (RN doesn't use rem).
 * Keys map to Tailwind spacing tokens directly.
 */

export const spacing = {
  0: '0rem',
  px: '1px',
  0.5: '0.125rem', //  2px
  1: '0.25rem', //  4px
  1.5: '0.375rem', //  6px
  2: '0.5rem', //  8px
  2.5: '0.625rem', // 10px
  3: '0.75rem', // 12px
  3.5: '0.875rem', // 14px
  4: '1rem', // 16px
  5: '1.25rem', // 20px
  6: '1.5rem', // 24px
  7: '1.75rem', // 28px
  8: '2rem', // 32px
  10: '2.5rem', // 40px
  12: '3rem', // 48px
  14: '3.5rem', // 56px
  16: '4rem', // 64px
  20: '5rem', // 80px
  24: '6rem', // 96px
} as const;

// Pixel mirror for React Native (1rem = 16px convention)
export const spacingPx = {
  0: 0,
  px: 1,
  0.5: 2,
  1: 4,
  1.5: 6,
  2: 8,
  2.5: 10,
  3: 12,
  3.5: 14,
  4: 16,
  5: 20,
  6: 24,
  7: 28,
  8: 32,
  10: 40,
  12: 48,
  14: 56,
  16: 64,
  20: 80,
  24: 96,
} as const;

export type SpacingToken = keyof typeof spacing;
