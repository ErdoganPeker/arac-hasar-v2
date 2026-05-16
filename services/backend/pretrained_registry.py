"""
pretrained_registry.py
======================

Registry of public, downloadable pre-trained models the user can select from
the frontend "Model: Pre-trained / Kendi Modellerim" toggle.

Design goals
------------
* Single source of truth for: id, display name, source URL, license, weight
  file location, class list, recommended use, mAP/accuracy hint.
* No model is loaded at import time. Registry entries describe how to load
  them; the actual loading is done by `model_manager.ModelManager` (lazy).
* Output schema MUST stay compatible with the custom pipeline (frontend
  contract). Pre-trained adapters bridge to the same v2 schema via
  `model_manager.PretrainedAdapter`.

Sources
-------
* Ultralytics official YOLO11-seg weights (COCO-80) — for "vehicle detected /
  not detected" baseline and instance segmentation of the car silhouette.
* Roboflow Universe public projects (CarDD-style damage/parts/severity)
  fetched via Roboflow API (requires ROBOFLOW_API_KEY in env).
* HuggingFace classifiers — currently optional, listed for completeness.

The registry is intentionally conservative (3-5 entries) so disk usage stays
under ~1.5 GB total.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ML_ROOT = Path(__file__).resolve().parent
# PRETRAINED_DIR is overridable via env (PRETRAINED_DIR) so production hosts
# with a read-only application dir can point it at writable scratch space
# (e.g. /tmp/pretrained on Render, /data on Fly.io).
PRETRAINED_DIR = Path(os.getenv("PRETRAINED_DIR", str(ML_ROOT / "pretrained")))
try:
    PRETRAINED_DIR.mkdir(parents=True, exist_ok=True)
except (PermissionError, OSError) as _e:
    import logging as _logging
    _logging.warning(
        "pretrained_registry: cannot create %s (%s). Set PRETRAINED_DIR env to "
        "a writable path or rebuild image with chown on this directory. "
        "Pretrained model downloads will fail until then.",
        PRETRAINED_DIR, _e,
    )


# ---------------------------------------------------------------------------
# Entry dataclass
# ---------------------------------------------------------------------------
@dataclass
class PretrainedEntry:
    """One downloadable pre-trained model.

    Attributes
    ----------
    id              Stable identifier used in API query (`?model=<id>`).
    name            Human-friendly display name (TR/EN mix ok).
    description     1-2 line description shown in the model picker.
    source          Provider: "ultralytics" | "roboflow" | "huggingface".
    source_url      Public link for citation in reports.
    license         SPDX-ish license name (AGPL-3.0, MIT, CC-BY-4.0, ...).
    role            Pipeline role: "damage" | "parts" | "severity" | "vehicle".
                    A model_source can mix several roles via `compose`.
    classes         List of class names exposed by the model.
    weights_path    Local weight file (resolved relative to PRETRAINED_DIR).
    download_url    Optional direct download URL (Ultralytics auto-fetches).
    roboflow        Optional {workspace, project, version} dict; the
                    downloader uses Roboflow SDK to fetch the YOLO export.
    hf_repo         Optional HuggingFace repo id.
    accuracy_hint   Free-text mAP/accuracy note for the report.
    size_mb         Approximate on-disk size after download.
    intended_use    Free-text policy / disclaimer for the report.
    """
    id: str
    name: str
    description: str
    source: str
    source_url: str
    license: str
    role: str
    classes: List[str] = field(default_factory=list)
    weights_path: Optional[str] = None
    download_url: Optional[str] = None
    roboflow: Optional[Dict[str, Any]] = None
    hf_repo: Optional[str] = None
    accuracy_hint: Optional[str] = None
    size_mb: float = 0.0
    intended_use: str = ""

    def resolved_path(self) -> Path:
        if self.weights_path is None:
            return PRETRAINED_DIR / f"{self.id}.pt"
        p = Path(self.weights_path)
        if not p.is_absolute():
            p = PRETRAINED_DIR / p
        return p

    def is_available(self) -> bool:
        # Roboflow Hosted API ile cagrilan modeller: weight dosyasi yok,
        # API key set ise kullanilabilir.
        if self.source == "roboflow" and self.roboflow:
            import os
            return bool(os.getenv("ROBOFLOW_API_KEY") or os.getenv("ROBOFLOW_KEY"))
        # Ultralytics: weight yoksa runtime'da CDN'den auto-download yapar.
        # Optimist davran — gercek fail inference'ta yakalanir, kullanici
        # 400 ile bilerek engellenmek yerine inference'i denesin.
        if self.source == "ultralytics":
            return True
        return self.resolved_path().exists()

    def to_public_dict(self) -> Dict[str, Any]:
        """JSON-safe dict for the GET /api/v1/models endpoint."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "source": self.source,
            "source_url": self.source_url,
            "license": self.license,
            "role": self.role,
            "classes": self.classes,
            "accuracy_hint": self.accuracy_hint,
            "size_mb": self.size_mb,
            "intended_use": self.intended_use,
            "available": self.is_available(),
        }


