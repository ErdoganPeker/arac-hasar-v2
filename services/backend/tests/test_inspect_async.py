"""
Async inspection E2E testleri.

Akis: register/login -> /api/v1/inspect?mode=async -> 202 + inspection_id ->
      GET /api/v1/inspect/{id}  (processing -> completed; worker simulate)

Worker conftest'te mocklanmistir (run_inspection_task.delay no-op).
'processing -> completed' transition'i in-memory store uzerinden manuel
asyncio.sleep ile simule edilir.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------- 202 ack ----------------

async def test_async_mode_returns_202_with_inspection_id(
    async_client: httpx.AsyncClient, png_bytes: bytes,
    reset_user_store, reset_inspection_store
):
    reg = await async_client.post(
        "/auth/register",
        json={"email": "asy@test.example.com", "password": "strong-pass-1234"},
    )
    token = reg.json()["access_token"]

    files = [("files", ("a.png", png_bytes, "image/png"))]
    r = await async_client.post(
        "/api/v1/inspect?mode=async",
        files=files,
        headers=_bearer(token),
    )
    assert r.status_code == 202, r.text

    body = r.json()
    assert body["status"] == "queued"
    assert body["inspection_id"]
    assert body["status_url"] == f"/api/v1/inspect/{body['inspection_id']}"
    assert body["created_at"]
    assert body["estimated_completion_seconds"] >= 15

    # Response header
    assert r.headers.get("X-Inspection-Id") == body["inspection_id"]


# ---------------- queued -> processing -> completed ----------------

async def test_async_status_transitions_queued_to_completed(
    async_client: httpx.AsyncClient, png_bytes: bytes,
    reset_user_store, reset_inspection_store
):
    """In-memory store uzerinden worker simulasyonu —
    inspection_id'yi queued ile olustur, sonra 1-2 sn sleep ile completed'a guncelle.
    """
    reg = await async_client.post(
        "/auth/register",
        json={"email": "trans@test.example.com", "password": "strong-pass-1234"},
    )
    token = reg.json()["access_token"]

    # 1) async enqueue
    files = [("files", ("a.png", png_bytes, "image/png"))]
    r = await async_client.post(
        "/api/v1/inspect?mode=async",
        files=files,
        headers=_bearer(token),
    )
    assert r.status_code == 202
    inspection_id = r.json()["inspection_id"]

    # 2) Hemen GET — status queued olmali
    r1 = await async_client.get(
        f"/api/v1/inspect/{inspection_id}",
        headers=_bearer(token),
    )
    assert r1.status_code == 200, r1.text
    assert r1.json()["status"] == "queued"

    # 3) Worker simulasyonu — processing
    from main import update_inspection
    update_inspection(inspection_id, status="processing")
    await asyncio.sleep(0.05)  # event loop yield

    r2 = await async_client.get(
        f"/api/v1/inspect/{inspection_id}",
        headers=_bearer(token),
    )
    assert r2.status_code == 200
    assert r2.json()["status"] == "processing"

    # 4) Worker tamamlandi — completed + result
    fake_result = {
        "inspection_id": inspection_id,
        "timestamp": "2026-05-16T00:01:00Z",
        "image": {"url": "test://img", "width": 640, "height": 480},
        "parts": [],
        "summary": {
            "total_parts_inspected": 0,
            "damaged_parts_count": 0,
            "clean_parts_count": 0,
            "total_damage_count": 0,
            "unknown_part_damages_count": 0,
            "multi_part_damages_count": 0,
            "most_severe_level": None,
            "most_severe_level_tr": None,
            "total_damage_area_ratio": 0.0,
            "total_cost_range_tl": [0.0, 0.0],
            "cost_confidence": "low",
            "repair_recommendation": "hasar_yok",
            "repair_recommendation_tr": "Hasar tespit edilmedi",
            "estimated_repair_days": 0,
        },
    }
    update_inspection(
        inspection_id,
        status="completed",
        result=fake_result,
        completed_at="2026-05-16T00:01:00Z",
    )
    await asyncio.sleep(0.05)

    r3 = await async_client.get(
        f"/api/v1/inspect/{inspection_id}",
        headers=_bearer(token),
    )
    assert r3.status_code == 200
    body = r3.json()
    assert body["status"] == "completed"
    assert body["result"] is not None
    assert body["result"]["summary"]["total_parts_inspected"] == 0


async def test_async_polling_eventually_completes(
    async_client: httpx.AsyncClient, png_bytes: bytes,
    reset_user_store, reset_inspection_store
):
    """Background task simulasyonu — asyncio task ile completed'a getir,
    main thread polling loop'u yapsin.
    """
    reg = await async_client.post(
        "/auth/register",
        json={"email": "poll@test.example.com", "password": "strong-pass-1234"},
    )
    token = reg.json()["access_token"]

    files = [("files", ("a.png", png_bytes, "image/png"))]
    r = await async_client.post(
        "/api/v1/inspect?mode=async",
        files=files,
        headers=_bearer(token),
    )
    inspection_id = r.json()["inspection_id"]

    async def _fake_worker():
        await asyncio.sleep(0.5)
        from main import update_inspection
        update_inspection(inspection_id, status="processing")
        await asyncio.sleep(0.5)
        update_inspection(
            inspection_id,
            status="completed",
            result={
                "inspection_id": inspection_id,
                "timestamp": "2026-05-16T00:02:00Z",
                "image": {"url": "test://img", "width": 1, "height": 1},
                "parts": [],
                "summary": {
                    "total_parts_inspected": 0,
                    "damaged_parts_count": 0,
                    "clean_parts_count": 0,
                    "total_damage_count": 0,
                    "unknown_part_damages_count": 0,
                    "multi_part_damages_count": 0,
                    "most_severe_level": None,
                    "most_severe_level_tr": None,
                    "total_damage_area_ratio": 0.0,
                    "total_cost_range_tl": [0.0, 0.0],
                    "cost_confidence": "low",
                    "repair_recommendation": "hasar_yok",
                    "repair_recommendation_tr": "Hasar tespit edilmedi",
                    "estimated_repair_days": 0,
                },
            },
        )

    worker_task = asyncio.create_task(_fake_worker())

    # Polling loop — max 3 saniye
    final_status = None
    for _ in range(30):
        await asyncio.sleep(0.1)
        rr = await async_client.get(
            f"/api/v1/inspect/{inspection_id}",
            headers=_bearer(token),
        )
        assert rr.status_code == 200
        final_status = rr.json()["status"]
        if final_status == "completed":
            break

    await worker_task
    assert final_status == "completed"


# ---------------- async limits ----------------

async def test_async_rejects_too_many_files(
    async_client: httpx.AsyncClient, png_bytes: bytes,
    reset_user_store, reset_inspection_store
):
    reg = await async_client.post(
        "/auth/register",
        json={"email": "many@test.example.com", "password": "strong-pass-1234"},
    )
    token = reg.json()["access_token"]

    # max_images_async = 20 default — 21 ile asalim
    files = [("files", (f"img_{i}.png", png_bytes, "image/png")) for i in range(21)]
    r = await async_client.post(
        "/api/v1/inspect?mode=async",
        files=files,
        headers=_bearer(token),
    )
    assert r.status_code == 400


async def test_get_inspection_missing_id_returns_404(
    async_client: httpx.AsyncClient,
    reset_user_store, reset_inspection_store
):
    reg = await async_client.post(
        "/auth/register",
        json={"email": "missing@test.example.com", "password": "strong-pass-1234"},
    )
    token = reg.json()["access_token"]

    r = await async_client.get(
        "/api/v1/inspect/00000000-0000-0000-0000-000000000000",
        headers=_bearer(token),
    )
    assert r.status_code == 404
