"""
Visualization endpoint testleri.

GET /api/v1/inspect/{id}/visualization/{annotated|parts|damages}
Beklenen davranis:
  - completed inspection icin result.visualization_urls var ise -> 302 redirect
  - yoksa storage.get_presigned_url fallback'inden URL uretir veya 404

Bu test'te:
  1. Sync inspection olusturup, sonra result icine visualization_urls enjekte ederiz
  2. GET endpoint'i 302 doner ve Location header'i set eder
  3. Olmayan tipler icin 404 doner (mocked get_presigned_url ile)
"""
from __future__ import annotations

import httpx
import pytest


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _setup_completed_with_viz(
    async_client: httpx.AsyncClient,
    png_bytes: bytes,
    viz_url_map: dict | None = None,
) -> tuple[str, str]:
    """Sync inspection olustur ve result.visualization_urls'i guncelle.

    Returns: (inspection_id, access_token)
    """
    reg = await async_client.post(
        "/auth/register",
        json={"email": "viz@test.example.com", "password": "strong-pass-1234"},
    )
    token = reg.json()["access_token"]

    files = {"file": ("a.png", png_bytes, "image/png")}
    r = await async_client.post(
        "/api/v1/inspect/sync",
        files=files,
        headers=_bearer(token),
    )
    assert r.status_code == 200
    inspection_id = r.json()["inspection_id"]

    if viz_url_map is not None:
        # Mevcut result'i al, visualization_urls ekle
        from main import get_db, update_inspection
        existing = get_db().get(inspection_id)
        result = dict(existing.get("result") or {})
        result["visualization_urls"] = viz_url_map
        update_inspection(inspection_id, result=result)

    return inspection_id, token


async def test_visualization_redirects_302_when_url_exists(
    async_client: httpx.AsyncClient, png_bytes: bytes,
    reset_user_store, reset_inspection_store
):
    viz_map = {
        "annotated": "https://cdn.test.local/inspections/x/annotated.png?sig=abc",
        "parts": "https://cdn.test.local/inspections/x/parts.png?sig=def",
        "damages": "https://cdn.test.local/inspections/x/damages.png?sig=ghi",
    }
    inspection_id, token = await _setup_completed_with_viz(
        async_client, png_bytes, viz_url_map=viz_map
    )

    for viz_type, expected_url in viz_map.items():
        r = await async_client.get(
            f"/api/v1/inspect/{inspection_id}/visualization/{viz_type}",
            headers=_bearer(token),
            follow_redirects=False,
        )
        assert r.status_code == 302, f"{viz_type}: {r.status_code} {r.text}"
        assert r.headers.get("location") == expected_url


async def test_visualization_falls_back_to_presigned_when_no_urls(
    async_client: httpx.AsyncClient, png_bytes: bytes, monkeypatch,
    reset_user_store, reset_inspection_store
):
    """visualization_urls yoksa, storage.get_presigned_url cagrilir."""
    fake_signed = "https://cdn.test.local/fallback/annotated.png?token=xyz"

    def fake_get_presigned_url(key, expires_in=None):
        return fake_signed

    # main.py'deki import noktasini yamala
    monkeypatch.setattr("main.get_presigned_url", fake_get_presigned_url)

    inspection_id, token = await _setup_completed_with_viz(
        async_client, png_bytes, viz_url_map=None
    )

    r = await async_client.get(
        f"/api/v1/inspect/{inspection_id}/visualization/annotated",
        headers=_bearer(token),
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers.get("location") == fake_signed


async def test_visualization_returns_404_when_no_url_and_presign_fails(
    async_client: httpx.AsyncClient, png_bytes: bytes, monkeypatch,
    reset_user_store, reset_inspection_store
):
    def fake_get_presigned_url(key, expires_in=None):
        raise RuntimeError("S3 unreachable")

    monkeypatch.setattr("main.get_presigned_url", fake_get_presigned_url)

    inspection_id, token = await _setup_completed_with_viz(
        async_client, png_bytes, viz_url_map=None
    )

    r = await async_client.get(
        f"/api/v1/inspect/{inspection_id}/visualization/annotated",
        headers=_bearer(token),
        follow_redirects=False,
    )
    assert r.status_code == 404


async def test_visualization_invalid_type_returns_422(
    async_client: httpx.AsyncClient, png_bytes: bytes,
    reset_user_store, reset_inspection_store
):
    inspection_id, token = await _setup_completed_with_viz(
        async_client, png_bytes, viz_url_map=None
    )
    r = await async_client.get(
        f"/api/v1/inspect/{inspection_id}/visualization/invalid_type_xyz",
        headers=_bearer(token),
    )
    # Literal pattern check -> FastAPI 422
    assert r.status_code == 422


async def test_visualization_404_when_inspection_missing(
    async_client: httpx.AsyncClient,
    reset_user_store, reset_inspection_store
):
    reg = await async_client.post(
        "/auth/register",
        json={"email": "noinspec@test.example.com", "password": "strong-pass-1234"},
    )
    token = reg.json()["access_token"]

    r = await async_client.get(
        "/api/v1/inspect/00000000-0000-0000-0000-000000000000/visualization/annotated",
        headers=_bearer(token),
        follow_redirects=False,
    )
    assert r.status_code == 404
