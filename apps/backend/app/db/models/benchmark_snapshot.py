"""BenchmarkSnapshot — append-only daily-close time series for reference index funds (SPY/VOO/…).

The dashboard compares each live book's return-since-inception against passive benchmarks over the
**same** window. Mirrors ``EquitySnapshot``: the earliest snapshot per symbol is the benchmark's
inception price (so `latest/earliest − 1` is the benchmark return over exactly the book's live
window). Operational telemetry, not the audit log (not hash-chained); purely additive; no order path.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BenchmarkSnapshot(Base):
    __tablename__ = "benchmark_snapshots"
    __table_args__ = (Index("ix_benchmark_snapshots_symbol_ts", "symbol", "ts"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
