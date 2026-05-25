"""StrategyContext — the safe accessors handed to user strategy code.

Design principle: every method on this class either reads state read-only
or dispatches through an existing component (``OrderRouter``,
``BarCache``, ``IndicatorComputer``). NOTHING here lets a strategy reach
the broker adapter directly or bypass the risk engine. ADR 0002 holds.

This file does NOT import ``OrderRouter`` directly; it accepts a callable
so unit tests can inject a stub.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.enums import OrderSourceType, SignalType
from app.db.models.position import Position
from app.db.models.signal import Signal
from app.db.models.symbol import Symbol
from app.risk import OrderRequest

logger = structlog.get_logger(__name__)


# ---------- DTOs handed to user code ----------


@dataclass
class Bar:
    """A single OHLCV bar."""

    symbol: str
    timeframe: str
    t: datetime
    o: float
    h: float
    l: float  # noqa: E741 — OHLCV convention
    c: float
    v: int


@dataclass
class SignalEvent:
    """A signal scoped to a strategy."""

    signal_id: int
    strategy_id: int
    symbol: str
    type: SignalType
    payload: dict[str, Any]
    received_at: datetime


@dataclass
class FillEvent:
    """A fill on one of this strategy's orders."""

    fill_id: int
    order_id: int
    symbol: str
    side: str  # "buy" | "sell"
    qty: Decimal
    price: Decimal
    filled_at: datetime


# ---------- StrategyContext ----------


# Signature of the order-router callable injected into the context. Returns
# the persisted Order (or an ephemeral rejected Order — same shape as
# OrderRouter.submit).
OrderRouterCallable = Callable[[OrderRequest], Awaitable[Any]]


# Default lookback windows by timeframe — sized so SMA200 has headroom on
# every supported timeframe. Values are hours.
_LOOKBACK_HOURS_BY_TF: dict[str, int] = {
    "1Min": 6,
    "5Min": 24,
    "15Min": 48,
    "1Hour": 168,
    "1Day": 24 * 365,
}


