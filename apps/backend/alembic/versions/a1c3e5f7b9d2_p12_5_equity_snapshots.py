"""P12.5: equity_snapshots — append-only equity time series per account.

The history behind `accounts_state` (which is point-in-time): one append per account per snapshot
tick, so the live book's equity curve + realized vol/drawdown/return can be reported (Production
Validation). Operational telemetry, not hash-chained. Purely additive.

Revision ID: a1c3e5f7b9d2
Revises: c4e9a2b7d1f3
Create Date: 2026-06-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a1c3e5f7b9d2"
down_revision = "c4e9a2b7d1f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "equity_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(),
                  sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("equity", sa.Numeric(18, 4), nullable=False),
        sa.Column("cash", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("portfolio_value", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("day_change_pct", sa.Numeric(10, 6), nullable=False, server_default="0"),
    )
    op.create_index("ix_equity_snapshots_account_ts", "equity_snapshots", ["account_id", "ts"])


def downgrade() -> None:
    op.drop_index("ix_equity_snapshots_account_ts", table_name="equity_snapshots")
    op.drop_table("equity_snapshots")
