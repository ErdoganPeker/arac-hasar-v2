"""
train_all.py - Tek komutla: damage-seg + parts-seg + severity-cls egitir,
modelleri tek bundle'a koyar, hibrit (damages-listesi + parts-merkezli) JSON
ureten smoke inference calistirir.

Iki mod:
  --quick   2-3 dakikalik smoke test (kucuk dataset fraction + 1-2 epoch)
  --full    Production egitim (default 100 epoch, full dataset)

Ornek:
  # Hizli smoke test (RTX 5050 ~2 dk):
  python train_all.py --quick

  # Tam egitim (RTX 5050 ~6-8 saat):
  python train_all.py --full --damage_epochs 100 --parts_epochs 100 --severity_epochs 50

  # Sadece bir-iki adim:
  python train_all.py --quick --skip_parts --skip_severity

Cikti yapisi:
  runs/bundle_<timestamp>/
    ├── damage/weights/best.pt
    ├── parts/weights/best.pt
    ├── severity/weights/best.pt
    ├── manifest.json          # tum yollar + metrikler + smoke sonuc
    ├── smoke_inference.json   # ornek hibrit cikti
    └── smoke_inference.jpg    # annotated overlay
"""
from __future__ import annotations

import argparse
import gc
import json
import random
import shutil
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLO

DONE_SENTINEL = "DONE"
ML_DIR = Path(__file__).resolve().parent
DEFAULT_BUNDLE_ROOT = ML_DIR / "runs" / "bundles"

CARDD_YAML = ML_DIR / "data" / "cardd_yolo" / "cardd.yaml"
CARDD_VAL_DIR = ML_DIR / "data" / "cardd_yolo" / "images" / "val"

PARTS_DATA_YAML = "carparts-seg.yaml"  # Ultralytics auto-download

SEVERITY_RAW_DIR = ML_DIR / "data" / "severity_roboflow" / "Car-Damage-Severity-Assessment-6"
SEVERITY_YOLO_DIR = ML_DIR / "data" / "severity_yolocls"  # train/val klasorlu YOLO-cls format

CARDD_CLASSES = ["dent", "scratch", "crack", "glass_shatter", "lamp_broken", "tire_flat"]

PART_NAME_TR = {
    "back_bumper": "Arka tampon", "back_door": "Arka kapi", "back_glass": "Arka cam",
    "back_left_door": "Arka sol kapi", "back_left_light": "Arka sol stop",
    "back_light": "Arka stop", "back_right_door": "Arka sag kapi",
    "back_right_light": "Arka sag stop", "front_bumper": "On tampon",
    "front_glass": "On cam", "front_left_door": "On sol kapi",
    "front_left_light": "On sol far", "front_light": "On far",
    "front_right_door": "On sag kapi", "front_right_light": "On sag far",
    "hood": "Kaput", "left_mirror": "Sol ayna", "right_mirror": "Sag ayna",
    "tailgate": "Bagaj kapagi", "trunk": "Bagaj", "wheel": "Tekerlek",
    "unknown": "Bilinmeyen",
}

DAMAGE_TR = {
    "dent": "Gocuk", "scratch": "Cizik", "crack": "Catlak",
    "glass_shatter": "Cam kirilmasi", "lamp_broken": "Far kirilmasi",
    "tire_flat": "Lastik patlak",
}

# severity_classifier.py ile birebir
PART_IMPORTANCE = {
    "front_bumper": 1.2, "back_bumper": 1.1, "hood": 1.4,
    "front_glass": 1.6, "back_glass": 1.3,
    "front_left_door": 1.2, "front_right_door": 1.2,
    "back_left_door": 1.1, "back_right_door": 1.1,
    "front_left_light": 1.3, "front_right_light": 1.3,
    "back_left_light": 1.1, "back_right_light": 1.1,
    "front_light": 1.3, "back_light": 1.1,
    "left_mirror": 0.9, "right_mirror": 0.9,
    "tailgate": 1.2, "trunk": 1.2, "wheel": 1.0, "unknown": 1.0,
}
DAMAGE_TYPE_WEIGHT = {
    "scratch": 0.6, "dent": 1.0, "crack": 1.4,
    "glass_shatter": 2.0, "lamp_broken": 1.8, "tire_flat": 1.5,
}
SEVERITY_LEVELS = ["hafif", "orta", "agir"]

# Iskelet maliyet tablosu (cost_table.yaml senin TR data ile zenginlesir)
COST_FALLBACK = {
    ("front_bumper", "dent"): (3500, 7500),
    ("front_bumper", "scratch"): (1200, 3500),
    ("hood", "dent"): (4500, 9000),
    ("front_glass", "crack"): (3500, 6500),
    ("front_glass", "glass_shatter"): (5000, 9500),
    ("front_light", "lamp_broken"): (4000, 12000),
    ("wheel", "tire_flat"): (1500, 3500),
}
GLOBAL_COST_DEFAULT = (1500, 5000)


# -------------------- yardimcilar --------------------

def header(msg: str):
    print("\n" + "=" * 78)
    print(f"  {msg}")
    print("=" * 78)


