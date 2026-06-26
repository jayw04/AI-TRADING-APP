"""P8 §7 — the range-trading template: schema parity + fade-the-range on_bar."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.strategies.context import Bar
from strategies_user.templates.range_trader import RangeTrader

# 14:00 ET (mid-session) / 09:32 ET (open window) / 15:57 ET (close window), in UTC.
MID = datetime(2026, 6, 10, 18, 0, tzinfo=UTC)
OPEN_WINDOW = datetime(2026, 6, 10, 13, 32, tzinfo=UTC)
CLOSE_WINDOW = datetime(2026, 6, 10, 19, 57, tzinfo=UTC)
# opening_range mode: two bars inside the 30-min window (09:35 / 09:50 ET) and one
# after it (10:05 ET) — all in UTC.
OR_BAR_1 = datetime(2026, 6, 10, 13, 35, tzinfo=UTC)
OR_BAR_2 = datetime(2026, 6, 10, 13, 50, tzinfo=UTC)
AFTER_OR = datetime(2026, 6, 10, 14, 5, tzinfo=UTC)


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
    # Sizing reads live equity (None → fall back to initial_equity_estimate).
    ctx.get_account_equity = AsyncMock(return_value=None)
    return ctx


def _params(**over):
    # These cases exercise FIXED levels (explicit entry/exit/stop), so pin level_mode
    # — the template now defaults to opening_range (E5: daily-adaptive by default).
    return {
        **RangeTrader.default_params,
        "level_mode": "fixed",
        "entry_price": 100.0,
        "exit_price": 110.0,
        "stop_price": 95.0,
        **over,
    }


def test_schema_matches_default_params() -> None:
    assert set(RangeTrader.params_schema) == set(RangeTrader.default_params)


def test_default_level_mode_is_dynamic() -> None:
    """E5: a Range Trader created with no overrides is daily-adaptive (opening_range),
    not frozen fixed levels — so its proposal eval simulates the real rules."""
    assert RangeTrader.default_params["level_mode"] == "opening_range"
    assert RangeTrader.params_schema["level_mode"]["default"] == "opening_range"


async def test_entry_buys_at_support() -> None:
    ctx = _ctx(position_qty=None)
    strat = RangeTrader(ctx=ctx, params=_params())
    await strat.on_init()
    await strat.on_bar(_bar(MID, c=100.0))  # price <= entry 100
    ctx.submit_order.assert_called_once()
    req = ctx.submit_order.call_args.args[0]
    assert req.side.value == "buy"
    assert req.qty > 0  # risk 1000 / (100-95) = 200, capped at 100


async def test_entry_zone_default_is_exact_low() -> None:
    """entry_zone_pct=0 (default) reproduces the exact-low touch: a price *above* the
    support level does NOT buy — back-compatible."""
    ctx = _ctx(position_qty=None)
    strat = RangeTrader(ctx=ctx, params=_params())  # entry 100, exit 110, zone 0
    await strat.on_init()
    await strat.on_bar(_bar(MID, c=102.0))  # above entry 100, zone=0 → no buy
    ctx.submit_order.assert_not_called()


async def test_entry_zone_buys_within_the_band() -> None:
    """zone_pct=0.2 → ceiling = 100 + 0.2×(110−100) = 102; price 102 is inside → buy."""
    ctx = _ctx(position_qty=None)
    strat = RangeTrader(ctx=ctx, params=_params(entry_zone_pct=0.2))
    await strat.on_init()
    await strat.on_bar(_bar(MID, c=102.0))
    ctx.submit_order.assert_called_once()
    assert ctx.submit_order.call_args.args[0].side.value == "buy"


async def test_entry_zone_rejects_above_the_band() -> None:
    """price 103 > the 102 zone ceiling → no buy even with a 20% zone."""
    ctx = _ctx(position_qty=None)
    strat = RangeTrader(ctx=ctx, params=_params(entry_zone_pct=0.2))
    await strat.on_init()
    await strat.on_bar(_bar(MID, c=103.0))
    ctx.submit_order.assert_not_called()


async def test_atr_zone_widens_entry_ceiling() -> None:
    """ATR-scaled zone: mult 0.5 × atr20_pct 0.04 × entry 100 = a $2 band → ceiling 102.
    Price 101.5 is above support yet inside the ATR band → buy (default zone would reject it)."""
    ctx = _ctx(position_qty=None)
    strat = RangeTrader(ctx=ctx, params=_params(entry_zone_atr_mult=0.5, atr20_pct=0.04))
    await strat.on_init()
    await strat.on_bar(_bar(MID, c=101.5))
    ctx.submit_order.assert_called_once()
    assert ctx.submit_order.call_args.args[0].side.value == "buy"


async def test_atr_zone_off_without_atr20_pct() -> None:
    """A multiplier with no atr20_pct (0) leaves the ATR zone OFF → exact-low touch."""
    ctx = _ctx(position_qty=None)
    strat = RangeTrader(ctx=ctx, params=_params(entry_zone_atr_mult=0.5, atr20_pct=0.0))
    await strat.on_init()
    await strat.on_bar(_bar(MID, c=101.0))  # above entry 100, ATR zone inert → no buy
    ctx.submit_order.assert_not_called()


async def test_atr_zone_takes_precedence_over_pct() -> None:
    """When both are set the ATR band wins: pct 0.05 → ceiling 100.5, ATR → ceiling 102.
    Price 101.5 is above the pct ceiling but inside the ATR band, so the entry fires."""
    ctx = _ctx(position_qty=None)
    strat = RangeTrader(
        ctx=ctx, params=_params(entry_zone_pct=0.05, entry_zone_atr_mult=0.5, atr20_pct=0.04)
    )
    await strat.on_init()
    await strat.on_bar(_bar(MID, c=101.5))
    ctx.submit_order.assert_called_once()


async def test_atr_zone_clamped_to_resistance() -> None:
    """A large ATR band is clamped to resistance — never fade above exit. exit 101 with a
    raw $10 ATR band → ceiling 101; price 101.5 is above resistance → no entry."""
    ctx = _ctx(position_qty=None)
    strat = RangeTrader(
        ctx=ctx,
        params=_params(exit_price=101.0, entry_zone_atr_mult=1.0, atr20_pct=0.10),
    )
    await strat.on_init()
    await strat.on_bar(_bar(MID, c=101.5))
    ctx.submit_order.assert_not_called()


async def test_vwap_gate_off_enters_below_vwap() -> None:
    """Default (vwap_gate_pct=0): gate off, so an entry fires even far below VWAP — back-compatible."""
    ctx = _ctx(position_qty=None)
    strat = RangeTrader(ctx=ctx, params=_params())  # gate off
    await strat.on_init()
    await strat.on_bar(_bar(MID, c=120.0))  # builds VWAP high, no entry (120 > entry 100)
    await strat.on_bar(_bar(MID, c=99.0))   # ≤ entry, far below VWAP, gate off → entry
    ctx.submit_order.assert_called_once()


async def test_vwap_gate_blocks_entry_far_below_vwap() -> None:
    """Gate on: skip a support entry when price is far below session VWAP (a downtrend)."""
    ctx = _ctx(position_qty=None)
    strat = RangeTrader(ctx=ctx, params=_params(vwap_gate_pct=0.05))
    await strat.on_init()
    await strat.on_bar(_bar(MID, c=120.0))  # VWAP → 120
    await strat.on_bar(_bar(MID, c=99.0))   # VWAP 109.5; 99 < 109.5×0.95≈104 → gated
    ctx.submit_order.assert_not_called()


async def test_vwap_gate_allows_entry_near_vwap() -> None:
    """Gate on: when price is at/above the VWAP threshold, the entry passes the gate."""
    ctx = _ctx(position_qty=None)
    strat = RangeTrader(ctx=ctx, params=_params(vwap_gate_pct=0.05))
    await strat.on_init()
    await strat.on_bar(_bar(MID, c=100.0))  # VWAP=100; 100 ≥ 100×0.95=95 → entry fires
    ctx.submit_order.assert_called_once()
    assert ctx.submit_order.call_args.args[0].side.value == "buy"


async def test_exit_sells_at_resistance() -> None:
    ctx = _ctx(position_qty=Decimal("10"))
    strat = RangeTrader(ctx=ctx, params=_params())
    await strat.on_init()
    await strat.on_bar(_bar(MID, c=110.0))  # price >= exit 110
    req = ctx.submit_order.call_args.args[0]
    assert req.side.value == "sell"


async def test_stop_loss_sells_below_stop() -> None:
    ctx = _ctx(position_qty=Decimal("10"))
    strat = RangeTrader(ctx=ctx, params=_params())
    await strat.on_init()
    await strat.on_bar(_bar(MID, c=94.0))  # price <= stop 95
    ctx.submit_order.assert_called_once()
    assert ctx.submit_order.call_args.args[0].side.value == "sell"


async def test_no_entry_in_open_window() -> None:
    ctx = _ctx(position_qty=None)
    strat = RangeTrader(ctx=ctx, params=_params())
    await strat.on_init()
    await strat.on_bar(_bar(OPEN_WINDOW, c=100.0))  # within first 5 min → no trade
    ctx.submit_order.assert_not_called()


async def test_force_exit_in_close_window() -> None:
    ctx = _ctx(position_qty=Decimal("10"))
    strat = RangeTrader(ctx=ctx, params=_params())
    await strat.on_init()
    await strat.on_bar(_bar(CLOSE_WINDOW, c=105.0))  # last 5 min → force exit
    req = ctx.submit_order.call_args.args[0]
    assert req.side.value == "sell"


async def test_inert_when_levels_unset() -> None:
    ctx = _ctx(position_qty=None)
    strat = RangeTrader(ctx=ctx, params=RangeTrader.default_params)  # levels 0
    await strat.on_init()
    await strat.on_bar(_bar(MID, c=50.0))
    ctx.submit_order.assert_not_called()


async def test_daily_trade_cap() -> None:
    ctx = _ctx(position_qty=None)
    strat = RangeTrader(ctx=ctx, params=_params(max_trades_per_day=1))
    await strat.on_init()
    await strat.on_bar(_bar(MID, c=100.0))
    await strat.on_bar(_bar(MID, c=100.0))  # still flat (mock), but cap hit
    assert ctx.submit_order.call_count == 1


# ---- opening_range (dynamic daily levels) ----


async def test_opening_range_builds_levels_then_enters_at_range_low() -> None:
    ctx = _ctx(position_qty=None)
    strat = RangeTrader(
        ctx=ctx,
        params=_params(level_mode="opening_range", opening_range_minutes=30,
                       stop_buffer_pct=0.01),
    )
    await strat.on_init()
    # Build the opening range from two in-window bars: OR = [low 99.9, high 101.1].
    await strat.on_bar(_bar(OR_BAR_1, c=100.0))  # h=100.1 l=99.9
    await strat.on_bar(_bar(OR_BAR_2, c=101.0))  # h=101.1 l=100.9
    ctx.submit_order.assert_not_called()  # no entry while the range is forming
    # After the window, price dips to the dynamic entry (range low 99.9) → BUY.
    await strat.on_bar(_bar(AFTER_OR, c=99.9))
    ctx.submit_order.assert_called_once()
    assert ctx.submit_order.call_args.args[0].side.value == "buy"


async def test_opening_range_no_entry_while_forming() -> None:
    ctx = _ctx(position_qty=None)
    strat = RangeTrader(ctx=ctx, params=_params(level_mode="opening_range"))
    await strat.on_init()
    # A low price during the window must NOT trigger an entry — levels aren't set yet.
    await strat.on_bar(_bar(OR_BAR_1, c=50.0))
    ctx.submit_order.assert_not_called()


# ---- multi-symbol independence (one Range Trader over a candidate universe) ----


async def test_two_symbols_have_independent_opening_ranges() -> None:
    """Two symbols build their OWN opening ranges and enter at their OWN range lows —
    no state collision (the core multi-symbol-safety guarantee)."""
    ctx = _ctx(position_qty=None)
    strat = RangeTrader(ctx=ctx, params=_params(level_mode="opening_range", stop_buffer_pct=0.01))
    await strat.on_init()
    # AAPL OR ≈ [99.9, 101.1]; AMD OR ≈ [199.9, 201.1] — disjoint price regimes.
    await strat.on_bar(_bar(OR_BAR_1, c=100.0, symbol="AAPL"))
    await strat.on_bar(_bar(OR_BAR_2, c=101.0, symbol="AAPL"))
    await strat.on_bar(_bar(OR_BAR_1, c=200.0, symbol="AMD"))
    await strat.on_bar(_bar(OR_BAR_2, c=201.0, symbol="AMD"))
    ctx.submit_order.assert_not_called()  # both still forming

    # Each symbol's frozen levels are its own and distinct.
    aapl_levels = strat._sym["AAPL"].dyn_levels
    amd_levels = strat._sym["AMD"].dyn_levels
    assert aapl_levels is None and amd_levels is None  # not frozen until first post-OR bar

    await strat.on_bar(_bar(AFTER_OR, c=99.9, symbol="AAPL"))   # AAPL at its range low → BUY
    await strat.on_bar(_bar(AFTER_OR, c=199.9, symbol="AMD"))   # AMD at its range low → BUY
    assert strat._sym["AAPL"].dyn_levels[0] == 99.9
    assert strat._sym["AMD"].dyn_levels[0] == 199.9
    sides = [(c.args[0].symbol_ticker, c.args[0].side.value) for c in ctx.submit_order.call_args_list]
    assert ("AAPL", "buy") in sides and ("AMD", "buy") in sides


async def test_one_symbol_opening_range_does_not_leak_into_another() -> None:
    """A symbol with NO opening range of its own stays inert — it must not inherit another
    symbol's frozen levels."""
    ctx = _ctx(position_qty=None)
    strat = RangeTrader(ctx=ctx, params=_params(level_mode="opening_range"))
    await strat.on_init()
    # Only AAPL builds a range.
    await strat.on_bar(_bar(OR_BAR_1, c=100.0, symbol="AAPL"))
    await strat.on_bar(_bar(OR_BAR_2, c=101.0, symbol="AAPL"))
    # AMD's first-ever bar is post-window with no OR → no levels → no entry at any price.
    await strat.on_bar(_bar(AFTER_OR, c=99.9, symbol="AMD"))
    sides = [c.args[0].symbol_ticker for c in ctx.submit_order.call_args_list]
    assert "AMD" not in sides
    assert strat._sym["AMD"].dyn_levels is None


