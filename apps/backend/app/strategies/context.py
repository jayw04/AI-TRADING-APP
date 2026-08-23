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
from typing import Any, cast

import pandas as pd
import structlog
from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.enums import (
    TERMINAL_ORDER_STATUSES,
    OrderSide,
    OrderSourceType,
    SignalType,
)
from app.db.models.account_state import AccountState
from app.db.models.fill import Fill
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
    """A fill on one of this strategy's orders (strategy- and account-scoped).

    Carries enough to prove the five qualifying-fill conditions in the seed
    reconciliation (identity, account, attempt tag, positive qty, effective
    status). ``order_status`` is the OWNING ORDER's effective status — fill-level
    reversal is not modelled in the schema, so the reconciliation layer reasons
    about validity from the order status rather than the template guessing from
    raw rows. New fields default so existing positional construction stays valid.
    """

    fill_id: int
    order_id: int
    symbol: str
    side: str  # "buy" | "sell"
    qty: Decimal
    price: Decimal
    filled_at: datetime
    client_order_id: str | None = None
    account_id: int | None = None
    source_id: str | None = None
    order_status: str = ""


@dataclass(frozen=True)
class OpenOrderObs:
    """A still-open (non-terminal) order for THIS strategy+account, carrying enough
    for the seed reconciliation to attribute it to an attempt (P7 §7-A). Order-level
    (not aggregated) — so per-order open/terminal state and attempt membership are
    both observable."""

    order_id: int
    symbol: str
    status: str = ""
    client_order_id: str | None = None


# ---------- StrategyContext ----------


# Signature of the order-router callable injected into the context. Returns
# the persisted Order (or an ephemeral rejected Order — same shape as
# OrderRouter.submit).
OrderRouterCallable = Callable[[OrderRequest], Awaitable[Any]]

