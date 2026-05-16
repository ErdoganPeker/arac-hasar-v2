# Hafta 1–3 Detaylı Rehber: CarDD Üzerinde Baseline YOLO26-seg

Bu rehber, araç hasar tespiti MVP'sinin **temel modelini** kurmak için ilk üç haftalık planı, çalışan kod ile birlikte adım adım anlatır.

## Hedefler (Faz 1 sonu)

- CarDD veri setinde YOLO26-seg ile eğitilmiş, mAP50 ≥ 0.55 olan bir baseline model
- Tekrar üretilebilir veri prep + eğitim + değerlendirme pipeline'ı
- Hata analizi (hangi sınıf neyle karışıyor, küçük nesneler nerede başarısız)
- Bir sonraki haftalara temel olacak proje iskeleti

## Proje Yapısı

Bu rehberle birlikte gelen dosyalar:

```
mvp-arac-hasar/
├── HAFTA_1_3_REHBER.md         # Bu dosya
├── setup.sh                     # Ortam kurulumu
├── prepare_data.py              # CarDD → YOLO format dönüşümü
├── train.py                     # YOLO26-seg eğitimi
├── evaluate.py                  # Test + hata analizi
├── inference_demo.py            # Tek görüntü üzerinde demo
└── cardd.yaml                   # YOLO veri konfigi
```

Tüm dosyaları aynı klasöre koyup şu sırayla çalıştır: `setup.sh` → `prepare_data.py` → `train.py` → `evaluate.py`.

---

## Hafta 1: Kurulum ve Veri Hazırlığı

### Gün 1–2: Donanım ve ortam

**Seçenek A — Yerel GPU (RTX 3090/4090 veya benzeri):**
```bash
chmod +x setup.sh
./setup.sh
```

**Seçenek B — Google Colab Pro+ (A100):**
Notebook'un başında:
```python
!pip install -q ultralytics fiftyone pycocotools wandb
from google.colab import drive
drive.mount('/content/drive')
```

**Seçenek C — RunPod / Vast.ai (saatlik A100/H100):**
PyTorch 2.x image'ı seç, ardından `./setup.sh`. SSH ile bağlanıp `tmux` içinde eğitim koştur — bağlantı kopsa bile devam eder.

### Gün 3: CarDD'yi indir

CarDD halka açık fakat manuel başvuru gerektirir. İki yol:

