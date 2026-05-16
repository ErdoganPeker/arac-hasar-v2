"""
inference_server.py - Lightweight, thread-safe wrapper around DamagePipelineV2.

This is the production entry point that FastAPI imports. It guarantees:
  - Single pipeline instance (process-wide singleton) protected by a lock
  - Lazy load with explicit warmup() support
  - Thread-safe concurrent inference (Ultralytics releases the GIL during
    the forward pass; predict() is reentrant, but model construction must
    happen exactly once)
  - Batch helper that maps to pipeline.analyze_batch
  - Friendly error envelope for the API layer

Typical usage in FastAPI startup:

    from services.ml.inference_server import InferenceServer

    server = InferenceServer.from_env()

    @app.on_event("startup")
    async def warmup():
        server.warmup()

    @app.post("/analyze")
    def analyze(file: UploadFile):
        return server.analyze(file.file.read(), inspection_id=...)
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from pipeline import (
    DamagePipelineV2, ImagePreprocessError, MODEL_VERSIONS, resolve_device,
)


logger = logging.getLogger(__name__)


_ML_DIR = Path(__file__).resolve().parent
_BUNDLES_DIR = _ML_DIR / "runs" / "bundles"


def _autodiscover_snapshot() -> Path:
    """Return the most recent full_* snapshot bundle, or a sentinel path.

    Order:
      1. Newest `full_*` bundle by mtime (production training output)
      2. Newest `quick_*` bundle (smoke training)
      3. Last-known hard default (kept for back-compat; may not exist on
         fresh checkouts and will be reported by warm_up logs)
    """
    if _BUNDLES_DIR.exists():
        candidates = sorted(
            (p for p in _BUNDLES_DIR.iterdir()
             if p.is_dir() and (p / "_SNAPSHOT_FOR_BUILD").is_dir()
             and p.name.startswith("full_")),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            candidates = sorted(
                (p for p in _BUNDLES_DIR.iterdir()
                 if p.is_dir() and (p / "_SNAPSHOT_FOR_BUILD").is_dir()),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        if candidates:
            return candidates[0] / "_SNAPSHOT_FOR_BUILD"
    # Last-known production snapshot path (may not exist; warm_up will log)
    return _BUNDLES_DIR / "full_20260515_044630" / "_SNAPSHOT_FOR_BUILD"


DEFAULT_SNAPSHOT = _autodiscover_snapshot()


class InferenceServer:
    """Thread-safe singleton wrapper around DamagePipelineV2."""

    _instance: Optional["InferenceServer"] = None
    _instance_lock = threading.Lock()

    # ----- Construction ------------------------------------------------
    def __init__(self,
                 damage_weights: Union[str, Path],
                 parts_weights: Optional[Union[str, Path]] = None,
                 severity_weights: Optional[Union[str, Path]] = None,
                 cost_table: Union[str, Path] = "cost_table.yaml",
                 device: Optional[str] = None,
                 imgsz: int = 640,
                 damage_conf: float = 0.25,
                 parts_conf: float = 0.30,
                 max_concurrent: Optional[int] = None):
        self._pipeline = DamagePipelineV2(
            damage_weights=damage_weights,
            parts_weights=parts_weights,
            severity_weights=severity_weights,
            cost_table=cost_table,
            device=device,
            imgsz=imgsz,
            damage_conf=damage_conf,
            parts_conf=parts_conf,
            eager_load=False,
        )
        self.device = self._pipeline.device
        self._semaphore: Optional[threading.BoundedSemaphore] = (
            threading.BoundedSemaphore(max_concurrent) if max_concurrent else None
        )
        self._inflight = 0
        self._inflight_lock = threading.Lock()
        self._warmed_up = False
        self._warmup_lock = threading.Lock()

    # ----- Factories ---------------------------------------------------
    @classmethod
    def from_env(cls) -> "InferenceServer":
        """Build a server from env vars / default snapshot path.

        An empty string for any weights env var disables that model (falls
        through to rule-based / detector-only paths).

        Pre-trained fallback: if a configured weights path doesn't exist on
        disk we fall back to the bundled Ultralytics pre-trained .pt files
        sitting next to this module (yolo11m-seg.pt etc.). This keeps the
        server runnable end-to-end on a fresh checkout that hasn't trained
        yet — accuracy will be poor (COCO classes), but the pipeline wiring,
        API, and visualizations all work.
        """
        snap = Path(os.getenv("ML_SNAPSHOT_DIR", str(DEFAULT_SNAPSHOT)))

        def _opt(name: str, default: str) -> Optional[str]:
            v = os.getenv(name, default)
            return v if v else None

        def _resolve(env_name: str, snap_path: Path, pretrained_name: Optional[str]) -> Optional[str]:
            raw = os.getenv(env_name)
            if raw is not None and raw == "":
                # Caller explicitly disabled this model
                return None
            candidate = Path(raw) if raw else snap_path
            if candidate.exists():
                return str(candidate)
            if pretrained_name:
                fallback = _ML_DIR / pretrained_name
                if fallback.exists():
                    logger.warning(
                        "%s missing at %s — falling back to pre-trained %s (DEV ONLY, accuracy will be poor)",
                        env_name, candidate, fallback.name,
                    )
                    return str(fallback)
            # Returning the original path lets YOLO() raise a clear error.
            return str(candidate)

        damage_w = _resolve("ML_DAMAGE_WEIGHTS", snap / "damage_best.pt", "yolo11m-seg.pt")
        parts_w = _resolve("ML_PARTS_WEIGHTS", snap / "parts_best.pt", "yolo11s-seg.pt")
        # Severity uses a custom torchvision checkpoint; no Ultralytics
        # pre-trained equivalent. If missing -> rule-based scoring kicks in.
        sev_default = _opt("ML_SEVERITY_WEIGHTS", str(snap / "severity_best.pt"))
        severity_w = sev_default if (sev_default and Path(sev_default).exists()) else None

        return cls(
            damage_weights=damage_w,
            parts_weights=parts_w,
            severity_weights=severity_w,
            cost_table=os.getenv("ML_COST_TABLE",
                                  str(_ML_DIR / "cost_table.yaml")),
            # Honor either MODEL_DEVICE or ML_DEVICE; resolve_device handles both.
            device=os.getenv("MODEL_DEVICE") or os.getenv("ML_DEVICE") or "auto",
            imgsz=int(os.getenv("ML_IMGSZ", "640")),
            damage_conf=float(os.getenv("ML_DAMAGE_CONF", "0.25")),
            parts_conf=float(os.getenv("ML_PARTS_CONF", "0.30")),
            max_concurrent=int(os.getenv("ML_MAX_CONCURRENT", "0")) or None,
        )

    @classmethod
    def get(cls) -> "InferenceServer":
        """Process-wide singleton (created from env on first call)."""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls.from_env()
        return cls._instance

    # ----- Lifecycle ---------------------------------------------------
    def warmup(self, n: int = 2) -> Dict[str, Any]:
        """Idempotent warmup. Pre-loads weights and runs n dummy passes."""
        if self._warmed_up:
            return {"status": "already_warm", "device": self.device}
        with self._warmup_lock:
            if self._warmed_up:
                return {"status": "already_warm", "device": self.device}
            t0 = time.perf_counter()
            self._pipeline.warmup(n=n)
            self._warmed_up = True
            elapsed = (time.perf_counter() - t0) * 1000
            logger.info("InferenceServer warmup completed in %.1fms", elapsed)
            return {
                "status": "warmed",
                "device": self.device,
                "warmup_ms": round(elapsed, 1),
                "model_versions": dict(MODEL_VERSIONS),
            }

    def health(self) -> Dict[str, Any]:
        return {
            "ready": self._pipeline._initialized,  # noqa: SLF001
            "warmed_up": self._warmed_up,
            "device": self.device,
            "inflight": self._inflight,
            "model_versions": dict(MODEL_VERSIONS),
        }

    # ----- Inference ---------------------------------------------------
    def analyze(self,
                image_input: Any,
                inspection_id: Optional[str] = None,
                image_id: Optional[str] = None,
                generate_visuals: bool = True,
                part_centric: bool = False) -> Dict[str, Any]:
        """Single-image analysis with concurrency guard and error envelope."""
        if self._semaphore is not None and not self._semaphore.acquire(blocking=True, timeout=30):
            return {
                "error": "server_busy",
                "error_detail": "Max concurrent inferences reached. Retry shortly.",
                "inspection_id": inspection_id,
            }
        try:
            with self._inflight_lock:
                self._inflight += 1
            try:
                return self._pipeline.analyze(
                    image_input,
                    inspection_id=inspection_id,
                    image_id=image_id,
                    generate_visuals=generate_visuals,
                    part_centric=part_centric,
                )
            except ImagePreprocessError as exc:
                return {
                    "error": "image_preprocess_error",
                    "error_detail": str(exc),
                    "inspection_id": inspection_id,
                }
            except Exception as exc:  # noqa: BLE001
                logger.exception("inference failure")
                return {
                    "error": "inference_failed",
                    "error_detail": str(exc),
                    "inspection_id": inspection_id,
                }
            finally:
                with self._inflight_lock:
                    self._inflight -= 1
        finally:
            if self._semaphore is not None:
                self._semaphore.release()

    def analyze_batch(self,
                      images: Sequence[Any],
                      batch_size: int = 4,
                      inspection_ids: Optional[Sequence[str]] = None,
                      generate_visuals: bool = False,
                      part_centric: bool = False) -> List[Dict[str, Any]]:
        return self._pipeline.analyze_batch(
            images,
            batch_size=batch_size,
            inspection_ids=inspection_ids,
            generate_visuals=generate_visuals,
            part_centric=part_centric,
        )


__all__ = ["InferenceServer", "MODEL_VERSIONS", "resolve_device"]
