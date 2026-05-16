# Pre-trained Models Registry

Bu dosya `services/ml/pretrained_registry.py` icindeki tum pre-trained model
entry'lerinin kanonik dokumantasyonu. Document Generator ajani buradan rapor
seksiyonlarini uretir. Tum modeller frontend toggle'i ("Model: Pre-trained /
Kendi Modellerim") uzerinden secilebilir; her birinin output'u custom
modelimizin v2 semasiyla uyumlu hale getirilir (adapter pattern).

## Ozet Tablo

| ID                                  | Kaynak       | Rol               | Lisans       | Boyut (MB) | mAP / Acc hint    |
|-------------------------------------|--------------|-------------------|--------------|------------|-------------------|
| `ultralytics_yolo11n_seg`           | Ultralytics  | vehicle (COCO-80) | AGPL-3.0     | 5.9        | seg mAP ~32.0     |
| `ultralytics_yolo11m_seg`           | Ultralytics  | vehicle (COCO-80) | AGPL-3.0     | 43.7       | seg mAP ~43.0     |
| `roboflow_cardd_scratch_dent`       | Roboflow     | damage            | CC-BY-4.0    | 22.0       | mAP50 ~0.78       |
| `roboflow_car_parts_seg`            | Roboflow     | parts             | CC-BY-4.0    | 26.0       | seg mAP50 ~0.71   |
| `roboflow_cardd_severity`           | Roboflow     | severity          | CC-BY-4.0    | 15.0       | cls acc ~0.82     |
| `hf_dima806_car_damage_cls`         | HuggingFace  | damage_classifier | Apache-2.0   | 346.0      | val acc ~0.95     |
| **TOPLAM**                          |              |                   |              | **~458**   |                   |

Roboflow modelleri yalnizca `ROBOFLOW_API_KEY` env tanimliysa indirilebilir.

## Composite Model Sources (UI Toggle Secenekleri)

`ModelSource` registry'sinden gelen ve frontend dropdown'inda gorunen
secenekler:

| Source ID                              | Kapsam                                    | Fallback to Custom |
|----------------------------------------|-------------------------------------------|--------------------|
| `custom`                               | Bizim 3 finetune model (default)          | —                  |
| `pretrained_ultralytics_yolo11m`       | Yalniz COCO-80 vehicle silhouette         | (none)             |
| `pretrained_roboflow_cardd`            | Roboflow damage + parts + severity        | severity           |
| `pretrained_hybrid`                    | Ultralytics + Roboflow karma              | severity           |

## Entry Detaylari

### 1. Ultralytics YOLO11n-seg (COCO)
- **Source URL**: https://docs.ultralytics.com/models/yolo11/
- **License**: AGPL-3.0 (ticari kullanim icin Ultralytics Enterprise lisansi gerekir)
- **Classes (80)**: car, truck, bus, motorcycle, bicycle, person, ... (full COCO)
- **mAP**: COCO val mAP50-95 ~38.9 (box), seg mAP ~32.0
- **Intended use**: Sahne validasyonu — "gercekten araç var mı?" baseline.
  Hasar tespiti yapmaz; pre-trained pipeline icinde sadece `vehicle` rolu.
- **Auto-download**: Ultralytics paketi CDN'den otomatik ceker. Local cache:
  `~/.cache/ultralytics/yolo11n-seg.pt`.

### 2. Ultralytics YOLO11m-seg (COCO)
- Aynı kaynak ve sınıflar; daha buyuk model. seg mAP ~43.0.
- Daha dogru arac silueti tespiti icin tercih.

### 3. Roboflow Car Scratch & Dent
- **Source URL**: https://universe.roboflow.com/carpro/car-scratch-and-dent
- **License**: CC-BY-4.0 (atif zorunlu, ticari OK)
- **Classes (2)**: scratch, dent
- **Accuracy hint**: Yayinci raporu mAP@50 ~0.78
- **Intended use**: Iki sinifli hasar detection. Cam/lamba kirilmasi gibi
  hasarlari tespit etmez — bizim CarDD'den dar kapsamli.
- **API**: workspace=`carpro`, project=`car-scratch-and-dent`, version=3,
  format=`yolov8`.

