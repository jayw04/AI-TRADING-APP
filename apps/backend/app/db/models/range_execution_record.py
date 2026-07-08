"""RangeExecutionRecord — daily Range Trader execution vs. the stock's actual daily high/low.

One append-only row per (symbol, ET trading day): our qty-weighted average BUY/SELL fill (null when we
did not trade that name) alongside the stock's RTH daily low/high. Lets us track how well the range-fade
book buys near the low and sells near the high. Materializes the daily high/low — which otherwise lives
only in the bar cache — into the DB so it is queryable and *frozen* (a completed day is captured once).

Operational telemetry (not hash-chained), purely additive, off the order path. Mirrors the append-only
shape of ``BenchmarkSnapshot`` / ``EquitySnapshot``.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RangeExecutionRecord(Base):
    __tablename__ = "range_execution_records"
    __table_args__ = (
        # One frozen row per symbol per day; also serves the (symbol, et_date) window query.
        UniqueConstraint(
            "symbol", "et_date", name="uq_range_execution_records_symbol_et_date"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    et_date: Mapped[date] = mapped_column(Date, nullable=False)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    # Our fills — null when the range book did not trade this name that day.
    avg_buy_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    avg_sell_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    # The stock's RTH daily range (from the 1Day bar).
    daily_low: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    daily_high: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
