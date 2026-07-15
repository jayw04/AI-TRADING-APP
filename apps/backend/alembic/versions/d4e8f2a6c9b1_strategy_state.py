"""strategy_state — durable per-strategy key/value state (Workstream B prerequisite)

Revision ID: d4e8f2a6c9b1
Revises: a4c7e1f9d2b8
Create Date: 2026-07-14

One row per (strategy_id, key); JSON value. Enables the Workstream B daily-evaluation lifecycle
(signal_date / attempted_at / completed_at, backstop review date, once-per-day latch) to survive
restarts and reloads. Reviewed by hand: single head (a4c7e1f9d2b8 — re-parented onto the current
main head; confirmed via `alembic heads`, not a regex), clean down_revision, no destructive
operation, FK cascade to strategies. Verified `upgrade head` applies only this step on a4c7.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "d4e8f2a6c9b1"
down_revision = "a4c7e1f9d2b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("strategy_id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("strategy_id", "key", name="uq_strategy_state_strategy_key"),
    )
    op.create_index(
        "ix_strategy_state_strategy_id", "strategy_state", ["strategy_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_strategy_state_strategy_id", table_name="strategy_state")
    op.drop_table("strategy_state")
