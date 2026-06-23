"""orders.estimated_notional — persisted pre-trade notional for pending-aware risk gates.

The risk engine's gross-exposure and position caps previously counted only SETTLED
positions, and valued MARKET orders at 0 (no fill price up front). Three baskets
submitted before any fill therefore each passed independently, stacking unintended
leverage (incident 2026-06-22, momentum-conservative). To let the gates see in-flight
exposure, the engine now persists the estimated notional it computed for each order;
the gross/position checks sum the notional of non-terminal orders alongside settled
positions. Nullable + purely additive: pre-existing rows and orders with no resolvable
price stay NULL (treated as 0 — the prior behavior).

Revision ID: e7b2c9d4f1a6
Revises: a1c3e5f7b9d2
Create Date: 2026-06-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "e7b2c9d4f1a6"
down_revision = "a1c3e5f7b9d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("estimated_notional", sa.Numeric(20, 4), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orders", "estimated_notional")
