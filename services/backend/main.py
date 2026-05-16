"""
backend/main.py
FastAPI ana uygulama — multi-platform (web + mobile + desktop) hasar tespit API'si.

Endpoint listesi:
  GET    /health                                              - Basit health check
  GET    /api/v1/version                                      - Versiyon + git sha
  GET    /api/v1/models                                       - Kullanilabilir modeller (custom + pretrained)
  POST   /api/v1/inspect?mode=sync|async&model=<id>           - Coklu goruntu hasar tespiti
  POST   /api/v1/inspect/sync?model=<id>                      - Tek goruntu hizli (on-device once kullan)
  GET    /api/v1/inspect/{id}                                 - Durum + sonuc
  GET    /api/v1/inspect/{id}/visualization/{type}            - Annotated/parts/damages PNG redirect
  GET    /api/v1/inspect                                      - Liste (paginated)
  DELETE /api/v1/inspect/{id}                                 - Sil
  WS     /api/v1/inspect/{id}/stream                          - Realtime status

Calistirma:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

import asyncio
import logging
import math
import uuid
from datetime import datetime, timezone
from typing import List, Literal, Optional

import cv2
import numpy as np
from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from auth import AuthContext, require_api_key, router as auth_router
from config import settings
from middleware import install_security_middleware, limiter
# NOT: services/backend/database.py SQLAlchemy async engine'ine tasindi
# (Database Optimizer ajaninin domain'i). db_models.py icindeki Inspection
# ORM modeli henuz hazir degil — bu modulun alt kisminda inline minimal repo
# (psycopg2 raw SQL + idempotent CREATE TABLE + in-memory fallback) yer
# aliyor. ORM hazir oldugunda asagidaki _InspectionRepo, ORM session'ina
# migrate edilir; endpoint imzalari degismez.
from models import (
    ApiError,
    HealthResponse,
    InspectionCreateResponse,
    InspectionListItem,
    InspectionListResponse,
    InspectionStatusResponse,
    SyncInspectionResponse,
    VersionResponse,
)
from ml_service import (
    DEFAULT_MODEL_ID,
    check_model_files_available,
    is_known_model_id,
    list_available_models,
    ml_pipeline,
    resolve_model_id,
)
from storage import get_presigned_url, upload_image
from ws import stream_inspection
from worker import run_inspection_task


# ---------------- Logging ----------------

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
logger = logging.getLogger("backend")


# ---------------- Inspections repo (inline; pilot interim) ----------------
#
# Database Optimizer'in db_models.py + Inspection ORM modeli hazirlandiginda
# bu blok ORM session'ina migrate edilir. O ana kadar psycopg2 raw SQL +
# idempotent schema + in-memory fallback ile calisir; ayni Postgres'i kullanir
# (DATABASE_URL).

import json as _json
import threading as _threading

try:
    import psycopg2 as _psycopg2
    from psycopg2.extras import RealDictCursor as _RealDictCursor
except ImportError:  # pragma: no cover
    _psycopg2 = None  # type: ignore[assignment]
    _RealDictCursor = None  # type: ignore[assignment]


_INSPECTIONS_SCHEMA_SQL = """
-- NOT: Alembic migration 0001_initial 'inspections' tablosunu ORM semasiyla
-- yarattigi icin (user_id UUID FK, image_count INT, error_msg TEXT, no
-- legacy result/image_urls/client_id columns), bu CREATE TABLE artik bos
-- DB'de calismaz — kendi semayi yaratmiyoruz. Bunun yerine ORM tablosunu
-- raw repo'nun ihtiyaclarini karsilayacak sekilde ALTER ile genisletiyoruz.
-- Tum eklemeler IF NOT EXISTS (PG 9.6+) ile idempotent.

