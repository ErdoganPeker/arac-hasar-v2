"""
Gercek inference smoke test — docker stack ayakta ve ML weights yuklu olmali.

Bu test mock'lari devre disi birakir; gercek backend container'ina HTTP
istek atar, gercek YOLO pipeline'i kosturur, response schema'sini dogrular.

Calistirmak icin:
    INTEGRATION_DOCKER=1 docker exec hasarui-backend pytest \\
        tests/test_real_inference.py -v -m integration

CI'da default skip; INTEGRATION_DOCKER env yoksa atlanir.
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest


# Bu modulun tum testleri integration marker'i ile etiketlenir
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("INTEGRATION_DOCKER") != "1",
        reason="Real ML inference disabled (set INTEGRATION_DOCKER=1)",
    ),
]


BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")


def _candidate_fixture_dirs() -> list[Path]:
    """Container ve host'ta calisirken farkli path yapilari olabilir.

    Defensive: tum makul lokasyonlari sirayla dene.
    """
    here = Path(__file__).resolve()
    candidates: list[Path] = []
    # Host: services/backend/tests/ -> repo root = parents[3]
    # Container: /app/tests/ -> /app
    for n in (3, 2, 4, 5):
        try:
            base = here.parents[n]
        except IndexError:
            continue
        candidates.append(base / "tests" / "fixtures")
        candidates.append(base / "services" / "ml" / "quick_test_out")
        candidates.append(base / "fixtures")
    # Env override
    if os.environ.get("FIXTURE_DIR"):
        candidates.insert(0, Path(os.environ["FIXTURE_DIR"]))
    return candidates


def _find_sample_image() -> Path:
    """Repo'daki ilk arac fotografini dondur, yoksa skip."""
    for d in _candidate_fixture_dirs():
        if not d.exists():
            continue
        for ext in ("*.jpg", "*.jpeg", "*.png"):
            for p in sorted(d.glob(ext)):
                if p.stat().st_size > 1024:  # > 1KB gercek foto
                    return p
    pytest.skip("Sample image not found in repo fixtures (set FIXTURE_DIR env)")


@pytest.fixture(autouse=True)
def _disable_mocks(monkeypatch):
    """Bu modulde conftest mock'larini override etme — gercek backend'e HTTP atiyoruz."""
    # Hicbir sey yapma: conftest.py'daki monkeypatch'ler yalniz in-process
    # app icin gecerli. Burada httpx ile HARICI URL'e (BACKEND_URL) gidiyoruz,
    # bu yuzden mock'lar etkisiz.
    yield


@pytest.fixture
def real_client():
    """Gercek docker backend'ine baglanan httpx client."""
    with httpx.Client(base_url=BACKEND_URL, timeout=120.0) as c:
        # health check — backend ayakta mi?
        try:
            h = c.get("/health")
            if h.status_code != 200:
                pytest.skip(f"Backend health check failed: {h.status_code}")
        except httpx.RequestError as e:
            pytest.skip(f"Backend unreachable at {BACKEND_URL}: {e}")
        yield c


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_real(client: httpx.Client, email: str) -> str:
    """Gercek backend'de kullanici olustur, access_token dondur."""
    r = client.post(
        "/auth/register",
        json={"email": email, "password": "strong-pass-1234", "full_name": "Integration"},
    )
    if r.status_code == 409:
        # zaten kayitli — login dene
        r = client.post(
            "/auth/login",
            json={"email": email, "password": "strong-pass-1234"},
        )
    assert r.status_code in (200, 201), r.text
    return r.json()["access_token"]


def test_real_sync_inference_returns_valid_schema(real_client: httpx.Client):
    """Gercek bir arac fotografini /api/v1/inspect/sync'e yukle, response schema'sini dogrula."""
    img_path = _find_sample_image()
    token = _register_real(real_client, "integration-sync@test.example")

    with img_path.open("rb") as f:
        files = {"file": (img_path.name, f.read(), "image/jpeg")}

    r = real_client.post(
        "/api/v1/inspect/sync",
        files=files,
        headers=_bearer(token),
    )
    assert r.status_code == 200, r.text

    body = r.json()
    # Top-level schema kontrolu
    assert "inspection_id" in body
    assert "result" in body
    assert "processed_at" in body

    result = body["result"]
    assert "parts" in result, "result.parts[] missing"
    assert isinstance(result["parts"], list), "parts must be array"

    assert "summary" in result, "result.summary missing"
    summary = result["summary"]

    # Summary key'leri (ML mock'taki ile ayni anahtar seti)
    required_summary_keys = {
        "total_parts_inspected",
        "damaged_parts_count",
        "clean_parts_count",
        "total_damage_count",
        "total_cost_range_tl",
        "repair_recommendation",
        "estimated_repair_days",
    }
    missing = required_summary_keys - set(summary.keys())
    assert not missing, f"summary missing keys: {missing}"

    # Cost range tutarliligi
    cr = summary["total_cost_range_tl"]
    assert isinstance(cr, list) and len(cr) == 2
    assert cr[0] >= 0 and cr[1] >= cr[0]

    # Sayilar tutarli olmali
    total = summary["total_parts_inspected"]
    damaged = summary["damaged_parts_count"]
    clean = summary["clean_parts_count"]
    assert damaged + clean == total or total == 0


def test_real_inference_persists_to_db(real_client: httpx.Client):
    """Sync sonrasi GET /api/v1/inspect/{id} ile sonucu cekebilmeli."""
    img_path = _find_sample_image()
    token = _register_real(real_client, "integration-persist@test.example")

    with img_path.open("rb") as f:
        files = {"file": (img_path.name, f.read(), "image/jpeg")}

    r = real_client.post(
        "/api/v1/inspect/sync",
        files=files,
        headers=_bearer(token),
    )
    assert r.status_code == 200
    inspection_id = r.json()["inspection_id"]

    # GET ile geri al
    r2 = real_client.get(
        f"/api/v1/inspect/{inspection_id}",
        headers=_bearer(token),
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "completed"
    assert r2.json()["result"] is not None
