# Backend Testleri

E2E pytest test suite — FastAPI + httpx AsyncClient + ML mock.

## Kapsam

| Dosya | Senaryolar |
|---|---|
| `test_api.py` | Health, version, CORS, dev/prod auth, sync inspect (mevcut) |
| `test_health.py` | `/health`, `/healthz`, `/api/v1/version` (httpx async + sema) |
| `test_auth_flow.py` | register -> login -> me -> refresh -> me (yeni token) -> invalid token -> 401 |
| `test_inspect_sync.py` | `/api/v1/inspect/sync` + `/api/v1/inspect?mode=sync` sema + reject senaryolar |
| `test_inspect_async.py` | `mode=async` -> 202 + status transitions (queued/processing/completed) + 20+ image reddi |
| `test_authorization.py` | User A inspection -> User B GET/DELETE -> 403/404; list isolation |
| `test_visualization.py` | `/visualization/{annotated|parts|damages}` 302 redirect, fallback presign, 404 |

## Calistirma

Backend dizinine `cd` edip:

```bash
cd services/backend
pytest tests/
```

Ya da root'tan:

```bash
pytest services/backend/tests/
```

Belirli bir dosya:

```bash
pytest services/backend/tests/test_auth_flow.py -v
```

Coverage:

```bash
pytest services/backend/tests/ --cov=services/backend --cov-report=term-missing
```

## Bagimliliklar

`services/backend/requirements.txt`:

- `pytest>=8.0`
- `pytest-asyncio>=0.23`  (mode=auto)
- `httpx>=0.27`

Yukle:

```bash
pip install -r services/backend/requirements.txt
```

## Mock Stratejisi

`tests/conftest.py` her testte autouse olarak:

- **ML pipeline**: `ml_pipeline.analyze()` sabit JSON doner (YOLO calismaz)
- **Storage**: `upload_image()` async no-op, fake URL doner
- **Worker**: `run_inspection_task.delay()` MagicMock — Redis/Celery gerek yok
- **DB**: `init_db()` no-op + invalid `DATABASE_URL` -> in-memory fallback (auth.py + main.py)

## Notlar

- Test'ler **Docker gerektirmez** — Postgres/Redis/MinIO baglantisi otomatik bypass edilir
- `pytest.ini`: `asyncio_mode = auto` -> `async def` test fonksiyonlari otomatik calisir
- In-memory user/inspection store'lar `reset_user_store` / `reset_inspection_store` fixture'lari ile her test arasinda sifirlanir
