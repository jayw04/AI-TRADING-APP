"""BacktestResult — one row per backtest run.

Sized for SQLite: ``metrics_json``, ``equity_curve_json``, and
``trades_json`` may each be tens to hundreds of KB. SQLite handles this
fine. On a future Postgres migration these become JSONB.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Human-readable label distinguishing runs ("default-params",
    # "tighter-rsi", etc.). The actual parameter set is in params_json.
    label: Mapped[str] = mapped_column(String(128), nullable=False, default="default")

    params_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    metrics_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )
    equity_curve_json: Mapped[list[Any]] = mapped_column(
        JSON, nullable=False, default=list
    )
    trades_json: Mapped[list[Any]] = mapped_column(
        JSON, nullable=False, default=list
    )

    range_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    range_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    strategy = relationship("Strategy")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<BacktestResult strategy_id={self.strategy_id} "
            f"created_at={self.created_at}>"
        )
