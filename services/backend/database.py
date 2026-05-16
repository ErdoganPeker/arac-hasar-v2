"""
backend/database.py
PostgreSQL + SQLAlchemy 2.0 async engine ve session factory.

Diger modullerin (auth, ml_service, worker, main, ws) kullanacagi temel altyapi:
    from database import Base, get_db, AsyncSessionLocal, engine

Driver: asyncpg
Pool: production-grade defaults (pool_size=10, max_overflow=20, pool_pre_ping)
URL: DATABASE_URL ortam degiskeninden. Eski (sync) DATABASE_URL "postgresql://"
ile baslarsa otomatik olarak "postgresql+asyncpg://"a normalize edilir.

Not: Bu surum sync (psycopg2) helper'larini Pilot/MVP'den kaldirdi.
Eski endpoint'ler ORM uzerinden async olarak yeniden yazilmalidir.
"""
from __future__ import annotations

import logging
import os
import socket
from contextlib import asynccontextmanager
from typing import AsyncIterator

# ---------------------------------------------------------------------------
# IPv4-only DNS resolution (Render + Supabase compatibility shim)
# ---------------------------------------------------------------------------
# Render free tier has no IPv6 routes. Supabase publishes AAAA records (and
# the new shared pooler hosts publish BOTH A and AAAA). asyncpg's connect
# pipeline calls asyncio.loop.getaddrinfo with family=0 (AF_UNSPEC), which
# returns AAAA first on dual-stack hosts; the IPv6 connect attempt then
# fails with `OSError: [Errno 101] Network is unreachable` and asyncpg
# bubbles up the IPv6 error instead of falling back to A.
#
# Setting FORCE_IPV4=1 (default in Render env) hard-pins getaddrinfo to
# AF_INET so every DNS lookup — asyncpg, psycopg2, requests, boto3 — only
# sees IPv4. This is the smallest patch that makes Supabase work on Render
# without paying for the $4/mo IPv4 add-on.
if os.getenv("FORCE_IPV4", "1") == "1":
    _orig_getaddrinfo = socket.getaddrinfo

    def _ipv4_only_getaddrinfo(host, port, family=0, *args, **kwargs):
        return _orig_getaddrinfo(host, port, socket.AF_INET, *args, **kwargs)

    socket.getaddrinfo = _ipv4_only_getaddrinfo

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

try:
    # Backend kendi paketi olarak import edilirken
    from config import settings  # type: ignore
    _DEFAULT_URL = getattr(
        settings,
        "database_url_async",
        getattr(settings, "database_url", "postgresql+asyncpg://postgres:postgres@db:5432/arac_hasar"),
    )
except Exception:  # pragma: no cover - alembic context'inden import edildiginde
    _DEFAULT_URL = os.getenv(
        "DATABASE_URL_ASYNC",
        os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://postgres:postgres@db:5432/arac_hasar",
        ),
    )


logger = logging.getLogger(__name__)


def _normalize_async_url(url: str) -> str:
    """`postgresql://` -> `postgresql+asyncpg://` (defansif normalizasyon)."""
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url[len("postgresql://") :]
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url[len("postgres://") :]
    return url


DATABASE_URL: str = _normalize_async_url(_DEFAULT_URL)


# ---------------- Declarative base ----------------

class Base(DeclarativeBase):
    """Tum ORM modelleri bu base'i miras alir.

    SQLAlchemy 2.0 style declarative base.
    `db_models.py` icindeki modeller burayi import eder.
    """


# ---------------- Engine + session factory ----------------

# pool_pre_ping=True: kopan baglantilari (Supabase pooler, kontainer restart)
#   yakalar; ilk SELECT 1 testi yapar.
# pool_recycle=1800: 30 dk uzerindeki connection'lari geri donusturur.
# pool_size + max_overflow: pilot trafik icin makul; observability'den izleyip
#   gerekirse ENV ile artirilir.
#
# Supabase / PgBouncer (transaction mode) notu:
#   - Transaction pooler arkasinda calisirken `DB_USE_PGBOUNCER=true` set edilmeli.
#   - Bu durumda asyncpg statement cache devre disi (prepared statement sorunu)
#     ve pool_size kucuk tutulur (PgBouncer kendi pool'unu yonetir).
_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))
_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "1800"))
_SQL_ECHO = os.getenv("DB_ECHO", "false").lower() == "true"
_USE_PGBOUNCER = os.getenv("DB_USE_PGBOUNCER", "false").lower() == "true"


def _create_engine(url: str = DATABASE_URL) -> AsyncEngine:
    kwargs: dict = dict(
        echo=_SQL_ECHO,
        pool_size=_POOL_SIZE,
        max_overflow=_MAX_OVERFLOW,
        pool_timeout=_POOL_TIMEOUT,
        pool_recycle=_POOL_RECYCLE,
        pool_pre_ping=True,
        future=True,
    )
    if _USE_PGBOUNCER:
        # asyncpg: PgBouncer transaction mode'da prepared statement cache kapali olmali.
        kwargs["connect_args"] = {
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        }
    return create_async_engine(url, **kwargs)


engine: AsyncEngine = _create_engine()

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
    class_=AsyncSession,
)


# ---------------- FastAPI dependency ----------------

async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. Endpoint imzasinda kullan:

        from database import get_db

        @router.get("/...")
        async def handler(db: AsyncSession = Depends(get_db)):
            ...

    Rollback on exception, commit'i caller yapmali (explicit).
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Worker/script icin context manager. Otomatik commit + rollback.

        async with session_scope() as db:
            db.add(obj)
            # commit otomatik (exception yoksa)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------- Healthcheck ----------------

async def ping() -> bool:
    """SELECT 1 — readiness probe icin."""
    from sqlalchemy import text

    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception as exc:  # pragma: no cover
        logger.warning("DB ping failed: %s", exc)
        return False


__all__ = [
    "Base",
    "DATABASE_URL",
    "engine",
    "AsyncSessionLocal",
    "get_db",
    "session_scope",
    "ping",
]