# ---------------------------------------------------------------------------
# Composite model sources exposed to the frontend.
# ---------------------------------------------------------------------------
@dataclass
class ModelSource:
    """A selectable option in the UI toggle.

    Either points at the "custom" snapshot pipeline (the 3 trained models)
    OR composes one or more PretrainedEntry objects into a pipeline.
    """
    id: str
    name: str
    description: str
    kind: str  # "custom" | "pretrained"
    entries: List[str] = field(default_factory=list)  # PretrainedEntry ids
    # If pretrained but missing some roles, we fall back to these custom roles
    fallback_to_custom: List[str] = field(default_factory=list)

    def to_public_dict(self, registry: "PretrainedRegistry") -> Dict[str, Any]:
        ents = [registry.get(eid) for eid in self.entries]
        ents = [e for e in ents if e is not None]
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "kind": self.kind,
            "entries": [e.to_public_dict() for e in ents],
            "fallback_to_custom": self.fallback_to_custom,
            "available": all(e.is_available() for e in ents) if ents else True,
        }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
_ENTRIES: List[PretrainedEntry] = [
    # ---- Ultralytics official YOLO11-seg (COCO-80) ----------------------
    PretrainedEntry(
        id="ultralytics_yolo11n_seg",
        name="Ultralytics YOLO11n-seg (COCO)",
        description=(
            "Resmi Ultralytics YOLO11 nano segmentation modeli. COCO-80 "
            "siniflari (car, truck, bus, motorcycle vb.) tespit eder. Hizli "
            "baseline; arac silueti + tipik sahne nesneleri."
        ),
        source="ultralytics",
        source_url="https://docs.ultralytics.com/models/yolo11/",
        license="AGPL-3.0",
        role="vehicle",
        classes=["car", "truck", "bus", "motorcycle", "bicycle", "person"],
        weights_path="yolo11n-seg.pt",
        accuracy_hint="COCO val mAP50-95 ~38.9 (seg ~32.0)",
        size_mb=5.9,
        intended_use=(
            "Genel araç tespiti / silueti icin baseline. Hasar tespiti "
            "yapmaz; sadece sahne validasyonu (gercekten bir araç var mı?)."
        ),
    ),
    PretrainedEntry(
        id="ultralytics_yolo11m_seg",
        name="Ultralytics YOLO11m-seg (COCO)",
        description=(
            "Orta boyut YOLO11 segmentation. Daha yuksek dogruluk, daha "
            "buyuk model. Aynı 80 COCO sınıfı."
        ),
        source="ultralytics",
        source_url="https://docs.ultralytics.com/models/yolo11/",
        license="AGPL-3.0",
        role="vehicle",
        classes=["car", "truck", "bus", "motorcycle", "bicycle", "person"],
        weights_path="yolo11m-seg.pt",
        accuracy_hint="COCO val mAP50-95 ~51.5 (seg ~43.0)",
        size_mb=43.7,
        intended_use=(
            "Daha dogru arac silueti / sahne validasyonu. Hasar tespiti "
            "yapmaz; pre-trained pipeline icinde 'vehicle' rolu icin tercih."
        ),
    ),
    # ---- Roboflow public car-damage projects ----------------------------
    # NOT: project/version slug'lari Roboflow Universe URL'sinden alindi.
    # Ozel API key olmasa da public projeler API ile cekilebilir; ancak
    # workspace_id + project + version triplet'i gereklidir.
    PretrainedEntry(
        id="roboflow_cardd_scratch_dent",
        name="Roboflow Car Scratch & Dent",
        description=(
            "Roboflow Universe public projesi (carpro/car-scratch-and-dent). "
            "Iki sinifli (scratch, dent) YOLOv8 modeli. Hızlı hasar "
            "ayırt etme baseline'i."
        ),
        source="roboflow",
        source_url="https://universe.roboflow.com/carpro/car-scratch-and-dent",
        license="CC-BY-4.0",
        role="damage",
        classes=["scratch", "dent"],
        weights_path="roboflow_cardd_scratch_dent/weights/best.pt",
        roboflow={
            "workspace": "carpro",
            "project": "car-scratch-and-dent",
            "version": 3,
            "format": "yolov8",
        },
        accuracy_hint="Roboflow rapor: mAP@50 ~0.78 (publisher metrigi)",
        size_mb=22.0,
        intended_use=(
            "Iki sinifli (scratch/dent) hasar detection. Ciddi cam/lamba "
            "kirilmasini tespit etmez; CarDD trainset'imizden dar kapsamli."
        ),
    ),
    # NOT (2026-05-16): roboflow_car_parts_seg ve roboflow_cardd_severity
    # registry'den kaldirildi. Sebep:
    #   - popular-benchmarks/car-parts-segmentation v2: dataset zip bozuk
    #     ("File is not a zip file"), hosted inference de basarisiz.
    #   - sreevishnu-damarla/car-damage-severity-mr5kk: workspace silinmis
    #     (404 GraphMethodException).
    # Yeniden kullanima alinabilmesi icin alternatif Roboflow Universe
    # projeleri arasini deniyoruz; bulunca tekrar eklenecek.
    # ---- HuggingFace classifier (opsiyonel) -----------------------------
    PretrainedEntry(
        id="hf_dima806_car_damage_cls",
        name="HuggingFace dima806/car_damage_image_detection",
        description=(
            "ViT tabanlı tek-tetiklikli sınıflandırıcı. Bir araç fotoğrafının "
            "hasarlı olup olmadığını ikili sınıflandırır."
        ),
        source="huggingface",
        source_url="https://huggingface.co/dima806/car_damage_image_detection",
        license="Apache-2.0",
        role="damage_classifier",
        classes=["damaged", "not_damaged"],
        weights_path="hf_dima806_car_damage_cls/pytorch_model.bin",
        hf_repo="dima806/car_damage_image_detection",
        accuracy_hint="HF rapor: val accuracy ~0.95 (publisher metrigi)",
        size_mb=346.0,
        intended_use=(
            "Triage on-filter: hasar yoksa pipeline'i komple atlatmak icin "
            "ucuz bir 'is damaged' kontrolü. Detection yapmaz."
        ),
    ),
]