def assert_gpu(allow_cpu: bool = False):
    """GPU zorunlu - CUDA yoksa hizli olum (allow_cpu=True ile bypass)."""
    if torch.cuda.is_available():
        return
    msg = (
        "\n[FATAL] CUDA bulunamadi. Bu pipeline GPU zorunlu calismak icin tasarlandi.\n"
        "  - torch CUDA'siz mi kuruldu? `python -c \"import torch; print(torch.cuda.is_available())\"`\n"
        "  - Driver/CUDA toolkit yuklu mu? `nvidia-smi`\n"
        "  - Blackwell (RTX 5050) cu128 wheel gerektirir.\n"
        "  CPU'da denemek istersen: --allow_cpu (cok yavas, onerilmez)\n"
    )
    if allow_cpu:
        print(msg + "  --allow_cpu verildigi icin devam ediliyor (CPU).\n")
        return
    print(msg)
    sys.exit(2)


def gpu_info():
    if not torch.cuda.is_available():
        return "CPU mode (CUDA yok!)"
    name = torch.cuda.get_device_name(0)
    props = torch.cuda.get_device_properties(0)
    vram_gb = props.total_memory / 1024**3
    cc = f"{props.major}.{props.minor}"
    return f"GPU: {name} | VRAM: {vram_gb:.1f} GB | CC: sm_{cc} | torch: {torch.__version__}"


def gpu_mem_used() -> str:
    if not torch.cuda.is_available():
        return "n/a"
    used = torch.cuda.memory_allocated() / 1024**3
    reserved = torch.cuda.memory_reserved() / 1024**3
    return f"alloc={used:.2f}GB reserved={reserved:.2f}GB"


def release_gpu(*objs):
    """Modeller arasi GPU bellek temizligi - OOM zinciri onlemek icin kritik."""
    for o in objs:
        try:
            del o
        except Exception:
            pass
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()


def find_resume_target(bundle_dir: Path, model_name: str) -> Path | None:
    """Bir modelin yarim kalmis bir last.pt'sini dondur (DONE sentinel yoksa)."""
    done = bundle_dir / model_name / DONE_SENTINEL
    if done.exists():
        return None
    last = bundle_dir / model_name / "weights" / "last.pt"
    return last if last.exists() else None


def find_latest_full_bundle(bundle_root: Path) -> Path | None:
    """En son 'full_*' bundle dir'i bul (resume icin)."""
    if not bundle_root.exists():
        return None
    candidates = sorted(bundle_root.glob("full_*"), key=lambda p: p.stat().st_mtime)
    return candidates[-1] if candidates else None


def mark_done(bundle_dir: Path, model_name: str):
    (bundle_dir / model_name / DONE_SENTINEL).touch()


def prepare_severity_yolocls(quick: bool) -> Path | None:
    """Roboflow severity_dir'i YOLO-cls bekledigi train/val/test/<class>/ formatina copyala.

    YOLO-cls 'val' bekler, Roboflow 'valid' kullanir → yeniden adlandir.
    Quick modda her sinifa max 30 ornek (hizli train icin).
    """
    if not SEVERITY_RAW_DIR.exists():
        print(f"  [!] Severity raw yok: {SEVERITY_RAW_DIR}")
        return None

    needed = {"train": "train", "val": "valid", "test": "test"}
    if SEVERITY_YOLO_DIR.exists():
        # icindeki tum split + class klasorleri var mi?
        ok = all((SEVERITY_YOLO_DIR / split).exists() for split in needed)
        if ok and not quick:
            return SEVERITY_YOLO_DIR
        if ok and quick:
            # quick'te her zaman yeniden uret (ornek sayisi farkli olabilir)
            shutil.rmtree(SEVERITY_YOLO_DIR)

    SEVERITY_YOLO_DIR.mkdir(parents=True, exist_ok=True)
    classes = sorted([d.name for d in (SEVERITY_RAW_DIR / "train").iterdir() if d.is_dir()])

    for split, src_split in needed.items():
        src = SEVERITY_RAW_DIR / src_split
        if not src.exists():
            print(f"  [!] split yok: {src}")
            continue
        for cls in classes:
            src_cls = src / cls
            dst_cls = SEVERITY_YOLO_DIR / split / cls
            dst_cls.mkdir(parents=True, exist_ok=True)
            imgs = sorted(src_cls.glob("*.*"))
            if quick and split == "train":
                imgs = imgs[:30]
            elif quick:
                imgs = imgs[:10]
            for img in imgs:
                tgt = dst_cls / img.name
                if not tgt.exists():
                    shutil.copy2(img, tgt)
        n_train = sum(len(list((SEVERITY_YOLO_DIR / split / c).glob("*.*"))) for c in classes)
        print(f"  [+] severity {split}: {n_train} ornek ({len(classes)} sinif)")

    return SEVERITY_YOLO_DIR


# -------------------- egitim adimlari --------------------

