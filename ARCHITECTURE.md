# Mimari — Hasarİ v2

Bu doküman ML pipeline'ın iç işleyişini, parça-merkezli çıktı reorganizasyonunu ve servisler arası kontratları açıklar.

## 1. ML Pipeline — Akıllı Hibrit Mimari

Pipeline iki YOLO26-seg modelini **paralel** koşturur, sonra **akıllı eşleme** ile her hasarı doğru parçaya atar.

```
Görüntü
   │
   ├──► Quality check (blur, exposure, vehicle present)
   │
   ├──► [Paralel] Hasar modeli (YOLO26-seg, 6 sınıf)
   │    └─► damages: [{type, polygon, bbox, confidence}, ...]
   │
   ├──► [Paralel] Parça modeli (YOLO26-seg, 23 sınıf)
   │    └─► parts: [{name, polygon, bbox, confidence}, ...]
   │
   ├──► Akıllı eşleme (IoU + intersection_ratio)
   │    ├─ Hasar parçaya tam kaplı → tek parça
   │    ├─ Hasar iki+ parçaya yayılıyor → multi-part flag + affected_parts
   │    ├─ Düşük güven → is_low_confidence_match flag
   │    └─ Parça bulunamadı → primary_part = "unknown"
   │
   ├──► Şiddet sınıflandırma (ensemble)
   │    ├─ Kural-tabanlı: maske alanı + hasar tipi + parça → hafif/orta/ağır
   │    ├─ CNN classifier: hasar bölgesi crop → 3-sınıf
   │    └─ Ensemble: ağırlıklı kombinasyon
   │
   ├──► Maliyet motoru (kademeli lookup)
   │    ├─ (parça, hasar_tipi, şiddet) → range
   │    ├─ Aynı parçada çoklu hasar → en pahalı dominant
   │    └─ Toplam aggregation
   │
   └──► Output formatter (parça-merkezli reorganizasyon)
        └─► JSON: { parts: [...], summary, multi_part_damages, visualization_urls }
```

### Neden paralel + IoU eşleme?

**Alternatif 1 — Kaskad (parça → her parçada hasar):**
- ✅ Daha az false positive (sadece parça içi tarama)
- ❌ Yavaş (her parça için ayrı inference)
- ❌ İki parçaya yayılan hasarda problem (kapı↔çamurluk arası çizik)
- ❌ Parça kaçırılırsa üzerindeki hasar da kaçar

**Alternatif 2 — Naif paralel (her hasar en yakın parçaya):**
- ✅ Hızlı, tek geçişte
- ❌ Yanlış parça eşleme riski

**Seçim — Akıllı paralel:**
- Paralel hızını korur
- IoU + intersection_ratio ile *doğru* eşleme yapar
- Multi-part hasarı ayrı işaretler (bilgi kaybı yok)
- Parça kaçırılsa bile hasar yine tespit edilir ("unknown" fallback)

### IoU eşleme kuralları

```python
# pseudocode — services/ml/pipeline.py
for damage in damages:
    candidates = []
    for part in parts:
        iou = iou(damage.mask, part.mask)
        intersection_ratio = intersection_area(damage.mask, part.mask) / damage.area
        if intersection_ratio >= 0.5:    # hasar parçanın yarısından fazla içindeyse
            candidates.append((part, iou, intersection_ratio))

    if not candidates:
        damage.primary_part = "unknown"
    elif len(candidates) == 1:
        damage.primary_part = candidates[0][0].name
    else:
        # Birden fazla parça örtüşüyor → multi-part
        candidates.sort(key=lambda c: -c[2])  # intersection_ratio'ya göre
        damage.primary_part = candidates[0][0].name
        damage.secondary_parts = [{"part": c[0].name, "ratio": c[2]} for c in candidates[1:]]
        damage.is_multi_part = True

    # Düşük güven kontrolü
    if candidates and candidates[0][1] < 0.05:
        damage.is_low_confidence_match = True
```

