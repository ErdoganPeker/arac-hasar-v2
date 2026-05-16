# ML Model Guide

Everything about the three machine-learning models powering Hasarİ — performance numbers, when each one runs, known failure modes, and how to retrain.

> Target audience: ML engineers and technical operators. End-user model intuition lives in [USER_GUIDE_TR.md](USER_GUIDE_TR.md#6-sonuçları-anlama).

---

## Pipeline overview

For every uploaded image, three models run **in parallel**, then a deterministic post-processor stitches the outputs into a part-centric JSON:

```
                       ┌──────────────────────────────┐
                       │  Damage YOLO11m-seg          │
                       │  6 classes, segmentation     │
                       │  (where is the damage?)      │
                       └──────────┬───────────────────┘
                                  │
   ┌──────────────────────┐       │                       ┌────────────────────┐
   │ Parts YOLO11s-seg    │       │                       │ For each damage    │
   │ 21 classes, seg      │       │  IoU(damage, part)    │ crop:              │
   │ (which part?)        ├───────┼───────────────────►   │ Severity classifier│
   └──────────────────────┘       │                       │ YOLO11n-cls 3 cls  │
                                  │                       │ (hafif/orta/agir)  │
                                  ▼                       └─────────┬──────────┘
                       ┌──────────────────────────────┐             │
                       │ Match every damage to its    │             │
                       │ best-overlapping part        │◄────────────┘
                       │ → "front_bumper has a dent"  │
                       └──────────┬───────────────────┘
                                  │
                                  ▼
                       ┌──────────────────────────────┐
                       │ Cost engine (lookup table +  │
                       │ part × damage × severity)    │
                       │ → ₺ range per part           │
                       └──────────┬───────────────────┘
                                  │
                                  ▼
                       ┌──────────────────────────────┐
                       │ Aggregate to summary         │
                       │ (totals, recommendation)     │
                       └──────────────────────────────┘
```

End-to-end latency on a single 1920×1080 image, RTX 5050 8GB (Blackwell, sm_120, cu128):

| Stage | Time |
|---|---|
| Image decode + preprocess | ~10 ms |
| Damage YOLO11m-seg | ~45 ms |
| Parts YOLO11s-seg | ~30 ms |
| Severity (per damage crop, avg 3 damages) | ~36 ms total |
| IoU matching + post-processing | ~5 ms |
| Cost engine | ~1 ms |
| **Single-image total** | **~125 ms** |

A typical 4-photo inspection runs sequentially on the worker and finishes in **5–8 seconds** including S3 round trips.

---

## Model 1 — Damage segmentation (YOLO11m-seg)

**What it does**: pixel-level segmentation of damage regions on the car body. Outputs a mask + class label + bounding box + confidence for each damage instance.

### Specs

| Item | Value |
|---|---|
| **Architecture** | YOLO11m-seg (Ultralytics) |
| **Input size** | 640×640 |
| **Parameters** | ~22M |
| **Classes (6)** | `dent`, `scratch`, `crack`, `glass_shatter`, `lamp_broken`, `tire_flat` |
| **Dataset** | CarDD (academic, non-commercial) — ~4 000 labeled images |
| **Epochs trained** | 120 |
| **Optimizer** | SGD with default Ultralytics schedule |
| **Augmentation** | Mosaic + HSV + flip (Ultralytics defaults) |
| **Weights file** | `services/ml/yolo11m-seg.pt` |

### Performance (validation set)

| Metric | Value |
|---|---|
| **mAP50-95 (box)** | 0.491 |
| **mAP50 (box)** | 0.671 |
| **mAP50-95 (mask)** | **0.509** |
| **mAP50 (mask)** | **0.683** |
| **Precision (mask, IoU≥0.5)** | 0.71 |
| **Recall (mask, IoU≥0.5)** | 0.67 |

### Per-class behavior

| Class | mAP50 | Notes |
|---|---|---|
| `dent` | 0.74 | Strongest. Lots of training data, distinctive shape. |
| `scratch` | 0.69 | Mostly good, occasionally confused with cosmetic dirt. |
| `crack` | 0.61 | Plastic crack vs. paint crack ambiguity; thin cracks under-recalled. |
| `glass_shatter` | 0.78 | Very strong — shatter pattern is distinctive. |
| `lamp_broken` | 0.65 | Good when lamp lens is shattered; missed when only a fine crack. |
| `tire_flat` | 0.42 | **Weakest** — only ~80 training instances; needs more data (v0.2). |

### Known failure modes

- **Cosmetic dirt / mud** on bumpers occasionally classified as scratch. Mitigation: instruct users to clean the vehicle (USER_GUIDE rule).
- **Reflective glare** on glass produces phantom `glass_shatter` detections. Confidence threshold ≥ 0.55 reduces this; tune per deployment.
- **Tire flatness** rarely detected — class is included for completeness but should be considered advisory only until v0.2 dataset boost.
- **Wet surfaces** reflect like cracks. Same mitigation as glare.

---

## Model 2 — Parts segmentation (YOLO11s-seg)

**What it does**: pixel-level segmentation of vehicle body parts. Tells us *which* part each damage sits on.

### Specs

| Item | Value |
|---|---|
| **Architecture** | YOLO11s-seg |
| **Input size** | 640×640 |
| **Parameters** | ~10M |
| **Classes (21)** | `back_bumper`, `front_bumper`, `back_door`, `front_left_door`, `front_right_door`, `back_left_door`, `back_right_door`, `back_glass`, `front_glass`, `back_light`, `front_light`, `back_left_light`, `back_right_light`, `front_left_light`, `front_right_light`, `hood`, `trunk`, `tailgate`, `left_mirror`, `right_mirror`, `wheel` |
| **Dataset** | Combined: Roboflow car-parts + supplementary CarPartsDB scrape — ~6 000 images |
| **Epochs trained** | ~50 |
| **Weights file** | `services/ml/yolo11s-seg.pt` |

### Performance (validation set)

| Metric | Value |
|---|---|
| **mAP50 (mask)** | **~0.72** |
| **mAP50-95 (mask)** | ~0.55 |

### Known failure modes

- **Left/right confusion** on doors and headlights when the vehicle is photographed from the rear quarter — the system fuses left/right calls using image orientation heuristics, but it's still a known weak spot.
- **Mirror miss** on small images: the mirror class has ~3% of bounding-box area on average and is sometimes missed on low-resolution input.
- **Trunk vs. tailgate** ambiguity on hatchbacks — both classes can fire on the same region. Post-processor picks the higher-confidence one.

---

## Model 3 — Severity classifier (YOLO11n-cls)

**What it does**: given a tight crop of a single damage region, classify its severity as `hafif` (minor), `orta` (moderate), or `agir` (severe).

### Specs

| Item | Value |
|---|---|
| **Architecture** | YOLO11n-cls |
| **Input size** | 224×224 |
| **Parameters** | ~2.6M |
| **Classes (3)** | `hafif`, `orta`, `agir` |
| **Dataset** | Roboflow Severity dataset — ~1 800 labeled crops |
| **Epochs trained** | 30 |
| **Weights file** | `services/ml/yolo11n-cls.pt` |

### Performance (validation set)

| Metric | Value |
|---|---|
| **Top-1 accuracy** | **0.742** |
| **Macro F1** | 0.71 |
| **Confusion** | Mostly `orta` ↔ `agir`; `hafif` is well-separated. |

### Known failure modes

- **Overfitting tendency**: small dataset means the model is slightly biased toward `orta`. Val accuracy plateaued at ~0.74 — adding more `agir` examples is a v0.2 priority.
- **Crop quality dependency**: if the damage YOLO produces a tight, well-centered crop, classification is reliable. Loose or off-center crops degrade accuracy by ~10%.
- **Glass shatter severity** is currently always classified as `orta` or `agir` — there's no "minor glass shatter" in the training distribution. Acceptable for v0.1.

---

## Cost engine

Not an ML model — a **lookup-table-driven** function:

```
cost(part, damage_type, severity) → (min_tl, max_tl)
```

The table lives at `services/ml/cost_table.yaml` and is calibrated to local Türkiye OEM + aftermarket prices (March 2026). Example entries:

```yaml
front_bumper:
  dent:
    hafif: [400, 1200]
    orta:  [2500, 5500]
    agir:  [6000, 12000]
  scratch:
    hafif: [200, 600]
    orta:  [800, 2000]
    agir:  [2500, 4500]
```

**Why not ML for cost?** Insufficient labeled price data (you need real repair invoices) and the lookup table is more debuggable for pilot use. v0.2 plans an ML regression head once the pilot accumulates ~500 verified inspections with actual repair costs.

---

## Inference configuration

Default thresholds in `services/ml/pipeline.py`:

| Hyperparameter | Default | When to tune |
|---|---|---|
| `damage_conf_threshold` | 0.55 | Lower → more sensitive, more false positives. Raise to 0.65 in noisy environments. |
| `parts_conf_threshold` | 0.5 | Parts model is more reliable; rarely needs tuning. |
| `iou_match_threshold` | 0.15 | How much a damage mask must overlap a part to be assigned to it. Lower = more aggressive matching. |
| `severity_min_crop_size` | 32×32 px | Smaller crops degrade severity accuracy; below this we skip severity and label `bilinmiyor`. |
| `max_damages_per_image` | 25 | Hard cap to prevent runaway false positives. |

To change a threshold per request, pass the override in the API call (planned feature — not yet exposed in v0.1).

---

## Retraining

### Quick: incremental data, same architecture

For weekly fine-tuning runs on top of the existing checkpoint:

```powershell
cd services\ml
# Damage model — 30 more epochs on top of the v0.1 weights
python train.py --resume yolo11m-seg.pt --data cardd.yaml --epochs 30 --batch 8 --device 0

# Parts model
python train_parts.py --resume yolo11s-seg.pt --data parts.yaml --epochs 20 --batch 16 --device 0

# Severity classifier
python train_severity.py --resume yolo11n-cls.pt --data data/severity --epochs 15 --batch 32 --device 0
```

### Full: clean retrain from pre-trained YOLO11

For a major version bump (v0.2 → v0.3):

```powershell
cd services\ml
python train_all.py --full --device 0
```

`train_all.py --full` runs all three trainings sequentially and logs to `services/ml/runs/` and `services/ml/logs/`. It will:

1. Download pre-trained YOLO11 base weights if missing.
2. Train damage model for 120 epochs.
3. Train parts model for 50 epochs.
4. Train severity classifier for 30 epochs.
5. Run the regression test suite (`tools/regression_test.py`) and write a comparison report against the previous deployment.

**Wall-clock time** on RTX 5050 8GB: ~14 hours for the full run.

### Dataset refresh

Before retraining, refresh datasets:

```powershell
# CarDD — re-download if upstream HuggingFace mirror updated
python scripts\download_data.py --cardd-hf --force

# Roboflow severity — set API key first
$env:ROBOFLOW_API_KEY = "..."
python scripts\download_data.py --roboflow-severity --force

# Pilot in-the-wild data (if you've collected labeled images from pilot users)
python scripts\merge_pilot_data.py --in pilot_inspections.csv --out data/pilot/
python scripts\verify_data.py --datasets cardd pilot
```

### Validating a new checkpoint

Always run the regression suite before promoting:

```powershell
python tools\regression_test.py `
  --baseline services\ml\runs\v0.1\weights\best.pt `
  --candidate services\ml\runs\v0.2\weights\best.pt `
  --fixtures tools\fixtures\regression\
```

The regression suite scores both models on 200 hand-curated images and fails the build if any of these regresses by >2%:
- mAP50 (mask) per class
- IoU matching accuracy (does each damage land on the right part?)
- Total cost variance (is the new model producing drastically different cost ranges?)

### Promoting weights to production

1. Copy the new `.pt` files to a versioned S3 location:
   ```bash
   aws s3 cp services/ml/runs/v0.2/weights/best.pt s3://hasari-models/v0.2/yolo11m-seg.pt
   ```
2. Update `ML_MODEL_VERSION=v0.2` env var on the Render API service.
3. The backend reads `ML_MODEL_VERSION` at startup and downloads the matching weights from S3.
4. Smoke-test on staging before pointing production at the new version.
5. Keep the previous version (`v0.1`) on S3 for instant rollback.

### Export for on-device (mobile, v0.2 backlog)

```powershell
cd tools
python export.py --model yolo11n-seg.pt --format tflite --output models/damage_yolo11n.tflite
python export.py --model yolo11n-seg.pt --format coreml --output models/damage_yolo11n.mlpackage
```

Output models are quantized to int8 by default — ~3 MB, runs at ~80 ms on iPhone 13 Neural Engine.

---

## Hardware requirements

### Training (full pipeline)

- **GPU**: NVIDIA, ≥8 GB VRAM (Blackwell architecture or newer recommended for sm_120 features)
- **CUDA**: 12.8+
- **PyTorch**: 2.4+ with `cu128` wheels (see `services/ml/setup.ps1` / `setup.sh` — Blackwell support is non-trivial)
- **RAM**: 32 GB
- **CPU**: ≥8 cores (for data loader workers)
- **Disk**: 50 GB free (datasets + checkpoints)

### Inference

- **GPU (preferred)**: 4 GB VRAM minimum
- **CPU-only (acceptable)**: any modern x86_64; ~5–10× slower than GPU. Used in the Render-hosted pilot until GPU host is provisioned.

---

## Telemetry: what we measure in production

Every inference logs:

- Per-model wall time (`damage_ms`, `parts_ms`, `severity_ms`, `total_ms`)
- Per-image counts: detected damages, detected parts, matched/unmatched damages
- Confidence-score distributions (P50, P95) per class
- Image dimensions and file size
- Failure category if the inference errors out

These flow to Prometheus and are visible in the Grafana "ML Pipeline" dashboard (config in `observability/grafana/dashboards/ml-pipeline.json`).

Use this data to:
- Set alerts when P95 latency drifts upward (often signals model loading wrong weights)
- Identify class drift (sudden drop in `dent` confidences usually means input distribution shifted — new car models, new camera type)
- Schedule retraining when false-positive rate creeps above 5% per a sampled human review.

---

## Limitations & honest caveats

- **English vehicles only**: training data is heavily biased toward Western and Turkish-market cars. SUVs and pickups from non-Turkish markets may underperform.
- **Night / low-light**: no IR or HDR training data. Below ~100 lux the system degrades quickly. Recommend rejecting low-light photos in v0.2.
- **Multiple vehicles per image**: the pipeline assumes one car. If two cars are in frame, parts and damages from both are merged — output is unreliable. Pre-check (planned) will reject multi-vehicle images.
- **Severity ground truth is subjective**: even human raters disagree ~15% of the time on `orta` vs. `agir`. A 74% accuracy is close to inter-rater agreement on this dataset.
- **Cost calibration drifts with inflation / FX**: re-calibrate `cost_table.yaml` quarterly.

---

## Related docs

- [DATA.md](../DATA.md) — dataset sources, licenses, train/val splits
- [ARCHITECTURE.md](../ARCHITECTURE.md) — pipeline internals at code level
- [services/ml/setup.ps1](../services/ml/setup.ps1) / [setup.sh](../services/ml/setup.sh) — ML environment bootstrap
- [tools/regression_test.py](../tools/regression_test.py) — pre-promotion validation
