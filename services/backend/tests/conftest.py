"""
Pytest fixtures — backend testleri icin ML pipeline'i ve external bagimliliklari mockla.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import pytest


# Backend modullerini path'e ekle
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture(scope="session", autouse=True)
def _env_setup():
    """Test environment — DB ve external'lari devre disi birak."""
    os.environ["DATABASE_URL"] = "postgresql://invalid:invalid@invalid:5432/invalid"
    os.environ["REDIS_URL"] = "redis://invalid:6379/0"
    os.environ["S3_ENDPOINT"] = "http://invalid:9000"
    os.environ["API_KEYS"] = ""  # dev mode
    os.environ["ENVIRONMENT"] = "test"
    yield


@pytest.fixture(autouse=True)
def _mock_external(monkeypatch):
    """ML pipeline + storage + worker'i her testte mockla."""
    # ML pipeline
    from ml_service import ml_pipeline
    monkeypatch.setattr(ml_pipeline, "warm_up", lambda: None)
    monkeypatch.setattr(ml_pipeline, "is_loaded", lambda: True)

    fake_result = {
        "inspection_id": "test-id",
        "timestamp": "2026-05-14T00:00:00Z",
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
    monkeypatch.setattr(ml_pipeline, "analyze", lambda img, retries=2: dict(fake_result))

    # Storage — async upload'i bypass et
    async def fake_upload(content, key, content_type=None):
        return f"http://test-s3/{key}"

    monkeypatch.setattr("storage.upload_image", fake_upload)
    monkeypatch.setattr("main.upload_image", fake_upload)

    # Celery task — sahte .delay()
    task_mock = MagicMock()
    task_mock.delay = MagicMock(return_value=MagicMock(id="celery-task-id"))
    monkeypatch.setattr("main.run_inspection_task", task_mock)

    # DB init no-op
    monkeypatch.setattr("main.init_db", lambda: None)

    # auth.py + main.py icindeki DB probe'larini bypass et — her HTTP request'te
    # 2 saniyelik psycopg2 connect timeout yememek icin sahte 'DB unreachable'
    # cevabini hizla don. In-memory fallback'i tetikler.
    monkeypatch.setattr("auth._can_connect_db", lambda: False)
    monkeypatch.setattr("main._db_available", lambda: False)


@pytest.fixture
def client():
    """Sync TestClient — ASGI requests icin."""
    from fastapi.testclient import TestClient
    from main import app
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Async / httpx fixtures (yeni testler icin)
# ---------------------------------------------------------------------------

@pytest.fixture
async def async_client():
    """httpx AsyncClient — pytest-asyncio ile async testler icin.

    ASGITransport ile direkt FastAPI app'ine baglanir; network/port acmaz.
    """
    import httpx
    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def png_bytes() -> bytes:
    """Minimal gecerli 1x1 PNG — ML mock'landigi icin gercek decode yok."""
    import base64
    return base64.b64decode(
        b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
    )


@pytest.fixture
def reset_user_store():
    """In-memory user store'u her test arasinda temizle.

    auth modulundeki _memory_users module-level — test izolasyonu icin sifirla.
    """
    from auth import _memory_users
    _memory_users._by_id.clear()
    _memory_users._by_email.clear()
    yield
    _memory_users._by_id.clear()
    _memory_users._by_email.clear()


@pytest.fixture
def reset_inspection_store():
    """In-memory inspection store'u temizle."""
    from main import _memory_inspections
    _memory_inspections._store.clear()
    yield
    _memory_inspections._store.clear()


async def _register_and_login(client, email: str, password: str = "test-password-123",
                              full_name: str = "Test User") -> dict:
    """Yardimci: register -> TokenPair dondur."""
    r = await client.post(
        "/auth/register",
        json={"email": email, "password": password, "full_name": full_name},
    )
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
async def user_a_tokens(async_client, reset_user_store):
    """User A icin register edilmis TokenPair (access + refresh)."""
    return await _register_and_login(async_client, "user_a@test.example.com")


@pytest.fixture
async def user_b_tokens(async_client, reset_user_store):
    """User B — authorization testleri icin ikinci kullanici."""
    return await _register_and_login(async_client, "user_b@test.example.com")


@pytest.fixture
async def two_users(async_client, reset_user_store):
    """User A ve User B'yi paralel olarak register et — authorization icin."""
    a = await _register_and_login(async_client, "user_a@test.example.com")
    b = await _register_and_login(async_client, "user_b@test.example.com")
    return {"a": a, "b": b}
