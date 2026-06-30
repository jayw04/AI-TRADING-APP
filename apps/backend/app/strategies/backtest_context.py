"""BacktestContext — drop-in replacement for StrategyContext during backtests.

A separate class instead of mode-switching the real one:

- Backtest semantics are different enough (simulated fills, deterministic
  clock, no DB writes) that overloading would be confusing.
- The real ``StrategyContext`` writes audit rows and persists signals;
  doing that during a backtest would pollute production tables.

Both contexts expose the same surface so strategy code is unchanged across
paper and backtest dispatch.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

import pandas as pd
import structlog

from app.db.enums import OrderSide, OrderType, SignalType
from app.risk import OrderRequest
from app.utils.time import EASTERN

from .backtest_models import BacktestTrade
from .context import FillEvent

logger = structlog.get_logger(__name__)


@dataclass
class _SimPosition:
    symbol: str
    qty: Decimal
    avg_entry_price: Decimal
    entry_ts: datetime
    side: str  # 'long' | 'short'
    entry_bar_index: int = 0  # master-symbol cursor at entry → bars-held metric
    # Phase 0A: running worst/best price seen DURING the hold (init to entry at open;
    # updated each bar from the bar's low/high → MAE/MFE at close).
    mae_price: Decimal = Decimal("0")
    mfe_price: Decimal = Decimal("0")


@dataclass
class _PendingOrder:
    """A market order placed on bar N, fills at bar N+1 open."""

    submit_ts: datetime
    symbol: str
    side: OrderSide
    qty: Decimal
    type: OrderType
    limit_price: Decimal | None
    stop_price: Decimal | None


@dataclass
class _PositionView:
    """Drop-in for a ``Position`` row inside the backtest. Only the fields
    the typical strategy reads are populated."""

    symbol: str
    qty: Decimal
    avg_entry_price: Decimal
    side: str


@dataclass
class _FakeOrderResult:
    order_id: int
    status: str
    rejection_reason: str | None

    @property
    def passed(self) -> bool:
        return self.status != "rejected"


class BacktestContext:
    """In-memory simulation context used by the :class:`Backtester`.

    State held:

    - ``positions``: dict[symbol → :class:`_SimPosition`]
    - ``pending_orders``: orders submitted on the current bar; filled at the
      next bar's open price.
    - ``trades``: completed round-trips, written to
      ``BacktestResult.trades_json``.
    - ``signals``: in-memory log of signals emitted via ``log_signal``.
    - ``cash``: current cash balance (drives equity tracking).
    - ``equity_curve``: ``(ts, equity)`` points sampled at end of each bar.

    Sentinel ``strategy_id`` / ``user_id`` / ``account_id`` are ``-1`` so any
    code that tries to use them as DB FKs raises loudly rather than silently
    writing a row.
    """

    def __init__(
        self,
        *,
        symbols: list[str],
        bars_by_symbol: dict[str, pd.DataFrame],
        initial_equity: Decimal,
        slippage_bps: float,
        commission_per_share: float,
        indicator_computer: Any,
        factor_accessor: Any | None = None,  # FactorAccessor (P9 §2); parity with live ctx
    ) -> None:
        self.strategy_id = -1
        self.user_id = -1
        self.account_id = -1
        self.symbols = [s.upper() for s in symbols]
        self._bars_by_symbol = {
            k.upper(): v.reset_index(drop=True) for k, v in bars_by_symbol.items()
        }
        self._cursor: int = 0  # current bar index, set by harness
        self._initial_equity = initial_equity
        self._slippage_bps = slippage_bps
        self._commission_per_share = commission_per_share
        self._indicator_computer = indicator_computer
        self._factor_accessor = factor_accessor

        self.cash: Decimal = initial_equity
        self.positions: dict[str, _SimPosition] = {}
        self.pending_orders: list[_PendingOrder] = []
        self.trades: list[BacktestTrade] = []
        self.signals: list[dict[str, Any]] = []
        self.equity_curve: list[tuple[datetime, Decimal]] = []
        # Phase 0B Opportunity Funnel: per stage, the set of (symbol, ET-day) that reached
        # it. universe/qualified/touched are strategy-reported via record_opportunity();
        # entered/stopped/exited are recorded automatically on fills/closes.
        self._funnel: dict[str, set[tuple[str, str]]] = {
            stage: set()
            for stage in (
                "universe",
                "qualified",
                "touched",
                "entered",
                "stopped",
                "exited",
            )
        }

    @property
    def factors(self) -> Any:
        """The sandboxed read-only :class:`FactorAccessor` (P9 §2). Mirrors
        ``StrategyContext.factors`` so the same strategy code runs in backtest and
        live. Raises ``FactorDataUnavailable`` if no accessor was provisioned."""
        if self._factor_accessor is None:
            from app.factor_data.accessor import FactorDataUnavailable

            raise FactorDataUnavailable(
                "factor data is not provisioned for this backtest. Pass a "
                "FactorAccessor to BacktestContext / the Backtester."
            )
        return self._factor_accessor

    # ---------- Opportunity Funnel (Phase 0B) ----------

    def record_opportunity(self, symbol: str, stage: str, day: str) -> None:
        """Strategy-reported funnel stage for a (symbol, ET-day). Idempotent per
        symbol-day (set semantics). Mirrored as a no-op on the live StrategyContext so
        the same strategy code runs in both."""
        bucket = self._funnel.get(stage)
        if bucket is not None:
            bucket.add((symbol.upper(), day))

    def opportunity_funnel_counts(self) -> dict[str, int]:
        """Distinct symbol-days that reached each funnel stage."""
        return {stage: len(s) for stage, s in self._funnel.items()}

    # ---------- harness-only methods ----------

    def _advance_cursor(self, idx: int) -> None:
        self._cursor = idx

    def _current_bar_for(self, symbol: str) -> pd.Series | None:
        df = self._bars_by_symbol.get(symbol.upper())
        if df is None or self._cursor >= len(df):
            return None
        return df.iloc[self._cursor]

    def _next_bar_open(self, symbol: str) -> Decimal | None:
        df = self._bars_by_symbol.get(symbol.upper())
        if df is None or self._cursor >= len(df):
            return None
        return Decimal(str(df.iloc[self._cursor]["o"]))

    def _settle_pending_orders(self, now: datetime) -> list[FillEvent]:
        """Fill pending orders at the current bar's open ± slippage.

        Called by the harness at the start of each bar (after the cursor
        advances). Orders submitted on the previous bar settle here.
        """
        fills: list[FillEvent] = []
        if not self.pending_orders:
            return fills

        remaining: list[_PendingOrder] = []
        for po in self.pending_orders:
            open_px = self._next_bar_open(po.symbol)
            if open_px is None:
                remaining.append(po)
                continue

            # Slippage: buys pay up, sells receive less.
            slippage = open_px * Decimal(str(self._slippage_bps / 10000.0))
            fill_price = (
                open_px + slippage if po.side == OrderSide.BUY else open_px - slippage
            )

            commission = Decimal(str(self._commission_per_share)) * po.qty
            notional = fill_price * po.qty

            if po.side == OrderSide.BUY:
                self.cash -= notional + commission
            else:
                self.cash += notional - commission

            self._apply_fill_to_position(po.symbol, po.side, po.qty, fill_price, now)

            fills.append(
                FillEvent(
                    fill_id=len(self.trades) + len(fills) + 1,
                    order_id=-1,
                    symbol=po.symbol,
                    side=po.side.value,
                    qty=po.qty,
                    price=fill_price,
                    filled_at=now,
                )
            )

        self.pending_orders = remaining
        return fills

    def _apply_fill_to_position(
        self,
        symbol: str,
        side: OrderSide,
        qty: Decimal,
        fill_price: Decimal,
        ts: datetime,
    ) -> None:
        """Update ``self.positions`` and append to ``self.trades`` on a fill."""
        current = self.positions.get(symbol)

        if side == OrderSide.BUY:
            if current is None:
                self.positions[symbol] = _SimPosition(
                    symbol=symbol,
                    qty=qty,
                    avg_entry_price=fill_price,
                    entry_ts=ts,
                    side="long",
                    entry_bar_index=self._cursor,
                    mae_price=fill_price,
                    mfe_price=fill_price,
                )
                self._funnel["entered"].add(
                    (symbol.upper(), ts.astimezone(EASTERN).date().isoformat())
                )
            elif current.side == "long":
                total_qty = current.qty + qty
                avg = (
                    current.avg_entry_price * current.qty + fill_price * qty
                ) / total_qty
                current.qty = total_qty
                current.avg_entry_price = avg
            else:  # short
                self._close_or_reduce(
                    current, qty, fill_price, ts, exit_reason="exit_signal"
                )
        else:  # SELL
            if current is None:
                # Opening short (rare for mean-reversion; allowed if risk OKs).
                self.positions[symbol] = _SimPosition(
                    symbol=symbol,
                    qty=qty,
                    avg_entry_price=fill_price,
                    entry_ts=ts,
                    side="short",
                    entry_bar_index=self._cursor,
                    mae_price=fill_price,
                    mfe_price=fill_price,
                )
                self._funnel["entered"].add(
                    (symbol.upper(), ts.astimezone(EASTERN).date().isoformat())
                )
            elif current.side == "long":
                self._close_or_reduce(
                    current, qty, fill_price, ts, exit_reason="exit_signal"
                )
            else:  # short
                total_qty = current.qty + qty
                avg = (
                    current.avg_entry_price * current.qty + fill_price * qty
                ) / total_qty
                current.qty = total_qty
                current.avg_entry_price = avg

    def _close_or_reduce(
        self,
        position: _SimPosition,
        qty: Decimal,
        exit_price: Decimal,
        exit_ts: datetime,
        exit_reason: str,
    ) -> None:
        """Realize P&L for closed (or partially closed) portions of a position."""
        closing_qty = min(position.qty, qty)
        if position.side == "long":
            pnl = float((exit_price - position.avg_entry_price) * closing_qty)
        else:
            pnl = float((position.avg_entry_price - exit_price) * closing_qty)

        # Phase 0A: excursions as signed fractions of entry (mae <= 0 adverse, mfe >= 0
        # favorable), and time from the 09:30 ET session open to the entry fill.
        entry = position.avg_entry_price
        if entry > 0:
            if position.side == "long":
                mae = float((position.mae_price - entry) / entry)
                mfe = float((position.mfe_price - entry) / entry)
            else:
                mae = float((entry - position.mae_price) / entry)
                mfe = float((entry - position.mfe_price) / entry)
        else:
            mae = mfe = 0.0
        entry_et = position.entry_ts.astimezone(EASTERN)
        session_open = entry_et.replace(hour=9, minute=30, second=0, microsecond=0)
        time_to_entry = max(0, int((entry_et - session_open).total_seconds()))

        # Phase 0B: funnel — exited (+ stopped) keyed on the ENTRY day so all stages align
        # to the same opportunity-day.
        entry_day = entry_et.date().isoformat()
        self._funnel["exited"].add((position.symbol, entry_day))
        if "stop" in exit_reason.lower():
            self._funnel["stopped"].add((position.symbol, entry_day))

        self.trades.append(
            BacktestTrade(
                symbol=position.symbol,
                side=position.side,
                entry_ts=position.entry_ts.isoformat(),
                entry_price=float(position.avg_entry_price),
                exit_ts=exit_ts.isoformat(),
                exit_price=float(exit_price),
                qty=float(closing_qty),
                pnl=pnl,
                duration_seconds=int((exit_ts - position.entry_ts).total_seconds()),
                bar_count_held=max(0, self._cursor - position.entry_bar_index),
                exit_reason=exit_reason,
                mae=mae,
                mfe=mfe,
                time_to_entry_seconds=time_to_entry,
            )
        )

        if closing_qty >= position.qty:
            del self.positions[position.symbol]
        else:
            position.qty = position.qty - closing_qty

    def _force_close_all_open_positions(self, ts: datetime, label: str) -> None:
        """At end-of-backtest: close everything still open at the most recent
        close price. The exit_reason on those trades is whatever ``label``
        the caller passes (typically ``backtest_end``)."""
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]
            df = self._bars_by_symbol.get(symbol)
            if df is None or len(df) == 0:
                continue
            last_close = Decimal(str(df.iloc[-1]["c"]))
            self._close_or_reduce(pos, pos.qty, last_close, ts, exit_reason=label)

    def _mark_to_market(self, ts: datetime) -> Decimal:
        """Sample equity at the current bar's close for the equity curve."""
        equity = self.cash
        for symbol, pos in self.positions.items():
            df = self._bars_by_symbol.get(symbol)
            if df is None or self._cursor >= len(df):
                continue
            bar = df.iloc[self._cursor]
            # Phase 0A: extend this position's running excursion with the bar's extremes.
            # Done here (the per-bar equity sample) so it runs exactly once per bar.
            bar_hi = Decimal(str(bar["h"]))
            bar_lo = Decimal(str(bar["l"]))
            if pos.side == "long":
                if bar_lo < pos.mae_price:
                    pos.mae_price = bar_lo
                if bar_hi > pos.mfe_price:
                    pos.mfe_price = bar_hi
            else:
                if bar_hi > pos.mae_price:
                    pos.mae_price = bar_hi
                if bar_lo < pos.mfe_price:
                    pos.mfe_price = bar_lo
            current_close = Decimal(str(bar["c"]))
            if pos.side == "long":
                equity += current_close * pos.qty
            else:
                # Short: cash already increased on entry; unrealized gain is
                # (entry - current) * qty, plus the original notional that
                # cash captured.
                equity += (pos.avg_entry_price - current_close) * pos.qty
                equity += pos.avg_entry_price * pos.qty
        self.equity_curve.append((ts, equity))
        return equity

    # ---------- StrategyContext-compatible API ----------

    async def get_recent_bars(
        self,
        symbol: str,
        timeframe: str,  # noqa: ARG002 — kept for signature compat with StrategyContext
        n: int = 100,
    ) -> pd.DataFrame:
        """Serve from preloaded bars, slicing to the cursor.

        Includes the current bar (so on_bar can read its own data) and the
        previous ``n - 1`` bars.
        """
        df = self._bars_by_symbol.get(symbol.upper())
        if df is None or self._cursor < 0:
            return pd.DataFrame(columns=["t", "o", "h", "l", "c", "v"])
        end_idx = self._cursor + 1  # inclusive
        start_idx = max(0, end_idx - n)
        return df.iloc[start_idx:end_idx].reset_index(drop=True)

    async def get_indicators(
        self,
        symbol: str,
        names: list[str],
        timeframe: str = "1Min",
        n_bars: int = 250,
    ) -> dict[str, Any]:
        bars = await self.get_recent_bars(symbol, timeframe, n=n_bars)
        if bars.empty:
            return {n: pd.Series(dtype="float64") for n in names}
        return self._indicator_computer.compute(
            bars,
            names=names,
            symbol=symbol.upper(),
            timeframe=timeframe,
        )

    async def get_positions(self) -> list[_PositionView]:
        return [
            _PositionView(
                symbol=sym,
                qty=p.qty,
                avg_entry_price=p.avg_entry_price,
                side=p.side,
            )
            for sym, p in self.positions.items()
        ]

    async def get_account_equity(self) -> Decimal | None:
        """Simulated account equity for position sizing during backtest.

        Mirrors ``StrategyContext.get_account_equity`` so strategies that size
        from live equity (e.g. range_trader) can run unchanged in eval jobs.
        """
        ts = self._current_bar_ts()
        if ts is None:
            return self._initial_equity if self._cursor <= 0 else None
        equity = self.cash
        for symbol, pos in self.positions.items():
            df = self._bars_by_symbol.get(symbol)
            if df is None or self._cursor >= len(df):
                continue
            current_close = Decimal(str(df.iloc[self._cursor]["c"]))
            if pos.side == "long":
                equity += current_close * pos.qty
            else:
                equity += (pos.avg_entry_price - current_close) * pos.qty
                equity += pos.avg_entry_price * pos.qty
        return equity

    async def get_position_for(self, symbol: str) -> _PositionView | None:
        symbol = symbol.upper()
        p = self.positions.get(symbol)
        if p is None:
            return None
        return _PositionView(
            symbol=symbol,
            qty=p.qty,
            avg_entry_price=p.avg_entry_price,
            side=p.side,
        )

    async def submit_order(self, order_request: OrderRequest) -> _FakeOrderResult:
        """Queue a market order for simulated fill at the next bar's open.

        Non-market orders (limit/stop/stop-limit) are rejected — see Note 3
        in the Session 3 doc. The reference RSI strategy works around this
        with a virtual stop check in ``on_bar``. Real limit/stop simulation
        lands when a strategy actually needs it.
        """
        if order_request.type != OrderType.MARKET:
            logger.warning(
                "backtest_non_market_order_ignored",
                order_type=order_request.type.value,
            )
            return _FakeOrderResult(
                order_id=-1,
                status="rejected",
                rejection_reason="non_market_orders_unsupported_in_backtest",
            )
        if order_request.qty <= 0:
            return _FakeOrderResult(
                order_id=-1,
                status="rejected",
                rejection_reason="invalid_qty",
            )

        now = self._current_bar_ts()
        if now is None:
            return _FakeOrderResult(
                order_id=-1,
                status="rejected",
                rejection_reason="no_current_bar",
            )

        self.pending_orders.append(
            _PendingOrder(
                submit_ts=now,
                symbol=order_request.symbol_ticker.upper(),
                side=order_request.side,
                qty=order_request.qty,
                type=order_request.type,
                limit_price=order_request.limit_price,
                stop_price=order_request.stop_price,
            )
        )
        return _FakeOrderResult(
            order_id=len(self.pending_orders),
            status="submitted",
            rejection_reason=None,
        )

    async def log_signal(
        self,
        symbol: str,
        type_: SignalType,
        payload: dict[str, Any] | None = None,
    ) -> int:
        ts = self._current_bar_ts()
        self.signals.append(
            {
                "symbol": symbol.upper(),
                "type": type_.value,
                "payload": payload or {},
                "ts": ts.isoformat() if ts is not None else None,
            }
        )
        return len(self.signals)

    # ---------- helpers ----------

    def _current_bar_ts(self) -> datetime | None:
        """The current bar's timestamp. Uses the first symbol's bars as the
        master clock — all symbols share the same timeline in our backtest
        (bars are pre-aligned by the harness)."""
        if not self.symbols:
            return None
        df = self._bars_by_symbol.get(self.symbols[0])
        if df is None or self._cursor >= len(df):
            return None
        t = df.iloc[self._cursor]["t"]
        return pd.Timestamp(t).to_pydatetime() if not isinstance(t, datetime) else t
