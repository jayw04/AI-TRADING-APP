"""benchmark_snapshots — reference index-fund daily-close series for the dashboard comparison.

Append-only operational telemetry (not hash-chained). Safe to apply on the existing DB — it only
creates a new table + index.

Revision ID: a7c4e1b9d3f2
Revises: b7f3a9c2e1d8
Create Date: 2026-07-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a7c4e1b9d3f2"
down_revision = "b7f3a9c2e1d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "benchmark_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("close", sa.Numeric(precision=18, scale=4), nullable=False),
    )
    op.create_index(
        "ix_benchmark_snapshots_symbol_ts", "benchmark_snapshots", ["symbol", "ts"]
    )


def downgrade() -> None:
    op.drop_index("ix_benchmark_snapshots_symbol_ts", table_name="benchmark_snapshots")
    op.drop_table("benchmark_snapshots")
