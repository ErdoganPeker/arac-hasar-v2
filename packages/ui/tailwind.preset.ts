/**
 * Shared Tailwind preset — web + desktop ortak design tokens.
 *
 * Web and Desktop import this in their tailwind.config:
 *   presets: [require('@arac-hasar/ui/tailwind-preset')]
 */
import type { Config } from 'tailwindcss';
import {
  colors,
  spacing,
  fontFamily,
  fontSize,
  fontWeight,
  letterSpacing,
  radii,
  shadows,
  zIndex,
  breakpoints,
} from '@arac-hasar/design';

const preset: Partial<Config> = {
  darkMode: 'class',
  theme: {
    screens: {
      sm: `${breakpoints.sm}px`,
      md: `${breakpoints.md}px`,
      lg: `${breakpoints.lg}px`,
      xl: `${breakpoints.xl}px`,
      '2xl': `${breakpoints['2xl']}px`,
    },
    extend: {
      colors: {
        brand: colors.primary,
        primary: colors.primary,
        neutral: colors.neutral,
        severity: colors.severity,
        success: colors.success,
        warning: colors.warning,
        danger: colors.danger,
        info: colors.info,
        surface: colors.surface,
      },
      spacing: spacing as unknown as Record<string, string>,
      fontFamily: {
        sans: fontFamily.sans,
        mono: fontFamily.mono,
        display: fontFamily.display,
      },
      fontSize: fontSize as unknown as Config['theme'] extends infer T
        ? T extends { fontSize: infer F }
          ? F
          : never
        : never,
      fontWeight,
      letterSpacing,
      borderRadius: radii,
      boxShadow: shadows,
      zIndex: zIndex as unknown as Record<string, string>,
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fade-in': 'fadeIn 200ms ease-out',
        'slide-up': 'slideUp 250ms ease-out',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
      },
    },
  },
};

export default preset;
module.exports = preset;
