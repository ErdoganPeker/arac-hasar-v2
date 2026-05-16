import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { DAMAGE_TYPE_TR, Damage } from '@arac-hasar/types';
import { colors, radius, spacing, typography } from '../theme';
import SeverityBadge from './SeverityBadge';
import CostText from './CostText';

interface Props {
  damage: Damage;
}

export default function DamageRow({ damage }: Props) {
  const typeLabel =
    damage.type_tr ||
    (DAMAGE_TYPE_TR as Record<string, string>)[damage.type as string] ||
    damage.type;
  const confidencePct = Math.round((damage.confidence ?? 0) * 100);

  return (
    <View style={styles.row}>
      <View style={styles.topRow}>
        <Text style={styles.title}>{typeLabel}</Text>
        <SeverityBadge level={damage.severity?.level} size="sm" />
      </View>
      <View style={styles.metaRow}>
        <Text style={styles.meta}>Güven: %{confidencePct}</Text>
        {damage.affected_parts && damage.affected_parts.length > 0 ? (
          <Text style={styles.meta} numberOfLines={1}>
            • {damage.affected_parts.join(', ')}
          </Text>
        ) : null}
      </View>
      <CostText
        min={damage.cost?.min_tl}
        max={damage.cost?.max_tl}
        midpoint={damage.cost?.midpoint_tl}
        inline
        style={styles.cost}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.sm,
    borderWidth: 1,
    borderColor: colors.divider,
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.xs,
  },
  title: {
    ...typography.bodyBold,
    color: colors.text,
    flex: 1,
    marginRight: spacing.sm,
  },
  metaRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
    marginBottom: spacing.xs,
  },
  meta: {
    ...typography.caption,
    color: colors.textMuted,
  },
  cost: {
    ...typography.bodyBold,
    color: colors.primaryLight,
    marginTop: spacing.xs,
  },
});
