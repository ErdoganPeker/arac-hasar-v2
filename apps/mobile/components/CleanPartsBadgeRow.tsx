/**
 * components/CleanPartsBadgeRow.tsx — Hasarsız parça rozetleri
 *
 * Hasarsız parçaları kompakt yeşil rozetler halinde gösterir.
 * "Kontrol edildi, temiz" güvencesi verir.
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

interface CleanPartsBadgeRowProps {
  parts: Array<{ name: string; name_tr: string }>;
}

export const CleanPartsBadgeRow: React.FC<CleanPartsBadgeRowProps> = ({ parts }) => {
  if (parts.length === 0) return null;

  return (
    <View style={styles.container}>
      <View style={styles.badgesWrapper}>
        {parts.map((p, i) => (
          <View key={i} style={styles.badge}>
            <Text style={styles.checkmark}>✓</Text>
            <Text style={styles.badgeText}>{p.name_tr}</Text>
          </View>
        ))}
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    marginHorizontal: 12,
    marginBottom: 16,
    padding: 14,
    backgroundColor: '#fff',
    borderRadius: 12,
    borderWidth: 0.5,
    borderColor: 'rgba(0,0,0,0.08)',
  },
  badgesWrapper: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#E1F5EE',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 8,
    gap: 4,
  },
  checkmark: {
    color: '#0F6E56',
    fontSize: 12,
    fontWeight: 'bold',
  },
  badgeText: {
    color: '#0F6E56',
    fontSize: 12,
    fontWeight: '500',
  },
});