def train_damage(args, bundle_dir: Path) -> dict:
    header(f"1/3  Damage segmentation ({args.damage_model})")
    if not CARDD_YAML.exists():
        raise FileNotFoundError(f"cardd.yaml yok: {CARDD_YAML}")

    if (bundle_dir / "damage" / DONE_SENTINEL).exists():
        weights = bundle_dir / "damage" / "weights" / "best.pt"
        print(f"  [SKIP] damage zaten DONE: {weights}")
        return {"weights": str(weights), "skipped": True,
                "classes": CARDD_CLASSES}

    resume_pt = find_resume_target(bundle_dir, "damage")
    epochs = 1 if args.quick else args.damage_epochs
    fraction = 0.05 if args.quick else 1.0
    imgsz = 320 if args.quick else args.imgsz
    batch = args.batch
    save_period = -1 if args.quick else args.save_period

    t0 = time.time()
    if resume_pt:
        print(f"  [RESUME] damage devam ediyor: {resume_pt}")
        model = YOLO(str(resume_pt))
        results = model.train(resume=True)  # epochs/data ckpt'ten gelir
    else:
        model = YOLO(args.damage_model + ".pt")
        results = model.train(
            data=str(CARDD_YAML), epochs=epochs, imgsz=imgsz, batch=batch,
            fraction=fraction, device=args.device, workers=args.workers,
            nbs=args.nbs,
            optimizer="AdamW", lr0=0.001, lrf=0.01, cos_lr=True,
            amp=True, plots=not args.quick, verbose=False,
            project=str(bundle_dir), name="damage", exist_ok=True,
            patience=args.patience, save_period=save_period,
            cache=args.cache, mosaic=1.0, mixup=0.1, copy_paste=0.3,
            hsv_v=0.5, degrees=10.0, seed=42,
        )
    dt = time.time() - t0
    weights = Path(results.save_dir) / "weights" / "best.pt"
    if not weights.exists():  # ultra-kisa egitimde best.pt olmayabilir
        weights = Path(results.save_dir) / "weights" / "last.pt"

    metrics = {}
    try:
        m = results.results_dict
        metrics = {
            "mAP50_M": float(m.get("metrics/mAP50(M)", 0)),
            "mAP50_95_M": float(m.get("metrics/mAP50-95(M)", 0)),
            "precision_M": float(m.get("metrics/precision(M)", 0)),
            "recall_M": float(m.get("metrics/recall(M)", 0)),
        }
    except Exception:
        pass

    mark_done(bundle_dir, "damage")
    release_gpu(model)
    print(f"  [OK] damage egitim {dt:.1f}s | VRAM: {gpu_mem_used()} | weights: {weights}")
    return {
        "weights": str(weights), "epochs": epochs, "imgsz": imgsz,
        "fraction": fraction, "duration_s": round(dt, 1),
        "classes": CARDD_CLASSES, "metrics": metrics,
    }


def train_parts(args, bundle_dir: Path) -> dict:
    header(f"2/3  Parts segmentation ({args.parts_model})")
    if (bundle_dir / "parts" / DONE_SENTINEL).exists():
        weights = bundle_dir / "parts" / "weights" / "best.pt"
        print(f"  [SKIP] parts zaten DONE: {weights}")
        return {"weights": str(weights), "skipped": True}

    resume_pt = find_resume_target(bundle_dir, "parts")
    epochs = 1 if args.quick else args.parts_epochs
    fraction = 0.05 if args.quick else 1.0
    imgsz = 320 if args.quick else args.imgsz
    batch = args.batch
    save_period = -1 if args.quick else args.save_period
    parts_cache = args.cache_parts if args.cache_parts is not None else args.cache

    t0 = time.time()
    if resume_pt:
        print(f"  [RESUME] parts devam ediyor: {resume_pt}")
        model = YOLO(str(resume_pt))
        results = model.train(resume=True)
    else:
        model = YOLO(args.parts_model + ".pt")
        results = model.train(
            data=PARTS_DATA_YAML, epochs=epochs, imgsz=imgsz, batch=batch,
            fraction=fraction, device=args.device, workers=args.workers,
            nbs=args.nbs,
            optimizer="AdamW", lr0=0.001, lrf=0.01, cos_lr=True, amp=True,
            plots=not args.quick, verbose=False,
            project=str(bundle_dir), name="parts", exist_ok=True,
            patience=args.patience, save_period=save_period,
            cache=parts_cache, mosaic=1.0, mixup=0.1, copy_paste=0.3, seed=42,
        )
    dt = time.time() - t0
    weights = Path(results.save_dir) / "weights" / "best.pt"
    if not weights.exists():
        weights = Path(results.save_dir) / "weights" / "last.pt"

    metrics = {}
    try:
        m = results.results_dict
        metrics = {
            "mAP50_M": float(m.get("metrics/mAP50(M)", 0)),
            "mAP50_95_M": float(m.get("metrics/mAP50-95(M)", 0)),
        }
    except Exception:
        pass

    # YOLO names dict - mevcut model.names'tan al, ekstra YOLO yukleme yapma
    parts_names = list(model.names.values()) if hasattr(model, "names") else []

    mark_done(bundle_dir, "parts")
    release_gpu(model)
    print(f"  [OK] parts egitim {dt:.1f}s | VRAM: {gpu_mem_used()} | weights: {weights}")
    return {
        "weights": str(weights), "epochs": epochs, "imgsz": imgsz,
        "fraction": fraction, "duration_s": round(dt, 1),
        "classes": parts_names, "metrics": metrics,
    }


