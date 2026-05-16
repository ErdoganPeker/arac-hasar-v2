"""
inference_demo.py
Tek goruntu uzerinde model inference + JSON cikti.
Mobil/backend entegrasyonu icin referans formati.

Kullanim:
    python inference_demo.py --weights runs/.../best.pt --image test.jpg --output result.json
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO


CARDD_CLASSES = ["dent", "scratch", "crack", "glass_shatter", "lamp_broken", "tire_flat"]

# Backend'in tukettigi ortak JSON sema
def build_response(img_path, predictions, img_size):
    """Frontend/backend'in beklenebilecek bir format."""
    h, w = img_size
    damages = []
    for i, box in enumerate(predictions.boxes):
        cls_id = int(box.cls.item())
        conf = float(box.conf.item())
        x1, y1, x2, y2 = box.xyxy[0].tolist()

        damage_area = 0.0
        area_ratio = 0.0
        polygon_norm = []
        if predictions.masks is not None and i < len(predictions.masks.xy):
            poly = predictions.masks.xy[i]
            polygon_norm = [[float(p[0] / w), float(p[1] / h)] for p in poly]
            # masks.data is at YOLO's network resolution (e.g. 160x160), not
            # the original image — compute area_ratio in mask-space so it's
            # consistent regardless of the source image resolution.
            mask_bin = predictions.masks.data[i].cpu().numpy()
            damage_area = float(mask_bin.sum())
            mh, mw = mask_bin.shape[-2:]
            area_ratio = damage_area / float(mh * mw) if (mh * mw) else 0.0

        damages.append({
            "id": i,
            "class": CARDD_CLASSES[cls_id],
            "confidence": round(conf, 4),
            "bbox": {
                "x1": round(x1, 2), "y1": round(y1, 2),
                "x2": round(x2, 2), "y2": round(y2, 2),
            },
            "bbox_normalized": {
                "x1": round(x1 / w, 4), "y1": round(y1 / h, 4),
                "x2": round(x2 / w, 4), "y2": round(y2 / h, 4),
            },
            "polygon_normalized": polygon_norm,
            "area_pixels": round(damage_area, 2),
            "area_ratio": round(area_ratio, 6),
        })

    return {
        "image": str(img_path),
        "width": w,
        "height": h,
        "damage_count": len(damages),
        "damages": damages,
        # Hizli ozet - mobil UI icin
        "summary": {
            "has_damage": len(damages) > 0,
            "classes_detected": sorted(set(d["class"] for d in damages)),
            "max_confidence": max([d["confidence"] for d in damages], default=0.0),
            "total_damage_area_ratio": round(
                sum(d["area_ratio"] for d in damages), 4
            ),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", type=str, required=True)
    parser.add_argument("--image", type=str, required=True)
    parser.add_argument("--output", type=str, default=None,
                        help="JSON cikti dosyasi (varsayilan: <image>_result.json)")
    parser.add_argument("--save_overlay", action="store_true",
                        help="Goruntu uzerine cizimi de kaydet")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--conf", type=float, default=0.25)
    args = parser.parse_args()

    img_path = Path(args.image)
    if not img_path.exists():
        raise FileNotFoundError(f"Goruntu bulunamadi: {img_path}")

    # Model yukle (singleton olarak tutmak gerekir gercek backend'de)
    model = YOLO(args.weights)

    # Inference
    results = model.predict(str(img_path), imgsz=args.imgsz, conf=args.conf,
                            verbose=False)
    pred = results[0]

    # Goruntu boyutu
    img = cv2.imread(str(img_path))
    h, w = img.shape[:2]

    # JSON yaratimi
    response = build_response(img_path, pred, (h, w))

    # Cikti yolu
    out_path = Path(args.output) if args.output else img_path.with_suffix(".result.json")
    with open(out_path, "w") as f:
        json.dump(response, f, indent=2)

    print(f"Hasar sayisi: {response['damage_count']}")
    print(f"Tespit edilen siniflar: {response['summary']['classes_detected']}")
    print(f"Toplam hasar/araz alani orani: {response['summary']['total_damage_area_ratio']}")
    print(f"JSON: {out_path}")

    # Overlay kaydet
    if args.save_overlay:
        overlay = pred.plot()  # Ultralytics built-in cizim
        overlay_path = img_path.with_suffix(".overlay.jpg")
        cv2.imwrite(str(overlay_path), overlay)
        print(f"Overlay: {overlay_path}")


if __name__ == "__main__":
    main()
