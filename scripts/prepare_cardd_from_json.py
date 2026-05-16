"""
prepare_cardd_from_json.py — CarDD HF mirror samples.json → YOLO segmentation format

Fast direct parser. No FiftyOne dependency. Reads samples.json (FiftyOne export format)
and converts each detection's mask (zlib-compressed binary, base64) to YOLO segmentation
polygons.

Usage:
    python scripts/prepare_cardd_from_json.py \\
        --samples C:\\Users\\Erdogan\\fiftyone\\huggingface\\hub\\harpreetsahota\\CarDD\\samples.json \\
        --images_root C:\\Users\\Erdogan\\Desktop\\arac-hasar-v2\\services\\ml\\data\\cardd_hf \\
        --output_dir services/ml/data/cardd_yolo
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import random
import shutil
import sys
import zlib
from pathlib import Path

import numpy as np
import cv2
from tqdm import tqdm

# Class mapping: label (lowercase) → class_id (matches services/ml/cardd.yaml)
CLASS_MAP = {
    "dent": 0,
    "scratch": 1,
    "crack": 2,
    "glass shatter": 3,
    "lamp broken": 4,
    "tire flat": 5,
}
CLASS_NAMES = ["dent", "scratch", "crack", "glass_shatter", "lamp_broken", "tire_flat"]


def decode_mask(mask_b64: str) -> np.ndarray | None:
    """FiftyOne mask: zlib-compressed numpy .npy bytes, base64-encoded.

    Returns a 2D boolean (or uint8) array, or None if decode fails.
    """
    try:
        raw = base64.b64decode(mask_b64)
        decompressed = zlib.decompress(raw)
        arr = np.load(io.BytesIO(decompressed))
        return arr
    except Exception:
        return None


def mask_to_polygon(
    mask_arr: np.ndarray,
    bbox: list,  # [x_min, y_min, w, h] normalized
    img_w: int,
    img_h: int,
) -> list[list[tuple[float, float]]]:
    """Convert mask + bbox to normalized image-level polygons.

    Mask is a 2D array (H, W) at bbox pixel resolution.
    """
    if mask_arr is None or mask_arr.ndim != 2:
        return []
    bx, by, _, _ = bbox
    mh, mw = mask_arr.shape
    mask_2d = mask_arr
    # Find contours in mask
    contours, _ = cv2.findContours(
        (mask_2d > 0).astype(np.uint8) * 255,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )

    polygons = []
    for c in contours:
        if len(c) < 3:
            continue
        # Simplify polygon to reduce points (epsilon = 0.5% of perimeter)
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.005 * peri, True)
        if len(approx) < 3:
            continue
        # Convert from mask-local pixels to image-normalized coords
        poly = []
        for pt in approx.squeeze(axis=1):
            px, py = pt[0], pt[1]
            # mask-local pixel → image-pixel: image_x = bx*img_w + px
            image_x = bx * img_w + px
            image_y = by * img_h + py
            nx = image_x / img_w
            ny = image_y / img_h
            poly.append((max(0.0, min(1.0, nx)), max(0.0, min(1.0, ny))))
        polygons.append(poly)
    return polygons


def bbox_to_polygon(bbox: list) -> list[tuple[float, float]]:
    """Fallback: bbox as 4-point polygon (normalized)."""
    bx, by, bw, bh = bbox
    return [(bx, by), (bx + bw, by), (bx + bw, by + bh), (bx, by + bh)]


def process_sample(sample: dict, images_root: Path, splits: dict, out_dir: Path) -> str:
    """Returns: 'ok' | 'skip_no_img' | 'skip_no_label' | 'skip_decode_fail'"""
    rel_path = sample["filepath"]  # e.g., "data/000001.jpg"
    img_path = images_root / rel_path
    if not img_path.exists():
        return "skip_no_img"

    meta = sample.get("metadata") or {}
    img_w = meta.get("width", 0)
    img_h = meta.get("height", 0)
    if not (img_w and img_h):
        # Read from file
        from PIL import Image
        with Image.open(img_path) as im:
            img_w, img_h = im.size

    segmentations = sample.get("segmentations") or {}
    detections_list = segmentations.get("detections") or []

    # Fallback to detections if no segmentations
    if not detections_list:
        det_field = sample.get("detections") or {}
        detections_list = det_field.get("detections") or []

    yolo_lines = []
    for det in detections_list:
        label = (det.get("label") or "").lower().strip()
        if label not in CLASS_MAP:
            continue
        cls_id = CLASS_MAP[label]
        bbox = det.get("bounding_box") or []
        if len(bbox) != 4:
            continue

        polygons = []
        mask_obj = det.get("mask")
        if mask_obj and "$binary" in mask_obj:
            b64 = mask_obj["$binary"].get("base64", "")
            if b64:
                try:
                    mask_arr = decode_mask(b64)
                    polygons = mask_to_polygon(mask_arr, bbox, img_w, img_h)
                except Exception:
                    polygons = []

        if not polygons:
            # Fallback to bbox
            polygons = [bbox_to_polygon(bbox)]

        for poly in polygons:
            if len(poly) < 3:
                continue
            coords = " ".join(f"{x:.6f} {y:.6f}" for (x, y) in poly)
            yolo_lines.append(f"{cls_id} {coords}")

    if not yolo_lines:
        return "skip_no_label"

    sid = sample.get("_id", {}).get("$oid", "")
    split = splits.get(sid, "train")

    # Copy/hardlink image
    dst_img = out_dir / "images" / split / img_path.name
    if not dst_img.exists():
        try:
            import os
            os.link(img_path, dst_img)  # Hardlink for zero-copy
        except OSError:
            shutil.copy2(img_path, dst_img)

    # Write labels
    label_path = out_dir / "labels" / split / (img_path.stem + ".txt")
    label_path.write_text("\n".join(yolo_lines), encoding="utf-8")
    return "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=Path, required=True)
    ap.add_argument("--images_root", type=Path, required=True,
                    help="Path containing 'data/' subdir with images")
    ap.add_argument("--output_dir", type=Path, required=True)
    ap.add_argument("--train_ratio", type=float, default=0.8)
    ap.add_argument("--val_ratio", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    print(f">> Loading samples.json: {args.samples}")
    with open(args.samples, "r", encoding="utf-8") as f:
        data = json.load(f)
    samples = data.get("samples", data) if isinstance(data, dict) else data
    print(f">> Loaded {len(samples)} samples")

    # Prepare output dirs
    out = args.output_dir
    for sp in ("train", "val", "test"):
        (out / "images" / sp).mkdir(parents=True, exist_ok=True)
        (out / "labels" / sp).mkdir(parents=True, exist_ok=True)

    # Split
    random.seed(args.seed)
    sample_ids = [s.get("_id", {}).get("$oid", f"id_{i}") for i, s in enumerate(samples)]
    shuffled = list(zip(sample_ids, samples))
    random.shuffle(shuffled)
    n = len(shuffled)
    n_train = int(n * args.train_ratio)
    n_val = int(n * args.val_ratio)
    splits = {}
    for i, (sid, _) in enumerate(shuffled):
        if i < n_train:
            splits[sid] = "train"
        elif i < n_train + n_val:
            splits[sid] = "val"
        else:
            splits[sid] = "test"

    counts = {"ok": 0, "skip_no_img": 0, "skip_no_label": 0, "skip_decode_fail": 0}
    for sample in tqdm(samples, desc="Converting"):
        result = process_sample(sample, args.images_root, splits, out)
        counts[result] = counts.get(result, 0) + 1

    print()
    print(">> Conversion complete:")
    for k, v in counts.items():
        print(f"   {k}: {v}")

    # Per-split tallies
    print(">> Per-split tallies:")
    for sp in ("train", "val", "test"):
        n_imgs = len(list((out / "images" / sp).iterdir()))
        n_lbls = len(list((out / "labels" / sp).iterdir()))
        print(f"   {sp}: images={n_imgs}, labels={n_lbls}")

    # Write YAML config
    yaml_path = out / "cardd.yaml"
    yaml_path.write_text(
        "# Auto-generated by prepare_cardd_from_json.py\n"
        f"path: {out.resolve().as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "test: images/test\n"
        "nc: 6\n"
        "names:\n" + "\n".join(f"  {i}: {n}" for i, n in enumerate(CLASS_NAMES)) + "\n",
        encoding="utf-8",
    )
    print(f">> Wrote dataset config: {yaml_path}")


if __name__ == "__main__":
    main()
