"""risk_reservations: exposure reservations (ADR 0042 § D)

Revision ID: f7a3d1e9c5b2
Revises: e5b2c9d7f1a3
Create Date: 2026-07-13

Two concurrent sells of 300 against a long of 500 each pass the zero-crossing check in
isolation and TOGETHER create a 100-share short. Capacity is only real if an approval consumes
it, so an approved reduction reserves the quantity it was approved for.

Separate from `risk_decisions` on purpose: the ledger is append-only (a decision is a historical
fact), while a reservation has a lifecycle (held -> consumed | released). Mixing a mutable
lifecycle into an immutable ledger would quietly destroy the ledger's central property.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f7a3d1e9c5b2"
down_revision = "e5b2c9d7f1a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "risk_reservations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("qty", sa.Numeric(20, 8), nullable=False),
        sa.Column("decision_id", sa.Integer(), nullable=True),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("state", sa.String(length=12), nullable=False, server_default="HELD"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("release_reason", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decision_id"], ["risk_decisions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_risk_reservations_open", "risk_reservations", ["account_id", "symbol", "state"]
    )


def downgrade() -> None:
    op.drop_index("ix_risk_reservations_open", table_name="risk_reservations")
    op.drop_table("risk_reservations")
