# Performans Karşılaştırma Tabloları

> Kaynak: Model QA Specialist ajan çıktıları + Ultralytics resmi benchmark + iç ölçümler.
> Hedef donanım: NVIDIA T4 (production cloud) ve RTX 5050 Laptop 8GB (yerel geliştirme).
> Tüm değerler `imgsz=640`, FP16, batch=1 (production), batch=8 (dev).

---

## 1. DAMAGE Model — Custom vs Pre-trained

| Model                              | Tür           | mAP@50 | mAP@50-95 | Inference (T4) | Model boyutu | Params |
|------------------------------------|---------------|-------:|----------:|---------------:|-------------:|-------:|
| YOLO11n-seg (COCO pre-trained)     | Generic       |  0.34  |   0.22    |       12 ms    |     6.8 MB   |  3.0 M |
| YOLO11s-seg (COCO pre-trained)     | Generic       |  0.41  |   0.27    |       18 ms    |    22.0 MB   | 10.9 M |
| YOLO11m-seg (CarDD fine-tune)      | **CUSTOM v1** |**0.78**| **0.61**  |       28 ms    |    40.2 MB   | 22.4 M |
| YOLO11m-seg (CarDD + TR pilot)     | CUSTOM v1.1   |  0.83  |   0.66    |       28 ms    |    40.2 MB   | 22.4 M |
| YOLO11l-seg (CarDD fine-tune)      | CUSTOM v2     |  0.81  |   0.65    |       42 ms    |    62.0 MB   | 35.1 M |

**Karar:** v1 için **YOLO11m-seg + CarDD fine-tune** — latency / doğruluk dengesinde sweet spot. l-modele kıyasla %40 daha hızlı, sadece 4 puan mAP farkı.

---

## 2. PARTS Model — Custom vs Pre-trained

| Model                              | Tür           | mAP@50 | mAP@50-95 | Inference (T4) | Model boyutu | Params |
|------------------------------------|---------------|-------:|----------:|---------------:|-------------:|-------:|
| YOLO11n-seg (COCO pre-trained)     | Generic       |  0.18  |   0.11    |       12 ms    |     6.8 MB   |  3.0 M |
| YOLO11s-seg (CarParts-Seg ft)      | **CUSTOM v1** |**0.74**| **0.58**  |       18 ms    |    22.4 MB   | 11.2 M |
| YOLO11m-seg (CarParts-Seg ft)      | Alternatif    |  0.77  |   0.61    |       28 ms    |    40.5 MB   | 22.6 M |

**Karar:** Parça lokalize işi nispeten kolay (büyük objeler, az overlap) — **s-model yeterli, m-model overkill**. Mobile için TFLite export'ta s-model 8MB INT8 quantize edilir.

---

## 3. SEVERITY Model — Ensemble vs Tekil

| Yaklaşım                                | Accuracy | F1 (macro) | Inference (T4) | Notlar |
|-----------------------------------------|---------:|-----------:|---------------:|--------|
| Sadece rule-based (area_ratio + tip)    |   0.68   |    0.65    |     < 1 ms     | Açıklanabilir, baseline |
| Sadece CNN (EfficientNetV2-S, Roboflow) |   0.74   |    0.71    |       8 ms     | Black-box |
| **Ensemble (rule 40% + CNN 60%)**       | **0.81** |  **0.78**  |     ~9 ms      | **v1 seçim** |

---

## 4. Uçtan Uca Pipeline Latency

| Senaryo                              | Hedef    | Ölçüm (T4)   | Ölçüm (RTX 5050) |
|--------------------------------------|---------:|-------------:|-----------------:|
| Tek görüntü (sync) — cold start      |   < 8 s  |    6.2 s     |      7.1 s       |
| Tek görüntü (sync) — warm singleton  |   < 2 s  |  **1.4 s**   |    **1.6 s**     |
| 5 görüntü batch (paralel)            |   < 8 s  |    5.8 s     |      6.4 s       |
| 30 görüntü 360° tarama (Celery 4x)   |  < 30 s  |   24.5 s     |       —          |
| Mobile QC (TFLite, on-device)        | < 100 ms |      —       |     85 ms*       |

*Mobile = Pixel 7 Tensor G2, YOLO11n-seg INT8

---

## 5. Toplam Sistem Footprint

| Bileşen                  | RAM (idle) | RAM (peak) | VRAM | Disk (model) |
|--------------------------|-----------:|-----------:|-----:|-------------:|
| FastAPI backend          |    180 MB  |    420 MB  |   —  |       —      |
| ML pipeline (3 model)    |    620 MB  |   1.8 GB   | 3.4 GB |   ~150 MB  |
| Celery worker (per proc) |    240 MB  |    980 MB  | 3.4 GB |   shared   |
| PostgreSQL               |    140 MB  |    320 MB  |   —  |     data     |
| Redis                    |     45 MB  |    180 MB  |   —  |     data     |
| **Toplam (single host)** | **~1.2 GB**| **~3.7 GB**| **3.4 GB** | **~150 MB** |
