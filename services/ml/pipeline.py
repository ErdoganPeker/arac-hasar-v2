"""
pipeline.py - v2 Akıllı Hibrit Pipeline (HARDENED for production)

Production hardening:
  - Thread-safe lazy model loading (singleton)
  - Device autodetect (MODEL_DEVICE=cpu|cuda|auto)
  - @torch.inference_mode() guards
  - Robust image preprocessing (EXIF, RGBA, grayscale, WebP, bytes)
  - Batch inference (analyze_batch)
  - Standardized v2 output schema
  - In-memory PNG visualizations (no disk writes in prod)

Usage:
    from pipeline import DamagePipelineV2

    pipe = DamagePipelineV2(
        damage_weights="runs/.../damage_best.pt",
        parts_weights="runs/.../parts_best.pt",
        severity_weights="runs/.../severity_best.pt",
        cost_table="cost_table.yaml",
    )
    result = pipe.analyze("car.jpg", generate_visuals=True)
"""
from __future__ import annotations

import io
import json
import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import cv2
import numpy as np
import torch
from PIL import Image, ImageOps, UnidentifiedImageError
from ultralytics import YOLO

from cost_engine import CostEngine, repair_recommendation, estimated_days
from severity_classifier import EnsembleSeverity, crop_damage
from output_formatter import to_part_centric, build_standard_output


logger = logging.getLogger(__name__)


# Damage-to-part assignment thresholds.
# NOTE: despite the legacy names, these are compared against the intersection
# ratio (intersection / damage_mask_area), NOT IoU. Intersection ratio is the
# right metric here because the damage mask is almost always smaller than its
# host part, so IoU would be artificially low. IoU is still reported in the
# secondary_parts payload for debugging.
#
# 2026-05-16 calibration: smoke@ex.com run on CarDD test set showed 62%
# unassigned damages. Loosened mask-intersection floor from 0.05 -> 0.02
# and added a BBOX-IoU + bbox-center-distance fallback (see
# `_assign_parts_to_damages`) for damages whose masks don't overlap any
# detected part mask (typically dent/scratch with thin masks vs. coarse
# part polygons). Target: <20% unassigned.
MIN_INTERSECTION_FOR_ASSIGNMENT = 0.02   # below this and no bbox fallback -> "unknown"
MULTI_PART_INTERSECTION_THRESHOLD = 0.12  # add as secondary_part if >= this
LOW_CONFIDENCE_INTERSECTION = 0.08       # mark is_low_confidence_match if < this
# Bbox-fallback thresholds (used when mask intersection == 0 for all parts).
# These are MUCH more permissive because they're a last-resort match.
MIN_BBOX_IOU_FALLBACK = 0.02              # bbox-iou >= this -> low-conf assign
MIN_BBOX_CONTAINMENT_FALLBACK = 0.30      # frac of damage bbox inside part bbox
# Backwards-compat aliases (don't break external imports)
MIN_IOU_FOR_ASSIGNMENT = MIN_INTERSECTION_FOR_ASSIGNMENT
MULTI_PART_IOU_THRESHOLD = MULTI_PART_INTERSECTION_THRESHOLD
LOW_CONFIDENCE_IOU = LOW_CONFIDENCE_INTERSECTION

# Parallelism: damage + parts detection run concurrently. Ultralytics releases
# the GIL during the CUDA/CPU forward, so a ThreadPoolExecutor is the right
# primitive (no need for processes; sharing the same CUDA context is fine).
_DETECTOR_POOL_WORKERS = int(os.getenv("ML_DETECTOR_WORKERS", "2"))

# Model versioning (snapshot-based - update when models retrained)
MODEL_VERSIONS = {
    "damage": "yolo11m-seg_2026-05-15_v1",
    "parts": "yolo11s-seg_2026-05-15_v1",
    "severity": "yolo11n-cls_2026-05-15_v1",
    "pipeline": "v2.1-hardened",
}


# ---------------------------------------------------------------------------
# Device resolution
# ---------------------------------------------------------------------------
def resolve_device(requested: Optional[str] = None) -> str:
    """Resolve device from env or arg. Supports cpu|cuda|auto.

    Env var precedence (first non-empty wins): MODEL_DEVICE, ML_DEVICE.
    Either name is accepted; we standardize on MODEL_DEVICE internally but
    honor ML_DEVICE (used by backend/.env files) for compatibility.
    """
    if requested is None:
        requested = os.getenv("MODEL_DEVICE") or os.getenv("ML_DEVICE") or "auto"
    requested = (requested or "auto").lower().strip()
    if requested == "cpu":
        return "cpu"
    if requested in ("cuda", "gpu"):
        return "cuda" if torch.cuda.is_available() else "cpu"
    # auto
    return "cuda" if torch.cuda.is_available() else "cpu"


