"""P9 §4 — momentum-portfolio template: schema parity, weekly rebalance, diff, bail-out."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pandas as pd

from app.factor_data.accessor import FactorDataUnavailable
from app.strategies.context import Bar
from strategies_user.templates.momentum_portfolio import MomentumPortfolio

# Two timestamps in the same ISO week, and one in the next week.
WK1_A = datetime(2026, 6, 8, 14, 0, tzinfo=UTC)   # Mon
WK1_B = datetime(2026, 6, 8, 14, 1, tzinfo=UTC)   # same tick, same week
WK2 = datetime(2026, 6, 15, 14, 0, tzinfo=UTC)    # next Mon, next ISO week


def _bar(ts: datetime, symbol: str = "AAA") -> Bar:
    return Bar(symbol=symbol, timeframe="1Day", t=ts, o=1, h=1, l=1, c=1, v=1)


def _scores(order: list[tuple[str, float]]) -> pd.DataFrame:
    """A momentum_scores-shaped frame: indexed by ticker, 'score' col, desc."""
    idx = [t for t, _ in order]
    df = pd.DataFrame({"score": [s for _, s in order]}, index=idx)
    df.index.name = "ticker"
    return df


def _pos(qty: int):
    p = MagicMock()
    p.side = "long"
    p.qty = Decimal(qty)
    return p


def _ctx(symbols: list[str], scores: pd.DataFrame, holdings: dict[str, int] | None = None,
         price: float = 100.0):
    holdings = holdings or {}
    ctx = MagicMock()
    ctx.symbols = symbols
    ctx.factors = MagicMock()
    ctx.factors.momentum_scores = MagicMock(return_value=scores)
    ctx.get_position_for = AsyncMock(side_effect=lambda s: _pos(holdings[s]) if s in holdings else None)
    ctx.get_recent_bars = AsyncMock(return_value=pd.DataFrame({"c": [price]}))
    ctx.submit_order = AsyncMock(return_value=MagicMock(rejection_reason=None))
    ctx.log_signal = AsyncMock(return_value=1)
    return ctx


def _orders(ctx) -> dict[str, tuple[str, Decimal]]:
    """{symbol: (side, qty)} from recorded submit_order calls."""
    out = {}
    for call in ctx.submit_order.call_args_list:
        req = call.args[0]
        out[req.symbol_ticker] = (req.side.value, req.qty)
    return out


def test_schema_matches_default_params() -> None:
    assert set(MomentumPortfolio.params_schema) == set(MomentumPortfolio.default_params)


async def test_rebalances_once_per_iso_week() -> None:
    scores = _scores([("AAA", 2.0), ("BBB", 1.0)])
    ctx = _ctx(["AAA", "BBB"], scores)
    strat = MomentumPortfolio(ctx=ctx, params={**MomentumPortfolio.default_params})
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    await strat.on_bar(_bar(WK1_B))  # same week → no second rebalance
    assert ctx.factors.momentum_scores.call_count == 1
    await strat.on_bar(_bar(WK2))    # new week → rebalances again
    assert ctx.factors.momentum_scores.call_count == 2


async def test_selection_diff_buys_targets_sells_leavers() -> None:
    # 5 candidates; top_quantile 0.4 → ceil(5*0.4)=2 → target {AAA, BBB}.
    scores = _scores([("AAA", 2.0), ("BBB", 1.0), ("CCC", 0.0), ("DDD", -1.0), ("EEE", -2.0)])
    ctx = _ctx(["AAA", "BBB", "CCC", "DDD", "EEE"], scores,
               holdings={"CCC": 10, "AAA": 5}, price=100.0)
    params = {**MomentumPortfolio.default_params, "top_quantile": 0.4, "max_names": 10,
              "initial_equity_estimate": 100_000}
    strat = MomentumPortfolio(ctx=ctx, params=params)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))

    orders = _orders(ctx)
    # equity 100k / k=2 = 50k per name; price 100 → target_qty 500
    assert orders["CCC"] == ("sell", Decimal(10))     # held, dropped out → sold flat
    assert orders["AAA"] == ("buy", Decimal(495))     # 500 target - 5 held
    assert orders["BBB"] == ("buy", Decimal(500))     # new entry
    assert "DDD" not in orders and "EEE" not in orders  # not selected, not held


async def test_names_outside_universe_never_traded() -> None:
    # scores include ZZZ which is NOT in ctx.symbols → must never be ordered.
    scores = _scores([("ZZZ", 9.0), ("AAA", 2.0), ("BBB", 1.0)])
    ctx = _ctx(["AAA", "BBB"], scores)
    params = {**MomentumPortfolio.default_params, "top_quantile": 1.0, "max_names": 10}
    strat = MomentumPortfolio(ctx=ctx, params=params)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    assert "ZZZ" not in _orders(ctx)


async def test_min_score_floor_excludes_low_names() -> None:
    scores = _scores([("AAA", 2.0), ("BBB", -0.5)])
    ctx = _ctx(["AAA", "BBB"], scores)
    params = {**MomentumPortfolio.default_params, "top_quantile": 1.0, "max_names": 10,
              "min_score": 0.0}
    strat = MomentumPortfolio(ctx=ctx, params=params)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    orders = _orders(ctx)
    assert "AAA" in orders and "BBB" not in orders  # BBB below the 0.0 floor


async def test_factor_unavailable_holds_no_orders() -> None:
    ctx = _ctx(["AAA"], _scores([("AAA", 1.0)]))
    ctx.factors.momentum_scores = MagicMock(side_effect=FactorDataUnavailable("no store"))
    strat = MomentumPortfolio(ctx=ctx, params={**MomentumPortfolio.default_params})
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    ctx.submit_order.assert_not_called()  # held, traded nothing
    # logged the bail-out
    assert any("factor_unavailable" in str(c.kwargs.get("payload", {}))
               for c in ctx.log_signal.call_args_list)


async def test_skips_target_with_no_price() -> None:
    scores = _scores([("AAA", 2.0)])
    ctx = _ctx(["AAA"], scores)
    ctx.get_recent_bars = AsyncMock(return_value=pd.DataFrame({"c": []}))  # empty → no price
    params = {**MomentumPortfolio.default_params, "top_quantile": 1.0}
    strat = MomentumPortfolio(ctx=ctx, params=params)
    await strat.on_init()
    await strat.on_bar(_bar(WK1_A))
    ctx.submit_order.assert_not_called()  # couldn't size → skipped, no order
