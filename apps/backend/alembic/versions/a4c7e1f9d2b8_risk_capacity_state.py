"""ADR 0042 §D — durable cross-process reducible-capacity claim

The process-local ``asyncio.Lock`` that previously guarded classify→reserve→persist protected
nothing across processes. Two independent Python processes each read ``reserved = 0`` and each
received ALLOW for the same 183 shares; only the broker prevented the double reduction. The broker
is not a safety mechanism.

This adds the capacity row that the claim compare-and-swaps against, and binds the resulting
capacity version onto the decision ledger so an audit can reconstruct which capacity version each
decision consumed.

Revision ID: a4c7e1f9d2b8
Revises: f7a3d1e9c5b2
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision = "a4c7e1f9d2b8"
down_revision = "f7a3d1e9c5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "risk_capacity_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("snapshot_version", sa.String(length=64), nullable=False),
        sa.Column(
            "reducible_capacity_qty",
            sa.Numeric(20, 8),
            nullable=False,
            server_default="0",
        ),
        sa.Column("reserved_qty", sa.Numeric(20, 8), nullable=False, server_default="0"),
        sa.Column("state_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        # One row per (account, symbol). This constraint controls IDENTITY — it is deliberately
        # NOT the aggregate-quantity guard, which no unique index can express. The aggregate
        # invariant (sum of held reductions <= reducible capacity) is enforced by the conditional
        # UPDATE in RiskDecisionService._claim_capacity.
        sa.UniqueConstraint(
            "account_id", "symbol", name="uq_risk_capacity_account_symbol"
        ),
    )
    op.create_index(
        "ix_risk_capacity_state_account_id", "risk_capacity_state", ["account_id"]
    )

    with op.batch_alter_table("risk_decisions") as batch:
        batch.add_column(sa.Column("capacity_state_version", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("risk_decisions") as batch:
        batch.drop_column("capacity_state_version")
    op.drop_index("ix_risk_capacity_state_account_id", table_name="risk_capacity_state")
    op.drop_table("risk_capacity_state")
