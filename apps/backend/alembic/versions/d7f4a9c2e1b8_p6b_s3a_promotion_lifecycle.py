"""P6b s3a: promotion lifecycle + last_promoted_at

Single additive column: ``strategies.last_promoted_at`` — a nullable timestamp
recording when this strategy was last promoted from a paper variant (ADR 0007).
Defined in §3a; §3b's promotion endpoint sets it and the 30-day post-promotion
lockout reads it. NULL = never promoted.

The three new ``ProposalState`` values (EVIDENCE_READY / PROMOTING / PROMOTED)
and the ``AuditAction.STRATEGY_PROMOTED`` value are app-level only
(``SQLEnum(native_enum=False)`` / ``StrEnum`` store strings in a VARCHAR; new
members need no DB change, and EVIDENCE_READY fits the ``length=16`` column) —
same pattern as the c5e1a2b3f4d6 PAPER_VARIANT/EVALUATING additions.

Revision ID: d7f4a9c2e1b8
Revises: c5e1a2b3f4d6
Create Date: 2026-06-04

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7f4a9c2e1b8"
down_revision: str | Sequence[str] | None = "c5e1a2b3f4d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("strategies", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("last_promoted_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("strategies", schema=None) as batch_op:
        batch_op.drop_column("last_promoted_at")