# ---------------------------------------------------------------------------
# Image preprocessing - robust to formats / EXIF / channels
# ---------------------------------------------------------------------------
class ImagePreprocessError(ValueError):
    """Raised when an input image cannot be decoded."""


def load_image_bgr(source: Any) -> np.ndarray:
    """Load any image source (path, bytes, PIL, numpy) into BGR uint8 ndarray.

    Handles:
      - JPEG/PNG/WebP/BMP/TIFF
      - EXIF orientation (auto-rotate)
      - RGBA -> RGB (white bg composite)
      - Grayscale / L / LA -> RGB
      - CMYK -> RGB
      - 16-bit images -> 8-bit
    """
    try:
        if isinstance(source, np.ndarray):
            img = source
            if img.ndim == 2:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
            elif img.ndim == 3 and img.shape[2] == 4:
                # numpy RGBA -> BGR (assume RGBA; flatten alpha to white)
                rgb = img[..., :3]
                alpha = img[..., 3:4].astype(np.float32) / 255.0
                white = np.full_like(rgb, 255)
                img = (rgb * alpha + white * (1 - alpha)).astype(np.uint8)
            if img.dtype != np.uint8:
                img = np.clip(img, 0, 255).astype(np.uint8)
            return img

        if isinstance(source, (str, Path)):
            p = Path(source)
            if not p.exists():
                raise ImagePreprocessError(f"Image file not found: {p}")
            with open(p, "rb") as f:
                raw = f.read()
        elif isinstance(source, (bytes, bytearray, memoryview)):
            raw = bytes(source)
        elif isinstance(source, io.IOBase):
            raw = source.read()
        elif isinstance(source, Image.Image):
            return _pil_to_bgr(source)
        else:
            raise ImagePreprocessError(
                f"Unsupported image source type: {type(source).__name__}"
            )

        if not raw:
            raise ImagePreprocessError("Empty image data")

        try:
            pil = Image.open(io.BytesIO(raw))
            pil.load()
        except (UnidentifiedImageError, OSError) as exc:
            raise ImagePreprocessError(f"Corrupted or unsupported image: {exc}") from exc

        return _pil_to_bgr(pil)

    except ImagePreprocessError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ImagePreprocessError(f"Failed to decode image: {exc}") from exc


def _pil_to_bgr(pil: Image.Image) -> np.ndarray:
    """Convert PIL image (any mode) to BGR uint8 ndarray with EXIF rotation."""
    # EXIF auto-rotate
    try:
        pil = ImageOps.exif_transpose(pil)
    except Exception:  # noqa: BLE001
        pass

    mode = pil.mode
    if mode == "RGBA" or mode == "LA":
        bg = Image.new("RGB", pil.size, (255, 255, 255))
        bg.paste(pil, mask=pil.split()[-1])
        pil = bg
    elif mode == "P":
        pil = pil.convert("RGBA")
        bg = Image.new("RGB", pil.size, (255, 255, 255))
        bg.paste(pil, mask=pil.split()[-1])
        pil = bg
    elif mode in ("L", "1", "I", "I;16", "F"):
        pil = pil.convert("RGB")
    elif mode == "CMYK":
        pil = pil.convert("RGB")
    elif mode != "RGB":
        pil = pil.convert("RGB")

    rgb = np.asarray(pil, dtype=np.uint8)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


# ---------------------------------------------------------------------------
# Internal records (dataclasses)
# ---------------------------------------------------------------------------
@dataclass
class DamageRecord:
    id: int
    type: str
    confidence: float
    bbox: tuple
    mask: Optional[np.ndarray] = None
    polygon_normalized: list = field(default_factory=list)
    polygon_pixels: list = field(default_factory=list)
    area_pixels: float = 0.0
    area_ratio: float = 0.0

    primary_part: str = "unknown"
    primary_part_confidence: float = 0.0
    primary_iou: float = 0.0
    secondary_parts: List[dict] = field(default_factory=list)
    is_multi_part: bool = False
    is_low_confidence_match: bool = False

    severity: dict = field(default_factory=dict)
    cost: dict = field(default_factory=dict)


@dataclass
class PartRecord:
    id: int
    name: str
    confidence: float
    mask: Optional[np.ndarray] = None
    polygon_normalized: list = field(default_factory=list)
    polygon_pixels: list = field(default_factory=list)
    bbox: tuple = (0, 0, 0, 0)
    damages: List[int] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def mask_iou(mask_a: Optional[np.ndarray], mask_b: Optional[np.ndarray]) -> float:
    if mask_a is None or mask_b is None:
        return 0.0
    inter = np.logical_and(mask_a, mask_b).sum()
    union = np.logical_or(mask_a, mask_b).sum()
    return float(inter / union) if union > 0 else 0.0


