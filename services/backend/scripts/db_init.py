"""
backend/scripts/db_init.py
One-shot DB init: Alembic'i programatik calistirir ve istege bagli admin user yaratir.

Calistirma (services/backend altinda):
    python -m scripts.db_init
    # veya
    python scripts/db_init.py

Env'ler:
    DATABASE_URL / DATABASE_URL_ASYNC  — zorunlu
    ADMIN_EMAIL                        — opsiyonel (varsa ADMIN_PASSWORD da gerekli)
    ADMIN_PASSWORD                     — opsiyonel

Sifre hashing:
    `security.py` Backend Architect tarafindan yazildiginda `hash_password`
    fonksiyonu oradan import edilir. Su an direkt passlib[bcrypt] kullanilir
    (requirements.txt'te zaten mevcut).
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

# services/backend dizinini path'e ekle
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from database import AsyncSessionLocal, engine  # noqa: E402
from db_models import User, UserRole  # noqa: E402


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
)
log = logging.getLogger("db_init")


# ---------------- Password hashing ----------------

def _hash_password(plain: str) -> str:
    """Bcrypt hash.

    Once `security.py`'den import etmeyi dene (Backend Architect tarafindan
    yazilacak kanonik fonksiyon). Yoksa passlib ile direkt bcrypt.
    """
    try:
        from security import hash_password  # type: ignore

        return hash_password(plain)
    except Exception:
        log.debug("security.hash_password yok — passlib bcrypt fallback")

    try:
        from passlib.context import CryptContext

        ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        return ctx.hash(plain)
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Sifre hashleyemedim. Backend Architect 'security.py' icine "
            "`hash_password(plain: str) -> str` bcrypt fonksiyonu yazmali "
            "veya passlib[bcrypt] kurulu olmali."
        ) from exc


# ---------------- Alembic upgrade ----------------

def _run_migrations() -> None:
    """`alembic upgrade head` esdegerini programatik calistir."""
    from alembic import command
    from alembic.config import Config

    ini_path = _BACKEND_DIR / "alembic.ini"
    if not ini_path.exists():
        raise FileNotFoundError(f"alembic.ini bulunamadi: {ini_path}")

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "migrations"))

    log.info("Alembic upgrade head calisiyor...")
    command.upgrade(cfg, "head")
    log.info("Migration tamam.")


# ---------------- Admin seed ----------------

async def _ensure_admin() -> None:
    admin_email = os.getenv("ADMIN_EMAIL")
    admin_password = os.getenv("ADMIN_PASSWORD")

    if not admin_email:
        log.info("ADMIN_EMAIL set degil — admin user yaratilmadi (atlandi).")
        return
    if not admin_password:
        log.warning(
            "ADMIN_EMAIL var ama ADMIN_PASSWORD yok. Admin yaratilmadi. "
            "Iki env'i de doldur."
        )
        return

    admin_email_norm = admin_email.strip().lower()

    async with AsyncSessionLocal() as session:
        existing = await session.scalar(
            select(User).where(User.email == admin_email_norm)
        )
        if existing is not None:
            log.info("Admin user zaten var: %s (id=%s)", admin_email_norm, existing.id)
            return

        user = User(
            email=admin_email_norm,
            password_hash=_hash_password(admin_password),
            full_name=os.getenv("ADMIN_FULL_NAME", "Admin"),
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        log.info("Admin user olusturuldu: %s (id=%s)", admin_email_norm, user.id)


# ---------------- Healthcheck ----------------

async def _ping() -> None:
    from sqlalchemy import text

    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1
    log.info("DB ping OK.")


# ---------------- Main ----------------

async def main() -> None:
    log.info("DB init basliyor (DATABASE_URL=%s)", _mask_url())
    await _ping()
    _run_migrations()
    await _ensure_admin()
    await engine.dispose()
    log.info("DB init tamam.")


def _mask_url() -> str:
    url = os.getenv("DATABASE_URL_ASYNC") or os.getenv("DATABASE_URL") or "<unset>"
    # parola maskele
    if "@" in url and "://" in url:
        scheme, rest = url.split("://", 1)
        if "@" in rest:
            creds, host = rest.split("@", 1)
            if ":" in creds:
                user, _ = creds.split(":", 1)
                return f"{scheme}://{user}:***@{host}"
    return url


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as exc:
        log.exception("DB init basarisiz: %s", exc)
        sys.exit(1)
