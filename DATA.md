# Veri Setleri — Hasarİ v2

Bu doküman, kullanılan veri setlerinin kısa özetidir. Detaylı indirme talimatları için `scripts/DATA_README.md`'a bak.

## Tek bakışta

| Kullanım | Veri seti | Boyut | Lisans | Nereden |
|---|---|---|---|---|
| Hasar tespiti (ana) | **CarDD** | 4.000 görüntü, 9.000+ etiket, 6 sınıf | Academic non-commercial | [cardd-ustc.github.io](https://cardd-ustc.github.io) (form) veya HF mirror `harpreetsahota/CarDD` |
| Parça segmentasyonu | **Ultralytics CarParts-Seg** | ~3.000 görüntü, 23 parça | AGPL-3.0 | Ultralytics otomatik (`carparts-seg.yaml`) |
| Parça (ek) | **DSMLR Car Parts** | 500 görüntü, 18 parça | MIT | `github.com/dsmlr/Car-Parts-Segmentation` |
| Şiddet sınıflandırma | **Roboflow Severity** | ~2.500 görüntü, 19 sınıf → 3'e indir | CC BY 4.0 | Roboflow Universe (`car-damage-detection-cardd`) |
| TR maliyet tablosu | YOK — manuel | — | — | TR pazar verisiyle güncellenmeli |

## CarDD (ana hasar seti)

**Neden:** Bu alandaki ilk büyük ölçekli halka açık veri seti. Altı hasar kategorisi (dent, scratch, crack, glass_shatter, lamp_broken, tire_flat), dört görev (classification, detection, instance segmentation, salient object detection) destekler.

**Kritik gerçek:** Çiziklerin %45'inden fazlası, çatlakların %90'ından fazlası "küçük" örnekler. Modelinin küçük nesne tespitinde iyi olması ZORUNLU — bu yüzden `imgsz=1024` veya minimum 832 öneririz.

**Lisans uyarısı:** Academic non-commercial. Startup için ticari kullanım istiyorsanız, baseline'ı CarDD ile kurun ama production öncesi kendi etiketli verinizi toplayın.

**İndirme:**
- Hızlı yol: `python scripts/download_data.py --cardd-hf` (HuggingFace mirror, anında)
- Resmi yol: `cardd-ustc.github.io`'da form doldur, onay 1-2 gün, indir, `python scripts/download_data.py --cardd-manual <zip-path>`

## Ultralytics CarParts-Seg

**Neden:** Parça segmentasyonu için tek bütünleşik açık set. 23 parça sınıfı: front_bumper, hood, front_glass, side_door, mirror, wheel, vb.

**Performans referansı:** YOLO11-seg CarParts-Seg üzerinde back_bumper, front_bumper, front_glass parçalarında mAP50 %96+; tailgate, küçük lambalar daha düşük (%57–60).

**İndirme:** Ultralytics otomatik. `prepare_parts_data.py --use_ultralytics` çağırınca cache'ler.

## DSMLR Car Parts (ek)

**Neden:** Küçük (500 görüntü) ama yüksek kaliteli COCO formatında. Ultralytics setiyle birleştirilince çeşitliliği artırır. HTC (Hybrid Task Cascade) ile mAP 55.2/59.1.

**İndirme:** `python scripts/download_data.py` içinde manuel adım — `git clone github.com/dsmlr/Car-Parts-Segmentation`.

## Roboflow Severity

**Neden:** Şiddet ensemble'ının CNN tarafını eğitmek için. 19 sınıf var (minor-scratches, moderate-deformation, severe-deformation vb.), bunları 3-sınıfa (hafif/orta/ağır) eşleyeceğiz.

**İndirme:** Roboflow API key gerekli. `python scripts/download_data.py --roboflow-severity`. Workspace/project slug'ı Universe'den doğrula.

## TR maliyet tablosu

**Açık veri seti yok.** `services/ml/cost_table.yaml`'daki rakamlar başlangıç tahmini. Gerçeğe çevirmek için:

- **otoyedek.com, parcacim.com** → yedek parça fiyat scraping
- **Yetkili servisler** (Renault, Fiat, Ford, Hyundai TR) → işçilik saat ücretleri
- **TSB (tsb.org.tr)** → ortalama hasar verileri
- **Eksperler** (pilot için zaten ulaşacaksın) → 5-10 gerçek hasar dosyası
- **sahibinden.com** hasarlı araç ilanları → hasarsız vs. hasarlı değer farkı

## Eğitim sırası önerisi (RTX 5050 8GB)

```powershell
# 1. Pretrained baseline (veri olmadan, ilk gün)
python scripts\download_pretrained.py --all
# Test inference: services/ml/inference_demo.py ile herhangi bir araç fotoğrafında dene

# 2. Hasar modeli (CarDD ile)
cd services\ml
python prepare_data.py --cardd_root data\cardd_hf --output_dir data\cardd_yolo
python train.py --model yolo11s-seg --epochs 100 --batch 16 --imgsz 640
# Hedef: mAP50 ≥ 0.55 (CarDD test). Küçük nesne mAP'sini izle.

# 3. Parça modeli (Ultralytics CarParts-Seg)
python prepare_parts_data.py --use_ultralytics
python train_parts.py --model yolo11s-seg --epochs 100 --batch 16 --imgsz 640

# 4. Şiddet CNN (opsiyonel v1, ensemble v2'de)
# python train_severity.py --backbone efficientnet_v2_s --epochs 50

# 5. Pipeline'ı dene
python pipeline.py \
  --damage_weights runs\arac-hasar\yolo11s-seg\weights\best.pt \
  --parts_weights runs\arac-hasar\parts_yolo11s-seg\weights\best.pt \
  --image test_car.jpg \
  --visualize
```

## Yer/disk gereksinimi

| Veri | Disk |
|---|---|
| CarDD (raw) | ~3 GB |
| CarDD YOLO formatına dönüştürülmüş | ~6 GB |
| CarParts-Seg | ~1.5 GB |
| Roboflow Severity | ~500 MB |
| YOLO11/26 pretrained ağırlıklar (n+s+m) | ~150 MB |
| Eğitim runs (5 epoch'lık checkpoint'ler) | ~2 GB |
| **Toplam minimum** | **~15 GB** |
| Konforlu | 30 GB |

## v0.2 backlog — kendi veri toplama

Pilot süresince:
- 500-1000 Türk araç görüntüsü (Fiat Egea, Renault Symbol, Hyundai i20 vb.)
- CVAT veya Roboflow Annotate ile etiketle
- Mevcut CarDD + parça setlerine ekle, fine-tune
- Türkiye'ye özel hasar tiplerini gözlemle: yan ayna kırıkları, jant hasarı, tuz/pas, kaza sonrası deformasyon

Detaylar: `docs/HAFTA_10_12.md`.