class StrategyContext:
    """The safe surface user strategy code sees.

    Constructed once per :class:`Strategy` instance by the engine. Holds:

    - ``strategy_id``, ``user_id``, ``account_id``: scopes any DB reads.
    - ``symbols``: the allowed universe — reads / signals outside it
      no-op with a warning rather than raising.
    - ``session_factory``: opens DB sessions on demand.
    - ``bar_cache``, ``indicator_computer``: market-data accessors
      (Session 1).
    - ``submit_order_fn``: bound to ``OrderRouter.submit`` with
      ``source_type=STRATEGY`` and ``source_id=str(strategy_id)``.
    """

    def __init__(
        self,
        *,
        strategy_id: int,
        user_id: int,
        account_id: int,
        symbols: list[str],
        session_factory: async_sessionmaker[AsyncSession],
        bar_cache: Any,  # app.market_data.bar_cache.BarCache
        indicator_computer: Any,  # app.indicators.IndicatorComputer
        submit_order_fn: OrderRouterCallable,
        bus: Any | None = None,  # app.events.bus.EventBus; optional for tests
    ) -> None:
        self.strategy_id = strategy_id
        self.user_id = user_id
        self.account_id = account_id
        self.symbols = list(symbols)
        self._session_factory = session_factory
        self._bar_cache = bar_cache
        self._indicator_computer = indicator_computer
        self._submit_order_fn = submit_order_fn
        self._bus = bus

    # ---- market data ----

    async def get_recent_bars(
        self,
        symbol: str,
        timeframe: str,
        n: int = 100,
    ) -> pd.DataFrame:
        """Return the most recent ``n`` bars for ``(symbol, timeframe)``.

        Symbol must be in this strategy's allowed universe; otherwise we
        return an empty frame and log a warning. (Don't raise — a typo in a
        strategy shouldn't take itself down.)
        """
        if symbol.upper() not in {s.upper() for s in self.symbols}:
            logger.warning(
                "strategy_requested_unauthorized_symbol",
                strategy_id=self.strategy_id,
                symbol=symbol,
                allowed=self.symbols,
            )
            return pd.DataFrame(columns=["t", "o", "h", "l", "c", "v"])

        now = datetime.now(UTC)
        hours_back = _LOOKBACK_HOURS_BY_TF.get(timeframe, 24)
        start = now - timedelta(hours=hours_back)
        df = await self._bar_cache.get_bars(symbol.upper(), timeframe, start, now)
        return df.tail(n).reset_index(drop=True)

    async def get_indicators(
        self,
        symbol: str,
        names: list[str],
        timeframe: str = "1Min",
        n_bars: int = 250,
    ) -> dict[str, Any]:
        """Compute indicators for the last ``n_bars`` on ``(symbol, timeframe)``.

        Returns a dict keyed by indicator name. Multi-output indicators
        (MACD, BB) return ``dict[str, pd.Series]``.
        """
        bars = await self.get_recent_bars(symbol, timeframe, n=n_bars)
        if bars.empty:
            return {n: pd.Series(dtype="float64") for n in names}
        return self._indicator_computer.compute(
            bars,
            names=names,
            symbol=symbol.upper(),
            timeframe=timeframe,
        )

    # ---- positions ----

    async def get_positions(self) -> list[Position]:
        """Open positions for THIS strategy's allowed symbols only.

        A strategy should not be aware of holdings outside its mandate.
        """
        async with self._session_factory() as session:
            symbol_ids = (
                await session.execute(
                    select(Symbol.id).where(
                        Symbol.ticker.in_([s.upper() for s in self.symbols])
                    )
                )
            ).scalars().all()
            if not symbol_ids:
                return []
            positions = (
                await session.execute(
                    select(Position).where(
                        Position.account_id == self.account_id,
                        Position.symbol_id.in_(symbol_ids),
                    )
                )
            ).scalars().all()
            return list(positions)

    async def get_position_for(self, symbol: str) -> Position | None:
        """Open position in one specific symbol, or None."""
        symbol = symbol.upper()
        if symbol not in {s.upper() for s in self.symbols}:
            return None
        async with self._session_factory() as session:
            sym = (
                await session.execute(select(Symbol).where(Symbol.ticker == symbol))
            ).scalars().first()
            if sym is None:
                return None
            return (
                await session.execute(
                    select(Position).where(
                        Position.account_id == self.account_id,
                        Position.symbol_id == sym.id,
                    )
                )
            ).scalars().first()

    # ---- order submission ----

    async def submit_order(self, order_request: OrderRequest) -> Any:
        """Dispatch an order through OrderRouter with strategy attribution.

        Stamps provenance fields on the request if the caller didn't:

        - ``source_type = OrderSourceType.STRATEGY``
        - ``source_id = str(self.strategy_id)``
        - ``user_id = self.user_id`` (if unset)
        - ``account_id = self.account_id`` (if unset)

        The risk engine evaluates as usual; rejections are returned to the
        strategy (not raised), so the strategy can log them as info signals.

        ``OrderRequest`` is a frozen dataclass; we build a replacement with
        ``dataclasses.replace`` rather than mutating in place.
        """
        from dataclasses import replace

        updates: dict[str, Any] = {}
        if order_request.source_type != OrderSourceType.STRATEGY:
            updates["source_type"] = OrderSourceType.STRATEGY
        if not order_request.source_id:
            updates["source_id"] = str(self.strategy_id)
        if order_request.user_id == 0:
            updates["user_id"] = self.user_id
        if order_request.account_id == 0:
            updates["account_id"] = self.account_id

        if updates:
            order_request = replace(order_request, **updates)
        return await self._submit_order_fn(order_request)

    # ---- signal logging ----

    async def log_signal(
        self,
        symbol: str,
        type_: SignalType,
        payload: dict[str, Any] | None = None,
    ) -> int:
        """Persist a ``signals`` row attributed to this strategy.

        Returns the new signal id, or 0 if the symbol couldn't be resolved.
        """
        symbol = symbol.upper()
        if symbol not in {s.upper() for s in self.symbols}:
            logger.warning(
                "strategy_logged_unauthorized_signal",
                strategy_id=self.strategy_id,
                symbol=symbol,
            )
        async with self._session_factory() as session:
            sym = (
                await session.execute(select(Symbol).where(Symbol.ticker == symbol))
            ).scalars().first()
            if sym is None:
                logger.warning("strategy_signal_unknown_symbol", symbol=symbol)
                return 0
            sig = Signal(
                user_id=self.user_id,
                strategy_id=self.strategy_id,
                symbol_id=sym.id,
                type=type_,
                payload_json=payload or {},
                received_at=datetime.now(UTC),
            )
            session.add(sig)
            await session.commit()
            await session.refresh(sig)
            signal_id = sig.id

        # Publish AFTER the commit so any subscriber that reads back from the
        # DB sees the row. Bus is optional (BacktestContext + unit tests pass
        # bus=None); never let a publish failure swallow the signal id.
        if self._bus is not None:
            try:
                await self._bus.publish(
                    "signal.new",
                    {
                        "signal_id": signal_id,
                        "strategy_id": self.strategy_id,
                        "symbol": symbol,
                        "type": type_.value,
                        "payload": payload or {},
                        "received_at": datetime.now(UTC).isoformat(),
                    },
                )
            except Exception:
                logger.exception("signal_publish_failed", signal_id=signal_id)
        return signal_id
