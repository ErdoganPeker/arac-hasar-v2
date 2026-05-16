"""
backend/ml_service.py
ML pipeline singleton + async-safe inference giris noktasi.

Sundugu API:
  - ml_pipeline.warm_up()                         (startup'ta cagrilir)
  - ml_pipeline.is_loaded() -> bool
  - ml_pipeline.analyze(image_bgr_np) -> dict     (senkron, tek goruntu)
  - run_inspection(images: list[bytes], user_id) -> dict   (async, coklu goruntu)

Tasarim:
  - Modeller lazy-load + threadsafe (cogu HTTP request ayni instance'i kullanir).
  - YOLO weight'leri uretim snapshot'undan alinir:
      services/ml/runs/bundles/full_20260515_044630/_SNAPSHOT_FOR_BUILD/
        damage_best.pt, parts_best.pt, severity_best.pt
  - run_inspection(): bytes -> cv2 decode -> threadpool'da pipeline.analyze
    -> main.aggregate_results ile birlestir. GPU bound oldugu icin bir kerede
    1 inference, ama event-loop'u bloklamiyor.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

from config import settings


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# services/ml path bootstrap
# ---------------------------------------------------------------------------
# AI Engineer ajaninin model_manager.py + pretrained_registry.py modulleri
# services/ml/ altinda. Backend dev modunda services/backend/'den calistirilir;
# Docker image'inda CI step pipeline.py'yi backend'e kopyalar ama yeni
# model_manager dosyalari icin de yol gerekli. Idempotent:
_ML_DIR_CANDIDATES = [
    Path(__file__).resolve().parent.parent / "ml",  # services/backend/.. -> services/ml
    Path(__file__).resolve().parent / "ml",         # services/backend/ml (CI-baked)
]
for _candidate in _ML_DIR_CANDIDATES:
    if _candidate.is_dir() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))


class MLPipeline:
    """ModelManager sarmalar (custom + pretrained).

    Process icinde tek instance. `analyze(image, source=...)` ile cagrilir;
    source default "custom" — geriye uyumlu.
    """

    _instance: Optional["MLPipeline"] = None
    _ctor_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._ctor_lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._manager = None              # ModelManager instance
                    inst._pipeline = None             # geriye uyumluluk
                    inst._loaded = False
                    inst._infer_lock = threading.Lock()  # GPU paylasimi serialize
                    cls._instance = inst
        return cls._instance

    def is_loaded(self) -> bool:
        return bool(self._loaded)

    def list_sources(self) -> list[dict[str, Any]]:
        """Kullanilabilir model kaynaklarinin public listesi."""
        if self._manager is None:
            return []
        return self._manager.list_sources()

    def total_disk_mb(self, only_available: bool = True) -> float:
        if self._manager is None:
            return 0.0
        return self._manager.total_disk_mb(only_available=only_available)

    def warm_up(self) -> None:
        """Modelleri RAM/GPU'ya yukle. Idempotent."""
        if self._loaded:
            return

        # Lazy import — ModelManager torch/ultralytics import eder; sadece
        # gercekten ihtiyac duyuldugunda yukle (unit testler hizli kalsin).
        try:
            from model_manager import ModelManager  # type: ignore[import-not-found]
        except ImportError as e:
            logger.error(
                "ModelManager import edilemedi (%s). pipeline.py + "
                "model_manager.py + pretrained_registry.py backend image'a "
                "kopyalanmali ya da PYTHONPATH'e services/ml eklenmeli. "
                "ML warm-up atlandi; analyze() cagrildiginda hata firlatacak.", e,
            )
            return

        logger.info("ML ModelManager yukleniyor (custom + pretrained registry)...")
        logger.info("  damage_weights:   %s", settings.damage_weights)
        logger.info("  parts_weights:    %s", settings.parts_weights)
        logger.info("  severity_weights: %s", settings.severity_weights)
        logger.info("  device:           %s, imgsz=%d", settings.ml_device, settings.ml_imgsz)

        for name, path in [
            ("damage", settings.damage_weights),
            ("parts", settings.parts_weights),
            ("severity", settings.severity_weights),
        ]:
            if path and not Path(path).exists():
                logger.warning("[%s] agirlik dosyasi yok: %s — model atlanacak", name, path)

        t0 = time.perf_counter()
        self._manager = ModelManager(
            custom_kwargs=dict(
                damage_weights=settings.damage_weights,
                parts_weights=settings.parts_weights or None,
                severity_weights=settings.severity_weights or None,
                cost_table=settings.cost_table_path,
                device=settings.ml_device,
                imgsz=settings.ml_imgsz,
            ),
            device=settings.ml_device,
            imgsz=settings.ml_imgsz,
            cost_table=settings.cost_table_path,
        )

        # Custom modeli simdi eager yukle (baseline pipeline kullanima hazir).
        # Pre-trained kaynaklar ilk istek geldiginde lazy yuklenir.
        try:
            self._manager.warm_up(source="custom")
            # geri uyumluluk: eski callsite'lar self._pipeline'i bekliyor
            self._pipeline = self._manager._holders["custom"].pipeline  # noqa: SLF001
        except Exception as e:
            logger.warning("Custom pipeline warmup basarisiz: %s", e)

        # Warmup inference — GPU memory alokasyonunu ilk istek oncesi yap
        try:
            dummy = np.zeros((settings.ml_imgsz, settings.ml_imgsz, 3), dtype=np.uint8)
            self._manager.analyze(dummy, source="custom")
        except Exception as e:
            logger.warning("Warm-up inference basarisiz (yine de devam): %s", e)

        self._loaded = True
        logger.info("ML ModelManager hazir (%.2fs).", time.perf_counter() - t0)

    def analyze(self, image: np.ndarray, retries: int = 2,
                source: str = "custom") -> dict[str, Any]:
        """Tek bir goruntu analiz et (senkron, blocking). Retry destekli.

        Args:
            image: BGR numpy array.
            retries: hata halinde yeniden deneme sayisi.
            source: model kaynak id'si ("custom" default; pre-trained ornekleri
                pretrained_registry.py icinde tanimli — "pretrained_roboflow_cardd",
                "pretrained_ultralytics_yolo11m", "pretrained_hybrid").
        """
        if not self._loaded:
            # Lazy warm-up: HTTP startup'ta atlandiysa burada kurtar
            logger.warning("Pipeline yuklenmemis, lazy warm-up tetikleniyor")
            self.warm_up()
        if self._manager is None:
            raise RuntimeError(
                "ML ModelManager yuklenemedi (pipeline.py veya "
                "model_manager.py bulunamadi). Backend image'a "
                "services/ml/*.py dosyalarini ekleyin."
            )

        last_err: Optional[Exception] = None
        for attempt in range(retries + 1):
            try:
                # GPU paylasimi: ayni anda 1 inference (Celery worker concurrency
                # > 1 olabilir; bu lock kritik).
                with self._infer_lock:
                    return self._manager.analyze(image, source=source)
            except ValueError as e:
                # source id gecersiz -> retry yapma, hatayi yukari ver
                raise
            except Exception as e:  # noqa: BLE001 — yeniden raise
                last_err = e
                logger.warning("Analiz denemesi %d/%d hatali: %s", attempt + 1, retries + 1, e)
        assert last_err is not None
        raise last_err


