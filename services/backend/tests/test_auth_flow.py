"""
Auth flow E2E testleri.

Akis: register -> login -> me -> refresh -> me (yeni token) -> invalid token -> 401

Bu testler /auth/* router'inin tam islevselligini kapsar; security.py'daki
JWT verify + auth.py'deki dependency chain'i birlikte calistirir.
"""
from __future__ import annotations

import httpx
import pytest


# ---------------- register ----------------

async def test_register_creates_user_and_returns_tokens(
    async_client: httpx.AsyncClient, reset_user_store
):
    r = await async_client.post(
        "/auth/register",
        json={
            "email": "alice@test.example.com",
            "password": "strong-pass-1234",
            "full_name": "Alice",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["access_token"] != body["refresh_token"]
    assert body["expires_in"] > 0


async def test_register_duplicate_email_returns_409(
    async_client: httpx.AsyncClient, reset_user_store
):
    payload = {"email": "dup@test.example.com", "password": "strong-pass-1234"}
    r1 = await async_client.post("/auth/register", json=payload)
    assert r1.status_code == 201
    r2 = await async_client.post("/auth/register", json=payload)
    assert r2.status_code == 409
    assert "zaten" in r2.json()["detail"].lower()


async def test_register_weak_password_rejected(
    async_client: httpx.AsyncClient, reset_user_store
):
    # password min_length=8 (models.py)
    r = await async_client.post(
        "/auth/register",
        json={"email": "weak@test.example.com", "password": "short"},
    )
    assert r.status_code == 422  # pydantic validation


# ---------------- login ----------------

async def test_login_with_valid_credentials(
    async_client: httpx.AsyncClient, reset_user_store
):
    await async_client.post(
        "/auth/register",
        json={"email": "bob@test.example.com", "password": "strong-pass-1234"},
    )
    r = await async_client.post(
        "/auth/login",
        json={"email": "bob@test.example.com", "password": "strong-pass-1234"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["access_token"]
    assert body["refresh_token"]


async def test_login_with_wrong_password_returns_401(
    async_client: httpx.AsyncClient, reset_user_store
):
    await async_client.post(
        "/auth/register",
        json={"email": "bob2@test.example.com", "password": "strong-pass-1234"},
    )
    r = await async_client.post(
        "/auth/login",
        json={"email": "bob2@test.example.com", "password": "WRONG-PASSWORD"},
    )
    assert r.status_code == 401


async def test_login_with_nonexistent_email_returns_401(
    async_client: httpx.AsyncClient, reset_user_store
):
    r = await async_client.post(
        "/auth/login",
        json={"email": "ghost@test.example.com", "password": "anything-12345"},
    )
    assert r.status_code == 401


# ---------------- me ----------------

async def test_me_returns_current_user(
    async_client: httpx.AsyncClient, reset_user_store
):
    reg = await async_client.post(
        "/auth/register",
        json={
            "email": "carol@test.example.com",
            "password": "strong-pass-1234",
            "full_name": "Carol",
        },
    )
    token = reg.json()["access_token"]

    r = await async_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == "carol@test.example.com"
    assert body["full_name"] == "Carol"
    assert body["role"] == "user"
    assert body["is_active"] is True


# ---------------- refresh ----------------

async def test_refresh_returns_new_token_pair_and_new_token_works(
    async_client: httpx.AsyncClient, reset_user_store
):
    reg = await async_client.post(
        "/auth/register",
        json={"email": "dave@test.example.com", "password": "strong-pass-1234"},
    )
    refresh_token = reg.json()["refresh_token"]
    old_access = reg.json()["access_token"]

    # /auth/refresh
    r = await async_client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert r.status_code == 200, r.text
    new_pair = r.json()
    assert new_pair["access_token"]
    assert new_pair["refresh_token"]
    # JTI farkli olmali — token degismis
    assert new_pair["access_token"] != old_access

    # Yeni access token ile /auth/me cagrisi gecmeli
    me = await async_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {new_pair['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["email"] == "dave@test.example.com"


async def test_refresh_with_invalid_token_returns_401(
    async_client: httpx.AsyncClient, reset_user_store
):
    r = await async_client.post(
        "/auth/refresh",
        json={"refresh_token": "this.is.not.a.valid.jwt.token"},
    )
    assert r.status_code == 401


async def test_refresh_with_access_token_type_rejected(
    async_client: httpx.AsyncClient, reset_user_store
):
    """Access token, refresh endpoint'inde kullanilamamali (type=access != refresh)."""
    reg = await async_client.post(
        "/auth/register",
        json={"email": "eve@test.example.com", "password": "strong-pass-1234"},
    )
    access = reg.json()["access_token"]

    r = await async_client.post(
        "/auth/refresh",
        json={"refresh_token": access},
    )
    assert r.status_code == 401


# ---------------- invalid token -> 401 ----------------

async def test_me_with_invalid_token_returns_401(
    async_client: httpx.AsyncClient, reset_user_store, monkeypatch
):
    # Dev mode bypass'i devre disi birak: API_KEYS dolu yap
    from config import settings
    monkeypatch.setattr(settings, "api_keys", ["valid-key-123"])
    monkeypatch.setattr(settings, "environment", "production")

    r = await async_client.get(
        "/auth/me",
        headers={"Authorization": "Bearer not-a-valid-jwt"},
    )
    assert r.status_code == 401


async def test_me_with_tampered_token_returns_401(
    async_client: httpx.AsyncClient, reset_user_store, monkeypatch
):
    from config import settings
    monkeypatch.setattr(settings, "api_keys", ["valid-key-123"])
    monkeypatch.setattr(settings, "environment", "production")

    reg = await async_client.post(
        "/auth/register",
        json={"email": "frank@test.example.com", "password": "strong-pass-1234"},
    )
    token = reg.json()["access_token"]
    # Son karakteri degistir -> imza bozulur
    tampered = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")

    r = await async_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {tampered}"},
    )
    assert r.status_code == 401


async def test_me_without_token_in_prod_mode_returns_401(
    async_client: httpx.AsyncClient, reset_user_store, monkeypatch
):
    from config import settings
    monkeypatch.setattr(settings, "api_keys", ["valid-key-123"])
    monkeypatch.setattr(settings, "environment", "production")

    r = await async_client.get("/auth/me")
    assert r.status_code == 401