def train_severity(args, bundle_dir: Path) -> dict:
    header("3/3  Severity classification (yolo11n-cls)")
    if (bundle_dir / "severity" / DONE_SENTINEL).exists():
        weights = bundle_dir / "severity" / "weights" / "best.pt"
        print(f"  [SKIP] severity zaten DONE: {weights}")
        return {"weights": str(weights), "skipped": True}

    data_dir = prepare_severity_yolocls(args.quick)
    if data_dir is None:
        print("  [!] Severity dataset yok, atlandi")
        return {}

    resume_pt = find_resume_target(bundle_dir, "severity")
    epochs = 2 if args.quick else args.severity_epochs
    imgsz = 128 if args.quick else 224
    batch = 64
    save_period = -1 if args.quick else max(5, args.save_period // 2)
    sev_patience = 5 if args.quick else min(args.patience, 8)

    t0 = time.time()
    if resume_pt:
        print(f"  [RESUME] severity devam ediyor: {resume_pt}")
        model = YOLO(str(resume_pt))
        results = model.train(resume=True)
    else:
        model = YOLO("yolo11n-cls.pt")
        results = model.train(
            data=str(data_dir), epochs=epochs, imgsz=imgsz, batch=batch,
            device=args.device, workers=args.workers,
            optimizer="AdamW", lr0=0.0005, lrf=0.01, cos_lr=True,
            weight_decay=0.001, amp=True,
            plots=not args.quick, verbose=False,
            project=str(bundle_dir), name="severity", exist_ok=True,
            patience=sev_patience, save_period=save_period,
            hsv_h=0.02, hsv_s=0.7, hsv_v=0.5, fliplr=0.5, seed=42,
        )
    dt = time.time() - t0
    weights = Path(results.save_dir) / "weights" / "best.pt"
    if not weights.exists():
        weights = Path(results.save_dir) / "weights" / "last.pt"

    metrics = {}
    try:
        m = results.results_dict
        metrics = {
            "top1_acc": float(m.get("metrics/accuracy_top1", 0)),
            "top5_acc": float(m.get("metrics/accuracy_top5", 0)),
        }
    except Exception:
        pass

    classes = list(model.names.values()) if hasattr(model, "names") else []
    mark_done(bundle_dir, "severity")
    release_gpu(model)
    print(f"  [OK] severity egitim {dt:.1f}s | VRAM: {gpu_mem_used()} | weights: {weights}")
    return {
        "weights": str(weights), "epochs": epochs, "imgsz": imgsz,
        "duration_s": round(dt, 1),
        "classes": classes, "metrics": metrics,
    }


# -------------------- hibrit inference --------------------

def crop_padded(image, bbox, padding=0.15):
    h, w = image.shape[:2]
    x1, y1, x2, y2 = bbox
    bw, bh = x2 - x1, y2 - y1
    px, py = int(bw * padding), int(bh * padding)
    return image[max(0, int(y1) - py):min(h, int(y2) + py),
                 max(0, int(x1) - px):min(w, int(x2) + px)]


def rule_based_severity(damage_type: str, part_name: str, area_ratio: float):
    dw = DAMAGE_TYPE_WEIGHT.get(damage_type, 1.0)
    pw = PART_IMPORTANCE.get(part_name, 1.0)
    score = area_ratio * 100.0 * dw * pw
    level = "hafif" if score < 1.0 else ("orta" if score < 4.0 else "agir")
    return {"level": level, "score": round(score, 4)}


def cnn_severity(model: YOLO | None, crop) -> dict:
    if model is None or crop is None or crop.size == 0:
        return None
    device_arg = 0 if torch.cuda.is_available() else "cpu"
    res = model.predict(crop, device=device_arg, verbose=False)[0]
    if not hasattr(res, "probs") or res.probs is None:
        return None
    probs = res.probs.data.cpu().numpy()
    names = list(model.names.values())
    idx = int(np.argmax(probs))
    raw = names[idx]
    # Roboflow class isimleri "01-minor" → "hafif" map
    tr_map = {"01-minor": "hafif", "02-moderate": "orta", "03-severe": "agir"}
    level = tr_map.get(raw, raw)
    return {
        "level": level, "raw_class": raw,
        "confidence": float(probs[idx]),
        "all_probs": {tr_map.get(n, n): float(p) for n, p in zip(names, probs)},
    }


def ensemble_severity(rule, cnn):
    if cnn is None:
        return {**rule, "method": "rule_only"}
    if rule["level"] == cnn["level"]:
        return {"level": rule["level"], "method": "ensemble_agree",
                "confidence": cnn["confidence"], "rule": rule, "cnn": cnn}
    # weighted: rule 0.4 cnn 0.6
    scores = {l: 0.0 for l in SEVERITY_LEVELS}
    scores[rule["level"]] += 0.4
    scores[cnn["level"]] += 0.6 * cnn["confidence"]
    best = max(scores, key=scores.get)
    return {"level": best, "method": "ensemble_resolved",
            "confidence": scores[best], "rule": rule, "cnn": cnn,
            "scores": scores}


def iou_match(damage_mask: np.ndarray, part_masks: list, part_names: list,
              iou_thresh: float = 0.05, intersect_ratio_thresh: float = 0.5):
    """damage maskesi vs parca maskeleri. (primary, secondary, multi_part_flag)"""
    d_area = float(damage_mask.sum())
    if d_area == 0 or not part_masks:
        return "unknown", [], False, False

    candidates = []
    for name, pmask in zip(part_names, part_masks):
        if pmask.shape != damage_mask.shape:
            # Binary mask → INTER_NEAREST (bilinear yanlis)
            pmask = cv2.resize(pmask.astype(np.uint8), damage_mask.shape[::-1],
                               interpolation=cv2.INTER_NEAREST).astype(bool)
        inter = float((damage_mask & pmask).sum())
        union = float((damage_mask | pmask).sum()) or 1.0
        iou = inter / union
        ir = inter / d_area
        if ir >= intersect_ratio_thresh:
            candidates.append({"name": name, "iou": iou, "intersect_ratio": ir})

    if not candidates:
        return "unknown", [], False, False
    candidates.sort(key=lambda c: -c["intersect_ratio"])
    primary = candidates[0]["name"]
    secondary = [{"part": c["name"], "ratio": round(c["intersect_ratio"], 3)}
                 for c in candidates[1:]]
    multi = len(candidates) > 1
    low_conf = candidates[0]["iou"] < iou_thresh
    return primary, secondary, multi, low_conf


def cost_lookup(part: str, dtype: str, severity: str):
    base = COST_FALLBACK.get((part, dtype), GLOBAL_COST_DEFAULT)
    mult = {"hafif": 0.6, "orta": 1.0, "agir": 1.5}.get(severity, 1.0)
    return int(base[0] * mult), int(base[1] * mult)


def part_status(damages: list) -> str:
    if not damages:
        return "clean"
    sevs = [d["severity"]["level"] for d in damages]
    if "agir" in sevs:
        return "severe"
    if "orta" in sevs:
        return "moderate"
    return "minor"


def _list_val_images(val_dir: Path) -> list:
    """Tum yaygin uzantilar (case-insensitive)."""
    exts = ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG")
    out = []
    for e in exts:
        out.extend(val_dir.glob(e))
    return sorted(set(out))


def smoke_inference(bundle_dir: Path, manifest: dict, val_dir: Path,
                    smoke_seed: int = 7, num_attempts: int = 5,
                    smoke_conf: float = 0.15):
    header("Smoke inference - hibrit JSON")
    images = _list_val_images(val_dir)
    if not images:
        print(f"  [!] val gorseli yok: {val_dir}")
        return None

    damage_w = manifest.get("damage", {}).get("weights")
    parts_w = manifest.get("parts", {}).get("weights")
    severity_w = manifest.get("severity", {}).get("weights")

    if not damage_w:
        print("  [!] damage modeli yok, smoke iptal")
        return None
    damage_model = YOLO(damage_w)
    parts_model = YOLO(parts_w) if parts_w else None
    sev_model = YOLO(severity_w) if severity_w else None

    device_arg = 0 if torch.cuda.is_available() else "cpu"

    # 5 random gorsel dene, ilk non-zero detection'i kullan
    rng = random.Random(smoke_seed)
    candidates = rng.sample(images, min(num_attempts, len(images)))
    img_path = None
    image = None
    d_pred = None
    p_pred = None
    for attempt, cand in enumerate(candidates):
        cand_img = cv2.imread(str(cand))
        if cand_img is None:
            print(f"  [!] okunamadi: {cand.name}")
            continue
        cand_d = damage_model.predict(cand_img, conf=smoke_conf,
                                      device=device_arg, verbose=False)[0]
        n = len(cand_d.boxes) if cand_d.boxes is not None else 0
        print(f"  [{attempt+1}/{len(candidates)}] {cand.name}: {n} damage @ conf>={smoke_conf}")
        if n > 0 or attempt == len(candidates) - 1:
            img_path = cand
            image = cand_img
            d_pred = cand_d
            break
    if image is None or d_pred is None:
        print("  [!] hicbir gorsel yuklenemedi")
        return None

    h, w = image.shape[:2]
    print(f"  [+] secilen test gorseli: {img_path.name} ({w}x{h})")

    p_pred = parts_model.predict(image, conf=0.15, device=device_arg,
                                 verbose=False)[0] if parts_model else None

    # Parts maskelerini topla
    parts_info = []
    if p_pred is not None and p_pred.masks is not None:
        p_names_dict = parts_model.names
        for i, box in enumerate(p_pred.boxes):
            name = p_names_dict[int(box.cls.item())]
            mask = p_pred.masks.data[i].cpu().numpy().astype(bool)
            parts_info.append({
                "name": name, "mask": mask,
                "conf": float(box.conf.item()),
                "polygon": p_pred.masks.xy[i].tolist() if i < len(p_pred.masks.xy) else [],
            })

    # Damages → her biri icin part match + severity
    damages_out = []
    for i, box in enumerate(d_pred.boxes):
        cls_id = int(box.cls.item())
        dtype = CARDD_CLASSES[cls_id]
        det_conf = float(box.conf.item())
        x1, y1, x2, y2 = box.xyxy[0].tolist()

        if d_pred.masks is not None and i < len(d_pred.masks.data):
            d_mask = d_pred.masks.data[i].cpu().numpy().astype(bool)
            area_pixels = float(d_mask.sum())
            poly = d_pred.masks.xy[i].tolist() if i < len(d_pred.masks.xy) else []
        else:
            d_mask = np.zeros((h, w), dtype=bool)
            area_pixels = (x2 - x1) * (y2 - y1)
            poly = []
        area_ratio = area_pixels / (h * w)

        primary, secondary, multi, low_conf_match = iou_match(
            d_mask, [p["mask"] for p in parts_info],
            [p["name"] for p in parts_info]
        )

        crop = crop_padded(image, (x1, y1, x2, y2))
        rule = rule_based_severity(dtype, primary, area_ratio)
        cnn = cnn_severity(sev_model, crop)
        sev = ensemble_severity(rule, cnn)

        cost_min, cost_max = cost_lookup(primary, dtype, sev["level"])

        damages_out.append({
            "id": i,
            "type": dtype, "type_tr": DAMAGE_TR.get(dtype, dtype),
            "detection_confidence": round(det_conf, 4),
            "primary_part": primary,
            "secondary_parts": secondary,
            "is_multi_part": multi,
            "is_low_confidence_match": low_conf_match,
            "bbox": {"x1": round(x1, 1), "y1": round(y1, 1),
                     "x2": round(x2, 1), "y2": round(y2, 1)},
            "polygon_normalized": [[round(p[0]/w, 4), round(p[1]/h, 4)] for p in poly],
            "area_pixels": round(area_pixels, 1),
            "area_ratio": round(area_ratio, 6),
            "severity": sev,
            "cost_tl": [cost_min, cost_max],
        })

    # Parts-merkezli reorganizasyon
    parts_out = []
    for p in parts_info:
        related = [d for d in damages_out
                   if d["primary_part"] == p["name"]
                   or any(s["part"] == p["name"] for s in d["secondary_parts"])]
        status = part_status(related)
        if related:
            cost_min = max(d["cost_tl"][0] for d in related)
            cost_max = max(d["cost_tl"][1] for d in related)
            cost_note = ("Tek parca degisimi diger hasarlari kapsar"
                         if len(related) > 1 else None)
        else:
            cost_min = cost_max = 0
            cost_note = None
        parts_out.append({
            "name": p["name"], "name_tr": PART_NAME_TR.get(p["name"], p["name"]),
            "status": status, "damage_count": len(related),
            "damage_ids": [d["id"] for d in related],
            "confidence": round(p["conf"], 4),
            "polygon_normalized": [[round(pt[0]/w, 4), round(pt[1]/h, 4)]
                                   for pt in p["polygon"]],
            "part_cost_min_tl": cost_min, "part_cost_max_tl": cost_max,
            "cost_note": cost_note,
        })

    # Toplam summary
    sevs = [d["severity"]["level"] for d in damages_out]
    overall = "agir" if "agir" in sevs else ("orta" if "orta" in sevs
              else ("hafif" if sevs else "yok"))
    total_min = sum(p["part_cost_min_tl"] for p in parts_out)
    total_max = sum(p["part_cost_max_tl"] for p in parts_out)

    hybrid = {
        "image": img_path.name,
        "width": w, "height": h,
        "model_versions": {
            "damage": Path(damage_w).name if damage_w else None,
            "parts": Path(parts_w).name if parts_w else None,
            "severity": Path(severity_w).name if severity_w else None,
        },
        "damages": damages_out,
        "parts": parts_out,
        "summary": {
            "total_damages": len(damages_out),
            "affected_parts": sum(1 for p in parts_out if p["status"] != "clean"),
            "overall_severity": overall,
            "total_cost_tl": [total_min, total_max],
        },
    }

    # JSON kaydet
    json_path = bundle_dir / "smoke_inference.json"
    json_path.write_text(json.dumps(hybrid, indent=2, ensure_ascii=False))

    # Overlay
    overlay = image.copy()
    palette = {"hafif": (60, 200, 60), "orta": (40, 180, 230),
               "agir": (40, 40, 230), "clean": (180, 180, 180)}
    for p in parts_out:
        col = palette.get(p["status"], (180, 180, 180))
        if p["polygon_normalized"]:
            poly = np.array([[int(x * w), int(y * h)]
                             for x, y in p["polygon_normalized"]], dtype=np.int32)
            cv2.polylines(overlay, [poly], True, col, 1)
    for d in damages_out:
        col = palette.get(d["severity"]["level"], (200, 200, 200))
        b = d["bbox"]
        cv2.rectangle(overlay, (int(b["x1"]), int(b["y1"])),
                      (int(b["x2"]), int(b["y2"])), col, 2)
        label = f"{d['type']}|{d['severity']['level']}|{d['primary_part']}"
        cv2.putText(overlay, label, (int(b["x1"]), max(15, int(b["y1"]) - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1, cv2.LINE_AA)
    overlay_path = bundle_dir / "smoke_inference.jpg"
    # Unicode-safe imwrite (Turkce path icin)
    ok_enc, buf = cv2.imencode(".jpg", overlay)
    if ok_enc:
        buf.tofile(str(overlay_path))

    # JSON sema kontrol (regression catch)
    assert all(k in hybrid for k in ("damages", "parts", "summary")), \
        "Hibrit JSON sema BOZUK"
    assert "overall_severity" in hybrid["summary"], "summary.overall_severity yok"

    release_gpu(damage_model, parts_model, sev_model)

    print(f"  [OK] hibrit JSON: {json_path}")
    print(f"  [OK] overlay:    {overlay_path}")
    print(f"  ---")
    print(f"  damages: {len(damages_out)}, parts(detected): {len(parts_out)}, "
          f"affected: {hybrid['summary']['affected_parts']}, "
          f"overall: {overall}, cost: {hybrid['summary']['total_cost_tl']} TL")
    return {"json": str(json_path), "overlay": str(overlay_path),
            "summary": hybrid["summary"],
            "tested_image": img_path.name}


# -------------------- main --------------------

def main():
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--quick", action="store_true",
                      help="2-3 dakikalik smoke test")
    mode.add_argument("--full", action="store_true",
                      help="Production egitim (default)")

    ap.add_argument("--damage_model", default="yolo11n-seg",
                    choices=["yolo11n-seg", "yolo11s-seg", "yolo11m-seg"])
    ap.add_argument("--parts_model", default="yolo11n-seg",
                    choices=["yolo11n-seg", "yolo11s-seg", "yolo11m-seg"])
    ap.add_argument("--damage_epochs", type=int, default=100)
    ap.add_argument("--parts_epochs", type=int, default=100)
    ap.add_argument("--severity_epochs", type=int, default=30)

    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--nbs", type=int, default=64,
                    help="Nominal batch size (gradient accumulation hedefi)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--device", default="0")
    ap.add_argument("--patience", type=int, default=30)
    ap.add_argument("--save_period", type=int, default=5,
                    help="Her N epoch'ta intermediate checkpoint (cokme guvencesi)")
    ap.add_argument("--cache", default="ram",
                    help="Dataset cache: False / 'ram' / 'disk' (RAM 10x hizlandirir)")
    ap.add_argument("--cache_parts", default=None,
                    help="Parts icin ayri cache (None=ana cache, 'disk'=RAM tasarrufu)")

    ap.add_argument("--skip_damage", action="store_true")
    ap.add_argument("--skip_parts", action="store_true")
    ap.add_argument("--skip_severity", action="store_true")

    ap.add_argument("--bundle_root", type=Path, default=DEFAULT_BUNDLE_ROOT)
    ap.add_argument("--resume_bundle", type=Path, default=None,
                    help="Belirli bundle dir'i resume et (path). Yoksa: --resume_latest")
    ap.add_argument("--resume_latest", action="store_true",
                    help="En son full_* bundle'i bul ve resume et (last.pt mevcut modeller icin)")
    ap.add_argument("--smoke_seed", type=int, default=7)
    ap.add_argument("--smoke_attempts", type=int, default=5,
                    help="Detection bulana kadar kac val gorseli denesin")
    ap.add_argument("--smoke_conf", type=float, default=0.15)
    ap.add_argument("--allow_cpu", action="store_true",
                    help="GPU yoksa CPU'da calismaya izin ver (cok yavas)")
    args = ap.parse_args()

    assert_gpu(allow_cpu=args.allow_cpu)

    if not args.quick and not args.full:
        args.full = True
    if args.quick:
        # quick'te yolo11n her zaman zorla, dataset ufak
        args.damage_model = "yolo11n-seg"
        args.parts_model = "yolo11n-seg"

    # Resume mantigi: explicit path > resume_latest > yeni timestamp
    resumed = False
    if args.resume_bundle:
        bundle_dir = args.resume_bundle
        if not bundle_dir.exists():
            print(f"[FATAL] resume_bundle bulunamadi: {bundle_dir}")
            sys.exit(2)
        resumed = True
    elif args.resume_latest and not args.quick:
        latest = find_latest_full_bundle(args.bundle_root)
        if latest:
            bundle_dir = latest
            resumed = True
        else:
            print("  [!] resume_latest istendi ama bundle yok, yeni baslatiyor")
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            bundle_dir = args.bundle_root / f"full_{ts}"
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        bundle_dir = args.bundle_root / f"{'quick' if args.quick else 'full'}_{ts}"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    header("Train-All Pipeline")
    print(f"  Mode:      {'QUICK SMOKE' if args.quick else 'FULL'}{' (RESUME)' if resumed else ''}")
    print(f"  {gpu_info()}")
    print(f"  Bundle:    {bundle_dir}")
    if resumed:
        for m in ("damage", "parts", "severity"):
            done = (bundle_dir / m / DONE_SENTINEL).exists()
            last = (bundle_dir / m / "weights" / "last.pt").exists()
            state = "DONE" if done else ("RESUME" if last else "FRESH")
            print(f"    {m:8s}: {state}")
    print(f"  Damage:    {args.damage_model}, "
          f"epochs={1 if args.quick else args.damage_epochs}")
    print(f"  Parts:     {args.parts_model}, "
          f"epochs={1 if args.quick else args.parts_epochs}")
    print(f"  Severity:  yolo11n-cls, "
          f"epochs={2 if args.quick else args.severity_epochs}")

    manifest_path = bundle_dir / "manifest.json"
    # Eski manifest varsa (resume) yukle, yoksa yeni
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["resumed_at"] = datetime.now().strftime("%Y%m%d_%H%M%S")
        except Exception:
            manifest = {}
    else:
        manifest = {}
    manifest.setdefault("created", datetime.now().strftime("%Y%m%d_%H%M%S"))
    manifest["mode"] = "quick" if args.quick else "full"
    manifest["config"] = {k: (str(v) if isinstance(v, Path) else v)
                          for k, v in vars(args).items()}
    t_total = time.time()

    def _write_manifest():
        manifest["total_duration_s"] = round(time.time() - t_total, 1)
        try:
            manifest_path.write_text(
                json.dumps(manifest, indent=2, ensure_ascii=False),
                encoding="utf-8")
        except Exception as e:
            print(f"  [WARN] manifest yazilamadi: {e}")

    try:
        if not args.skip_damage:
            try:
                manifest["damage"] = train_damage(args, bundle_dir)
            except torch.cuda.OutOfMemoryError as e:
                print(f"  [OOM] damage: {e}")
                manifest["damage"] = {"error": "OOM", "msg": str(e)}
                release_gpu()
                _write_manifest()
                sys.exit(137)  # OOM exit code (wrapper bunu tanir)
            except Exception as e:
                print(f"  [HATA] damage egitim: {e}\n{traceback.format_exc()}")
                manifest["damage"] = {"error": str(e)}
                release_gpu()
            finally:
                _write_manifest()

        if not args.skip_parts:
            try:
                manifest["parts"] = train_parts(args, bundle_dir)
            except torch.cuda.OutOfMemoryError as e:
                print(f"  [OOM] parts: {e}")
                manifest["parts"] = {"error": "OOM", "msg": str(e)}
                release_gpu()
                _write_manifest()
                sys.exit(137)
            except Exception as e:
                print(f"  [HATA] parts egitim: {e}\n{traceback.format_exc()}")
                manifest["parts"] = {"error": str(e)}
                release_gpu()
            finally:
                _write_manifest()

        if not args.skip_severity:
            try:
                manifest["severity"] = train_severity(args, bundle_dir)
            except torch.cuda.OutOfMemoryError as e:
                print(f"  [OOM] severity: {e}")
                manifest["severity"] = {"error": "OOM", "msg": str(e)}
                release_gpu()
                _write_manifest()
                sys.exit(137)
            except Exception as e:
                print(f"  [HATA] severity egitim: {e}\n{traceback.format_exc()}")
                manifest["severity"] = {"error": str(e)}
                release_gpu()
            finally:
                _write_manifest()
    except KeyboardInterrupt:
        print("\n  [ABORT] kullanici Ctrl+C")
        _write_manifest()
        sys.exit(130)

    # Smoke inference
    smoke = None
    try:
        smoke = smoke_inference(bundle_dir, manifest, CARDD_VAL_DIR,
                                smoke_seed=args.smoke_seed,
                                num_attempts=args.smoke_attempts,
                                smoke_conf=args.smoke_conf)
        if smoke:
            manifest["smoke"] = smoke
    except Exception as e:
        print(f"  [HATA] smoke inference: {e}\n{traceback.format_exc()}")
        manifest["smoke"] = {"error": str(e)}
    finally:
        _write_manifest()

    header("Tamamlandi")
    print(f"  Toplam sure:  {manifest['total_duration_s']}s")
    print(f"  Bundle:       {bundle_dir}")
    print(f"  Manifest:     {bundle_dir / 'manifest.json'}")
    if smoke:
        print(f"  Smoke JSON:   {smoke['json']}")
        print(f"  Overlay:      {smoke['overlay']}")
    print(f"\n  Production icin:")
    print(f"    python train_all.py --full --damage_model yolo11s-seg "
          f"--parts_model yolo11s-seg --damage_epochs 100 --parts_epochs 100")


if __name__ == "__main__":
    main()
