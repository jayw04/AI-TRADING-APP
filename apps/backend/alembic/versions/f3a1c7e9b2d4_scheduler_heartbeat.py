"""scheduler_heartbeat — armed-host observability for the single-scheduler invariant (ADR 0032).

One row per host; the armed scheduler upserts its beat. Purely additive operational telemetry
(not hash-chained). Safe to apply on the existing laptop DB — it only creates a new table.

Revision ID: f3a1c7e9b2d4
Revises: e7b2c9d4f1a6
Create Date: 2026-06-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "f3a1c7e9b2d4"
down_revision = "e7b2c9d4f1a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduler_heartbeat",
        sa.Column("host_id", sa.String(), primary_key=True),
        sa.Column("armed", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("last_beat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_dispatch_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("code_version", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("scheduler_heartbeat")
