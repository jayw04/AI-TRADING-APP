"""Live cache of the Alpaca account snapshot.

One row per account. Updated by `AccountSyncService` on each poll. Distinct
from the static `accounts` table (which holds identity/credentials metadata)
— this table is the *current* live snapshot the UI Dashboard reads.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AccountState(Base):
    __tablename__ = "accounts_state"

    id: Mapped[int] = mapped_column(primary_key=True)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    # Decimal(18, 4) is overkill for retail equity prices, but leaves headroom.
    cash: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal(0))
    equity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal(0))
    last_equity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal(0))
    buying_power: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal(0))
    portfolio_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal(0))
    daytrade_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Computed convenience fields (kept on the row so the UI doesn't have to recompute).
    day_change: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal(0))
    day_change_pct: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False, default=Decimal(0))
    # Provenance of the baseline behind the two fields above — see services/day_change_basis.py.
    # ``UNAVAILABLE`` means no baseline was found and the two numbers above are placeholders, NOT a
    # measured flat day. The conservative default applies to rows written before this column
    # existed: their basis was never recorded, so it is not asserted.
    # The literal is spelled out rather than imported to keep models free of service imports;
    # `test_model_default_matches_constant` pins it to `day_change_basis.UNAVAILABLE`.
    day_change_basis: Mapped[str] = mapped_column(
        String(32), nullable=False, default="UNAVAILABLE", server_default="UNAVAILABLE"
    )

    # Status flags
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN")
    pattern_day_trader: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    trading_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    account_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Forensic dump of the full Alpaca payload — we never lose a field even if a
    # column-mapped name changes upstream.
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    account = relationship("Account")