**Yol 1 — Resmi (önerilen):** [cardd-ustc.github.io](https://cardd-ustc.github.io) üzerinden form doldur, indirme linki gelir. Dosya `CarDD_release.zip` (~3.5 GB).

**Yol 2 — Hugging Face mirror:**
```bash
pip install huggingface_hub
huggingface-cli download harpreetsahota/CarDD --repo-type dataset \
  --local-dir ./data/CarDD_raw
```

İndirdikten sonra yapı şöyle olmalı:
```
data/CarDD_release/CarDD_COCO/
├── annotations/
│   ├── instances_train2017.json
│   ├── instances_val2017.json
│   └── instances_test2017.json
├── train2017/   # ~2800 görüntü
├── val2017/     # ~400 görüntü
└── test2017/    # ~800 görüntü
```

### Gün 4: Veri keşfi (FiftyOne ile)

```python
import fiftyone as fo
import fiftyone.utils.coco as fouc

dataset = fo.Dataset.from_dir(
    dataset_type=fo.types.COCODetectionDataset,
    data_path="data/CarDD_release/CarDD_COCO/train2017",
    labels_path="data/CarDD_release/CarDD_COCO/annotations/instances_train2017.json",
    name="cardd_train",
)
session = fo.launch_app(dataset)
```

Tarayıcıda http://localhost:5151 açılır. Burada şunları kontrol et:
- Sınıf dağılımı dengeli mi? (genelde scratch+dent çoğunlukta)
- Etiketleme tutarlı mı? (manuel olarak 50 örnek incele)
- Görüntü kalitesi (blur, ekstrem ışık)
- Çözünürlük dağılımı

### Gün 5: YOLO formatına dönüş

```bash
python prepare_data.py \
    --cardd_root data/CarDD_release/CarDD_COCO \
    --output_dir data/cardd_yolo
```

Bu script COCO segmentation poligonlarını YOLO seg formatına çevirir:
```
data/cardd_yolo/
├── images/
│   ├── train/ val/ test/
└── labels/
    ├── train/ val/ test/
```

YOLO segmentation label formatı: her satır `class_id x1 y1 x2 y2 ... xn yn` (0-1 arası normalize).

---

## Hafta 2: Baseline Eğitim

### Gün 1: İlk eğitim — küçük model

Önce `yolo26n-seg` ile (nano, ~5MB) hızlı bir deneme yapalım:

```bash
python train.py --model yolo26n-seg --epochs 50 --imgsz 640 --batch 32
```

Bu ~30-60 dakika sürer (RTX 4090'da). Çıkan modelin mAP50'sine bakıp veri pipeline'ının düzgün çalıştığını doğrula.

### Gün 2–3: Ana eğitim — orta model

```bash
python train.py --model yolo26m-seg --epochs 150 --imgsz 640 --batch 16 \
    --optimizer AdamW --lr0 0.001 --weight_decay 0.0005 \
    --mosaic 1.0 --mixup 0.1 --copy_paste 0.3
```

Bu ~4-8 saat sürer. `wandb` veya tensorboard ile loss eğrilerini izle.

### Gün 4: Hyperparameter sweep

Üç önemli kararı dene:
- `imgsz`: 640 vs 1024 (yüksek çözünürlük küçük çizik tespiti için kritik)
- `batch`: GPU'na göre maksimuma çek (mixed precision ile büyüt)
- `lr0`: 0.001 vs 0.0005 vs 0.002

```bash
# Yüksek çözünürlük denemesi
python train.py --model yolo26m-seg --epochs 150 --imgsz 1024 --batch 8
```

### Gün 5: En iyi modeli seç

`runs/segment/train*/weights/best.pt` altındakileri karşılaştır:
- Hangisinin val mAP50'si en yüksek
- Hangisi küçük nesnede (mAP_small) iyi
- İnference hızı kabul edilebilir mi

---

## Hafta 3: Değerlendirme ve İyileştirme

### Gün 1–2: Test seti değerlendirmesi

```bash
python evaluate.py --weights runs/segment/train/weights/best.pt \
    --data cardd.yaml --split test --save_failures
```

Bu üretir:
- Per-class precision/recall/mAP
- Confusion matrix (PNG)
- `failures/` klasöründe yanlış tahmin yapılan ilk 100 örnek

### Gün 3: Hata analizi

Hata tipleri:
1. **False negatives (kaçırılan hasar):** çoğunlukla küçük çizikler, ince çatlaklar
2. **False positives (yanlış alarm):** gölge → dent, yansıma → scratch klasiktir
3. **Sınıf karışıklığı:** dent ↔ scratch ayrımı zor
4. **Lokalizasyon hatası:** maske doğru ama bounding box kayık

Her tip için ne yapılır:
- Küçük nesne kaçırma → `imgsz` artır, P2 head ekle
- Gölge/yansıma → daha çok augmentation (HSV, brightness)
- Sınıf karışıklığı → class weights ayarla, focal loss
- Maske kalitesi → mask loss weight artır

### Gün 4: İkinci iterasyon

```bash
# Düzeltilmiş hyperparams ile yeni eğitim
python train.py --model yolo26m-seg --epochs 200 --imgsz 1024 \
    --batch 8 --hsv_v 0.6 --hsv_s 0.7 \
    --cls_weights "1.0,1.2,1.5,1.0,1.0,1.0"
# scratch ve crack için ağırlık artırıldı
```

### Gün 5: Karar noktası

Hedef metrikler (CarDD test seti):
- **mAP50 (bbox):** ≥ 0.55 (literatür baseline)
- **mAP50 (seg):** ≥ 0.45
- **mAP_small:** ≥ 0.25 (en zor metrik)
- **Inference latency:** ≤ 100ms (T4 GPU'da)

Bu hedeflere ulaşırsan Faz 2'ye (parça segmentasyonu) geç. Ulaşamadıysan:
- Veri augmentation'ını agresifleştir
- Pretrain ağırlığını değiştir (COCO yerine OpenImages?)
- Ek veri ekle (Roboflow Universe'den 1-2 set)

---

## Yaygın Hatalar ve Çözümleri

**CUDA out of memory:** `batch` küçült veya `imgsz` düşür. AMP zaten açık olmalı.

**Train loss düşüyor, val mAP yerinde duruyor:** Overfitting. Daha çok augmentation, daha az epoch, veya dropout artır.

**Belirli bir sınıfta sıfıra yakın mAP:** Etiket gürültüsü olabilir. FiftyOne'da o sınıfın 50 örneğini gözden geçir.

**FiftyOne açılmıyor / port hatası:** `fo.launch_app(dataset, port=5152)`.

**COCO annotation parse hatası:** `pycocotools` sürümü güncel mi? `pip install -U pycocotools`.

---

## Sonraki Adım

Hafta 3 sonunda elinde:
- Çalışan `best.pt` (hasar tespiti)
- Test metrikleri
- Bilinen failure mode'lar listesi

Hafta 4'te parça segmentasyon modelini ekleyip iki modeli birleştireceğiz (DSMLR Car Parts üzerinde benzer akış). Hafta 5'te şiddet sınıflandırıcı.

İhtiyacın olursa bu rehberde her komutu detaylandırırım.
