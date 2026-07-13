"""risk_decisions: append-only risk-decision ledger (ADR 0042 § 7)

Revision ID: e5b2c9d7f1a3
Revises: d3f6a1c8b2e4
Create Date: 2026-07-13

Rejected orders are not persisted anywhere. On 2026-07-13 the `orders` table showed zero rows
for account 1 while the momentum book was in fact having eighteen proposals refused, and the
investigation reached the wrong conclusion twice before the `signals` table gave it up by
accident.

Written for ALLOW and REJECT alike. An order that never existed because a gate refused it is
exactly the event you most need a record of.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e5b2c9d7f1a3"
down_revision = "d3f6a1c8b2e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "risk_decisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("strategy_id", sa.Integer(), nullable=True),
        sa.Column("strategy_version", sa.String(length=32), nullable=True),
        sa.Column("slot_claim_id", sa.Integer(), nullable=True),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("action_type", sa.String(length=16), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("order_group_id", sa.String(length=64), nullable=True),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=True),
        sa.Column("qty", sa.Numeric(20, 8), nullable=True),
        sa.Column("lock_state", sa.String(length=24), nullable=False),
        sa.Column("lock_reason", sa.String(length=64), nullable=True),
        sa.Column("daily_pnl", sa.Numeric(20, 4), nullable=True),
        sa.Column("risk_policy_version", sa.String(length=16), nullable=False),
        sa.Column("before_state_hash", sa.String(length=64), nullable=False),
        sa.Column("projected_after_state_hash", sa.String(length=64), nullable=True),
        sa.Column("broker_cursor", sa.String(length=64), nullable=True),
        sa.Column("position_qty_before", sa.Numeric(20, 8), nullable=True),
        sa.Column("position_qty_after", sa.Numeric(20, 8), nullable=True),
        sa.Column("gross_exposure_before", sa.Numeric(20, 4), nullable=True),
        sa.Column("gross_exposure_after", sa.Numeric(20, 4), nullable=True),
        sa.Column("leverage_before", sa.Numeric(12, 6), nullable=True),
        sa.Column("leverage_after", sa.Numeric(12, 6), nullable=True),
        sa.Column("available_reducible_qty", sa.Numeric(20, 8), nullable=True),
        sa.Column("risk_effect", sa.String(length=20), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("reason_codes", sa.Text(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("supersedes_id", sa.Integer(), nullable=True),
        sa.Column("retry_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["slot_claim_id"], ["strategy_slot_claims.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["supersedes_id"], ["risk_decisions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_risk_decisions_account_decided", "risk_decisions", ["account_id", "decided_at"]
    )
    op.create_index("ix_risk_decisions_correlation", "risk_decisions", ["correlation_id"])


def downgrade() -> None:
    op.drop_index("ix_risk_decisions_correlation", table_name="risk_decisions")
    op.drop_index("ix_risk_decisions_account_decided", table_name="risk_decisions")
    op.drop_table("risk_decisions")
