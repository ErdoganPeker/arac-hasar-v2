import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';

import { InspectionListItem, InspectionStatus } from '@arac-hasar/types';
import { MainScreenProps } from '../navigation/types';
import { api, describeError } from '../services/api';
import EmptyState from '../components/EmptyState';
import LoadingSpinner from '../components/LoadingSpinner';
import { colors, radius, spacing, typography } from '../theme';

type Props = MainScreenProps<'History'>;

const PAGE_SIZE = 20;

function statusLabel(t: (k: string) => string, s: InspectionStatus): string {
  switch (s) {
    case 'completed':
      return t('history:completed');
    case 'processing':
      return t('history:processing');
    case 'failed':
      return t('history:failed');
    case 'queued':
      return t('history:queued');
    default:
      return s;
  }
}

function statusColor(s: InspectionStatus): string {
  switch (s) {
    case 'completed':
      return colors.success;
    case 'processing':
    case 'queued':
      return colors.info;
    case 'failed':
      return colors.danger;
    default:
      return colors.textMuted;
  }
}

function fmtDate(iso: string, locale: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(locale, {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export default function HistoryScreen({ navigation }: Props) {
  const { t, i18n } = useTranslation(['history', 'common']);
  const locale = i18n.language || 'tr';

  const [items, setItems] = useState<InspectionListItem[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (targetPage = 1, replace = false) => {
      try {
        const res = await api.inspections.list({ page: targetPage, pageSize: PAGE_SIZE });
        setTotal(res.total ?? 0);
        setPage(targetPage);
        if (replace) {
          setItems(res.items ?? []);
        } else {
          setItems((prev) => [...prev, ...(res.items ?? [])]);
        }
      } catch (e) {
        setError(describeError(e));
      }
    },
    [],
  );

  useEffect(() => {
    (async () => {
      setLoading(true);
      await load(1, true);
      setLoading(false);
    })();
  }, [load]);

  const handleRefresh = async () => {
    setRefreshing(true);
    setError(null);
    await load(1, true);
    setRefreshing(false);
  };

  const handleEndReached = async () => {
    if (loadingMore) return;
    if (items.length >= total) return;
    setLoadingMore(true);
    await load(page + 1, false);
    setLoadingMore(false);
  };

  if (loading) {
    return (
      <SafeAreaView style={styles.safe}>
        <LoadingSpinner fullscreen />
      </SafeAreaView>
    );
  }

  if (items.length === 0) {
    return (
      <SafeAreaView style={styles.safe} edges={['bottom']}>
        <EmptyState
          title={t('history:empty')}
          description={error ? error : t('history:emptyDescription')}
          actionLabel={t('history:newInspection')}
          onAction={() => navigation.navigate('Camera')}
        />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <FlatList
        data={items}
        keyExtractor={(it) => it.inspection_id}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={handleRefresh}
            tintColor={colors.primaryLight}
            colors={[colors.primaryLight]}
          />
        }
        onEndReached={handleEndReached}
        onEndReachedThreshold={0.4}
        ListFooterComponent={
          loadingMore ? (
            <View style={{ paddingVertical: spacing.lg }}>
              <ActivityIndicator color={colors.primaryLight} />
            </View>
          ) : null
        }
        renderItem={({ item }) => (
          <Pressable
            accessibilityRole="button"
            onPress={() =>
              navigation.navigate('InspectionDetail', { inspectionId: item.inspection_id })
            }
            style={({ pressed }) => [styles.row, pressed && styles.rowPressed]}
          >
            <View style={styles.rowMain}>
              <Text style={styles.rowDate}>{fmtDate(item.created_at, locale)}</Text>
              <Text style={styles.rowMeta}>
                {t('history:damageCount', { count: item.damage_count })}
                {item.total_cost_midpoint_tl
                  ? ` • ${Math.round(item.total_cost_midpoint_tl).toLocaleString(locale)} ₺`
                  : ''}
              </Text>
            </View>
            <View
              style={[
                styles.statusPill,
                { backgroundColor: statusColor(item.status) + '22', borderColor: statusColor(item.status) },
              ]}
            >
              <Text style={[styles.statusText, { color: statusColor(item.status) }]}>
                {statusLabel(t, item.status)}
              </Text>
            </View>
          </Pressable>
        )}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  list: { padding: spacing.lg },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.sm,
    borderWidth: 1,
    borderColor: colors.divider,
  },
  rowPressed: { opacity: 0.85 },
  rowMain: { flex: 1, marginRight: spacing.md },
  rowDate: { ...typography.bodyBold, color: colors.text },
  rowMeta: { ...typography.caption, color: colors.textMuted, marginTop: spacing.xxs },
  statusPill: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: radius.pill,
    borderWidth: 1,
  },
  statusText: { ...typography.small, fontWeight: '700' },
});
