"""P10 — VWAP±σ range variant: schema parity + dynamic-band on_bar behavior."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.strategies.context import Bar
from strategies_user.templates.range_trader_vwap import RangeTraderVWAP

# 14:00 ET mid-session, in UTC; bars step forward 5 min within the same ET day.
MID = datetime(2026, 6, 10, 18, 0, tzinfo=UTC)
CLOSE_WINDOW = datetime(2026, 6, 10, 19, 57, tzinfo=UTC)  # 15:57 ET


def _bar(ts: datetime, c: float, symbol: str = "AAPL") -> Bar:
    return Bar(symbol=symbol, timeframe="5Min", t=ts, o=c, h=c + 0.1, l=c - 0.1, c=c, v=1000)


def _ctx(position_qty: Decimal | None = None):
    ctx = MagicMock()
    if position_qty is not None:
        pos = MagicMock()
        pos.side = "long"
        pos.qty = position_qty
        ctx.get_position_for = AsyncMock(return_value=pos)
    else:
        ctx.get_position_for = AsyncMock(return_value=None)
    ctx.submit_order = AsyncMock(return_value=MagicMock(rejection_reason=None))
    ctx.log_signal = AsyncMock(return_value=1)
    return ctx


async def _warmup(strat, closes, start=MID):
    """Feed a sequence of closes (5-min apart) to build session VWAP/σ."""
    for i, c in enumerate(closes):
        await strat.on_bar(_bar(start + timedelta(minutes=5 * i), c=c))


def test_schema_matches_default_params() -> None:
    assert set(RangeTraderVWAP.params_schema) == set(RangeTraderVWAP.default_params)


async def test_no_trade_before_sigma_warmup() -> None:
    ctx = _ctx(position_qty=None)
    strat = RangeTraderVWAP(ctx=ctx, params={**RangeTraderVWAP.default_params})
    await strat.on_init()
    # 3 bars (< default warmup of 6), including a deep dip — must NOT trade yet.
    await _warmup(strat, [100.0, 95.0, 100.0])
    ctx.submit_order.assert_not_called()


async def test_entry_below_lower_band_after_warmup() -> None:
    ctx = _ctx(position_qty=None)
    strat = RangeTraderVWAP(ctx=ctx, params={**RangeTraderVWAP.default_params})
    await strat.on_init()
    # Rising warm-up so closes stay above the lower band (σ > 0); then isolate
    # the deep-dip bar by resetting the mock — only it should trigger a buy.
    await _warmup(strat, [100.0, 102.0, 101.0, 103.0, 102.0, 104.0, 103.0])
    ctx.submit_order.reset_mock()
    await strat.on_bar(_bar(MID + timedelta(minutes=35), c=92.0))  # << VWAP - 1σ
    ctx.submit_order.assert_called_once()
    req = ctx.submit_order.call_args.args[0]
    assert req.side.value == "buy" and req.qty > 0


async def test_eod_force_flat_when_long() -> None:
    ctx = _ctx(position_qty=Decimal("50"))
    strat = RangeTraderVWAP(ctx=ctx, params={**RangeTraderVWAP.default_params})
    await strat.on_init()
    # Close-window bar with an open long → force-flat SELL, even pre-warmup.
    await strat.on_bar(_bar(CLOSE_WINDOW, c=100.0))
    ctx.submit_order.assert_called_once()
    assert ctx.submit_order.call_args.args[0].side.value == "sell"


async def test_exit_toward_vwap_when_long() -> None:
    ctx = _ctx(position_qty=Decimal("50"))
    strat = RangeTraderVWAP(ctx=ctx, params={**RangeTraderVWAP.default_params})
    await strat.on_init()
    # Warm up σ while holding a long, then a bar at/above VWAP → revert exit.
    await _warmup(strat, [100.0, 101.0, 99.0, 101.0, 99.0, 101.0, 100.0])
    await strat.on_bar(_bar(MID + timedelta(minutes=35), c=102.0))  # >= VWAP
    assert ctx.submit_order.called
    assert ctx.submit_order.call_args.args[0].side.value == "sell"
