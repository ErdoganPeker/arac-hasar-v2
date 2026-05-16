import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Image,
  LayoutChangeEvent,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';

import {
  Damage,
  Inspection,
  InspectionStatusResponse,
  PART_TR,
  REPAIR_RECOMMENDATION_TR,
} from '@arac-hasar/types';

import { MainScreenProps } from '../navigation/types';
import { api, describeError } from '../services/api';
import LoadingSpinner from '../components/LoadingSpinner';
import SeverityBadge from '../components/SeverityBadge';
import DamageRow from '../components/DamageRow';
import CostText from '../components/CostText';
import MaskOverlay from '../components/MaskOverlay';
import UploadButton from '../components/UploadButton';
import { colors, radius, spacing, typography } from '../theme';

type Props = MainScreenProps<'Result'>;

const POLL_INTERVAL_MS = 2_000;
const POLL_MAX_ATTEMPTS = 60; // 2 minutes

export default function ResultScreen({ navigation, route }: Props) {
  const { t } = useTranslation(['inspect', 'history', 'common']);
  const inspectionId = route.params.inspectionId;

  const [status, setStatus] = useState<InspectionStatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [imageLayout, setImageLayout] = useState<{ w: number; h: number }>({ w: 0, h: 0 });
  const attemptsRef = useRef(0);
  const stoppedRef = useRef(false);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await api.inspections.get(inspectionId);
      setStatus(res);
      return res;
    } catch (e) {
      setError(describeError(e));
      return null;
    }
  }, [inspectionId]);

  useEffect(() => {
    stoppedRef.current = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      if (stoppedRef.current) return;
      attemptsRef.current += 1;
      const res = await fetchStatus();
      if (stoppedRef.current) return;
      if (res?.status === 'completed' || res?.status === 'failed') return;
      if (attemptsRef.current >= POLL_MAX_ATTEMPTS) return;
      timer = setTimeout(tick, POLL_INTERVAL_MS);
    };

    tick();
    return () => {
      stoppedRef.current = true;
      if (timer) clearTimeout(timer);
    };
  }, [fetchStatus]);

  const result: Inspection | undefined = status?.result;
  const isProcessing =
    !status || status.status === 'queued' || status.status === 'processing';

  const damages: Damage[] = useMemo(() => {
    if (!result) return [];
    const all: Damage[] = [];
    for (const p of result.parts ?? []) all.push(...(p.damages ?? []));
    all.push(...(result.multi_part_damages ?? []));
    all.push(...(result.unassigned_damages ?? []));
    return all;
  }, [result]);

  const imageUri = useMemo(() => {
    if (!result) return null;
    if (result.image?.url) return result.image.url;
    // Fallback to annotated visualization endpoint.
    return api.inspections.visualizationUrl(inspectionId, 'annotated');
  }, [result, inspectionId]);

  const onImageLayout = (e: LayoutChangeEvent) => {
    const { width } = e.nativeEvent.layout;
    if (!result?.image) return;
    const ratio = result.image.height / Math.max(1, result.image.width);
    setImageLayout({ w: width, h: width * ratio });
  };

  if (error && !result) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.center}>
          <Text style={styles.error}>{t('inspect:fetchFailed')}</Text>
          <UploadButton
            label={t('common:retry')}
            variant="secondary"
            onPress={() => {
              setError(null);
              attemptsRef.current = 0;
              fetchStatus();
            }}
            style={{ marginTop: spacing.lg }}
          />
        </View>
      </SafeAreaView>
    );
  }

  if (isProcessing) {
    return (
      <SafeAreaView style={styles.safe} edges={['bottom']}>
        <View style={styles.center}>
          <LoadingSpinner label={t('inspect:processing')} />
          <Text style={styles.processingDesc}>{t('inspect:processingDescription')}</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (status?.status === 'failed') {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.center}>
          <Text style={styles.error}>{status.error || t('inspect:fetchFailed')}</Text>
          <UploadButton
            label={t('common:back')}
            variant="secondary"
            onPress={() => navigation.goBack()}
            style={{ marginTop: spacing.lg }}
          />
        </View>
      </SafeAreaView>
    );
  }

  if (!result) {
    return (
      <SafeAreaView style={styles.safe}>
        <LoadingSpinner fullscreen />
      </SafeAreaView>
    );
  }

  const s = result.summary;
  const repairLabel =
    s.repair_recommendation_tr ||
    REPAIR_RECOMMENDATION_TR[s.repair_recommendation] ||
    s.repair_recommendation;

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.scroll}>
        {/* Image with overlay */}
        {imageUri ? (
          <View style={styles.imageWrap} onLayout={onImageLayout}>
            <Image
              source={{ uri: imageUri }}
              style={[styles.image, { height: imageLayout.h || 220 }]}
              resizeMode="contain"
            />
            {imageLayout.w > 0 && imageLayout.h > 0 ? (
              <MaskOverlay
                width={imageLayout.w}
                height={imageLayout.h}
                damages={damages}
                showDamages
              />
            ) : null}
          </View>
        ) : null}

        {/* Summary card */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>{t('inspect:summary')}</Text>
          <View style={styles.statsRow}>
            <Stat
              label={t('inspect:totalDamages')}
              value={String(s.total_damage_count ?? damages.length)}
            />
            <Stat label={t('inspect:damagedParts')} value={String(s.damaged_parts_count)} />
            <Stat label={t('inspect:cleanParts')} value={String(s.clean_parts_count)} />
          </View>

          <View style={styles.severityRow}>
            <Text style={styles.cardLabel}>{t('inspect:mostSevere')}</Text>
            <SeverityBadge level={s.most_severe_level} />
          </View>

          <View style={styles.divider} />

          <CostText
            label={t('inspect:estimatedCost')}
            min={s.total_cost_range_tl?.[0]}
            max={s.total_cost_range_tl?.[1]}
            midpoint={s.total_cost_midpoint_tl}
          />

          <View style={styles.recoBox}>
            <Text style={styles.cardLabel}>{t('inspect:repairRecommendation')}</Text>
            <Text style={styles.recoText}>{repairLabel}</Text>
            <Text style={styles.recoDays}>
              {t('inspect:estimatedDays', { days: s.estimated_repair_days })}
            </Text>
          </View>
        </View>

        {/* Damages list */}
        <Text style={styles.section}>{t('inspect:damagesList')}</Text>
        {damages.length === 0 ? (
          <View style={styles.emptyDamages}>
            <Text style={styles.emptyDamagesText}>{t('inspect:noDamages')}</Text>
          </View>
        ) : (
          damages.map((d, i) => <DamageRow key={`${d.id}-${i}`} damage={d} />)
        )}

        {/* Parts list */}
        {result.parts?.length ? (
          <>
            <Text style={styles.section}>{t('inspect:partsList')}</Text>
            {result.parts.map((p, i) => {
              const partName =
                p.name_tr || (PART_TR as Record<string, string>)[p.name] || p.name;
              return (
                <View key={`${p.name}-${i}`} style={styles.partRow}>
                  <Text style={styles.partName}>{partName}</Text>
                  <Text style={styles.partMeta}>
                    {p.damage_count > 0
                      ? t('history:damageCount', { count: p.damage_count })
                      : t('inspect:noDamages')}
                  </Text>
                </View>
              );
            })}
          </>
        ) : null}

        <Pressable
          onPress={() => navigation.navigate('History')}
          style={({ pressed }) => [styles.linkBtn, pressed && styles.linkBtnPressed]}
        >
          <Text style={styles.linkText}>{t('inspect:saveToHistory')} ›</Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel} numberOfLines={1}>
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xxl, paddingBottom: spacing.huge },
  center: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xxl,
    backgroundColor: colors.bg,
  },
  processingDesc: {
    ...typography.body,
    color: colors.textMuted,
    textAlign: 'center',
    marginTop: spacing.md,
  },
  error: {
    ...typography.body,
    color: colors.danger,
    textAlign: 'center',
  },

  imageWrap: {
    width: '100%',
    backgroundColor: '#000',
    borderRadius: radius.lg,
    overflow: 'hidden',
    marginBottom: spacing.lg,
    position: 'relative',
  },
  image: { width: '100%' },

  card: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.lg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.divider,
    marginBottom: spacing.lg,
  },
  cardTitle: { ...typography.h3, color: colors.text, marginBottom: spacing.md },
  cardLabel: { ...typography.caption, color: colors.textMuted, marginBottom: spacing.xxs },

  statsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: spacing.md,
  },
  stat: { flex: 1, alignItems: 'center' },
  statValue: { ...typography.h1, color: colors.primaryLight },
  statLabel: { ...typography.caption, color: colors.textMuted, marginTop: spacing.xxs },

  severityRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.md,
  },

  divider: {
    height: 1,
    backgroundColor: colors.divider,
    marginVertical: spacing.sm,
  },

  recoBox: { marginTop: spacing.md },
  recoText: { ...typography.bodyBold, color: colors.text },
  recoDays: { ...typography.caption, color: colors.textMuted, marginTop: spacing.xxs },

  section: {
    ...typography.h3,
    color: colors.text,
    marginTop: spacing.md,
    marginBottom: spacing.sm,
  },

  emptyDamages: {
    padding: spacing.xl,
    borderRadius: radius.md,
    backgroundColor: colors.bgCard,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.divider,
  },
  emptyDamagesText: { ...typography.body, color: colors.textMuted, textAlign: 'center' },

  partRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    backgroundColor: colors.bgCard,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
    marginBottom: 6,
    borderWidth: 1,
    borderColor: colors.divider,
  },
  partName: { ...typography.body, color: colors.text },
  partMeta: { ...typography.caption, color: colors.textMuted },

  linkBtn: {
    marginTop: spacing.xl,
    alignSelf: 'center',
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.lg,
  },
  linkBtnPressed: { opacity: 0.7 },
  linkText: { ...typography.bodyBold, color: colors.primaryLight },
});
