/**
 * components/PartCard.tsx — Hasarlı parça kartı
 *
 * Bir parça ve onun içindeki tüm hasarları gösterir.
 * Her hasarı ayrı badge olarak render eder (orta, hafif gibi şiddet etiketiyle).
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

interface DamageItem {
  id: number;
  type: string;
  type_tr: string;
  severity: { level: string; level_tr: string };
  cost?: { min_tl: number; max_tl: number };
  is_multi_part?: boolean;
}

interface PartCardProps {
  part: {
    name: string;
    name_tr: string;
    status: string;
    damage_count: number;
    damages: DamageItem[];
    part_cost_min_tl: number;
    part_cost_max_tl: number;
    cost_note?: string;
  };
}

export const PartCard: React.FC<PartCardProps> = ({ part }) => {
  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <View>
          <Text style={styles.partName}>{part.name_tr}</Text>
          <Text style={styles.damageCount}>
            {part.damage_count} hasar tespit edildi
          </Text>
        </View>
        <View style={styles.priceWrapper}>
          <Text style={styles.priceRange}>
            ₺{formatTL(part.part_cost_min_tl)} – ₺{formatTL(part.part_cost_max_tl)}
          </Text>
          {part.cost_note && (
            <Text style={styles.costNote}>{part.cost_note}</Text>
          )}
        </View>
      </View>

      <View style={styles.damageBadges}>
        {part.damages.map((d) => (
          <View
            key={d.id}
            style={[styles.badge, severityStyle(d.severity.level)]}
          >
            <Text style={[styles.badgeText, severityTextStyle(d.severity.level)]}>
              {d.type_tr} • {d.severity.level_tr}
              {d.is_multi_part && ' ⚭'}
            </Text>
          </View>
        ))}
      </View>
    </View>
  );
};

function formatTL(n?: number) {
  if (n === undefined || n === null) return '—';
  return n.toLocaleString('tr-TR', { maximumFractionDigits: 0 });
}

function severityStyle(level: string) {
  const map: any = {
    'hafif': { backgroundColor: '#EAF3DE' },
    'orta':  { backgroundColor: '#FAEEDA' },
    'agir':  { backgroundColor: '#FCEBEB' },
  };
  return map[level] || { backgroundColor: '#f1f5f9' };
}

function severityTextStyle(level: string) {
  const map: any = {
    'hafif': { color: '#3B6D11' },
    'orta':  { color: '#854F0B' },
    'agir':  { color: '#791F1F' },
  };
  return map[level] || { color: '#0f172a' };
}

const styles = StyleSheet.create({
  card: {
    marginHorizontal: 12,
    marginBottom: 10,
    padding: 16,
    backgroundColor: '#fff',
    borderRadius: 12,
    borderWidth: 0.5,
    borderColor: 'rgba(0,0,0,0.08)',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  partName: {
    fontSize: 15,
    fontWeight: '500',
    color: '#0f172a',
  },
  damageCount: {
    fontSize: 12,
    color: '#64748b',
    marginTop: 2,
  },
  priceWrapper: {
    alignItems: 'flex-end',
  },
  priceRange: {
    fontSize: 14,
    fontWeight: '500',
    color: '#0f172a',
  },
  costNote: {
    fontSize: 10,
    color: '#94a3b8',
    marginTop: 2,
    textAlign: 'right',
    maxWidth: 140,
  },
  damageBadges: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  badge: {
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 8,
  },
  badgeText: {
    fontSize: 12,
    fontWeight: '500',
  },
});
