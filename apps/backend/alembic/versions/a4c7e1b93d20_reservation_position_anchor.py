"""risk_reservations: position anchor for provable fill absorption (ADR 0042 §D amendment)

Revision ID: a4c7e1b93d20
Revises: e7b3f2a9c4d1
Create Date: 2026-07-22

The §D capacity arithmetic credits back the part of a held reservation the broker position has
ALREADY absorbed, so a partial fill is not charged twice (once by the shrunken position, once by
the still-full reservation). Crediting it requires PROOF that the position moved.

Broker positions, broker orders and local fills are three separate, non-atomic reads. A fill
recorded locally may not yet appear in the positions endpoint. Crediting such a fill back would
add capacity that does not exist and could admit a sell that crosses zero into a short — the
exact outcome ADR 0042 exists to prevent, reached from the opposite direction.

This column records the broker long for the symbol at the instant the reservation was created.
A later decision can then bound the credit by the position movement it can actually observe:

    observed_position_reduction = max(0, anchor - current_long)

NULLABLE on purpose. Rows written before this column existed carry no anchor, absorption is
therefore unprovable for them, and the capacity math credits them ZERO — conservative, and safe.
No backfill is attempted: inventing an anchor after the fact would fabricate the very proof this
column exists to supply.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a4c7e1b93d20"
down_revision = "e7b3f2a9c4d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "risk_reservations",
        sa.Column("position_qty_at_reservation", sa.Numeric(20, 8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("risk_reservations", "position_qty_at_reservation")
