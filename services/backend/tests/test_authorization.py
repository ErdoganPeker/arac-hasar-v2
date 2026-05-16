"""
Authorization E2E testleri (cross-user erisim).

Senaryo:
  - User A bir inspection olusturur (sync veya async)
  - User B ayni id'yi GET/DELETE etmeye calisir
  - Beklenen: 403 (yetki yok) veya 404 (yoksay, info-leak engelle)

Hem JWT path'i hem inspection ownership check'i (main.py'da client_id
karsilastirmasi) burada test edilir.
"""
from __future__ import annotations

import httpx
import pytest


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_sync_inspection(client: httpx.AsyncClient, token: str, png: bytes) -> str:
    """User A icin sync inspection olustur ve id'sini dondur."""
    files = {"file": ("a.png", png, "image/png")}
    r = await client.post(
        "/api/v1/inspect/sync",
        files=files,
        headers=_bearer(token),
    )
    assert r.status_code == 200, r.text
    return r.json()["inspection_id"]


# ---------------- GET ----------------

async def test_user_b_cannot_read_user_a_inspection(
    async_client: httpx.AsyncClient, png_bytes: bytes,
    reset_user_store, reset_inspection_store
):
    # Register two users
    a = await async_client.post(
        "/auth/register",
        json={"email": "owner@test.example.com", "password": "strong-pass-1234"},
    )
    b = await async_client.post(
        "/auth/register",
        json={"email": "attacker@test.example.com", "password": "strong-pass-1234"},
    )
    token_a = a.json()["access_token"]
    token_b = b.json()["access_token"]

    # User A creates
    inspection_id = await _create_sync_inspection(async_client, token_a, png_bytes)

    # User A okuyabilir
    r_a = await async_client.get(
        f"/api/v1/inspect/{inspection_id}",
        headers=_bearer(token_a),
    )
    assert r_a.status_code == 200

    # User B okuyamamali
    r_b = await async_client.get(
        f"/api/v1/inspect/{inspection_id}",
        headers=_bearer(token_b),
    )
    assert r_b.status_code in (403, 404), (
        f"User B'nin {inspection_id}'ye erisimi engellenmedi: {r_b.status_code}"
    )


# ---------------- DELETE ----------------

async def test_user_b_cannot_delete_user_a_inspection(
    async_client: httpx.AsyncClient, png_bytes: bytes,
    reset_user_store, reset_inspection_store
):
    a = await async_client.post(
        "/auth/register",
        json={"email": "owner2@test.example.com", "password": "strong-pass-1234"},
    )
    b = await async_client.post(
        "/auth/register",
        json={"email": "attacker2@test.example.com", "password": "strong-pass-1234"},
    )
    token_a = a.json()["access_token"]
    token_b = b.json()["access_token"]

    inspection_id = await _create_sync_inspection(async_client, token_a, png_bytes)

    # User B silemez
    r_b = await async_client.delete(
        f"/api/v1/inspect/{inspection_id}",
        headers=_bearer(token_b),
    )
    assert r_b.status_code in (403, 404)

    # User A hala okuyabilir — silinmedi
    r_a = await async_client.get(
        f"/api/v1/inspect/{inspection_id}",
        headers=_bearer(token_a),
    )
    assert r_a.status_code == 200


# ---------------- visualization endpoint cross-user ----------------

async def test_user_b_cannot_get_visualization_of_user_a(
    async_client: httpx.AsyncClient, png_bytes: bytes,
    reset_user_store, reset_inspection_store
):
    a = await async_client.post(
        "/auth/register",
        json={"email": "vizowner@test.example.com", "password": "strong-pass-1234"},
    )
    b = await async_client.post(
        "/auth/register",
        json={"email": "vizattacker@test.example.com", "password": "strong-pass-1234"},
    )
    token_a = a.json()["access_token"]
    token_b = b.json()["access_token"]

    inspection_id = await _create_sync_inspection(async_client, token_a, png_bytes)

    r_b = await async_client.get(
        f"/api/v1/inspect/{inspection_id}/visualization/annotated",
        headers=_bearer(token_b),
        follow_redirects=False,
    )
    assert r_b.status_code in (403, 404)


# ---------------- list isolation ----------------

async def test_list_returns_only_own_inspections(
    async_client: httpx.AsyncClient, png_bytes: bytes,
    reset_user_store, reset_inspection_store
):
    a = await async_client.post(
        "/auth/register",
        json={"email": "list_a@test.example.com", "password": "strong-pass-1234"},
    )
    b = await async_client.post(
        "/auth/register",
        json={"email": "list_b@test.example.com", "password": "strong-pass-1234"},
    )
    token_a = a.json()["access_token"]
    token_b = b.json()["access_token"]

    a_id = await _create_sync_inspection(async_client, token_a, png_bytes)
    b_id = await _create_sync_inspection(async_client, token_b, png_bytes)

    # User A list -> sadece kendi id'si
    la = await async_client.get("/api/v1/inspect", headers=_bearer(token_a))
    assert la.status_code == 200
    a_ids = {item["inspection_id"] for item in la.json()["items"]}
    assert a_id in a_ids
    assert b_id not in a_ids

    # User B list -> sadece kendi id'si
    lb = await async_client.get("/api/v1/inspect", headers=_bearer(token_b))
    assert lb.status_code == 200
    b_ids = {item["inspection_id"] for item in lb.json()["items"]}
    assert b_id in b_ids
    assert a_id not in b_ids


# ---------------- no auth ----------------

async def test_get_inspection_without_token_in_prod_returns_401(
    async_client: httpx.AsyncClient, png_bytes: bytes, monkeypatch,
    reset_user_store, reset_inspection_store
):
    """Dev mode kapali iken token olmadan erisim 401 olmali."""
    from config import settings
    monkeypatch.setattr(settings, "api_keys", ["valid-key-123"])
    monkeypatch.setattr(settings, "environment", "production")

    # Bir id'ye token'siz erisim — 401 olmali (404 degil, cunku auth onceden duser)
    r = await async_client.get(
        "/api/v1/inspect/00000000-0000-0000-0000-000000000000",
    )
    assert r.status_code == 401