_SOURCES: List[ModelSource] = [
    ModelSource(
        id="custom",
        name="Kendi Modellerim",
        description=(
            "Bu sistem icin CarDD uzerinde finetune edilmis 3 model: "
            "damage (YOLO11m-seg), parts (YOLO11s-seg), severity (YOLO11n-cls)."
        ),
        kind="custom",
        entries=[],
    ),
    ModelSource(
        id="pretrained_ultralytics_yolo11m",
        name="Pre-trained: Ultralytics YOLO11m-seg",
        description=(
            "Yalnızca araç silueti (COCO-80). Hasar tespiti yapmaz; "
            "baseline 'arac var mı?' kontrolu."
        ),
        kind="pretrained",
        entries=["ultralytics_yolo11m_seg"],
    ),
    ModelSource(
        id="pretrained_roboflow_cardd",
        name="Pre-trained: Roboflow Scratch & Dent",
        description=(
            "Roboflow Universe carpro/car-scratch-and-dent v3 modeli. "
            "İki sınıflı (scratch, dent) hızlı bbox tespiti. "
            "Hosted Inference API ile çağrılır — parça segmentasyonu "
            "ve şiddet sınıflandırması bu modelde yok."
        ),
        kind="pretrained",
        entries=["roboflow_cardd_scratch_dent"],
    ),
    # pretrained_hybrid kaldırıldı — Roboflow parts modeli erişilemez
    # olduğu için hibrit kombinasyon yapılamıyor.
]


class PretrainedRegistry:
    """Singleton-style accessor for entries and model sources."""

    def __init__(self,
                 entries: Optional[List[PretrainedEntry]] = None,
                 sources: Optional[List[ModelSource]] = None):
        self._entries: Dict[str, PretrainedEntry] = {
            e.id: e for e in (entries or _ENTRIES)
        }
        self._sources: Dict[str, ModelSource] = {
            s.id: s for s in (sources or _SOURCES)
        }

    # ---- Entry access ---------------------------------------------------
    def all_entries(self) -> List[PretrainedEntry]:
        return list(self._entries.values())

    def get(self, entry_id: str) -> Optional[PretrainedEntry]:
        return self._entries.get(entry_id)

    def entries_by_role(self, role: str) -> List[PretrainedEntry]:
        return [e for e in self._entries.values() if e.role == role]

    # ---- Source (UI option) access -------------------------------------
    def all_sources(self) -> List[ModelSource]:
        return list(self._sources.values())

    def get_source(self, source_id: str) -> Optional[ModelSource]:
        return self._sources.get(source_id)

    def public_sources(self) -> List[Dict[str, Any]]:
        return [s.to_public_dict(self) for s in self._sources.values()]

    # ---- Utilities ------------------------------------------------------
    def total_disk_mb(self, only_available: bool = False) -> float:
        total = 0.0
        for e in self._entries.values():
            if only_available and not e.is_available():
                continue
            total += float(e.size_mb or 0.0)
        return total


_REGISTRY: Optional[PretrainedRegistry] = None


def get_registry() -> PretrainedRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = PretrainedRegistry()
    return _REGISTRY


def has_roboflow_key() -> bool:
    return bool(os.getenv("ROBOFLOW_API_KEY"))
