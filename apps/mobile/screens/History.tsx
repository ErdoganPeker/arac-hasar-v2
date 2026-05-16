/**
 * Legacy History screen — superseded by HistoryScreen.tsx (registered in MainStack).
 * Kept for backwards compatibility with older deep links; uses the shared
 * MainStackParamList from navigation/types and the active "InspectionDetail" route.
 */
import { useEffect, useState } from 'react';
import { View, Text, FlatList, Pressable, StyleSheet, ActivityIndicator } from 'react-native';
import type { InspectionListItem } from '@arac-hasar/types';
import type { MainScreenProps } from '../navigation/types';
import { api } from '../services/api';

type Props = MainScreenProps<'History'>;

export default function History({ navigation }: Props) {
  const [items, setItems] = useState<InspectionListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listInspections()
      .then((res) => setItems(res.items))
      .catch((e) => setError(e instanceof Error ? e.message : 'Hata'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#3b82f6" />
      </View>
    );
  }

  if (error) {
    return (
      <View style={styles.center}>
        <Text style={styles.errorText}>Yüklenemedi: {error}</Text>
      </View>
    );
  }

  if (items.length === 0) {
    return (
      <View style={styles.center}>
        <Text style={styles.emptyText}>Henüz inceleme yok.</Text>
      </View>
    );
  }

  return (
    <FlatList
      style={styles.container}
      data={items}
      keyExtractor={(it) => it.inspection_id}
      renderItem={({ item }) => (
        <Pressable
          style={styles.card}
          onPress={() => navigation.navigate('InspectionDetail', { inspectionId: item.inspection_id })}
        >
          <Text style={styles.cardDate}>
            {new Date(item.created_at).toLocaleString('tr-TR')}
          </Text>
          <View style={styles.row}>
            <Text style={styles.cardLabel}>{item.damage_count} hasar</Text>
            {item.total_cost_midpoint_tl !== undefined && (
              <Text style={styles.cardCost}>
                {item.total_cost_midpoint_tl.toLocaleString('tr-TR')} ₺
              </Text>
            )}
          </View>
        </Pressable>
      )}
    />
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0f172a' },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
    backgroundColor: '#0f172a',
  },
  card: {
    backgroundColor: '#1e293b',
    margin: 12,
    padding: 16,
    borderRadius: 12,
  },
  cardDate: { color: '#cbd5e1', fontSize: 14 },
  row: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 8 },
  cardLabel: { color: '#fff', fontWeight: '600' },
  cardCost: { color: '#60a5fa', fontWeight: '700' },
  emptyText: { color: '#94a3b8', fontSize: 16 },
  errorText: { color: '#ef4444', fontSize: 14 },
});
