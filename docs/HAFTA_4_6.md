# Hafta 4–6 Detaylı Rehber: Parça Segmentasyonu, Şiddet, Pipeline ve Maliyet

Bu faz, Hafta 1–3'te kurduğun hasar tespit modelini **gerçek bir uçtan-uca pipeline'a** dönüştürür. Sonuç: bir görüntü gir → hasarlı parçalar + her hasarın şiddeti + tahmini maliyet aralığı.

## Faz 2 Sonu Hedefler

- Parça segmentasyon modeli (~15 parça sınıfı) eğitilmiş
- Şiddet sınıflandırıcı (hafif/orta/ağır) çalışıyor
- `pipeline.py` ile uçtan-uca akış: image → hasar + parça + şiddet + maliyet JSON
- Türkiye için ilk maliyet lookup tablosu (YAML) — sigortacı validasyonu için referans

## Dosya Haritası

```
mvp-arac-hasar/
├── (Faz 1 dosyaları)
├── HAFTA_4_6_REHBER.md            # Bu dosya
├── prepare_parts_data.py          # DSMLR/Ultralytics parts → YOLO
├── train_parts.py                 # Parça YOLO26-seg eğitimi
├── severity_classifier.py         # Şiddet sınıflandırıcı (eğitim + inference)
├── pipeline.py                    # Uçtan-uca orkestratör
├── cost_engine.py                 # Maliyet tahmin motoru
├── parts.yaml                     # Parça YOLO veri konfigi
└── cost_table.yaml                # Maliyet lookup tablosu (TR)
```

---

## Hafta 4: Parça Segmentasyonu

### Neden ayrı bir model?

Hasar modeli "bir göçük var" diyebilir ama "ön tampon orta-solda göçük var" demek için **parçaları da segment etmen gerek**. Bu olmadan ne maliyet hesaplayabilirsin ne de sigortacıya satabilirsin.

### Gün 1: Veri seçimi

İki ana açık kaynak veri seti var; ikisini birleştirip kullanmak en sağlam yol:

**Ultralytics CarParts-Seg (önerilen başlangıç):** 23 sınıf, Ultralytics tarafından bakımlı, YOLO formatında hazır. Ana parçalar: front/back bumper, front/back glass, front/back door, hood, tailgate, wheel, lights vs.

```python
from ultralytics import YOLO
# Veri kendiliğinden iner
model = YOLO("yolo26n-seg.pt")
model.train(data="carparts-seg.yaml", epochs=50)
```

**DSMLR Car Parts:** github.com/dsmlr/Car-Parts-Segmentation, 500 görüntü, 18 parça, COCO formatında. Boyutu küçük ama kaliteli, augmentasyon için iyi.

**Roboflow Universe:** "car-parts-segmentation" araması yap, en az 2-3 set daha bul. Hepsini birleştirip 5000+ görüntü hedefle.

### Gün 2–3: Eğitim

```bash
# Sadece Ultralytics seti ile hızlı baseline
python train_parts.py --data carparts-seg.yaml --model yolo26m-seg --epochs 100

# Birleşik veri seti ile ana eğitim
python train_parts.py --data parts_combined.yaml --model yolo26m-seg \
    --epochs 200 --imgsz 1024 --batch 8
```

Beklenen sonuç: ana parçalarda (bumper, hood, door, glass) **mAP50 ≥ 0.85**, küçük parçalarda (mirror, light, handle) **mAP50 ≥ 0.65**.

### Gün 4–5: İki modeli birleştir

`pipeline.py`'nin temel mantığı: hasar maskeleri ile parça maskelerinin IoU'sunu hesapla. Her hasarı en yüksek IoU'lu parçaya ata.

Edge case'ler:
- **Hasar birden fazla parçaya yayılıyor:** En büyük IoU'lu parçayı ana parça yap, diğerlerini ek parça olarak kaydet
- **Hasar hiç bir parçaya değmiyor:** Bu genelde false positive demektir; conf threshold'unu yükselt
- **Parça maskelerinin çakışması:** YOLO instance segmentation overlap yapabilir; her parça için en yüksek confidence olanı al

---

## Hafta 5: Şiddet Sınıflandırma

### Yaklaşım kararı

İki seçenek var:
1. **Direkt CNN (kara kutu):** Hasar bölgesi crop → ResNet50/EfficientNetV2-S → light/medium/heavy çıkarır
2. **Hibrit kural-tabanlı (açıklanabilir):** maske_alanı × parça_önem_katsayısı × hasar_tipi_katsayısı → eşik tablosu

Pratik tavsiye: Önce hibrit yaklaşımla başla (Hafta 5 Gün 1-2). Sonra CNN'i de eğit ve karşılaştır. Sigortacıya satarken açıklanabilirlik kazandırır.

### Veri kaynağı

Roboflow'daki **Car Damage Severity Detection/CarDD** seti 19 sınıfa kadar şiddet etiketli (minor-scratches, moderate-deformation, severe-deformation). Bunu 3 sınıfa indirgeyip kullan:

```
minor_*, paint-chips → hafif (0)
moderate-*, scratches → orta (1)
severe-*, detachment, glass-shatter → agir (2)
```

### Gün 1–2: Hibrit kural sistemi

`severity_classifier.py` içindeki `RuleBasedSeverity` sınıfını kullan. Mantık:

