import React from 'react';
import { StyleSheet, Text, TextStyle, View } from 'react-native';
import { colors, typography, spacing } from '../theme';

interface Props {
  min?: number | null;
  max?: number | null;
  midpoint?: number | null;
  label?: string;
  style?: TextStyle;
  inline?: boolean;
}

function fmt(value?: number | null): string {
  if (value == null) return '—';
  return new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 }).format(value);
}

export default function CostText({ min, max, midpoint, label, style, inline }: Props) {
  const range = `${fmt(min)} – ${fmt(max)} ₺`;
  if (inline) {
    return <Text style={[styles.value, style]}>{range}</Text>;
  }
  return (
    <View>
      {label ? <Text style={styles.label}>{label}</Text> : null}
      <Text style={[styles.value, style]}>{range}</Text>
      {midpoint != null ? (
        <Text style={styles.midpoint}>~ {fmt(midpoint)} ₺</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  label: {
    ...typography.caption,
    color: colors.textMuted,
    marginBottom: spacing.xxs,
  },
  value: {
    ...typography.h3,
    color: colors.text,
  },
  midpoint: {
    ...typography.caption,
    color: colors.textDim,
    marginTop: spacing.xxs,
  },
});
