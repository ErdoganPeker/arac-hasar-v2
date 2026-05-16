/**
 * screens/CaptureFlow.tsx
 * Yonlendirilmis cekim akisi - kullaniciyi 4-6 acidan fotograf cektirir
 * her cekimde on-device kalite kontrolu yapar.
 */
import React, { useState, useRef, useEffect } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity,
  ActivityIndicator, Alert, Image,
} from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { useNavigation } from '@react-navigation/native';

import { runQualityCheck } from '../services/onDeviceQC';
import { api } from '../services/api';

interface CaptureStep {
  id: string;
  title: string;
  hint: string;
  silhouette: string; // SVG path veya image URI
}

const CAPTURE_STEPS: CaptureStep[] = [
  {
    id: 'front',
    title: 'Aracın önü',
    hint: 'Aracı tam ön açıdan, çerçeveye sığacak şekilde çek',
    silhouette: 'front',
  },
  {
    id: 'left',
    title: 'Sol yan',
    hint: 'Sol kapı ve tampon görünsün, mesafe ~2-3 metre',
    silhouette: 'side',
  },
  {
    id: 'rear',
    title: 'Arka',
    hint: 'Aracı arkadan tam görecek şekilde çek',
    silhouette: 'rear',
  },
  {
    id: 'right',
    title: 'Sağ yan',
    hint: 'Sağ kapı ve tampon görünsün',
    silhouette: 'side',
  },
];

export default function CaptureFlow() {
  const navigation = useNavigation<any>();
  const [permission, requestPermission] = useCameraPermissions();
  const [currentStep, setCurrentStep] = useState(0);
  const [captures, setCaptures] = useState<{ uri: string; stepId: string }[]>([]);
  const [processing, setProcessing] = useState(false);
  const [qcMessage, setQcMessage] = useState<string | null>(null);
  const cameraRef = useRef<CameraView>(null);

  useEffect(() => {
    if (!permission?.granted) {
      requestPermission();
    }
  }, [permission]);

  if (!permission) {
    return <View style={styles.center}><ActivityIndicator /></View>;
  }

  if (!permission.granted) {
    return (
      <View style={styles.center}>
        <Text style={styles.message}>Kamera izni gerekli</Text>
        <TouchableOpacity style={styles.button} onPress={requestPermission}>
          <Text style={styles.buttonText}>İzin Ver</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const handleCapture = async () => {
    if (!cameraRef.current || processing) return;
    setProcessing(true);
    setQcMessage('Fotoğraf alınıyor...');

    try {
      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.85,
        skipProcessing: false,
      });
      if (!photo?.uri) {
        setProcessing(false);
        return;
      }

      // On-device kalite kontrolu
      setQcMessage('Kalite kontrol ediliyor...');
      const qc = await runQualityCheck(photo.uri);

      if (!qc.passed) {
        Alert.alert(
          'Tekrar dene',
          qc.reason || 'Fotoğrafın kalitesi yeterli değil. Tekrar çekebilir misin?',
          [{ text: 'Tamam' }]
        );
        setProcessing(false);
        setQcMessage(null);
        return;
      }

      // Capture'i kaydet, sonraki adima gec
      const newCapture = { uri: photo.uri, stepId: CAPTURE_STEPS[currentStep].id };
      const newCaptures = [...captures, newCapture];
      setCaptures(newCaptures);

      if (currentStep < CAPTURE_STEPS.length - 1) {
        setCurrentStep(currentStep + 1);
        setProcessing(false);
        setQcMessage(null);
      } else {
        // Tum adimlar tamamlandi - upload
        await uploadAndAnalyze(newCaptures);
      }
    } catch (err: any) {
      Alert.alert('Hata', err.message);
      setProcessing(false);
      setQcMessage(null);
    }
  };

  const uploadAndAnalyze = async (allCaptures: typeof captures) => {
    setQcMessage('Sunucuya gönderiliyor...');
    try {
      const inspectionId = await api.createInspection(
        allCaptures.map(c => c.uri)
      );
      // Active stack route name is "Result" (singular). Older deep links may
      // have used "Results" — both supported via a runtime fallback.
      navigation.replace('Result', { inspectionId });
    } catch (err: any) {
      Alert.alert('Yükleme hatası', err.message);
      setProcessing(false);
      setQcMessage(null);
    }
  };

  const step = CAPTURE_STEPS[currentStep];

  return (
    <View style={styles.container}>
      <CameraView ref={cameraRef} style={styles.camera} facing="back">
        {/* Ust bilgi */}
        <View style={styles.topBar}>
          <Text style={styles.stepCounter}>
            {currentStep + 1} / {CAPTURE_STEPS.length}
          </Text>
          <Text style={styles.stepTitle}>{step.title}</Text>
          <Text style={styles.stepHint}>{step.hint}</Text>
        </View>

        {/* Cekim butonu */}
        <View style={styles.bottomBar}>
          {qcMessage && <Text style={styles.qcMessage}>{qcMessage}</Text>}
          <TouchableOpacity
            style={[styles.captureBtn, processing && styles.captureBtnDisabled]}
            onPress={handleCapture}
            disabled={processing}
          >
            {processing ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <View style={styles.captureBtnInner} />
            )}
          </TouchableOpacity>
        </View>
      </CameraView>

      {/* Onceki cekimler */}
      {captures.length > 0 && (
        <View style={styles.thumbnails}>
          {captures.map((c, i) => (
            <Image key={i} source={{ uri: c.uri }} style={styles.thumbnail} />
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 20 },
  message: { color: '#fff', marginBottom: 20, textAlign: 'center' },
  camera: { flex: 1 },
  topBar: {
    backgroundColor: 'rgba(0,0,0,0.6)',
    paddingTop: 60,
    paddingBottom: 16,
    paddingHorizontal: 20,
  },
  stepCounter: { color: '#94a3b8', fontSize: 14 },
  stepTitle: { color: '#fff', fontSize: 20, fontWeight: 'bold', marginTop: 4 },
  stepHint: { color: '#cbd5e1', fontSize: 14, marginTop: 4 },
  bottomBar: {
    position: 'absolute',
    bottom: 40,
    left: 0, right: 0,
    alignItems: 'center',
  },
  qcMessage: { color: '#fff', marginBottom: 12 },
  captureBtn: {
    width: 80, height: 80, borderRadius: 40,
    backgroundColor: 'rgba(255,255,255,0.3)',
    justifyContent: 'center', alignItems: 'center',
  },
  captureBtnDisabled: { opacity: 0.5 },
  captureBtnInner: {
    width: 64, height: 64, borderRadius: 32,
    backgroundColor: '#fff',
  },
  thumbnails: {
    flexDirection: 'row', padding: 8, backgroundColor: '#000',
  },
  thumbnail: { width: 60, height: 60, marginRight: 4, borderRadius: 4 },
  button: { backgroundColor: '#3b82f6', padding: 12, borderRadius: 8 },
  buttonText: { color: '#fff', fontWeight: 'bold' },
});
