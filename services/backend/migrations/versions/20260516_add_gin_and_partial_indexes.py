"""add GIN indexes on JSONB columns + partial completed_at index

Revision ID: 20260516_idx
Revises: 0001_initial
Create Date: 2026-05-16

Amac:
  - JSONB sutunlarinda containment/`->>`/`@>` sorgulari icin GIN index.
  - "Son tamamlanan inspection'lar" icin partial DESC index.

Operasyonel notlar:
  - Index'ler `CONCURRENTLY` ile olusturulur — uretim tablolarini KILITLEMEZ.
  - CONCURRENTLY transaction bloku icinde calismaz: bu nedenle
    `op.execute("COMMIT")` ile autocommit moduna geciyoruz; downgrade'de de ayni.
  - `IF NOT EXISTS` ile idempotent: ayni migration tekrar calistirilirsa bozulmaz.
  - Hicbir tablo DROP/RENAME/ALTER edilmez; sadece yeni index'ler eklenir.

Sema breaking degisiklik YOK. Veri silme YOK.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260516_idx"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (index_name, table, definition) — definition CREATE INDEX gondesi disindaki kisim.
_INDEXES = (
    (
        "idx_inspections_model_versions_gin",
        "inspections",
        "USING gin (model_versions)",
    ),
    (
        "idx_damages_secondary_parts_gin",
        "damages",
        "USING gin (secondary_parts)",
    ),
    (
        "idx_damages_bbox_gin",
        "damages",
        "USING gin (bbox)",
    ),
    (
        "idx_parts_bbox_gin",
        "parts",
        "USING gin (bbox)",
    ),
    (
        "idx_audit_log_metadata_gin",
        "audit_log",
        'USING gin ("metadata")',
    ),
    (
        "idx_inspections_completed_at",
        "inspections",
        "(completed_at DESC) WHERE status = 'done'",
    ),
)


def upgrade() -> None:
    # CONCURRENTLY transaction icinde calisamaz: alembic'in default begin/commit
    # bloundan cikip autocommit moduna geciyoruz.
    op.execute("COMMIT")
    for name, table, definition in _INDEXES:
        op.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} {definition}"
        )


def downgrade() -> None:
    op.execute("COMMIT")
    # Ters sirada dusur (kritik degil ama tutarli)
    for name, _table, _definition in reversed(_INDEXES):
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
