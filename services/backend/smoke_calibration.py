"""Calibration smoke: run all sample images, measure unassigned ratio."""
import time
import json
import sys
from pathlib import Path

import cv2
from ml_service import ml_pipeline

ml_pipeline.warm_up()

sample_dir = Path("/tmp/samples")
images = sorted(sample_dir.glob("*.jpg"))
print(f"FOUND_IMAGES: {len(images)}")

total_damages = 0
total_unassigned = 0
total_low_conf = 0
per_image = []

# Match methods aren't on the v2 standard schema, so peek into the
# legacy parts-centric layout (under .parts[*].damages[*]) which is
# what the backend emits to clients via aggregate_results.
for img_path in images:
    img = cv2.imread(str(img_path))
    if img is None:
        print(f"SKIP_UNREADABLE: {img_path.name}")
        continue
    t0 = time.perf_counter()
    r = ml_pipeline.analyze(img)
    ms = (time.perf_counter() - t0) * 1000

    # Collect damages from parts-centric output (flat_legacy default ON)
    parts = r.get("parts", []) or []
    damages_via_parts = sum(len(p.get("damages", []) or []) for p in parts)
    unassigned = r.get("unassigned_damages", []) or []
    summary = r.get("summary", {}) or {}
    total = summary.get("total_damage_count", damages_via_parts + len(unassigned))

    # Count low_confidence_match flags across all parts.damages and unassigned
    low_conf = 0
    for p in parts:
        for d in p.get("damages", []) or []:
            if d.get("is_low_confidence_match"):
                low_conf += 1
    for d in unassigned:
        if d.get("is_low_confidence_match"):
            low_conf += 1

    total_damages += total
    total_unassigned += len(unassigned)
    total_low_conf += low_conf

    per_image.append({
        "img": img_path.name,
        "ms": round(ms, 1),
        "damages": total,
        "unassigned": len(unassigned),
        "low_conf": low_conf,
        "parts_detected": len(parts),
    })
    print(f"  {img_path.name}: ms={ms:.0f} total={total} unassigned={len(unassigned)} low_conf={low_conf} parts={len(parts)}")

print()
print("=" * 60)
print(f"AGGREGATE: damages={total_damages} unassigned={total_unassigned} low_conf={total_low_conf}")
if total_damages > 0:
    pct = 100.0 * total_unassigned / total_damages
    print(f"UNASSIGNED_PCT: {pct:.1f}%")
    pct_lc = 100.0 * total_low_conf / total_damages
    print(f"LOW_CONFIDENCE_PCT: {pct_lc:.1f}%")
else:
    print("NO_DAMAGES_FOUND")

# Single-image deep test: 01_dent__dent__000549.jpg
print()
print("=" * 60)
print("SINGLE_IMAGE_DEEP_TEST: 01_dent__dent__000549.jpg")
target = sample_dir / "01_dent__dent__000549.jpg"
if target.exists():
    img = cv2.imread(str(target))
    r = ml_pipeline.analyze(img)
    print("KEYS:", list(r.keys()))
    print("IMAGE_URL:", (r.get("image") or {}).get("url"))
    print("UNASSIGNED:", len(r.get("unassigned_damages", []) or []))
    print("PARTS:")
    for p in (r.get("parts", []) or [])[:8]:
        dn = p.get("damage_count", len(p.get("damages", []) or []))
        print(f"  {p.get('name')}: status={p.get('status')} damages={dn}")
    print("SUMMARY:", json.dumps(r.get("summary", {}), ensure_ascii=False, default=str)[:400])
else:
    print("TARGET_NOT_FOUND")
