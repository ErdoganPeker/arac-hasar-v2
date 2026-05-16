"""
backend/security.py
-------------------
Security primitives for arac-hasar-v2.

Owned by: Security Engineer.
Other backend files MUST import from here rather than rolling their own
crypto / JWT / API key logic.

Exports
=======
Password hashing
    - hash_password(password) -> str
    - verify_password(plain, hashed) -> bool

JWT
    - create_access_token(user_id, role, expires_minutes=30) -> str
    - create_refresh_token(user_id, expires_days=7) -> str
    - verify_token(token, expected_type="access") -> TokenPayload

API keys (for service-to-service / pilot integrations)
    - generate_api_key() -> tuple[plain_key, hash_to_store]
    - verify_api_key(plain_key, stored_hash) -> bool

FastAPI dependencies
    - require_user  -> TokenPayload (any authenticated user)
    - require_admin -> TokenPayload (role == "admin")

File upload validators
    - sniff_image_mime(buf) -> str | None
    - validate_image_upload(buf, max_size_mb=20, max_w=10000, max_h=10000)
        -> ValidatedImage  (decoded PIL image, EXIF stripped, orientation applied)
    - sanitize_filename(name) -> str

Config (read from env at import time)
    - JWT_SECRET_KEY   (32+ chars, hard-fail if missing in non-dev)
    - JWT_ALGORITHM    (default HS256)
    - ACCESS_TOKEN_MINUTES (default 30)
    - REFRESH_TOKEN_DAYS   (default 7)
    - BCRYPT_ROUNDS    (default 12)
    - RATE_LIMIT_REDIS_URL (used by middleware)
    - ALLOWED_ORIGINS  (CSV, parsed into list)
    - ENVIRONMENT      (development | staging | production)

SQL injection note
==================
This codebase relies on SQLAlchemy parameterized queries / ORM. NEVER build
SQL via f-strings or .format(). If raw SQL is unavoidable, use
`text("... :param ...").bindparams(param=value)`.
"""

from __future__ import annotations

import hashlib
import hmac
import io
import logging
import os
import re
import secrets
import time
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Final, Literal, Optional, Tuple
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import bcrypt as _bcrypt
from jose import JWTError, jwt
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field

log = logging.getLogger("backend.security")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

ENVIRONMENT: Final[str] = os.getenv("ENVIRONMENT", "development").lower()
JWT_SECRET_KEY: Final[str] = os.getenv("JWT_SECRET_KEY", "")
JWT_ALGORITHM: Final[str] = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_MINUTES: Final[int] = int(os.getenv("ACCESS_TOKEN_MINUTES", "15"))
REFRESH_TOKEN_DAYS: Final[int] = int(os.getenv("REFRESH_TOKEN_DAYS", "7"))
BCRYPT_ROUNDS: Final[int] = int(os.getenv("BCRYPT_ROUNDS", "12"))
RATE_LIMIT_REDIS_URL: Final[str] = os.getenv(
    "RATE_LIMIT_REDIS_URL", os.getenv("REDIS_URL", "redis://redis:6379/1")
)
ALLOWED_ORIGINS: Final[list[str]] = [
    s.strip() for s in os.getenv("ALLOWED_ORIGINS", "").split(",") if s.strip()
]


def _validate_config() -> None:
    """Hard-fail on insecure config in staging/production."""
    if ENVIRONMENT in ("staging", "production"):
        if len(JWT_SECRET_KEY) < 32:
            raise RuntimeError(
                "JWT_SECRET_KEY must be at least 32 characters in non-dev environments"
            )
        if JWT_ALGORITHM != "HS256" and not JWT_ALGORITHM.startswith(("HS", "RS", "ES")):
            raise RuntimeError(f"Unsupported JWT_ALGORITHM: {JWT_ALGORITHM}")
    elif len(JWT_SECRET_KEY) < 32:
        log.warning(
            "JWT_SECRET_KEY is short or unset; OK only for local dev. "
            "Set a 32+ char secret before staging/production."
        )


_validate_config()


# Effective secret for dev convenience (random per-process if unset).
_EFFECTIVE_JWT_SECRET = JWT_SECRET_KEY or secrets.token_urlsafe(48)


# ---------------------------------------------------------------------------
# Password hashing (bcrypt, cost 12)
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Bcrypt hash a plaintext password. Cost factor from BCRYPT_ROUNDS (default 12).

    Note: uses the `bcrypt` package directly. We dropped passlib because
    passlib 1.7.4 (unmaintained since 2020) mis-detects bcrypt >= 4.x and
    raises a spurious "password cannot be longer than 72 bytes" error for
    every input.
    """
    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string")
    pw_bytes = password.encode("utf-8")
    # bcrypt has a 72-byte limit; reject overly long inputs to avoid silent truncation.
    if len(pw_bytes) > 72:
        raise ValueError("password exceeds 72 bytes (bcrypt limit)")
    salt = _bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return _bcrypt.hashpw(pw_bytes, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time bcrypt verification. Never logs the inputs."""
    if not plain or not hashed:
        return False
    try:
        return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

TokenType = Literal["access", "refresh"]


