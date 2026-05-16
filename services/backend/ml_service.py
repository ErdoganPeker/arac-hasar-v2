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
import gc
import logging
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

from config import settings


logger = logging.getLogger(__name__)


def _force_gc(reason: str = "") -> None:
    """Aggresif gc + (varsa) torch CUDA cache temizleme.

    Render free 512MB icin kritik: Python obje grafindaki refcount=0 buyuk
    np.ndarray / torch.Tensor parcalarinin OS'a iade edilmesi icin tek bir
    gc.collect() pasi yetmez (generational GC). 2 pas + malloc_trim taklidi.
    """
    gc.collect()
    gc.collect()
    try:
        import torch  # type: ignore[import-not-found]
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        pass
    # Linux glibc'in arena'larini OS'a geri ver (Render container Linux).
    # ctypes ile libc.malloc_trim(0) — Windows/Mac'te sessizce no-op.
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
    except Exception:
        pass
    if reason:
        logger.debug("forced gc (%s)", reason)


def _rss_mb() -> Optional[float]:
    """Process RSS (MB). psutil yoksa /proc/self/status fallback. Hata -> None."""
    try:
        import psutil  # type: ignore[import-not-found]
        return round(psutil.Process().memory_info().rss / (1024 * 1024), 1)
    except Exception:
        pass
    try:
        with open("/proc/self/status", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    kb = int(line.split()[1])
                    return round(kb / 1024, 1)
    except Exception:
        return None
    return None


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

    def warm_up(self, run_dummy_inference: bool = False) -> None:
        """Modelleri RAM/GPU'ya yukle. Idempotent.

        Args:
            run_dummy_inference: True ise zeros-image uzerinde sicak prova
                yapilir (GPU memory alokasyonu prewarm). Default False —
                512MB Render free'de bu prova ~150MB ek RAM pinler ve ilk
                gercek istek zaten warmup yapacak.
        """
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

        # Warmup inference opsiyonel — default off. Render free 512MB'de
        # bu prova memory peak'i +150MB ediyor; ilk gercek istek zaten
        # tum dolapi sicaklastiriyor.
        if run_dummy_inference:
            try:
                dummy = np.zeros((settings.ml_imgsz, settings.ml_imgsz, 3), dtype=np.uint8)
                self._manager.analyze(dummy, source="custom")
            except Exception as e:
                logger.warning("Warm-up inference basarisiz (yine de devam): %s", e)

        self._loaded = True
        logger.info("ML ModelManager hazir (%.2fs).", time.perf_counter() - t0)

    def unload(self) -> dict[str, Any]:
        """Modelleri bellekten dusur; refcount 0'a indi -> gc + malloc_trim.

        AI Engineer ajan pipeline.py icine per-stage unload eklediyse
        ModelManager / Pipeline tarafinda close()/unload() metodu cikar —
        varsa once onu cagir, sonra Python tarafinda referansi birak.

        Returns:
            {"unloaded": bool, "before_rss_mb": float|None,
             "after_rss_mb": float|None, "freed_mb": float|None}
        """
        before = _rss_mb()
        unloaded = False
        with self._infer_lock:
            mgr = self._manager
            if mgr is not None:
                # Pipeline.py'da unload/close hook varsa cagir (defansif).
                for hook_name in ("unload", "close", "release", "cleanup"):
                    hook = getattr(mgr, hook_name, None)
                    if callable(hook):
                        try:
                            hook()
                            logger.info("ModelManager.%s() cagrildi", hook_name)
                            break
                        except Exception as e:  # noqa: BLE001
                            logger.warning("ModelManager.%s hata: %s", hook_name, e)
                # Pipeline holders tarafinda da hook olabilir
                holders = getattr(mgr, "_holders", None) or {}
                for src_id, holder in list(holders.items()):
                    pipe = getattr(holder, "pipeline", None)
                    for hook_name in ("unload", "close", "release", "cleanup"):
                        hook = getattr(pipe, hook_name, None)
                        if callable(hook):
                            try:
                                hook()
                                logger.info("Pipeline[%s].%s() cagrildi", src_id, hook_name)
                                break
                            except Exception as e:  # noqa: BLE001
                                logger.warning("Pipeline[%s].%s hata: %s", src_id, hook_name, e)
            self._manager = None
            self._pipeline = None
            self._loaded = False
            unloaded = mgr is not None
        _force_gc("ml_pipeline.unload")
        after = _rss_mb()
        freed = (before - after) if (before is not None and after is not None) else None
        logger.info(
            "ML unload tamamlandi: before=%sMB after=%sMB freed=%sMB",
            before, after, freed,
        )
        return {
            "unloaded": unloaded,
            "before_rss_mb": before,
            "after_rss_mb": after,
            "freed_mb": freed,
        }

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
        # Roboflow Hosted API path — image'a embed edilmemis pretrained
        # modeller icin HTTP API uzerinden inference.
        if source == "pretrained_roboflow_cardd":
            return self._analyze_via_roboflow(image)

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
        result: Optional[dict[str, Any]] = None
        for attempt in range(retries + 1):
            try:
                # GPU paylasimi: ayni anda 1 inference (Celery worker concurrency
                # > 1 olabilir; bu lock kritik).
                with self._infer_lock:
                    result = self._manager.analyze(image, source=source)
                break
            except ValueError:
                # source id gecersiz -> retry yapma, hatayi yukari ver
                raise
            except Exception as e:  # noqa: BLE001 — yeniden raise
                last_err = e
                logger.warning("Analiz denemesi %d/%d hatali: %s", attempt + 1, retries + 1, e)
        if result is None:
            assert last_err is not None
            raise last_err

        # ---- Roboflow Hosted API ozel pipeline ----  (sinif disi degil; gomulu)
        # Asagidaki _analyze_via_roboflow methodu pre-trained Roboflow modeli
        # icin custom YOLO pipeline'i atlatir; sadece HTTP API cagrisi yapar.

        # RAM-tasarrufu: 512MB Render free profili — her inference sonrasi
        # ModelManager'i bosalt. AI Engineer ajan pipeline.py icine zaten
        # per-stage (damage->del->parts->del->severity->del) cleanup ekledi;
        # bu bosalti ana modul-seviyesi referansi da kaldirip RSS'i baseline'a
        # geri dondurur (sonraki inference cold load = ~2-3sn extra latency).
        if getattr(settings, "ml_unload_after_inference", False):
            try:
                self.unload()
            except Exception as e:  # noqa: BLE001
                logger.warning("post-inference unload basarisiz: %s", e)
        else:
            # Unload yapmasak bile gc kosturalim — np.ndarray ara buffer'lari
            # serbest birakilsin (ultralytics tahmin sonrasi geride bos
            # tensor cache birakir).
            _force_gc("post-analyze")

        return result

    def _analyze_via_roboflow(self, image: np.ndarray) -> dict[str, Any]:
        """Pretrained Roboflow scratch_dent v3 modelini HTTP API ile cagir.

        Custom pipeline atlatilir; ne damage modeli ne parts ne severity
        yuklenir. Frontend Inspection schema uyumlu bir cikti uretir:
        Roboflow detection'lari `unassigned_damages` listesine konur
        (parts boş kalir, schema match olur).
        """
        import cv2  # local import
        from roboflow_inference import (  # type: ignore
            run_roboflow_damage_inference,
            is_roboflow_available,
        )

        if not is_roboflow_available():
            raise RuntimeError(
                "ROBOFLOW_API_KEY env yok — Roboflow pretrained modeli "
                "icin API key gerekli. HF Spaces secret olarak ekleyin."
            )

        h, w = image.shape[:2]
        ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok:
            raise RuntimeError("Goruntu JPEG encode edilemedi")
        img_bytes = buf.tobytes()

        raw_damages = run_roboflow_damage_inference(
            img_bytes,
            workspace="carpro",
            project="car-scratch-and-dent",
            version=3,
        )

        # TR ceviri + frontend Damage schema'sina map et
        TR = {"dent": "Göçük", "scratch": "Çizik", "damage": "Hasar"}
        SEVERITY_TR = {"hafif": "Hafif", "orta": "Orta", "agir": "Ağır"}

        unassigned: list[dict[str, Any]] = []
        for d in raw_damages:
            x1, y1, x2, y2 = d.get("bbox", [0, 0, 0, 0])
            bbox_w = max(0.0, x2 - x1)
            bbox_h = max(0.0, y2 - y1)
            area_ratio = (bbox_w * bbox_h) / max(1.0, float(w) * float(h))
            # Basit kural-tabanli severity (confidence + alan)
            conf = float(d.get("confidence", 0.0))
            if area_ratio > 0.15 or conf > 0.85:
                sev_level, sev_conf = "orta", 0.5
            elif area_ratio > 0.05 or conf > 0.7:
                sev_level, sev_conf = "hafif", 0.5
            else:
                sev_level, sev_conf = "hafif", 0.4

            dtype = d.get("class") or "damage"
            unassigned.append({
                "id": d.get("id", 0),
                "type": dtype,
                "type_tr": TR.get(dtype, dtype.title()),
                "confidence": conf,
                "bbox": d.get("bbox", [0, 0, 0, 0]),
                "polygon": d.get("polygon", []) or [],
                "polygon_normalized": [],  # detection-only model
                "area_ratio": area_ratio,
                "severity": {
                    "level": sev_level,
                    "level_tr": SEVERITY_TR.get(sev_level, sev_level.title()),
                    "confidence": sev_conf,
                    "method": "rule_based_roboflow",
                },
                "cost": {
                    "min_tl": 0,
                    "max_tl": 0,
                    "confidence": "low",
                    "source": "roboflow_no_cost",
                },
                "is_multi_part": False,
                "is_low_confidence_match": False,
                "source": "roboflow",
            })

        total_damage = len(unassigned)
        most_severe = None
        most_severe_tr = None
        if unassigned:
            # En agir level'i bul
            order = {"hafif": 1, "orta": 2, "agir": 3}
            top = max(unassigned, key=lambda u: order.get(u["severity"]["level"], 0))
            most_severe = top["severity"]["level"]
            most_severe_tr = top["severity"]["level_tr"]

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "image": {"url": None, "width": int(w), "height": int(h)},
            "parts": [],
            "unassigned_damages": unassigned,
            "multi_part_damages": [],
            "summary": {
                "total_parts_inspected": 0,
                "damaged_parts_count": 0,
                "clean_parts_count": 0,
                "total_damage_count": total_damage,
                "unknown_part_damages_count": total_damage,
                "multi_part_damages_count": 0,
                "most_severe_level": most_severe,
                "most_severe_level_tr": most_severe_tr,
                "total_damage_area_ratio": sum(u["area_ratio"] for u in unassigned),
                "total_cost_range_tl": [0, 0],
                "total_cost_midpoint_tl": 0,
                "cost_confidence": "low",
                "repair_recommendation": "manual_review" if unassigned else "hasar_yok",
                "repair_recommendation_tr": (
                    "Manuel inceleme önerilir (Roboflow: maliyet yok)"
                    if unassigned else "Hasar tespit edilmedi"
                ),
                "estimated_repair_days": 1 if unassigned else 0,
                "model_source": "roboflow",
                "note": (
                    "Roboflow scratch_dent v3 hosted inference. "
                    "Parça segmentasyonu / maliyet hesaplaması yapılmaz."
                ),
            },
            "visualization_urls": {"annotated": None, "parts": None, "damages": None},
            "model_versions": {
                "pretrained_source": "roboflow_cardd_scratch_dent_v3",
                "requested_model": "pretrained_roboflow_cardd",
            },
            "model_source": "roboflow",
        }


