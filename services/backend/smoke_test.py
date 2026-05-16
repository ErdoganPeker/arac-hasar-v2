"""Smoke test runner — executed inside hasarui-backend container."""
import time
import json
import cv2
import sys

from ml_service import ml_pipeline

t0 = time.perf_counter()
ml_pipeline.warm_up()
warmup_s = time.perf_counter() - t0
print("WARMUP_SEC:", round(warmup_s, 2))

img = cv2.imread("/tmp/car.jpg")
print("IMG_SHAPE:", img.shape)

# 1st inference (post-warmup)
t0 = time.perf_counter()
result = ml_pipeline.analyze(img)
elapsed_ms = (time.perf_counter() - t0) * 1000
print("INFERENCE_MS_1:", round(elapsed_ms, 1))

# 2nd inference (steady state)
t0 = time.perf_counter()
result2 = ml_pipeline.analyze(img)
elapsed_ms2 = (time.perf_counter() - t0) * 1000
print("INFERENCE_MS_2:", round(elapsed_ms2, 1))

print("KEYS:", list(result.keys()))
print("PARTS_COUNT:", len(result.get("parts", [])))
print("UNASSIGNED_DAMAGES:", len(result.get("unassigned_damages", [])))
print("MULTI_PART_DAMAGES:", len(result.get("multi_part_damages", [])))
summary = result.get("summary", {})
print("SUMMARY:", json.dumps(summary, ensure_ascii=False, default=str))

if result.get("parts"):
    p0 = result["parts"][0]
    print("PART0_KEYS:", list(p0.keys()))
    print("PART0_NAME:", p0.get("name"), "STATUS:", p0.get("status"),
          "DAMAGE_COUNT:", p0.get("damage_count"))
    if p0.get("damages"):
        d0 = p0["damages"][0]
        print("DAMAGE0_KEYS:", list(d0.keys()))
        print("DAMAGE0_TYPE:", d0.get("type"))
        print("DAMAGE0_SEV:", json.dumps(d0.get("severity"), default=str))
        print("DAMAGE0_COST:", json.dumps(d0.get("cost"), default=str))

print("PROCESSING_MS:", json.dumps(result.get("processing_ms"), default=str))

# Edge-case tests
print("\n=== EDGE: tiny image 100x100 ===")
tiny = cv2.resize(img, (100, 100))
try:
    t0 = time.perf_counter()
    r_tiny = ml_pipeline.analyze(tiny)
    print("TINY_OK_MS:", round((time.perf_counter() - t0) * 1000, 1))
    print("TINY_PARTS:", len(r_tiny.get("parts", [])),
          "TINY_DAMAGES:", r_tiny.get("summary", {}).get("total_damage_count"))
except Exception as e:
    print("TINY_FAIL:", type(e).__name__, str(e)[:200])

print("\n=== EDGE: large image 4000x3000 ===")
try:
    import numpy as np
    big = cv2.resize(img, (4000, 3000))
    t0 = time.perf_counter()
    r_big = ml_pipeline.analyze(big)
    print("BIG_OK_MS:", round((time.perf_counter() - t0) * 1000, 1))
    print("BIG_PARTS:", len(r_big.get("parts", [])),
          "BIG_DAMAGES:", r_big.get("summary", {}).get("total_damage_count"))
except Exception as e:
    print("BIG_FAIL:", type(e).__name__, str(e)[:200])

print("\n=== EDGE: blank black image ===")
import numpy as np
blank = np.zeros((640, 640, 3), dtype=np.uint8)
try:
    r_blank = ml_pipeline.analyze(blank)
    print("BLANK_PARTS:", len(r_blank.get("parts", [])))
    print("BLANK_DAMAGES:", r_blank.get("summary", {}).get("total_damage_count"))
    print("BLANK_COST:", r_blank.get("summary", {}).get("total_cost_range_tl"))
    print("BLANK_REPAIR:", r_blank.get("summary", {}).get("repair_recommendation"))
except Exception as e:
    print("BLANK_FAIL:", type(e).__name__, str(e)[:200])
