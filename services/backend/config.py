"""
backend/config.py
Tum konfigurasyon environment variable'lardan gelir.

Pydantic v2 (pydantic-settings) tabanli, type-safe ve validated.
Eski API_KEYS surec disi kalmadi (geriye uyumluluk icin korunur),
artik JWT primary auth mekanizmasi.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

from typing import Annotated

from pydantic import AliasChoices, Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    # pydantic-settings >= 2.3 ships NoDecode helper to disable JSON parsing
    # for env-sourced list/dict fields (so 'a,b,c' stays as raw string for our validator).
    from pydantic_settings import NoDecode  # type: ignore[attr-defined]
    _CSVList = Annotated[List[str], NoDecode]
except ImportError:  # pragma: no cover
    _CSVList = List[str]  # type: ignore[misc,assignment]


# ---- Bundle / model snapshot ----
_DEFAULT_BUNDLE = "services/ml/runs/bundles/full_20260515_044630/_SNAPSHOT_FOR_BUILD"


class Settings(BaseSettings):
    """Backend ayarlari — .env dosyasi veya environment'tan okur."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- API meta ----
    api_version: str = "0.3.0"
    git_sha: str = "dev"
    build_time: str = "unknown"
    environment: str = "development"  # development|staging|production

    # ---- JWT auth ----
    # Production'da MUTLAKA cryptographically random 32+ byte degeri kullan.
    # security.py modulu tarihsel olarak JWT_SECRET_KEY env'i okuyordu; config
    # tarafi JWT_SECRET kullaniyordu. AliasChoices ile her iki adi da destekle
    # (render.yaml `generateValue: true` -> JWT_SECRET_KEY uretir).
    jwt_secret: str = Field(
        default="CHANGE-ME-DEV-SECRET-NOT-FOR-PRODUCTION-USE-32B",
        validation_alias=AliasChoices("JWT_SECRET", "JWT_SECRET_KEY"),
    )
    jwt_algorithm: str = "HS256"
    jwt_access_expiry_seconds: int = 60 * 15             # 15dk (kisaltildi)
    jwt_refresh_expiry_seconds: int = 60 * 60 * 24 * 7   # 7g (kisaltildi)

    # Legacy API key (frontend henuz JWT'ye tasinmadiysa fallback).
    # _CSVList: env'den 'a,b,c' string raw gelsin, validator CSV'i split etsin.
    api_keys: _CSVList = Field(default_factory=list)  # type: ignore[valid-type]

    # ---- CORS ----
    cors_origins: _CSVList = Field(  # type: ignore[valid-type]
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:1420",
            "http://tauri.localhost",
            "tauri://localhost",
            "http://localhost:8081",
            "http://localhost:19006",
        ]
    )
    cors_origin_regex: str = (
        r"^(https?://([a-z0-9-]+\.)*vercel\.app"
        r"|tauri://localhost"
        r"|http://tauri\.localhost"
        r"|capacitor://localhost"
        r"|http://localhost(:\d+)?)$"
    )

    # ---- ML pipeline ----
    damage_weights: str = f"{_DEFAULT_BUNDLE}/damage_best.pt"
    parts_weights: str = f"{_DEFAULT_BUNDLE}/parts_best.pt"
    severity_weights: str = f"{_DEFAULT_BUNDLE}/severity_best.pt"
    cost_table_path: str = "services/backend/cost_table.yaml"
    ml_device: str = "cuda"   # cuda|cpu|mps
    ml_imgsz: int = 640
    ml_warmup_on_startup: bool = True

    # ---- S3 storage ----
    # Render production: AWS S3 ya da Cloudflare R2. Dev: MinIO.
    s3_endpoint: str = "http://minio:9000"
    s3_public_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "inspections"
    s3_region: str = "us-east-1"
    s3_presign_expiry: int = 900  # 15dk
    s3_force_path_style: bool = True

    # ---- Database ----
    database_url: str = "postgresql://postgres:postgres@db:5432/arac_hasar"
    database_url_async: str = "postgresql+asyncpg://postgres:postgres@db:5432/arac_hasar"

    # ---- Redis / Celery / Pub-sub ----
    redis_url: str = "redis://redis:6379/0"
    redis_pubsub_url: Optional[str] = None  # None ise redis_url kullanilir

    # ---- Limits / quotas ----
    max_image_size_mb: int = 10
    max_images_sync: int = 5
    max_images_async: int = 20
    request_id_header: str = "X-Request-Id"

    # ---- WebSocket ----
    ws_max_duration_sec: int = 600  # 10dk hard limit
    ws_poll_interval_sec: float = 1.0

    # ---- Sentry / observability (opsiyonel) ----
    sentry_dsn: Optional[str] = None

    # -------- Validators / computed --------

    @field_validator("api_keys", "cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, v):
        """Env'den 'a,b,c' string gelebilir — listeye cevir."""
        if v is None or v == "":
            return []
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @field_validator("environment")
    @classmethod
    def _env_lower(cls, v: str) -> str:
        return (v or "development").lower()

    @field_validator("jwt_secret")
    @classmethod
    def _jwt_secret_hard_fail(cls, v: str) -> str:
        """Production/staging'de default placeholder veya kisa secret REDDEDILIR.
        Dev'de uyari ile gecirilir; security.py kendi rastgele per-process key'ini uretir.
        """
        env = (os.getenv("ENVIRONMENT") or "development").lower()
        placeholder = (
            not v
            or v.startswith("CHANGE-ME")
            or v.startswith("change_me")
            or len(v) < 32
        )
        if env in ("staging", "production") and placeholder:
            raise ValueError(
                "jwt_secret production/staging'de en az 32 karakter ve placeholder "
                "olmayan bir deger olmali (ornek: openssl rand -base64 48)."
            )
        return v

    @computed_field  # type: ignore[misc]
    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @computed_field  # type: ignore[misc]
    @property
    def dev_mode(self) -> bool:
        """Auth bypass moda zorla yalniz development'ta izin verilir."""
        return self.environment == "development" and len(self.api_keys) == 0

    @computed_field  # type: ignore[misc]
    @property
    def effective_redis_pubsub_url(self) -> str:
        return self.redis_pubsub_url or self.redis_url


@lru_cache(maxsize=1)
def _load() -> Settings:
    return Settings()


settings: Settings = _load()
