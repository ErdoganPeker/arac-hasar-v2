"""
evaluate.py
Egitilmis modeli test seti uzerinde degerlendir + hata analizi yap.

Ornek:
    python evaluate.py \
        --weights runs/arac-hasar/yolo26m-seg_ep150/weights/best.pt \
        --data cardd.yaml --split test --save_failures

Cikti:
    runs/eval_<timestamp>/
        results.json        # Tum metrikler
        per_class.csv       # Sinif bazinda detay
        confusion_matrix.png
        failures/           # Yanlis tahminlerin gorsellesmesi (ilk N)
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from tqdm import tqdm
from ultralytics import YOLO


CARDD_CLASSES = ["dent", "scratch", "crack", "glass_shatter", "lamp_broken", "tire_flat"]


def visualize_prediction(img_path, pred_result, gt_path, save_path):
    """Bir goruntude tahmin + GT'yi yan yana cizer."""
    img = cv2.imread(str(img_path))
    if img is None:
        return
    h, w = img.shape[:2]

    # GT okuma
    gt_img = img.copy()
    if gt_path and gt_path.exists():
        with open(gt_path, "r") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) < 7:
                    continue
                cls_id = int(parts[0])
                coords = [float(x) for x in parts[1:]]
                pts = np.array([[coords[i] * w, coords[i + 1] * h]
                                for i in range(0, len(coords), 2)], dtype=np.int32)
                color = (0, 255, 0)  # yesil = GT
                cv2.polylines(gt_img, [pts], True, color, 2)
                if len(pts) > 0:
                    cv2.putText(gt_img, CARDD_CLASSES[cls_id],
                                tuple(pts[0]), cv2.FONT_HERSHEY_SIMPLEX,
                                0.6, color, 2)

    # Tahmin
    pred_img = img.copy()
    if pred_result.masks is not None:
        for i, mask_xy in enumerate(pred_result.masks.xy):
            cls_id = int(pred_result.boxes.cls[i].item())
            conf = float(pred_result.boxes.conf[i].item())
            pts = mask_xy.astype(np.int32)
            color = (0, 0, 255)  # kirmizi = tahmin
            cv2.polylines(pred_img, [pts], True, color, 2)
            if len(pts) > 0:
                label = f"{CARDD_CLASSES[cls_id]} {conf:.2f}"
                cv2.putText(pred_img, label, tuple(pts[0]),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

    # Yan yana birlestir
    combined = np.hstack([gt_img, pred_img])
    cv2.putText(combined, "GT (yesil)", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    cv2.putText(combined, "Tahmin (kirmizi)", (w + 10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

    cv2.imwrite(str(save_path), combined)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", type=str, required=True)
    parser.add_argument("--data", type=str, default="cardd.yaml")
    parser.add_argument("--split", type=str, default="test",
                        choices=["train", "val", "test"])
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--iou", type=float, default=0.5)
    parser.add_argument("--save_failures", action="store_true",
                        help="Hatali tahminleri PNG olarak kaydet")
    parser.add_argument("--max_failures", type=int, default=100)
    args = parser.parse_args()

    # Cikti klasoru
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(f"runs/eval_{timestamp}")
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Cikti klasoru: {out_dir}")

    # Modeli yukle
    model = YOLO(args.weights)

    # Ultralytics built-in val - en saglikli metrikler
    print(f"\n=== Validation ({args.split}) ===")
    metrics = model.val(
        data=args.data,
        split=args.split,
        imgsz=args.imgsz,
        batch=args.batch,
        conf=args.conf,
        iou=args.iou,
        plots=True,
        save_json=True,
        project=str(out_dir),
        name="val_run",
    )

    # Genel metrikler
    print("\n=== Genel Metrikler ===")
    box_map = metrics.box.map
    box_map50 = metrics.box.map50
    box_map75 = metrics.box.map75
    mask_map = metrics.seg.map
    mask_map50 = metrics.seg.map50
    print(f"Box  mAP50:    {box_map50:.4f}")
    print(f"Box  mAP50-95: {box_map:.4f}")
    print(f"Box  mAP75:    {box_map75:.4f}")
    print(f"Mask mAP50:    {mask_map50:.4f}")
    print(f"Mask mAP50-95: {mask_map:.4f}")

    # Per-class metrikler
    print("\n=== Sinif Bazinda mAP50 ===")
    per_class = {}
    for i, name in enumerate(CARDD_CLASSES):
        if i < len(metrics.box.maps):
            class_map50 = metrics.box.ap50[i] if i < len(metrics.box.ap50) else 0.0
            class_map = metrics.box.maps[i] if i < len(metrics.box.maps) else 0.0
            per_class[name] = {
                "map50": float(class_map50),
                "map50_95": float(class_map),
            }
            print(f"  {name:18s}  mAP50={class_map50:.4f}  mAP50-95={class_map:.4f}")

    # JSON olarak kaydet
    results = {
        "weights": args.weights,
        "split": args.split,
        "overall": {
            "box_map50": float(box_map50),
            "box_map50_95": float(box_map),
            "mask_map50": float(mask_map50),
            "mask_map50_95": float(mask_map),
        },
        "per_class": per_class,
    }
    with open(out_dir / "results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults: {out_dir / 'results.json'}")

    # Failure case'leri kaydet
    if args.save_failures:
        print(f"\n=== Failure Analizi (max {args.max_failures}) ===")
        failures_dir = out_dir / "failures"
        failures_dir.mkdir(exist_ok=True)

        # Test goruntulerinin yolunu cikar
        import yaml as yaml_mod
        with open(args.data, "r") as f:
            data_cfg = yaml_mod.safe_load(f)
        data_root = Path(data_cfg["path"])
        img_dir = data_root / data_cfg[args.split]
        lbl_dir = data_root / "labels" / args.split

        img_paths = sorted(list(img_dir.glob("*.jpg")) + list(img_dir.glob("*.png")))
        failures_saved = 0

        for img_path in tqdm(img_paths, desc="Failure tarama"):
            if failures_saved >= args.max_failures:
                break

            pred = model.predict(str(img_path), conf=args.conf,
                                 verbose=False, imgsz=args.imgsz)[0]
            gt_path = lbl_dir / (img_path.stem + ".txt")

            # Basit failure tanimi: tahmin sayisi != GT sayisi VEYA bos vs dolu
            gt_count = 0
            if gt_path.exists():
                with open(gt_path, "r") as f:
                    gt_count = len([l for l in f if l.strip()])
            pred_count = len(pred.boxes) if pred.boxes is not None else 0

            if gt_count != pred_count:
                save_path = failures_dir / f"{img_path.stem}_gt{gt_count}_pred{pred_count}.jpg"
                visualize_prediction(img_path, pred, gt_path, save_path)
                failures_saved += 1

        print(f"Kaydedilen failure: {failures_saved} -> {failures_dir}")

    print(f"\n=== Hata Analizi Onerileri ===")
    if per_class:
        worst = min(per_class.items(), key=lambda kv: kv[1]["map50"])
        print(f"En zayif sinif: {worst[0]} (mAP50={worst[1]['map50']:.3f})")
        if worst[1]["map50"] < 0.3:
            print(f"  -> Bu sinifin etiketlerini elden gozden gecir, gercek anlamda az veya hatali olabilir.")
            print(f"  -> Class weights ayarla veya focal loss dene.")

    if mask_map50 < 0.45:
        print("Mask mAP50 dusuk -> imgsz artir (640->1024) veya mask loss weight'i artir")
    if box_map50 < 0.55:
        print("Box mAP50 baseline'in altinda -> daha cok epoch, daha buyuk model dene")


if __name__ == "__main__":
    main()
