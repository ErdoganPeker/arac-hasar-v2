import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';

import { MainScreenProps } from '../navigation/types';
import { useAuth } from '../services/AuthContext';
import UploadButton from '../components/UploadButton';
import { colors, radius, spacing, typography, shadows } from '../theme';

type Props = MainScreenProps<'Home'>;

export default function HomeScreen({ navigation }: Props) {
  const { t } = useTranslation(['dashboard', 'inspect', 'common']);
  const { user } = useAuth();

  const greeting = user?.full_name?.split(' ')[0] || user?.email?.split('@')[0] || '';

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <View style={styles.header}>
          <View style={{ flex: 1 }}>
            <Text style={styles.greeting}>
              {t('dashboard:greeting')}
              {greeting ? `, ${greeting}` : ''} 👋
            </Text>
            <Text style={styles.tagline}>{t('dashboard:tagline')}</Text>
          </View>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t('dashboard:quickActionSettings')}
            onPress={() => navigation.navigate('Settings')}
            style={styles.iconButton}
            hitSlop={8}
          >
            <Text style={styles.iconButtonText}>⚙</Text>
          </Pressable>
        </View>

        <UploadButton
          label={t('dashboard:quickActionNewInspection')}
          icon="📸"
          onPress={() => navigation.navigate('Camera')}
          style={styles.cta}
        />

        <View style={styles.row}>
          <Pressable
            accessibilityRole="button"
            onPress={() => navigation.navigate('History')}
            style={({ pressed }) => [styles.tile, pressed && styles.tilePressed]}
          >
            <Text style={styles.tileIcon}>🗂️</Text>
            <Text style={styles.tileTitle}>{t('dashboard:quickActionHistory')}</Text>
          </Pressable>

          <Pressable
            accessibilityRole="button"
            onPress={() => navigation.navigate('Upload')}
            style={({ pressed }) => [styles.tile, pressed && styles.tilePressed]}
          >
            <Text style={styles.tileIcon}>🖼️</Text>
            <Text style={styles.tileTitle}>{t('inspect:openGallery', { defaultValue: 'Galeri' })}</Text>
          </Pressable>
        </View>

        <View style={styles.tipsCard}>
          <Text style={styles.tipsTitle}>{t('dashboard:tipsTitle')}</Text>
          <Text style={styles.tipItem}>• {t('dashboard:tip1')}</Text>
          <Text style={styles.tipItem}>• {t('dashboard:tip2')}</Text>
          <Text style={styles.tipItem}>• {t('dashboard:tip3')}</Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xxl, paddingBottom: spacing.huge },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.xxl,
  },
  greeting: { ...typography.h2, color: colors.text },
  tagline: { ...typography.body, color: colors.textMuted, marginTop: spacing.xs },
  iconButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.bgElevated,
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: spacing.md,
  },
  iconButtonText: { color: colors.text, fontSize: 20 },
  cta: { marginBottom: spacing.xl },
  row: {
    flexDirection: 'row',
    gap: spacing.md,
    marginBottom: spacing.xl,
  },
  tile: {
    flex: 1,
    aspectRatio: 1.4,
    backgroundColor: colors.bgCard,
    borderRadius: radius.lg,
    padding: spacing.lg,
    justifyContent: 'space-between',
    borderWidth: 1,
    borderColor: colors.divider,
    ...shadows.card,
  },
  tilePressed: { opacity: 0.85 },
  tileIcon: { fontSize: 28 },
  tileTitle: { ...typography.bodyBold, color: colors.text },
  tipsCard: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.lg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.divider,
  },
  tipsTitle: { ...typography.h3, color: colors.text, marginBottom: spacing.sm },
  tipItem: { ...typography.body, color: colors.textMuted, marginBottom: spacing.xs },
});
