"""
backend/db_models.py
SQLAlchemy 2.0 ORM modelleri — pilot-production schema.

Tasarim notlari:
  - Tum PK'lar UUID (server-side: gen_random_uuid via pgcrypto).
  - JSONB tercih edildi (bbox/polygon/metadata/secondary_parts) — Postgres native.
  - ENUM tipleri PG native ENUM (alembic migration'da CREATE TYPE).
  - Foreign key cascade davranisi: user silinince audit_log + inspection da silinir
    (pilot icin acceptable; production'da soft-delete dusunulebilir).
  - Tum FK kolonlar indekslenir; sik kullanilan filter+sort'lar icin composite +
    partial index'ler eklenmistir.

Import:
    from db_models import (
        Base, User, UserRole,
        Inspection, InspectionStatus, InspectionMode,
        InspectionImage, Damage, DamageType, Severity,
        Part, ApiKey, AuditLog,
    )
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


# ---------------- Enums (Postgres native) ----------------

class UserRole(str):
    ADMIN = "admin"
    USER = "user"


user_role_enum = SAEnum(
    "admin",
    "user",
    name="user_role",
    create_type=False,  # Alembic migration ENUM'u manuel create eder
    validate_strings=True,
)


class InspectionStatus(str):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


inspection_status_enum = SAEnum(
    "pending",
    "processing",
    "done",
    "failed",
    name="inspection_status",
    create_type=False,
    validate_strings=True,
)


class InspectionMode(str):
    SYNC = "sync"
    ASYNC = "async"


inspection_mode_enum = SAEnum(
    "sync",
    "async",
    name="inspection_mode",
    create_type=False,
    validate_strings=True,
)


class DamageType(str):
    DENT = "dent"
    SCRATCH = "scratch"
    CRACK = "crack"
    GLASS_SHATTER = "glass_shatter"
    LAMP_BROKEN = "lamp_broken"
    TIRE_FLAT = "tire_flat"


damage_type_enum = SAEnum(
    "dent",
    "scratch",
    "crack",
    "glass_shatter",
    "lamp_broken",
    "tire_flat",
    name="damage_type",
    create_type=False,
    validate_strings=True,
)


class Severity(str):
    HAFIF = "hafif"
    ORTA = "orta"
    AGIR = "agir"


severity_enum = SAEnum(
    "hafif",
    "orta",
    "agir",
    name="severity_level",
    create_type=False,
    validate_strings=True,
)


# ---------------- Helpers ----------------

def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


def _now() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


# ---------------- User ----------------

class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(
        user_role_enum, nullable=False, server_default=text("'user'")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    inspections: Mapped[list[Inspection]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    api_keys: Mapped[list[ApiKey]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(
        back_populates="user", passive_deletes=True
    )

    __table_args__ = (
        # email unique constraint zaten unique=True ile gelir; ek B-tree index
        # case-insensitive arama icin ileride lower(email) functional index eklenebilir.
        Index("idx_users_email", "email"),
        Index("idx_users_role", "role"),
    )


# ---------------- Inspection ----------------

class Inspection(Base):
    __tablename__ = "inspections"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        inspection_status_enum, nullable=False, server_default=text("'pending'")
    )
    mode: Mapped[str] = mapped_column(
        inspection_mode_enum, nullable=False, server_default=text("'async'")
    )
    image_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    created_at: Mapped[datetime] = _now()
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_duration_ms: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True
    )
    error_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_versions: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSONB, nullable=True
    )

    # Relationships
    user: Mapped[User] = relationship(back_populates="inspections")
    images: Mapped[list[InspectionImage]] = relationship(
        back_populates="inspection",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="InspectionImage.order_idx",
    )
    damages: Mapped[list[Damage]] = relationship(
        back_populates="inspection",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    parts: Mapped[list[Part]] = relationship(
        back_populates="inspection",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        # NOT: created_at DESC siralamasi ile pagination (history listesi) icin.
        # Migration 0001'de zaten DESC olusturuluyor; modeli hizalamak icin text() kullanildi.
        Index("idx_inspections_user_created", "user_id", text("created_at DESC")),
        # Aktif inspection'lar icin partial index — kuyruk taramasi O(active).
        Index(
            "idx_inspections_status_active",
            "status",
            postgresql_where=text("status IN ('pending', 'processing')"),
        ),
        Index("idx_inspections_status", "status"),
        # JSONB sutunlarinda nested sorgu (model_versions ->> 'detector') hizlandirmak icin GIN.
        Index(
            "idx_inspections_model_versions_gin",
            "model_versions",
            postgresql_using="gin",
        ),
        # Completed_at gore "son tamamlanan" sorgular icin partial DESC index.
        Index(
            "idx_inspections_completed_at",
            text("completed_at DESC"),
            postgresql_where=text("status = 'done'"),
        ),
    )


# ---------------- InspectionImage ----------------

class InspectionImage(Base):
    __tablename__ = "inspection_images"

    id: Mapped[uuid.UUID] = _uuid_pk()
    inspection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inspections.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_idx: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    s3_key: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)

    created_at: Mapped[datetime] = _now()

    inspection: Mapped[Inspection] = relationship(back_populates="images")
    damages: Mapped[list[Damage]] = relationship(
        back_populates="image", cascade="all, delete-orphan", passive_deletes=True
    )
    parts: Mapped[list[Part]] = relationship(
        back_populates="image", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        Index(
            "idx_inspection_images_inspection_order",
            "inspection_id",
            "order_idx",
            unique=True,
        ),
        CheckConstraint("order_idx >= 0", name="ck_inspection_images_order_idx_nonneg"),
    )


# ---------------- Damage ----------------

class Damage(Base):
    __tablename__ = "damages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    inspection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inspections.id", ondelete="CASCADE"),
        nullable=False,
    )
    image_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inspection_images.id", ondelete="CASCADE"),
        nullable=False,
    )

    damage_type: Mapped[str] = mapped_column(damage_type_enum, nullable=False)
    primary_part: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    secondary_parts: Mapped[Optional[list[str]]] = mapped_column(JSONB, nullable=True)

    bbox: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    polygon: Mapped[Optional[list[list[float]]]] = mapped_column(JSONB, nullable=True)

    confidence: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False
    )  # 0.0000 - 1.0000
    severity: Mapped[Optional[str]] = mapped_column(severity_enum, nullable=True)
    severity_confidence: Mapped[Optional[float]] = mapped_column(
        Numeric(5, 4), nullable=True
    )

    cost_min_tl: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    cost_max_tl: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)

    is_multi_part: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_low_confidence_match: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )

    created_at: Mapped[datetime] = _now()

    inspection: Mapped[Inspection] = relationship(back_populates="damages")
    image: Mapped[InspectionImage] = relationship(back_populates="damages")

    __table_args__ = (
        Index("idx_damages_inspection", "inspection_id"),
        Index("idx_damages_image", "image_id"),
        Index("idx_damages_type", "damage_type"),
        Index("idx_damages_severity", "severity"),
        # GIN: bbox/polygon/secondary_parts uzerinde @> containment ve ->> aramalari icin.
        Index(
            "idx_damages_secondary_parts_gin",
            "secondary_parts",
            postgresql_using="gin",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_damages_confidence_range",
        ),
        CheckConstraint(
            "severity_confidence IS NULL OR (severity_confidence >= 0 AND severity_confidence <= 1)",
            name="ck_damages_severity_confidence_range",
        ),
        CheckConstraint(
            "cost_min_tl IS NULL OR cost_max_tl IS NULL OR cost_min_tl <= cost_max_tl",
            name="ck_damages_cost_range",
        ),
    )


# ---------------- Part ----------------

class Part(Base):
    __tablename__ = "parts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    inspection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inspections.id", ondelete="CASCADE"),
        nullable=False,
    )
    image_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inspection_images.id", ondelete="CASCADE"),
        nullable=False,
    )

    part_name: Mapped[str] = mapped_column(String(64), nullable=False)
    bbox: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    polygon: Mapped[Optional[list[list[float]]]] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)

    created_at: Mapped[datetime] = _now()

    inspection: Mapped[Inspection] = relationship(back_populates="parts")
    image: Mapped[InspectionImage] = relationship(back_populates="parts")

    __table_args__ = (
        Index("idx_parts_inspection", "inspection_id"),
        Index("idx_parts_image", "image_id"),
        Index("idx_parts_name", "part_name"),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_parts_confidence_range",
        ),
    )


# ---------------- ApiKey ----------------

class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = _now()
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    user: Mapped[User] = relationship(back_populates="api_keys")

    __table_args__ = (
        Index("idx_api_keys_user", "user_id"),
        # Aktif anahtarlar uzerinde sorgu icin partial index
        Index(
            "idx_api_keys_active",
            "key_hash",
            postgresql_where=text("is_active = true"),
        ),
    )


# ---------------- AuditLog ----------------

class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = _uuid_pk()
    # Audit log icin SET NULL: user silinse bile log kaydi tutulur (compliance).
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    # Pydantic v2 / TS uyumu icin alan adi "metadata" — ancak SQLAlchemy
    # `MetaData` ile karismamasi icin attribute "extra_metadata" yapildi ve
    # kolonu "metadata" olarak adlandirildi.
    extra_metadata: Mapped[Optional[dict[str, Any]]] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    ip_address: Mapped[Optional[str]] = mapped_column(INET, nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = _now()

    user: Mapped[Optional[User]] = relationship(back_populates="audit_logs")

    __table_args__ = (
        # created_at DESC: audit log her zaman tersten okunur.
        Index("idx_audit_log_user_created", "user_id", text("created_at DESC")),
        Index("idx_audit_log_action", "action"),
        Index("idx_audit_log_resource", "resource_type", "resource_id"),
        # JSONB metadata uzerinde sorgu (action filter + payload arama) icin GIN.
        # NOT: Index'e string ad verirken SQLAlchemy kolon adina (ORM attribute
        # degil) bakar. extra_metadata attribute'unun gercek kolonu "metadata"
        # (mapped_column'da rename edildi); GIN bu isim uzerinde tanimlanir.
        Index(
            "idx_audit_log_metadata_gin",
            "metadata",
            postgresql_using="gin",
        ),
    )


__all__ = [
    "Base",
    "User",
    "UserRole",
    "Inspection",
    "InspectionStatus",
    "InspectionMode",
    "InspectionImage",
    "Damage",
    "DamageType",
    "Severity",
    "Part",
    "ApiKey",
    "AuditLog",
]
