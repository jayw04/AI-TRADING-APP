"""Backtester — runs a Strategy against cached bars.

Loop::

    for bar_idx in range(len(bars)):
        ctx._advance_cursor(bar_idx)
        for fill in ctx._settle_pending_orders(now):     # from previous bar
            await strategy.on_fill(fill)
        for symbol in strategy.symbols:                   # dispatch this bar
            bar = ctx._current_bar_for(symbol)
            if bar is not None:
                await strategy.on_bar(Bar(...))
        ctx._mark_to_market(now)

End-of-backtest: force-close any open positions at the last close, then
compute metrics.
"""

from __future__ import annotations

import math
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pandas as pd
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

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


class BacktestCancelled(Exception):
    """Raised by the harness when ``cancel_check`` returns True between bars."""


# Async progress callback signature. Called periodically with the current bar
# index, total bars, and current bar timestamp.
ProgressCallback = Callable[[int, int, datetime], Awaitable[None]]
# Sync cancel-check callback signature. Called between bars; True bails out.
CancelCheck = Callable[[], bool]


class Backtester:
    """Stateless harness. Construct once with shared infrastructure; call
    :meth:`run` per backtest."""

    def __init__(
        self,
        bar_cache: Any,  # BarCache
        indicator_computer: Any,  # IndicatorComputer
    ) -> None:
        self._bar_cache = bar_cache
        self._indicator_computer = indicator_computer

    async def run(
        self,
        strategy_class: type[Strategy],
        symbols: list[str],
        config: BacktestConfig,
        *,
        progress_cb: ProgressCallback | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> tuple[BacktestMetrics, list[BacktestTrade], list[EquityPoint]]:
        """Run a backtest. Returns ``(metrics, trades, equity_curve)``.

        ``progress_cb`` is an optional async callable invoked periodically
        with ``(bar_idx, total_bars, current_bar_ts)``. The harness calls
        it at most every ``master_len // 200`` bars (≈200 calls total
        regardless of backtest length) plus once on the final bar.

        ``cancel_check`` is an optional sync callable checked between
        bars; returning True raises :class:`BacktestCancelled`. With both
        callbacks omitted the run is byte-identical to the P2 S3 path —
        the reproducibility test depends on that.
        """
        # 1. Load bars for every symbol over the requested range.
        bars_by_symbol: dict[str, pd.DataFrame] = {}
        for symbol in symbols:
            df = await self._bar_cache.get_bars(
                symbol, config.timeframe, config.start, config.end
            )
            if df.empty:
                logger.warning(
                    "backtest_no_bars_for_symbol",
                    symbol=symbol,
                    start=config.start.isoformat(),
                    end=config.end.isoformat(),
                )
                continue
            bars_by_symbol[symbol.upper()] = df.reset_index(drop=True)

        if not bars_by_symbol:
            return self._empty_metrics(config), [], []

        # 2. Master bar index. For MVP we assume all symbols share the same
        #    session timestamps (true for US equities on the same timeframe);
        #    use the first symbol's length as master.
        master_symbol = next(iter(bars_by_symbol.keys()))
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
        strategy = strategy_class(ctx=ctx, params=merged_params)  # type: ignore[arg-type]

        # 4. on_init
        try:
            await strategy.on_init()
        except Exception:
            logger.exception("backtest_on_init_failed", strategy=strategy_class.name)
            raise

        # Progress cadence: aim for ~200 callbacks per run regardless of
        # length. A 60-bar backtest pings on almost every bar; a 500k-bar
        # backtest pings every ~2500 bars. Bar-index-based, not wall-clock,
        # so we don't pay time.monotonic() in the hot loop.
        progress_every_n = max(1, master_len // 200)

        # 5. Main loop.
        for idx in range(master_len):
            # Cancellation honored between bars only — a bar already in
            # flight will finish even if cancellation lands mid-bar. In
            # practice strategy.on_bar is fast; if you ever ship a strategy
            # with multi-second per-bar work, thread the check deeper.
            if cancel_check is not None and cancel_check():
                raise BacktestCancelled(f"cancelled at bar {idx}/{master_len}")

            ctx._advance_cursor(idx)
            now = ctx._current_bar_ts() or config.start

            # Settle pending orders submitted on the previous bar.
            for fill in ctx._settle_pending_orders(now):
                try:
                    await strategy.on_fill(fill)
                except Exception:
                    logger.exception(
                        "backtest_on_fill_failed",
                        strategy=strategy_class.name,
                        bar=idx,
                    )
                    raise

            # Dispatch bars (one per symbol).
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
                    logger.exception(
                        "backtest_on_bar_failed",
                        strategy=strategy_class.name,
                        bar=idx,
                        symbol=symbol,
                    )
                    raise

            ctx._mark_to_market(now)

            # Progress callback at configured cadence; also fire on the
            # final bar so subscribers see ~100% before backtest.completed.
            if progress_cb is not None and (
                idx % progress_every_n == 0 or idx == master_len - 1
            ):
                try:
                    await progress_cb(idx, master_len, now)
                except Exception:
                    # A progress-cb error must never kill the backtest.
                    logger.exception(
                        "backtest_progress_cb_failed",
                        strategy=strategy_class.name,
                        bar=idx,
                    )

        # 6. on_shutdown + force-close anything still open.
        try:
            await strategy.on_shutdown()
        except Exception:
            logger.exception(
                "backtest_on_shutdown_failed", strategy=strategy_class.name
            )

        final_ts = ctx._current_bar_ts() or config.end
        ctx._force_close_all_open_positions(final_ts, label="backtest_end")

        # 7. Compute metrics.
        metrics = self._compute_metrics(ctx, config)
        equity_points = [
            EquityPoint(t=t.isoformat(), equity=float(e)) for t, e in ctx.equity_curve
        ]
        return metrics, ctx.trades, equity_points

    # ---- metrics ----

    def _empty_metrics(self, config: BacktestConfig) -> BacktestMetrics:
        return BacktestMetrics(
            total_return=0.0,
            annualized_return=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            profit_factor=float("nan"),
            trade_count=0,
            avg_win=0.0,
            avg_loss=0.0,
            avg_trade_duration_seconds=0.0,
            starting_equity=float(config.initial_equity),
            ending_equity=float(config.initial_equity),
        )

    def _compute_metrics(
        self, ctx: BacktestContext, config: BacktestConfig
    ) -> BacktestMetrics:
        starting = float(config.initial_equity)
        ending = float(ctx.equity_curve[-1][1]) if ctx.equity_curve else starting
        total_return = (ending / starting) - 1.0 if starting > 0 else 0.0

        # Annualized assumes a year is ~365 calendar days for simplicity.
        if ctx.equity_curve and config.end > config.start:
            duration_days = (config.end - config.start).days or 1
            years = duration_days / 365.0
            annualized_return = (
                (ending / starting) ** (1.0 / years) - 1.0 if years > 0 and starting > 0 else 0.0
            )
        else:
            annualized_return = 0.0

        sharpe = self._sharpe(ctx.equity_curve)
        max_dd = self._max_drawdown(ctx.equity_curve)

        closed_trades = [t for t in ctx.trades if t.pnl is not None]
        wins = [t for t in closed_trades if (t.pnl or 0) > 0]
        losses = [t for t in closed_trades if (t.pnl or 0) < 0]
        win_rate = (len(wins) / len(closed_trades)) if closed_trades else 0.0
        gross_profit = sum(t.pnl or 0 for t in wins)
        gross_loss = abs(sum(t.pnl or 0 for t in losses))
        if gross_loss > 0:
            profit_factor = gross_profit / gross_loss
        elif gross_profit > 0:
            profit_factor = float("inf")
        else:
            profit_factor = 0.0
        avg_win = (sum(t.pnl or 0 for t in wins) / len(wins)) if wins else 0.0
        avg_loss = (
            (sum(t.pnl or 0 for t in losses) / len(losses)) if losses else 0.0
        )
        avg_duration = (
            sum((t.duration_seconds or 0) for t in closed_trades) / len(closed_trades)
            if closed_trades
            else 0.0
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
        """Annualized Sharpe from daily returns (rf=0). Intra-day returns
        would produce 60×√252 nonsense for a 1-minute strategy, so we bucket
        equity by ``ts.date()`` and use the last value of each day.
        """
        if len(equity_curve) < 2:
            return 0.0
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
    session: AsyncSession,
    *,
    strategy_id: int,
    config: BacktestConfig,
    metrics: BacktestMetrics,
    trades: list[BacktestTrade],
    equity: list[EquityPoint],
    label: str = "default",
) -> BacktestResult:
    """Write a ``BacktestResult`` row. The caller owns the session lifecycle."""
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
        created_at=datetime.now(UTC),
    )
    session.add(result)
    await session.commit()
    await session.refresh(result)
    return result
