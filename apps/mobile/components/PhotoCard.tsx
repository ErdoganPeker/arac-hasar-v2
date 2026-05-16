import React from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { colors, radius, spacing, typography } from '../theme';

interface Props {
  uri: string;
  index: number;
  onRemove?: () => void;
}

export default function PhotoCard({ uri, index, onRemove }: Props) {
  return (
    <View style={styles.wrap}>
      <Image source={{ uri }} style={styles.image} resizeMode="cover" />
      <View style={styles.indexBadge}>
        <Text style={styles.indexText}>{index + 1}</Text>
      </View>
      {onRemove ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="remove"
          style={({ pressed }) => [styles.removeBtn, pressed && styles.pressed]}
          onPress={onRemove}
          hitSlop={8}
        >
          <Text style={styles.removeText}>×</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const SIZE = 88;
const styles = StyleSheet.create({
  wrap: {
    width: SIZE,
    height: SIZE,
    borderRadius: radius.md,
    overflow: 'hidden',
    marginRight: spacing.sm,
    backgroundColor: colors.bgElevated,
    borderWidth: 1,
    borderColor: colors.divider,
  },
  image: {
    width: '100%',
    height: '100%',
  },
  indexBadge: {
    position: 'absolute',
    left: 4,
    top: 4,
    backgroundColor: colors.overlay,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: radius.sm,
  },
  indexText: {
    ...typography.small,
    color: colors.text,
  },
  removeBtn: {
    position: 'absolute',
    right: 4,
    top: 4,
    width: 22,
    height: 22,
    borderRadius: 11,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(220,38,38,0.92)',
  },
  removeText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '700',
    lineHeight: 18,
  },
  pressed: { opacity: 0.7 },
});
