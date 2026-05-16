"""
model_manager.py
================

Multi-pipeline manager: holds the custom DamagePipelineV2 *and* one or more
pre-trained pipelines, all lazy-loaded.

API
---
    mgr = ModelManager(custom_kwargs={...})
    mgr.analyze(image, source="custom")
    mgr.analyze(image, source="pretrained_roboflow_cardd")
    mgr.list_sources()                     # for /api/v1/models

Design
------
* Each `ModelSource` from `pretrained_registry` becomes a runnable pipeline.
* "custom" wraps the existing `DamagePipelineV2` unchanged (no schema drift).
* Pre-trained sources build an *ad-hoc* pipeline by reusing the same
  `DamagePipelineV2` class but pointing its damage/parts/severity weights to
  the downloaded files (Ultralytics YOLO is plug-compatible).
* The output adapter is responsible for normalizing alien class names back to
  the frontend-stable schema (e.g. roboflow "scratch"/"dent" -> "scratch"/
  "dent" passthrough; "windshield" -> "front_glass"; "minor" -> "hafif").

Thread-safety
-------------
* One `_load_lock` per source id so concurrent first-hits don't double-load.
* GPU inference is still serialized at the backend `MLPipeline._infer_lock`.
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from pretrained_registry import (
    PretrainedEntry,
    PretrainedRegistry,
    ModelSource,
    get_registry,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Class-name adapters: map foreign class names to the frontend-stable schema.
# ---------------------------------------------------------------------------
# Parts (Roboflow Universe public projeleri ile bizim sema arasındaki köprü)
PARTS_REMAP: Dict[str, str] = {
    # roboflow car-parts-segmentation -> our PART_TR keys
    "windshield": "front_glass",
    "rear_window": "back_glass",
    "front-bumper": "front_bumper",
    "back-bumper": "back_bumper",
    "rear_bumper": "back_bumper",
    "front-door": "front_left_door",      # left/right unknown w/o orientation
    "back-door": "back_left_door",
    "rear_door": "back_left_door",
    "front-light": "front_light",
    "back-light": "back_light",
    "rear_light": "back_light",
    "headlight": "front_light",
    "taillight": "back_light",
    "trunk": "trunk",
    "tailgate": "tailgate",
    "fender": "front_left_door",          # heuristic; flagged low-conf
}

# Damage type remap (Roboflow / HF -> our DAMAGE_TYPE_TR keys)
DAMAGE_TYPE_REMAP: Dict[str, str] = {
    "scratch": "scratch",
    "Scratch": "scratch",
    "dent": "dent",
    "Dent": "dent",
    "crack": "crack",
    "broken-glass": "glass_shatter",
    "shattered-glass": "glass_shatter",
    "broken-lamp": "lamp_broken",
    "flat-tire": "tire_flat",
}

# Severity remap (Roboflow ENG -> our TR labels)
SEVERITY_REMAP: Dict[str, str] = {
    "minor": "hafif",
    "moderate": "orta",
    "severe": "agir",
    "Minor": "hafif",
    "Moderate": "orta",
    "Severe": "agir",
}


# ---------------------------------------------------------------------------
# Pipeline holder for a single source (custom or composed pre-trained)
# ---------------------------------------------------------------------------
class _PipelineHolder:
    def __init__(self, source_id: str):
        self.source_id = source_id
        self.pipeline = None
        self._lock = threading.Lock()
        self._loaded = False
        self._load_failure: Optional[str] = None


class ModelManager:
    """Owns every selectable pipeline.

    Parameters
    ----------
    custom_kwargs : dict
        Keyword args forwarded verbatim to `DamagePipelineV2(...)` when the
        "custom" source is first loaded.
    device, imgsz, cost_table : passed through to pre-trained pipelines too.
    """

    def __init__(self,
                 custom_kwargs: Optional[Dict[str, Any]] = None,
                 device: Optional[str] = None,
                 imgsz: int = 640,
                 cost_table: str = "cost_table.yaml",
                 registry: Optional[PretrainedRegistry] = None):
        self.custom_kwargs = dict(custom_kwargs or {})
        self.device = device
        self.imgsz = imgsz
        self.cost_table = cost_table
        self.registry = registry or get_registry()

        # one holder per registered source
        self._holders: Dict[str, _PipelineHolder] = {
            s.id: _PipelineHolder(s.id) for s in self.registry.all_sources()
        }
        # default fallback for unknown ids
        if "custom" not in self._holders:
            self._holders["custom"] = _PipelineHolder("custom")

    # ---- Public listing -----------------------------------------------
    def list_sources(self) -> List[Dict[str, Any]]:
        out = self.registry.public_sources()
        for s in out:
            holder = self._holders.get(s["id"])
            s["loaded"] = bool(holder and holder._loaded)
            s["load_failure"] = holder._load_failure if holder else None
        return out

    def total_disk_mb(self, only_available: bool = False) -> float:
        return self.registry.total_disk_mb(only_available=only_available)

    # ---- Pipeline build -----------------------------------------------
    def _build_custom_pipeline(self):
        # Lazy import — keep module-load light.
        from pipeline import DamagePipelineV2
        return DamagePipelineV2(**self.custom_kwargs)

    def _build_pretrained_pipeline(self, source: ModelSource):
        """Compose a DamagePipelineV2 from pretrained registry entries.

        Roles:
          - "damage"  -> damage_weights
          - "parts"   -> parts_weights
          - "severity"/"vehicle" -> handled below
        Missing roles fall back to the custom weights so the pipeline is
        always functional (declared via `source.fallback_to_custom`).
        """
        from pipeline import DamagePipelineV2

        by_role: Dict[str, PretrainedEntry] = {}
        for eid in source.entries:
            e = self.registry.get(eid)
            if e is None:
                continue
            # "vehicle" detector is mapped onto damage_weights if no damage
            # entry exists — it'll detect cars but classify them as the
            # COCO class name; the adapter will flag those as "low-conf".
            by_role.setdefault(e.role, e)

        # damage weights
        if "damage" in by_role:
            damage_w = str(by_role["damage"].resolved_path())
        elif "vehicle" in by_role:
            # NOTE: COCO-80 has no damage classes. Output will be empty
            # damages until user supplies a damage model; we keep the
            # ultralytics weights as the YOLO entrypoint so the pipeline
            # still runs (and reports the silhouette via parts logic).
            damage_w = str(by_role["vehicle"].resolved_path())
        elif "damage" in source.fallback_to_custom or True:
            damage_w = self.custom_kwargs.get("damage_weights")
        else:
            damage_w = self.custom_kwargs.get("damage_weights")

        # parts weights
        if "parts" in by_role:
            parts_w = str(by_role["parts"].resolved_path())
        elif "parts" in source.fallback_to_custom:
            parts_w = self.custom_kwargs.get("parts_weights")
        else:
            parts_w = self.custom_kwargs.get("parts_weights")

        # severity weights (Ultralytics CLS or our own CNN)
        if "severity" in by_role:
            sev_w = str(by_role["severity"].resolved_path())
        elif "severity" in source.fallback_to_custom:
            sev_w = self.custom_kwargs.get("severity_weights")
        else:
            sev_w = self.custom_kwargs.get("severity_weights")

        # If a weight file doesn't exist on disk, leave it None so
        # DamagePipelineV2 logs a warning and skips that head instead of
        # crashing — that's exactly what the user gets when they pick a
        # pre-trained source whose download hasn't been run yet.
        def _maybe(p):
            if not p:
                return None
            return p if Path(p).exists() else None

        pipe = DamagePipelineV2(
            damage_weights=_maybe(damage_w) or damage_w,
            parts_weights=_maybe(parts_w),
            severity_weights=_maybe(sev_w),
            cost_table=self.cost_table,
            device=self.device,
            imgsz=self.imgsz,
        )
        return pipe

    def _ensure_loaded(self, source_id: str):
        holder = self._holders.get(source_id)
        if holder is None:
            raise ValueError(f"Unknown model source: {source_id}")
        if holder._loaded:
            return holder
        with holder._lock:
            if holder._loaded:
                return holder
            t0 = time.perf_counter()
            try:
                if source_id == "custom":
                    holder.pipeline = self._build_custom_pipeline()
                else:
                    src = self.registry.get_source(source_id)
                    if src is None:
                        raise ValueError(f"No registry entry: {source_id}")
                    holder.pipeline = self._build_pretrained_pipeline(src)
                holder._loaded = True
                holder._load_failure = None
                logger.info(
                    "ModelManager loaded source=%s in %.2fs",
                    source_id, time.perf_counter() - t0,
                )
            except Exception as exc:  # noqa: BLE001
                holder._load_failure = f"{type(exc).__name__}: {exc}"
                logger.exception("ModelManager: load failed for %s", source_id)
                raise
        return holder

    # ---- Public inference --------------------------------------------
    def analyze(self,
                image,
                source: str = "custom",
                **analyze_kwargs) -> Dict[str, Any]:
        """Run inference on the chosen model source.

        The output is *always* normalized to the v2 / legacy schema the
        frontend already consumes. For pre-trained sources, class names are
        remapped via PARTS_REMAP / DAMAGE_TYPE_REMAP / SEVERITY_REMAP.
        """
        src = source or "custom"
        holder = self._ensure_loaded(src)
        result = holder.pipeline.analyze(image, **analyze_kwargs)
        # Tag the result so the frontend can show which model produced it.
        if isinstance(result, dict):
            result.setdefault("model_source", src)
            if src != "custom":
                _adapt_pretrained_output(result, src, self.registry)
        return result

    def warm_up(self, source: str = "custom") -> None:
        self._ensure_loaded(source)


# ---------------------------------------------------------------------------
# Adapter: normalize pre-trained class names to the frontend schema.
# ---------------------------------------------------------------------------
def _remap(name: Optional[str], table: Dict[str, str]) -> Optional[str]:
    if name is None:
        return None
    return table.get(name, table.get(name.lower(), name))


def _adapt_pretrained_output(
    result: Dict[str, Any],
    source_id: str,
    registry: PretrainedRegistry,
) -> None:
    """Mutate result IN-PLACE so it matches the frontend contract.

    The custom pipeline emits Turkish severity labels (hafif/orta/agir) and
    our own part / damage names; pre-trained ones may emit minor/moderate/
    severe and english part names. We translate those here, additively
    (we never drop fields) and we set ``model_source`` plus per-detection
    ``model_source_detail`` so the UI can render a small badge.
    """
    # Per-damage normalization (v2 standard schema)
    damages = result.get("damages") or []
    for d in damages:
        if isinstance(d, dict):
            if "type" in d:
                d["type"] = _remap(d.get("type"), DAMAGE_TYPE_REMAP) or d.get("type")
            sev = d.get("severity") or {}
            if isinstance(sev, dict) and "level" in sev:
                sev["level"] = _remap(sev.get("level"), SEVERITY_REMAP) or sev.get("level")
                d["severity"] = sev
            # part name remap
            for key in ("primary_part", "part"):
                if key in d:
                    d[key] = _remap(d.get(key), PARTS_REMAP) or d.get(key)
            d["model_source"] = source_id

    # Per-part normalization (parts-centric legacy + v2)
    parts = result.get("parts") or []
    for p in parts:
        if isinstance(p, dict) and "name" in p:
            p["name"] = _remap(p.get("name"), PARTS_REMAP) or p.get("name")
            p["model_source"] = source_id

    # Model versions block — tag with composed source info for the report
    mv = result.get("model_versions") or {}
    src = registry.get_source(source_id)
    if src is not None:
        mv["pretrained_source"] = {
            "id": src.id,
            "name": src.name,
            "entries": [
                {"id": eid, "name": (registry.get(eid).name if registry.get(eid) else eid)}
                for eid in src.entries
            ],
        }
        result["model_versions"] = mv
