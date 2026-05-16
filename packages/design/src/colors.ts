/**
 * Color tokens — plain hex values, platform-agnostic.
 * Consumed by:
 *   - Web (Tailwind preset)
 *   - Desktop (Tailwind preset)
 *   - Mobile (React Native StyleSheet)
 */

export const colors = {
  // Brand / primary — used for CTAs, links, focus rings, accents
  primary: {
    50: '#eef7ff',
    100: '#d9ecff',
    200: '#bcdfff',
    300: '#8ecaff',
    400: '#5aabff',
    500: '#338af3',
    600: '#1e6ee0',
    700: '#1858c0',
    800: '#194a99',
    900: '#1a3f7a',
    950: '#13284e',
  },

  // Neutrals — slate scale, text/background backbone
  neutral: {
    50: '#f8fafc',
    100: '#f1f5f9',
    200: '#e2e8f0',
    300: '#cbd5e1',
    400: '#94a3b8',
    500: '#64748b',
    600: '#475569',
    700: '#334155',
    800: '#1e293b',
    900: '#0f172a',
    950: '#020617',
  },

  // Severity — domain-specific damage severity colors.
  // Scale: clean (green) → hafif (amber) → orta (orange) → agir (red).
  // Amber chosen over pure yellow for WCAG AA contrast on white surfaces
  // (yellow-400 on white fails 3:1 contrast for badges; amber-400 passes).
  severity: {
    hafif: '#fbbf24', // amber-400  (mild)     — yellow-leaning amber for contrast
    orta: '#fb923c', // orange-400 (moderate)
    agir: '#ef4444', // red-500    (severe)
    clean: '#22c55e', // green-500 (no damage)
  },

  // Semantic feedback colors
  success: {
    50: '#ecfdf5',
    100: '#d1fae5',
    500: '#10b981',
    600: '#059669',
    700: '#047857',
    900: '#064e3b',
  },
  warning: {
    50: '#fffbeb',
    100: '#fef3c7',
    500: '#f59e0b',
    600: '#d97706',
    700: '#b45309',
    900: '#78350f',
  },
  danger: {
    50: '#fef2f2',
    100: '#fee2e2',
    500: '#ef4444',
    600: '#dc2626',
    700: '#b91c1c',
    900: '#7f1d1d',
  },
  info: {
    50: '#eff6ff',
    100: '#dbeafe',
    500: '#3b82f6',
    600: '#2563eb',
    700: '#1d4ed8',
    900: '#1e3a8a',
  },

  // Surface colors (semantic aliases)
  surface: {
    background: '#ffffff',
    card: '#ffffff',
    muted: '#f8fafc',
    inverted: '#0f172a',
  },

  // Pure values
  white: '#ffffff',
  black: '#000000',
  transparent: 'transparent',
} as const;

// Dark theme palette (RN/desktop dark mode source of truth)
export const colorsDark = {
  primary: colors.primary, // hue stays the same; surfaces flip
  neutral: colors.neutral,
  severity: colors.severity,
  success: colors.success,
  warning: colors.warning,
  danger: colors.danger,
  info: colors.info,
  surface: {
    background: '#0f172a',
    card: '#1e293b',
    muted: '#334155',
    inverted: '#ffffff',
  },
  white: '#ffffff',
  black: '#000000',
  transparent: 'transparent',
} as const;

export type ColorScale = keyof typeof colors;
export type SeverityColorKey = keyof typeof colors.severity;