```python
severity_score = damage_area_ratio * part_importance * damage_type_weight

# Ornekler:
# scratch + door + 0.005 area_ratio → score=0.03 → "hafif"
# dent + hood + 0.02 area_ratio → score=0.12 → "orta"  
# crack + windshield + 0.05 area_ratio → score=0.5 → "agir"
```

### Gün 3–5: CNN şiddet modeli

YOLO-cls (classification head) ile çabuk bir model:

```bash
python severity_classifier.py train \
    --data data/severity_yolo \
    --model yolo26n-cls --epochs 50
```

Veri yapısı:
```
data/severity_yolo/
├── train/
│   ├── hafif/
│   ├── orta/
│   └── agir/
├── val/...
```

Çıktıyı hibritle kombine et: kural-tabanlı + CNN ensemble. Hesaplama hızlı, sonuç açıklanabilir.

---

## Hafta 6: Pipeline Orkestrasyon ve Maliyet

### Gün 1–2: Uçtan-uca pipeline

`pipeline.py` tüm bileşenleri birleştirir:

```python
from pipeline import DamagePipeline

pipe = DamagePipeline(
    damage_weights="runs/.../best.pt",
    parts_weights="runs/.../parts_best.pt",
    severity_weights="runs/.../severity_best.pt",
    cost_table="cost_table.yaml",
)
result = pipe.analyze("car_photo.jpg")
print(result["total_cost_range"])  # [3500, 8000] TL
```

### Gün 3: Maliyet lookup tablosu

`cost_table.yaml` formatı:

```yaml
# (parça, hasar_tipi, şiddet) → fiyat aralığı TL
front_bumper:
  scratch:
    hafif: [200, 800]      # Pasta-cila
    orta: [1500, 3500]     # Boya
    agir: [4000, 12000]    # Parça değişimi
  dent:
    hafif: [400, 1200]     # PDR (boyasız göçük)
    orta: [2500, 5000]     # Düzeltme + boya
    agir: [5000, 15000]    # Değişim
```

Bu değerleri sıfırdan tahmin etmek yerine **veri toplamak gerek**. Türkiye için kaynaklar:
- TSB (Türkiye Sigorta Birliği) açık veri portalı
- Otoyedek.com, partsplus.com.tr, parcacim.com — yedek parça fiyatları
- Yetkili servis liste fiyatları (Renault, Fiat, Ford, Hyundai TR)
- Bağımsız oto-boyacı/tornacı tarifeleri (saha araştırması)

İlk versiyon "yaklaşık" olsun, 2-3 ay sonra gerçek veri ile fine-tune et.

### Gün 4: API kontrak'ı

`pipeline.py` çıktısı şu formatta olsun (Hafta 7 backend'in FastAPI endpoint'i bu JSON'u serve edecek):

```json
{
  "inspection_id": "uuid",
  "image_url": "s3://...",
  "vehicle": {
    "make": null, "model": null, "year": null
  },
  "damages": [
    {
      "id": 0,
      "type": "scratch",
      "confidence": 0.87,
      "part": "front_bumper",
      "part_confidence": 0.95,
      "severity": "orta",
      "severity_confidence": 0.78,
      "area_pixels": 4521,
      "area_ratio": 0.012,
      "cost_range_tl": [1500, 3500]
    }
  ],
  "summary": {
    "total_damages": 3,
    "total_cost_range_tl": [4200, 9500],
    "most_severe": "agir",
    "repair_recommendation": "parça_değişimi",
    "estimated_repair_days": 3
  }
}
```

### Gün 5: Integration test

Manuel olarak 10 farklı görüntü hazırla:
- 1 hasarsız araç (sistem boş döndürmeli)
- 3 tek hafif hasar (scratch, paint chip)
- 3 orta hasar (dent, broken light)
- 3 ağır/çoklu hasar (multiple damages, kombine)

Her birinde pipeline'ı koştur, beklenen vs. gerçek karşılaştır. Bu test seti Hafta 10'da regression için kullanılacak.

---

## Yaygın Sorunlar ve Çözümleri

**Parça modeli "wheel" diye lastikleri her zaman görüyor ama "side_mirror" kaçırıyor:** Sınıf dengesizliği. CarParts-Seg'de mirror çok az örnekli. Sadece mirror için 200-300 ek görüntü topla veya class weights ayarla.

**Hasar bir parçaya değiyor ama IoU 0.05 gibi düşük:** Threshold'u 0.1'e çek ama log'a yaz. Çok düşük IoU'larda büyük ihtimal hasar segmentasyon hatası var.

**Şiddet modeli her şeye "orta" diyor:** Veri dengesizliği klasik. WeightedRandomSampler veya class_weight kullan.

**Maliyet hep aynı çıkıyor:** Maliyet motorunda parça/şiddet/tip kombinasyonun lookup'ta yoksa default değer dönüyor. `cost_engine.py` log'larında "missing key" uyarılarına bak.

---

## Karar Noktası — Faz 2 Sonu

Bu hafta sonunda elinde:
- `pipeline.analyze(image)` → tam JSON dönüyor
- 10 test case'inde manuel kontrol → tutarlı
- Bilinen edge case'ler dokümanlı

Hazırsan Hafta 7'de FastAPI + mobil app iskeletine geçeriz. Bu pipeline'ı endpoint olarak sarmalayacağız.