-- Backwards-compat: ORM tablosu yoksa minimal sema. Production'da Alembic'in
-- yarattigi tabloyla cakismaz (ORM zaten daha kapsamli).
CREATE TABLE IF NOT EXISTS inspections (
    id UUID PRIMARY KEY,
    client_id TEXT,
    status TEXT NOT NULL,
    image_urls JSONB,
    result JSONB,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ORM-onlu tabloya raw repo'nun bekledigi legacy kolonlari ekle. PostgreSQL
-- 9.6+ IF NOT EXISTS destekler; mevcut kolonlara dokunmaz.
ALTER TABLE inspections ADD COLUMN IF NOT EXISTS client_id TEXT;
ALTER TABLE inspections ADD COLUMN IF NOT EXISTS image_urls JSONB;
ALTER TABLE inspections ADD COLUMN IF NOT EXISTS result JSONB;
ALTER TABLE inspections ADD COLUMN IF NOT EXISTS error TEXT;
ALTER TABLE inspections ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
-- Inspection tablosunun NOT NULL user_id FK constraint'i raw INSERT'leri
-- engelliyor (Alembic ORM tablosunda user_id NOT NULL). Raw repo henuz
-- user_id'yi UUID olarak yazamiyor — gecici olarak NOT NULL gevsetiliyor.
ALTER TABLE inspections ALTER COLUMN user_id DROP NOT NULL;
-- image_count NOT NULL default 0 olduguna gore raw INSERT etkilenmez.

CREATE INDEX IF NOT EXISTS idx_inspections_client_created
    ON inspections (client_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_inspections_legacy_status ON inspections (status);
"""


def _pg_connect():
    if _psycopg2 is None:
        raise RuntimeError("psycopg2 yuklu degil")
    return _psycopg2.connect(settings.database_url, connect_timeout=3)


_db_available_cache: Optional[bool] = None
_db_check_lock = _threading.Lock()


def _db_available() -> bool:
    global _db_available_cache
    if _db_available_cache is not None:
        return _db_available_cache
    with _db_check_lock:
        if _db_available_cache is not None:
            return _db_available_cache
        try:
            with _pg_connect() as _:
                _db_available_cache = True
        except Exception as e:
            logger.warning("DB erisilemiyor, in-memory fallback aktif: %s", e)
            _db_available_cache = False
        return _db_available_cache


_schema_inited = False


def init_db() -> None:
    """Inspections tablosu yoksa olustur. Idempotent.

    Iki adimda calisir: (1) DDL transaction icinde CREATE/ALTER TABLE; (2)
    enum genisletme ayri autocommit baglantida cunku PG 12+ `ALTER TYPE ADD
    VALUE` islemi transaction icinde calismaz.
    """
    global _schema_inited
    if _schema_inited:
        return
    if not _db_available():
        _schema_inited = True
        return
    try:
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_INSPECTIONS_SCHEMA_SQL)
            conn.commit()
        # Enum genisletme: ORM enum 'pending|processing|done|failed' tanimliyor,
        # raw repo 'queued|completed' kullaniyor. Legacy degerleri enum'a ekleyip
        # iki katmani da calisir tutuyoruz. ALTER TYPE ADD VALUE transaction
        # disinda olmali (PG kisiti).
        _enum_legacy_values = [
            ("inspection_status", "queued"),
            ("inspection_status", "completed"),
        ]
        conn = _pg_connect()
        try:
            conn.set_session(autocommit=True)
            with conn.cursor() as cur:
                for type_name, value in _enum_legacy_values:
                    cur.execute(
                        f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS %s",
                        (value,),
                    )
        finally:
            conn.close()
        _schema_inited = True
        logger.info("Inspections schema hazir.")
    except Exception as e:
        logger.warning("inspections schema bootstrap basarisiz: %s", e)


# --- In-memory fallback (dev / DB down senaryosu) ---

class _MemoryStore:
    def __init__(self) -> None:
        self._store: dict[str, dict] = {}
        self._lock = _threading.Lock()

    def get(self, key: str) -> Optional[dict]:
        return self._store.get(key)

    def list(self, client_id: str, limit: int = 20, offset: int = 0):
        items = [v for v in self._store.values() if v["client_id"] == client_id]
        items.sort(key=lambda x: x["created_at"], reverse=True)
        return items[offset:offset + limit]

    def count(self, client_id: str) -> int:
        return sum(1 for v in self._store.values() if v["client_id"] == client_id)

    def save(self, row: dict) -> None:
        with self._lock:
            self._store[row["id"]] = row

    def update(self, key: str, fields: dict) -> None:
        with self._lock:
            if key in self._store:
                self._store[key].update(fields)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)


_memory_inspections = _MemoryStore()


class _PgInspectionsAdapter:
    """psycopg2 raw SQL adapter. ORM hazirlandiginda ORM session'a degistirilir."""

    def get(self, inspection_id: str) -> Optional[dict]:
        with _pg_connect() as conn:
            with conn.cursor(cursor_factory=_RealDictCursor) as cur:
                cur.execute("SELECT * FROM inspections WHERE id = %s", (inspection_id,))
                row = cur.fetchone()
        return _normalize_inspection_row(row)

    def list(self, client_id: str, limit: int = 20, offset: int = 0):
        # NOT: image_urls JSONB legacy kolonu — history listesinde thumbnail
        # icin kullaniliyor. ORM Inspection.images relation hazirlandiginda
        # JOIN ile ilk siradaki s3_key cekilir; o zamana kadar inline
        # image_urls listesinden ilk URL alinir.
        with _pg_connect() as conn:
            with conn.cursor(cursor_factory=_RealDictCursor) as cur:
                cur.execute(
                    """SELECT id, status, created_at, completed_at, result, image_urls
                       FROM inspections
                       WHERE client_id = %s
                       ORDER BY created_at DESC
                       LIMIT %s OFFSET %s""",
                    (client_id, limit, offset),
                )
                rows = cur.fetchall()
        return [_normalize_inspection_row(r) for r in rows]

    def count(self, client_id: str) -> int:
        with _pg_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT COUNT(*) FROM inspections WHERE client_id = %s",
                    (client_id,),
                )
                return cur.fetchone()[0]


def _normalize_inspection_row(row):
    if not row:
        return None
    row = dict(row)
    for k in ("created_at", "completed_at", "updated_at"):
        v = row.get(k)
        if hasattr(v, "isoformat"):
            row[k] = v.isoformat()
    # postgres jsonb -> python dict; raw stored str ise yukle
    for k in ("result", "image_urls"):
        v = row.get(k)
        if isinstance(v, str):
            try:
                row[k] = _json.loads(v)
            except Exception:
                pass
    return row


def get_db():
    """Inspections DB adapter dondur. DB yoksa in-memory."""
    return _PgInspectionsAdapter() if _db_available() else _memory_inspections


def save_inspection(
    inspection_id: str,
    client_id: str,
    status: str,
    image_urls: list,
    result: Optional[dict] = None,
    error: Optional[str] = None,
) -> None:
    """Yeni inspection kaydet."""
    now_iso = datetime.utcnow().isoformat() + "Z"
    if not _db_available():
        _memory_inspections.save({
            "id": inspection_id,
            "client_id": client_id,
            "status": status,
            "image_urls": image_urls,
            "result": result,
            "error": error,
            "created_at": now_iso,
        })
        return

    init_db()
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO inspections (id, client_id, status, image_urls, result, error)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    inspection_id, client_id, status,
                    _json.dumps(image_urls),
                    _json.dumps(result) if result is not None else None,
                    error,
                ),
            )
        conn.commit()


def update_inspection(inspection_id: str, **fields) -> None:
    if not fields:
        return
    if not _db_available():
        _memory_inspections.update(inspection_id, fields)
        return
    sets = []
    values: list = []
    # JSONB sutunlar — psycopg2 dict adapt edemiyor, manuel json-dump.
    _JSONB_COLS = {"result", "image_urls", "model_versions", "metadata"}
    for k, v in fields.items():
        if k in _JSONB_COLS:
            v = _json.dumps(v) if v is not None else None
        sets.append(f"{k} = %s")
        values.append(v)
    sets.append("updated_at = NOW()")
    values.append(inspection_id)
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE inspections SET {', '.join(sets)} WHERE id = %s",
                values,
            )
        conn.commit()


def delete_inspection(inspection_id: str) -> None:
    if not _db_available():
        _memory_inspections.delete(inspection_id)
        return
    with _pg_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM inspections WHERE id = %s", (inspection_id,))
        conn.commit()


# ---------------- FastAPI app ----------------

app = FastAPI(
    title="Arac Hasar Tespit API",
    description=(
        "Arac hasar tespiti, parca segmentasyonu, siddet ve maliyet tahmini. "
        "Web (Next.js), Mobile (Expo/React Native) ve Desktop (Tauri) icin "
        "ortak REST + WebSocket API."
    ),
    version=settings.api_version,
    contact={"name": "arac-hasar-v2", "email": "weblineet@gmail.com"},
    openapi_tags=[
        {"name": "health", "description": "Saglik ve versiyon"},
        {"name": "auth", "description": "Kimlik dogrulama / kullanici"},
        {"name": "inspect", "description": "Hasar inceleme islemleri"},
        {"name": "stream", "description": "Realtime WebSocket"},
    ],
)


# ---------------- Routers ----------------

app.include_router(auth_router)


# ---------------- Security middleware stack ----------------
# Replaces the previous ad-hoc CORS + request-id wiring.
# Installs (request path order): CORS -> SecurityHeaders -> AccessLog -> RequestID.
# Owned by middleware.py — see that file for CSP/HSTS/rate-limit policy.

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
install_security_middleware(app, cors_origins=settings.cors_origins)
# GZip: 12-foto inspection result ~400KB polygon-heavy JSON. Browser/mobile
# clients Accept-Encoding: gzip yolluyor; >1KB payload'lari sikistir.
# CORS + RequestID + SecurityHeaders zincirinin ALTINDA olsun ki sikistirilmis
# yanitta da rid/headers gorunsun (Starlette middleware ekleme sirasi LIFO).
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)


