"""
Alembic env.py — async-aware, DATABASE_URL env'den okur.

Online mode: AsyncEngine ile run_sync(do_migrations).
Offline mode: standart SQL emit.

Hem `alembic upgrade head` hem `alembic revision --autogenerate` calisir.
"""
from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# services/backend dizinini path'e ekle ki "database", "db_models" import edilebilsin.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from database import Base  # noqa: E402
import db_models  # noqa: F401, E402  - tum modellerin Base.metadata'ya kayitli olmasi icin

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _resolve_url() -> str:
    """ENV > alembic.ini override."""
    env_url = os.getenv("DATABASE_URL_ASYNC") or os.getenv("DATABASE_URL")
    if env_url:
        # Sync URL'i async driver'a normalize et
        if env_url.startswith("postgresql://"):
            env_url = "postgresql+asyncpg://" + env_url[len("postgresql://") :]
        elif env_url.startswith("postgres://"):
            env_url = "postgresql+asyncpg://" + env_url[len("postgres://") :]
        return env_url
    return config.get_main_option("sqlalchemy.url", "")


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = _resolve_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    url = _resolve_url()
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = url

    # PgBouncer transaction-mode (Supabase shared pooler on :6543) does NOT
    # support PostgreSQL prepared statements — asyncpg's default named-stmt
    # cache fires DuplicatePreparedStatementError ("__asyncpg_stmt_1__")
    # right at the dialect's "SELECT pg_catalog.version()" probe. Detect
    # the pooler URL and disable both caches in the asyncpg connect kwargs.
    connect_args = {}
    if ":6543/" in url or "pooler.supabase.com" in url:
        connect_args = {
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
        }

    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
