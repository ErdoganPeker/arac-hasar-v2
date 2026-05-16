"""
backend/ws.py
WebSocket streaming for async inspection jobs.

Endpoint: WS /api/v1/inspect/{inspection_id}/stream

Strateji:
  1) Redis pub/sub varsa kullan (worker.py inspection_id'ye publish eder)
  2) Yoksa DB polling fallback (her 1s'de bir status check)

Worker tarafi (worker.py) status degisikliginde su kanala publish etmelidir:
    redis.publish(f"inspection:{id}:status", json.dumps({"status": "...", ...}))
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import WebSocket, WebSocketDisconnect, status

from config import settings
# Inspection okuma — pilot interim main.py icindeki repo. ORM hazirsa
# main.get_db yerine ORM session ile yer degistir.
from models import InspectionStatus


logger = logging.getLogger(__name__)


POLL_INTERVAL_SEC = 1.0
MAX_DURATION_SEC = 600  # 10 dakika hard limit


def _channel(inspection_id: str) -> str:
    return f"inspection:{inspection_id}:status"


async def _redis_client():
    """Async redis client kur. Yoksa None don."""
    try:
        import redis.asyncio as aioredis
        url = settings.effective_redis_pubsub_url
        if not url:
            logger.warning("Redis URL bos, pub/sub devre disi")
            return None
        client = aioredis.from_url(url, decode_responses=True)
        await client.ping()
        return client
    except Exception as e:
        logger.warning(f"Redis pubsub kullanilamiyor, polling moduna gec: {e}")
        return None


def _get_inspection(inspection_id: str) -> Optional[dict]:
    """main.get_db() lazy import — circular import korumasi."""
    from main import get_db  # local import; ws.py main'den hemen sonra yuklenir
    return get_db().get(inspection_id)


async def _send_current_state(ws: WebSocket, inspection_id: str) -> Optional[InspectionStatus]:
    """DB'den son durumu cek ve gonder. Don: son status."""
    inspection = _get_inspection(inspection_id)
    if not inspection:
        await ws.send_json({
            "type": "error",
            "inspection_id": inspection_id,
            "error": "Inspection bulunamadi",
        })
        return None

    current_status: InspectionStatus = inspection["status"]

    if current_status == "completed":
        await ws.send_json({
            "type": "completed",
            "inspection_id": inspection_id,
            "result": inspection.get("result"),
        })
    elif current_status == "failed":
        await ws.send_json({
            "type": "error",
            "inspection_id": inspection_id,
            "error": inspection.get("error") or "Inceleme basarisiz",
        })
    else:
        await ws.send_json({
            "type": "status",
            "inspection_id": inspection_id,
            "status": current_status,
        })

    return current_status


async def stream_inspection(websocket: WebSocket, inspection_id: str):
    """WebSocket endpoint handler.

    Akis:
      - Accept
      - Mevcut durumu gonder (idempotent)
      - Terminal degilse: pub/sub veya polling ile guncellemeleri bekle
      - Terminal duruma gelince close
    """
    await websocket.accept()

    try:
        last_status = await _send_current_state(websocket, inspection_id)
        if last_status in ("completed", "failed", None):
            await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)
            return

        redis_client = await _redis_client()
        deadline = asyncio.get_event_loop().time() + MAX_DURATION_SEC

        if redis_client:
            # Pub/sub modu
            pubsub = redis_client.pubsub()
            await pubsub.subscribe(_channel(inspection_id))
            try:
                while True:
                    if asyncio.get_event_loop().time() > deadline:
                        await websocket.send_json({
                            "type": "error",
                            "inspection_id": inspection_id,
                            "error": "Timeout: 10 dakika ictinde tamamlanmadi",
                        })
                        break

                    msg = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=POLL_INTERVAL_SEC,
                    )
                    if msg is None:
                        continue
                    try:
                        payload = json.loads(msg["data"])
                    except (ValueError, TypeError):
                        continue

                    await websocket.send_json(payload)
                    if payload.get("type") in ("completed", "error"):
                        break
            finally:
                try:
                    await pubsub.unsubscribe(_channel(inspection_id))
                    await pubsub.close()
                    await redis_client.close()
                except Exception:
                    pass
        else:
            # Polling fallback
            while True:
                if asyncio.get_event_loop().time() > deadline:
                    await websocket.send_json({
                        "type": "error",
                        "inspection_id": inspection_id,
                        "error": "Timeout: 10 dakika ictinde tamamlanmadi",
                    })
                    break

                await asyncio.sleep(POLL_INTERVAL_SEC)
                inspection = _get_inspection(inspection_id)
                if not inspection:
                    break

                new_status: InspectionStatus = inspection["status"]
                if new_status != last_status:
                    last_status = new_status
                    if new_status == "completed":
                        await websocket.send_json({
                            "type": "completed",
                            "inspection_id": inspection_id,
                            "result": inspection.get("result"),
                        })
                        break
                    elif new_status == "failed":
                        await websocket.send_json({
                            "type": "error",
                            "inspection_id": inspection_id,
                            "error": inspection.get("error") or "Inceleme basarisiz",
                        })
                        break
                    else:
                        await websocket.send_json({
                            "type": "status",
                            "inspection_id": inspection_id,
                            "status": new_status,
                        })

        await websocket.close(code=status.WS_1000_NORMAL_CLOSURE)

    except WebSocketDisconnect:
        logger.info(f"WS client disconnected: {inspection_id}")
    except Exception as e:
        logger.exception(f"WS handler hatasi ({inspection_id}): {e}")
        try:
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR)
        except Exception:
            pass


async def publish_status(inspection_id: str, payload: dict) -> bool:
    """Worker tarafi kullanir: bir incelemenin durumunu yayinla.

    Returns: True if published successfully.
    """
    try:
        import redis.asyncio as aioredis
        url = settings.effective_redis_pubsub_url
        if not url:
            return False
        client = aioredis.from_url(url, decode_responses=True)
        await client.publish(_channel(inspection_id), json.dumps(payload))
        await client.close()
        return True
    except Exception as e:
        logger.warning(f"Pub/sub publish basarisiz: {e}")
        return False


def publish_status_sync(inspection_id: str, payload: dict) -> bool:
    """Senkron versiyon (Celery worker icin)."""
    try:
        import redis as sync_redis
        url = settings.effective_redis_pubsub_url
        if not url:
            return False
        client = sync_redis.from_url(url, decode_responses=True)
        client.publish(_channel(inspection_id), json.dumps(payload))
        client.close()
        return True
    except Exception as e:
        logger.warning(f"Pub/sub publish (sync) basarisiz: {e}")
        return False