class TokenPayload(BaseModel):
    """Decoded JWT claims surfaced to handlers."""

    sub: str = Field(..., description="user_id as string")
    role: str = Field(default="user")
    type: TokenType = Field(default="access")
    iat: int
    exp: int
    jti: str

    @property
    def user_id(self) -> UUID:
        return UUID(self.sub)


def _build_token(
    *,
    user_id: UUID,
    role: str,
    token_type: TokenType,
    lifetime: timedelta,
) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": str(user_id),
        "role": role,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
        "jti": secrets.token_urlsafe(16),
        "iss": "arac-hasar-v2",
    }
    return jwt.encode(payload, _EFFECTIVE_JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_access_token(
    user_id: UUID, role: str, expires_minutes: int = ACCESS_TOKEN_MINUTES
) -> str:
    """Short-lived access token. Default 30 minutes."""
    return _build_token(
        user_id=user_id,
        role=role,
        token_type="access",
        lifetime=timedelta(minutes=expires_minutes),
    )


def create_refresh_token(user_id: UUID, expires_days: int = REFRESH_TOKEN_DAYS) -> str:
    """Long-lived refresh token. Default 7 days. Role is intentionally 'user' --
    privilege must be re-checked from DB on refresh."""
    return _build_token(
        user_id=user_id,
        role="user",
        token_type="refresh",
        lifetime=timedelta(days=expires_days),
    )


def verify_token(token: str, expected_type: str = "access") -> TokenPayload:
    """Decode + validate JWT. Raises 401 on any failure (expired, bad sig, wrong type)."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        claims = jwt.decode(
            token,
            _EFFECTIVE_JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["exp", "iat", "sub", "jti"]},
        )
    except JWTError as e:
        log.info("jwt.verify.fail reason=%s", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    try:
        payload = TokenPayload(**claims)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="malformed token payload",
        ) from None

    if payload.type != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"wrong token type (expected {expected_type})",
        )
    return payload


# ---------------------------------------------------------------------------
# API keys (for pilot integrations / service-to-service)
# ---------------------------------------------------------------------------

_API_KEY_PREFIX = "ahv2_"
_API_KEY_BYTES = 32  # 256 bits of entropy


def generate_api_key() -> Tuple[str, str]:
    """
    Generate a new API key. Returns (plain_key, hash_to_store).

    plain_key is shown to the user EXACTLY ONCE. Store only the hash.
    Hash is SHA-256 (fast, deterministic) -- API keys are already 256 bits
    of entropy, so bcrypt-style slow hashing is unnecessary.
    """
    raw = secrets.token_urlsafe(_API_KEY_BYTES)
    plain_key = f"{_API_KEY_PREFIX}{raw}"
    stored_hash = hashlib.sha256(plain_key.encode("utf-8")).hexdigest()
    return plain_key, stored_hash


def verify_api_key(plain_key: str, stored_hash: str) -> bool:
    """Constant-time comparison of plain key against stored sha256 hash."""
    if not plain_key or not stored_hash:
        return False
    if not plain_key.startswith(_API_KEY_PREFIX):
        return False
    computed = hashlib.sha256(plain_key.encode("utf-8")).hexdigest()
    return hmac.compare_digest(computed, stored_hash)


# ---------------------------------------------------------------------------
# FastAPI auth dependencies
# ---------------------------------------------------------------------------

_bearer = HTTPBearer(auto_error=False, description="JWT access token")


def _extract_token(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if creds.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid auth scheme",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return creds.credentials


def require_user(token: str = Depends(_extract_token)) -> TokenPayload:
    """FastAPI dependency: any authenticated user (access token)."""
    return verify_token(token, expected_type="access")


def require_admin(payload: TokenPayload = Depends(require_user)) -> TokenPayload:
    """FastAPI dependency: role == admin."""
    if payload.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin privileges required",
        )
    return payload


# ---------------------------------------------------------------------------
# File upload validation
# ---------------------------------------------------------------------------

# Magic-byte signatures. We do NOT trust client-provided Content-Type or filename.
_MAGIC_SIGS: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    # WEBP: "RIFF????WEBP" -- handled below
)

ALLOWED_IMAGE_MIMES: frozenset[str] = frozenset({"image/jpeg", "image/png", "image/webp"})
DEFAULT_MAX_UPLOAD_MB: Final[int] = 20
DEFAULT_MAX_DIM: Final[int] = 10_000


def sniff_image_mime(buf: bytes) -> Optional[str]:
    """Return the sniffed MIME type for the buffer, or None if unrecognized."""
    if not buf or len(buf) < 12:
        return None
    for sig, mime in _MAGIC_SIGS:
        if buf.startswith(sig):
            return mime
    # WEBP requires checking bytes 0..3 and 8..11
    if buf[0:4] == b"RIFF" and buf[8:12] == b"WEBP":
        return "image/webp"
    return None


@dataclass(frozen=True)
class ValidatedImage:
    """Result of validate_image_upload: decoded image + sanitized metadata."""

    image: Image.Image           # PIL image, EXIF stripped, orientation applied
    mime: str
    width: int
    height: int
    size_bytes: int
    sha256: str


def validate_image_upload(
    buf: bytes,
    *,
    max_size_mb: int = DEFAULT_MAX_UPLOAD_MB,
    max_w: int = DEFAULT_MAX_DIM,
    max_h: int = DEFAULT_MAX_DIM,
) -> ValidatedImage:
    """
    Validate and normalize an image upload.

    Steps:
      1. Size limit (default 20 MB).
      2. MIME sniff by magic bytes (jpeg/png/webp only).
      3. Decode with PIL. Reject on UnidentifiedImageError / DecompressionBombError.
      4. Apply EXIF orientation (so downstream ML sees the correct rotation).
      5. Strip EXIF metadata (PII: GPS, camera serial, timestamps).
      6. Dimension limits.

    Returns a ValidatedImage. Raises HTTPException(400/413) on rejection.
    """
    size_bytes = len(buf)
    max_bytes = max_size_mb * 1024 * 1024
    if size_bytes == 0:
        raise HTTPException(status_code=400, detail="empty upload")
    if size_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"file exceeds {max_size_mb} MB limit",
        )

    mime = sniff_image_mime(buf)
    if mime not in ALLOWED_IMAGE_MIMES:
        raise HTTPException(
            status_code=400,
            detail="unsupported image type (allowed: jpeg, png, webp)",
        )

    # Guard against decompression-bomb DoS.
    Image.MAX_IMAGE_PIXELS = max_w * max_h
    try:
        probe = Image.open(io.BytesIO(buf))
        probe.verify()  # cheap structural check
        img = Image.open(io.BytesIO(buf))  # reopen: verify() consumes the stream
        img = ImageOps.exif_transpose(img)  # apply orientation, then we'll drop EXIF
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        raise HTTPException(status_code=400, detail="invalid or corrupt image") from None

    if img.width > max_w or img.height > max_h:
        raise HTTPException(
            status_code=400,
            detail=f"image dimensions exceed {max_w}x{max_h}",
        )

    # Strip EXIF: create a clean copy without the info dict.
    clean = Image.new(img.mode, img.size)
    clean.putdata(list(img.getdata()))

    digest = hashlib.sha256(buf).hexdigest()
    return ValidatedImage(
        image=clean,
        mime=mime,
        width=img.width,
        height=img.height,
        size_bytes=size_bytes,
        sha256=digest,
    )


# Filename sanitizer ---------------------------------------------------------

_UNSAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def sanitize_filename(name: str, *, fallback_ext: str = "bin") -> str:
    """
    Produce a safe filename for S3/storage.

    Defenses:
      - No path components (basename only).
      - Strip null bytes and control chars.
      - Unicode normalize NFKD then drop non-ASCII.
      - Whitelist [A-Za-z0-9._-]; everything else -> "_".
      - Reject reserved Windows names just in case (CON, PRN, AUX, NUL, COM1..LPT9).
      - Cap length at 120 chars and ALWAYS prefix with a fresh uuid4 to prevent
        collisions and obscure user-controlled content from logs.
    """
    if not isinstance(name, str):
        name = "upload"
    # basename only -- defeats ../, absolute paths, backslashes.
    name = os.path.basename(name.replace("\\", "/"))
    # Strip nulls/control chars before normalization.
    name = name.replace("\x00", "")
    name = "".join(ch for ch in name if ch.isprintable())
    # Unicode normalize and drop non-ASCII.
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    # Whitelist.
    name = _UNSAFE_FILENAME_RE.sub("_", name).strip("._-") or f"upload.{fallback_ext}"
    # Reserved Windows names (belt + suspenders).
    stem = name.split(".", 1)[0].upper()
    if stem in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"(COM|LPT)[1-9]", stem):
        name = f"_{name}"
    if len(name) > 120:
        # keep extension
        root, dot, ext = name.rpartition(".")
        if dot and len(ext) <= 8:
            name = f"{root[: 120 - len(ext) - 1]}.{ext}"
        else:
            name = name[:120]
    return f"{uuid.uuid4().hex}_{name}"


# ---------------------------------------------------------------------------
# Helpers re-exported for middleware / handlers
# ---------------------------------------------------------------------------

def utcnow_ms() -> int:
    """Monotonic-ish wall-clock millisecond timestamp for access logs."""
    return int(time.time() * 1000)


__all__ = [
    # config
    "ENVIRONMENT",
    "JWT_ALGORITHM",
    "ACCESS_TOKEN_MINUTES",
    "REFRESH_TOKEN_DAYS",
    "BCRYPT_ROUNDS",
    "RATE_LIMIT_REDIS_URL",
    "ALLOWED_ORIGINS",
    # password
    "hash_password",
    "verify_password",
    # jwt
    "TokenPayload",
    "create_access_token",
    "create_refresh_token",
    "verify_token",
    # api keys
    "generate_api_key",
    "verify_api_key",
    # deps
    "require_user",
    "require_admin",
    # uploads
    "ValidatedImage",
    "ALLOWED_IMAGE_MIMES",
    "sniff_image_mime",
    "validate_image_upload",
    "sanitize_filename",
    # misc
    "utcnow_ms",
]