`iou_threshold = 0.05` bilinçli olarak düşük — bilinmeyen parça > yanlış parça. Detaylar: `services/ml/pipeline.py`.

## 2. Parça-merkezli output reorganizasyonu

Pipeline iç düzeyde **hasar-listesi** tutar, ama API kullanıcısına **parça-merkezli** JSON döner. `services/ml/output_formatter.py` bu çeviriyi yapar.

İç (raw):
```python
damages = [{id, type, primary_part, severity, cost, ...}, ...]
parts = [{name, polygon, confidence}, ...]
```

Dış (kullanıcıya):
```python
parts = [
    {
        name, name_tr, status,            # status: clean | minor | moderate | severe
        damage_count,
        damages: [...],                    # bu parçaya ait hasarlar
        part_cost_min_tl, part_cost_max_tl,
        cost_note,                         # "Tek parça değişimi diğer hasarları kapsar"
    }
]
```

Kritik: **hasarsız parçalar da listede**, `status: "clean"` ile. Kullanıcı "kontrol edildi, hasar yok" güvencesi alıyor.

## 3. Şiddet ensemble

`services/ml/severity_classifier.py` üç katman:

1. **Kural-tabanlı** (`RuleBasedSeverity`):
   - `area_ratio < 0.005` → hafif
   - `0.005 ≤ area_ratio < 0.02` → orta
   - `area_ratio ≥ 0.02` → ağır
   - Hasar tipi çarpanları: glass_shatter → her zaman ≥ orta, scratch → genelde hafif
2. **CNN classifier** (`CNNSeverity`):
   - EfficientNetV2-S, hasar crop'u → 3-sınıf softmax
   - Roboflow severity setinde fine-tune edilir
3. **Ensemble** (`EnsembleSeverity`):
   - Anlaşıyorlarsa → o seviye, yüksek güven
   - Anlaşmıyorlarsa → ağırlıklı (kural %40, CNN %60), düşük güven flag

v1'de kural-tabanlı yeter (açıklanabilir, sigortacı için satılabilir). CNN v2 backlog.

## 4. Maliyet motoru — kademeli lookup

`services/ml/cost_engine.py` + `cost_table.yaml` (TR-specific).

**Lookup hiyerarşisi:** (parça, tip, şiddet) → (parça, tip default) → (global default) → hard default. Her seviye düştükçe `cost_confidence` düşer (high → medium → low).

**Çoklu hasar aggregation:** Aynı parçada birden fazla hasar varsa, naif toplam yanlış olur (parça değişimi diğer hasarları zaten kapsar). En pahalı %70'i aşıyorsa, sadece o alınır + `cost_note: "Tek parça değişimi diğer hasarları kapsar"`.

**v1 sınırlamaları:**
- Lookup tablosu manuel — TR pazar verileriyle güncellenmeli (otoyedek, yetkili servisler, TSB)
- Araç modeline duyarlı değil (Fiat Egea vs. BMW 5 farkı yok) — v2 backlog
- İşçilik vs. parça ayrı satır değil — agregate range

## 5. Servisler arası kontratlar

### Backend ↔ Frontend (TypeScript)

`packages/types/src/` altında Pydantic şemalarının birebir TS karşılığı. Web, desktop ve mobile aynı tipleri kullanır.

| Backend (Pydantic) | Frontend (TS) | Yer |
|---|---|---|
| `models.Damage` | `Damage` | `packages/types/src/damage.ts` |
| `models.Part` | `Part` | `packages/types/src/part.ts` |
| `models.Inspection` | `Inspection` | `packages/types/src/inspection.ts` |
| `models.InspectionSummary` | `InspectionSummary` | `packages/types/src/inspection.ts` |
| `models.HealthResponse` | `HealthResponse` | `packages/types/src/api.ts` |