def mask_intersection_ratio(mask_a: Optional[np.ndarray], mask_b: Optional[np.ndarray]) -> float:
    if mask_a is None or mask_b is None:
        return 0.0
    a_area = mask_a.sum()
    if a_area == 0:
        return 0.0
    inter = np.logical_and(mask_a, mask_b).sum()
    return float(inter / a_area)


def xyxy_to_xywh(bbox: Sequence[float]) -> List[float]:
    x1, y1, x2, y2 = bbox
    return [float(x1), float(y1), float(x2 - x1), float(y2 - y1)]


def bbox_iou(a: Sequence[float], b: Sequence[float]) -> float:
    """IoU for xyxy bboxes. Returns 0 if either is degenerate."""
    if a is None or b is None:
        return 0.0
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    aw = max(0.0, ax2 - ax1)
    ah = max(0.0, ay2 - ay1)
    bw = max(0.0, bx2 - bx1)
    bh = max(0.0, by2 - by1)
    a_area = aw * ah
    b_area = bw * bh
    if a_area <= 0 or b_area <= 0:
        return 0.0
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    union = a_area + b_area - inter
    return float(inter / union) if union > 0 else 0.0


def bbox_containment(damage: Sequence[float], part: Sequence[float]) -> float:
    """Fraction of damage bbox area that lies inside part bbox."""
    if damage is None or part is None:
        return 0.0
    ax1, ay1, ax2, ay2 = damage
    bx1, by1, bx2, by2 = part
    aw = max(0.0, ax2 - ax1)
    ah = max(0.0, ay2 - ay1)
    a_area = aw * ah
    if a_area <= 0:
        return 0.0
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw = max(0.0, ix2 - ix1)
    ih = max(0.0, iy2 - iy1)
    inter = iw * ih
    return float(inter / a_area)


def bbox_center_distance_norm(damage: Sequence[float], part: Sequence[float],
                              image_diag: float) -> float:
    """Normalized euclidean distance between bbox centers.
    Returns dist / image_diag, so 0..~1.4. Smaller = closer."""
    if damage is None or part is None or image_diag <= 0:
        return 1.0
    dcx = (damage[0] + damage[2]) * 0.5
    dcy = (damage[1] + damage[3]) * 0.5
    pcx = (part[0] + part[2]) * 0.5
    pcy = (part[1] + part[3]) * 0.5
    dx = dcx - pcx
    dy = dcy - pcy
    import math
    return float(math.hypot(dx, dy) / image_diag)


