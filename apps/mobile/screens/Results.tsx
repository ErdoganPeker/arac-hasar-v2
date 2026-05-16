/**
 * screens/Results.tsx — v2 Parça-merkezli sonuç ekranı
 *
 * Yapı:
 *   - Üst: özet metrikleri (toplam parça, hasarlı, maliyet)
 *   - 3 tab: Annotated / Parçalar / Hasarlar
 *   - Hasarlı parçaların kartları (her parça içinde hasar badge'leri)
 *   - Hasarsız parçaların yeşil rozet satırı
 */
import React, { useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, ActivityIndicator,
  TouchableOpacity, Image, Dimensions,
} from 'react-native';
import { useRoute, useNavigation } from '@react-navigation/native';

import { api } from '../services/api';
import { PartCard } from '../components/PartCard';
import { CleanPartsBadgeRow } from '../components/CleanPartsBadgeRow';

const POLL_INTERVAL_MS = 2500;
const MAX_POLL_ATTEMPTS = 30;
const { width: SCREEN_W } = Dimensions.get('window');

type VisualTab = 'annotated' | 'parts' | 'damages';

interface PartCentricResult {
  inspection_id: string;
  image: { url: string; width: number; height: number };
  parts: any[];
  summary: any;
  visualization_urls?: {
    annotated_image?: string;
    parts_overlay?: string;
    damages_overlay?: string;
  };
}

