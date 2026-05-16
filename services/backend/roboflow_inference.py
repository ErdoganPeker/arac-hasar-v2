"""
roboflow_inference.py — Roboflow Hosted Inference API adapter

Roboflow Universe'te host edilen modelleri HTTP API uzerinden cagirir;
sonucu pipeline output formatina cevirir. Boylece pretrained Roboflow
modelleri image'a embed edilmeden, runtime'da network call ile kullanilir.

Kullanim:
    from roboflow_inference import run_roboflow_damage_inference
    damages = run_roboflow_damage_inference(
        image_bytes,
        workspace="carpro",
        project="car-scratch-and-dent",
        version=3,
        api_key=os.getenv("ROBOFLOW_API_KEY"),
    )

Free tier sinir: ~1000 inference/ay. Quota dolarsa API 429 doner ve
adapter graceful degrade yapar (bos liste).
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

ROBOFLOW_BASE = "https://detect.roboflow.com"
ROBOFLOW_TIMEOUT = 30  # saniye
DEFAULT_CONFIDENCE = 40  # %
DEFAULT_OVERLAP = 30  # %


def get_api_key() -> Optional[str]:
    return os.getenv("ROBOFLOW_API_KEY") or os.getenv("ROBOFLOW_KEY")


def is_roboflow_available() -> bool:
    """API key set mi? Set ise inference deneyebiliriz."""
    return bool(get_api_key())


def _call_roboflow(
    image_bytes: bytes,
    workspace: str,
    project: str,
    version: int,
    api_key: Optional[str] = None,
    confidence: int = DEFAULT_CONFIDENCE,
    overlap: int = DEFAULT_OVERLAP,
) -> Optional[Dict[str, Any]]:
    """Tek bir HTTP cagrisi yap. Hata durumunda None.

    Roboflow Detect API base64-encoded image bekliyor x-www-form-urlencoded
    body olarak (path: <project>/<version>).
    """
    key = api_key or get_api_key()
    if not key:
        logger.warning("ROBOFLOW_API_KEY yok; adapter atlandi")
        return None

    url = f"{ROBOFLOW_BASE}/{project}/{version}"
    b64 = base64.b64encode(image_bytes).decode("ascii")
    try:
        resp = requests.post(
            url,
            params={
                "api_key": key,
                "confidence": confidence,
                "overlap": overlap,
            },
            data=b64,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=ROBOFLOW_TIMEOUT,
        )
    except requests.RequestException as exc:
        logger.warning("Roboflow API HTTP exception: %s", exc)
        return None

    if resp.status_code == 429:
        logger.warning("Roboflow quota dolu (429); pilot ucretsiz tier limit")
        return None
    if resp.status_code >= 400:
        logger.warning(
            "Roboflow API %s: %s", resp.status_code, resp.text[:200]
        )
        return None

    try:
        return resp.json()
    except ValueError as exc:
        logger.warning("Roboflow JSON parse hata: %s", exc)
        return None


def _bbox_xywh_center_to_xyxy(p: Dict[str, Any]) -> List[float]:
    """Roboflow {x, y, width, height} center-format → [x1, y1, x2, y2]."""
    cx, cy, w, h = p["x"], p["y"], p["width"], p["height"]
    return [cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0]


def run_roboflow_damage_inference(
    image_bytes: bytes,
    workspace: str,
    project: str,
    version: int,
    api_key: Optional[str] = None,
    confidence: int = DEFAULT_CONFIDENCE,
) -> List[Dict[str, Any]]:
    """Roboflow detection modelini cagir, damage list dondur.

    Cikti formati pipeline'in `damages` listesi ile uyumlu:
    [
        {
            "id": 0,
            "class": "dent",
            "class_id": 0,
            "confidence": 0.76,
            "bbox": [x1, y1, x2, y2],
            "polygon": [],  # detection modelinde polygon yok
            "source": "roboflow",
        }, ...
    ]
    """
    data = _call_roboflow(
        image_bytes, workspace, project, version,
        api_key=api_key, confidence=confidence,
    )
    if not data:
        return []

    out: List[Dict[str, Any]] = []
    for idx, p in enumerate(data.get("predictions", [])):
        out.append({
            "id": idx,
            "class": p.get("class", "damage"),
            "class_id": int(p.get("class_id", 0)),
            "confidence": float(p.get("confidence", 0.0)),
            "bbox": _bbox_xywh_center_to_xyxy(p),
            "polygon": [],  # detection-only model
            "source": "roboflow",
            "is_low_confidence_match": False,
        })
    return out


__all__ = [
    "get_api_key",
    "is_roboflow_available",
    "run_roboflow_damage_inference",
]
