"""
prepare_cardd_hf.py — CarDD HuggingFace mirror (FiftyOne format) → YOLO segmentation format

The HF mirror `harpreetsahota/CarDD` is a FiftyOne dataset (not COCO). This script:
1. Loads the dataset via `fiftyone.utils.huggingface.load_from_hub`
2. Maps original CarDD class names to our 6-class taxonomy
3. Exports to YOLO segmentation format (images + .txt polygons)
4. Creates train/val/test splits (80/10/10)

Usage:
    python scripts/prepare_cardd_hf.py \\
        --output_dir services/ml/data/cardd_yolo \\
        [--max_samples N]
"""
from __future__ import annotations

import argparse
import os
import random
import shutil
import sys
from pathlib import Path

# Class mapping — CarDD original labels → our taxonomy (matches services/ml/cardd.yaml)
CLASS_MAP = {
    "dent": 0,
    "scratch": 1,
    "crack": 2,
    "glass shatter": 3,
    "glass_shatter": 3,
    "broken lamp": 4,
    "lamp broken": 4,
    "lamp_broken": 4,
    "broken_lamp": 4,
    "tire flat": 5,
    "tire_flat": 5,
    "flat tire": 5,
}

CLASS_NAMES = ["dent", "scratch", "crack", "glass_shatter", "lamp_broken", "tire_flat"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output_dir", required=True, type=Path)
    ap.add_argument("--hf_repo", default="harpreetsahota/CarDD")
    ap.add_argument("--max_samples", type=int, default=None,
                    help="Limit samples (debugging)")
    ap.add_argument("--train_ratio", type=float, default=0.8)
    ap.add_argument("--val_ratio", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--symlink", action="store_true",
                    help="Symlink images instead of copying (saves disk)")
    args = ap.parse_args()

    try:
        import fiftyone as fo
        from fiftyone.utils.huggingface import load_from_hub
    except ImportError:
        print("FiftyOne yüklü değil. Önce: pip install fiftyone")
        sys.exit(1)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    for split in ("train", "val", "test"):
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)

    print(f">> Loading dataset from HF: {args.hf_repo}")
    kwargs = {}
    if args.max_samples:
        kwargs["max_samples"] = args.max_samples
    dataset = load_from_hub(args.hf_repo, **kwargs)
    print(f">> Loaded {len(dataset)} samples")

    # Explore label structure once
    sample = dataset.first()
    print(">> First sample fields:")
    for field, value in sample.iter_fields():
        if value is None:
            continue
        print(f"   {field}: {type(value).__name__}")

    # Find the label field — usually 'ground_truth', 'detections', or 'segmentations'
    label_field = None
    for cand in ("ground_truth", "detections", "segmentations", "polylines"):
        if dataset.has_sample_field(cand):
            label_field = cand
            break
    if label_field is None:
        print("HATA: label field bulunamadı. Mevcut field'lar:")
        print(dataset.get_field_schema())
        sys.exit(2)
    print(f">> Using label field: {label_field}")

    # Shuffle + split
    random.seed(args.seed)
    sample_ids = list(dataset.values("id"))
    random.shuffle(sample_ids)
    n = len(sample_ids)
    n_train = int(n * args.train_ratio)
    n_val = int(n * args.val_ratio)
    split_assign: dict[str, str] = {}
    for i, sid in enumerate(sample_ids):
        if i < n_train:
            split_assign[sid] = "train"
        elif i < n_train + n_val:
            split_assign[sid] = "val"
        else:
            split_assign[sid] = "test"

    counts = {"train": 0, "val": 0, "test": 0}
    skipped = 0

    for sample in dataset.iter_samples(progress=True):
        split = split_assign[sample.id]
        img_path = Path(sample.filepath)
        if not img_path.exists():
            skipped += 1
            continue

        # Get image dimensions
        try:
            w = sample.metadata.width
            h = sample.metadata.height
        except (AttributeError, TypeError):
            from PIL import Image
            with Image.open(img_path) as im:
                w, h = im.size

        # Get label field — may be Detections or Polylines
        labels = sample[label_field]
        if labels is None:
            skipped += 1
            continue

        yolo_lines = []
        # Detections has .detections, Polylines has .polylines
        items = (
            getattr(labels, "detections", None)
            or getattr(labels, "polylines", None)
            or getattr(labels, "segmentations", None)
            or []
        )

        for item in items:
            cls_name = (item.label or "").lower().strip().replace(" ", "_")
            if cls_name not in CLASS_MAP:
                continue
            cls_id = CLASS_MAP[cls_name]

            # Try mask first (Detections may have mask), then polylines
            mask = getattr(item, "mask", None)
            polys = getattr(item, "points", None)

            if polys:
                # Polylines.points is list[list[(x,y) tuples]] — list of contours
                for contour in polys:
                    if len(contour) < 3:
                        continue
                    flat = []
                    for (x, y) in contour:
                        # FiftyOne polylines: normalized [0,1] coords
                        flat.append(f"{x:.6f} {y:.6f}")
                    yolo_lines.append(f"{cls_id} " + " ".join(flat))
            elif mask is not None and hasattr(item, "bounding_box"):
                # Convert mask to polygon contour
                import numpy as np
                import cv2
                bbox = item.bounding_box  # [x_min, y_min, w, h] normalized
                # Mask is relative to bbox; convert to image-level polygon
                mask_array = (mask * 255).astype(np.uint8) if mask.dtype != np.uint8 else mask
                contours, _ = cv2.findContours(mask_array, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                bx, by, bw, bh = bbox
                for c in contours:
                    if len(c) < 3:
                        continue
                    # Normalize: c is (n,1,2) in mask-local pixels
                    mh, mw = mask_array.shape[:2]
                    flat = []
                    for pt in c.squeeze(axis=1):
                        px, py = pt[0] / mw, pt[1] / mh
                        # px,py in [0,1] within bbox; map to image-level
                        ix = bx + px * bw
                        iy = by + py * bh
                        flat.append(f"{ix:.6f} {iy:.6f}")
                    yolo_lines.append(f"{cls_id} " + " ".join(flat))
            elif hasattr(item, "bounding_box"):
                # Fallback: bbox as 4-point polygon
                bx, by, bw, bh = item.bounding_box
                pts = [(bx, by), (bx + bw, by), (bx + bw, by + bh), (bx, by + bh)]
                flat = " ".join(f"{x:.6f} {y:.6f}" for x, y in pts)
                yolo_lines.append(f"{cls_id} {flat}")

        if not yolo_lines:
            skipped += 1
            continue

        # Copy/symlink image
        dst_img = out / "images" / split / img_path.name
        if not dst_img.exists():
            if args.symlink:
                try:
                    os.symlink(img_path, dst_img)
                except OSError:
                    shutil.copy2(img_path, dst_img)
            else:
                shutil.copy2(img_path, dst_img)

        # Write label
        label_path = out / "labels" / split / (img_path.stem + ".txt")
        label_path.write_text("\n".join(yolo_lines), encoding="utf-8")
        counts[split] += 1

    print(f">> Done. Counts: train={counts['train']}, val={counts['val']}, test={counts['test']}, skipped={skipped}")

    # Write YAML config
    yaml_path = out / "cardd.yaml"
    yaml_path.write_text(
        "# Auto-generated by prepare_cardd_hf.py\n"
        f"path: {out.resolve().as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n"
        "names:\n" + "\n".join(f"  {i}: {n}" for i, n in enumerate(CLASS_NAMES)) + "\n",
        encoding="utf-8",
    )
    print(f">> Wrote dataset config: {yaml_path}")


if __name__ == "__main__":
    main()
