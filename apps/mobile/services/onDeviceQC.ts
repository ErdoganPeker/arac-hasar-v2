/**
 * services/onDeviceQC.ts
 * On-device kalite kontrolu - upload oncesi reddet.
 *
 * Kontroller:
 *  1. Goruntu dosyasi gecerli mi
 *  2. (TFLite) Arac var mi - kullanim alaninin >%25'i
 *  3. (Native) Blur skoru kabul edilebilir mi
 *
 * NOT: TFLite entegrasyonu icin react-native-fast-tflite kurmak gerek.
 * Bu dosyada basic + opsiyonel TFLite stub var.
 */
import * as FileSystem from 'expo-file-system';
import { Image } from 'react-native';

export interface QCResult {
  passed: boolean;
  reason?: string;
  vehicleDetected?: boolean;
  vehicleBboxRatio?: number;
  blurScore?: number;
}

const MIN_VEHICLE_BBOX_RATIO = 0.25;  // arac, ekranin en az %25'ini kaplamali
const MIN_BLUR_SCORE = 100;            // Laplacian variance esigi
const MIN_FILE_SIZE_KB = 50;           // 50KB altinda sik kullanilan thumbnail

/**
 * Asil QC fonksiyonu - tum kontrolleri yapar.
 */
export async function runQualityCheck(uri: string): Promise<QCResult> {
  // 1. Dosya bilgileri
  const info = await FileSystem.getInfoAsync(uri);
  if (!info.exists) {
    return { passed: false, reason: 'Fotoğraf bulunamadı' };
  }

  const sizeKB = (info.size || 0) / 1024;
  if (sizeKB < MIN_FILE_SIZE_KB) {
    return { passed: false, reason: 'Fotoğraf çok küçük' };
  }

  // 2. Boyut kontrolu
  const dims = await getImageDimensions(uri);
  if (dims.width < 480 || dims.height < 480) {
    return { passed: false, reason: 'Çözünürlük çok düşük' };
  }

  // 3. Arac tespiti (TFLite varsa)
  let vehicleDetected = true;
  let vehicleBboxRatio = 1.0;
  try {
    const vehicleResult = await detectVehicle(uri);
    vehicleDetected = vehicleResult.detected;
    vehicleBboxRatio = vehicleResult.bboxRatio;

    if (!vehicleDetected) {
      return {
        passed: false,
        reason: 'Fotoğrafta araç tespit edilemedi',
        vehicleDetected: false,
      };
    }
    if (vehicleBboxRatio < MIN_VEHICLE_BBOX_RATIO) {
      return {
        passed: false,
        reason: 'Araç çok uzakta - daha yakın çek',
        vehicleBboxRatio,
      };
    }
  } catch (err) {
    // TFLite yoksa kontrolu atla, sunucu yapacak
    console.warn('Vehicle QC atlandi:', err);
  }

  // 4. Blur kontrolu (native modulle olsa daha iyi)
  // Stub - gercek implementasyonda VisionCamera frame processor kullan
  let blurScore = 500; // default OK
  try {
    blurScore = await computeBlurScore(uri);
    if (blurScore < MIN_BLUR_SCORE) {
      return {
        passed: false,
        reason: 'Fotoğraf bulanık - sabit dur ve tekrar çek',
        blurScore,
      };
    }
  } catch (err) {
    console.warn('Blur QC atlandi:', err);
  }

  return {
    passed: true,
    vehicleDetected,
    vehicleBboxRatio,
    blurScore,
  };
}

/**
 * Goruntu boyutlarini al.
 */
function getImageDimensions(uri: string): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    Image.getSize(
      uri,
      (width, height) => resolve({ width, height }),
      reject,
    );
  });
}

/**
 * Arac tespiti - TFLite ile.
 *
 * Gercek implementasyon:
 *   import { loadTensorflowModel } from 'react-native-fast-tflite';
 *   const model = await loadTensorflowModel(require('../assets/yolo26n-qc.tflite'));
 *   const output = model.runSync([imageInput]);
 *   ...
 */
async function detectVehicle(uri: string): Promise<{ detected: boolean; bboxRatio: number }> {
  // STUB - production'da gercek inference
  // Bu dummy degerler her zaman gecerli kabul eder
  return { detected: true, bboxRatio: 0.6 };
}

/**
 * Blur skoru - Laplacian variance.
 *
 * Gercek implementasyon:
 *   - Native module ile OpenCV
 *   - veya VisionCamera frame processor
 */
async function computeBlurScore(uri: string): Promise<number> {
  // STUB
  return 500;
}
