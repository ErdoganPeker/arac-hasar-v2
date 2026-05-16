"""
Sync inspection E2E testleri.

Akis: register/login -> /api/v1/inspect/sync -> response sema dogrulamasi
      (parts[], summary, total_cost_range_tl)

ML servisi conftest'te mocklanmistir; gercek YOLO calismaz, sabit JSON doner.
"""
from __future__ import annotations

from typing import Any

import httpx
import pytest

from models import SyncInspectionResponse


# ---------------- yardimcilar ----------------

def _install_rich_ml_mock(monkeypatch) -> None:
    """ML mock'unu parts dolu bir sonuc dondurecek sekilde gucverin —
    response sema dogrulamasini gercek bir aggregate sonucu uzerinden yap.
    """
    from ml_service import ml_pipeline

    rich = {
        "inspection_id": "will-be-overwritten",
        "timestamp": "2026-05-16T00:00:00Z",
        "image": {"url": "test://img", "width": 640, "height": 480},
        "parts": [
            {
                "name": "front_bumper",
                "name_tr": "On tampon",
                "confidence": 0.92,
                "status": "moderate_damage",
                "damage_count": 1,
                "polygon_normalized": [],
                "bbox": [10.0, 10.0, 100.0, 100.0],
                "damages": [
                    {
                        "id": 1,
                        "type": "dent",
                        "type_tr": "Gocuk",
                        "confidence": 0.88,
                        "severity": {
                            "level": "orta",
                            "level_tr": "Orta",
                            "confidence": 0.81,
                            "method": "rule",
                        },
                        "bbox": [12.0, 12.0, 80.0, 80.0],
                        "polygon_normalized": [],
                        "area_ratio": 0.02,
                        "cost": {
                            "min_tl": 1500.0,
                            "max_tl": 3500.0,
                            "midpoint_tl": 2500.0,
                            "confidence": "medium",
                            "source": "cost_table.yaml",
                        },
                    }
                ],
                "part_cost_min_tl": 1500.0,
                "part_cost_max_tl": 3500.0,
                "cost_note": None,
            }
        ],
        "summary": {
            "total_parts_inspected": 1,
            "damaged_parts_count": 1,
            "clean_parts_count": 0,
            "total_damage_count": 1,
            "unknown_part_damages_count": 0,
            "multi_part_damages_count": 0,
            "most_severe_level": "orta",
            "most_severe_level_tr": "Orta",
            "total_damage_area_ratio": 0.02,
            "total_cost_range_tl": [1500.0, 3500.0],
            "total_cost_midpoint_tl": 2500.0,
            "cost_confidence": "medium",
            "repair_recommendation": "tamir_boya",
            "repair_recommendation_tr": "Tamir + boya gerekli",
            "estimated_repair_days": 1,
        },
    }
    monkeypatch.setattr(ml_pipeline, "analyze", lambda img, retries=2: dict(rich))


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------- tests ----------------

async def test_sync_single_image_returns_valid_schema(
    async_client: httpx.AsyncClient, png_bytes: bytes, monkeypatch,
    reset_user_store, reset_inspection_store
):
    _install_rich_ml_mock(monkeypatch)

    # Register
    reg = await async_client.post(
        "/auth/register",
        json={"email": "syncuser@test.example.com", "password": "strong-pass-1234"},
    )
    token = reg.json()["access_token"]

    # POST sync — multipart upload
    files = {"file": ("car.png", png_bytes, "image/png")}
    r = await async_client.post(
        "/api/v1/inspect/sync",
        files=files,
        headers=_bearer(token),
    )
    assert r.status_code == 200, r.text

    # Pydantic ile sema dogrulamasi — SyncInspectionResponse validate eder
    body = r.json()
    parsed = SyncInspectionResponse.model_validate(body)

    # Top-level fields
    assert parsed.inspection_id
    assert parsed.processed_at
    assert parsed.result is not None

    # parts[]
    assert len(parsed.result.parts) == 1
    part = parsed.result.parts[0]
    assert part.name == "front_bumper"
    assert part.status == "moderate_damage"
    assert part.damage_count == 1
    assert len(part.damages) == 1

    # summary
    summary = parsed.result.summary
    assert summary.total_parts_inspected == 1
    assert summary.damaged_parts_count == 1
    assert summary.total_damage_count == 1
    assert summary.most_severe_level == "orta"

    # total_cost_range_tl — sema gerektirir
    cost_range = summary.total_cost_range_tl
    assert isinstance(cost_range, tuple)
    assert len(cost_range) == 2
    assert cost_range[0] == 1500.0
    assert cost_range[1] == 3500.0
    assert summary.total_cost_midpoint_tl == 2500.0


async def test_sync_response_has_x_inspection_id_header(
    async_client: httpx.AsyncClient, png_bytes: bytes,
    reset_user_store, reset_inspection_store
):
    reg = await async_client.post(
        "/auth/register",
        json={"email": "hdr@test.example.com", "password": "strong-pass-1234"},
    )
    token = reg.json()["access_token"]

    files = {"file": ("a.png", png_bytes, "image/png")}
    r = await async_client.post(
        "/api/v1/inspect/sync",
        files=files,
        headers=_bearer(token),
    )
    assert r.status_code == 200
    # main.py _process_sync header'i ekliyor — ama /sync wrapper'in JSONResponse'unda
    # body dondurur. Hala JSON icinde inspection_id olmali.
    assert r.json()["inspection_id"]


async def test_sync_inspect_multi_endpoint_with_sync_mode(
    async_client: httpx.AsyncClient, png_bytes: bytes, monkeypatch,
    reset_user_store, reset_inspection_store
):
    """/api/v1/inspect?mode=sync de calismali — ayni semayi dondurmeli."""
    _install_rich_ml_mock(monkeypatch)

    reg = await async_client.post(
        "/auth/register",
        json={"email": "msync@test.example.com", "password": "strong-pass-1234"},
    )
    token = reg.json()["access_token"]

    files = [("files", ("a.png", png_bytes, "image/png"))]
    r = await async_client.post(
        "/api/v1/inspect?mode=sync",
        files=files,
        headers=_bearer(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "inspection_id" in body
    assert "result" in body
    assert body["result"]["summary"]["total_cost_range_tl"] == [1500.0, 3500.0]


async def test_sync_rejects_empty_file(
    async_client: httpx.AsyncClient,
    reset_user_store, reset_inspection_store
):
    reg = await async_client.post(
        "/auth/register",
        json={"email": "empty@test.example.com", "password": "strong-pass-1234"},
    )
    token = reg.json()["access_token"]

    files = {"file": ("empty.png", b"", "image/png")}
    r = await async_client.post(
        "/api/v1/inspect/sync",
        files=files,
        headers=_bearer(token),
    )
    assert r.status_code == 400


async def test_sync_rejects_non_image_mime(
    async_client: httpx.AsyncClient,
    reset_user_store, reset_inspection_store
):
    reg = await async_client.post(
        "/auth/register",
        json={"email": "txt@test.example.com", "password": "strong-pass-1234"},
    )
    token = reg.json()["access_token"]

    files = {"file": ("doc.txt", b"hello world content", "text/plain")}
    r = await async_client.post(
        "/api/v1/inspect/sync",
        files=files,
        headers=_bearer(token),
    )
    assert r.status_code == 400
