"""
Health & version endpoint testleri (httpx AsyncClient ile).

Bu testler test_api.py'daki sync versiyonlarla cakismaz; httpx AsyncClient
yolunu (yeni Eklenen) ve ek alan dogrulamalarini kapsar.
"""
from __future__ import annotations

import re

import httpx
import pytest


# ---------------- /health ----------------

async def test_health_returns_200(async_client: httpx.AsyncClient):
    r = await async_client.get("/health")
    assert r.status_code == 200


async def test_health_body_schema(async_client: httpx.AsyncClient):
    r = await async_client.get("/health")
    body = r.json()
    # status
    assert body["status"] == "ok"
    # ml_loaded — conftest is_loaded()'i True'ya pinned
    assert body["ml_loaded"] is True
    # timestamp: ISO-8601 (suffix Z)
    assert "timestamp" in body
    assert isinstance(body["timestamp"], str)
    # version semver-like
    assert "version" in body
    assert body["version"]


async def test_health_legacy_healthz_alias(async_client: httpx.AsyncClient):
    """Geriye uyumluluk — /healthz da calismali."""
    r = await async_client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_health_has_request_id_header(async_client: httpx.AsyncClient):
    """Request-Id middleware her response'a X-Request-Id ekler."""
    r = await async_client.get("/health")
    assert r.status_code == 200
    rid = r.headers.get("X-Request-Id")
    assert rid
    # 32 hex char (uuid4().hex) veya client-provided
    assert len(rid) >= 8


async def test_health_propagates_request_id_when_provided(
    async_client: httpx.AsyncClient,
):
    custom = "trace-id-test-1234"
    r = await async_client.get("/health", headers={"X-Request-Id": custom})
    assert r.headers.get("X-Request-Id") == custom


# ---------------- /api/v1/version ----------------

async def test_version_returns_200(async_client: httpx.AsyncClient):
    r = await async_client.get("/api/v1/version")
    assert r.status_code == 200


async def test_version_body_schema(async_client: httpx.AsyncClient):
    r = await async_client.get("/api/v1/version")
    body = r.json()
    # Tum alanlar zorunlu (StrictModel)
    for field in ("version", "git_sha", "build_time", "environment"):
        assert field in body, f"version response missing {field}"
        assert isinstance(body[field], str)

    # version semver-benzeri (X.Y.Z)
    assert re.match(r"^\d+\.\d+", body["version"]), body["version"]

    # environment: test conftest'i 'test' ata; gercekte
    # 'development|staging|production|test' icinden biri olabilir
    assert body["environment"]


async def test_version_consistent_with_health(async_client: httpx.AsyncClient):
    """/health ve /api/v1/version ayni 'version' degerini donmeli."""
    h = (await async_client.get("/health")).json()
    v = (await async_client.get("/api/v1/version")).json()
    assert h["version"] == v["version"]