Senkron tutmak için: `python services/backend/scripts/export_openapi.py` çalıştırıp `packages/types/openapi.json` üretilir, manuel karşılaştırma yapılır. (v0.2'de openapi-typescript ile otomatik gen düşünülebilir.)

### Frontend (UI paylaşımı)

`packages/ui` web ve desktop tarafından doğrudan import edilir. Mobile (RN) React DOM yerine RN component'leri kullandığından `packages/ui`'yi DOĞRUDAN kullanmaz — `apps/mobile/components/` altında benzer component'ler RN-native olarak yaşar. Hedef: aynı API yüzeyini koru, render farklı.

### ML ↔ Backend

ML pipeline (`services/ml/pipeline.py`) Python class olarak çağrılır:
```python
pipeline = DamagePipeline(damage_weights="...", parts_weights="...", ...)
result = pipeline.run(image_path)  # dict, packages/types ile uyumlu
```

Backend `services/backend/ml_service.py` singleton wrapper'ı tutar (model yükleme tek sefer, request başına inference). Celery worker (`worker.py`) async job için bu singleton'ı yeniden kullanır.

## 6. Veri akışı — uçtan uca

```
Kullanıcı (Web/Desktop/Mobile)
    │
    │ multipart POST /api/v1/inspect
    ▼
FastAPI
    ├─ S3/MinIO'ya orijinal görüntü yükle
    ├─ Postgres'e inspection kaydı (status=queued)
    ├─ Celery task'ı kuyruğa koy
    └─ {inspection_id, status_url} döndür
    │
    ▼
Celery Worker (Redis broker)
    ├─ S3'ten görüntü çek
    ├─ ML Pipeline (singleton, warm)
    │   ├─ paralel hasar + parça inference
    │   ├─ IoU eşleme, severity, cost
    │   └─ visualization.py: 3 PNG üret (annotated, parts, damages)
    ├─ Postgres'e sonuç + status=completed
    ├─ S3'e visualization PNG'leri
    └─ Redis pub/sub: status push
    │
    ▼
Frontend
    ├─ Polling: GET /api/v1/inspect/{id} (2sn aralık)
    │   veya WS /api/v1/inspect/{id}/stream
    └─ status=completed → result JSON + visualization URL'leri
```

## 7. Performans hedefleri

| Senaryo | Hedef latency | Notlar |
|---|---|---|
| Sync tek görüntü (cloud GPU, T4) | < 2sn | YOLO26-m batch=1 |
| Async 5 görüntü | < 8sn | paralel inference |
| Async 30 görüntü (360° tarama) | < 30sn | Celery 4-worker |
| Mobile on-device QC | < 100ms | YOLO26-n TFLite |
| Cold start (model load) | < 8sn | singleton ile bir kere |

Yerel dev (RTX 5050 8GB): batch=8 m-model ~30ms/image. Production GPU (T4) benzer.

## 8. Gözlemlenebilirlik (v0.2)

- **Sentry** — frontend ve backend hataları
- **Prometheus** — request latency, inference time, queue depth, error rate
- **Grafana** — `observability/` altında dashboard JSON
- **Structured logs** — backend loguru JSON, frontend pino (browser)
- **Trace ID** — her inspection için, headers ve log'larda

## 9. Güvenlik

- **Auth:** v1 API key (`X-API-Key`), v2 JWT
- **CORS:** `localhost:3000` (web dev), `tauri://localhost` (desktop prod), Expo emülatör. Production'da env'den whitelist.
- **CSP:** Tauri config'te sıkı, sadece localhost+https.
- **PII:** Plaka/VIN ham görüntüde — anonimleştirme v0.2.
- **Rate limit:** v0.2, Redis-based.

## 10. Bilinçli kısıtlamalar

- **CarDD academic non-commercial** — ticari pilot için ayrı izin gerekli, ya da kendi etiketli veri seti.
- **Türk araç modelleri zayıf temsil** — pilot'tan 500-1000 TR görüntüyü etiketleyip fine-tune (Hafta 11-12).
- **Aydınlatma/açı edge case'leri** — capture flow'da rehberlik, yine de %20-30 başarısız case kaçınılmaz.
- **Maliyet tablosu manuel** — TR pazar verisiyle güncellenmeli, otomatik scraping v2.
