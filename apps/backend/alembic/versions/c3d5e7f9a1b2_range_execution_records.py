"""range_execution_records — Range Trader daily execution vs. the stock's daily high/low.

Append-only operational telemetry (not hash-chained). Safe to apply on the existing DB — it only
creates a new table + a unique (symbol, et_date) constraint.

Revision ID: c3d5e7f9a1b2
Revises: a7c4e1b9d3f2
Create Date: 2026-07-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c3d5e7f9a1b2"
down_revision = "a7c4e1b9d3f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "range_execution_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("et_date", sa.Date(), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("avg_buy_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("avg_sell_price", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("daily_low", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("daily_high", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "symbol", "et_date", name="uq_range_execution_records_symbol_et_date"
        ),
    )


def downgrade() -> None:
    op.drop_table("range_execution_records")