### 4. Roboflow Car Parts Segmentation
- **Source URL**: https://universe.roboflow.com/popular-benchmarks/car-parts-segmentation
- **License**: CC-BY-4.0
- **Classes (~10)**: front_bumper, back_bumper, hood, front_door, back_door,
  front_light, back_light, windshield, fender, trunk
- **Accuracy hint**: seg mAP@50 ~0.71
- **Intended use**: Parca segmentasyonu. Adapter `windshield`->`front_glass`,
  `rear_window`->`back_glass` gibi remap'leri uygular (bkz.
  `model_manager.PARTS_REMAP`).

### 5. Roboflow Car Damage Severity
- **Source URL**: https://universe.roboflow.com/sreevishnu-damarla/car-damage-severity-mr5kk
- **License**: CC-BY-4.0
- **Classes (3)**: minor, moderate, severe -> adapter ile hafif/orta/agir
- **Accuracy hint**: cls accuracy ~0.82
- **Intended use**: Crop tabanli 3-sinifli siddet tahmini.

### 6. HuggingFace dima806/car_damage_image_detection
- **Source URL**: https://huggingface.co/dima806/car_damage_image_detection
- **License**: Apache-2.0 (ticari OK, atif iyilesim)
- **Classes (2)**: damaged, not_damaged
- **Accuracy hint**: val accuracy ~0.95 (yayinci raporu)
- **Intended use**: Triage on-filter. Hasar yoksa pipeline'i tamamen atlatmak
  icin ucuz bir ikili sinif. Detection yapmaz.

## Disk Kullanim Ozeti

| Klasor                                    | Icerik                            | Toplam   |
|-------------------------------------------|-----------------------------------|----------|
| `services/ml/runs/.../damage_best.pt`     | Custom damage (YOLO11m-seg)       | 45 MB    |
| `services/ml/runs/.../parts_best.pt`      | Custom parts (YOLO11s-seg)        | 81 MB    |
| `services/ml/runs/.../severity_best.pt`   | Custom severity (CNN)             | 16 MB    |
| **Custom toplam**                         |                                   | **~142 MB** |
| `services/ml/pretrained/` (registry)      | Ultralytics + Roboflow + HF       | ~458 MB  |
| **Genel toplam**                          |                                   | **~600 MB** |

HF entry'si opsiyonel; cikarilirsa toplam ~250 MB'a duser.

## Adapter ve Output Uyumlulugu

Tum pre-trained modeller cikti olarak custom pipeline'in v2 semasiyla aynı
sozlesmeyi dondurur. Class adlari `model_manager.PARTS_REMAP`,
`DAMAGE_TYPE_REMAP`, `SEVERITY_REMAP` tablolarinda Turkce / kanonik
isimlere cevrilir. Sonuc dict'inde ek olarak:

```json
{
  "model_source": "pretrained_roboflow_cardd",
  "model_versions": {
    "pretrained_source": {
      "id": "pretrained_roboflow_cardd",
      "name": "Pre-trained: Roboflow CarDD Pipeline",
      "entries": [
        {"id": "roboflow_cardd_scratch_dent", "name": "Roboflow Car Scratch & Dent"},
        ...
      ]
    }
  }
}
```

alanlari yer alir — rapor uretiminde "Bu inceleme X modeliyle yapildi" ifadesi
icin kullanilabilir.

## Indirme

```bash
# Sadece registry entry'leri (frontend toggle):
python scripts/download_pretrained.py --registry

# Tum modeller (eski yolo11/26 backbone'lar dahil):
python scripts/download_pretrained.py --all

# Sadece plan goster:
python scripts/download_pretrained.py --all --dry-run
```

`ROBOFLOW_API_KEY` env yoksa Roboflow entry'leri atlanir; Ultralytics public
weights auto-fetch ile cekilir.

## Etik / Lisans Notlari

- **Ultralytics AGPL-3.0**: ticari kullanim icin Enterprise lisansi gerekir.
  MVP demo / arastirma asamasinda sorun degil; production deploy oncesi
  lisans degerlendirilmeli.
- **Roboflow CC-BY-4.0**: rapor PDF'lerinde mutlaka atif zorunlu (model
  ismi + source_url).
- **HuggingFace Apache-2.0**: ticari OK, atif istenir.
- Tum bu modeller bagimsiz dataset'ler uzerinde egitildi; sahaya ozgu (TR
  araclar, lokal isiklandirma) performansi custom modelimizden dusuk olabilir.
