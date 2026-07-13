"""strategy_slot_claims: durable one-run-per-scheduled-slot control

Revision ID: d3f6a1c8b2e4
Revises: b5c7d9e1f3a5
Create Date: 2026-07-13

Incident 2026-07-13: momentum-portfolio executed its 10:00 ET slot SIX times in 52 seconds,
re-proposing the same SNDK/LITE trims on each pass. The in-process guard is not a safety
boundary — it does not survive a restart and is not evidence after the fact.

The UNIQUE constraint below IS the control. It is not an index for speed.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d3f6a1c8b2e4"
down_revision = "b5c7d9e1f3a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_slot_claims",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("strategy_id", sa.Integer(), nullable=False),
        sa.Column("scheduled_slot", sa.String(length=32), nullable=False),
        sa.Column("strategy_version", sa.String(length=32), nullable=False),
        sa.Column("retry_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retry_reason", sa.Text(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=False, server_default="RUNNING"),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id",
            "strategy_id",
            "scheduled_slot",
            "strategy_version",
            "retry_generation",
            name="uq_strategy_slot_claim",
        ),
    )
    op.create_index(
        "ix_strategy_slot_claims_strategy_slot",
        "strategy_slot_claims",
        ["strategy_id", "scheduled_slot"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_strategy_slot_claims_strategy_slot", table_name="strategy_slot_claims"
    )
    op.drop_table("strategy_slot_claims")
