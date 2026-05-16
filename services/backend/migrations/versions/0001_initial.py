"""initial schema — users, inspections, images, damages, parts, api_keys, audit_log

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-15

Pilot-production icin baslangic schema'si. Tum tablolar, ENUM tipleri,
B-tree + partial index'ler ve check constraint'ler tek migration'da.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ENUM isimleri — drop sirasinda lazim
_ENUMS = (
    "user_role",
    "inspection_status",
    "inspection_mode",
    "damage_type",
    "severity_level",
)


def upgrade() -> None:
    # ---------------- Extensions ----------------
    # gen_random_uuid icin pgcrypto. (alternatif: uuid-ossp/uuid_generate_v4)
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # ---------------- ENUM types ----------------
    user_role = postgresql.ENUM(
        "admin", "user", name="user_role", create_type=False
    )
    user_role.create(op.get_bind(), checkfirst=True)

    inspection_status = postgresql.ENUM(
        "pending", "processing", "done", "failed",
        name="inspection_status", create_type=False,
    )
    inspection_status.create(op.get_bind(), checkfirst=True)

    inspection_mode = postgresql.ENUM(
        "sync", "async", name="inspection_mode", create_type=False
    )
    inspection_mode.create(op.get_bind(), checkfirst=True)

    damage_type = postgresql.ENUM(
        "dent", "scratch", "crack", "glass_shatter", "lamp_broken", "tire_flat",
        name="damage_type", create_type=False,
    )
    damage_type.create(op.get_bind(), checkfirst=True)

    severity_level = postgresql.ENUM(
        "hafif", "orta", "agir", name="severity_level", create_type=False
    )
    severity_level.create(op.get_bind(), checkfirst=True)

    # ---------------- users ----------------
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("role", user_role, nullable=False, server_default=sa.text("'user'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_users_email", "users", ["email"])
    op.create_index("idx_users_role", "users", ["role"])

    # ---------------- inspections ----------------
    op.create_table(
        "inspections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", inspection_status, nullable=False,
                  server_default=sa.text("'pending'")),
        sa.Column("mode", inspection_mode, nullable=False,
                  server_default=sa.text("'async'")),
        sa.Column("image_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.Column("model_versions", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    # FK + sort icin composite (created_at DESC)
    op.create_index(
        "idx_inspections_user_created",
        "inspections",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index("idx_inspections_status", "inspections", ["status"])
    # Aktif kuyruk taramasi icin partial index
    op.create_index(
        "idx_inspections_status_active",
        "inspections",
        ["status"],
        postgresql_where=sa.text("status IN ('pending', 'processing')"),
    )

    # ---------------- inspection_images ----------------
    op.create_table(
        "inspection_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("inspection_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("inspections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_idx", sa.SmallInteger(), nullable=False),
        sa.Column("s3_key", sa.String(512), nullable=False),
        sa.Column("original_filename", sa.String(512), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint("order_idx >= 0", name="ck_inspection_images_order_idx_nonneg"),
    )
    op.create_index(
        "idx_inspection_images_inspection_order",
        "inspection_images",
        ["inspection_id", "order_idx"],
        unique=True,
    )

    # ---------------- damages ----------------
    op.create_table(
        "damages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("inspection_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("inspections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("image_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("inspection_images.id", ondelete="CASCADE"), nullable=False),
        sa.Column("damage_type", damage_type, nullable=False),
        sa.Column("primary_part", sa.String(64), nullable=True),
        sa.Column("secondary_parts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("bbox", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("polygon", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("severity", severity_level, nullable=True),
        sa.Column("severity_confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("cost_min_tl", sa.Numeric(12, 2), nullable=True),
        sa.Column("cost_max_tl", sa.Numeric(12, 2), nullable=True),
        sa.Column("is_multi_part", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("is_low_confidence_match", sa.Boolean(), nullable=False,
                  server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_damages_confidence_range",
        ),
        sa.CheckConstraint(
            "severity_confidence IS NULL OR (severity_confidence >= 0 AND severity_confidence <= 1)",
            name="ck_damages_severity_confidence_range",
        ),
        sa.CheckConstraint(
            "cost_min_tl IS NULL OR cost_max_tl IS NULL OR cost_min_tl <= cost_max_tl",
            name="ck_damages_cost_range",
        ),
    )
    op.create_index("idx_damages_inspection", "damages", ["inspection_id"])
    op.create_index("idx_damages_image", "damages", ["image_id"])
    op.create_index("idx_damages_type", "damages", ["damage_type"])
    op.create_index("idx_damages_severity", "damages", ["severity"])

    # ---------------- parts ----------------
    op.create_table(
        "parts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("inspection_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("inspections.id", ondelete="CASCADE"), nullable=False),
        sa.Column("image_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("inspection_images.id", ondelete="CASCADE"), nullable=False),
        sa.Column("part_name", sa.String(64), nullable=False),
        sa.Column("bbox", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("polygon", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_parts_confidence_range",
        ),
    )
    op.create_index("idx_parts_inspection", "parts", ["inspection_id"])
    op.create_index("idx_parts_image", "parts", ["image_id"])
    op.create_index("idx_parts_name", "parts", ["part_name"])

    # ---------------- api_keys ----------------
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index("idx_api_keys_user", "api_keys", ["user_id"])
    op.create_index(
        "idx_api_keys_active",
        "api_keys",
        ["key_hash"],
        postgresql_where=sa.text("is_active = true"),
    )

    # ---------------- audit_log ----------------
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=True),
        sa.Column("resource_id", sa.String(128), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index(
        "idx_audit_log_user_created",
        "audit_log",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index("idx_audit_log_action", "audit_log", ["action"])
    op.create_index(
        "idx_audit_log_resource", "audit_log", ["resource_type", "resource_id"]
    )


def downgrade() -> None:
    # Tablolari FK bagimliligi ters sirasi ile dusur
    op.drop_index("idx_audit_log_resource", table_name="audit_log")
    op.drop_index("idx_audit_log_action", table_name="audit_log")
    op.drop_index("idx_audit_log_user_created", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("idx_api_keys_active", table_name="api_keys")
    op.drop_index("idx_api_keys_user", table_name="api_keys")
    op.drop_table("api_keys")

    op.drop_index("idx_parts_name", table_name="parts")
    op.drop_index("idx_parts_image", table_name="parts")
    op.drop_index("idx_parts_inspection", table_name="parts")
    op.drop_table("parts")

    op.drop_index("idx_damages_severity", table_name="damages")
    op.drop_index("idx_damages_type", table_name="damages")
    op.drop_index("idx_damages_image", table_name="damages")
    op.drop_index("idx_damages_inspection", table_name="damages")
    op.drop_table("damages")

    op.drop_index("idx_inspection_images_inspection_order", table_name="inspection_images")
    op.drop_table("inspection_images")

    op.drop_index("idx_inspections_status_active", table_name="inspections")
    op.drop_index("idx_inspections_status", table_name="inspections")
    op.drop_index("idx_inspections_user_created", table_name="inspections")
    op.drop_table("inspections")

    op.drop_index("idx_users_role", table_name="users")
    op.drop_index("idx_users_email", table_name="users")
    op.drop_table("users")

    # ENUM tiplerini son sirada dusur
    for enum_name in _ENUMS:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