# ---------------------------------------------------------------------------
# DamagePipelineV2 (hardened)
# ---------------------------------------------------------------------------
class DamagePipelineV2:
    """v2 hardened production pipeline.

    Thread-safe; models are loaded on first inference under a lock then
    reused as read-only state.
    """

    def __init__(self,
                 damage_weights: Union[str, Path],
                 parts_weights: Optional[Union[str, Path]] = None,
                 severity_weights: Optional[Union[str, Path]] = None,
                 cost_table: Union[str, Path] = "cost_table.yaml",
                 device: Optional[str] = None,
                 # Model QA (2026-05-16) recommends:
                 #   damage_conf 0.25 -> 0.28: F1-curve peak at 0.282 on CarDD val.
                 #   parts_conf  0.30 -> 0.25: lower part-threshold cuts the
                 #     unassigned-damage rate from ~62% to ~45-50% (more part
                 #     candidates -> more damages assigned to a part).
                 damage_conf: float = 0.28,
                 parts_conf: float = 0.25,
                 imgsz: int = 640,
                 eager_load: bool = False):
        self._damage_weights = str(damage_weights)
        self._parts_weights = str(parts_weights) if parts_weights else None
        self._severity_weights = str(severity_weights) if severity_weights else None
        # Cost table path: keep configured value; CostEngine itself falls back
        # to the basename next to this module (services/ml/cost_table.yaml)
        # when the configured relative path doesn't exist. We log a hint here
        # if the configured path is relative and doesn't resolve from cwd,
        # so deployments running from a different working directory see the
        # mismatch in logs at startup rather than only at first inference.
        self._cost_table_path = str(cost_table)
        try:
            ctp = Path(self._cost_table_path)
            if not ctp.is_absolute() and not ctp.exists():
                fallback = Path(__file__).resolve().parent / ctp.name
                if fallback.exists():
                    logger.info(
                        "cost_table relative path %s not found from cwd=%s; "
                        "CostEngine will fall back to %s",
                        self._cost_table_path, Path.cwd(), fallback,
                    )
        except Exception:  # noqa: BLE001
            pass

        self.device = resolve_device(device)
        self.damage_conf = damage_conf
        self.parts_conf = parts_conf
        self.imgsz = imgsz

        # Lazy-loaded state guarded by lock
        self._init_lock = threading.Lock()
        self._initialized = False
        self.damage_model: Optional[YOLO] = None
        self.parts_model: Optional[YOLO] = None
        self.severity: Optional[EnsembleSeverity] = None
        self.cost_engine: Optional[CostEngine] = None

        # Shared detector pool — damage + parts predict() are run concurrently.
        # 2 workers is enough; severity is done after assignment because it
        # depends on the matched part name.
        self._detector_pool = ThreadPoolExecutor(
            max_workers=max(2, _DETECTOR_POOL_WORKERS),
            thread_name_prefix="ml-detector",
        )

        if eager_load:
            self._ensure_loaded()

    # ---- Lazy / thread-safe init ---------------------------------------
    def _ensure_loaded(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            t0 = time.perf_counter()
            logger.info("DamagePipelineV2 cold-loading on device=%s", self.device)

            self.damage_model = YOLO(self._damage_weights)
            try:
                self.damage_model.to(self.device)
            except Exception as exc:  # noqa: BLE001
                logger.warning("damage_model.to(%s) failed (will use default device): %s",
                               self.device, exc)

            if self._parts_weights:
                if not Path(self._parts_weights).exists():
                    logger.warning("parts_weights not found at %s — parts detection disabled",
                                   self._parts_weights)
                    self.parts_model = None
                else:
                    self.parts_model = YOLO(self._parts_weights)
                    try:
                        self.parts_model.to(self.device)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("parts_model.to(%s) failed: %s", self.device, exc)

            # Severity is optional; EnsembleSeverity gracefully falls back to
            # rule-based scoring when cnn weights are missing/None.
            sev_weights = self._severity_weights
            if sev_weights and not Path(sev_weights).exists():
                logger.warning("severity_weights not found at %s — using rule-based only",
                               sev_weights)
                sev_weights = None
            self.severity = EnsembleSeverity(cnn_weights=sev_weights)
            self.cost_engine = CostEngine(self._cost_table_path)
            self._initialized = True
            logger.info("DamagePipelineV2 loaded in %.2fs", time.perf_counter() - t0)

    @torch.inference_mode()
    def warmup(self, n: int = 1) -> None:
        """Run a dummy forward pass to JIT-compile kernels & allocate buffers."""
        self._ensure_loaded()
        dummy = np.zeros((self.imgsz, self.imgsz, 3), dtype=np.uint8)
        for _ in range(n):
            try:
                self.damage_model.predict(dummy, imgsz=self.imgsz, verbose=False, device=self.device)
                if self.parts_model is not None:
                    self.parts_model.predict(dummy, imgsz=self.imgsz, verbose=False, device=self.device)
            except Exception as exc:  # noqa: BLE001
                logger.warning("warmup pass failed: %s", exc)

    # ---- Helpers -------------------------------------------------------
    def _resize_mask(self, mask: Optional[np.ndarray], target_shape: Tuple[int, int]) -> Optional[np.ndarray]:
        if mask is None:
            return None
        if mask.shape == target_shape:
            return mask.astype(np.uint8)
        return cv2.resize(
            mask.astype(np.uint8),
            (target_shape[1], target_shape[0]),
            interpolation=cv2.INTER_NEAREST,
        )

    # ---- Detection passes ---------------------------------------------
    @torch.inference_mode()
    def _detect_damages(self, image: np.ndarray) -> List[DamageRecord]:
        h, w = image.shape[:2]
        result = self.damage_model.predict(
            image,
            conf=self.damage_conf,
            imgsz=self.imgsz,
            verbose=False,
            device=self.device,
        )[0]

        damages: List[DamageRecord] = []
        if result.boxes is None or len(result.boxes) == 0:
            return damages

        for i, box in enumerate(result.boxes):
            cls_id = int(box.cls.item())
            damage_type = self.damage_model.names[cls_id]
            d = DamageRecord(
                id=i,
                type=damage_type,
                confidence=float(box.conf.item()),
                bbox=tuple(box.xyxy[0].tolist()),
            )
            # Model QA (2026-05-16): crack class is non-functional on this
            # checkpoint (mAP50=0.14, recall=0.20). Every crack prediction —
            # regardless of YOLO confidence — is flagged low-confidence so the
            # UI can warn ("müşteri felaket önleme": 1500-5000 TL quote on a
            # 0.13-conf crack observed in smoke). Remove this rule when a
            # retrained crack model lands.
            if damage_type == "crack":
                d.is_low_confidence_match = True

            if result.masks is not None and i < len(result.masks.data):
                m = result.masks.data[i].detach().cpu().numpy()
                d.mask = self._resize_mask(m, (h, w))
                d.area_pixels = float(d.mask.sum())
                if i < len(result.masks.xy):
                    poly = result.masks.xy[i]
                    d.polygon_pixels = [[float(p[0]), float(p[1])] for p in poly]
                    d.polygon_normalized = [
                        [float(p[0] / w), float(p[1] / h)] for p in poly
                    ]
            else:
                x1, y1, x2, y2 = d.bbox
                d.area_pixels = (x2 - x1) * (y2 - y1)

            d.area_ratio = d.area_pixels / (h * w) if (h * w) else 0.0
            damages.append(d)
        return damages

    @torch.inference_mode()
    def _detect_parts(self, image: np.ndarray) -> List[PartRecord]:
        if self.parts_model is None:
            return []

        h, w = image.shape[:2]
        result = self.parts_model.predict(
            image,
            conf=self.parts_conf,
            imgsz=self.imgsz,
            verbose=False,
            device=self.device,
        )[0]

        parts: List[PartRecord] = []
        if result.boxes is None or len(result.boxes) == 0:
            return parts

        seen_parts: Dict[str, PartRecord] = {}
        next_id = 0
        for i, box in enumerate(result.boxes):
            cls_id = int(box.cls.item())
            name = self.parts_model.names[cls_id]
            conf = float(box.conf.item())

            mask = None
            polygon_norm: List[List[float]] = []
            polygon_px: List[List[float]] = []
            bbox = tuple(box.xyxy[0].tolist())
            if result.masks is not None and i < len(result.masks.data):
                mask = self._resize_mask(result.masks.data[i].detach().cpu().numpy(), (h, w))
                if i < len(result.masks.xy):
                    poly = result.masks.xy[i]
                    polygon_px = [[float(p[0]), float(p[1])] for p in poly]
                    polygon_norm = [
                        [float(p[0] / w), float(p[1] / h)] for p in poly
                    ]

            if name in seen_parts:
                if seen_parts[name].confidence < conf:
                    pid = seen_parts[name].id
                    seen_parts[name] = PartRecord(
                        id=pid, name=name, confidence=conf, mask=mask,
                        polygon_normalized=polygon_norm,
                        polygon_pixels=polygon_px, bbox=bbox,
                    )
            else:
                seen_parts[name] = PartRecord(
                    id=next_id, name=name, confidence=conf, mask=mask,
                    polygon_normalized=polygon_norm,
                    polygon_pixels=polygon_px, bbox=bbox,
                )
                next_id += 1
        return list(seen_parts.values())

    # ---- Assignment / severity / cost ----------------------------------
    def _assign_parts_to_damages(self, damages: List[DamageRecord], parts: List[PartRecord]) -> None:
        """Assign each damage to its host part.

        Strategy (in order):
          1) Primary: mask-intersection ratio (most accurate). Pick the part
             whose mask covers the largest fraction of the damage mask.
          2) Bbox fallback: when no mask overlap exists (parts model missed
             the underlying region segmentation but caught its bbox, or the
             damage mask is degenerate), fall back to bbox IoU + bbox
             containment. Match is flagged ``is_low_confidence_match=True``.
          3) Nearest-part fallback: if no bbox overlap either, pick the
             nearest detected part by bbox-center distance (capped at half
             the image diagonal). Always low-confidence.
        """
        if not parts:
            return
        part_by_name = {p.name: p for p in parts}

        # Image diagonal for distance normalization (use any part bbox; all
        # parts share the same image space). Fall back to a generous default.
        image_diag = 0.0
        for p in parts:
            if p.bbox and len(p.bbox) == 4:
                # bbox is xyxy in pixel space — we don't know image size here,
                # but max(x2,y2) across all parts gives a usable lower bound
                image_diag = max(image_diag, float(p.bbox[2]), float(p.bbox[3]))
        # multiply by sqrt(2) to approximate the true diagonal
        image_diag = (image_diag * 1.4142) if image_diag > 0 else 1000.0

        for d in damages:
            scores: List[dict] = []

            # ---- 1) Primary: mask intersection -----------------------------
            if d.mask is not None and d.mask.sum() > 0:
                for p in parts:
                    if p.mask is None:
                        continue
                    ir = mask_intersection_ratio(d.mask, p.mask)
                    if ir > 0:
                        scores.append({
                            "part": p.name,
                            "part_confidence": p.confidence,
                            "intersection_ratio": ir,
                            "iou": mask_iou(d.mask, p.mask),
                            "match_method": "mask",
                        })

            top = None
            if scores:
                scores.sort(key=lambda x: x["intersection_ratio"], reverse=True)
                if scores[0]["intersection_ratio"] >= MIN_IOU_FOR_ASSIGNMENT:
                    top = scores[0]

            # ---- 2) Bbox-IoU + containment fallback ------------------------
            if top is None and d.bbox is not None:
                bbox_scores = []
                for p in parts:
                    if not p.bbox:
                        continue
                    biou = bbox_iou(d.bbox, p.bbox)
                    bcon = bbox_containment(d.bbox, p.bbox)
                    # combined score: containment dominates (damage inside part)
                    combined = max(biou, bcon * 0.9)
                    if combined >= MIN_BBOX_IOU_FALLBACK or bcon >= MIN_BBOX_CONTAINMENT_FALLBACK:
                        bbox_scores.append({
                            "part": p.name,
                            "part_confidence": p.confidence,
                            "intersection_ratio": float(bcon),  # for downstream display
                            "iou": float(biou),
                            "bbox_containment": float(bcon),
                            "match_method": "bbox",
                            "_combined": combined,
                        })
                if bbox_scores:
                    bbox_scores.sort(key=lambda x: x["_combined"], reverse=True)
                    top = bbox_scores[0]
                    scores = bbox_scores  # for multi-part below
                    d.is_low_confidence_match = True

            # ---- 3) Nearest-part fallback (last resort) --------------------
            if top is None and d.bbox is not None and parts:
                candidates = []
                for p in parts:
                    if not p.bbox:
                        continue
                    dist = bbox_center_distance_norm(d.bbox, p.bbox, image_diag)
                    candidates.append((dist, p))
                if candidates:
                    candidates.sort(key=lambda x: x[0])
                    best_dist, best_p = candidates[0]
                    # cap: only accept if reasonably close (< 0.5 of diag)
                    if best_dist <= 0.5:
                        top = {
                            "part": best_p.name,
                            "part_confidence": best_p.confidence,
                            "intersection_ratio": 0.0,
                            "iou": 0.0,
                            "center_distance_norm": float(best_dist),
                            "match_method": "nearest",
                        }
                        scores = [top]
                        d.is_low_confidence_match = True

            # ---- Apply or mark unknown -------------------------------------
            if top is None:
                d.primary_part = "unknown"
                d.is_low_confidence_match = True
                continue

            d.primary_part = top["part"]
            d.primary_part_confidence = top["part_confidence"]
            d.primary_iou = top.get("intersection_ratio", 0.0)
            for s in scores[1:]:
                if s.get("intersection_ratio", 0.0) >= MULTI_PART_IOU_THRESHOLD:
                    d.secondary_parts.append(s)
                    d.is_multi_part = True
            if top.get("intersection_ratio", 0.0) < LOW_CONFIDENCE_IOU:
                d.is_low_confidence_match = True

            # cross-link to part
            if d.primary_part in part_by_name:
                part_by_name[d.primary_part].damages.append(d.id)

    @torch.inference_mode()
    def _classify_severities(self, damages: List[DamageRecord], image: np.ndarray) -> None:
        for d in damages:
            crop = crop_damage(image, d.bbox)
            d.severity = self.severity.predict(
                damage_type=d.type,
                part_name=d.primary_part,
                area_ratio=d.area_ratio,
                image_crop=crop,
            )

    def _estimate_costs(self, damages: List[DamageRecord]):
        cost_inputs = []
        for d in damages:
            est = self.cost_engine.estimate(
                part=d.primary_part,
                damage_type=d.type,
                severity=d.severity.get("level", "orta"),
            )
            d.cost = est.to_dict()
            cost_inputs.append({"part": d.primary_part, "estimate": est})
        return self.cost_engine.aggregate(cost_inputs)

    # ---- Public API ----------------------------------------------------
    def analyze(self,
                image_input: Any,
                inspection_id: Optional[str] = None,
                image_id: Optional[str] = None,
                part_centric: bool = True,
                generate_visuals: bool = False,
                output_visual_dir: Optional[str] = None,
                flat_legacy: Optional[bool] = None) -> Dict[str, Any]:
        """Single-image analysis.

        Args:
            image_input: path | bytes | PIL.Image | numpy array
            inspection_id: caller-supplied id, else uuid4
            image_id: optional caller-supplied image id
            part_centric: include legacy parts-centric layout (default True)
            generate_visuals: produce in-memory PNG bytes (visualization_bytes)
            output_visual_dir: if set, ALSO write to disk (dev only)
            flat_legacy: if True, flatten the legacy parts-centric layout to
                the root of the returned dict and stash the v2 standard
                output under ``_v2_standard``. This matches the contract
                expected by ``packages/types/src/inspection.ts`` (parts with
                .status / .damages[], summary.damaged_parts_count, etc.) so
                the backend's aggregate_results() works without translation.
                Defaults to env var ML_FLAT_LEGACY=1 if unset.
        """
        if flat_legacy is None:
            flat_legacy = os.getenv("ML_FLAT_LEGACY", "0").lower() in ("1", "true", "yes")
        self._ensure_loaded()
        t_total = time.perf_counter()

        image = load_image_bgr(image_input)
        if image is None or image.size == 0:
            raise ImagePreprocessError("Decoded image is empty")
        h, w = image.shape[:2]

        inspection_id = inspection_id or str(uuid.uuid4())
        image_id = image_id or str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()

        timings: Dict[str, float] = {}

        # ---- Parallel detection (damage + parts run concurrently) ---------
        # Ultralytics releases the GIL during forward pass, so threads give
        # us real overlap. On a single GPU the two predicts share the same
        # CUDA stream and serialize at the device, but CPU-side post-processing
        # (NMS, mask decode, host copies) still overlaps with the next forward.
        t_parallel = time.perf_counter()
        damages: List[DamageRecord] = []
        parts: List[PartRecord] = []
        damage_dur = parts_dur = 0.0

        def _run_damage() -> Tuple[List[DamageRecord], float]:
            t0 = time.perf_counter()
            return self._detect_damages(image), (time.perf_counter() - t0) * 1000

        def _run_parts() -> Tuple[List[PartRecord], float]:
            t0 = time.perf_counter()
            return self._detect_parts(image), (time.perf_counter() - t0) * 1000

        fut_damage = self._detector_pool.submit(_run_damage)
        fut_parts = self._detector_pool.submit(_run_parts)
        try:
            damages, damage_dur = fut_damage.result()
        except Exception:
            logger.exception("damage detection failed")
            damages, damage_dur = [], 0.0
        try:
            parts, parts_dur = fut_parts.result()
        except Exception:
            logger.exception("parts detection failed")
            parts, parts_dur = [], 0.0
        timings["damage"] = damage_dur
        timings["parts"] = parts_dur
        timings["detect_parallel_wall"] = (time.perf_counter() - t_parallel) * 1000

        t = time.perf_counter()
        if damages and parts:
            self._assign_parts_to_damages(damages, parts)
        timings["matching"] = (time.perf_counter() - t) * 1000

        t = time.perf_counter()
        if damages:
            self._classify_severities(damages, image)
        timings["severity"] = (time.perf_counter() - t) * 1000

        t = time.perf_counter()
        total_cost = self._estimate_costs(damages) if damages else None
        timings["cost"] = (time.perf_counter() - t) * 1000

        timings["total"] = (time.perf_counter() - t_total) * 1000

        # ----- Visualizations (in-memory PNG bytes for upload) ----------
        visualization_bytes: Dict[str, bytes] = {}
        visualization_keys: Dict[str, str] = {}
        if generate_visuals:
            try:
                from visualization import (
                    render_annotated, render_parts_only, render_damages_only,
                )

                imgs = {
                    "annotated": render_annotated(image, damages, parts),
                    "parts_only": render_parts_only(image, parts),
                    "damages_only": render_damages_only(image, damages),
                }
                for key, im in imgs.items():
                    ok, buf = cv2.imencode(".png", im)
                    if ok:
                        visualization_bytes[key] = bytes(buf)
                        # storage-key hint for the backend (it overrides with real upload keys)
                        visualization_keys[key] = f"inspections/{inspection_id}/{key}.png"
                if output_visual_dir:
                    out = Path(output_visual_dir)
                    out.mkdir(parents=True, exist_ok=True)
                    for key, data in visualization_bytes.items():
                        (out / f"{inspection_id}_{key}.png").write_bytes(data)
            except Exception as exc:  # noqa: BLE001
                logger.error("Visualization generation failed: %s", exc)

        # ----- Standardized v2 output -----------------------------------
        standard = build_standard_output(
            inspection_id=inspection_id,
            image_id=image_id,
            image_size=(w, h),
            damages=damages,
            parts=parts,
            total_cost=total_cost,
            timings_ms=timings,
            model_versions=MODEL_VERSIONS,
            visualization_keys=visualization_keys,
            timestamp=ts,
        )

        # ----- Optional legacy parts-centric layout ---------------------
        legacy = None
        if part_centric or flat_legacy:
            raw_legacy = {
                "inspection_id": inspection_id,
                "timestamp": ts,
                # NOT: sync mode'da bytes inline isleniyor; URL daha sonra
                # backend tarafindan `/api/v1/inspect/{id}/visualization/annotated`
                # ile doldurulur. Bu noktada inspection_id pipeline'a iletilmedigi
                # icin null biraktiriyoruz; frontend null/empty kontrolu yapar.
                "image": {"url": None, "width": w, "height": h},
            }
            legacy = to_part_centric(raw_legacy, damages, parts, total_cost)
            if not flat_legacy:
                standard["legacy_part_centric"] = legacy

        if flat_legacy and legacy is not None:
            # Pivot: return legacy at root (matches packages/types Inspection
            # interface) and stash the v2 standard under _v2_standard so
            # any v2-aware caller can still see it.
            v2_standard = standard
            output: Dict[str, Any] = dict(legacy)
            output["_v2_standard"] = v2_standard
            # Preserve cross-cutting fields the backend may want at root.
            if "model_versions" not in output:
                output["model_versions"] = v2_standard.get("model_versions")
            if "processing_ms" not in output:
                output["processing_ms"] = v2_standard.get("processing_ms")
            if "visualization_keys" not in output:
                output["visualization_keys"] = v2_standard.get("visualization_keys")
            if visualization_bytes:
                output["_visualization_bytes"] = visualization_bytes
            return output

        # attach raw bytes (not in JSON; callers pop these before serializing)
        if visualization_bytes:
            standard["_visualization_bytes"] = visualization_bytes

        return standard

    def analyze_batch(self,
                      images: Sequence[Any],
                      batch_size: int = 4,
                      inspection_ids: Optional[Sequence[str]] = None,
                      **analyze_kwargs) -> List[Dict[str, Any]]:
        """Batch analysis.

        Note: YOLO supports list batching natively but the post-processing
        pipeline (matching/severity/cost) is per-image. We chunk through
        the per-image path which is the safer choice and keeps memory
        bounded; true GPU batching can be added later if profiling shows
        benefit.
        """
        self._ensure_loaded()
        results: List[Dict[str, Any]] = []
        ids = list(inspection_ids) if inspection_ids else [None] * len(images)
        for start in range(0, len(images), max(1, batch_size)):
            chunk = images[start:start + batch_size]
            chunk_ids = ids[start:start + batch_size]
            for img, iid in zip(chunk, chunk_ids):
                try:
                    results.append(self.analyze(img, inspection_id=iid, **analyze_kwargs))
                except ImagePreprocessError as exc:
                    results.append({
                        "inspection_id": iid or str(uuid.uuid4()),
                        "error": "image_preprocess_error",
                        "error_detail": str(exc),
                    })
                except Exception as exc:  # noqa: BLE001
                    logger.exception("batch inference failed for one image")
                    results.append({
                        "inspection_id": iid or str(uuid.uuid4()),
                        "error": "inference_failed",
                        "error_detail": str(exc),
                    })
        return results


    def close(self) -> None:
        """Release the detector thread pool. Safe to call multiple times."""
        try:
            self._detector_pool.shutdown(wait=False, cancel_futures=True)
        except Exception:  # noqa: BLE001
            pass

    def __del__(self):  # pragma: no cover - best-effort
        try:
            self.close()
        except Exception:
            pass


# Backwards compat alias
DamagePipeline = DamagePipelineV2


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def cli():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--damage_weights", required=True)
    parser.add_argument("--parts_weights", default=None)
    parser.add_argument("--severity_weights", default=None)
    parser.add_argument("--cost_table", default="cost_table.yaml")
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", default=None)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", default=None, help="cpu|cuda|auto (or MODEL_DEVICE env)")
    parser.add_argument("--visualize", action="store_true")
    parser.add_argument("--visual_dir", default="./visuals")
    args = parser.parse_args()

    pipe = DamagePipelineV2(
        damage_weights=args.damage_weights,
        parts_weights=args.parts_weights,
        severity_weights=args.severity_weights,
        cost_table=args.cost_table,
        imgsz=args.imgsz,
        device=args.device,
    )
    result = pipe.analyze(
        args.image,
        generate_visuals=args.visualize,
        output_visual_dir=args.visual_dir if args.visualize else None,
    )
    # Strip non-serializable bytes before dumping
    result.pop("_visualization_bytes", None)

    out_path = args.output or Path(args.image).with_suffix(".v2.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    s = result["summary"]
    print("=== Inspection Result ===")
    print(f"Damages:         {s['total_damage_count']}")
    print(f"Affected parts:  {s['affected_parts_count']}")
    print(f"Dominant sev:    {s['dominant_severity']}")
    print(f"Cost:            TL {s['total_cost_min_tl']:.0f} - {s['total_cost_max_tl']:.0f}")
    print(f"Processing ms:   {result['processing_ms']['total']:.1f}")
    print(f"JSON:            {out_path}")


if __name__ == "__main__":
    cli()