# ---------------- Hata gosterimi ----------------

def _utc_iso() -> str:
    """RFC 3339, timezone-aware UTC ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """ApiError sozlesmesine uygun JSON donus + request_id logu."""
    rid = getattr(request.state, "request_id", None)
    if exc.status_code >= 500:
        logger.error("HTTPException %s rid=%s path=%s detail=%s",
                     exc.status_code, rid, request.url.path, exc.detail)
    else:
        logger.info("HTTPException %s rid=%s path=%s detail=%s",
                    exc.status_code, rid, request.url.path, exc.detail)
    payload = ApiError(detail=str(exc.detail))
    headers = getattr(exc, "headers", None) or {}
    return JSONResponse(
        status_code=exc.status_code,
        content=payload.model_dump(exclude_none=True),
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """422 hatalarini ApiError sozlesmesine uydur — field path + ilk hata mesaji."""
    errors = exc.errors() or []
    if errors:
        first = errors[0]
        loc = ".".join(str(p) for p in first.get("loc", []))
        msg = first.get("msg", "Gecersiz istek")
        detail = f"{loc}: {msg}" if loc else msg
        code = first.get("type")
    else:
        detail = "Gecersiz istek"
        code = None
    rid = getattr(request.state, "request_id", None)
    logger.info("422 rid=%s path=%s detail=%s", rid, request.url.path, detail)
    payload = ApiError(detail=detail, code=code)
    return JSONResponse(status_code=422, content=payload.model_dump(exclude_none=True))


# ---------------- Startup / Shutdown ----------------

@app.on_event("startup")
async def on_startup():
    logger.info("Sunucu baslatildi — startup (lazy ML mode)")
    # DB init: idempotent CREATE/ALTER; connection acilir/kapanir, RAM tutmaz.
    # Async engine (database.py) ise lazy: ilk get_db() cagrisinda baglanir.
    try:
        init_db()
    except Exception as e:
        logger.warning(f"DB init basarisiz, mock mode olabilir: {e}")
    # ML warmup: 512MB Render free icin default OFF (config.ml_warmup_on_startup).
    # Ilk /api/v1/inspect cagrisinda ml_service.MLPipeline.analyze() lazy
    # warm_up() tetikleyecek (~5-10sn cold start; sonraki istekler hizli).
    # Eager warmup istenirse env: ML_WARMUP_ON_STARTUP=1 (dev/GPU host).
    if settings.ml_warmup_on_startup:
        try:
            ml_pipeline.warm_up()
        except Exception as e:
            logger.warning(f"ML warm-up basarisiz, lazy mode: {e}")
    else:
        logger.info("ML warmup atlandi (ml_warmup_on_startup=False, lazy)")
    # S3 bucket bootstrap — yok ise olustur (dev MinIO icin yararli)
    try:
        from storage import ensure_bucket
        ensure_bucket()
    except Exception as e:
        logger.warning(f"S3 bucket bootstrap atlandi: {e}")
    if settings.dev_mode:
        logger.warning("DEV MODE: API_KEYS bos ve environment=development")
    # OpenAPI JSON'i diske yaz — sadece development'ta (production'da CI yapsin,
    # boot'ta openapi() schema build'i ~40MB heap allocation pinler).
    if not settings.is_production:
        try:
            _export_openapi()
        except Exception as e:
            logger.warning(f"OpenAPI export basarisiz: {e}")
    logger.info("Hazir.")


@app.on_event("shutdown")
async def on_shutdown():
    logger.info("Sunucu kapaniyor.")


# Request-Id middleware is now provided by install_security_middleware
# (middleware.RequestIDMiddleware). Old inline middleware removed.


# ---------------- OpenAPI export ----------------

def _export_openapi() -> None:
    """OpenAPI JSON'u services/backend/openapi.json'a yaz.
    Frontend ajanlari (web/mobile/desktop) bu dosyadan tip uretebilir.
    """
    import json
    from pathlib import Path
    out = Path(__file__).parent / "openapi.json"
    spec = app.openapi()
    out.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("OpenAPI JSON yazildi: %s (%d endpoint)", out, len(spec.get("paths", {})))


# ---------------- Health & version ----------------

@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["health"],
    summary="Saglik kontrolu",
)
async def health():
    return HealthResponse(
        status="ok",
        ml_loaded=ml_pipeline.is_loaded(),
        timestamp=datetime.utcnow().isoformat() + "Z",
        version=settings.api_version,
    )


# Geriye uyumluluk: eski path
@app.get("/healthz", response_model=HealthResponse, include_in_schema=False)
async def healthz_legacy():
    return await health()


@app.get(
    "/api/v1/version",
    response_model=VersionResponse,
    tags=["health"],
    summary="Versiyon bilgisi",
)
async def version_info():
    return VersionResponse(
        version=settings.api_version,
        git_sha=settings.git_sha,
        build_time=settings.build_time,
        environment=settings.environment,
    )


# ---------------- Model registry ----------------

@app.get(
    "/api/v1/models",
    tags=["inspect"],
    summary="Kullanilabilir modeller (custom + pretrained)",
    responses={
        200: {
            "description": "Model listesi",
            "content": {
                "application/json": {
                    "example": {
                        "models": [
                            {
                                "id": "custom",
                                "name": "Kendi Modellerim",
                                "description": "CarDD finetune pipeline (damage+parts+severity).",
                                "source": "custom",
                                "classes_count": 0,
                                "license": "proprietary",
                                "is_custom": True,
                                "available": True,
                                "loaded": True,
                                "kind": "custom",
                                "entries": [],
                            },
                            {
                                "id": "pretrained_roboflow_cardd",
                                "name": "Pre-trained: Roboflow CarDD Pipeline",
                                "description": "Roboflow Universe public modelleri.",
                                "source": "roboflow",
                                "classes_count": 15,
                                "license": "CC-BY-4.0",
                                "is_custom": False,
                                "available": True,
                                "loaded": False,
                                "kind": "pretrained",
                                "entries": [
                                    {
                                        "id": "roboflow_cardd_scratch_dent",
                                        "name": "Roboflow Car Scratch & Dent",
                                        "license": "CC-BY-4.0",
                                        "classes": ["scratch", "dent"],
                                        "source": "roboflow",
                                    }
                                ],
                            },
                        ],
                        "default": "custom",
                    }
                }
            },
        },
    },
)
async def list_models(auth: AuthContext = Depends(require_api_key)):
    """Frontend model-selector dropdown'i icin kaynak listesi.

    Auth gerektirir (API key veya bearer). Custom + pre-trained registry'den
    derlenmis tum kaynaklar donulur. `is_custom=True` olan tek bir kayit hep
    bulunur — fallback varsayilandir.
    """
    models = list_available_models()
    return JSONResponse(
        status_code=200,
        content={
            "models": models,
            "default": DEFAULT_MODEL_ID,
            "count": len(models),
        },
    )


# ---------------- Admin: ML lifecycle ----------------

@app.post(
    "/api/v1/admin/ml/unload",
    tags=["inspect"],
    summary="ML pipeline bellegi serbest birak (admin only)",
    responses={
        200: {
            "description": "Unload tamamlandi",
            "content": {
                "application/json": {
                    "example": {
                        "unloaded": True,
                        "before_rss_mb": 1480.0,
                        "after_rss_mb": 410.5,
                        "freed_mb": 1069.5,
                        "rss_mb": 410.5,
                    }
                }
            },
        },
        401: {"model": ApiError},
        403: {"model": ApiError, "description": "Admin yetkisi gerekli"},
    },
)
async def admin_ml_unload(auth: AuthContext = Depends(require_api_key)):
    """ML pipeline'i bellekten dusur — demo/pilot sonrasi RAM toparlama.

    Render free 512MB profili icin: bir inceleme batch'i bittikten sonra
    bu endpoint cagrildiginda pipeline + model agirliklari unload edilir,
    RSS baseline'a (~150MB) doner. Sonraki /inspect cagrisi cold-load yapar
    (~5-10sn extra latency).

    Yetki: role=admin (dev_mode bypass haric).
    """
    if not (getattr(auth, "is_dev", False) or (getattr(auth, "role", "user") == "admin")):
        raise HTTPException(status_code=403, detail="Admin yetkisi gerekli")
    try:
        # Local import — circular avoidance + boot-time RAM
        from ml_service import _rss_mb as rss_mb  # noqa: WPS433
        stats = ml_pipeline.unload()
        stats["rss_mb"] = rss_mb()
        logger.info("admin ml unload: %s", stats)
        return JSONResponse(status_code=200, content=stats)
    except Exception as e:  # noqa: BLE001
        logger.exception("admin ml unload hatasi: %s", e)
        raise HTTPException(status_code=500, detail=f"Unload basarisiz: {e}")


# ---------------- Yardimcilar ----------------

def _sniff_image_format(content: bytes) -> Optional[str]:
    """Magic-byte tabanli format tespiti. Sadece header'a guvenme.

    Frontend Content-Type spoofing yapabilir; gercek bytes sniff edilir.
    """
    if len(content) < 12:
        return None
    # JPEG: FF D8 FF
    if content[:3] == b"\xff\xd8\xff":
        return "jpeg"
    # PNG: 89 50 4E 47 0D 0A 1A 0A
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    # WEBP: "RIFF....WEBP"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    # GIF (87a / 89a) — ML tarafi desteklemiyor olabilir ama yine de tanin
    if content[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    # HEIC/HEIF: "....ftypheic" veya benzeri
    if content[4:8] == b"ftyp" and content[8:12] in (
        b"heic", b"heix", b"hevc", b"heim", b"heis", b"hevm", b"hevs", b"mif1",
    ):
        return "heic"
    return None


_SUPPORTED_IMAGE_FORMATS = {"jpeg", "png", "webp"}


def _validate_image_file(file: UploadFile, content: bytes, index: int):
    max_bytes = settings.max_image_size_mb * 1024 * 1024
    if not content:
        raise HTTPException(status_code=400, detail=f"Goruntu {index} bos")
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Goruntu {index} cok buyuk (>{settings.max_image_size_mb}MB)",
        )
    # MIME sanity check
    ct = (file.content_type or "").lower()
    if ct and not (ct.startswith("image/") or ct == "application/octet-stream"):
        raise HTTPException(
            status_code=400,
            detail=f"Goruntu {index} gecersiz MIME tipi: {ct}",
        )
    # Magic byte content validation — header degil bytes
    fmt = _sniff_image_format(content)
    if fmt is None:
        raise HTTPException(
            status_code=400,
            detail=f"Goruntu {index} tanimlanamayan format (jpg/png/webp bekleniyor)",
        )
    if fmt not in _SUPPORTED_IMAGE_FORMATS:
        raise HTTPException(
            status_code=415,
            detail=f"Goruntu {index} desteklenmeyen format: {fmt} (jpg/png/webp bekleniyor)",
        )


async def _store_upload(file: UploadFile, inspection_id: str, index: int) -> tuple[bytes, str]:
    content = await file.read()
    _validate_image_file(file, content, index)
    safe_name = (file.filename or f"image_{index}").replace("/", "_").replace("\\", "_")
    key = f"inspections/{inspection_id}/img_{index}_{safe_name}"
    # Pilot/HF Spaces fallback: S3 provider (B2) yazma fail olursa ML sonucu
    # yine dondur; image kaydetme zorunlu degil. Visualization endpoint'i
    # bu durumda image bulamaz ama core hasar tespiti calismaya devam eder.
    import os as _os
    if _os.getenv("STORAGE_OPTIONAL", "0") == "1":
        try:
            url = await upload_image(content, key, content_type=file.content_type)
        except Exception as exc:  # noqa: BLE001
            logger.warning("S3 upload atlandi (STORAGE_OPTIONAL=1) key=%s err=%s", key, exc)
            url = f"local://skipped/{key}"
    else:
        url = await upload_image(content, key, content_type=file.content_type)
    return content, url


def _decode_image(content: bytes, index: int) -> np.ndarray:
    nparr = np.frombuffer(content, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail=f"Goruntu {index} okunamadi (corrupt veya desteklenmeyen format)")
    return img


# ---------------- Inspect endpoints ----------------

@app.post(
    "/api/v1/inspect",
    response_model=None,  # union — manuel
    responses={
        202: {"model": InspectionCreateResponse, "description": "Async kuyruga alindi"},
        200: {"model": SyncInspectionResponse, "description": "Sync tamamlandi"},
        400: {"model": ApiError},
        401: {"model": ApiError},
        403: {"model": ApiError},
        429: {"model": ApiError, "description": "Rate limit asildi"},
    },
    tags=["inspect"],
    summary="Coklu goruntu hasar tespiti",
)
# Rate limit: sync agir (GPU bound + max 5 foto), async kuyruga atilir +
# max 20 foto. Mod runtime'da bilindigi icin once en kati esikle kapiyi
# acmak gerek; sync icin etkili olan asil limit /api/v1/inspect/sync uzerindeki
# 10/minute decoratoru. Bu endpoint hem sync hem async kapidigi icin
# 10/minute ile her iki yolu da koruruz. user_or_ip_key (middleware default)
# ile tenant fairness.
@limiter.limit("10/minute")
async def create_inspection(
    request: Request,
    files: List[UploadFile] = File(..., description="1+ goruntu (jpg/png)"),
    mode: Literal["sync", "async"] = Query("async", description="Calisma modu"),
    model: str = Query(
        DEFAULT_MODEL_ID,
        description=(
            "Model kaynak id'si — 'custom' (default, kendi eğitilmiş "
            "modellerimiz) veya pre-trained: "
            "'pretrained_ultralytics_yolo11m', 'pretrained_roboflow_cardd', "
            "'pretrained_hybrid'. Tum liste: GET /api/v1/models"
        ),
    ),
    auth: AuthContext = Depends(require_api_key),
):
    """Cok goruntulu hasar tespiti.

    - **mode=sync**: Max 5 goruntu, sonuc hemen doner.
    - **mode=async**: Max 20 goruntu, kuyruga alinir; status WS veya GET ile takip edilir.
    - **model**: hangi pipeline kullanilacak. Frontend toggle (Pre-trained / Kendi Modellerim).
      Gecersiz id -> 400 'Bilinmeyen model'.
    """
    if not files:
        raise HTTPException(status_code=400, detail="En az 1 goruntu gerekli")

    # Model validasyonu — registry'de tanimli olmali. Bilinmeyen id ->
    # 400 (HTTP 422 degil; bu bir is kurali, schema hatasi degil).
    model_id = resolve_model_id(model)
    if not is_known_model_id(model_id):
        raise HTTPException(
            status_code=400,
            detail=f"Bilinmeyen model: {model}",
        )

    # Pretrained model agirlik dosyalari bu deploy'da mevcut mu?
    # HF Spaces gibi disk kisitli ortamlarda pretrained_hybrid / roboflow
    # agirliklari image'a embed edilmemis olabilir — 500 yerine net 400 don.
    available, reason = check_model_files_available(model_id)
    if not available:
        raise HTTPException(status_code=400, detail=reason)

    if mode == "sync":
        if len(files) > settings.max_images_sync:
            raise HTTPException(
                status_code=400,
                detail=f"Sync modda max {settings.max_images_sync} goruntu",
            )
        return await _process_sync(files, auth, model=model_id)

    # Async
    if len(files) > settings.max_images_async:
        raise HTTPException(
            status_code=400,
            detail=f"Async modda max {settings.max_images_async} goruntu",
        )
    return await _enqueue_async(files, auth, model=model_id)


async def _enqueue_async(files: List[UploadFile], auth: AuthContext,
                         model: str = DEFAULT_MODEL_ID) -> JSONResponse:
    inspection_id = str(uuid.uuid4())
    image_urls: List[str] = []

    for i, f in enumerate(files):
        _, url = await _store_upload(f, inspection_id, i)
        image_urls.append(url)

    save_inspection(
        inspection_id=inspection_id,
        client_id=auth.client_id,
        status="queued",
        image_urls=image_urls,
    )

    # Hangi modelin secildigini DB'ye yaz — worker bunu okuyup analyze'a
    # tasiyabilir, audit trail icin model_versions JSONB sutununda kalir.
    # Worker model param almasa bile DB'de "requested_model" kayitli olur.
    try:
        update_inspection(
            inspection_id,
            model_versions={"requested_model": model},
        )
    except Exception as e:  # noqa: BLE001
        # model_versions kolonu yok (legacy raw repo) -> sessiz fallback
        logger.debug("model_versions kaydedilemedi (legacy schema?): %s", e)

    try:
        # Geriye uyumlu cagri: model param celery task'a kwargs olarak gecsin
        try:
            run_inspection_task.delay(inspection_id, image_urls, model=model)
        except TypeError:
            # Eski worker imza: model param yok — sessiz fallback (custom kullanir).
            # Worker tarafindan inspection.model_versions.requested_model
            # okunarak compat saglanabilir; bu MVP'de log'da kalir.
            logger.warning(
                "Worker run_inspection_task 'model' kwarg kabul etmiyor — "
                "async pipeline 'custom' modeliyle calisacak (inspection=%s)",
                inspection_id,
            )
            run_inspection_task.delay(inspection_id, image_urls)
    except Exception as e:
        logger.error(f"Celery enqueue basarisiz: {e}")
        update_inspection(inspection_id, status="failed", error="Kuyruk hizmeti kapali")
        raise HTTPException(status_code=503, detail="Is kuyrugu su an kullanilamiyor")

    # Tahmini bekleme suresi — frontend polling backoff'u icin yararli.
    # Kuyrukta onumuzde olanlari sayariz (status IN queued/processing).
    # NOT: Bu sayim cross-tenant; gercek "queue_position" Celery inspect
    # active'a baglandiginda dogrudur. MVP icin "approx" yeterli.
    est_seconds = max(15, len(files) * 10)
    queue_position: Optional[int] = None
    try:
        if _db_available():
            with _pg_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT COUNT(*) FROM inspections WHERE status IN ('queued','processing')"
                    )
                    queue_position = int(cur.fetchone()[0] or 0)
                    if queue_position > 1:
                        est_seconds = max(est_seconds, queue_position * len(files) * 8)
    except Exception as e:  # noqa: BLE001
        logger.debug("queue_position sayilamadi: %s", e)

    payload = InspectionCreateResponse(
        inspection_id=inspection_id,
        status="queued",
        status_url=f"/api/v1/inspect/{inspection_id}",
        created_at=_utc_iso(),
        estimated_completion_seconds=est_seconds,
    )
    body = payload.model_dump(exclude_none=True)
    if queue_position is not None:
        # Pydantic StrictModel extra=forbid — manuel ekle (response_model
        # union oldugu icin valide edilmiyor; sozlesme kirilmiyor).
        body["queue_position"] = queue_position
    # Hangi modelle inference yapilacagini frontend'e bildir (audit + UI badge).
    body["model_used"] = model
    return JSONResponse(
        status_code=202,
        content=body,
        headers={"X-Inspection-Id": inspection_id, "X-Model-Id": model},
    )


async def _process_sync(files: List[UploadFile], auth: AuthContext,
                        model: str = DEFAULT_MODEL_ID) -> JSONResponse:
    inspection_id = str(uuid.uuid4())
    image_urls: List[str] = []
    results: List[dict] = []
    per_image: List[dict] = []

    failed_indices: List[int] = []
    for i, f in enumerate(files):
        try:
            content, url = await _store_upload(f, inspection_id, i)
        except HTTPException:
            raise  # 400/413 - validation, kullaniciya net don
        except Exception as e:  # noqa: BLE001
            logger.exception("Store upload hatasi index=%d: %s", i, e)
            per_image.append({
                "index": i, "url": None, "status": "failed",
                "error": f"Goruntu yuklenemedi: {e}",
                "image": {"url": None}, "parts": [], "summary": {},
                "unassigned_damages": [], "multi_part_damages": [],
            })
            failed_indices.append(i)
            continue
        image_urls.append(url)
        try:
            img = _decode_image(content, i)
        except HTTPException as e:
            per_image.append({
                "index": i, "url": url, "status": "failed",
                "error": str(e.detail),
                "image": {"url": url}, "parts": [], "summary": {},
                "unassigned_damages": [], "multi_part_damages": [],
            })
            failed_indices.append(i)
            continue
        # GPU inference event-loop'u bloklamasin -> threadpool
        # Per-image error containment: tek foto fail tum batch'i ucurmasin.
        try:
            r = await asyncio.to_thread(ml_pipeline.analyze, img, 2, model)
        except RuntimeError as e:
            logger.error("ML pipeline runtime hatasi index=%d: %s", i, e)
            if len(files) == 1:
                raise HTTPException(status_code=503, detail="ML servisi su an kullanilamiyor")
            per_image.append({
                "index": i, "url": url, "status": "failed",
                "error": f"ML servisi: {e}",
                "image": {"url": url}, "parts": [], "summary": {},
                "unassigned_damages": [], "multi_part_damages": [],
            })
            failed_indices.append(i)
            continue
        except Exception as e:  # noqa: BLE001
            msg = str(e).lower()
            if "out of memory" in msg or "cuda" in msg:
                logger.error("GPU OOM index=%d: %s", i, e)
                if len(files) == 1:
                    raise HTTPException(status_code=503, detail="GPU bellegi yetersiz, daha kucuk goruntu deneyin")
                per_image.append({
                    "index": i, "url": url, "status": "failed",
                    "error": "GPU bellegi yetersiz",
                    "image": {"url": url}, "parts": [], "summary": {},
                    "unassigned_damages": [], "multi_part_damages": [],
                })
                failed_indices.append(i)
                continue
            logger.exception("ML analyze hatasi index=%d: %s", i, e)
            if len(files) == 1:
                raise HTTPException(status_code=500, detail=f"Analiz hatasi: {e}")
            per_image.append({
                "index": i, "url": url, "status": "failed",
                "error": f"Analiz hatasi: {e}",
                "image": {"url": url}, "parts": [], "summary": {},
                "unassigned_damages": [], "multi_part_damages": [],
            })
            failed_indices.append(i)
            continue
        if isinstance(r, dict):
            img_blk = r.get("image") if isinstance(r.get("image"), dict) else {}
            if (not img_blk.get("url")) or img_blk.get("url") == "<inline>":
                img_blk["url"] = url
            r["image"] = img_blk
        results.append(r)
        per_image.append({
            "index": i,
            "url": url,
            "status": "completed",
            "image": (r.get("image") if isinstance(r, dict) else None) or {"url": url},
            "parts": (r.get("parts") if isinstance(r, dict) else []) or [],
            "summary": (r.get("summary") if isinstance(r, dict) else {}) or {},
            "unassigned_damages": (r.get("unassigned_damages") if isinstance(r, dict) else []) or [],
            "multi_part_damages": (r.get("multi_part_damages") if isinstance(r, dict) else []) or [],
        })

    # En az 1 sonuc yoksa toplu fail; sıralamayı sayfanın bozulmaması için
    # results bos olsa bile per_image listesi UI'a doner.
    if not results:
        raise HTTPException(status_code=500, detail=(
            f"Hicbir goruntu analiz edilemedi ({len(failed_indices)} adet basarisiz)"
        ))

    try:
        aggregated = aggregate_results(results) if len(results) > 1 else dict(results[0])
    except Exception as e:  # noqa: BLE001
        logger.exception("aggregate_results crash: %s", e)
        # Fallback: ilk sonucu ham dondur, per_image kullanici icin yeterli
        aggregated = dict(results[0])
        aggregated["_aggregation_error"] = str(e)
    # inspection_id'yi zorla yerlestir
    aggregated["inspection_id"] = inspection_id
    aggregated["images"] = per_image
    # Audit: hangi modelle inference yapildi. ModelManager adapter'i de
    # result["model_source"] olarak ekliyor; biz top-level "model_used"i
    # yeni sozlesme alani olarak veriyoruz (frontend bu alani okusun).
    aggregated["model_used"] = model

    now_iso = _utc_iso()
    save_inspection(
        inspection_id=inspection_id,
        client_id=auth.client_id,
        status="completed",
        image_urls=image_urls,
        result=aggregated,
    )
    # Sync mode'da completed_at de set edilmeli (async worker yaziyor; sync'te biz yazariz)
    # + model_versions JSONB sutununa hangi modelle calistigini yaz.
    # ModelManager adapter'inin doldurdugu result["model_versions"] varsa onu
    # esas al; yoksa minimal payload yaz.
    model_versions_payload = (
        aggregated.get("model_versions")
        if isinstance(aggregated.get("model_versions"), dict)
        else {}
    )
    model_versions_payload = dict(model_versions_payload)
    model_versions_payload.setdefault("requested_model", model)
    model_versions_payload.setdefault("model_source", aggregated.get("model_source") or model)
    try:
        update_inspection(
            inspection_id,
            completed_at=now_iso,
            model_versions=model_versions_payload,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("completed_at/model_versions update atlandi: %s", e)
        # Geri: en azindan completed_at yaz
        try:
            update_inspection(inspection_id, completed_at=now_iso)
        except Exception:
            pass

    # Pydantic strict validation pipeline output ile drift halinde —
    # pilot icin ham dict ile dondur, schema enforcement client-side'da
    # opsiyonel. Lokal dev'de SyncInspectionResponse(...) ile validate
    # edilmek istenirse STRICT_RESPONSE_VALIDATION=1 env'i ile zorlanir.
    import os as _os
    if _os.getenv("STRICT_RESPONSE_VALIDATION", "0") == "1":
        payload = SyncInspectionResponse(
            inspection_id=inspection_id,
            result=aggregated,
            processed_at=now_iso,
        )
        body = payload.model_dump(exclude_none=True)
    else:
        body = {
            "inspection_id": inspection_id,
            "result": aggregated,
            "processed_at": now_iso,
        }
    body["model_used"] = model
    return JSONResponse(
        status_code=200,
        content=body,
        headers={"X-Inspection-Id": inspection_id, "X-Model-Id": model},
    )


@app.post(
    "/api/v1/inspect/sync",
    response_model=None,  # JSONResponse — _process_sync donuyor
    responses={
        200: {"model": SyncInspectionResponse, "description": "Sync tamamlandi"},
        400: {"model": ApiError},
        401: {"model": ApiError},
        413: {"model": ApiError},
        415: {"model": ApiError},
        503: {"model": ApiError},
    },
    tags=["inspect"],
    summary="Hizli senkron inceleme (tek veya az sayida goruntu)",
)
async def sync_single(
    file: Optional[UploadFile] = File(None, description="Tek goruntu (eski alan adi)"),
    files: Optional[List[UploadFile]] = File(None, description="1+ goruntu (web)"),
    model: str = Query("custom", description="Model kaynak id'si (GET /api/v1/models)"),
    auth: AuthContext = Depends(require_api_key),
):
    """Senkron inceleme — latency hassas.

    Frontend uyumu icin hem `file` (tekil — mobile eski path) hem `files` (cogul —
    web/desktop) field adlarini kabul eder. En az 1 dosya gerekli, max
    `max_images_sync`.
    """
    # Frontend hangi adi gonderdiyse onu al; ikisi de bos -> 400
    upload_list: List[UploadFile] = []
    if files:
        upload_list.extend([f for f in files if f is not None])
    if file is not None:
        upload_list.append(file)

    if not upload_list:
        raise HTTPException(
            status_code=400,
            detail="En az 1 goruntu gerekli (multipart field: 'files' veya 'file')",
        )
    if len(upload_list) > settings.max_images_sync:
        raise HTTPException(
            status_code=400,
            detail=f"Sync modda max {settings.max_images_sync} goruntu",
        )
    model_id = resolve_model_id(model)
    if not is_known_model_id(model_id):
        raise HTTPException(status_code=400, detail=f"Bilinmeyen model: {model}")
    return await _process_sync(upload_list, auth, model=model_id)


@app.get(
    "/api/v1/inspect/{inspection_id}",
    response_model=None,  # strict schema drift — ham dict ile dondur
    tags=["inspect"],
    summary="Inceleme durumu + sonucu",
)
async def get_inspection(
    inspection_id: str,
    auth: AuthContext = Depends(require_api_key),
):
    inspection = get_db().get(inspection_id)
    if not inspection:
        raise HTTPException(status_code=404, detail="Inceleme bulunamadi")
    if inspection["client_id"] != auth.client_id and not auth.is_dev:
        raise HTTPException(status_code=403, detail="Bu incelemeye erisim yetkiniz yok")

    # Pipeline output drift'ten kacin — strict validation yerine ham dict.
    return JSONResponse(
        status_code=200,
        content={
            "inspection_id": inspection_id,
            "status": inspection["status"],
            "result": inspection.get("result"),
            "error": inspection.get("error"),
            "created_at": inspection["created_at"],
            "completed_at": inspection.get("completed_at"),
        },
    )


@app.get(
    "/api/v1/inspect/{inspection_id}/visualization/{viz_type}",
    tags=["inspect"],
    summary="Annotated/parts/damages PNG (presigned URL'e redirect)",
    responses={
        302: {"description": "S3 presigned URL'e yonlendir"},
        404: {"model": ApiError},
        403: {"model": ApiError},
        409: {"model": ApiError, "description": "Inspection henuz tamamlanmamis"},
    },
)
async def get_visualization(
    inspection_id: str,
    viz_type: Literal["annotated", "parts", "damages"],
    auth: AuthContext = Depends(require_api_key),
):
    inspection = get_db().get(inspection_id)
    if not inspection:
        raise HTTPException(status_code=404, detail="Inceleme bulunamadi")
    # Owner-only erisim (dev bypass haric)
    if inspection["client_id"] != auth.client_id and not auth.is_dev:
        raise HTTPException(status_code=403, detail="Yetki yok")

    inspection_status = inspection.get("status")
    if inspection_status in ("queued", "processing"):
        raise HTTPException(
            status_code=409,
            detail=f"Inceleme henuz tamamlanmamis (status={inspection_status})",
        )
    if inspection_status == "failed":
        raise HTTPException(
            status_code=409,
            detail="Inceleme basarisiz oldu, gorsel mevcut degil",
        )

    result = inspection.get("result") or {}
    urls = (result.get("visualization_urls") or {}) if isinstance(result, dict) else {}
    target_url = urls.get(viz_type)

    if not target_url:
        # Fallback: standart key formati uretmeyi dene
        key = f"inspections/{inspection_id}/visualizations/{viz_type}.png"
        try:
            target_url = get_presigned_url(key)
        except Exception as e:
            logger.warning(f"Presigned url uretilemedi: {e}")
            raise HTTPException(
                status_code=404,
                detail=f"{viz_type} gorsel henuz uretilmemis",
            )

    # Security: presigned URL imzali, tekrar kullanilabilir kisa omurlu URL.
    # Browser cache'lemesin — owner kontrolunu her seferinde tetiklesin.
    return RedirectResponse(
        url=target_url,
        status_code=302,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, private",
            "Pragma": "no-cache",
        },
    )


@app.get(
    "/api/v1/inspect",
    response_model=InspectionListResponse,
    tags=["inspect"],
    summary="Inceleme listesi (sayfalanmis)",
)
async def list_inspections(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    auth: AuthContext = Depends(require_api_key),
):
    db = get_db()
    offset = (page - 1) * page_size
    raw_items = db.list(client_id=auth.client_id, limit=page_size, offset=offset)
    total = db.count(client_id=auth.client_id) if hasattr(db, "count") else len(raw_items)

    items: List[InspectionListItem] = []
    for r in raw_items:
        result_obj = r.get("result") if isinstance(r.get("result"), dict) else None
        summary = (result_obj or {}).get("summary")

        # ---- Thumbnail URL resolution -------------------------------------
        # Oncelik sirasi (frontend history sayfasinda gorsel kart icin):
        #   1) result.images[0].url             (yeni per-image kontrat)
        #   2) result.image.url                 (tek-goruntu legacy/sync)
        #   3) result.visualization_urls.annotated  (annotated thumbnail)
        #   4) image_urls JSONB legacy ilk URL  (raw repo legacy column)
        #   5) /api/v1/inspect/{id}/visualization/annotated (server-side redirect)
        thumb: Optional[str] = None
        if result_obj:
            imgs_block = result_obj.get("images")
            if isinstance(imgs_block, list) and imgs_block:
                first = imgs_block[0]
                if isinstance(first, dict):
                    u = first.get("url")
                    if isinstance(u, str) and u and u != "<inline>":
                        thumb = u
                    elif isinstance(first.get("image"), dict):
                        u2 = first["image"].get("url")
                        if isinstance(u2, str) and u2 and u2 != "<inline>":
                            thumb = u2
            if not thumb:
                img_blk = result_obj.get("image")
                if isinstance(img_blk, dict):
                    u = img_blk.get("url")
                    if isinstance(u, str) and u and u != "<inline>":
                        thumb = u
            if not thumb:
                viz = result_obj.get("visualization_urls")
                if isinstance(viz, dict):
                    u = viz.get("annotated")
                    if isinstance(u, str) and u:
                        thumb = u

        if not thumb:
            iu = r.get("image_urls")
            if isinstance(iu, list) and iu:
                cand = iu[0]
                if isinstance(cand, str) and cand and cand != "<inline>" \
                        and not cand.startswith("local://"):
                    thumb = cand

        inspection_id_val = r["id"] if "id" in r else r.get("inspection_id")
        if not thumb and inspection_id_val:
            # Son care: annotated visualization endpoint (302 -> presigned).
            # Inspection completed degilse 409 doner ama frontend bunu
            # bos thumbnail olarak ele alir (placeholder gosterir).
            if r.get("status") == "completed":
                thumb = f"/api/v1/inspect/{inspection_id_val}/visualization/annotated"

        items.append(InspectionListItem(
            inspection_id=inspection_id_val,
            created_at=r["created_at"],
            status=r["status"],
            damage_count=(summary or {}).get("total_damage_count", 0),
            total_cost_midpoint_tl=(summary or {}).get("total_cost_midpoint_tl"),
            thumbnail_url=thumb,
        ))

    return InspectionListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@app.delete(
    "/api/v1/inspect/{inspection_id}",
    status_code=204,
    tags=["inspect"],
    summary="Inceleme sil",
)
async def delete_inspection_endpoint(
    inspection_id: str,
    auth: AuthContext = Depends(require_api_key),
):
    inspection = get_db().get(inspection_id)
    if not inspection:
        raise HTTPException(status_code=404, detail="Inceleme bulunamadi")
    if inspection["client_id"] != auth.client_id and not auth.is_dev:
        raise HTTPException(status_code=403, detail="Yetki yok")

    try:
        delete_inspection(inspection_id)
    except Exception as e:
        logger.error(f"Silme hatasi: {e}")
        raise HTTPException(status_code=500, detail="Silme islemi basarisiz")

    return Response(status_code=204)


# ---------------- WebSocket ----------------

@app.websocket("/api/v1/inspect/{inspection_id}/stream")
async def inspect_stream(websocket: WebSocket, inspection_id: str):
    """Async inceleme icin canli durum streaming'i.

    Mesaj formatlari:
      - {"type":"status","inspection_id":"...","status":"queued|processing"}
      - {"type":"completed","inspection_id":"...","result":{...}}
      - {"type":"error","inspection_id":"...","error":"..."}

    NOT: Auth header WS handshake'te tasinmadigi icin MVP'de query param tabanli
    (?api_key=...) eklenebilir; suanlik dev modda acik.
    """
    await stream_inspection(websocket, inspection_id)


# ---------------- Aggregation helper ----------------

def aggregate_results(results: List[dict]) -> dict:
    """Birden cok goruntunun parca-merkezli sonuclarini birlestir.

    Naif strateji: parcalari name'e gore merge et; ayni hasari deduplicate et
    (bbox+type+part overlap). v2'de gelistirilecek.
    """
    if not results:
        return {
            "inspection_id": "",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "image": {"width": 0, "height": 0},
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

    if len(results) == 1:
        only = results[0]
        # Legacy "<inline>" sanitize — bazi eski pipeline output'lari hala
        # bu placeholder'i image.url icine yaziyor. Yeni kontrat: None.
        if isinstance(only, dict):
            img_blk = only.get("image") if isinstance(only.get("image"), dict) else None
            if img_blk and img_blk.get("url") == "<inline>":
                img_blk["url"] = None
        return only

    parts_by_name: dict = {}
    cost_min = 0.0
    cost_max = 0.0
    total_area = 0.0
    multi_part_damages: list = []
    unassigned_damages: list = []

    for r in results:
        for p in r.get("parts", []) or []:
            name = p["name"]
            if name not in parts_by_name:
                parts_by_name[name] = dict(p)
                parts_by_name[name]["damages"] = list(p.get("damages", []))
            else:
                existing = parts_by_name[name]
                existing["damages"].extend(p.get("damages", []))
                existing["damage_count"] = existing.get("damage_count", 0) + p.get("damage_count", 0)
                existing["part_cost_min_tl"] = (existing.get("part_cost_min_tl") or 0) + (p.get("part_cost_min_tl") or 0)
                existing["part_cost_max_tl"] = (existing.get("part_cost_max_tl") or 0) + (p.get("part_cost_max_tl") or 0)
                # Status: en kotuyu al
                rank = {"clean": 0, "minor_damage": 1, "moderate_damage": 2, "severe_damage": 3}
                if rank.get(p.get("status", "clean"), 0) > rank.get(existing.get("status", "clean"), 0):
                    existing["status"] = p["status"]

        multi_part_damages.extend(r.get("multi_part_damages", []) or [])
        unassigned_damages.extend(r.get("unassigned_damages", []) or [])

        s = r.get("summary") or {}
        rng = s.get("total_cost_range_tl") or [0, 0]
        cost_min += rng[0] or 0
        cost_max += rng[1] or 0
        total_area += s.get("total_damage_area_ratio") or 0

    parts_list = list(parts_by_name.values())
    parts_list.sort(key=lambda p: (p.get("status") == "clean", -p.get("damage_count", 0)))

    damaged = sum(1 for p in parts_list if p.get("status") != "clean")
    total_damage_count = sum(p.get("damage_count", 0) for p in parts_list) + len(unassigned_damages)

    severity_rank = {"hafif": 1, "orta": 2, "agir": 3}
    most_severe = None
    most_val = 0
    for p in parts_list:
        for d in p.get("damages", []):
            lvl = (d.get("severity") or {}).get("level")
            v = severity_rank.get(lvl, 0)
            if v > most_val:
                most_val = v
                most_severe = lvl

    summary = {
        "total_parts_inspected": len(parts_list),
        "damaged_parts_count": damaged,
        "clean_parts_count": len(parts_list) - damaged,
        "total_damage_count": total_damage_count,
        "unknown_part_damages_count": len(unassigned_damages),
        "multi_part_damages_count": len(multi_part_damages),
        "most_severe_level": most_severe,
        "most_severe_level_tr": {"hafif": "Hafif", "orta": "Orta", "agir": "Agir"}.get(most_severe),
        "total_damage_area_ratio": round(total_area, 4),
        "total_cost_range_tl": [round(cost_min, 2), round(cost_max, 2)],
        "total_cost_midpoint_tl": round((cost_min + cost_max) / 2, 2),
        "cost_confidence": "medium",
        "repair_recommendation": "tamir_boya" if total_damage_count else "hasar_yok",
        "repair_recommendation_tr": "Tamir + boya gerekli" if total_damage_count else "Hasar tespit edilmedi",
        "estimated_repair_days": max(1, math.ceil(total_damage_count / 2)) if total_damage_count else 0,
    }

    first = results[0]
    # Legacy "<inline>" sanitize on aggregate top-level image block too
    first_img = first.get("image", {"width": 0, "height": 0})
    if isinstance(first_img, dict) and first_img.get("url") == "<inline>":
        first_img = {**first_img, "url": None}
    return {
        "inspection_id": first.get("inspection_id", str(uuid.uuid4())),
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "image": first_img,
        "parts": parts_list,
        "summary": summary,
        **({"multi_part_damages": multi_part_damages} if multi_part_damages else {}),
        **({"unassigned_damages": unassigned_damages} if unassigned_damages else {}),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
