"""P6b s2a: paper-variant parent_strategy_id

Single additive change: ``strategies.parent_strategy_id`` — a nullable self-FK.
When set, the row is a paper-variant clone of the parent (status=PAPER_VARIANT),
spawned to validate a proposal's params forward on paper (ADR 0007). NULL for
normal user strategies; the discriminator that hides variants from user-facing
strategy lists.

The new ``StrategyStatus.PAPER_VARIANT`` + ``ProposalState.EVALUATING`` enum
values are app-level only (``SQLEnum(native_enum=False)`` stores strings in a
VARCHAR; new members need no DB change, and both fit the ``length=16`` columns).

Revision ID: c5e1a2b3f4d6
Revises: a3d9f1c4b7e2
Create Date: 2026-06-03

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5e1a2b3f4d6"
down_revision: str | Sequence[str] | None = "a3d9f1c4b7e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("strategies", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("parent_strategy_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_strategies_parent_strategy_id",
            "strategies",
            ["parent_strategy_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_strategies_parent_strategy_id", ["parent_strategy_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("strategies", schema=None) as batch_op:
        batch_op.drop_index("ix_strategies_parent_strategy_id")
        batch_op.drop_constraint(
            "fk_strategies_parent_strategy_id", type_="foreignkey"
        )
        batch_op.drop_column("parent_strategy_id")
