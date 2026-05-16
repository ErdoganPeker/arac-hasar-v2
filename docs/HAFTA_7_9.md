# Hafta 7–9 Detaylı Rehber: Backend, Mobil App, Model Export

> **Tarihsel planlama dokümanıdır.** Erken plan döneminde yazılmıştır; endpoint isimleri burada eski şemada (`/v1/inspect`, `/v1/inspections/{id}`) geçer. Üretimdeki gerçek API yüzeyi `/api/v1/inspect` prefix'i ile çalışır — güncel referans için bkz. [API_GUIDE.md](API_GUIDE.md).

Bu faz, Faz 2'de inşa ettiğin `pipeline.py`'yi gerçek bir **production sistemi** haline getirir. Sonuç: backend API çalışıyor, mobil app fotoğraf çekip sonuç alıyor, on-device kalite kontrolü ile UX akıcı.

## Faz 3 Sonu Hedefler

- FastAPI backend `POST /inspect` ve `GET /inspections/{id}` ile asenkron çalışıyor
- React Native mobil app: capture flow → upload → results
- YOLO modelleri TFLite (Android) ve CoreML (iOS) olarak export edilmiş
- On-device kalite kontrolü: araç var/yok, blur kontrolü
- Docker compose ile lokal stack tek komutla ayağa kalkıyor

## Dosya Haritası (Yeni Eklenenler)

```
mvp-arac-hasar/
├── (Faz 1+2 dosyaları)
├── HAFTA_7_9_REHBER.md
├── backend/
│   ├── main.py                # FastAPI ana app
│   ├── models.py              # Pydantic şemaları
│   ├── ml_service.py          # Pipeline singleton
│   ├── worker.py              # Celery async tasks
│   ├── storage.py             # S3/MinIO entegrasyonu
│   ├── config.py              # Settings (env)
│   ├── database.py            # SQLAlchemy + Postgres
│   ├── Dockerfile
│   ├── docker-compose.yml     # Tam local stack
│   ├── requirements.txt
│   └── .env.example
├── mobile/
│   ├── App.tsx
│   ├── screens/
│   │   ├── CaptureFlow.tsx
│   │   └── Results.tsx
│   ├── services/
│   │   ├── api.ts
│   │   └── onDeviceQC.ts      # TFLite ile araç tespiti
│   ├── package.json
│   └── README.md
└── export_models.py           # TFLite + CoreML export
```

---

## Hafta 7: Backend API

### Mimari kararlar

**Senkron mu asenkron mu?**

Tek görüntü, 1-3 hasar → ~1-3 saniye → senkron OK.
360° tarama (20+ görüntü) → ~30-60 saniye → mutlaka async (Celery + Redis queue).

Hibrit yaklaşım: backend hem senkron (`/inspect/sync`) hem async (`/inspect`) endpoint sunar.

**Ölçekleme stratejisi:**

İlk 6 ay: tek FastAPI worker + tek Celery worker + tek GPU instance. Yeterli.
Trafik artarsa: Triton Inference Server (model serving ayrı), multi-worker, gRPC.

### Gün 1–2: Temel iskelet

`backend/main.py` ile başla. Endpoint'ler:
- `POST /v1/inspect` — async, sonuç webhook veya polling
- `GET /v1/inspections/{id}` — durum + sonuç
- `POST /v1/inspect/sync` — küçük inspeksiyonlar için (timeout 30s)
- `GET /healthz` — health check
- `GET /v1/inspections` — kullanıcının geçmiş inspections'ı

### Gün 3: Storage ve veritabanı

**S3/MinIO:** Ham görüntüler ve sonuç JSON'ları. MinIO lokal geliştirmede S3 ile aynı API.

**Postgres:** Metadata, inspections, users, audit log. Migrations için Alembic ekleyebilirsin ama MVP'de schema sabit kalacak, gerekmez.

**Redis:** Celery broker + result backend + cache.

### Gün 4: Authentication