#: Returns the uppercased tickers this strategy may READ because it unambiguously owns a
#: current holding in them (PR S / S3). Built by ``app.universe`` and injected, so this
#: module never learns how ownership is established. Never a buy authorization.
OwnedHoldingsCallable = Callable[[], Awaitable[frozenset[str]]]


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
        owned_holdings_fn: OwnedHoldingsCallable | None = None,
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

        # PR S / S3 — READ authority, and ONLY read authority (LOW-PIT v0.3 §4.7).
        #
        # ``symbols`` stays exactly what it has always been: the registered universe. It
        # drives dispatch iteration, target-selection membership and buy planning, and
        # widening it would quietly widen all three. So ownership-derived visibility is a
        # SEPARATE scope consulted only by the three read operations a strategy needs in
        # order to manage a position it already holds — ``get_position_for``,
        # ``get_positions`` and ``get_recent_bars``.
        #
        # ``pending_buy_qty`` is deliberately NOT widened: netting in-flight buys is buy
        # planning, and an owned-but-unregistered holding is only ever exited.
        #
        # The capability is injected (built in ``app.universe``) rather than constructed
        # here, so this module gains no dependency on the ownership resolver, the position
        # query or any identity source — the same seam ``submit_order_fn`` uses, and what
        # keeps ``check_strategy_isolation.sh`` satisfiable once PR B adds broker imports
        # to that package. ``None`` means no widening at all: pure v1.0.1 behavior.
        self._owned_holdings_fn = owned_holdings_fn
        self._owned_cache: tuple[int | None, frozenset[str]] | None = None

        # Which cron dispatch we are inside. The engine bumps this ONCE per
        # ``_dispatch_bar_tick`` and then calls ``on_bar`` once per symbol (200+ times), so a
        # portfolio strategy needs to know "these 209 calls are all the SAME rebalance slot".
        #
        # It cannot infer that from the bars: each call carries that symbol's own latest bar,
        # and symbols routinely DISAGREE on how recent that is (a stale cached month-bucket, a
        # thin ETF that has not printed yet). A guard keyed on ``bar.t``'s ISO week therefore
        # oscillates — Friday is week 28, Monday is week 29 — and re-runs the whole rebalance
        # against stale holdings. That is what fired the combined book 5× on 2026-07-13.
        #
        # None in backtests (bars are replayed with no engine dispatch), where the bar-derived
        # week IS the correct cadence signal.
        self.dispatch_seq: int | None = None

    # ---- read authority (PR S / S3) ----

    def _registered(self, symbol: str) -> bool:
        return symbol.upper() in {s.upper() for s in self.symbols}

    async def _owned_readable(self) -> frozenset[str]:
        """Ownership-derived read scope for the current dispatch.

        Cached per ``dispatch_seq`` because the engine calls ``on_bar`` once per symbol —
        200+ times in one rebalance slot — and the owned set cannot change within a slot.
        A ``None`` dispatch_seq (backtests, unit tests) caches under its own key; that is
        the same lifetime the rest of this class already assumes for a non-dispatch
        context.

        **Fails closed on error.** If the capability raises, the read scope is empty, so
        behaviour degrades to registered-only v1.0.1 rather than to unbounded visibility.
        A failure here must never be able to widen what a strategy can see.
        """
        if self._owned_holdings_fn is None:
            return frozenset()
        if self._owned_cache is not None and self._owned_cache[0] == self.dispatch_seq:
            return self._owned_cache[1]
        try:
            owned = frozenset(t.upper() for t in await self._owned_holdings_fn())
        except Exception:
            logger.exception(
                "owned_holdings_resolution_failed",
                strategy_id=self.strategy_id,
                account_id=self.account_id,
            )
            owned = frozenset()
        self._owned_cache = (self.dispatch_seq, owned)
        return owned

    async def _readable(self, symbol: str) -> bool:
        """May this strategy READ ``symbol``? Registered, or an unambiguously owned holding.

        This is NOT buy authority (LOW-PIT v0.3 §4.7). Registration is checked first so a
        registered symbol never pays for an ownership lookup, and a strategy with no
        injected capability behaves exactly as it did in v1.0.1.
        """
        return self._registered(symbol) or symbol.upper() in await self._owned_readable()

    async def read_scope(self) -> frozenset[str]:
        """Registered ∪ owned-held, uppercased. Diagnostics and tests; not for planning."""
        return frozenset(s.upper() for s in self.symbols) | await self._owned_readable()

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

        Symbol must be READABLE — registered, or an unambiguously owned current holding
        (PR S / S3). Otherwise we return an empty frame and log a warning. (Don't raise —
        a typo in a strategy shouldn't take itself down.)

        Pricing an owned holding is a prerequisite for exiting it, which is why this is in
        the widened set. It confers no buy eligibility: a price is not a target.
        """
        if not await self._readable(symbol):
            logger.warning(
                "strategy_requested_unauthorized_symbol",
                strategy_id=self.strategy_id,
                symbol=symbol,
                allowed=self.symbols,
            )
            return pd.DataFrame(columns=["t", "o", "h", "l", "c", "v"])

        now = datetime.now(UTC)
        # The fetch window must cover at least ``n`` bars. The per-timeframe values are a floor;
        # for daily bars a large ``n`` needs a wider window than the 1-year default, else
        # get_recent_bars(n) silently caps at ~251 trading days no matter how deep the cache
        # (this starved the combined-book cross-asset sleeve, which needs ~338 trading days).
        # ~1.6× calendar days covers weekends/holidays.
        if timeframe == "1Day":
            days_back = max(365, int(n * 1.6) + 10)
            start = now - timedelta(days=days_back)
        else:
            start = now - timedelta(hours=_LOOKBACK_HOURS_BY_TF.get(timeframe, 24))
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

    async def get_holdings(self) -> dict[str, Decimal]:
        """Long quantities currently held inside this strategy's READ scope, by ticker.

        The ticker-keyed projection of :meth:`get_positions`. ``Position`` rows carry a
        ``symbol_id`` and no ticker, so a strategy that needs to reason about *which*
        securities it holds would otherwise have to resolve symbols itself — and would end
        up re-deriving the read scope, which is exactly the ownership logic that must stay
        below this boundary (PR S / S4).

        The candidate set is registered ∪ strategy-owned-held, so a holding the strategy
        unambiguously owns is enumerated even when its symbol was never registered. That is
        what makes an exit intent formable for it. It is still not buy authority: the
        result feeds "what do I hold", never "what may I buy".

        One query rather than one per symbol. Long side only, ``qty > 0`` — a flat or short
        row is not a holding to manage here.
        """
        readable = await self.read_scope()
        if not readable:
            return {}
        stmt = (
            select(Symbol.ticker, Position.qty)
            .join(Position, Position.symbol_id == Symbol.id)
            .where(
                Position.account_id == self.account_id,
                Symbol.ticker.in_(sorted(readable)),
                Position.qty > Decimal(0),
            )
        )
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        return {ticker.upper(): Decimal(qty) for ticker, qty in rows}

    async def get_positions(self) -> list[Position]:
        """Open positions inside this strategy's READ scope.

        A strategy should not be aware of holdings outside its mandate — but a holding it
        unambiguously owns *is* its mandate even when the symbol was never registered
        (PR S / S3). Without this, a dynamically acquired position is invisible and
        therefore un-exitable, which is the LOW-PIT-01B defect.
        """
        readable = await self.read_scope()
        async with self._session_factory() as session:
            symbol_ids = (
                (
                    await session.execute(
                        select(Symbol.id).where(Symbol.ticker.in_(sorted(readable)))
                    )
                )
                .scalars()
                .all()
            )
            if not symbol_ids:
                return []
            positions = (
                (
                    await session.execute(
                        select(Position).where(
                            Position.account_id == self.account_id,
                            Position.symbol_id.in_(symbol_ids),
                        )
                    )
                )
                .scalars()
                .all()
            )
            return list(positions)

    async def get_position_for(self, symbol: str) -> Position | None:
        """Open position in one specific symbol, or None.

        Readable if registered OR unambiguously owned and currently held (PR S / S3).
        """
        symbol = symbol.upper()
        if not await self._readable(symbol):
            return None
        async with self._session_factory() as session:
            sym = (
                (await session.execute(select(Symbol).where(Symbol.ticker == symbol)))
                .scalars()
                .first()
            )
            if sym is None:
                return None
            return (
                (
                    await session.execute(
                        select(Position).where(
                            Position.account_id == self.account_id,
                            Position.symbol_id == sym.id,
                        )
                    )
                )
                .scalars()
                .first()
            )

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

    async def recent_payloads(self, *, limit: int = 50) -> list[dict[str, Any]]:
        """Newest ``signals.payload_json`` rows for THIS strategy.

        Durable across process restarts (unlike in-memory week guards). Used by
        weekly books to record rebalance_started / rebalance_completed and to
        retry an incomplete week. Read-only; does not leak other strategies.
        """
        async with self._session_factory() as session:
            rows = (
                (
                    await session.execute(
                        select(Signal.payload_json)
                        .where(Signal.strategy_id == self.strategy_id)
                        .order_by(Signal.received_at.desc(), Signal.id.desc())
                        .limit(int(limit))
                    )
                )
                .scalars()
                .all()
            )
        return [dict(p) for p in rows if p]

    async def recent_fills(
        self,
        *,
        since: datetime | None = None,
        after_fill_id: int | None = None,
        client_order_id_prefix: str | None = None,
    ) -> list[FillEvent]:
        """Fills on THIS strategy's own orders for THIS account, oldest-first.

        Strategy- and account-scoped and READ-ONLY (P7 §7-A, momentum-daily
        cold-start seed reconciliation). The authorization boundary is the
        fills->orders relationship plus this context's own identity — NOT the
        ``client_order_id``::

            fill.order_id     == order.id
            order.account_id  == self.account_id
            order.source_type == STRATEGY
            order.source_id   == str(self.strategy_id)

        ``client_order_id_prefix`` is an OPTIONAL attempt-level filter layered on
        top, never the primary authorization: a malformed or user-controlled
        client-order id therefore cannot make another order's fill attributable
        here. The caller passes NO strategy_id/account_id/source_id — scope is the
        context's own identity only.

        Deterministic ascending order ``(filled_at, fill_id)`` with a stable
        tie-break. The cursor is TWO-PART to be exact across ties: pass both
        ``since`` and ``after_fill_id`` (the last processed
        ``(filled_at, fill_id)``) and the query returns strictly
        ``filled_at > since OR (filled_at == since AND fill_id > after_fill_id)``
        — so a crash between two fills sharing a timestamp neither drops nor
        replays them. ``since`` alone is inclusive (``>=``, for the first poll
        from the seed attempt's ``created_at``); reconciliation stays idempotent
        by ``fill_id`` regardless.

        ``FillEvent.order_status`` carries the owning order's status for
        diagnostics ONLY. The order model has no fill-void/reversal concept, so a
        fill with ``qty > 0`` is economically valid even if its order later
        reached a terminal ``CANCELED`` (partial-fill-then-cancel). Callers must
        therefore qualify on ``filled_quantity > 0`` — NOT on order status — and
        must not treat an ordinary terminal status as fill invalidation. This
        method returns ALL such fills (including on CANCELED orders); the
        reconciliation layer decides qualification.
        """
        stmt = (
            select(
                Fill.id,
                Fill.order_id,
                Fill.qty,
                Fill.price,
                Fill.filled_at,
                Order.client_order_id,
                Order.account_id,
                Order.source_id,
                Order.status,
                Order.side,
                Symbol.ticker,
            )
            .join(Order, Order.id == Fill.order_id)
            .join(Symbol, Symbol.id == Order.symbol_id)
            .where(
                Order.account_id == self.account_id,
                Order.source_type == OrderSourceType.STRATEGY,
                Order.source_id == str(self.strategy_id),
            )
        )
        if since is not None and after_fill_id is not None:
            stmt = stmt.where(
                (Fill.filled_at > since) | ((Fill.filled_at == since) & (Fill.id > after_fill_id))
            )
        elif since is not None:
            stmt = stmt.where(Fill.filled_at >= since)
        if client_order_id_prefix is not None:
            stmt = stmt.where(Order.client_order_id.like(f"{client_order_id_prefix}%"))
        stmt = stmt.order_by(Fill.filled_at.asc(), Fill.id.asc())
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        out: list[FillEvent] = []
        for fid, oid, qty, price, filled_at, coid, acct, src, status, side, ticker in rows:
            out.append(
                FillEvent(
                    fill_id=fid,
                    order_id=oid,
                    symbol=ticker.upper(),
                    side=("buy" if side == OrderSide.BUY else "sell"),
                    qty=Decimal(qty),
                    price=Decimal(price),
                    filled_at=filled_at,
                    client_order_id=coid,
                    account_id=acct,
                    source_id=src,
                    order_status=str(status),
                )
            )
        return out

    async def open_orders(self, *, client_order_id_prefix: str | None = None) -> list[OpenOrderObs]:
        """Still-open (non-terminal) orders for THIS strategy+account, oldest-first
        (P7 §7-A). Strategy+account-scoped like ``recent_fills``;
        ``client_order_id_prefix`` optionally narrows to a single seed attempt.
        Order-level (not aggregated) so the caller can tell whether each intended
        seed order remains open, which attempt it belongs to, and whether an
        unrelated strategy order is being mistaken for a seed order — none of which
        is inferrable from an aggregated pending quantity.
        """
        stmt = (
            select(Order.id, Symbol.ticker, Order.status, Order.client_order_id)
            .join(Symbol, Symbol.id == Order.symbol_id)
            .where(
                Order.account_id == self.account_id,
                Order.source_type == OrderSourceType.STRATEGY,
                Order.source_id == str(self.strategy_id),
                Order.status.notin_(TERMINAL_ORDER_STATUSES),
            )
        )
        if client_order_id_prefix is not None:
            stmt = stmt.where(Order.client_order_id.like(f"{client_order_id_prefix}%"))
        stmt = stmt.order_by(Order.id.asc())
        async with self._session_factory() as session:
            rows = (await session.execute(stmt)).all()
        return [
            OpenOrderObs(
                order_id=oid, symbol=ticker.upper(), status=str(status), client_order_id=coid
            )
            for oid, ticker, status, coid in rows
        ]

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
                (
                    await session.execute(
                        select(AccountState).where(AccountState.account_id == self.account_id)
                    )
                )
                .scalars()
                .first()
            )
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
                (await session.execute(select(Symbol).where(Symbol.ticker == symbol)))
                .scalars()
                .first()
            )
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
                        (
                            await session.execute(
                                select(Symbol).where(Symbol.ticker == PORTFOLIO_SIGNAL_SYMBOL)
                            )
                        )
                        .scalars()
                        .first()
                    )
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

    # ---- durable per-strategy state (Workstream B) ----

    async def get_state(self, key: str, default: Any = None) -> Any:
        """The stored JSON value for ``key``, or ``default`` if unset.

        Durable and restart-safe — this is the mechanism an in-memory counter is NOT. A strategy
        that reads its rebalance lifecycle or a backstop date from here sees the same value after a
        reload; an instance attribute would silently reset to its initial value and defeat the very
        discipline it was meant to enforce.
        """
        from app.db.models.strategy_state import StrategyState

        async with self._session_factory() as session:
            row = (
                (
                    await session.execute(
                        select(StrategyState).where(
                            StrategyState.strategy_id == self.strategy_id,
                            StrategyState.key == key,
                        )
                    )
                )
                .scalars()
                .first()
            )
            return row.value if row is not None else default

    async def set_state(self, key: str, value: Any) -> None:
        """Upsert the JSON ``value`` for ``key`` (one row per (strategy, key)).

        A single strategy instance is dispatched serially, so a read-modify-write here does not race
        itself; the unique constraint on (strategy_id, key) is the backstop against a duplicate row
        if two instances ever overlap during a reload handoff.
        """
        from app.db.models.strategy_state import StrategyState

        async with self._session_factory() as session, session.begin():
            row = (
                (
                    await session.execute(
                        select(StrategyState).where(
                            StrategyState.strategy_id == self.strategy_id,
                            StrategyState.key == key,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if row is None:
                session.add(
                    StrategyState(
                        strategy_id=self.strategy_id,
                        key=key,
                        value=value,
                        updated_at=datetime.now(UTC),
                    )
                )
            else:
                row.value = value
                row.updated_at = datetime.now(UTC)

    async def compare_and_set_state(
        self, key: str, *, expected_rev: int | None, new_value: dict[str, Any]
    ) -> bool:
        """Atomic compare-and-set on a versioned state blob (P7 §7-A write-ahead).

        Real optimistic concurrency, unlike ``set_state`` (last-write-wins): the
        write applies only if the stored blob's ``_rev`` still equals
        ``expected_rev`` — or, for ``expected_rev is None``, only if NO row exists.
        Returns True iff exactly one row transitioned, so two callers that both read
        the same revision cannot both write a seed attempt. ``new_value`` MUST carry
        its own (incremented) ``_rev``.
        """
        from app.db.models.strategy_state import StrategyState

        if expected_rev is None:
            # Create-if-absent: the UNIQUE(strategy_id, key) constraint makes a
            # concurrent duplicate insert fail — a dialect-agnostic CAS for the
            # first write.
            try:
                async with self._session_factory() as session, session.begin():
                    session.add(
                        StrategyState(
                            strategy_id=self.strategy_id,
                            key=key,
                            value=new_value,
                            updated_at=datetime.now(UTC),
                        )
                    )
                return True
            except IntegrityError:
                return False
        async with self._session_factory() as session, session.begin():
            # DML yields a `CursorResult` at runtime though typed as `Result`; `rowcount`
            # is the CAS witness here.
            res = cast(
                "CursorResult[Any]",
                await session.execute(
                    update(StrategyState)
                    .where(
                        StrategyState.strategy_id == self.strategy_id,
                        StrategyState.key == key,
                        func.json_extract(StrategyState.value, "$._rev") == expected_rev,
                    )
                    .values(value=new_value, updated_at=datetime.now(UTC))
                ),
            )
            changed = res.rowcount
        return changed == 1

    async def clear_state(self, key: str) -> None:
        """Remove ``key`` entirely (so a subsequent ``get_state`` returns its default)."""
        from app.db.models.strategy_state import StrategyState

        async with self._session_factory() as session, session.begin():
            row = (
                (
                    await session.execute(
                        select(StrategyState).where(
                            StrategyState.strategy_id == self.strategy_id,
                            StrategyState.key == key,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if row is not None:
                await session.delete(row)
