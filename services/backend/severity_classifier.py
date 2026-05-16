"""
severity_classifier.py
Hasar siddet siniflandirma. Iki strateji destekler:
  1. RuleBasedSeverity: maske alani + parca onemi + hasar tipi → skor → siddet
  2. CNNSeverity: hasar bolgesini crop → YOLO-cls → siddet

Ensemble: ikisini kombine eder.

Kullanim:
    # CNN egit
    python severity_classifier.py train --data data/severity_yolo \\
        --model yolo26n-cls --epochs 50

    # Tek goruntu uzerinde test (her iki yontem)
    python severity_classifier.py test \\
        --image car.jpg \\
        --damage_weights runs/.../damage_best.pt \\
        --severity_weights runs/.../severity_best.pt
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO


SEVERITY_LEVELS = ["hafif", "orta", "agir"]

# Parca onem katsayilari - hasarin gozukurlugu ve onarim maliyeti agirligi
# 1.0 = ortalama, daha yuksek = daha kritik
PART_IMPORTANCE = {
    "front_bumper": 1.2,
    "back_bumper": 1.1,
    "hood": 1.4,
    "front_glass": 1.6,    # On cam ciddi
    "back_glass": 1.3,
    "front_left_door": 1.2,
    "front_right_door": 1.2,
    "back_left_door": 1.1,
    "back_right_door": 1.1,
    "front_left_light": 1.3,
    "front_right_light": 1.3,
    "back_left_light": 1.1,
    "back_right_light": 1.1,
    "front_light": 1.3,
    "back_light": 1.1,
    "left_mirror": 0.9,
    "right_mirror": 0.9,
    "tailgate": 1.2,
    "trunk": 1.2,
    "wheel": 1.0,
    "unknown": 1.0,
}

# Hasar tipi agirligi - kac kat ciddidir
DAMAGE_TYPE_WEIGHT = {
    "scratch": 0.6,        # En hafif
    "dent": 1.0,           # Referans
    "crack": 1.4,          # Cizgisel, yayilir
    "glass_shatter": 2.0,  # Cam parcalanmasi = aliyo parca degisimi
    "lamp_broken": 1.8,    # Far kirilmasi
    "tire_flat": 1.5,      # Lastik
}


class RuleBasedSeverity:
    """Aciklanabilir, kural tabanli siddet skorlama.

    score = area_ratio * part_importance * damage_type_weight * 100

    Esikler:
        score < 1.0   → hafif
        1.0 ≤ score < 4.0  → orta
        score ≥ 4.0   → agir
    """
    THRESHOLDS = [1.0, 4.0]

    def predict(self, damage_type, part_name, area_ratio):
        damage_w = DAMAGE_TYPE_WEIGHT.get(damage_type, 1.0)
        part_w = PART_IMPORTANCE.get(part_name, 1.0)
        score = area_ratio * 100.0 * damage_w * part_w

        if score < self.THRESHOLDS[0]:
            level = "hafif"
        elif score < self.THRESHOLDS[1]:
            level = "orta"
        else:
            level = "agir"

        return {
            "level": level,
            "score": round(score, 4),
            "confidence": min(1.0, score / 6.0 + 0.5),  # heuristik
            "method": "rule_based",
            "components": {
                "area_ratio": area_ratio,
                "damage_weight": damage_w,
                "part_weight": part_w,
            },
        }


class CNNSeverity:
    """CNN siddet siniflandirici.

    Supports two checkpoint formats:
      (a) Ultralytics YOLO-cls .pt (loaded with YOLO())
      (b) Custom torchvision checkpoint dict from train_severity.py
          with keys: model_state_dict, classes, tr_names, arch, img_size
    """

    IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

    def __init__(self, weights_path):
        import torch
        self._torch = torch
        self.weights_path = weights_path
        self.kind = None        # "yolo" or "torchvision"
        self.model = None
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.img_size = 224
        self.class_names = list(SEVERITY_LEVELS)
        self._load(weights_path)

    def _load(self, weights_path):
        torch = self._torch
        # Try torchvision-style checkpoint first
        try:
            ckpt = torch.load(weights_path, map_location="cpu", weights_only=False)
        except Exception:
            ckpt = None

        if isinstance(ckpt, dict) and "model_state_dict" in ckpt:
            self._load_torchvision(ckpt)
            return

        # Fall back to YOLO loader
        self.model = YOLO(weights_path)
        self.kind = "yolo"

    def _load_torchvision(self, ckpt):
        torch = self._torch
        from torchvision.models import efficientnet_b0
        import torch.nn as nn

        arch = ckpt.get("arch", "efficientnet_b0")
        if arch != "efficientnet_b0":
            raise ValueError(f"Unsupported torchvision arch: {arch}")

        model = efficientnet_b0(weights=None)
        # Replace classifier head to match training (3 classes)
        n_classes = len(ckpt.get("classes", SEVERITY_LEVELS))
        in_features = model.classifier[1].in_features
        model.classifier[1] = nn.Linear(in_features, n_classes)
        model.load_state_dict(ckpt["model_state_dict"])
        model.eval()
        model.to(self.device)
        self.model = model
        self.kind = "torchvision"
        self.img_size = int(ckpt.get("img_size", 224))
        # Prefer Turkish labels (hafif/orta/agir); fall back to raw class names
        self.class_names = list(ckpt.get("tr_names", ckpt.get("classes", SEVERITY_LEVELS)))

    @staticmethod
    def _bgr_to_normalized_tensor(image_crop, img_size: int):
        import torch
        rgb = cv2.cvtColor(image_crop, cv2.COLOR_BGR2RGB)
        rgb = cv2.resize(rgb, (img_size, img_size), interpolation=cv2.INTER_AREA)
        arr = rgb.astype(np.float32) / 255.0
        arr = (arr - CNNSeverity.IMAGENET_MEAN) / CNNSeverity.IMAGENET_STD
        arr = np.transpose(arr, (2, 0, 1))  # HWC -> CHW
        return torch.from_numpy(arr).unsqueeze(0)

    def predict(self, image_crop):
        """Tek bir BGR crop verir, en yuksek siddet sinifini dondur."""
        if image_crop is None or image_crop.size == 0:
            return {"level": "hafif", "confidence": 0.0, "method": "cnn_empty"}

        if self.kind == "torchvision":
            torch = self._torch
            try:
                x = self._bgr_to_normalized_tensor(image_crop, self.img_size).to(self.device)
                with torch.inference_mode():
                    logits = self.model(x)
                    probs = torch.softmax(logits, dim=1)[0].cpu().numpy()
            except Exception:
                return {"level": "orta", "confidence": 0.0, "method": "cnn_failed"}
            idx = int(np.argmax(probs))
            cls_names = self.class_names
            return {
                "level": cls_names[idx],
                "confidence": float(probs[idx]),
                "method": "cnn_torchvision",
                "all_probs": {cls_names[i]: float(p) for i, p in enumerate(probs)},
            }

        # YOLO-cls path
        result = self.model.predict(image_crop, verbose=False)[0]
        if not hasattr(result, "probs") or result.probs is None:
            return {"level": "orta", "confidence": 0.0, "method": "cnn_failed"}
        probs = result.probs.data.cpu().numpy()
        idx = int(np.argmax(probs))
        cls_names = list(self.model.names.values()) if hasattr(self.model, "names") else SEVERITY_LEVELS
        return {
            "level": cls_names[idx],
            "confidence": float(probs[idx]),
            "method": "cnn_yolo",
            "all_probs": {cls_names[i]: float(p) for i, p in enumerate(probs)},
        }


class EnsembleSeverity:
    """Hibrit: kural tabanli + CNN ensemble. CNN yoksa sadece kural."""

    def __init__(self, cnn_weights=None, rule_weight=0.4, cnn_weight=0.6):
        self.rule = RuleBasedSeverity()
        self.cnn = CNNSeverity(cnn_weights) if cnn_weights else None
        self.rule_weight = rule_weight
        self.cnn_weight = cnn_weight

    def predict(self, damage_type, part_name, area_ratio, image_crop=None):
        rule_pred = self.rule.predict(damage_type, part_name, area_ratio)

        if self.cnn is None or image_crop is None:
            rule_pred["method"] = "rule_only"
            return rule_pred

        cnn_pred = self.cnn.predict(image_crop)

        # Anlasma varsa kolay
        if rule_pred["level"] == cnn_pred["level"]:
            return {
                "level": rule_pred["level"],
                "confidence": max(rule_pred["confidence"], cnn_pred["confidence"]),
                "method": "ensemble_agree",
                "rule": rule_pred,
                "cnn": cnn_pred,
            }

        # Catismada: agirlikli oyla
        scores = {lvl: 0.0 for lvl in SEVERITY_LEVELS}
        scores[rule_pred["level"]] += self.rule_weight * rule_pred["confidence"]
        scores[cnn_pred["level"]] += self.cnn_weight * cnn_pred["confidence"]
        if "all_probs" in cnn_pred:
            for lvl, p in cnn_pred["all_probs"].items():
                if lvl in scores:
                    scores[lvl] += 0.3 * p

        best = max(scores, key=scores.get)
        return {
            "level": best,
            "confidence": scores[best],
            "method": "ensemble_resolved",
            "rule": rule_pred,
            "cnn": cnn_pred,
            "ensemble_scores": scores,
        }


def crop_damage(image, bbox, padding=0.15):
    """Bbox cevresinde padding'li crop dondur."""
    h, w = image.shape[:2]
    x1, y1, x2, y2 = bbox
    bw, bh = x2 - x1, y2 - y1
    px, py = int(bw * padding), int(bh * padding)
    x1 = max(0, int(x1) - px)
    y1 = max(0, int(y1) - py)
    x2 = min(w, int(x2) + px)
    y2 = min(h, int(y2) + py)
    return image[y1:y2, x1:x2]