# Singleton
ml_pipeline = MLPipeline()


# ---------------------------------------------------------------------------
# Public model-listing helpers (consumed by main.py /api/v1/models endpoint)
# ---------------------------------------------------------------------------

# Varsayilan model id — request'e param verilmezse / bos gelirse kullanilir.
# 'custom' = bu projeye finetune edilmis 3-modelli pipeline (damage+parts+severity).
DEFAULT_MODEL_ID = "custom"


def list_available_models() -> list[dict[str, Any]]:
    """GET /api/v1/models response payload'ini uret.

    Frontend dropdown sozlesmesi (her item):
        {
          "id":            str,        # query param degeri
          "name":          str,        # display label
          "description":   str,
          "source":        str,        # "custom" | "ultralytics" | "roboflow" | composite
          "classes_count": int,        # unique class sayisi (composite icin union)
          "license":       str,        # "proprietary" | "AGPL-3.0" | "MIT" | ...
          "is_custom":     bool,       # frontend "Kendi Modellerim" toggle icin
          "available":     bool,       # ag dosyalari diskte var mi
          "loaded":        bool,       # ModelManager bellege almis mi
          "kind":          str,        # "custom" | "pretrained"
          "entries":       [ {id, name, license, classes, source}, ... ],
        }

    ModelManager / pretrained_registry yuklenmemis ortamlarda (CI, minimal
    Docker image, eski deploy) yalniz "custom" doner — frontend bozulmasin.
    """
    # MLPipeline.list_sources() bos liste donerse warm_up et — listeleme
    # icin eager pipeline yuklemeye gerek yok ama registry lazy import edilmeli.
    sources: list[dict[str, Any]] = []
    try:
        sources = ml_pipeline.list_sources()
    except Exception as exc:  # noqa: BLE001
        logger.warning("ml_pipeline.list_sources hata: %s", exc)

    if not sources:
        # ModelManager henuz init edilmemis — registry'yi direkt deneyelim,
        # boylece warmup'tan once /api/v1/models hala dolu doner.
        try:
            from pretrained_registry import get_registry  # type: ignore[import-not-found]
            sources = get_registry().public_sources()
        except ImportError:
            logger.info(
                "pretrained_registry import edilemedi — sadece 'custom' modeli listelenir"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("pretrained_registry.public_sources hata: %s", exc)

    if not sources:
        return [{
            "id": "custom",
            "name": "Kendi Modellerim",
            "description": "Bu sistem icin CarDD uzerinde finetune edilmis pipeline (damage+parts+severity).",
            "source": "custom",
            "classes_count": 0,
            "license": "proprietary",
            "is_custom": True,
            "available": True,
            "loaded": ml_pipeline.is_loaded(),
            "kind": "custom",
            "entries": [],
        }]

    out: list[dict[str, Any]] = []
    for s in sources:
        entries = s.get("entries") or []
        unique_classes: set[str] = set()
        licenses: list[str] = []
        sources_set: set[str] = set()
        for e in entries:
            for c in (e.get("classes") or []):
                unique_classes.add(c)
            lic = e.get("license")
            if lic:
                licenses.append(lic)
            src = e.get("source")
            if src:
                sources_set.add(src)

        kind = s.get("kind", "custom")
        if kind == "custom":
            classes_count = 0
            license_str = "proprietary"
            source_label = "custom"
        else:
            classes_count = len(unique_classes)
            license_str = ", ".join(sorted(set(licenses))) or "unknown"
            source_label = ", ".join(sorted(sources_set)) or "pretrained"

        out.append({
            "id": s["id"],
            "name": s["name"],
            "description": s.get("description", ""),
            "source": source_label,
            "classes_count": classes_count,
            "license": license_str,
            "is_custom": kind == "custom",
            "available": bool(s.get("available", True)),
            "loaded": bool(s.get("loaded", False)),
            "kind": kind,
            "entries": [
                {
                    "id": e.get("id"),
                    "name": e.get("name"),
                    "license": e.get("license"),
                    "classes": e.get("classes") or [],
                    "source": e.get("source"),
                }
                for e in entries
            ],
        })
    return out


def is_known_model_id(model_id: Optional[str]) -> bool:
    """Verilen model_id valid bir kaynak mi?

    None / bos / "custom" her zaman valid. Diger id'ler registry'de aranir;
    registry yuklenememisse sadece "custom" kabul edilir (graceful degrade).
    """
    if not model_id or model_id == DEFAULT_MODEL_ID:
        return True
    try:
        return any(m["id"] == model_id for m in list_available_models())
    except Exception as exc:  # noqa: BLE001
        logger.warning("is_known_model_id check hata: %s", exc)
        return False


def resolve_model_id(model_id: Optional[str]) -> str:
    """None / bos -> DEFAULT_MODEL_ID; aksi durumda string'i geri ver."""
    if not model_id:
        return DEFAULT_MODEL_ID
    return model_id


# ============================ Async API ============================

async def _decode_bytes_to_bgr(content: bytes, index: int) -> np.ndarray:
    """Bytes -> numpy BGR. CPU bound ama hizli; threadpool sart degil."""
    nparr = np.frombuffer(content, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"Goruntu {index} decode edilemedi (corrupt/desteklenmeyen format)")
    return img


async def _analyze_one_async(image: np.ndarray, source: str = "custom") -> dict[str, Any]:
    """Senkron pipeline.analyze cagrisini threadpool'a tasi.

    asyncio.to_thread Python 3.9+; FastAPI route'lari event loop'unu bloke etmesin.
    """
    return await asyncio.to_thread(ml_pipeline.analyze, image, 2, source)


async def run_inspection(
    images: list[bytes],
    user_id: str,
    image_urls: Optional[list[str]] = None,
    source: str = "custom",
) -> dict[str, Any]:
    """Coklu goruntu icin async-safe inference giris noktasi.

    Args:
        images: ham bytes listesi (jpg/png/webp).
        user_id: cagrayi yapan kullanicinin id'si (audit/log icin).
        image_urls: opsiyonel — her bytes icin S3 URL'si. Per-image sonuca
            iliskilendirmek icin (frontend "12 foto = 12 result kart" beklentisi).

    Returns:
        main.aggregate_results sozlesmesine uyan birlesik sonuc dict'i.
        Ek olarak ``images: list[dict]`` alanini icerir — her giris goruntusu
        icin {index, url, status, parts, summary, ...} bireysel sonuc. Frontend
        bu listeyi tek tek kart olarak render edebilir; aggregate alanlar
        (parts/summary/unassigned_damages) tum gorseller uzerinden birlesik.
        Bos liste verilirse standart 'hasar_yok' iskeleti + bos images doner.
    """
    from main import aggregate_results  # circular import — yalniz cagri aninda

    image_urls = image_urls or []

    if not images:
        logger.info("run_inspection: bos image listesi (user=%s)", user_id)
        empty = aggregate_results([])
        empty["images"] = []
        return empty

    if not ml_pipeline.is_loaded():
        ml_pipeline.warm_up()

    results: list[dict[str, Any]] = []
    per_image: list[dict[str, Any]] = []
    t0 = time.perf_counter()

    for i, content in enumerate(images):
        url_i = image_urls[i] if i < len(image_urls) else None
        try:
            img = await _decode_bytes_to_bgr(content, i)
            r = await _analyze_one_async(img, source=source)
            if isinstance(r, dict):
                r.setdefault("image_index", i)
                # URL'i ham sonuc icine de yerlestir — aggregate'in image.url'i
                # legacy "<inline>" donduruyorsa override edelim.
                img_blk = r.get("image") if isinstance(r.get("image"), dict) else {}
                if (not img_blk.get("url")) or img_blk.get("url") == "<inline>":
                    img_blk["url"] = url_i
                    r["image"] = img_blk
            results.append(r)
            # Per-image ozet — frontend kart render'i icin
            per_image.append({
                "index": i,
                "url": url_i,
                "status": "completed",
                "image": (r.get("image") if isinstance(r, dict) else None) or {"url": url_i},
                "parts": (r.get("parts") if isinstance(r, dict) else []) or [],
                "summary": (r.get("summary") if isinstance(r, dict) else {}) or {},
                "unassigned_damages": (r.get("unassigned_damages") if isinstance(r, dict) else []) or [],
                "multi_part_damages": (r.get("multi_part_damages") if isinstance(r, dict) else []) or [],
            })
        except Exception as e:
            # Tek goruntu hatasi tum incelemeyi cokmesin
            logger.warning("[user=%s] Goruntu %d analiz hatasi: %s", user_id, i, e)
            per_image.append({
                "index": i,
                "url": url_i,
                "status": "failed",
                "error": str(e),
            })
            continue

    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "run_inspection tamamlandi: user=%s, %d/%d goruntu, %dms",
        user_id, len(results), len(images), elapsed_ms,
    )

    if not results:
        empty = aggregate_results([])
        empty["images"] = per_image
        return empty
    if len(results) == 1:
        out = dict(results[0])
        # tek goruntu de olsa frontend ayni sozlesmeyle calissin
        out["images"] = per_image
        return out
    aggregated = aggregate_results(results)
    aggregated["images"] = per_image
    return aggregated
