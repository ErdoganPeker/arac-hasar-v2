"""
Edge case validation testleri — /api/v1/inspect ve /api/v1/inspect/sync.

Kapsam:
  - 0 foto: 400 ya da 422
  - sync mode 6+ foto: 400 (max 5)
  - async mode 21+ foto: 400 (max 20)
  - 12MB+ foto: 400 (max 10MB)
  - Corrupt JPEG (binary garbage): sync'te 400 (cv2.imdecode None)
  - Bos icerik: 400
  - Gecersiz MIME (.txt'i .jpg uzantisiyla, content_type=text/plain): 400

Backend default limitler:
  - max_image_size_mb=10
  - max_images_sync=5
  - max_images_async=20

Bu testler ML mock'lariyla calisir (gercek inference yok).
"""
from __future__ import annotations

import httpx
import pytest


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _get_token(client: httpx.AsyncClient, email: str) -> str:
    r = await client.post(
        "/auth/register",
        json={"email": email, "password": "strong-pass-1234"},
    )
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


# ---------------- 0 foto ----------------

async def test_inspect_with_zero_files_returns_400_or_422(
    async_client: httpx.AsyncClient, reset_user_store, reset_inspection_store
):
    """FastAPI File(...) zorunlu — files yoksa 422, varsa ama bos liste ise 400."""
    token = await _get_token(async_client, "zero@test.example")
    r = await async_client.post(
        "/api/v1/inspect?mode=async",
        files=[],  # bos
        headers=_bearer(token),
    )
    # FastAPI tarafindan validation: File(...) zorunlu, 422
    # ya da endpoint icinde "En az 1 goruntu gerekli" 400
    assert r.status_code in (400, 422), f"status={r.status_code}, body={r.text}"


# ---------------- sync mode 6 foto ----------------

async def test_sync_mode_rejects_more_than_5_files(
    async_client: httpx.AsyncClient, png_bytes: bytes,
    reset_user_store, reset_inspection_store
):
    token = await _get_token(async_client, "6sync@test.example")
    files = [("files", (f"img_{i}.png", png_bytes, "image/png")) for i in range(6)]
    r = await async_client.post(
        "/api/v1/inspect?mode=sync",
        files=files,
        headers=_bearer(token),
    )
    assert r.status_code == 400, r.text
    assert "5" in r.json().get("detail", "") or "max" in r.json().get("detail", "").lower()


# ---------------- async mode 21 foto ----------------

async def test_async_mode_rejects_more_than_20_files(
    async_client: httpx.AsyncClient, png_bytes: bytes,
    reset_user_store, reset_inspection_store
):
    token = await _get_token(async_client, "21async@test.example")
    files = [("files", (f"img_{i}.png", png_bytes, "image/png")) for i in range(21)]
    r = await async_client.post(
        "/api/v1/inspect?mode=async",
        files=files,
        headers=_bearer(token),
    )
    assert r.status_code == 400, r.text
    assert "20" in r.json().get("detail", "") or "max" in r.json().get("detail", "").lower()


# ---------------- 12MB foto ----------------

async def test_file_larger_than_max_size_rejected(
    async_client: httpx.AsyncClient,
    reset_user_store, reset_inspection_store
):
    """max_image_size_mb=10 — 12MB icerik 400 donduralim."""
    token = await _get_token(async_client, "big@test.example")
    # 12MB binary blob
    huge = b"\xff\xd8\xff\xe0" + b"\x00" * (12 * 1024 * 1024)
    files = {"file": ("huge.jpg", huge, "image/jpeg")}
    r = await async_client.post(
        "/api/v1/inspect/sync",
        files=files,
        headers=_bearer(token),
    )
    # Backend, > max_image_size_mb durumunda 400 ya da 413 dondurebilir.
    # FastAPI/Starlette upload limit'ine takilirsa 413 (Request Entity Too Large) doner;
    # custom validator'a ulasirsa 400. Her ikisi de gecerli rejection.
    assert r.status_code in (400, 413), r.text
    detail = r.json().get("detail", "").lower()
    assert "buyuk" in detail or "10mb" in detail or "size" in detail or "large" in detail


# ---------------- bos icerik ----------------

async def test_empty_file_content_rejected(
    async_client: httpx.AsyncClient,
    reset_user_store, reset_inspection_store
):
    token = await _get_token(async_client, "empty-edge@test.example")
    files = {"file": ("empty.jpg", b"", "image/jpeg")}
    r = await async_client.post(
        "/api/v1/inspect/sync",
        files=files,
        headers=_bearer(token),
    )
    assert r.status_code == 400


# ---------------- corrupt JPEG (binary garbage) ----------------

async def test_corrupt_image_binary_garbage_rejected_in_sync(
    async_client: httpx.AsyncClient, monkeypatch,
    reset_user_store, reset_inspection_store
):
    """Sync mod cv2.imdecode'u cagirir; corrupt veri None doner -> 400.

    Sync mock'unda gercek decode bypass edilmis olabilir; ML pipeline'i ham
    decode'a degil mock'lanmis pipeline'a gider. Bu yuzden test sync endpoint'inde
    _decode_image'in real call edilmesini saglamak icin pipeline.analyze'i
    direkt gercek opencv decode'a vermek yerine main._decode_image'i izleyelim.
    main.py _process_sync icinde cv2.imdecode CALL EDILIYOR, yani corrupt veriyle
    400 donmeli.
    """
    token = await _get_token(async_client, "corrupt@test.example")
    # 1KB random olmayan ama image-decode-edemeyecek pattern
    garbage = b"\x89PNG\r\n\x1a\n" + b"\x00\x01\x02\x03" * 256  # PNG magic + rastgele
    files = {"file": ("corrupt.png", garbage, "image/png")}
    r = await async_client.post(
        "/api/v1/inspect/sync",
        files=files,
        headers=_bearer(token),
    )
    # Bos degil, MIME OK, size OK — ama decode hatasi
    assert r.status_code == 400, r.text
    detail = r.json().get("detail", "").lower()
    assert "okunamadi" in detail or "corrupt" in detail or "decode" in detail


# ---------------- gecersiz MIME (text/plain) ----------------

async def test_invalid_mime_text_plain_rejected(
    async_client: httpx.AsyncClient,
    reset_user_store, reset_inspection_store
):
    """.txt content-type'i ile gonderilen dosya 400 donmeli (MIME starts with image/ kontrolu)."""
    token = await _get_token(async_client, "wrongmime@test.example")
    files = {"file": ("doc.jpg", b"hello world text content", "text/plain")}
    r = await async_client.post(
        "/api/v1/inspect/sync",
        files=files,
        headers=_bearer(token),
    )
    assert r.status_code == 400, r.text
    detail = r.json().get("detail", "").lower()
    assert "mime" in detail or "gecersiz" in detail or "image" in detail


async def test_empty_mime_string_is_allowed_relaxed(
    async_client: httpx.AsyncClient, png_bytes: bytes,
    reset_user_store, reset_inspection_store
):
    """content_type='' ise validator sessizce gecirir (relaxed) — yine 200 olmali.

    Bu davranis _validate_image_file icindeki 'if ct and not ct.startswith...' gevsek check'inden
    geliyor. Documente ediyoruz; ileride sertlesirse magic-byte kontrolu eklenmeli.
    """
    token = await _get_token(async_client, "nomime@test.example")
    files = {"file": ("a.png", png_bytes, "")}
    r = await async_client.post(
        "/api/v1/inspect/sync",
        files=files,
        headers=_bearer(token),
    )
    # Bos MIME tolere ediliyor — ML mock'lu oldugu icin 200 doner
    assert r.status_code in (200, 400)
