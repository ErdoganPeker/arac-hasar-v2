"""
backend/auth.py
Kimlik dogrulama / yetkilendirme katmani.

Sundugu HTTP rotalari:
  - POST /auth/register   (yeni kullanici olustur, ilk token cifti)
  - POST /auth/login      (email+password -> access + refresh token)
  - GET  /auth/me         (mevcut kullanici)
  - POST /auth/refresh    (refresh -> yeni access + yeni refresh)

Dependency'ler:
  - get_current_user       (zorunlu auth — JWT primary, API key fallback)
  - require_api_key        (geriye uyumluluk; main.py'nin eski Depends'leri)
  - optional_current_user  (public endpoint'lerde caller bilgisi)

Bu modul kripto yapmaz — security.py'daki utility'leri kullanir.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import psycopg2
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from psycopg2.extras import RealDictCursor
from slowapi.util import get_remote_address

from middleware import limiter

from config import settings
from models import (
    RefreshTokenRequest,
    TokenPair,
    UserLoginRequest,
    UserPublic,
    UserRegisterRequest,
)
from security import (
    ACCESS_TOKEN_MINUTES,
    TokenPayload,
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
    verify_token,
)


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Bearer JWT (primary) + legacy API key (fallback)
_bearer_scheme = HTTPBearer(auto_error=False, scheme_name="JWT")
_api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


# ============================ Context ============================

@dataclass
class AuthContext:
    """Authenticated caller — DI ile route'lara aktarilir.

    Backward-compat: main.py'nin eski Depends'leri 'client_id', 'is_dev',
    'api_key' alanlarini bekliyor, oldugu gibi koruyoruz.
    """
    client_id: str                # JWT'de user_id (UUID str), API key'de 'apikey:xxx'
    email: Optional[str] = None
    role: str = "user"
    api_key: Optional[str] = None
    is_dev: bool = False
    is_api_key_auth: bool = False


# ============================ User repository ============================

# NOT: Database Optimizer ajaninin db_models.py + migrations'i hazirsa orasi
# kullanilir. Hazir degilse asagidaki minimal repo + idempotent CREATE TABLE
# devreye girer (dev/pilot rahat olsun).

_USERS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT,
    role TEXT NOT NULL DEFAULT 'user',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_email_ci ON users ((LOWER(email)));
"""


class _InMemoryUserStore:
    """DB yoksa kullanilan dev fallback. Production'da postgres bagliysa devre disi."""

    def __init__(self) -> None:
        self._by_id: dict[str, dict] = {}
        self._by_email: dict[str, str] = {}

    def get_by_id(self, user_id: str) -> Optional[dict]:
        return self._by_id.get(user_id)

    def get_by_email(self, email: str) -> Optional[dict]:
        uid = self._by_email.get(email.lower())
        return self._by_id.get(uid) if uid else None

    def create(self, row: dict) -> None:
        self._by_id[row["id"]] = row
        self._by_email[row["email"].lower()] = row["id"]


_memory_users = _InMemoryUserStore()


def _can_connect_db() -> bool:
    try:
        with psycopg2.connect(settings.database_url, connect_timeout=2):
            return True
    except Exception:
        return False


_schema_bootstrapped = False


def _ensure_schema_once() -> None:
    global _schema_bootstrapped
    if _schema_bootstrapped:
        return
    try:
        with psycopg2.connect(settings.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(_USERS_SCHEMA_SQL)
            conn.commit()
        _schema_bootstrapped = True
    except Exception as e:
        logger.debug("users schema bootstrap atlandi: %s", e)


class _UserRepo:
    """Minimal psycopg2 repo — SQLAlchemy ORM hazirsa o tarafa devredilir."""

    def get_by_id(self, user_id: str) -> Optional[dict]:
        if not _can_connect_db():
            return _memory_users.get_by_id(user_id)
        _ensure_schema_once()
        with psycopg2.connect(settings.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
                row = cur.fetchone()
        return self._normalize(row)

    def get_by_email(self, email: str) -> Optional[dict]:
        if not _can_connect_db():
            return _memory_users.get_by_email(email)
        _ensure_schema_once()
        with psycopg2.connect(settings.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM users WHERE LOWER(email) = LOWER(%s)",
                    (email,),
                )
                row = cur.fetchone()
        return self._normalize(row)

    def create(
        self,
        email: str,
        password_hash_value: str,
        full_name: Optional[str],
    ) -> dict:
        user_id = str(uuid.uuid4())
        now_iso = datetime.utcnow().isoformat() + "Z"
        row = {
            "id": user_id,
            "email": email,
            "password_hash": password_hash_value,
            "full_name": full_name,
            "role": "user",
            "is_active": True,
            "created_at": now_iso,
        }
        if not _can_connect_db():
            _memory_users.create(row)
            return row
        _ensure_schema_once()
        with psycopg2.connect(settings.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (id, email, password_hash, full_name)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (user_id, email, password_hash_value, full_name),
                )
            conn.commit()
        return row

    @staticmethod
    def _normalize(row: Optional[dict]) -> Optional[dict]:
        if not row:
            return None
        if "created_at" in row and hasattr(row["created_at"], "isoformat"):
            row["created_at"] = row["created_at"].isoformat()
        if "updated_at" in row and hasattr(row["updated_at"], "isoformat"):
            row["updated_at"] = row["updated_at"].isoformat()
        return dict(row)


_repo = _UserRepo()


def _to_public(row: dict) -> UserPublic:
    return UserPublic(
        id=str(row["id"]),
        email=row["email"],
        full_name=row.get("full_name"),
        role=row.get("role") or "user",
        is_active=bool(row.get("is_active", True)),
        created_at=str(row["created_at"]),
    )


# ============================ Dependencies ============================

_DEV_WARN_LOGGED = False


def _warn_dev_mode_once() -> None:
    global _DEV_WARN_LOGGED
    if not _DEV_WARN_LOGGED:
        logger.warning(
            "[AUTH] DEV MODE — auth-bypass aktif (ENVIRONMENT=development ve "
            "API_KEYS bos). Production'da otomatik kapanir."
        )
        _DEV_WARN_LOGGED = True


async def get_current_user(
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    x_api_key: Optional[str] = Depends(_api_key_scheme),
) -> AuthContext:
    """Zorunlu auth dependency. Oncelik sirasi:

      1) Authorization: Bearer <jwt>  -> security.verify_token + DB lookup
      2) X-API-Key                    -> legacy API_KEYS listesi
      3) Dev mode bypass              -> sadece environment=development AND API_KEYS bos
      4) Aksi: 401
    """
    # --- 1) JWT path ---
    if bearer is not None and (bearer.scheme or "").lower() == "bearer" and bearer.credentials:
        # verify_token zaten HTTPException(401) raise eder
        payload: TokenPayload = verify_token(bearer.credentials, expected_type="access")

        user = _repo.get_by_id(payload.sub)
        if not user or not user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Kullanici bulunamadi veya devre disi",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return AuthContext(
            client_id=str(user["id"]),
            email=user.get("email"),
            role=user.get("role") or payload.role or "user",
            is_dev=False,
            is_api_key_auth=False,
        )

    # --- 2) Legacy API key ---
    if x_api_key:
        if x_api_key in settings.api_keys:
            return AuthContext(
                client_id=f"apikey:{x_api_key[:8]}",
                api_key=x_api_key,
                is_dev=False,
                is_api_key_auth=True,
            )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Gecersiz API key",
        )

    # --- 3) Dev mode bypass ---
    if settings.dev_mode:
        _warn_dev_mode_once()
        return AuthContext(client_id="dev", is_dev=True)

    # --- 4) Unauthorized ---
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authorization gerekli (Bearer JWT veya X-API-Key)",
        headers={"WWW-Authenticate": "Bearer"},
    )


