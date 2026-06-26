"""EquitySnapshot — append-only equity time series per account (P12.5 Production Validation).

`accounts_state` holds the *current* snapshot (one row/account, updated in place); this table is
its **history** — one append per account per snapshot tick — so the live book's equity curve (and
realized vol / drawdown / return over the live window) can be reported. Operational telemetry, not
the audit log (not hash-chained). Purely additive; no order-path involvement.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EquitySnapshot(Base):
    __tablename__ = "equity_snapshots"
    __table_args__ = (Index("ix_equity_snapshots_account_ts", "account_id", "ts"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    equity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal(0))
    portfolio_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal(0))
    day_change_pct: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False, default=Decimal(0))