export default function Results() {
  const route = useRoute<any>();
  const navigation = useNavigation<any>();
  const { inspectionId } = route.params;

  const [result, setResult] = useState<PartCentricResult | null>(null);
  const [status, setStatus] = useState<string>('queued');
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [activeTab, setActiveTab] = useState<VisualTab>('annotated');

  useEffect(() => {
    let cancelled = false;
    let timer: any;

    const poll = async () => {
      try {
        const data = await api.getInspection(inspectionId);
        if (cancelled) return;

        setStatus(data.status);
        setAttempt(a => a + 1);

        if (data.status === 'completed') {
          if (data.result) {
            setResult(data.result as unknown as PartCentricResult);
          } else {
            setError('Sonuç boş döndü');
          }
        } else if (data.status === 'failed') {
          setError(data.error || 'Bilinmeyen hata');
        } else if (attempt < MAX_POLL_ATTEMPTS) {
          timer = setTimeout(poll, POLL_INTERVAL_MS);
        } else {
          setError('Zaman aşımı');
        }
      } catch (err: any) {
        if (!cancelled) setError(err.message);
      }
    };

    poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [inspectionId]);

  if (error) {
    return (
      <View style={styles.center}>
        <Text style={styles.errorText}>❌ {error}</Text>
        <TouchableOpacity style={styles.button} onPress={() => navigation.navigate('Home' as never)}>
          <Text style={styles.buttonText}>Ana sayfa</Text>
        </TouchableOpacity>
      </View>
    );
  }

  if (!result) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#3b82f6" />
        <Text style={styles.statusText}>
          {status === 'queued' ? 'Sırada bekliyor...' :
           status === 'processing' ? 'İnceleme yapılıyor...' :
           'Yükleniyor...'}
        </Text>
        <Text style={styles.attemptText}>{attempt}/{MAX_POLL_ATTEMPTS}</Text>
      </View>
    );
  }

  const summary = result.summary || {};
  const parts = result.parts || [];
  const damagedParts = parts.filter((p: any) => p.status !== 'clean');
  const cleanParts = parts.filter((p: any) => p.status === 'clean');

  const visualUrl =
    activeTab === 'annotated' ? result.visualization_urls?.annotated_image :
    activeTab === 'parts' ? result.visualization_urls?.parts_overlay :
    result.visualization_urls?.damages_overlay;

  return (
    <ScrollView style={styles.container}>
      {/* Üst özet */}
      <View style={styles.summaryCard}>
        <Text style={styles.summaryLabel}>İnceleme özeti</Text>
        <Text style={styles.summarySubtitle}>
          {summary.damaged_parts_count} parçada hasar — toplam {summary.total_damage_count} hasar
        </Text>
        <Text style={styles.priceRange}>
          ₺{formatTL(summary.total_cost_range_tl?.[0])} – ₺{formatTL(summary.total_cost_range_tl?.[1])}
        </Text>
        <Text style={styles.metaLine}>
          {summary.repair_recommendation_tr} • {summary.estimated_repair_days} gün
        </Text>
      </View>

      {/* Mini metrikler */}
      <View style={styles.metricsRow}>
        <View style={styles.metricCard}>
          <Text style={styles.metricLabel}>İncelenen parça</Text>
          <Text style={styles.metricValue}>{summary.total_parts_inspected}</Text>
        </View>
        <View style={styles.metricCard}>
          <Text style={styles.metricLabel}>Hasarlı parça</Text>
          <Text style={[styles.metricValue, { color: '#f59e0b' }]}>
            {summary.damaged_parts_count}
          </Text>
        </View>
      </View>

      {/* Görsel tabları */}
      {result.visualization_urls && (
        <View style={styles.visualSection}>
          <View style={styles.tabRow}>
            {[
              { id: 'annotated', label: 'Tümü' },
              { id: 'parts', label: 'Parçalar' },
              { id: 'damages', label: 'Hasarlar' },
            ].map((tab: any) => (
              <TouchableOpacity
                key={tab.id}
                style={[styles.tab, activeTab === tab.id && styles.tabActive]}
                onPress={() => setActiveTab(tab.id)}
              >
                <Text style={[
                  styles.tabText,
                  activeTab === tab.id && styles.tabTextActive,
                ]}>
                  {tab.label}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
          {visualUrl && (
            <Image
              source={{ uri: visualUrl }}
              style={styles.visualImage}
              resizeMode="contain"
            />
          )}
        </View>
      )}

      {/* Hasarlı parçalar */}
      {damagedParts.length > 0 && (
        <>
          <Text style={styles.sectionTitle}>Hasarlı parçalar</Text>
          {damagedParts.map((p: any, i: number) => (
            <PartCard key={i} part={p} />
          ))}
        </>
      )}

      {/* Hasarsız parçalar */}
      {cleanParts.length > 0 && (
        <>
          <Text style={styles.sectionTitle}>Hasarsız parçalar</Text>
          <CleanPartsBadgeRow parts={cleanParts} />
        </>
      )}

      {/* Edge case uyarıları */}
      {summary.unknown_part_damages_count > 0 && (
        <View style={styles.warningCard}>
          <Text style={styles.warningTitle}>⚠ Atanamayan hasarlar</Text>
          <Text style={styles.warningText}>
            {summary.unknown_part_damages_count} hasar bir parçaya kesin atanamadı — daha yakın bir fotoğraf yardımcı olabilir.
          </Text>
        </View>
      )}

      {summary.multi_part_damages_count > 0 && (
        <View style={styles.infoCard}>
          <Text style={styles.infoTitle}>ℹ Birden fazla parçaya yayılan hasar</Text>
          <Text style={styles.infoText}>
            {summary.multi_part_damages_count} hasar birden fazla parçayı etkiliyor.
          </Text>
        </View>
      )}

      <TouchableOpacity style={styles.button} onPress={() => navigation.popToTop()}>
        <Text style={styles.buttonText}>Yeni İnceleme</Text>
      </TouchableOpacity>
    </ScrollView>
  );
}

function formatTL(n?: number) {
  if (n === undefined || n === null) return '—';
  return n.toLocaleString('tr-TR', { maximumFractionDigits: 0 });
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f1f5f9' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 20 },
  statusText: { marginTop: 16, fontSize: 16, color: '#475569' },
  attemptText: { marginTop: 8, fontSize: 12, color: '#94a3b8' },
  errorText: { fontSize: 16, color: '#dc2626', marginBottom: 20, textAlign: 'center' },

  summaryCard: {
    margin: 12, padding: 18, backgroundColor: '#fff', borderRadius: 14,
  },
  summaryLabel: { fontSize: 12, color: '#94a3b8' },
  summarySubtitle: { fontSize: 14, color: '#475569', marginTop: 2 },
  priceRange: { fontSize: 30, fontWeight: 'bold', color: '#0f172a', marginTop: 10 },
  metaLine: { fontSize: 12, color: '#94a3b8', marginTop: 6 },

  metricsRow: {
    flexDirection: 'row',
    marginHorizontal: 12,
    gap: 8,
    marginBottom: 16,
  },
  metricCard: {
    flex: 1,
    backgroundColor: '#fff',
    padding: 12,
    borderRadius: 10,
  },
  metricLabel: { fontSize: 11, color: '#94a3b8' },
  metricValue: { fontSize: 22, fontWeight: 'bold', color: '#0f172a', marginTop: 4 },

  visualSection: { marginHorizontal: 12, marginBottom: 16 },
  tabRow: {
    flexDirection: 'row',
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 4,
    marginBottom: 10,
  },
  tab: {
    flex: 1,
    padding: 10,
    borderRadius: 6,
    alignItems: 'center',
  },
  tabActive: { backgroundColor: '#0f172a' },
  tabText: { fontSize: 13, color: '#64748b' },
  tabTextActive: { color: '#fff', fontWeight: '500' },
  visualImage: {
    width: SCREEN_W - 24,
    height: (SCREEN_W - 24) * 0.66,
    borderRadius: 8,
    backgroundColor: '#e2e8f0',
  },

  sectionTitle: {
    fontSize: 14, fontWeight: '500',
    color: '#0f172a',
    marginHorizontal: 16, marginTop: 16, marginBottom: 8,
  },

  warningCard: {
    margin: 12, padding: 12,
    backgroundColor: '#fef3c7',
    borderRadius: 10,
  },
  warningTitle: { fontSize: 13, fontWeight: '500', color: '#854F0B' },
  warningText: { fontSize: 12, color: '#854F0B', marginTop: 4 },

  infoCard: {
    margin: 12, padding: 12,
    backgroundColor: '#dbeafe',
    borderRadius: 10,
  },
  infoTitle: { fontSize: 13, fontWeight: '500', color: '#1e40af' },
  infoText: { fontSize: 12, color: '#1e40af', marginTop: 4 },

  button: {
    margin: 16, padding: 14,
    backgroundColor: '#3b82f6',
    borderRadius: 10,
    alignItems: 'center',
  },
  buttonText: { color: '#fff', fontWeight: 'bold', fontSize: 16 },
});
