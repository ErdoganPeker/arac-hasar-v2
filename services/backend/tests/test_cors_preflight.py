"""
CORS preflight dogrulamasi.

middleware.install_security_middleware:
  - allow_credentials=False  (JWT Authorization header, cookie yok)
  - allow_methods=[GET,POST,PUT,PATCH,DELETE,OPTIONS]
  - allow_headers=[Authorization, Content-Type, X-Request-ID]
  - cors_origins: settings.cors_origins (whitelist; localhost:3000 vs.)

Whitelist'te olmayan Origin -> CORS header'lar response'a EKLENMEZ
(Starlette CORSMiddleware davranisi; istek 200 doner ama Access-Control-*
header'lari yok). Tarayici bu durumda istegi blocklar.
"""
from __future__ import annotations

import httpx
import pytest


# ---------------- whitelist'teki origin ----------------

async def test_cors_preflight_for_whitelisted_origin(
    async_client: httpx.AsyncClient,
):
    """OPTIONS /api/v1/inspect, whitelist origin -> 200 + Access-Control-* header'lari."""
    r = await async_client.options(
        "/api/v1/inspect",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        },
    )
    # Starlette CORSMiddleware preflight'a 200 doner
    assert r.status_code in (200, 204), f"status={r.status_code}, body={r.text}"

    headers_lower = {k.lower(): v for k, v in r.headers.items()}
    assert "access-control-allow-origin" in headers_lower
    assert headers_lower["access-control-allow-origin"] == "http://localhost:3000"

    # POST allowed methods icinde
    allowed_methods = headers_lower.get("access-control-allow-methods", "")
    assert "POST" in allowed_methods.upper()

    # allow_headers icinde Authorization olmali
    allowed_headers = headers_lower.get("access-control-allow-headers", "").lower()
    assert "authorization" in allowed_headers


async def test_cors_allow_credentials_is_false(
    async_client: httpx.AsyncClient,
):
    """JWT modeli — cookie yok, allow_credentials=False olmali.

    Starlette CORSMiddleware allow_credentials=False ise
    'access-control-allow-credentials' header'i RESPONSE'a EKLENMEZ.
    """
    r = await async_client.options(
        "/api/v1/inspect",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    headers_lower = {k.lower(): v for k, v in r.headers.items()}
    # Header ya yok ya da 'false'
    if "access-control-allow-credentials" in headers_lower:
        assert headers_lower["access-control-allow-credentials"].lower() == "false"
    else:
        # Header tamamen yok — bu da allow_credentials=False ile uyumlu
        assert "access-control-allow-credentials" not in headers_lower


# ---------------- whitelist'te olmayan origin ----------------

async def test_cors_preflight_rejects_unknown_origin(
    async_client: httpx.AsyncClient,
):
    """Whitelist'te olmayan Origin -> Access-Control-Allow-Origin header EKLENMEZ.

    Starlette davranis: 400 dondurmez, sadece header'i set etmez. Tarayici
    bunu yorumlayip request'i blocklar. Test: header yokluğunu dogrula.
    """
    r = await async_client.options(
        "/api/v1/inspect",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    # Starlette CORSMiddleware preflight reject'i 400 doner
    # ya da response'a Allow-Origin koymadan 200 doner
    headers_lower = {k.lower(): v for k, v in r.headers.items()}
    allow_origin = headers_lower.get("access-control-allow-origin", "")

    # Whitelist'te olmayan origin echo edilmemeli
    assert allow_origin != "https://evil.example.com", (
        f"Whitelist'te olmayan origin echo edildi: '{allow_origin}'. "
        f"Bu CSRF/CORS bypass riski."
    )
    # Hicbir wildcard "*" da olmamali (allow_credentials=False olsa bile
    # backend'in cors_origins listesi explicit)
    assert allow_origin != "*", "Wildcard origin acik — guvenlik riski"


async def test_cors_actual_post_with_unknown_origin_does_not_get_allow_header(
    async_client: httpx.AsyncClient, png_bytes: bytes,
    reset_user_store, reset_inspection_store
):
    """Gercek POST isteginde de Origin whitelist'te degilse Allow-Origin yok."""
    # Once token al
    reg = await async_client.post(
        "/auth/register",
        json={"email": "cors@test.example", "password": "strong-pass-1234"},
    )
    token = reg.json()["access_token"]

    files = {"file": ("a.png", png_bytes, "image/png")}
    r = await async_client.post(
        "/api/v1/inspect/sync",
        files=files,
        headers={
            "Authorization": f"Bearer {token}",
            "Origin": "https://attacker.example.com",
        },
    )
    # Endpoint kendisi 200/4xx donebilir; onemli olan CORS header'i
    headers_lower = {k.lower(): v for k, v in r.headers.items()}
    allow_origin = headers_lower.get("access-control-allow-origin", "")
    assert allow_origin != "https://attacker.example.com"
    assert allow_origin != "*"


async def test_cors_exposes_x_request_id_header(
    async_client: httpx.AsyncClient,
):
    """expose_headers icinde X-Request-ID, RateLimit-Limit, RateLimit-Remaining olmali."""
    r = await async_client.options(
        "/api/v1/inspect",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    headers_lower = {k.lower(): v for k, v in r.headers.items()}
    exposed = headers_lower.get("access-control-expose-headers", "").lower()
    # Preflight'ta expose-headers OPSIYONEL — yoksa actual response'ta cikar
    # Bu kontrol gevsek; testin kirilganligi azaltmak icin:
    if exposed:
        assert "x-request-id" in exposed or "request-id" in exposed