def cmd_train(args):
    """YOLO-cls ile siddet modeli egit."""
    model = YOLO(f"{args.model}.pt")
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        optimizer="AdamW",
        lr0=0.001,
        weight_decay=0.0001,
        patience=20,
        plots=True,
        project="runs/arac-hasar",
        name=f"severity_{args.model}_ep{args.epochs}",
    )


def cmd_test(args):
    """Tek goruntude tum siddet siniflandirma yontemlerini dene."""
    image = cv2.imread(args.image)
    if image is None:
        raise FileNotFoundError(args.image)

    # Hasar modeli ile bul
    damage_model = YOLO(args.damage_weights)
    results = damage_model.predict(image, verbose=False)[0]

    if not results.boxes:
        print("Hasar bulunamadi.")
        return

    ensemble = EnsembleSeverity(cnn_weights=args.severity_weights)

    h, w = image.shape[:2]
    output = []
    for i, box in enumerate(results.boxes):
        cls_id = int(box.cls.item())
        damage_type = damage_model.names[cls_id]
        bbox = box.xyxy[0].tolist()

        # Alan orani: maske varsa maskeden, yoksa bbox'tan.
        # results.masks.data is at the model's mask resolution (typ. 160x160
        # or imgsz/4), so divide by the mask's own area for a consistent
        # ratio. Bbox-based fallback divides by the full image area.
        if results.masks is not None and i < len(results.masks.data):
            mask_t = results.masks.data[i]
            mh, mw = mask_t.shape[-2:]
            area_pixels = float(mask_t.sum())
            area_ratio = area_pixels / float(mh * mw) if (mh * mw) else 0.0
        else:
            area_pixels = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
            area_ratio = area_pixels / (h * w)

        # Parca varsayalim "unknown" (parca pipeline'i pipeline.py'da entegre)
        crop = crop_damage(image, bbox)
        sev = ensemble.predict(damage_type, "unknown", area_ratio, crop)

        output.append({
            "damage_id": i,
            "type": damage_type,
            "area_ratio": round(area_ratio, 5),
            "severity": sev,
        })

    print(json.dumps(output, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="cmd")

    p_train = subs.add_parser("train")
    p_train.add_argument("--data", type=str, required=True,
                         help="data/severity_yolo (train/val/test alti hafif/orta/agir klasorlu)")
    p_train.add_argument("--model", type=str, default="yolo26n-cls")
    p_train.add_argument("--epochs", type=int, default=50)
    p_train.add_argument("--imgsz", type=int, default=224)
    p_train.add_argument("--batch", type=int, default=64)
    p_train.add_argument("--device", type=str, default="0")
    p_train.set_defaults(func=cmd_train)

    p_test = subs.add_parser("test")
    p_test.add_argument("--image", type=str, required=True)
    p_test.add_argument("--damage_weights", type=str, required=True)
    p_test.add_argument("--severity_weights", type=str, default=None)
    p_test.set_defaults(func=cmd_test)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
