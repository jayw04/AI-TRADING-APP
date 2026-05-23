# P2 Session 3 — Reference RSI Strategy + Backtest Harness

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-21 |
| Phase | **P2**, **§4 + §5** |
| Predecessor | *TradingWorkbench_P2_Session2_v0.1.md* (tag `p2-session2-complete`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | (1) The reference RSI mean-reversion strategy implementing the framework from Session 2. (2) The backtest harness that runs any Strategy over cached bars with realistic slippage, persists results, and computes the metrics surface. (3) Tests including a fixture-driven reproducibility test that locks the reference strategy's backtest output across runs. Single PR. |
| Estimated wall time | 4–5 hours |
| Stopping point | `git tag p2-session3-complete` |
| Out of scope | REST endpoints for `/strategies` and `/backtest` (Session 4). Strategies UI (Session 5). Live paper deploy (Session 4 — that's where `start_strategy` becomes accessible from the UI). |

---

## Session Goal

After this session:
- `apps/backend/strategies_user/examples/rsi_meanreversion.py` exists, subclasses `Strategy`, and implements the spec from P2 Checklist §4.1.
- A `Backtester` class can run any `Strategy` over cached bars in a deterministic, replayable way. Fills simulate at next-bar open ± `slippage_bps`.
- A backtest run produces a `BacktestResult` row with metrics, equity curve, and trade list; metrics include total return, Sharpe (daily-annualized), max drawdown, win rate, profit factor, trade count.
- Two reproducibility tests pass: (a) the reference strategy emits exactly one entry and one exit on a hand-constructed RSI sweep; (b) two backtest runs on identical fixture bars produce identical metrics down to 1e-9.
- A risk-rejection test verifies that when the strategy attempts an oversized order, the strategy logs the rejection but keeps running (no crash).

What does NOT happen this session:
- No REST endpoint that lets the UI trigger a backtest. Session 4.
- No UI rendering of the backtest results. Session 5.
- No live paper-deploy flow that wires the reference strategy into the live engine for actual paper trading. The engine *can* register it (Session 2 proved that), but the kickoff path from the UI is Session 4.

---

## Prerequisites Check

```bash
cd ~/code/AI-TRADING-APP
git status                                       # clean
git pull origin main
git describe --tags --abbrev=0                   # expect: p2-session2-complete

# Session 2 framework boots cleanly + isolation tripwire passes
./scripts/dev.sh &
sleep 25
docker compose logs backend | grep -E "strategy_engine_started"
bash apps/backend/scripts/check_strategy_isolation.sh

# Session 1 bar cache has data for at least one symbol/timeframe
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "SELECT count(*) FROM strategies; SELECT count(*) FROM backtest_results;"
# Expect: 0 / 0

docker compose down
```

- [ ] On `main`, clean tree, at `p2-session2-complete` or later.
- [ ] Strategy engine starts at boot; isolation tripwire green.

Cut the branch:

```bash
git checkout -b feat/p2-rsi-strategy-and-backtester
```

---

## §3.1 — Backtest DTOs and Configuration

Backtest data structures used by both the harness and the persisted `BacktestResult` JSON columns. Keep them dataclasses so they serialize cleanly to JSON.

Create `apps/backend/app/strategies/backtest_models.py`:

```python
"""Dataclasses used by the backtest harness.

These are the on-the-wire and in-DB shapes for metrics, trades, and equity
curves. The shape is deliberately conservative: scalars where possible,
ISO timestamp strings rather than datetimes for trivial JSON round-trip.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional


@dataclass
class BacktestConfig:
    """Parameters that drive a backtest run."""
    start: datetime
    end: datetime
    initial_equity: Decimal = Decimal("100000")
    slippage_bps: float = 5.0           # 0.05% of fill price
    commission_per_share: float = 0.0   # Alpaca paper has no commissions
    timeframe: str = "1Min"
    # Strategy-side params override (merged over the strategy's defaults).
    params: dict = field(default_factory=dict)
    seed: int = 42                      # for any RNG inside the strategy or harness


@dataclass
class BacktestTrade:
    """One round-trip: entry fill -> exit fill, with realized P&L."""
    symbol: str
    side: str                            # 'long' | 'short'
    entry_ts: str
    entry_price: float
    exit_ts: Optional[str]
    exit_price: Optional[float]
    qty: float
    pnl: Optional[float]
    duration_seconds: Optional[int]
    exit_reason: Optional[str]           # 'exit_signal' | 'stop' | 'eod' | 'open'


@dataclass
class BacktestMetrics:
    """Standard performance metrics."""
    total_return: float                  # final_equity / initial_equity - 1
    annualized_return: float
    sharpe_ratio: float                  # daily returns, annualized * sqrt(252)
    max_drawdown: float                  # negative fraction, e.g. -0.123
    win_rate: float                      # fraction of closed trades with pnl > 0
    profit_factor: float                 # gross_profit / gross_loss; inf if no losses
    trade_count: int                     # closed trades
    avg_win: float
    avg_loss: float
    avg_trade_duration_seconds: float
    starting_equity: float
    ending_equity: float


@dataclass
class EquityPoint:
    t: str         # ISO timestamp
    equity: float


def metrics_to_dict(m: BacktestMetrics) -> dict:
    return asdict(m)


def trades_to_list(trades: list[BacktestTrade]) -> list[dict]:
    return [asdict(t) for t in trades]


def equity_to_list(points: list[EquityPoint]) -> list[dict]:
    return [asdict(p) for p in points]
```

- [ ] `backtest_models.py` created.

---

## §3.2 — Backtest Context

The backtester swaps in a different `StrategyContext` that intercepts `submit_order` (simulating fills in memory) and `get_recent_bars` (serving from a preloaded bars DataFrame, not Alpaca). Same `Strategy` class runs against either context.

Create `apps/backend/app/strategies/backtest_context.py`:

```python
"""BacktestContext — drop-in replacement for StrategyContext during backtests.

Why a separate class instead of mode-switching the real one:
  * Backtest semantics are different enough (simulated fills, deterministic
    clock, no DB writes) that overloading would be confusing.
  * The real StrategyContext writes audit rows and persists signals; doing
    that during a backtest pollutes production tables.

Both contexts share the same surface signature so strategy code is unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Optional

import pandas as pd
import structlog

from app.db.enums import OrderSide, OrderSourceType, OrderType, SignalType, TimeInForce
from app.risk import OrderRequest

from .backtest_models import BacktestTrade
from .context import Bar, FillEvent

logger = structlog.get_logger(__name__)


@dataclass
class _SimPosition:
    symbol: str
    qty: Decimal
    avg_entry_price: Decimal
    entry_ts: datetime
    side: str       # 'long' | 'short'


@dataclass
class _PendingOrder:
    """A market order placed by the strategy on bar N, fills at bar N+1 open."""
    submit_ts: datetime
    symbol: str
    side: OrderSide
    qty: Decimal
    type: OrderType
    limit_price: Optional[Decimal]
    stop_price: Optional[Decimal]


class BacktestContext:
    """In-memory simulation context used by the Backtester.

    State held:
      - positions: dict[symbol -> _SimPosition]
      - pending_orders: list of orders submitted on the current bar; filled
        at the next bar's open price.
      - trades: list of completed round-trips, written to BacktestResult.trades_json.
      - signals: in-memory log of signals emitted via log_signal.
      - cash: current cash balance (for equity tracking).
      - equity_curve: list of (ts, equity) points sampled at end of each bar.

    NB: the strategy's `ctx.user_id`, `ctx.account_id`, `ctx.strategy_id` are
    set to sentinel values (-1) so any code that tries to use them as DB FKs
    raises loudly rather than silently writing rows.
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
    ) -> None:
        self.strategy_id = -1
        self.user_id = -1
        self.account_id = -1
        self.symbols = [s.upper() for s in symbols]
        self._bars_by_symbol = {k.upper(): v.reset_index(drop=True) for k, v in bars_by_symbol.items()}
        self._cursor: int = 0                      # current bar index (set by harness)
        self._initial_equity = initial_equity
        self._slippage_bps = slippage_bps
        self._commission_per_share = commission_per_share
        self._indicator_computer = indicator_computer

        self.cash: Decimal = initial_equity
        self.positions: dict[str, _SimPosition] = {}
        self.pending_orders: list[_PendingOrder] = []
        self.trades: list[BacktestTrade] = []
        self.signals: list[dict] = []
        self.equity_curve: list[tuple[datetime, Decimal]] = []

    # ---------- harness-only methods ----------

    def _advance_cursor(self, idx: int) -> None:
        self._cursor = idx

    def _current_bar_for(self, symbol: str) -> Optional[pd.Series]:
        df = self._bars_by_symbol.get(symbol.upper())
        if df is None or self._cursor >= len(df):
            return None
        return df.iloc[self._cursor]

    def _next_bar_open(self, symbol: str) -> Optional[Decimal]:
        df = self._bars_by_symbol.get(symbol.upper())
        if df is None or self._cursor + 1 >= len(df):
            return None
        return Decimal(str(df.iloc[self._cursor + 1]["o"]))

    def _settle_pending_orders(self, now: datetime) -> list[FillEvent]:
        """Called by harness at the start of bar N+1: fill orders submitted
        on bar N at the current bar's open price (± slippage)."""
        fills: list[FillEvent] = []
        if not self.pending_orders:
            return fills

        remaining: list[_PendingOrder] = []
        for po in self.pending_orders:
            open_px = self._next_bar_open(po.symbol)  # cursor still at "previous" bar
            if open_px is None:
                # No more bars; order stays pending until EOD cleanup
                remaining.append(po)
                continue

            # Apply slippage: buys pay up, sells receive less
            slippage = open_px * Decimal(str(self._slippage_bps / 10000.0))
            if po.side == OrderSide.BUY:
                fill_price = open_px + slippage
            else:
                fill_price = open_px - slippage

            commission = Decimal(str(self._commission_per_share)) * po.qty
            notional = fill_price * po.qty

            # Update cash
            if po.side == OrderSide.BUY:
                self.cash -= (notional + commission)
            else:
                self.cash += (notional - commission)

            # Update position
            self._apply_fill_to_position(po.symbol, po.side, po.qty, fill_price, now)

            fills.append(FillEvent(
                fill_id=len(self.trades) + len(fills) + 1,
                order_id=-1,
                symbol=po.symbol,
                side=po.side.value,
                qty=po.qty,
                price=fill_price,
                filled_at=now,
            ))

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
        """Update self.positions and self.trades on a simulated fill."""
        current = self.positions.get(symbol)

        if side == OrderSide.BUY:
            if current is None:
                # New long
                self.positions[symbol] = _SimPosition(
                    symbol=symbol, qty=qty, avg_entry_price=fill_price,
                    entry_ts=ts, side="long",
                )
            elif current.side == "long":
                # Adding to long: weighted average
                total_qty = current.qty + qty
                avg = (current.avg_entry_price * current.qty + fill_price * qty) / total_qty
                current.qty = total_qty
                current.avg_entry_price = avg
            elif current.side == "short":
                # Buying back a short. Realize the trade.
                self._close_or_reduce(current, qty, fill_price, ts, exit_reason="exit_signal")
        else:  # SELL
            if current is None:
                # Opening short (rare in mean-reversion strategies; allowed if risk allows)
                self.positions[symbol] = _SimPosition(
                    symbol=symbol, qty=qty, avg_entry_price=fill_price,
                    entry_ts=ts, side="short",
                )
            elif current.side == "long":
                # Closing or reducing a long
                self._close_or_reduce(current, qty, fill_price, ts, exit_reason="exit_signal")
            elif current.side == "short":
                # Adding to short
                total_qty = current.qty + qty
                avg = (current.avg_entry_price * current.qty + fill_price * qty) / total_qty
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

        self.trades.append(BacktestTrade(
            symbol=position.symbol,
            side=position.side,
            entry_ts=position.entry_ts.isoformat(),
            entry_price=float(position.avg_entry_price),
            exit_ts=exit_ts.isoformat(),
            exit_price=float(exit_price),
            qty=float(closing_qty),
            pnl=pnl,
            duration_seconds=int((exit_ts - position.entry_ts).total_seconds()),
            exit_reason=exit_reason,
        ))

        if closing_qty >= position.qty:
            # Fully closed
            del self.positions[position.symbol]
        else:
            # Reduced
            position.qty = position.qty - closing_qty

    def _force_close_all_open_positions(self, ts: datetime, label: str) -> None:
        """At EOD or end-of-backtest: close everything still open at the most
        recent close price. Used for EOD cleanup and final equity reporting."""
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
            current_close = Decimal(str(df.iloc[self._cursor]["c"]))
            if pos.side == "long":
                equity += current_close * pos.qty
            else:
                # Short: cash already increased on entry; unrealized gain is (entry - current) * qty
                equity += (pos.avg_entry_price - current_close) * pos.qty
                # Add back the original notional that the cash already captured
                equity += pos.avg_entry_price * pos.qty
        self.equity_curve.append((ts, equity))
        return equity

    # ---------- StrategyContext-compatible API ----------

    async def get_recent_bars(
        self, symbol: str, timeframe: str, n: int = 100,
    ) -> pd.DataFrame:
        """Serve from preloaded bars, slicing to the cursor."""
        df = self._bars_by_symbol.get(symbol.upper())
        if df is None or self._cursor < 0:
            return pd.DataFrame(columns=["t", "o", "h", "l", "c", "v"])
        end_idx = self._cursor + 1   # include current bar
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
            bars, names=names, symbol=symbol.upper(), timeframe=timeframe
        )

    async def get_positions(self) -> list[Any]:
        """Return synthetic position objects compatible with strategy code that
        expects DB Position rows. Only the qty / avg_entry_price / side fields
        are populated; everything else is None."""
        out = []
        for sym, p in self.positions.items():
            out.append(_PositionView(
                symbol=sym, qty=p.qty,
                avg_entry_price=p.avg_entry_price, side=p.side,
            ))
        return out

    async def get_position_for(self, symbol: str) -> Any:
        symbol = symbol.upper()
        p = self.positions.get(symbol)
        if p is None:
            return None
        return _PositionView(
            symbol=symbol, qty=p.qty,
            avg_entry_price=p.avg_entry_price, side=p.side,
        )

    async def submit_order(self, order_request: OrderRequest) -> Any:
        """Queue a market order for simulated fill at next bar's open.

        Limit / stop orders fill at the limit/stop price if the next bar's
        range touches it; otherwise carry over. For MVP we only fully
        simulate market orders. Limit/stop simulation expands when a
        strategy actually needs it (per P2 Checklist §5.3).
        """
        if order_request.type != OrderType.MARKET:
            logger.warning("backtest_non_market_order_ignored",
                           order_type=order_request.type.value)
            return _FakeOrderResult(order_id=-1, status="rejected",
                                    rejection_reason="non_market_orders_unsupported_in_backtest")
        if order_request.qty <= 0:
            return _FakeOrderResult(order_id=-1, status="rejected",
                                    rejection_reason="invalid_qty")

        now = self._current_bar_ts()
        if now is None:
            return _FakeOrderResult(order_id=-1, status="rejected",
                                    rejection_reason="no_current_bar")

        self.pending_orders.append(_PendingOrder(
            submit_ts=now,
            symbol=order_request.symbol.upper(),
            side=order_request.side,
            qty=order_request.qty,
            type=order_request.type,
            limit_price=order_request.limit_price,
            stop_price=order_request.stop_price,
        ))
        return _FakeOrderResult(
            order_id=len(self.pending_orders),
            status="submitted",
            rejection_reason=None,
        )

    async def log_signal(self, symbol: str, type_: SignalType, payload=None) -> int:
        self.signals.append({
            "symbol": symbol.upper(),
            "type": type_.value,
            "payload": payload or {},
            "ts": self._current_bar_ts().isoformat() if self._current_bar_ts() else None,
        })
        return len(self.signals)

    # ---------- helpers ----------

    def _current_bar_ts(self) -> Optional[datetime]:
        # Use the first symbol's bars as the master clock — all symbols share
        # the same timeline in our backtest (bars are pre-aligned by the harness).
        if not self.symbols:
            return None
        df = self._bars_by_symbol.get(self.symbols[0])
        if df is None or self._cursor >= len(df):
            return None
        t = df.iloc[self._cursor]["t"]
        return pd.Timestamp(t).to_pydatetime() if not isinstance(t, datetime) else t


# ---------- small shims to keep strategy code unchanged ----------


@dataclass
class _PositionView:
    """Drop-in for a Position row inside the backtest. Only the fields the
    typical strategy reads are present."""
    symbol: str
    qty: Decimal
    avg_entry_price: Decimal
    side: str


@dataclass
class _FakeOrderResult:
    order_id: int
    status: str
    rejection_reason: Optional[str]

    @property
    def passed(self) -> bool:
        return self.status not in ("rejected",)
```

- [ ] `backtest_context.py` created.

---

## §3.3 — Backtest Harness

The harness drives the strategy bar-by-bar, owns the simulated context, and produces the metrics + persisted result.

Create `apps/backend/app/strategies/backtester.py`:

```python
"""Backtester — runs a Strategy against cached bars.

Loop:
    for bar_idx in range(len(bars)):
        ctx._advance_cursor(bar_idx)
        # Settle any orders submitted on the previous bar
        for fill in ctx._settle_pending_orders(now):
            await strategy.on_fill(fill)
        # Dispatch bars (one per symbol, sorted by time)
        for symbol in strategy.symbols:
            bar = ctx._current_bar_for(symbol)
            if bar is not None:
                await strategy.on_bar(Bar.from_series(bar))
        # Mark equity at end of bar
        ctx._mark_to_market(now)

End-of-backtest: force-close any open positions at the last close, then
compute metrics.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Type

import pandas as pd
import structlog

from app.db.models.backtest_result import BacktestResult

from .backtest_context import BacktestContext
from .backtest_models import (
    BacktestConfig,
    BacktestMetrics,
    BacktestTrade,
    EquityPoint,
    equity_to_list,
    metrics_to_dict,
    trades_to_list,
)
from .base import Strategy
from .context import Bar

logger = structlog.get_logger(__name__)


class Backtester:
    """Stateless harness. Construct with shared infrastructure; run() per backtest."""

    def __init__(
        self,
        bar_cache: Any,
        indicator_computer: Any,
    ) -> None:
        self._bar_cache = bar_cache
        self._indicator_computer = indicator_computer

    async def run(
        self,
        strategy_class: Type[Strategy],
        symbols: list[str],
        config: BacktestConfig,
    ) -> tuple[BacktestMetrics, list[BacktestTrade], list[EquityPoint]]:
        """Run a backtest. Returns (metrics, trades, equity_curve)."""
        # 1. Load bars for every symbol over the requested range
        bars_by_symbol: dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            df = await self._bar_cache.get_bars(symbol, config.timeframe, config.start, config.end)
            if df.empty:
                logger.warning("backtest_no_bars_for_symbol", symbol=symbol,
                               start=config.start.isoformat(), end=config.end.isoformat())
                continue
            bars_by_symbol[symbol.upper()] = df.reset_index(drop=True)

        if not bars_by_symbol:
            empty_metrics = BacktestMetrics(
                total_return=0.0, annualized_return=0.0, sharpe_ratio=0.0,
                max_drawdown=0.0, win_rate=0.0, profit_factor=float("nan"),
                trade_count=0, avg_win=0.0, avg_loss=0.0,
                avg_trade_duration_seconds=0.0,
                starting_equity=float(config.initial_equity),
                ending_equity=float(config.initial_equity),
            )
            return empty_metrics, [], []

        # 2. Align all symbols to a master bar index. For MVP we assume all
        #    symbols have the same trading session timestamps for the
        #    requested timeframe (true for US equities), so we just use the
        #    first symbol's length as master.
        master_symbol = list(bars_by_symbol.keys())[0]
        master_len = len(bars_by_symbol[master_symbol])

        # 3. Build the backtest context and the strategy instance.
        ctx = BacktestContext(
            symbols=symbols,
            bars_by_symbol=bars_by_symbol,
            initial_equity=config.initial_equity,
            slippage_bps=config.slippage_bps,
            commission_per_share=config.commission_per_share,
            indicator_computer=self._indicator_computer,
        )
        merged_params = {**strategy_class.default_params, **config.params}
        strategy = strategy_class(ctx=ctx, params=merged_params)

        # 4. on_init
        try:
            await strategy.on_init()
        except Exception:
            logger.exception("backtest_on_init_failed", strategy=strategy_class.name)
            raise

        # 5. Main loop
        for idx in range(master_len):
            ctx._advance_cursor(idx)
            now = ctx._current_bar_ts() or config.start

            # Settle pending orders submitted on previous bar
            for fill in ctx._settle_pending_orders(now):
                try:
                    await strategy.on_fill(fill)
                except Exception:
                    logger.exception("backtest_on_fill_failed",
                                     strategy=strategy_class.name, bar=idx)
                    raise

            # Dispatch bars (one per symbol)
            for symbol in ctx.symbols:
                bar_row = ctx._current_bar_for(symbol)
                if bar_row is None:
                    continue
                bar = Bar(
                    symbol=symbol,
                    timeframe=config.timeframe,
                    t=pd.Timestamp(bar_row["t"]).to_pydatetime(),
                    o=float(bar_row["o"]),
                    h=float(bar_row["h"]),
                    l=float(bar_row["l"]),
                    c=float(bar_row["c"]),
                    v=int(bar_row["v"]),
                )
                try:
                    await strategy.on_bar(bar)
                except Exception:
                    logger.exception("backtest_on_bar_failed",
                                     strategy=strategy_class.name, bar=idx, symbol=symbol)
                    raise

            ctx._mark_to_market(now)

        # 6. on_shutdown + force-close anything still open
        try:
            await strategy.on_shutdown()
        except Exception:
            logger.exception("backtest_on_shutdown_failed", strategy=strategy_class.name)

        final_ts = ctx._current_bar_ts() or config.end
        ctx._force_close_all_open_positions(final_ts, label="backtest_end")

        # 7. Compute metrics
        metrics = self._compute_metrics(ctx, config)
        equity_points = [
            EquityPoint(t=t.isoformat(), equity=float(e)) for t, e in ctx.equity_curve
        ]
        return metrics, ctx.trades, equity_points

    def _compute_metrics(self, ctx: BacktestContext, config: BacktestConfig) -> BacktestMetrics:
        starting = float(config.initial_equity)
        ending = float(ctx.equity_curve[-1][1]) if ctx.equity_curve else starting
        total_return = (ending / starting) - 1.0 if starting > 0 else 0.0

        # Annualized return assumes a year is 252 trading days.
        if ctx.equity_curve and config.end > config.start:
            duration_days = (config.end - config.start).days or 1
            years = duration_days / 365.0
            if years > 0 and starting > 0:
                annualized_return = (ending / starting) ** (1.0 / years) - 1.0
            else:
                annualized_return = 0.0
        else:
            annualized_return = 0.0

        # Sharpe: daily returns. Resample equity curve to daily, compute.
        sharpe = self._sharpe(ctx.equity_curve)
        max_dd = self._max_drawdown(ctx.equity_curve)

        # Trade-derived stats
        closed_trades = [t for t in ctx.trades if t.pnl is not None]
        wins = [t for t in closed_trades if (t.pnl or 0) > 0]
        losses = [t for t in closed_trades if (t.pnl or 0) < 0]
        win_rate = (len(wins) / len(closed_trades)) if closed_trades else 0.0
        gross_profit = sum(t.pnl for t in wins if t.pnl is not None)
        gross_loss = abs(sum(t.pnl for t in losses if t.pnl is not None))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0
        avg_win = (sum(t.pnl for t in wins) / len(wins)) if wins else 0.0
        avg_loss = (sum(t.pnl for t in losses) / len(losses)) if losses else 0.0
        avg_duration = (
            sum((t.duration_seconds or 0) for t in closed_trades) / len(closed_trades)
            if closed_trades else 0.0
        )

        return BacktestMetrics(
            total_return=total_return,
            annualized_return=annualized_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            win_rate=win_rate,
            profit_factor=profit_factor,
            trade_count=len(closed_trades),
            avg_win=avg_win,
            avg_loss=avg_loss,
            avg_trade_duration_seconds=avg_duration,
            starting_equity=starting,
            ending_equity=ending,
        )

    @staticmethod
    def _sharpe(equity_curve: list[tuple[datetime, Decimal]]) -> float:
        """Annualized Sharpe from daily returns. Risk-free rate assumed 0."""
        if len(equity_curve) < 2:
            return 0.0
        # Bucket equity by trading day; take last value of each day.
        by_day: dict[str, float] = {}
        for ts, eq in equity_curve:
            key = ts.date().isoformat()
            by_day[key] = float(eq)
        if len(by_day) < 2:
            return 0.0
        sorted_eq = [by_day[k] for k in sorted(by_day.keys())]
        returns: list[float] = []
        for i in range(1, len(sorted_eq)):
            prev = sorted_eq[i - 1]
            if prev <= 0:
                continue
            returns.append((sorted_eq[i] - prev) / prev)
        if not returns:
            return 0.0
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / max(1, len(returns) - 1)
        stdev = math.sqrt(variance)
        if stdev == 0:
            return 0.0
        return (mean / stdev) * math.sqrt(252.0)

    @staticmethod
    def _max_drawdown(equity_curve: list[tuple[datetime, Decimal]]) -> float:
        """Max drawdown as a negative fraction (e.g. -0.123 for a 12.3% dd)."""
        if not equity_curve:
            return 0.0
        peak = float(equity_curve[0][1])
        max_dd = 0.0
        for _, eq in equity_curve:
            v = float(eq)
            if v > peak:
                peak = v
            if peak > 0:
                dd = (v - peak) / peak
                if dd < max_dd:
                    max_dd = dd
        return max_dd


async def persist_backtest_result(
    session,
    *,
    strategy_id: int,
    config: BacktestConfig,
    metrics: BacktestMetrics,
    trades: list[BacktestTrade],
    equity: list[EquityPoint],
    label: str = "default",
) -> BacktestResult:
    """Write a BacktestResult row. Session is opened+committed by the caller."""
    result = BacktestResult(
        strategy_id=strategy_id,
        label=label,
        params_json={
            **config.params,
            "slippage_bps": config.slippage_bps,
            "commission_per_share": config.commission_per_share,
            "initial_equity": str(config.initial_equity),
            "timeframe": config.timeframe,
            "seed": config.seed,
        },
        metrics_json=metrics_to_dict(metrics),
        equity_curve_json=equity_to_list(equity),
        trades_json=trades_to_list(trades),
        range_start=config.start,
        range_end=config.end,
        created_at=datetime.now(timezone.utc),
    )
    session.add(result)
    await session.commit()
    await session.refresh(result)
    return result
```

- [ ] `backtester.py` created.

Export from `apps/backend/app/strategies/__init__.py`:

```python
# Add to the existing __init__.py exports:
from .backtester import Backtester, persist_backtest_result
from .backtest_models import (
    BacktestConfig,
    BacktestMetrics,
    BacktestTrade,
    EquityPoint,
)

# Extend __all__:
__all__ += [
    "Backtester",
    "persist_backtest_result",
    "BacktestConfig",
    "BacktestMetrics",
    "BacktestTrade",
    "EquityPoint",
]
```

- [ ] Exports added.

---

## §3.4 — Reference RSI Strategy

Per P2 Checklist §4.1. Lives at `apps/backend/strategies_user/examples/rsi_meanreversion.py`. Make sure the `examples/` directory exists (it should from earlier scaffolding):

```bash
mkdir -p apps/backend/strategies_user/examples
touch apps/backend/strategies_user/examples/__init__.py
```

Create `apps/backend/strategies_user/examples/rsi_meanreversion.py`:

```python
"""Reference RSI mean-reversion strategy.

THIS IS A REFERENCE IMPLEMENTATION, NOT A RECOMMENDED TRADING STRATEGY. It
exists to exercise the Strategy interface end-to-end on a recognizable
template. Do not deploy it live without redoing the math from scratch.

Logic:
  - Universe: configurable (default ["AAPL","MSFT","SPY"]).
  - Each 1-minute bar per symbol:
      - Compute RSI(14) and ATR(14).
      - If RSI < entry_threshold (default 30) AND no current position:
          - Compute position size: 1% of equity / (atr_multiple * ATR),
            rounded down to whole shares. Capped at the per-strategy
            risk limit (handled by the Risk Engine — we don't reimplement here).
          - Submit a MARKET BUY.
      - If long position AND RSI > exit_threshold (default 55):
          - Submit a MARKET SELL for the full quantity.
  - Hard stop: 2 * ATR below entry; submitted as a STOP order when the
    entry fills (in on_fill). MVP backtester only supports market orders,
    so during backtest the stop is enforced via a virtual price check in
    on_bar instead.
  - Time stop: at end-of-day (16:00 ET), exit any remaining position.
"""
from __future__ import annotations

from datetime import time, timezone
from decimal import Decimal
from typing import ClassVar

from app.db.enums import OrderSide, OrderSourceType, OrderType, SignalType, TimeInForce
from app.risk import OrderRequest
from app.strategies import Strategy


# US/Eastern session close — bar timestamps are UTC, so convert at use time.
SESSION_CLOSE = time(16, 0)


class RsiMeanReversion(Strategy):
    name: ClassVar[str] = "rsi-mean-reversion"
    version: ClassVar[str] = "0.1.0"
    symbols: ClassVar[list[str]] = ["AAPL", "MSFT", "SPY"]
    schedule: ClassVar[str] = "*/1 * * * *"     # every minute
    default_params: ClassVar[dict] = {
        "timeframe": "1Min",
        "entry_threshold": 30.0,
        "exit_threshold": 55.0,
        "atr_multiple_for_stop": 2.0,
        "atr_multiple_for_sizing": 2.0,
        "risk_per_trade_pct": 0.01,             # 1% of equity at risk
        "initial_equity_estimate": 100_000,
        "max_position_qty": 50,                 # hard ceiling beyond Risk Engine
    }

    def __init__(self, ctx, params):
        super().__init__(ctx, params)
        # Per-symbol entry tracking for backtest virtual stops
        self._entry_state: dict[str, dict] = {}

    async def on_init(self):
        # Best-effort: pull current equity to size positions accurately.
        # In paper mode the ctx may not have a way to fetch this; fall back
        # to the configured estimate.
        self._equity_estimate = Decimal(str(self.params.get("initial_equity_estimate", 100_000)))

    async def on_bar(self, bar):
        symbol = bar.symbol
        tf = self.params["timeframe"]

        indicators = await self.ctx.get_indicators(
            symbol, names=["RSI14", "ATR14"], timeframe=tf,
        )
        rsi_series = indicators.get("RSI14")
        atr_series = indicators.get("ATR14")
        if rsi_series is None or len(rsi_series) == 0 or len(rsi_series.dropna()) == 0:
            return
        if atr_series is None or len(atr_series.dropna()) == 0:
            return

        rsi = float(rsi_series.iloc[-1])
        atr = float(atr_series.iloc[-1])
        if rsi != rsi or atr != atr or atr <= 0:    # NaN guard
            return

        position = await self.ctx.get_position_for(symbol)
        in_long = position is not None and getattr(position, "side", None) == "long" and position.qty > 0

        # ---- Virtual stop check (backtest substitute for a real STOP order) ----
        if in_long:
            state = self._entry_state.get(symbol)
            if state is not None:
                stop_price = state["entry_price"] - state["atr_at_entry"] * Decimal(
                    str(self.params["atr_multiple_for_stop"])
                )
                if Decimal(str(bar.c)) <= stop_price:
                    await self._submit(symbol, OrderSide.SELL, position.qty, reason="stop_loss")
                    return

        # ---- Time stop (end of day) ----
        bar_et = bar.t.astimezone(_us_eastern())
        if in_long and bar_et.time() >= SESSION_CLOSE:
            await self._submit(symbol, OrderSide.SELL, position.qty, reason="eod")
            return

        # ---- Entry ----
        entry_threshold = float(self.params["entry_threshold"])
        if not in_long and rsi < entry_threshold:
            qty = self._size_position(price=bar.c, atr=atr)
            if qty > 0:
                self._entry_state[symbol] = {
                    "entry_price": Decimal(str(bar.c)),
                    "atr_at_entry": Decimal(str(atr)),
                }
                await self._submit(symbol, OrderSide.BUY, Decimal(qty), reason="rsi_oversold",
                                   payload={"rsi": rsi, "atr": atr})
                return

        # ---- Exit ----
        exit_threshold = float(self.params["exit_threshold"])
        if in_long and rsi > exit_threshold:
            await self._submit(symbol, OrderSide.SELL, position.qty, reason="rsi_exit",
                               payload={"rsi": rsi})
            return

    async def on_fill(self, fill):
        # In paper mode we'd submit a STOP order here. Keeping the entry_state
        # synced regardless lets the backtest's virtual-stop logic work too.
        if fill.side == "buy":
            self._entry_state.setdefault(fill.symbol, {})
            self._entry_state[fill.symbol]["entry_price"] = Decimal(str(fill.price))
        elif fill.side == "sell":
            self._entry_state.pop(fill.symbol, None)

    # ---- helpers ----

    def _size_position(self, *, price: float, atr: float) -> int:
        """Risk-based sizing. 1% of equity / (atr_multiple * ATR), capped."""
        risk_per_trade = float(self._equity_estimate) * float(self.params["risk_per_trade_pct"])
        stop_distance = float(self.params["atr_multiple_for_sizing"]) * atr
        if stop_distance <= 0:
            return 0
        raw = risk_per_trade / stop_distance
        ceiling = float(self.params["max_position_qty"])
        return int(min(raw, ceiling))

    async def _submit(
        self,
        symbol: str,
        side: OrderSide,
        qty: Decimal,
        *,
        reason: str,
        payload: dict | None = None,
    ):
        if qty <= 0:
            return
        req = OrderRequest(
            user_id=0, account_id=0,                  # context fills these in
            symbol_id=0,                              # context resolves the symbol
            symbol=symbol,
            side=side,
            qty=qty,
            type=OrderType.MARKET,
            tif=TimeInForce.DAY,
            source_type=OrderSourceType.STRATEGY,
            source_id=None,                           # context stamps strategy id
        )
        result = await self.ctx.submit_order(req)
        # Log a signal for visibility regardless of accept/reject
        sig_type = SignalType.ENTRY if side == OrderSide.BUY else SignalType.EXIT
        log_payload = {"reason": reason, **(payload or {})}
        if hasattr(result, "rejection_reason") and getattr(result, "rejection_reason", None):
            log_payload["rejected"] = result.rejection_reason
        await self.ctx.log_signal(symbol, sig_type, payload=log_payload)


def _us_eastern():
    """Lazy zoneinfo so import order doesn't matter."""
    from zoneinfo import ZoneInfo
    return ZoneInfo("America/New_York")


# When a module contains exactly one Strategy subclass we don't need __strategy__,
# but documenting the convention here for future reference:
# __strategy__ = RsiMeanReversion
```

> **Note on the symbol_id field.** The strategy doesn't know `symbol_id` — that's a DB FK. The `StrategyContext` doesn't currently resolve it from the ticker; in P1 the OrderRouter expected it set. **You may need to extend `StrategyContext.submit_order` to resolve `symbol_id` from the `symbol` ticker before dispatching.** Add this fallback at the top of `StrategyContext.submit_order` in `context.py`:
>
> ```python
> if order_request.symbol_id == 0 and order_request.symbol:
>     from app.db.models.symbol import Symbol
>     async with self._session_factory() as session:
>         from sqlalchemy import select
>         sym = (await session.execute(
>             select(Symbol).where(Symbol.ticker == order_request.symbol.upper())
>         )).scalars().first()
>         if sym is not None:
>             order_request.symbol_id = sym.id
> ```

- [ ] `rsi_meanreversion.py` created.
- [ ] `StrategyContext.submit_order` resolves `symbol_id` from ticker when 0.

---

## §3.5 — Reproducible Backtest Fixture

We need a committed fixture that the reproducibility test can run twice and compare. The Session 1 indicator fixture (`AAPL_2025-11-03_1Min.parquet`) is reusable here.

Generate two additional days so the backtest has more than one trading day of data (needed for daily Sharpe):

```bash
cd apps/backend
uv run python scripts/generate_fixture_bars.py AAPL 2025-11-04
uv run python scripts/generate_fixture_bars.py AAPL 2025-11-05
ls tests/fixtures/bars/
# Expect: AAPL_2025-11-03_1Min.parquet, _2025-11-04_, _2025-11-05_
cd ../..
```

- [ ] Three fixture days exist for AAPL.

---

## §3.6 — Tests

Four test files, in order of dependency.

### 3.6.1 — Strategy logic unit test

Create `apps/backend/tests/strategies/test_rsi_strategy.py`:

```python
"""Unit-level tests for the reference RSI mean-reversion strategy.

These hand-construct RSI sweeps and verify the strategy emits the right
signals at the right thresholds. No backtester here; we drive on_bar
directly via a stub context.
"""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from app.db.enums import SignalType
from app.strategies.context import Bar
from strategies_user.examples.rsi_meanreversion import RsiMeanReversion


def _bar(ts, c=100.0, symbol="AAPL", o=None, h=None, l=None, v=1000):
    return Bar(
        symbol=symbol, timeframe="1Min",
        t=ts, o=o or c, h=h or c+0.1, l=l or c-0.1, c=c, v=v,
    )


def _stub_ctx(rsi_value: float, atr_value: float = 1.0,
              has_position: bool = False, position_qty: Decimal = Decimal("0")):
    ctx = MagicMock()
    ctx.symbols = ["AAPL"]
    rsi_series = pd.Series([rsi_value])
    atr_series = pd.Series([atr_value])
    ctx.get_indicators = AsyncMock(return_value={
        "RSI14": rsi_series,
        "ATR14": atr_series,
    })
    if has_position:
        position = MagicMock()
        position.side = "long"
        position.qty = position_qty
        ctx.get_position_for = AsyncMock(return_value=position)
    else:
        ctx.get_position_for = AsyncMock(return_value=None)
    ctx.submit_order = AsyncMock(return_value=MagicMock(status="submitted", rejection_reason=None))
    ctx.log_signal = AsyncMock(return_value=1)
    return ctx


@pytest.mark.asyncio
async def test_entry_signal_fires_when_rsi_below_threshold():
    ctx = _stub_ctx(rsi_value=25.0)
    strategy = RsiMeanReversion(ctx=ctx, params=RsiMeanReversion.default_params)
    await strategy.on_init()
    bar = _bar(datetime(2025, 11, 3, 14, 30, tzinfo=timezone.utc), c=190.0)

    await strategy.on_bar(bar)

    ctx.submit_order.assert_called_once()
    submitted = ctx.submit_order.call_args.args[0]
    assert submitted.side.value == "buy"
    assert submitted.qty > 0
    ctx.log_signal.assert_called_once()
    args, kwargs = ctx.log_signal.call_args
    assert args[1] == SignalType.ENTRY


@pytest.mark.asyncio
async def test_no_entry_when_rsi_above_threshold():
    ctx = _stub_ctx(rsi_value=50.0)
    strategy = RsiMeanReversion(ctx=ctx, params=RsiMeanReversion.default_params)
    await strategy.on_init()
    await strategy.on_bar(_bar(datetime(2025, 11, 3, 14, 30, tzinfo=timezone.utc)))
    ctx.submit_order.assert_not_called()


@pytest.mark.asyncio
async def test_exit_signal_fires_when_rsi_above_exit_threshold():
    ctx = _stub_ctx(rsi_value=60.0, has_position=True, position_qty=Decimal("10"))
    strategy = RsiMeanReversion(ctx=ctx, params=RsiMeanReversion.default_params)
    await strategy.on_init()
    await strategy.on_bar(_bar(datetime(2025, 11, 3, 14, 30, tzinfo=timezone.utc)))
    ctx.submit_order.assert_called_once()
    submitted = ctx.submit_order.call_args.args[0]
    assert submitted.side.value == "sell"


@pytest.mark.asyncio
async def test_no_action_in_neutral_zone():
    """RSI 40 with no position: don't enter; with position: don't exit."""
    # No position
    ctx = _stub_ctx(rsi_value=40.0)
    strategy = RsiMeanReversion(ctx=ctx, params=RsiMeanReversion.default_params)
    await strategy.on_init()
    await strategy.on_bar(_bar(datetime(2025, 11, 3, 14, 30, tzinfo=timezone.utc)))
    ctx.submit_order.assert_not_called()

    # With position
    ctx2 = _stub_ctx(rsi_value=40.0, has_position=True, position_qty=Decimal("5"))
    strategy2 = RsiMeanReversion(ctx=ctx2, params=RsiMeanReversion.default_params)
    await strategy2.on_init()
    await strategy2.on_bar(_bar(datetime(2025, 11, 3, 14, 30, tzinfo=timezone.utc)))
    ctx2.submit_order.assert_not_called()


@pytest.mark.asyncio
async def test_position_sizing_respects_max_qty():
    """Risk-per-trade math: with $100k equity, 1% risk, ATR=1.0, multiple=2.0
    -> $1000 / $2 = 500 shares. But max_position_qty caps at 50."""
    ctx = _stub_ctx(rsi_value=25.0, atr_value=1.0)
    strategy = RsiMeanReversion(
        ctx=ctx,
        params={**RsiMeanReversion.default_params, "max_position_qty": 50},
    )
    await strategy.on_init()
    await strategy.on_bar(_bar(datetime(2025, 11, 3, 14, 30, tzinfo=timezone.utc)))
    submitted = ctx.submit_order.call_args.args[0]
    assert submitted.qty <= Decimal("50")
```

### 3.6.2 — Backtester unit tests

Create `apps/backend/tests/strategies/test_backtester.py`:

```python
"""Backtester correctness tests using small hand-built bar sets."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import ClassVar
from unittest.mock import MagicMock, AsyncMock

import pandas as pd
import pytest

from app.db.enums import OrderSide, OrderSourceType, OrderType, TimeInForce
from app.risk import OrderRequest
from app.strategies import Backtester, Strategy
from app.strategies.backtest_models import BacktestConfig


def _bars(count=10, start_price=100.0):
    """Build a tidy bars frame with one minute per row."""
    start = datetime(2025, 11, 3, 14, 30, tzinfo=timezone.utc)
    rows = []
    for i in range(count):
        p = start_price + i * 0.1
        rows.append({
            "t": start + timedelta(minutes=i),
            "o": p, "h": p + 0.05, "l": p - 0.05, "c": p + 0.02, "v": 1000 + i,
        })
    return pd.DataFrame(rows)


class _BuyOnceStrategy(Strategy):
    """Buys 10 shares on the second bar, sells everything on bar 6."""
    name: ClassVar[str] = "buy-once-test"
    version: ClassVar[str] = "0.1.0"
    symbols: ClassVar[list[str]] = ["TEST"]
    schedule: ClassVar[str] = "event"
    default_params: ClassVar[dict] = {}

    def __init__(self, ctx, params):
        super().__init__(ctx, params)
        self.bar_count = 0

    async def on_bar(self, bar):
        self.bar_count += 1
        if self.bar_count == 2:
            req = OrderRequest(
                user_id=0, account_id=0, symbol_id=0, symbol="TEST",
                side=OrderSide.BUY, qty=Decimal("10"),
                type=OrderType.MARKET, tif=TimeInForce.DAY,
                source_type=OrderSourceType.STRATEGY,
            )
            await self.ctx.submit_order(req)
        elif self.bar_count == 6:
            req = OrderRequest(
                user_id=0, account_id=0, symbol_id=0, symbol="TEST",
                side=OrderSide.SELL, qty=Decimal("10"),
                type=OrderType.MARKET, tif=TimeInForce.DAY,
                source_type=OrderSourceType.STRATEGY,
            )
            await self.ctx.submit_order(req)


@pytest.fixture
def harness():
    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=_bars(10))
    indicator_computer = MagicMock()
    return Backtester(bar_cache=bar_cache, indicator_computer=indicator_computer)


@pytest.mark.asyncio
async def test_backtester_simulates_fills_at_next_bar_open(harness):
    config = BacktestConfig(
        start=datetime(2025, 11, 3, 14, 30, tzinfo=timezone.utc),
        end=datetime(2025, 11, 3, 14, 40, tzinfo=timezone.utc),
        initial_equity=Decimal("10000"),
        slippage_bps=0.0,
        timeframe="1Min",
    )
    metrics, trades, equity = await harness.run(_BuyOnceStrategy, ["TEST"], config)

    # Exactly one closed round-trip
    assert len(trades) == 1
    trade = trades[0]
    assert trade.symbol == "TEST"
    assert trade.side == "long"
    assert trade.qty == 10.0
    assert trade.pnl is not None
    # The strategy bought 10 shares on bar 2 (filled at bar 3 open) and sold
    # on bar 6 (filled at bar 7 open). Prices rise 0.1/bar starting from 100.
    # bar 3 open = 100.2; bar 7 open = 100.6; pnl = (100.6 - 100.2) * 10 = 4.0
    assert abs(trade.pnl - 4.0) < 1e-6


@pytest.mark.asyncio
async def test_backtester_applies_slippage(harness):
    """Same setup with 100 bps slippage -> buys at higher price, sells at lower."""
    config = BacktestConfig(
        start=datetime(2025, 11, 3, 14, 30, tzinfo=timezone.utc),
        end=datetime(2025, 11, 3, 14, 40, tzinfo=timezone.utc),
        initial_equity=Decimal("10000"),
        slippage_bps=100.0,                # 1%
        timeframe="1Min",
    )
    metrics, trades, equity = await harness.run(_BuyOnceStrategy, ["TEST"], config)
    # PnL drops by ~2% of the average notional vs the no-slippage case
    assert trades[0].pnl < 4.0


@pytest.mark.asyncio
async def test_backtester_force_closes_open_positions_at_end(harness):
    """A strategy that never sells should still produce one trade at end-of-backtest."""
    class _BuyAndHold(Strategy):
        name = "buy-and-hold"
        version = "0.1.0"
        symbols = ["TEST"]
        schedule = "event"
        default_params = {}

        def __init__(self, ctx, params):
            super().__init__(ctx, params)
            self.bought = False

        async def on_bar(self, bar):
            if not self.bought:
                self.bought = True
                req = OrderRequest(
                    user_id=0, account_id=0, symbol_id=0, symbol="TEST",
                    side=OrderSide.BUY, qty=Decimal("10"),
                    type=OrderType.MARKET, tif=TimeInForce.DAY,
                    source_type=OrderSourceType.STRATEGY,
                )
                await self.ctx.submit_order(req)

    config = BacktestConfig(
        start=datetime(2025, 11, 3, 14, 30, tzinfo=timezone.utc),
        end=datetime(2025, 11, 3, 14, 40, tzinfo=timezone.utc),
        initial_equity=Decimal("10000"),
        slippage_bps=0.0,
        timeframe="1Min",
    )
    metrics, trades, equity = await harness.run(_BuyAndHold, ["TEST"], config)
    assert len(trades) == 1
    assert trades[0].exit_reason == "backtest_end"


@pytest.mark.asyncio
async def test_backtester_empty_bars_returns_neutral_metrics(harness):
    harness._bar_cache.get_bars = AsyncMock(return_value=pd.DataFrame(columns=["t","o","h","l","c","v"]))
    config = BacktestConfig(
        start=datetime(2025, 11, 3, tzinfo=timezone.utc),
        end=datetime(2025, 11, 3, 1, tzinfo=timezone.utc),
        initial_equity=Decimal("10000"),
    )
    metrics, trades, equity = await harness.run(_BuyOnceStrategy, ["TEST"], config)
    assert metrics.trade_count == 0
    assert metrics.total_return == 0.0
    assert len(trades) == 0
```

### 3.6.3 — Reproducibility test (the hard one)

Create `apps/backend/tests/strategies/test_backtest_reproducibility.py`:

```python
"""Reproducibility: same strategy + same bars + same params -> same metrics.

This locks down backtest math against accidental nondeterminism: dict
iteration order, hash randomization, floating-point reordering, etc.

If this test ever flakes, do not retry. Find the source of the nondeterminism;
it's a real bug.
"""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

import pandas as pd
import pytest

from app.indicators import IndicatorComputer
from app.strategies import Backtester
from app.strategies.backtest_models import BacktestConfig
from strategies_user.examples.rsi_meanreversion import RsiMeanReversion


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "bars"


def _load_fixture_days() -> pd.DataFrame:
    """Concatenate the three committed AAPL fixture days into one frame."""
    days = ["2025-11-03", "2025-11-04", "2025-11-05"]
    frames = []
    for d in days:
        path = FIXTURE_DIR / f"AAPL_{d}_1Min.parquet"
        if not path.exists():
            pytest.skip(f"Fixture not present: {path}. Run scripts/generate_fixture_bars.py.")
        frames.append(pd.read_parquet(path))
    df = pd.concat(frames).reset_index(drop=True)
    df["t"] = pd.to_datetime(df["t"], utc=True)
    return df.sort_values("t").reset_index(drop=True)


@pytest.mark.asyncio
async def test_reference_strategy_backtest_is_reproducible():
    bars = _load_fixture_days()
    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=bars)

    indicator_computer = IndicatorComputer()
    harness = Backtester(bar_cache=bar_cache, indicator_computer=indicator_computer)

    config = BacktestConfig(
        start=datetime(2025, 11, 3, tzinfo=timezone.utc),
        end=datetime(2025, 11, 6, tzinfo=timezone.utc),
        initial_equity=Decimal("100000"),
        slippage_bps=5.0,
        timeframe="1Min",
        seed=42,
    )

    m1, t1, e1 = await harness.run(RsiMeanReversion, ["AAPL"], config)
    m2, t2, e2 = await harness.run(RsiMeanReversion, ["AAPL"], config)

    # Every metric field must match exactly
    assert m1.total_return == m2.total_return
    assert m1.sharpe_ratio == m2.sharpe_ratio
    assert m1.max_drawdown == m2.max_drawdown
    assert m1.win_rate == m2.win_rate
    assert m1.trade_count == m2.trade_count
    assert m1.starting_equity == m2.starting_equity
    assert m1.ending_equity == m2.ending_equity

    # Trade lists identical
    assert len(t1) == len(t2)
    for a, b in zip(t1, t2):
        assert a.symbol == b.symbol
        assert a.entry_ts == b.entry_ts
        assert a.exit_ts == b.exit_ts
        assert abs((a.entry_price or 0) - (b.entry_price or 0)) < 1e-9
        assert abs((a.exit_price or 0) - (b.exit_price or 0)) < 1e-9
        assert abs((a.pnl or 0) - (b.pnl or 0)) < 1e-9

    # Equity curves identical in length and last point
    assert len(e1) == len(e2)
    if e1:
        assert abs(e1[-1].equity - e2[-1].equity) < 1e-9


@pytest.mark.asyncio
async def test_reference_strategy_produces_some_metrics_shape():
    """Sanity: the reference strategy should produce a sensible metrics
    object even if no trades fire on the fixture days.

    We do NOT assert specific PnL or trade counts because those depend on
    the exact data in the fixtures, which could be regenerated. The point
    of this test is to catch 'metrics dict is None' or 'sharpe_ratio is nan'
    regressions, not to lock the strategy's performance."""
    bars = _load_fixture_days()
    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=bars)

    indicator_computer = IndicatorComputer()
    harness = Backtester(bar_cache=bar_cache, indicator_computer=indicator_computer)

    config = BacktestConfig(
        start=datetime(2025, 11, 3, tzinfo=timezone.utc),
        end=datetime(2025, 11, 6, tzinfo=timezone.utc),
        initial_equity=Decimal("100000"),
        slippage_bps=5.0,
    )

    metrics, trades, equity = await harness.run(RsiMeanReversion, ["AAPL"], config)

    # Shape checks only — values intentionally not asserted
    assert metrics.starting_equity == 100000.0
    assert metrics.ending_equity > 0
    assert metrics.trade_count >= 0
    assert isinstance(metrics.sharpe_ratio, float)
    assert not (metrics.sharpe_ratio != metrics.sharpe_ratio)  # not NaN
    assert metrics.max_drawdown <= 0.0
```

### 3.6.4 — Risk integration test

Create `apps/backend/tests/strategies/test_strategy_risk_integration.py`:

```python
"""Verify: a strategy whose order is rejected by the Risk Engine keeps running."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.db.enums import (
    OrderSide, OrderSourceType, OrderStatus, OrderType,
    RiskScopeType, SignalType, StrategyStatus, StrategyType, TimeInForce,
)
from app.db.models.account import Account
from app.db.models.risk_limits import RiskLimits
from app.db.models.signal import Signal
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.events.bus import EventBus
from app.risk import OrderRequest
from app.strategies import StrategyEngine


FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "strategies"


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(Account(id=1, user_id=1, broker="alpaca", mode="paper", label="Paper"))
        session.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ",
                           asset_class="us_equity", name="Apple", active=True))
        session.add(RiskLimits(
            user_id=1, scope_type=RiskScopeType.GLOBAL, scope_id=None,
            max_position_qty=Decimal("100"),
            max_position_notional=Decimal("25000"),
            max_gross_exposure=Decimal("100000"),
            max_daily_loss=Decimal("2000"),
            max_orders_per_minute=10,
            allow_short=False,
            created_at=_now(), updated_at=_now(),
        ))
        await session.commit()


@pytest.mark.asyncio
async def test_rejected_order_does_not_crash_strategy(session_factory, seeded):
    """Engine register, strategy submits an oversized order, router rejects;
    strategy must NOT enter ERROR status."""
    scheduler = AsyncIOScheduler()
    scheduler.start()
    bus = EventBus()
    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=pd.DataFrame())
    indicator_computer = MagicMock()
    order_router = MagicMock()
    rejected_order = MagicMock()
    rejected_order.id = 99
    rejected_order.status = OrderStatus.REJECTED
    rejected_order.rejection_reason = "POSITION_CAP_NOTIONAL"
    order_router.submit = AsyncMock(return_value=rejected_order)

    eng = StrategyEngine(
        scheduler=scheduler, session_factory=session_factory, bus=bus,
        bar_cache=bar_cache, indicator_computer=indicator_computer,
        order_router=order_router, strategies_root=FIXTURES_ROOT,
    )

    # Register the EchoStrategy from Session 2 fixtures (it doesn't submit
    # orders itself, but we'll manually invoke its context to submit).
    async with session_factory() as session:
        row = StrategyRow(
            user_id=1, name="echo-test", version="0.0.1",
            type=StrategyType.PYTHON, status=StrategyStatus.IDLE,
            code_path="echo_strategy.py", params_json={"timeframe": "1Min"},
            symbols_json=["AAPL"], schedule="event", risk_limits_id=None,
            created_at=_now(), updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        sid = row.id

    running = await eng.register(sid)

    # Have the strategy's context submit a manifestly oversized order
    req = OrderRequest(
        user_id=0, account_id=0, symbol_id=0, symbol="AAPL",
        side=OrderSide.BUY, qty=Decimal("100000"),
        type=OrderType.MARKET, tif=TimeInForce.DAY,
        source_type=OrderSourceType.STRATEGY,
    )
    result = await running.instance.ctx.submit_order(req)

    # Verify: order was rejected, but strategy is still registered and not in ERROR
    async with session_factory() as session:
        row = await session.get(StrategyRow, sid)
        assert row.status == StrategyStatus.PAPER, (
            f"Strategy entered ERROR after a rejection; should keep running. status={row.status}"
        )
    assert sid in eng._running

    await eng.shutdown()
    scheduler.shutdown(wait=False)
```

### 3.6.5 — Run the suite

```bash
cd apps/backend
uv run pytest tests/strategies -v
uv run pytest -q
cd ../..
```

- [ ] Strategy logic tests pass.
- [ ] Backtester unit tests pass.
- [ ] Reproducibility test passes (and the fixture days exist).
- [ ] Risk integration test passes.
- [ ] All prior tests still green.

---

## §3.7 — Manual Smoke

No live trading in this session, but two things to verify against a running backend:

1. The backtester can be invoked from a Python REPL with the real bar cache.
2. The result is persisted as a `BacktestResult` row.

```bash
./scripts/dev.sh &
sleep 30

# Register the reference strategy in the DB and run a backtest on cached bars
docker compose exec backend uv run python << 'EOF'
import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from sqlalchemy import select

from app.db.enums import StrategyStatus, StrategyType
from app.db.models.strategy import Strategy as StrategyRow
from app.db.session import get_session_factory

async def main():
    sf = get_session_factory()
    async with sf() as session:
        # Insert a row pointing at the reference strategy file
        existing = (await session.execute(
            select(StrategyRow).where(StrategyRow.name == "rsi-mean-reversion")
        )).scalars().first()
        if existing is None:
            row = StrategyRow(
                user_id=1, name="rsi-mean-reversion", version="0.1.0",
                type=StrategyType.PYTHON, status=StrategyStatus.IDLE,
                code_path="examples/rsi_meanreversion.py",
                params_json={"timeframe": "1Min"},
                symbols_json=["AAPL"],
                schedule="*/1 * * * *",
                risk_limits_id=None,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            print(f"Inserted strategy id={row.id}")
        else:
            print(f"Strategy exists id={existing.id}")

asyncio.run(main())
EOF

# Run a backtest via the harness directly (REST endpoint lands in Session 4)
docker compose exec backend uv run python << 'EOF'
import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from app.indicators import IndicatorComputer
from app.market_data.bar_cache import BarCache
from app.strategies import Backtester, persist_backtest_result
from app.strategies.backtest_models import BacktestConfig
from app.db.session import get_session_factory
from app.config import get_settings
from app.brokers.alpaca import AlpacaAdapter
from strategies_user.examples.rsi_meanreversion import RsiMeanReversion

async def main():
    adapter = AlpacaAdapter()
    adapter.connect()
    s = get_settings()
    bar_cache = BarCache(adapter=adapter, root=s.bars_cache_root, max_gb=s.bars_cache_max_gb)
    indicator_computer = IndicatorComputer()
    harness = Backtester(bar_cache=bar_cache, indicator_computer=indicator_computer)

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=5)
    config = BacktestConfig(
        start=start, end=end,
        initial_equity=Decimal("100000"),
        slippage_bps=5.0,
        timeframe="1Min",
    )
    metrics, trades, equity = await harness.run(RsiMeanReversion, ["AAPL"], config)
    print(f"trade_count={metrics.trade_count} total_return={metrics.total_return:.4f}")
    print(f"sharpe={metrics.sharpe_ratio:.4f} max_dd={metrics.max_drawdown:.4f}")
    print(f"equity_points={len(equity)}")

    sf = get_session_factory()
    async with sf() as session:
        from sqlalchemy import select
        from app.db.models.strategy import Strategy as StrategyRow
        row = (await session.execute(select(StrategyRow).where(StrategyRow.name == "rsi-mean-reversion"))).scalars().first()
        result = await persist_backtest_result(
            session, strategy_id=row.id, config=config,
            metrics=metrics, trades=trades, equity=equity,
            label="smoke",
        )
        print(f"Persisted BacktestResult id={result.id}")

asyncio.run(main())
EOF

# Verify persistence
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "SELECT id, strategy_id, label,
   json_extract(metrics_json, '\$.trade_count') AS trades,
   json_extract(metrics_json, '\$.total_return') AS total_return
   FROM backtest_results ORDER BY id DESC LIMIT 1;"

docker compose down
```

- [ ] Reference strategy registered in DB.
- [ ] Backtest ran and printed metrics (trade_count may be 0 or small over 5 days — normal for a tight RSI threshold).
- [ ] `BacktestResult` row persisted with metrics_json.

---

## §3.8 — Commit and PR

```bash
git add apps/backend/app/strategies/backtest_models.py
git add apps/backend/app/strategies/backtest_context.py
git add apps/backend/app/strategies/backtester.py
git add apps/backend/app/strategies/__init__.py
git add apps/backend/app/strategies/context.py
git add apps/backend/strategies_user/examples/__init__.py
git add apps/backend/strategies_user/examples/rsi_meanreversion.py
git add apps/backend/tests/fixtures/bars/
git add apps/backend/tests/strategies/

git commit -m "feat(strategies): reference rsi strategy + backtest harness

- BacktestConfig / BacktestMetrics / BacktestTrade / EquityPoint dataclasses
- BacktestContext: in-memory simulation context with same surface as
  StrategyContext. Fills simulate at next-bar open ± slippage_bps.
  Limit/stop orders explicitly unsupported in P2 (returns rejected).
- Backtester: bar-by-bar loop with end-of-backtest force-close,
  Sharpe-from-daily-returns, max-drawdown, profit-factor, win-rate.
- StrategyContext.submit_order: resolves symbol_id from ticker when 0
  (lets strategy code stay symbol_id-agnostic).
- RsiMeanReversion reference strategy in strategies_user/examples/.
  Risk-based sizing, virtual stop in on_bar (backtester doesn't simulate
  stops), EOD time stop. THIS IS REFERENCE, NOT A TRADING RECOMMENDATION.
- Tests: strategy unit, backtester correctness, full reproducibility
  on committed fixture (3 days of AAPL 1Min), risk-rejection containment.

Backtest REST endpoint + UI: Sessions 4 and 5."

git push -u origin feat/p2-rsi-strategy-and-backtester

gh pr create \
  --title "feat(strategies): reference rsi strategy + backtest harness" \
  --body "P2 Session 3 deliverable.

In scope:
- Reference RsiMeanReversion strategy in strategies_user/examples/
- BacktestContext + Backtester
- Metrics: total/annualized return, Sharpe, max DD, win rate, profit factor
- Persistence helper persist_backtest_result()
- Tests including a deterministic backtest reproducibility test on committed bars

Out of scope (next sessions):
- /api/v1/strategies/{id}/backtest endpoint (Session 4)
- Strategies UI with backtest results view (Session 5)"

gh pr checks
gh pr merge --merge --delete-branch
git checkout main && git pull
```

- [ ] PR merged.

---

## Verification Checklist (full session)

- [ ] §3.1 BacktestConfig / BacktestMetrics / BacktestTrade / EquityPoint dataclasses created.
- [ ] §3.2 BacktestContext mirrors StrategyContext surface; fills simulate at next-bar open ± slippage.
- [ ] §3.3 Backtester loops bar-by-bar, computes metrics, end-closes open positions.
- [ ] §3.4 Reference RSI strategy file created; StrategyContext resolves symbol_id from ticker.
- [ ] §3.5 Three AAPL fixture days exist on disk.
- [ ] §3.6 Four test files pass; reproducibility test runs twice and matches.
- [ ] §3.7 Live smoke runs the backtester end-to-end and persists a BacktestResult row.
- [ ] §3.8 PR merged through the protected workflow.

---

## Sign-off

```bash
git tag -a p2-session3-complete -m "P2 Session 3 complete: reference rsi strategy + backtest harness"
git push origin p2-session3-complete
```

Update `todo.md`:
- Mark P2 Session 3 complete.
- Tee up **P2 Session 4 — REST + WS topics + paper deploy lifecycle** (Checklist §6).

---

## Notes & Gotchas

1. **The reference strategy is a reference, not a recommendation.** This is repeated in the file header, the strategy class docstring, and the commit message. Future contributors will read one of those; the goal is that nobody quietly takes it live thinking it's a known-good system.

2. **Backtest fills at next-bar open, not current bar close.** This avoids "lookahead bias" where the strategy effectively trades on information it wouldn't have had in real time. The slippage on top is applied to the open price.

3. **Limit and stop orders are rejected in backtest.** §3.2 returns `non_market_orders_unsupported_in_backtest` for non-market types. The reference strategy works around this with a virtual stop check inside `on_bar` instead of submitting a STOP order. If a future strategy needs real limit/stop simulation, extend `BacktestContext._settle_pending_orders` to check the next bar's high/low against the limit/stop price — but not before there's a strategy that needs it.

4. **Sharpe ratio is daily-bucketed, annualized × √252.** Intra-day returns aren't useful (a 1-minute strategy would show 60×√252 nonsense). The implementation buckets equity points by `ts.date()` and takes the last value of each day. For a backtest spanning <2 days, Sharpe is 0 by convention.

5. **EOD force-close uses `bar.t.astimezone(US/Eastern)` to detect 16:00.** This assumes bar timestamps from Alpaca arrive as UTC (they do). If a future data source returns naive timestamps, the comparison silently misbehaves; consider adding `assert bar.t.tzinfo is not None` in `on_bar`.

6. **`symbol_id=0` is the "resolve me" sentinel.** Strategy code doesn't have DB FK awareness, so `OrderRequest.symbol_id=0` triggers the context to look up the symbol row. If you ever truly need to submit `symbol_id=0` for some reason (you don't), you'd need a different sentinel. Worth noting in `context.py`.

7. **Reproducibility test is brittle on purpose.** If pandas-ta upgrades change RSI computation in a way that shifts the entry/exit moments by even one bar, the test fails — and that's the right behavior. Don't paper over it by relaxing tolerances. Investigate, decide whether the new behavior is correct, then regenerate the fixture if so.

8. **Decimal vs float drift.** The harness mixes `Decimal` (cash, fill prices) with `float` (metrics). This is deliberate: equity tracking needs precision, metrics are reported as floats. The conversion happens at `_compute_metrics`. If you ever see Decimal in the metrics JSON, something leaked.

9. **`BacktestContext.user_id = -1` etc.** Sentinel values to make sure any code that tries to use these as DB FKs blows up immediately. Better than silently writing a row with `user_id=-1` somewhere.

10. **The risk integration test uses the EchoStrategy fixture, not the reference RSI strategy.** That's intentional: we want to test "what happens when an arbitrary strategy gets a rejection," not specifically RSI's behavior. The reference strategy logs the rejection via `log_signal`, which is good citizenship but not load-bearing for the framework.

11. **Don't start P2 Session 4 in this PR.** The REST endpoints and WS topics are a separate concern (HTTP surface, schema, gateway wiring); mixing them with strategy logic would make the PR a sprawling 3000-line beast.

---

*End of P2 Session 3 v0.1.*
