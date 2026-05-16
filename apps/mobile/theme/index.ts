/**
 * theme/index.ts — Design tokens for Hasarİ mobile app.
 * Tailored for native iOS HIG + Material 3 spirit.
 */

export const colors = {
  // Backgrounds
  bg: '#0f172a',
  bgElevated: '#1e293b',
  bgCard: '#1e293b',
  bgInput: '#0b1220',

  // Surfaces / borders
  border: '#334155',
  borderMuted: '#475569',
  divider: '#1f2a44',

  // Text
  text: '#f8fafc',
  textMuted: '#cbd5e1',
  textDim: '#94a3b8',
  textInverse: '#0f172a',

  // Brand / actions
  primary: '#3b82f6',
  primaryDark: '#2563eb',
  primaryLight: '#60a5fa',

  // Status / feedback
  success: '#10b981',
  warning: '#F97316',
  danger: '#DC2626',
  info: '#0ea5e9',

  // Severity palette (project canonical)
  severityHafif: '#FBBF24',
  severityOrta: '#F97316',
  severityAgir: '#DC2626',

  // Misc
  overlay: 'rgba(0,0,0,0.55)',
  shadow: 'rgba(0,0,0,0.25)',
  transparent: 'transparent',
} as const;

export const spacing = {
  xxs: 2,
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  xxl: 24,
  xxxl: 32,
  huge: 48,
} as const;

export const radius = {
  sm: 6,
  md: 10,
  lg: 14,
  xl: 20,
  pill: 999,
} as const;

export const typography = {
  display: { fontSize: 32, fontWeight: '700' as const, lineHeight: 38 },
  h1: { fontSize: 26, fontWeight: '700' as const, lineHeight: 32 },
  h2: { fontSize: 22, fontWeight: '600' as const, lineHeight: 28 },
  h3: { fontSize: 18, fontWeight: '600' as const, lineHeight: 24 },
  body: { fontSize: 16, fontWeight: '400' as const, lineHeight: 22 },
  bodyBold: { fontSize: 16, fontWeight: '600' as const, lineHeight: 22 },
  caption: { fontSize: 13, fontWeight: '400' as const, lineHeight: 18 },
  label: { fontSize: 13, fontWeight: '600' as const, lineHeight: 18 },
  small: { fontSize: 11, fontWeight: '500' as const, lineHeight: 14 },
} as const;

export const shadows = {
  card: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.18,
    shadowRadius: 6,
    elevation: 3,
  },
  modal: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.32,
    shadowRadius: 16,
    elevation: 12,
  },
} as const;

export const severityColor = (level: 'hafif' | 'orta' | 'agir' | string): string => {
  switch (level) {
    case 'hafif':
      return colors.severityHafif;
    case 'orta':
      return colors.severityOrta;
    case 'agir':
      return colors.severityAgir;
    default:
      return colors.textMuted;
  }
};

export const theme = {
  colors,
  spacing,
  radius,
  typography,
  shadows,
  severityColor,
};

export default theme;
