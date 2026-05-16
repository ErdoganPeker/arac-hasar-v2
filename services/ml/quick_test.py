"""
quick_test.py - Hizli end-to-end test scripti.

Egitilmis modelleri val setinden secilen ornek goruntuler uzerinde calistirir,
JSON ciktisi + annotated overlay PNG uretir.

Tek ihtiyacin olan:
    cd services/ml
    .venv\\Scripts\\activate   (Windows)
    python quick_test.py

Ne yapar:
  1. Mini-test (yolo11n-seg, 2 epoch) ile damage segmentation
  2. EfficientNet-B0 ile severity classification (her bbox crop'una)
  3. Kural-tabanli severity (referans icin)
  4. quick_test_out/ altina <img>.json + <img>.overlay.jpg yazar

Argument istemiyorsan opsiyonel:
    python quick_test.py --num 5 --conf 0.15
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from torchvision import transforms
from torchvision.models import efficientnet_b0
from ultralytics import YOLO

ML_DIR = Path(__file__).resolve().parent


def _latest_snapshot() -> Path | None:
    bundles = ML_DIR / "runs" / "bundles"
    if not bundles.exists():
        return None
    cands = sorted(
        (p for p in bundles.iterdir()
         if p.is_dir() and (p / "_SNAPSHOT_FOR_BUILD").is_dir()
         and p.name.startswith("full_")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return (cands[0] / "_SNAPSHOT_FOR_BUILD") if cands else None


_SNAP = _latest_snapshot()
# Prefer the production snapshot (full_YYYYMMDD_HHMMSS) when present; fall
# back to the legacy mini-test path so this script keeps working in fresh
# checkouts that have only trained the smoke run.
if _SNAP is not None and (_SNAP / "damage_best.pt").exists():
    DEFAULT_DAMAGE_W = _SNAP / "damage_best.pt"
else:
    DEFAULT_DAMAGE_W = ML_DIR / "runs" / "segment" / "runs" / "arac-hasar" / "mini-test" / "weights" / "best.pt"

if _SNAP is not None and (_SNAP / "severity_best.pt").exists():
    DEFAULT_SEVERITY_W = _SNAP / "severity_best.pt"
else:
    DEFAULT_SEVERITY_W = ML_DIR / "runs" / "severity" / "best.pt"

DEFAULT_VAL_DIR = ML_DIR / "data" / "cardd_yolo" / "images" / "val"
DEFAULT_OUT = ML_DIR / "quick_test_out"

CARDD_CLASSES = ["dent", "scratch", "crack", "glass_shatter", "lamp_broken", "tire_flat"]

# severity_classifier.py'den birebir kopya (rule-based referans icin)
PART_IMPORTANCE_DEFAULT = 1.0
DAMAGE_TYPE_WEIGHT = {
    "scratch": 0.6, "dent": 1.0, "crack": 1.4,
    "glass_shatter": 2.0, "lamp_broken": 1.8, "tire_flat": 1.5,
}


def rule_based_severity(damage_type: str, area_ratio: float) -> dict:
    weight = DAMAGE_TYPE_WEIGHT.get(damage_type, 1.0)
    score = area_ratio * 100.0 * weight * PART_IMPORTANCE_DEFAULT
    if score < 1.0:
        level = "hafif"
    elif score < 4.0:
        level = "orta"
    else:
        level = "agir"
    return {"level": level, "score": round(score, 4), "method": "rule_based"}


class SeverityCNN:
    """EfficientNet-B0 severity classifier (train_severity.py ile uyumlu)."""

    def __init__(self, ckpt_path: Path, device: str = "cuda"):
        self.device = device if torch.cuda.is_available() else "cpu"
        ckpt = torch.load(ckpt_path, map_location=self.device, weights_only=False)
        self.classes = ckpt["classes"]
        self.tr_names = ckpt["tr_names"]
        self.img_size = ckpt.get("img_size", 224)
        self.train_val_acc = ckpt.get("val_acc", None)

        model = efficientnet_b0(weights=None)
        in_features = model.classifier[1].in_features
        model.classifier[1] = torch.nn.Linear(in_features, len(self.classes))
        model.load_state_dict(ckpt["model_state_dict"])
        model.to(self.device).eval()
        self.model = model

        self.tf = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((self.img_size, self.img_size)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                 std=[0.229, 0.224, 0.225]),
        ])

    def predict_bgr(self, bgr_crop: np.ndarray) -> dict:
        if bgr_crop is None or bgr_crop.size == 0:
            return {"level": "hafif", "confidence": 0.0, "method": "cnn_empty"}
        rgb = cv2.cvtColor(bgr_crop, cv2.COLOR_BGR2RGB)
        x = self.tf(rgb).unsqueeze(0).to(self.device)
        with torch.no_grad():
            logits = self.model(x)
            probs = F.softmax(logits, dim=1)[0].cpu().numpy()
        idx = int(np.argmax(probs))
        return {
            "level": self.tr_names[idx],
            "raw_class": self.classes[idx],
            "confidence": float(probs[idx]),
            "method": "cnn",
            "all_probs": {
                self.tr_names[i]: float(p) for i, p in enumerate(probs)
            },
        }


def crop_padded(image: np.ndarray, bbox, padding: float = 0.15) -> np.ndarray:
    h, w = image.shape[:2]
    x1, y1, x2, y2 = bbox
    bw, bh = x2 - x1, y2 - y1
    px, py = int(bw * padding), int(bh * padding)
    x1 = max(0, int(x1) - px)
    y1 = max(0, int(y1) - py)
    x2 = min(w, int(x2) + px)
    y2 = min(h, int(y2) + py)
    return image[y1:y2, x1:x2]


def annotate(image: np.ndarray, damages: list) -> np.ndarray:
    overlay = image.copy()
    palette = {
        "hafif": (60, 200, 60),
        "orta": (40, 180, 230),
        "agir": (40, 40, 230),
    }
    for d in damages:
        x1 = int(d["bbox"]["x1"]); y1 = int(d["bbox"]["y1"])
        x2 = int(d["bbox"]["x2"]); y2 = int(d["bbox"]["y2"])
        sev = d.get("severity_cnn", {}).get("level", "hafif")
        color = palette.get(sev, (200, 200, 200))
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)
        label = f"{d['type']} | cnn={sev} | rule={d['severity_rule']['level']}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(overlay, (x1, max(0, y1 - th - 6)),
                      (x1 + tw + 6, y1), color, -1)
        cv2.putText(overlay, label, (x1 + 3, max(th, y1 - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return overlay


def run_one(damage_model: YOLO, sev_cnn: SeverityCNN | None,
            img_path: Path, out_dir: Path, conf: float, imgsz: int) -> dict:
    image = cv2.imread(str(img_path))
    if image is None:
        return {"image": str(img_path), "error": "read_failed"}
    h, w = image.shape[:2]

    pred = damage_model.predict(image, imgsz=imgsz, conf=conf, verbose=False)[0]
    damages = []
    for i, box in enumerate(pred.boxes):
        cls_id = int(box.cls.item())
        damage_type = CARDD_CLASSES[cls_id] if cls_id < len(CARDD_CLASSES) else f"cls_{cls_id}"
        det_conf = float(box.conf.item())
        x1, y1, x2, y2 = box.xyxy[0].tolist()

        # NOTE: pred.masks.data is at YOLO's internal resolution (typically
        # 160x160 or imgsz/4), not the original image size. To get an
        # area-ratio that's comparable to the original frame we either
        # resize the mask to (h, w) first, or compute the ratio against the
        # mask's own pixel space — the latter is cheaper and equivalent.
        if pred.masks is not None and i < len(pred.masks.data):
            mask_t = pred.masks.data[i]
            mh, mw = mask_t.shape[-2:]
            area_pixels = float(mask_t.sum())  # pixels in mask-space
            area_ratio = area_pixels / float(mh * mw)
        else:
            area_pixels = (x2 - x1) * (y2 - y1)
            area_ratio = area_pixels / (h * w)

        crop = crop_padded(image, (x1, y1, x2, y2))
        sev_cnn_pred = sev_cnn.predict_bgr(crop) if sev_cnn else None
        sev_rule = rule_based_severity(damage_type, area_ratio)

        damages.append({
            "id": i,
            "type": damage_type,
            "detection_confidence": round(det_conf, 4),
            "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
            "area_ratio": round(area_ratio, 6),
            "severity_rule": sev_rule,
            "severity_cnn": sev_cnn_pred,
        })

    summary = {
        "image": img_path.name,
        "width": w,
        "height": h,
        "damage_count": len(damages),
        "classes_detected": sorted({d["type"] for d in damages}),
        "max_detection_conf": round(max((d["detection_confidence"] for d in damages),
                                        default=0.0), 4),
    }
    result = {"summary": summary, "damages": damages}

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{img_path.stem}.json"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    overlay = annotate(image, damages)
    overlay_path = out_dir / f"{img_path.stem}.overlay.jpg"
    cv2.imwrite(str(overlay_path), overlay)

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--damage_weights", type=Path, default=DEFAULT_DAMAGE_W)
    ap.add_argument("--severity_weights", type=Path, default=DEFAULT_SEVERITY_W)
    ap.add_argument("--val_dir", type=Path, default=DEFAULT_VAL_DIR)
    ap.add_argument("--out_dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--num", type=int, default=3, help="Kac val gorseli denesin")
    # Defaults track the production snapshot when present; otherwise we
    # assume the legacy mini-test model (imgsz=480, low conf).
    _is_prod_snap = _SNAP is not None and (_SNAP / "damage_best.pt").exists()
    _default_conf = 0.25 if _is_prod_snap else 0.15
    _default_imgsz = 640 if _is_prod_snap else 480
    ap.add_argument("--conf", type=float, default=_default_conf,
                    help="Detection confidence threshold "
                         "(snapshot: 0.25, mini-test: 0.15)")
    ap.add_argument("--imgsz", type=int, default=_default_imgsz,
                    help="Inference image size (snapshot: 640, mini-test: 480)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--image", type=Path, default=None,
                    help="Belirli bir gorsel ver, val secimini atla")
    args = ap.parse_args()

    if not args.damage_weights.exists():
        raise FileNotFoundError(
            f"Damage agirligi yok: {args.damage_weights}\n"
            f"Once `python train.py` tamamla.")

    print(f"[+] Damage model: {args.damage_weights}")
    damage_model = YOLO(str(args.damage_weights))

    sev_cnn = None
    if args.severity_weights.exists():
        print(f"[+] Severity model: {args.severity_weights}")
        sev_cnn = SeverityCNN(args.severity_weights)
        print(f"    Classes: {sev_cnn.classes} → {sev_cnn.tr_names}")
        if sev_cnn.train_val_acc is not None:
            print(f"    Egitim val_acc: {sev_cnn.train_val_acc:.3f}")
    else:
        print(f"[!] Severity agirligi yok: {args.severity_weights} (atlandi)")

    if args.image:
        images = [args.image]
    else:
        all_imgs = sorted(args.val_dir.glob("*.jpg"))
        if not all_imgs:
            raise FileNotFoundError(f"Val'da gorsel yok: {args.val_dir}")
        random.seed(args.seed)
        images = random.sample(all_imgs, min(args.num, len(all_imgs)))

    print(f"\n[+] {len(images)} gorsel test ediliyor...")
    print(f"    out_dir: {args.out_dir}\n")

    for img in images:
        print(f"--- {img.name} ---")
        res = run_one(damage_model, sev_cnn, img, args.out_dir,
                      conf=args.conf, imgsz=args.imgsz)
        s = res["summary"]
        print(f"  damage_count: {s['damage_count']}, "
              f"classes: {s['classes_detected']}, "
              f"max_conf: {s['max_detection_conf']}")
        for d in res["damages"]:
            cnn = d["severity_cnn"]
            cnn_str = f"{cnn['level']} ({cnn['confidence']:.2f})" if cnn else "n/a"
            print(f"    [{d['id']}] {d['type']} conf={d['detection_confidence']:.2f} "
                  f"area={d['area_ratio']:.4f} "
                  f"rule={d['severity_rule']['level']} cnn={cnn_str}")
        print()

    print(f"[OK] Tum sonuclar: {args.out_dir}")


if __name__ == "__main__":
    main()
