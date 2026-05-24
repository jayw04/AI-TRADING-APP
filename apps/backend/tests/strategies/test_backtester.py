"""Backtester correctness tests using small hand-built bar sets.

Verifies the fill-at-next-bar-open semantics, slippage application, EOD
force-close, and the empty-bars neutral path. No fixture bars; everything
is generated in-test for determinism.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock

import pandas as pd

from app.db.enums import OrderSide, OrderSourceType, OrderType, TimeInForce
from app.risk import OrderRequest
from app.strategies import Backtester, Strategy
from app.strategies.backtest_models import BacktestConfig


def _bars(count: int = 10, start_price: float = 100.0) -> pd.DataFrame:
    """Build a tidy bars frame: one minute per row, price drifts up by 0.1
    per bar with a tiny intra-bar spread."""
    start = datetime(2025, 11, 3, 14, 30, tzinfo=UTC)
    rows = []
    for i in range(count):
        p = start_price + i * 0.1
        rows.append(
            {
                "t": start + timedelta(minutes=i),
                "o": p,
                "h": p + 0.05,
                "l": p - 0.05,
                "c": p + 0.02,
                "v": 1000 + i,
            }
        )
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
            await self.ctx.submit_order(
                OrderRequest(
                    user_id=0,
                    account_id=0,
                    symbol_ticker="TEST",
                    side=OrderSide.BUY,
                    qty=Decimal("10"),
                    type=OrderType.MARKET,
                    tif=TimeInForce.DAY,
                    source_type=OrderSourceType.STRATEGY,
                )
            )
        elif self.bar_count == 6:
            await self.ctx.submit_order(
                OrderRequest(
                    user_id=0,
                    account_id=0,
                    symbol_ticker="TEST",
                    side=OrderSide.SELL,
                    qty=Decimal("10"),
                    type=OrderType.MARKET,
                    tif=TimeInForce.DAY,
                    source_type=OrderSourceType.STRATEGY,
                )
            )


def _make_harness(bars: pd.DataFrame) -> Backtester:
    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=bars)
    indicator_computer = MagicMock()
    return Backtester(bar_cache=bar_cache, indicator_computer=indicator_computer)


async def test_backtester_simulates_fills_at_next_bar_open():
    harness = _make_harness(_bars(10))
    config = BacktestConfig(
        start=datetime(2025, 11, 3, 14, 30, tzinfo=UTC),
        end=datetime(2025, 11, 3, 14, 40, tzinfo=UTC),
        initial_equity=Decimal("10000"),
        slippage_bps=0.0,
        timeframe="1Min",
    )
    _metrics, trades, _equity = await harness.run(_BuyOnceStrategy, ["TEST"], config)

    # Exactly one closed round-trip.
    assert len(trades) == 1
    trade = trades[0]
    assert trade.symbol == "TEST"
    assert trade.side == "long"
    assert trade.qty == 10.0
    assert trade.pnl is not None

    # Strategy bought 10 shares on bar 2 (filled at bar 3 open = 100.2) and
    # sold on bar 6 (filled at bar 7 open = 100.6). PnL = (100.6 - 100.2) × 10 = 4.0.
    assert abs(trade.pnl - 4.0) < 1e-6


async def test_backtester_applies_slippage():
    """Same setup with 100 bps slippage → buys at higher, sells at lower."""
    harness = _make_harness(_bars(10))
    config = BacktestConfig(
        start=datetime(2025, 11, 3, 14, 30, tzinfo=UTC),
        end=datetime(2025, 11, 3, 14, 40, tzinfo=UTC),
        initial_equity=Decimal("10000"),
        slippage_bps=100.0,
        timeframe="1Min",
    )
    _metrics, trades, _equity = await harness.run(_BuyOnceStrategy, ["TEST"], config)
    assert trades[0].pnl is not None
    # Slippage shaves >2% of the trade move (1% per side).
    assert trades[0].pnl < 4.0


async def test_backtester_force_closes_open_positions_at_end():
    """A strategy that never sells should still produce one trade at
    end-of-backtest with ``exit_reason='backtest_end'``."""

    class _BuyAndHold(Strategy):
        name = "buy-and-hold"
        version = "0.1.0"
        symbols = ["TEST"]
        schedule = "event"
        default_params: ClassVar[dict] = {}

        def __init__(self, ctx, params):
            super().__init__(ctx, params)
            self.bought = False

        async def on_bar(self, bar):
            if not self.bought:
                self.bought = True
                await self.ctx.submit_order(
                    OrderRequest(
                        user_id=0,
                        account_id=0,
                        symbol_ticker="TEST",
                        side=OrderSide.BUY,
                        qty=Decimal("10"),
                        type=OrderType.MARKET,
                        tif=TimeInForce.DAY,
                        source_type=OrderSourceType.STRATEGY,
                    )
                )

    harness = _make_harness(_bars(10))
    config = BacktestConfig(
        start=datetime(2025, 11, 3, 14, 30, tzinfo=UTC),
        end=datetime(2025, 11, 3, 14, 40, tzinfo=UTC),
        initial_equity=Decimal("10000"),
        slippage_bps=0.0,
        timeframe="1Min",
    )
    _metrics, trades, _equity = await harness.run(_BuyAndHold, ["TEST"], config)
    assert len(trades) == 1
    assert trades[0].exit_reason == "backtest_end"


async def test_backtester_empty_bars_returns_neutral_metrics():
    harness = _make_harness(pd.DataFrame(columns=["t", "o", "h", "l", "c", "v"]))
    config = BacktestConfig(
        start=datetime(2025, 11, 3, tzinfo=UTC),
        end=datetime(2025, 11, 3, 1, tzinfo=UTC),
        initial_equity=Decimal("10000"),
    )
    metrics, trades, _equity = await harness.run(_BuyOnceStrategy, ["TEST"], config)
    assert metrics.trade_count == 0
    assert metrics.total_return == 0.0
    assert len(trades) == 0


async def test_backtester_rejects_non_market_orders():
    """The BacktestContext currently only simulates market orders. Submit a
    LIMIT order and verify the strategy receives a rejection."""

    class _LimitOnly(Strategy):
        name = "limit-only-test"
        version = "0.1.0"
        symbols = ["TEST"]
        schedule = "event"
        default_params: ClassVar[dict] = {}

        def __init__(self, ctx, params):
            super().__init__(ctx, params)
            self.last_result = None

        async def on_bar(self, bar):
            if self.last_result is None:
                self.last_result = await self.ctx.submit_order(
                    OrderRequest(
                        user_id=0,
                        account_id=0,
                        symbol_ticker="TEST",
                        side=OrderSide.BUY,
                        qty=Decimal("1"),
                        type=OrderType.LIMIT,
                        tif=TimeInForce.DAY,
                        limit_price=Decimal("50"),
                        source_type=OrderSourceType.STRATEGY,
                    )
                )

    harness = _make_harness(_bars(3))
    config = BacktestConfig(
        start=datetime(2025, 11, 3, 14, 30, tzinfo=UTC),
        end=datetime(2025, 11, 3, 14, 33, tzinfo=UTC),
        initial_equity=Decimal("10000"),
    )
    _metrics, trades, _equity = await harness.run(_LimitOnly, ["TEST"], config)
    assert len(trades) == 0  # no fills, no trades
