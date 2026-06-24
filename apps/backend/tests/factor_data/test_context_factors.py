"""StrategyContext / BacktestContext factor-accessor wiring (P9 §2 §4.6)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.factor_data.accessor import FactorAccessor, FactorDataUnavailable
from app.strategies.backtest_context import BacktestContext
from app.strategies.context import StrategyContext


def _strategy_ctx(factor_accessor) -> StrategyContext:
    return StrategyContext(
        strategy_id=1,
        user_id=1,
        account_id=1,
        symbols=["AAPL"],
        session_factory=None,  # not exercised here
        bar_cache=None,
        indicator_computer=None,
        submit_order_fn=lambda *a, **k: None,
        factor_accessor=factor_accessor,
    )


def test_strategy_context_exposes_injected_accessor() -> None:
    acc = FactorAccessor(None)
    ctx = _strategy_ctx(acc)
    assert ctx.factors is acc


def test_strategy_context_without_accessor_raises() -> None:
    ctx = _strategy_ctx(None)
    with pytest.raises(FactorDataUnavailable):
        _ = ctx.factors


def _backtest_ctx(factor_accessor) -> BacktestContext:
    return BacktestContext(
        symbols=["AAPL"],
        bars_by_symbol={},
        initial_equity=Decimal("10000"),
        slippage_bps=0.0,
        commission_per_share=0.0,
        indicator_computer=None,
        factor_accessor=factor_accessor,
    )


def test_backtest_context_exposes_injected_accessor() -> None:
    acc = FactorAccessor(None)
    assert _backtest_ctx(acc).factors is acc


def test_backtest_context_without_accessor_raises() -> None:
    with pytest.raises(FactorDataUnavailable):
        _ = _backtest_ctx(None).factors


@pytest.mark.asyncio
async def test_backtest_context_get_account_equity_returns_initial() -> None:
    ctx = _backtest_ctx(None)
    assert await ctx.get_account_equity() == Decimal("10000")