İki kullanım senaryosu:
- **B2C mobil app:** Firebase Auth veya Supabase Auth → JWT
- **B2B API:** API key (basit, dashboard'tan üretilir)

MVP için sadece API key yeter, JWT'yi v2'de ekle.

### Gün 5: Docker compose ile test

```bash
cd backend
cp .env.example .env  # API_KEY, S3 endpoint vs. doldur
docker-compose up
```

API hazır: `http://localhost:8000/docs` (Swagger UI).

---

## Hafta 8: Mobil App İskeleti

### Teknoloji seçimi

**React Native + Expo** seçtim çünkü:
- Tek codebase iOS + Android
- Expo Camera API: izinler, focus, ışık otomatik
- Native modules için `expo-modules-core` var (TFLite/CoreML)
- OTA update (TestFlight'a yeni build göndermeden değişiklik)

Alternatif: Flutter. Eğer ekipte Dart bilen varsa daha iyi performans verir. Bizim örneklerde RN kullanıyoruz.

### Gün 1–2: Capture flow tasarımı

İyi UX = yönlendirilmiş çekim. Ravin ve Tractable bunu çok iyi yapıyor — sen de aynısını yap.

Çekim sırası (4-6 fotoğraf):
1. **Ön (1):** Aracın önünden, tüm araç çerçeveye girsin
2. **Sol yan (2):** Sol kapı + tampon görünsün
3. **Arka (3):** Arkadan tam çekim
4. **Sağ yan (4):** Sağ kapı + tampon
5. **Hasar yakın çekimi (5+):** Görünür hasar varsa yaklaş

Her adımda:
- Üstte hangi açıdan çekmesi gerektiğini söyle
- Şablon overlay (silüet) göster
- Otomatik kalite kontrolü: blur, ışık, araç var mı

### Gün 3: On-device kalite kontrolü

Bu kritik. Kullanıcının çöp fotoğraf yüklemesine izin verme — gönderim öncesi reddet.

YOLO26-n (5MB) ile on-device:
1. Araç var mı? (COCO `car`, `truck` class'ı)
2. Bbox kullanılabilir alanın en az %30'unu kaplıyor mu?
3. Blur skoru kabul edilebilir mi? (Laplacian variance)

### Gün 4–5: Upload + polling

```tsx
const inspectionId = await api.createInspection(images);
// Polling - her 2 sn'de bir kontrol
const result = await api.pollInspection(inspectionId);
```

Daha iyi: WebSocket veya Server-Sent Events. v1 polling ile başla, v2'de SSE.

---

## Hafta 9: Model Export ve Edge Deployment

### Gün 1–2: TFLite export

YOLO26 → TFLite çevirim:

```bash
python export_models.py --weights runs/.../best.pt \
    --format tflite --imgsz 320 --int8
```

Mobile için optimization:
- **imgsz 320:** Mobile'da 640 çok yavaş, 320 yeterli (sadece QC için)
- **INT8 quantization:** ~4x boyut/hız kazanımı, ~%2 mAP düşüşü
- **Static input shape:** Dynamic shape mobile'da yavaş

Çıktı: `best_int8.tflite` (~3-5MB).

### Gün 3: CoreML export

```bash
python export_models.py --weights runs/.../best.pt \
    --format coreml --imgsz 320 --half
```

iOS'ta Neural Engine (ANE) çok hızlı — int8 yerine fp16 daha iyi sonuç verir genelde.

### Gün 4: Mobile integration

React Native'de TFLite çalıştırmak için `react-native-fast-tflite` veya `vision-camera-tflite` kullan. CoreML için `@react-native-community/vision-camera` + MLKit veya kendi native modülün.

### Gün 5: Performance test

Test hedefleri:
- Pixel 6 / iPhone 12 üzerinde inference < 100ms
- App boyutu < 50MB (model dahil)
- Soğuk başlangıçta UI < 1s görünür

---

## Faz 3 Sonu — Karar Noktası

Elinde olması gereken:
- Backend production'da (veya en azından staging'de) çalışıyor
- Mobil app TestFlight + Google Play Internal Testing'de
- En az 3-5 iç kullanıcı baştan sona akışı denemiş

Hazırsan Hafta 10'da gözlemlenebilirlik ve pilot çalışmasına geç.
