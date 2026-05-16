"""
backend/worker.py
Celery worker — async hasar tespit jobs.

Run:
    celery -A worker.celery_app worker --loglevel=info --concurrency=2

Concurrency 1-2 onerilir (GPU paylasimi MLPipeline icindeki lock ile serialize edilir;
yine de proses bazinda dusuk tut, RAM/VRAM darbogazi).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

import cv2
import numpy as np
from celery import Celery
from celery.signals import worker_ready

from config import settings
from ml_service import ml_pipeline
from storage import download_image


def _update_inspection(inspection_id: str, **fields):
    """Lazy import — main.py'den circular dependency'i bozmadan kullan."""
    from main import update_inspection
    return update_inspection(inspection_id, **fields)


logger = logging.getLogger(__name__)


# ============================ Celery app ============================

_broker_url = settings.redis_url
# Upstash/managed Redis genelde rediss:// (TLS) — kombu default insecure
# warning veriyor + 'ssl_cert_reqs' eksik error firlatiyor. Explicit set.
import ssl as _ssl
_uses_tls = _broker_url.startswith("rediss://")
_ssl_opts = {"ssl_cert_reqs": _ssl.CERT_NONE} if _uses_tls else None

celery_app = Celery(
    "arac_hasar",
    broker=_broker_url,
    backend=_broker_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Istanbul",
    enable_utc=True,
    task_soft_time_limit=180,
    task_time_limit=240,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
    broker_connection_retry_on_startup=True,
)
if _ssl_opts:
    celery_app.conf.broker_use_ssl = _ssl_opts
    celery_app.conf.redis_backend_use_ssl = _ssl_opts


# ============================ Pub-sub helper ============================

def _publish(inspection_id: str, payload: dict) -> None:
    """WS abonelerine yayin. Hata loglar, exception throw etmez."""
    try:
        from ws import publish_status_sync
        publish_status_sync(inspection_id, payload)
    except Exception as e:  # noqa: BLE001
        logger.warning("Pub/sub yayini basarisiz (%s): %s", inspection_id, e)


# ============================ Worker lifecycle ============================

@worker_ready.connect
def _on_worker_ready(**_: Any) -> None:
    """Worker basladiginda modeli yukle — ilk task'in latency'si dussun."""
    logger.info("Celery worker hazirlaniyor — ML pipeline yukleniyor...")
    try:
        ml_pipeline.warm_up()
        logger.info("Worker hazir, modeller bellekte.")
    except Exception as e:
        logger.exception("ML warm-up basarisiz; istekler lazy-load'a dusecek: %s", e)


# ============================ Tasks ============================

@celery_app.task(name="run_inspection", bind=True, max_retries=2, default_retry_delay=10)
def run_inspection_task(self, inspection_id: str, image_urls: list[str],
                        model: str = "custom"):
    """Bir inspection icin tum goruntuleri isle ve sonucu DB'ye yaz.

    Args:
        inspection_id: DB primary key.
        image_urls: S3 URL listesi.
        model: pipeline kaynak id'si — "custom" (default) ya da
               "pretrained_*". Frontend toggle'ndan gecer.
    """
    logger.info("[%s] Basladi, %d goruntu", inspection_id, len(image_urls))

    try:
        _update_inspection(inspection_id, status="processing")
        # (lazy delegate -> main.update_inspection)
        _publish(inspection_id, {
            "type": "status",
            "inspection_id": inspection_id,
            "status": "processing",
        })

        # Goruntuleri indir — basarili olanlarin URL'i ile aynı sırada eşle
        image_bytes: list[bytes] = []
        downloaded_urls: list[str] = []
        for i, url in enumerate(image_urls):
            try:
                image_bytes.append(download_image(url))
                downloaded_urls.append(url)
            except Exception as e:
                logger.warning("[%s] Goruntu %d indirilemedi: %s", inspection_id, i, e)

        if not image_bytes:
            raise RuntimeError("Hicbir goruntu indirilemedi")

        # ml_service.run_inspection async — celery sync. Yeni event-loop'ta cagir.
        # image_urls de iletilir ki per-image response'da S3 URL'leri yer alsin
        # (frontend "N foto = N kart" beklentisi + "<inline>" legacy override).
        from ml_service import run_inspection
        # Yalniz basariyla indirilen byte'larla eslesen URL listesini ilet.
        # Burada image_bytes'a paralel listede tutmak yerine pratik olarak
        # tam image_urls'i geciyoruz; indirilemeyenler ml_service tarafinda
        # status=failed/per-image kaydiyla yansir.
        aggregated = asyncio.run(
            run_inspection(image_bytes, user_id=inspection_id,
                           image_urls=downloaded_urls, source=model)
        )
        aggregated["inspection_id"] = inspection_id

        _update_inspection(
            inspection_id,
            status="completed",
            result=aggregated,
            completed_at=datetime.utcnow().isoformat(),
        )
        _publish(inspection_id, {
            "type": "completed",
            "inspection_id": inspection_id,
            "result": aggregated,
        })
        logger.info(
            "[%s] Tamamlandi. %d hasar.",
            inspection_id,
            (aggregated.get("summary") or {}).get("total_damage_count", 0),
        )
        return {"inspection_id": inspection_id, "status": "completed"}

    except Exception as e:  # noqa: BLE001
        logger.exception("[%s] Kritik hata: %s", inspection_id, e)
        _update_inspection(
            inspection_id,
            status="failed",
            error=str(e),
            completed_at=datetime.utcnow().isoformat(),
        )
        _publish(inspection_id, {
            "type": "error",
            "inspection_id": inspection_id,
            "error": str(e),
        })
        if self.request.retries < self.max_retries:
            logger.info("[%s] Retry %d/%d", inspection_id, self.request.retries + 1, self.max_retries)
            raise self.retry(exc=e)
        return {"inspection_id": inspection_id, "status": "failed", "error": str(e)}
