"""Unit-level tests for the reference RSI mean-reversion strategy.

These hand-construct RSI sweeps and verify the strategy emits the right
signals at the right thresholds. No backtester here; we drive ``on_bar``
directly via a stub context.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pandas as pd

from app.db.enums import SignalType
from app.strategies.context import Bar
from strategies_user.examples.rsi_meanreversion import RsiMeanReversion


def _bar(ts, c=100.0, symbol="AAPL", o=None, h=None, lo=None, v=1000) -> Bar:
    return Bar(
        symbol=symbol,
        timeframe="1Min",
        t=ts,
        o=o or c,
        h=h or c + 0.1,
        l=lo or c - 0.1,  # noqa: E741 — `l` matches OHLCV convention
        c=c,
        v=v,
    )


def _stub_ctx(
    rsi_value: float,
    atr_value: float = 1.0,
    has_position: bool = False,
    position_qty: Decimal = Decimal("0"),
):
    ctx = MagicMock()
    ctx.symbols = ["AAPL"]
    rsi_series = pd.Series([rsi_value])
    atr_series = pd.Series([atr_value])
    ctx.get_indicators = AsyncMock(
        return_value={"RSI14": rsi_series, "ATR14": atr_series}
    )
    if has_position:
        position = MagicMock()
        position.side = "long"
        position.qty = position_qty
        ctx.get_position_for = AsyncMock(return_value=position)
    else:
        ctx.get_position_for = AsyncMock(return_value=None)
    ctx.submit_order = AsyncMock(
        return_value=MagicMock(status="submitted", rejection_reason=None)
    )
    ctx.log_signal = AsyncMock(return_value=1)
    return ctx


async def test_entry_signal_fires_when_rsi_below_threshold():
    ctx = _stub_ctx(rsi_value=25.0)
    strategy = RsiMeanReversion(ctx=ctx, params=RsiMeanReversion.default_params)
    await strategy.on_init()
    await strategy.on_bar(_bar(datetime(2025, 11, 3, 14, 30, tzinfo=UTC), c=190.0))

    ctx.submit_order.assert_called_once()
    submitted = ctx.submit_order.call_args.args[0]
    assert submitted.side.value == "buy"
    assert submitted.qty > 0
    ctx.log_signal.assert_called_once()
    args, _kwargs = ctx.log_signal.call_args
    assert args[1] == SignalType.ENTRY


async def test_no_entry_when_rsi_above_threshold():
    ctx = _stub_ctx(rsi_value=50.0)
    strategy = RsiMeanReversion(ctx=ctx, params=RsiMeanReversion.default_params)
    await strategy.on_init()
    await strategy.on_bar(_bar(datetime(2025, 11, 3, 14, 30, tzinfo=UTC)))
    ctx.submit_order.assert_not_called()


async def test_exit_signal_fires_when_rsi_above_exit_threshold():
    ctx = _stub_ctx(rsi_value=60.0, has_position=True, position_qty=Decimal("10"))
    strategy = RsiMeanReversion(ctx=ctx, params=RsiMeanReversion.default_params)
    await strategy.on_init()
    await strategy.on_bar(_bar(datetime(2025, 11, 3, 14, 30, tzinfo=UTC)))
    ctx.submit_order.assert_called_once()
    submitted = ctx.submit_order.call_args.args[0]
    assert submitted.side.value == "sell"


async def test_no_action_in_neutral_zone():
    """RSI 40: don't enter (no position) and don't exit (with position)."""
    ctx = _stub_ctx(rsi_value=40.0)
    strategy = RsiMeanReversion(ctx=ctx, params=RsiMeanReversion.default_params)
    await strategy.on_init()
    await strategy.on_bar(_bar(datetime(2025, 11, 3, 14, 30, tzinfo=UTC)))
    ctx.submit_order.assert_not_called()

    ctx2 = _stub_ctx(rsi_value=40.0, has_position=True, position_qty=Decimal("5"))
    strategy2 = RsiMeanReversion(ctx=ctx2, params=RsiMeanReversion.default_params)
    await strategy2.on_init()
    await strategy2.on_bar(_bar(datetime(2025, 11, 3, 14, 30, tzinfo=UTC)))
    ctx2.submit_order.assert_not_called()


async def test_position_sizing_respects_max_qty():
    """Risk math: $100k equity × 1% = $1000 risk; ATR=1.0 × multiple=2.0 = $2
    stop distance → 500 shares raw → capped at max_position_qty=50."""
    ctx = _stub_ctx(rsi_value=25.0, atr_value=1.0)
    strategy = RsiMeanReversion(
        ctx=ctx,
        params={**RsiMeanReversion.default_params, "max_position_qty": 50},
    )
    await strategy.on_init()
    await strategy.on_bar(_bar(datetime(2025, 11, 3, 14, 30, tzinfo=UTC)))
    submitted = ctx.submit_order.call_args.args[0]
    assert submitted.qty <= Decimal("50")


async def test_rejection_does_not_crash_strategy():
    """ctx.submit_order returns a rejected result; strategy should keep
    running and log the rejection in the signal payload."""
    ctx = _stub_ctx(rsi_value=25.0)
    ctx.submit_order = AsyncMock(
        return_value=MagicMock(
            status="rejected", rejection_reason="POSITION_CAP_NOTIONAL"
        )
    )
    strategy = RsiMeanReversion(ctx=ctx, params=RsiMeanReversion.default_params)
    await strategy.on_init()
    # Must not raise.
    await strategy.on_bar(_bar(datetime(2025, 11, 3, 14, 30, tzinfo=UTC)))
    ctx.log_signal.assert_called_once()
    payload = ctx.log_signal.call_args.kwargs.get("payload") or {}
    assert payload.get("rejected") == "POSITION_CAP_NOTIONAL"
