"""p5 session1 broker_mode

Adds the two columns the LIVE / PAPER distinction needs (P5 §1):

  * ``accounts.broker_mode_locked_at`` — records when LIVE was activated. Set
    by the P5 §7 activation wizard; declared now so the wizard ships without a
    migration. Nullable.
  * ``risk_limits.broker_mode`` — scopes a limits row to PAPER or LIVE. The
    risk engine filters on it, hence the index. Existing rows backfill to
    'paper' via the server_default, so the NOT NULL add is safe.

No data is destroyed and none needs normalising: ``accounts.mode`` is already
a typed enum (paper|live) with a CHECK constraint, so there are no stray values
to clean up before broker_mode becomes load-bearing.

Revision ID: 3f9a2b1c8d4e
Revises: 0e039e08250e
Create Date: 2026-05-30

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3f9a2b1c8d4e"
down_revision: str | None = "0e039e08250e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("accounts", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "broker_mode_locked_at", sa.DateTime(timezone=True), nullable=True
            )
        )

    with op.batch_alter_table("risk_limits", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "broker_mode",
                sa.String(length=16),
                server_default="paper",
                nullable=False,
            )
        )
        batch_op.create_index(
            batch_op.f("ix_risk_limits_broker_mode"),
            ["broker_mode"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("risk_limits", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_risk_limits_broker_mode"))
        batch_op.drop_column("broker_mode")

    with op.batch_alter_table("accounts", schema=None) as batch_op:
        batch_op.drop_column("broker_mode_locked_at")
