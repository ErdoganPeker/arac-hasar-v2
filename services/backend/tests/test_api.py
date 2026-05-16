"""
Backend API testleri.

Coverage:
  - Health endpoint
  - Version endpoint
  - Auth: dev mode + (mocked) prod mode
  - Inspect sync (mock ML)
  - CORS preflight
  - 404/403 davranisi
"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient


# ---------------- Health & version ----------------

def test_health_ok(client: TestClient):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["ml_loaded"] is True
    assert "timestamp" in body
    assert "version" in body


def test_version_endpoint(client: TestClient):
    r = client.get("/api/v1/version")
    assert r.status_code == 200
    body = r.json()
    assert "version" in body
    assert "git_sha" in body
    assert "build_time" in body
    assert "environment" in body


# ---------------- Auth ----------------

def test_dev_mode_allows_no_api_key(client: TestClient):
    """API_KEYS bos => dev mode => key olmadan calismali."""
    r = client.get("/api/v1/inspect", params={"page": 1, "page_size": 10})
    # 200: list bos olabilir ama auth gecti
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert body["page"] == 1


def test_prod_mode_requires_api_key(client: TestClient, monkeypatch):
    """API_KEYS dolu => header olmadan 401."""
    from config import settings
    monkeypatch.setattr(settings, "api_keys", ["valid-key-123"])
    monkeypatch.setattr(settings, "environment", "production")

    r = client.get("/api/v1/inspect")
    assert r.status_code == 401
    assert "X-API-Key" in r.json()["detail"]


def test_prod_mode_invalid_api_key(client: TestClient, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "api_keys", ["valid-key-123"])
    monkeypatch.setattr(settings, "environment", "production")

    r = client.get("/api/v1/inspect", headers={"X-API-Key": "wrong"})
    assert r.status_code == 403


def test_prod_mode_valid_api_key(client: TestClient, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "api_keys", ["valid-key-123"])
    monkeypatch.setattr(settings, "environment", "production")

    r = client.get("/api/v1/inspect", headers={"X-API-Key": "valid-key-123"})
    assert r.status_code == 200


# ---------------- CORS ----------------

def test_cors_preflight_localhost_web(client: TestClient):
    """Next.js dev origin'inden preflight gecmeli."""
    r = client.options(
        "/api/v1/inspect",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-api-key,content-type",
        },
    )
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "POST" in r.headers.get("access-control-allow-methods", "")


def test_cors_preflight_tauri(client: TestClient):
    """Tauri desktop origin'i kabul edilmeli."""
    r = client.options(
        "/api/v1/inspect",
        headers={
            "Origin": "http://tauri.localhost",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-api-key",
        },
    )
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == "http://tauri.localhost"


def test_cors_preflight_vercel_regex(client: TestClient):
    """*.vercel.app origin'i regex ile kabul edilmeli."""
    r = client.options(
        "/api/v1/inspect",
        headers={
            "Origin": "https://my-app-abc123.vercel.app",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-api-key",
        },
    )
    assert r.status_code in (200, 204)
    assert "vercel.app" in (r.headers.get("access-control-allow-origin") or "")


# ---------------- Inspect ----------------

def _png_bytes() -> bytes:
    """Minimal gecerli 1x1 PNG."""
    import base64
    return base64.b64decode(
        b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )


def test_sync_single_inspection(client: TestClient):
    """Tek goruntu sync inspection — mock ML donduruyor."""
    img = _png_bytes()
    r = client.post(
        "/api/v1/inspect/sync",
        files={"file": ("test.png", img, "image/png")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "inspection_id" in body
    assert "result" in body
    assert body["result"]["summary"]["total_parts_inspected"] == 0


def test_sync_rejects_non_image(client: TestClient):
    """Image olmayan MIME tipi reddedilmeli."""
    r = client.post(
        "/api/v1/inspect/sync",
        files={"file": ("test.txt", b"not an image", "text/plain")},
    )
    assert r.status_code == 400


def test_inspect_404_for_missing(client: TestClient):
    r = client.get("/api/v1/inspect/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
    assert "bulunamadi" in r.json()["detail"].lower()


def test_inspect_async_mode_returns_202(client: TestClient):
    img = _png_bytes()
    r = client.post(
        "/api/v1/inspect?mode=async",
        files=[("files", ("test1.png", img, "image/png"))],
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "queued"
    assert body["status_url"].startswith("/api/v1/inspect/")
    assert "X-Inspection-Id" in r.headers
