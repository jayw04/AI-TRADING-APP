"""StrategyRun — one row per (paper|live|backtest) run of a strategy.

A *run* is bounded: starts when ``StrategyEngine.register`` fires, ends when
the engine unregisters or an unhandled exception transitions the strategy
to ``ERROR``. The row lets the UI show ranges like "today the strategy
ran from 09:30 to 16:00 and produced 12 signals".
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import StrategyStatus


class StrategyRun(Base):
    __tablename__ = "strategy_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Final state of this run (PAPER/LIVE/BACKTEST while running;
    # IDLE/HALTED/ERROR when ended).
    status: Mapped[StrategyStatus] = mapped_column(
        SQLEnum(StrategyStatus, native_enum=False, length=16),
        nullable=False,
    )

    error_text: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    strategy = relationship("Strategy")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<StrategyRun strategy_id={self.strategy_id} "
            f"started_at={self.started_at}>"
        )
