"""P5 §8: audit_log immutability — row_hash/prev_hash + append-only triggers

Adds the hash-chain columns, backfills them for existing rows (per-user chain,
in id order), then installs the storage-layer triggers that block UPDATE and
DELETE. Order matters: the backfill UPDATEs row_hash, so it must run BEFORE the
no_update trigger exists.

Revision ID: f2a7c1d9e4b6
Revises: e1f6b4c9a8d3
Create Date: 2026-06-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.observability.audit_hash import compute_row_hash

# revision identifiers, used by Alembic.
revision = "f2a7c1d9e4b6"
down_revision = "e1f6b4c9a8d3"
branch_labels = None
depends_on = None


_NO_UPDATE_TRIGGER = (
    "CREATE TRIGGER IF NOT EXISTS audit_log_no_update "
    "BEFORE UPDATE ON audit_log "
    "BEGIN SELECT RAISE(ABORT, 'audit_log is append-only; UPDATE forbidden'); END;"
)
_NO_DELETE_TRIGGER = (
    "CREATE TRIGGER IF NOT EXISTS audit_log_no_delete "
    "BEFORE DELETE ON audit_log "
    "BEGIN SELECT RAISE(ABORT, 'audit_log is append-only; DELETE forbidden'); END;"
)


def upgrade() -> None:
    # 1. Columns. row_hash is NOT NULL; a temporary server_default lets us add it
    #    to a populated table, then we backfill real hashes and drop the default.
    op.add_column(
        "audit_log",
        sa.Column("row_hash", sa.String(64), nullable=False, server_default=""),
    )
    op.add_column(
        "audit_log",
        sa.Column("prev_hash", sa.String(64), nullable=True),
    )

    # 2. Backfill the per-user chain in id order. Runs BEFORE the triggers, so
    #    these UPDATEs are permitted. Hashing is not available in SQLite without
    #    an extension, so we do it in Python.
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, user_id, actor_type, actor_id, action, "
            "target_type, target_id, payload_json, ts "
            "FROM audit_log ORDER BY id"
        )
    ).fetchall()
    per_user_prev: dict[int | None, str | None] = {}
    for row in rows:
        prev_hash = per_user_prev.get(row.user_id)
        row_hash = compute_row_hash(
            user_id=row.user_id,
            actor_type=row.actor_type,
            actor_id=row.actor_id,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            payload_json=row.payload_json,
            ts=row.ts,
            prev_hash=prev_hash,
        )
        conn.execute(
            sa.text("UPDATE audit_log SET row_hash = :rh, prev_hash = :ph WHERE id = :id"),
            {"rh": row_hash, "ph": prev_hash, "id": row.id},
        )
        per_user_prev[row.user_id] = row_hash

    # 3. Drop the temporary server_default now that every row has a real hash.
    with op.batch_alter_table("audit_log") as batch:
        batch.alter_column("row_hash", server_default=None)

    # 4. Triggers — block UPDATE and DELETE at the storage layer.
    op.execute(_NO_UPDATE_TRIGGER)
    op.execute(_NO_DELETE_TRIGGER)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_update;")
    op.execute("DROP TRIGGER IF EXISTS audit_log_no_delete;")
    with op.batch_alter_table("audit_log") as batch:
        batch.drop_column("prev_hash")
        batch.drop_column("row_hash")
