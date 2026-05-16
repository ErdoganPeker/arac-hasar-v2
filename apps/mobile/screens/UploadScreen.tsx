import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  FlatList,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import * as ImagePicker from 'expo-image-picker';
import * as ImageManipulator from 'expo-image-manipulator';

import { MainScreenProps } from '../navigation/types';
import { api, describeError } from '../services/api';
import UploadButton from '../components/UploadButton';
import PhotoCard from '../components/PhotoCard';
import { colors, radius, spacing, typography } from '../theme';

type Props = MainScreenProps<'Upload'>;

const MAX_PHOTOS = 8;
const MAX_WIDTH = 1600;
const COMPRESS_QUALITY = 0.85;

async function compress(uri: string): Promise<string> {
  try {
    const out = await ImageManipulator.manipulateAsync(
      uri,
      [{ resize: { width: MAX_WIDTH } }],
      { compress: COMPRESS_QUALITY, format: ImageManipulator.SaveFormat.JPEG },
    );
    return out.uri;
  } catch {
    return uri;
  }
}

export default function UploadScreen({ navigation, route }: Props) {
  const { t } = useTranslation(['inspect', 'common']);
  const initialPhotos = useMemo(() => route.params?.photos ?? [], [route.params?.photos]);
  const initialMode = route.params?.mode ?? 'async';

  const [photos, setPhotos] = useState<string[]>(initialPhotos);
  const [mode, setMode] = useState<'sync' | 'async'>(initialMode);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setPhotos(initialPhotos);
  }, [initialPhotos]);

  const pickFromGallery = useCallback(async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      Alert.alert(t('common:permissionDenied'));
      return;
    }
    const remaining = Math.max(0, MAX_PHOTOS - photos.length);
    if (remaining === 0) {
      Alert.alert(t('inspect:maxPhotosReached', { max: MAX_PHOTOS }));
      return;
    }
    const res = await ImagePicker.launchImageLibraryAsync({
      // SDK 52 prefers the new string-array form over MediaTypeOptions.Images.
      mediaTypes: ['images'],
      allowsMultipleSelection: true,
      quality: 0.9,
      selectionLimit: remaining,
    });
    if (res.canceled) return;
    const uris = (res.assets ?? []).map((a) => a.uri).slice(0, remaining);
    setPhotos((prev) => [...prev, ...uris]);
  }, [photos.length, t]);

  const remove = (idx: number) => {
    setPhotos((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleSubmit = useCallback(async () => {
    if (photos.length === 0) {
      setError(t('inspect:needAtLeastOne'));
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const compressed = await Promise.all(photos.map((u) => compress(u)));
      if (mode === 'sync') {
        const res = await api.inspections.createSync(compressed[0]);
        navigation.replace('Result', { inspectionId: res.inspection_id });
      } else {
        const res = await api.inspections.createAsync(compressed);
        navigation.replace('Result', { inspectionId: res.inspection_id });
      }
    } catch (e) {
      const msg = describeError(e);
      setError(msg === 'networkError' ? t('common:networkError') : t('inspect:uploadFailed'));
    } finally {
      setSubmitting(false);
    }
  }, [photos, mode, navigation, t]);

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.section}>{t('inspect:reviewTitle')}</Text>

        {photos.length > 0 ? (
          <FlatList
            data={photos}
            keyExtractor={(uri, idx) => `${uri}-${idx}`}
            renderItem={({ item, index }) => (
              <PhotoCard uri={item} index={index} onRemove={() => remove(index)} />
            )}
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.photoRow}
          />
        ) : (
          <Pressable
            style={styles.dropzone}
            onPress={pickFromGallery}
            accessibilityRole="button"
          >
            <Text style={styles.dropzoneIcon}>🖼️</Text>
            <Text style={styles.dropzoneTitle}>{t('inspect:openGallery')}</Text>
            <Text style={styles.dropzoneHint}>
              {t('inspect:photoCount', { count: 0, max: MAX_PHOTOS })}
            </Text>
          </Pressable>
        )}

        <View style={styles.actionsRow}>
          <UploadButton
            label={t('inspect:openGallery')}
            icon="🖼️"
            variant="secondary"
            onPress={pickFromGallery}
            style={{ flex: 1 }}
          />
          <UploadButton
            label={t('inspect:addMorePhotos')}
            icon="📸"
            variant="secondary"
            onPress={() => navigation.navigate('Camera', { mode })}
            style={{ flex: 1 }}
          />
        </View>

        <Text style={styles.section}>{t('inspect:modeAsync')}</Text>
        <View style={styles.modeRow}>
          <ModeChip
            active={mode === 'async'}
            onPress={() => setMode('async')}
            title={t('inspect:modeAsync')}
            description={t('inspect:modeAsyncDescription')}
          />
          <ModeChip
            active={mode === 'sync'}
            onPress={() => setMode('sync')}
            title={t('inspect:modeSync')}
            description={t('inspect:modeSyncDescription')}
            disabled={photos.length > 1}
          />
        </View>

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <UploadButton
          label={submitting ? t('inspect:submitting') : t('inspect:submit')}
          icon="🚀"
          loading={submitting}
          onPress={handleSubmit}
          disabled={photos.length === 0}
          style={{ marginTop: spacing.xl }}
        />
      </ScrollView>
    </SafeAreaView>
  );
}

function ModeChip({
  active,
  onPress,
  title,
  description,
  disabled,
}: {
  active: boolean;
  onPress: () => void;
  title: string;
  description: string;
  disabled?: boolean;
}) {
  return (
    <Pressable
      onPress={disabled ? undefined : onPress}
      style={[
        styles.modeChip,
        active && styles.modeChipActive,
        disabled && styles.modeChipDisabled,
      ]}
      accessibilityRole="button"
      accessibilityState={{ selected: active, disabled }}
    >
      <Text style={[styles.modeTitle, active && styles.modeTitleActive]}>{title}</Text>
      <Text style={styles.modeDesc}>{description}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.xxl, paddingBottom: spacing.huge },

  section: {
    ...typography.h3,
    color: colors.text,
    marginTop: spacing.lg,
    marginBottom: spacing.sm,
  },

  photoRow: { paddingVertical: spacing.sm },

  dropzone: {
    height: 160,
    borderRadius: radius.lg,
    borderStyle: 'dashed',
    borderWidth: 1.5,
    borderColor: colors.borderMuted,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.bgCard,
  },
  dropzoneIcon: { fontSize: 32, marginBottom: spacing.xs },
  dropzoneTitle: { ...typography.bodyBold, color: colors.text },
  dropzoneHint: { ...typography.caption, color: colors.textMuted, marginTop: spacing.xxs },

  actionsRow: {
    flexDirection: 'row',
    gap: spacing.md,
    marginTop: spacing.lg,
  },

  modeRow: {
    flexDirection: 'row',
    gap: spacing.md,
  },
  modeChip: {
    flex: 1,
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.bgCard,
    borderWidth: 1,
    borderColor: colors.divider,
  },
  modeChipActive: {
    borderColor: colors.primary,
    backgroundColor: 'rgba(59,130,246,0.08)',
  },
  modeChipDisabled: { opacity: 0.4 },
  modeTitle: { ...typography.bodyBold, color: colors.text, marginBottom: spacing.xxs },
  modeTitleActive: { color: colors.primaryLight },
  modeDesc: { ...typography.caption, color: colors.textMuted },

  error: {
    ...typography.caption,
    color: colors.danger,
    marginTop: spacing.md,
  },
});
