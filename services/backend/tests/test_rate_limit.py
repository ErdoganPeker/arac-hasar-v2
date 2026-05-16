"""
Rate limit dogrulamasi — /auth/login.

middleware.py'da slowapi.Limiter tanimli. Yorumda /auth/login icin
"5/minute, key_func=get_remote_address" oneriliyor. Bu test, 6'inci
basarisiz login isteginin 429 dondurup dondurmedigini DOGRULAR.

Onemli not: auth.py'deki @router.post("/login") fonksiyonunda
@limiter.limit("5/minute") decoratoru gercekten uygulanmis MI, bu test ile
ortaya cikiyor. Eger uygulanmadi ise test FAIL eder ve backend bug raporlanir.
"""
from __future__ import annotations

import httpx
import pytest


# ---------------- 6 basarisiz login -> 429 ----------------

async def test_login_rate_limit_after_5_failed_attempts(
    async_client: httpx.AsyncClient, reset_user_store
):
    """Ayni IP'den 6 basarisiz login -> 6'inci 429 olmali.

    slowapi default 'fixed-window' strategi; ayni IP'den (TestClient ic IP'si
    "testclient" sabit) 5'inci basarili gecer, 6'inci 429 olur.

    Eger /auth/login uzerinde @limiter.limit("5/minute") DECORATOR'u
    UYGULANMADI ise — bu test fail eder; bu durum middleware.py'daki
    yorumda onerilen rate-limit wire'in EKSIK oldugunu gosterir.
    """
    # Once kullanici olustur ki "kullanici yok" yerine "wrong password" 401'i tetiklenir
    await async_client.post(
        "/auth/register",
        json={"email": "rl@test.example", "password": "strong-pass-1234"},
    )

    statuses = []
    for i in range(6):
        r = await async_client.post(
            "/auth/login",
            json={"email": "rl@test.example", "password": "WRONG-PASSWORD"},
        )
        statuses.append(r.status_code)

    # Ilk 5'i 401 (gecersiz parola), 6'inci 429 (rate limit) bekleniyor
    # Eger rate-limit hic uygulanmadiysa hepsi 401 olur — bu kabul edilemez.
    assert 429 in statuses, (
        f"6 attempt sonrasi 429 (rate limit) bekleniyordu. "
        f"Aldigimiz status'ler: {statuses}. "
        f"Backend bug: /auth/login uzerinde @limiter.limit decorator EKSIK."
    )

    # Ilk 5 attempt 401 olmali (rate limit'e takilmadan)
    assert statuses[0] == 401
    # 6'inci 429
    assert statuses[5] == 429


async def test_login_rate_limit_response_has_retry_after_header(
    async_client: httpx.AsyncClient, reset_user_store
):
    """429 response'unun retry-after veya rate-limit header'i olmali (RFC + slowapi)."""
    await async_client.post(
        "/auth/register",
        json={"email": "rl2@test.example", "password": "strong-pass-1234"},
    )

    last_response = None
    for i in range(7):
        r = await async_client.post(
            "/auth/login",
            json={"email": "rl2@test.example", "password": "wrong"},
        )
        last_response = r
        if r.status_code == 429:
            break

    assert last_response is not None
    if last_response.status_code != 429:
        pytest.fail(
            f"Rate limit hic tetiklenmedi; son status={last_response.status_code}. "
            f"Backend bug: /auth/login @limiter.limit eksik."
        )

    # slowapi tipik header'lari
    headers_lower = {k.lower(): v for k, v in last_response.headers.items()}
    has_retry = "retry-after" in headers_lower
    has_rl = any(k.startswith("ratelimit-") or k.startswith("x-ratelimit-") for k in headers_lower)
    assert has_retry or has_rl, (
        f"429 response'unda Retry-After veya RateLimit-* header'i yok. "
        f"Headers: {dict(last_response.headers)}"
    )