async def test_per_symbol_trade_counter_is_independent() -> None:
    """One symbol hitting max_trades_per_day must not consume another symbol's budget."""
    ctx = _ctx(position_qty=None)
    strat = RangeTrader(ctx=ctx, params=_params(max_trades_per_day=1))
    await strat.on_init()
    await strat.on_bar(_bar(MID, c=100.0, symbol="AAPL"))  # AAPL enters (counter → 1)
    await strat.on_bar(_bar(MID, c=100.0, symbol="AMD"))   # AMD independent → also enters
    syms = [c.args[0].symbol_ticker for c in ctx.submit_order.call_args_list]
    assert syms.count("AAPL") == 1 and syms.count("AMD") == 1
    assert strat._sym["AAPL"].trades_today == 1 and strat._sym["AMD"].trades_today == 1


async def test_per_symbol_stop_out_halt_is_independent() -> None:
    """A stop-out (range broken) on one symbol must not halt entries on another."""
    ctx = _ctx(position_qty=None)
    strat = RangeTrader(ctx=ctx, params=_params())  # fixed entry 100 / stop 95
    await strat.on_init()
    await strat.on_bar(_bar(MID, c=94.0, symbol="AAPL"))   # below stop → AAPL range broken
    await strat.on_bar(_bar(MID, c=100.0, symbol="AAPL"))  # at entry but halted → no buy
    await strat.on_bar(_bar(MID, c=100.0, symbol="AMD"))   # AMD unaffected → buys
    assert strat._sym["AAPL"].stopped_today is True
    syms = [c.args[0].symbol_ticker for c in ctx.submit_order.call_args_list]
    assert "AAPL" not in syms and syms.count("AMD") == 1


async def test_per_position_budget_caps_notional() -> None:
    """per_position_budget caps each symbol's qty to budget/price (multi-symbol allocation)."""
    ctx = _ctx(position_qty=None)
    # Without a budget this sizes to 100 (risk 1000 / per-share-risk 5 = 200, capped at 100).
    strat = RangeTrader(ctx=ctx, params=_params(per_position_budget=300.0))  # 300/100 = 3 shares
    await strat.on_init()
    await strat.on_bar(_bar(MID, c=100.0))
    assert ctx.submit_order.call_args.args[0].qty == Decimal(3)


async def test_live_equity_sizing_uses_account_balance() -> None:
    ctx = _ctx(position_qty=None)
    ctx.get_account_equity = AsyncMock(return_value=Decimal("10000"))  # small account
    strat = RangeTrader(ctx=ctx, params=_params(initial_equity_estimate=100_000))
    await strat.on_init()
    await strat.on_bar(_bar(MID, c=100.0))  # entry 100, stop 95 → per-share risk 5
    req = ctx.submit_order.call_args.args[0]
    # Live equity 10k → risk 100 → qty 20. (The 100k estimate would size to 200→cap100.)
    assert req.qty == Decimal(20)