# Singleton — module import edildiginde MLPipeline() constructor'i hicbir
# model yuklemiyor; sadece bos slot'lar olusturuyor. Ilk warm_up() veya
# analyze() cagrisina kadar torch/ultralytics bile import edilmiyor.
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


def check_model_files_available(model_id: Optional[str]) -> tuple[bool, str]:
    """Pretrained model agirlik dosyalari bu deploy'da mevcut mu?
    Returns (available, reason). custom her zaman OK (entrypoint indirir).
    """
    if not model_id or model_id == DEFAULT_MODEL_ID:
        return True, ""
    try:
        # Registry'den entry'i al — modul `get_registry()` veya direkt erisim
        # destekliyor. REGISTRY sembolu yok; eski kodda hata kaynagiydi.
        from pretrained_registry import get_registry  # type: ignore
        reg = get_registry()
        entry = None
        # PretrainedRegistry sinifinda get() metodu var
        if hasattr(reg, "get"):
            entry = reg.get(model_id)
        # Eger entry uygunsa dosya/key check
        if entry is not None and hasattr(entry, "is_available"):
            if not entry.is_available():
                return False, (
                    f"'{getattr(entry, 'name', model_id)}' modeli bu deploy'da "
                    "indirilmemis. Lutfen 'Kendi Modellerim' (custom) "
                    "secenegini kullanin."
                )
            return True, ""
        # Source-level model_id ise (pretrained_roboflow_cardd vs)
        for m in list_available_models():
            if m.get("id") == model_id:
                if m.get("available") is False:
                    return False, (
                        f"'{m.get('name', model_id)}' modeli bu deploy'da "
                        "indirilmemis. Lutfen 'Kendi Modellerim' (custom) "
                        "secenegini kullanin."
                    )
                return True, ""
        return False, f"Model bulunamadi: {model_id}"
    except Exception as exc:  # noqa: BLE001
        logger.warning("check_model_files_available hata: %s", exc)
        return True, ""  # fail-open; gerçek inference patlarsa orada handle


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
