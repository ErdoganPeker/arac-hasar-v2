import React, { useCallback, useRef, useState } from 'react';
import {
  Alert,
  FlatList,
  Image,
  Linking,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTranslation } from 'react-i18next';
import {
  CameraView,
  CameraType,
  FlashMode,
  useCameraPermissions,
} from 'expo-camera';

import { MainScreenProps } from '../navigation/types';
import UploadButton from '../components/UploadButton';
import { colors, radius, spacing, typography } from '../theme';

type Props = MainScreenProps<'Camera'>;

const MAX_PHOTOS = 8;

export default function CameraScreen({ navigation, route }: Props) {
  const { t } = useTranslation(['inspect', 'common']);
  const [permission, requestPermission] = useCameraPermissions();
  const [facing, setFacing] = useState<CameraType>('back');
  const [flash, setFlash] = useState<FlashMode>('off');
  const [photos, setPhotos] = useState<string[]>([]);
  const [capturing, setCapturing] = useState(false);
  const cameraRef = useRef<CameraView | null>(null);

  const mode = route.params?.mode ?? 'async';

  const togglePermission = useCallback(async () => {
    const res = await requestPermission();
    if (!res.granted && !res.canAskAgain) {
      Alert.alert(t('inspect:permissionTitle'), t('inspect:permissionDescription'), [
        { text: t('common:cancel'), style: 'cancel' },
        { text: t('inspect:openSettings'), onPress: () => Linking.openSettings() },
      ]);
    }
  }, [requestPermission, t]);

  const handleCapture = useCallback(async () => {
    if (!cameraRef.current || capturing) return;
    if (photos.length >= MAX_PHOTOS) {
      Alert.alert(t('inspect:maxPhotosReached', { max: MAX_PHOTOS }));
      return;
    }
    setCapturing(true);
    try {
      const pic = await cameraRef.current.takePictureAsync({
        quality: 0.85,
        skipProcessing: false,
      });
      if (pic?.uri) {
        setPhotos((prev) => [...prev, pic.uri]);
      }
    } catch (e) {
      console.warn('Capture error', e);
    } finally {
      setCapturing(false);
    }
  }, [capturing, photos.length, t]);

  const removePhoto = (idx: number) => {
    setPhotos((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleContinue = () => {
    if (photos.length === 0) {
      Alert.alert(t('inspect:needAtLeastOne'));
      return;
    }
    navigation.navigate('Upload', { photos, mode });
  };

  if (!permission) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.center}>
          <Text style={styles.text}>{t('common:loading')}</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (!permission.granted) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.permissionWrap}>
          <Text style={styles.permissionIcon}>📷</Text>
          <Text style={styles.permissionTitle}>{t('inspect:permissionTitle')}</Text>
          <Text style={styles.permissionBody}>{t('inspect:permissionDescription')}</Text>
          <UploadButton
            label={t('inspect:grantPermission')}
            onPress={togglePermission}
            style={{ marginTop: spacing.lg }}
          />
          {!permission.canAskAgain ? (
            <UploadButton
              label={t('inspect:openSettings')}
              variant="secondary"
              onPress={() => Linking.openSettings()}
              style={{ marginTop: spacing.sm }}
            />
          ) : null}
        </View>
      </SafeAreaView>
    );
  }

  const nextFlash: Record<FlashMode, FlashMode> = {
    off: 'on',
    on: 'auto',
    auto: 'off',
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <View style={styles.cameraWrap}>
        <CameraView
          ref={cameraRef}
          style={StyleSheet.absoluteFillObject}
          facing={facing}
          flash={flash}
        />
        <View style={styles.topBar}>
          <Pressable
            style={styles.topBtn}
            onPress={() => navigation.goBack()}
            hitSlop={8}
          >
            <Text style={styles.topBtnText}>‹</Text>
          </Pressable>
          <Text style={styles.counter}>
            {t('inspect:photoCount', { count: photos.length, max: MAX_PHOTOS })}
          </Text>
          <Pressable
            style={styles.topBtn}
            onPress={() => setFlash(nextFlash[flash])}
            hitSlop={8}
          >
            <Text style={styles.topBtnText}>
              {flash === 'on' ? '⚡' : flash === 'auto' ? 'A' : '⨯'}
            </Text>
          </Pressable>
        </View>
      </View>

      <View style={styles.bottomBar}>
        {photos.length > 0 ? (
          <FlatList
            horizontal
            keyboardShouldPersistTaps="handled"
            data={photos}
            keyExtractor={(uri, i) => `${uri}-${i}`}
            contentContainerStyle={{ paddingHorizontal: spacing.lg }}
            showsHorizontalScrollIndicator={false}
            renderItem={({ item, index }) => (
              <Pressable
                onLongPress={() => removePhoto(index)}
                style={styles.thumbWrap}
              >
                <Image source={{ uri: item }} style={styles.thumb} />
                <Pressable style={styles.removeBtn} onPress={() => removePhoto(index)}>
                  <Text style={styles.removeBtnText}>×</Text>
                </Pressable>
              </Pressable>
            )}
            style={styles.thumbList}
          />
        ) : (
          <View style={styles.thumbHint}>
            <Text style={styles.thumbHintText}>{t('inspect:needAtLeastOne')}</Text>
          </View>
        )}

        <View style={styles.controls}>
          <Pressable
            onPress={() => setFacing((f) => (f === 'back' ? 'front' : 'back'))}
            style={styles.controlBtn}
            hitSlop={8}
          >
            <Text style={styles.controlBtnText}>↺</Text>
          </Pressable>

          <Pressable
            onPress={handleCapture}
            disabled={capturing}
            style={({ pressed }) => [styles.shutter, pressed && styles.shutterPressed]}
            accessibilityRole="button"
            accessibilityLabel={t('inspect:capturePhoto')}
          >
            <View style={styles.shutterInner} />
          </Pressable>

          <Pressable
            onPress={handleContinue}
            disabled={photos.length === 0}
            style={[styles.controlBtn, photos.length === 0 && styles.controlBtnDisabled]}
            hitSlop={8}
            accessibilityRole="button"
            accessibilityLabel={t('common:continue')}
          >
            <Text style={styles.controlBtnText}>›</Text>
          </Pressable>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#000' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  text: { color: colors.text },

  cameraWrap: { flex: 1, position: 'relative', backgroundColor: '#000' },
  topBar: {
    position: 'absolute',
    top: spacing.md,
    left: spacing.md,
    right: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  topBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(0,0,0,0.55)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  topBtnText: { color: '#fff', fontSize: 22, fontWeight: '600' },
  counter: {
    ...typography.label,
    color: '#fff',
    backgroundColor: 'rgba(0,0,0,0.55)',
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: radius.pill,
  },

  bottomBar: {
    backgroundColor: '#000',
    paddingTop: spacing.md,
    paddingBottom: Platform.select({ ios: spacing.md, android: spacing.lg }),
  },
  thumbList: { height: 76, marginBottom: spacing.md },
  thumbHint: { height: 76, alignItems: 'center', justifyContent: 'center' },
  thumbHintText: { color: '#94a3b8', ...typography.caption },
  thumbWrap: {
    width: 64,
    height: 64,
    borderRadius: radius.sm,
    overflow: 'hidden',
    marginRight: spacing.sm,
  },
  thumb: { width: '100%', height: '100%' },
  removeBtn: {
    position: 'absolute',
    right: 2,
    top: 2,
    width: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: 'rgba(220,38,38,0.9)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  removeBtnText: { color: '#fff', fontSize: 13, fontWeight: '700', lineHeight: 14 },

  controls: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-around',
    paddingHorizontal: spacing.xxl,
  },
  controlBtn: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: 'rgba(255,255,255,0.12)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  controlBtnDisabled: { opacity: 0.35 },
  controlBtnText: { color: '#fff', fontSize: 26, fontWeight: '600' },
  shutter: {
    width: 78,
    height: 78,
    borderRadius: 39,
    backgroundColor: 'rgba(255,255,255,0.18)',
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 4,
    borderColor: '#fff',
  },
  shutterPressed: { backgroundColor: 'rgba(255,255,255,0.36)' },
  shutterInner: { width: 58, height: 58, borderRadius: 29, backgroundColor: '#fff' },

  permissionWrap: {
    flex: 1,
    padding: spacing.xxl,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.bg,
  },
  permissionIcon: { fontSize: 64, marginBottom: spacing.lg },
  permissionTitle: {
    ...typography.h2,
    color: colors.text,
    textAlign: 'center',
    marginBottom: spacing.sm,
  },
  permissionBody: {
    ...typography.body,
    color: colors.textMuted,
    textAlign: 'center',
  },
});
