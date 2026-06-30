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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.enums import (
    TERMINAL_ORDER_STATUSES,
    OrderSide,
    OrderSourceType,
    SignalType,
)
from app.db.models.account_state import AccountState
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.signal import Signal
from app.db.models.symbol import Symbol
from app.risk import OrderRequest

logger = structlog.get_logger(__name__)

# Sanctioned portfolio-level signal sentinel. A strategy may log a signal that is
# about the book as a whole (a full-liquidation EXIT, a gross-exposure overlay
# decision) rather than a single ticker — e.g. momentum_portfolio / low_volatility
# log ``log_signal("PORTFOLIO", …)``. This is NOT a universe-isolation violation, so
# it must not raise ``strategy_logged_unauthorized_signal``; it is persisted against a
# non-tradeable sentinel ``symbols`` row so the decision is recorded in the signal feed.
PORTFOLIO_SIGNAL_SYMBOL = "PORTFOLIO"


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
    - ``factor_accessor`` (P9 §2): optional read-only, point-in-time factor
      accessor (``app.factor_data.accessor.FactorAccessor``). Reachable via the
      ``factors`` property; ``None`` means factor data is not provisioned and any
      access raises ``FactorDataUnavailable``.
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
        factor_accessor: Any | None = None,  # app.factor_data.accessor.FactorAccessor
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
        self._factor_accessor = factor_accessor

    # ---- factor data (P9 §2) ----

    @property
    def factors(self) -> Any:
        """The sandboxed read-only :class:`FactorAccessor` for PIT factor scores.

        Raises ``FactorDataUnavailable`` if factor data was not provisioned for
        this run (no store). The accessor cannot reach the order path, the broker,
        a DB session, or the network — it is the deliberate factor extension point
        (P9 §2; mirrors how this context wraps ``BarCache`` for prices)."""
        if self._factor_accessor is None:
            from app.factor_data.accessor import FactorDataUnavailable

            raise FactorDataUnavailable(
                "factor data is not provisioned for this run. Ingest the Sharadar "
                "spine first — see docs/runbook/factor-data.md."
            )
        return self._factor_accessor

    # ---- market session (§9A) ----

    @property
    def session(self) -> Any:
        """The current market session (:class:`app.market.session.SessionInfo`):
        current session + the day's open/close. Use this instead of
        ``datetime.now()`` to compute open/close offsets against an authoritative
        clock. The engine already gates dispatch on this (a strategy is only
        called in a permitted session); ``ctx.session`` lets a strategy refine
        its own timing within the session."""
        from app.market.session import default_market_session

        return default_market_session().classify()

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

    async def pending_buy_qty(self) -> dict[str, Decimal]:
        """In-flight BUY quantity per ticker for THIS strategy, keyed by ticker.

        Sums the qty of this strategy's own non-terminal BUY orders (routed but
        not yet filled/settled, so not yet visible in ``positions``). A strategy
        nets its target buys against this so a re-run — e.g. after a
        deactivate/reactivate within the same rebalance period — does not submit a
        duplicate basket and stack unintended exposure (incident 2026-06-22).

        DB-backed, so the guard survives the in-memory strategy instance being
        recreated. Scoped to this strategy's own orders (``source_id``); other
        strategies and manual orders on the account are netted by the risk
        engine's account-level gates (ADR 0025), not here. Conservative: counts
        each order's full qty (a partial fill's remainder lags in ``positions``).
        Restricted to the strategy's allowed universe.
        """
        allowed = {s.upper() for s in self.symbols}
        out: dict[str, Decimal] = {}
        async with self._session_factory() as session:
            rows = (
                await session.execute(
                    select(Symbol.ticker, Order.qty)
                    .join(Symbol, Symbol.id == Order.symbol_id)
                    .where(
                        Order.account_id == self.account_id,
                        Order.source_type == OrderSourceType.STRATEGY,
                        Order.source_id == str(self.strategy_id),
                        Order.side == OrderSide.BUY,
                        Order.status.notin_(TERMINAL_ORDER_STATUSES),
                    )
                )
            ).all()
        for ticker, qty in rows:
            t = ticker.upper()
            if t not in allowed:
                continue
            out[t] = out.get(t, Decimal(0)) + Decimal(qty)
        return out

    async def get_account_equity(self) -> Decimal | None:
        """Live account equity from the cached broker snapshot, or ``None`` if no
        snapshot exists yet.

        Reads ``accounts_state`` (the per-account Alpaca snapshot kept fresh by
        ``AccountSyncService``) scoped to this strategy's account. Read-only — for
        position sizing; it never touches the order path or the broker directly. A
        ``None`` return means a caller should fall back to a configured estimate
        rather than assume an equity."""
        async with self._session_factory() as session:
            row = (
                await session.execute(
                    select(AccountState).where(AccountState.account_id == self.account_id)
                )
            ).scalars().first()
            return row.equity if row is not None else None

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

    # ---- opportunity funnel (Phase 0B) ----

    def record_opportunity(self, symbol: str, stage: str, day: str) -> None:
        """No-op in live (today). Mirrors ``BacktestContext.record_opportunity`` so the
        SAME strategy code reports funnel stages in backtest without erroring live. A live
        funnel collector (for the permanent dashboard KPI) is a future surface."""
        return None

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
        is_portfolio = symbol == PORTFOLIO_SIGNAL_SYMBOL
        if not is_portfolio and symbol not in {s.upper() for s in self.symbols}:
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
                if not is_portfolio:
                    logger.warning("strategy_signal_unknown_symbol", symbol=symbol)
                    return 0
                # Lazily create the non-tradeable PORTFOLIO sentinel (once ever). A
                # concurrent first-use race resolves to the row the other writer made.
                try:
                    async with session.begin_nested():
                        sym = Symbol(
                            ticker=PORTFOLIO_SIGNAL_SYMBOL,
                            asset_class="sentinel",
                            name="Portfolio-level signal sentinel",
                            active=False,
                        )
                        session.add(sym)
                        await session.flush()
                except IntegrityError:
                    sym = (
                        await session.execute(
                            select(Symbol).where(Symbol.ticker == PORTFOLIO_SIGNAL_SYMBOL)
                        )
                    ).scalars().first()
                    if sym is None:
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
