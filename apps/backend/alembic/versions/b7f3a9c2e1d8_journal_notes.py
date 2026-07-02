"""journal_notes table (+ merge the two open alembic heads)

Revision ID: b7f3a9c2e1d8
Revises: f2a7c1d9e4b6, f3a1c7e9b2d4
Create Date: 2026-07-02

Adds ``journal_notes`` (one free-text note per order) for the Trade Journal page.

This migration also serves as a MERGE POINT. ``main`` had two open Alembic heads
— ``f2a7c1d9e4b6`` (P5 §8 audit-log immutability) and ``f3a1c7e9b2d4`` (scheduler
heartbeat, ADR 0032) — so ``alembic upgrade head`` would fail with "multiple head
revisions". Depending on both unifies the tree to a single head again.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b7f3a9c2e1d8"
down_revision = ("f2a7c1d9e4b6", "f3a1c7e9b2d4")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "journal_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_id", name="uq_journal_notes_order_id"),
    )
    op.create_index("ix_journal_notes_user_id", "journal_notes", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_journal_notes_user_id", table_name="journal_notes")
    op.drop_table("journal_notes")
