import React from 'react';
import { StyleSheet, Text, View, ViewStyle } from 'react-native';
import { SEVERITY_TR, SeverityLevel } from '@arac-hasar/types';
import { colors, radius, spacing, severityColor, typography } from '../theme';

interface Props {
  level: SeverityLevel | string | null | undefined;
  size?: 'sm' | 'md';
  style?: ViewStyle;
}

export default function SeverityBadge({ level, size = 'md', style }: Props) {
  if (!level) return null;
  const bg = severityColor(level);
  const label =
    (SEVERITY_TR as Record<string, string>)[level as string] ?? String(level);

  return (
    <View
      accessibilityRole="text"
      style={[
        styles.badge,
        { backgroundColor: bg },
        size === 'sm' && styles.badgeSm,
        style,
      ]}
    >
      <Text style={[styles.text, size === 'sm' && styles.textSm]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    alignSelf: 'flex-start',
    paddingHorizontal: spacing.md,
    paddingVertical: 4,
    borderRadius: radius.pill,
  },
  badgeSm: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  text: {
    ...typography.label,
    color: '#0f172a',
  },
  textSm: {
    ...typography.small,
    color: '#0f172a',
  },
});

// Re-export the color helper for callers that need it directly.
export { severityColor };
export { colors };