# Geriye uyumluluk — main.py'deki mevcut Depends'ler bunu cagiriyor.
require_api_key = get_current_user


async def optional_current_user(
    bearer: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
    x_api_key: Optional[str] = Depends(_api_key_scheme),
) -> Optional[AuthContext]:
    """Opsiyonel auth — health/version icin caller kimligi varsa logla."""
    if not bearer and not x_api_key:
        return None
    try:
        return await get_current_user(bearer=bearer, x_api_key=x_api_key)
    except HTTPException:
        return None


# ============================ Token helper ============================

def _build_token_pair(user_id: str, role: str) -> TokenPair:
    user_uuid = uuid.UUID(user_id)
    return TokenPair(
        access_token=create_access_token(user_uuid, role=role),
        refresh_token=create_refresh_token(user_uuid),
        expires_in=ACCESS_TOKEN_MINUTES * 60,
    )


# ============================ Routes ============================

@router.post(
    "/register",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni kullanici kaydi",
)
async def register(payload: UserRegisterRequest) -> TokenPair:
    if _repo.get_by_email(payload.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu email zaten kayitli",
        )
    try:
        password_hash_value = hash_password(payload.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    user = _repo.create(
        email=payload.email,
        password_hash_value=password_hash_value,
        full_name=payload.full_name,
    )
    logger.info("Yeni kullanici: %s (%s)", user["id"], user["email"])
    return _build_token_pair(
        user_id=str(user["id"]),
        role=user.get("role") or "user",
    )


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Email + parola ile giris",
)
@limiter.limit("5/minute", key_func=get_remote_address)
async def login(request: Request, payload: UserLoginRequest) -> TokenPair:
    user = _repo.get_by_email(payload.email)
    # Timing-safe: kullanici yoksa bile bcrypt cagrisini calistir
    dummy_hash = "$2b$12$abcdefghijklmnopqrstuvCk1L9F8KH9zXOQ/4r3yL.lq.zN.dWNm"
    hashed = user["password_hash"] if user else dummy_hash
    valid = verify_password(payload.password, hashed)

    if not user or not valid or not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email veya parola hatali",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _build_token_pair(
        user_id=str(user["id"]),
        role=user.get("role") or "user",
    )


@router.get(
    "/me",
    response_model=UserPublic,
    summary="Oturum acmis kullanici bilgileri",
)
async def me(auth: AuthContext = Depends(get_current_user)) -> UserPublic:
    if auth.is_api_key_auth or auth.is_dev:
        # API key / dev: gercek user kaydi olmayabilir; pseudo-user dondur
        return UserPublic(
            id=auth.client_id,
            email=auth.email or f"{auth.client_id}@local",  # type: ignore[arg-type]
            full_name=None,
            role=auth.role or "user",
            is_active=True,
            created_at=datetime.utcnow().isoformat() + "Z",
        )
    user = _repo.get_by_id(auth.client_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kullanici bulunamadi",
        )
    return _to_public(user)


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Refresh token ile yeni access + refresh cifti al",
)
async def refresh(payload: RefreshTokenRequest) -> TokenPair:
    # verify_token kendi 401'ini frlatir
    token_payload: TokenPayload = verify_token(payload.refresh_token, expected_type="refresh")

    user = _repo.get_by_id(token_payload.sub)
    if not user or not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kullanici bulunamadi veya devre disi",
        )

    # Refresh anlaminda role DB'den yeniden okunur (security.py uyarisi: refresh
    # icindeki role hep 'user' geliyor, privilege escalation icin DB shart).
    return _build_token_pair(
        user_id=str(user["id"]),
        role=user.get("role") or "user",
    )
