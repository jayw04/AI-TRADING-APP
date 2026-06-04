"""P6b §2b-variant — variant-vs-live comparison service."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    StrategyStatus,
)
from app.db.models.backtest_result import BacktestResult
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.strategy import Strategy
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.services.paper_variant import (
    VariantComparison,
    _pct_delta,
    _read_capital_base,
    compare_variant_to_parent,
)

NOW = datetime.now(UTC)
START = NOW - timedelta(days=5)
_oid = 0


def _round_trip(session, *, strategy_id, symbol_id, entry, exit_, qty=10, when=None):
    """Buy then sell (one long round-trip) for a strategy."""
    global _oid
    ts = when or (START + timedelta(hours=1))
    for side, price, off in ((OrderSide.BUY, entry, 0), (OrderSide.SELL, exit_, 1)):
        _oid += 1
        session.add(Order(
            id=_oid, user_id=1, account_id=1, symbol_id=symbol_id,
            side=side, qty=Decimal(str(qty)), type=OrderType.MARKET,
            status=OrderStatus.FILLED, source_type=OrderSourceType.STRATEGY,
            source_id=str(strategy_id), created_at=ts, updated_at=ts,
        ))
        session.add(Fill(
            order_id=_oid, qty=Decimal(str(qty)), price=Decimal(str(price)),
            commission=Decimal("0"), filled_at=ts + timedelta(minutes=off),
        ))


async def _seed_parent_and_variant(session, *, baseline_equity=None):
    session.add(User(id=1, email="jay@test"))
    session.add(Strategy(
        id=1, user_id=1, name="S1", code_path="strat.py", params_json={"rsi": 30},
        symbols_json=["AAPL"], status=StrategyStatus.LIVE, created_at=START, updated_at=START,
    ))
    session.add(Strategy(
        id=2, user_id=1, name="S1 (variant)", code_path="strat.py", params_json={"rsi": 40},
        symbols_json=["AAPL"], status=StrategyStatus.PAPER_VARIANT, parent_strategy_id=1,
        created_at=START, updated_at=START,
    ))
    session.add(Symbol(id=1, ticker="AAPL"))
    if baseline_equity is not None:
        session.add(BacktestResult(
            id=1, strategy_id=1, label="default", params_json={"rsi": 30},
            metrics_json={"starting_equity": baseline_equity},
            equity_curve_json=[], trades_json=[],
            range_start=START, range_end=NOW, created_at=START,
        ))


# ---- unit: capital base + delta helpers ----


def test_read_capital_base_reads_starting_equity():
    assert _read_capital_base({"starting_equity": 50000.0}) == Decimal("50000.0")


def test_read_capital_base_defaults_to_100k():
    assert _read_capital_base(None) == Decimal("100000")
    assert _read_capital_base({}) == Decimal("100000")
    assert _read_capital_base({"other": 1}) == Decimal("100000")


def test_pct_delta_safe_on_zero_baseline():
    assert _pct_delta(5.0, 0.0) is None
    assert _pct_delta(None, 1.0) is None
    assert _pct_delta(1.5, 1.0) == 50.0


# ---- integration ----


async def test_compare_returns_none_if_not_a_variant(session_factory):
    async with session_factory() as s:
        s.add(Strategy(
            id=1, user_id=1, name="S1", code_path="x.py", params_json={},
            symbols_json=[], status=StrategyStatus.LIVE, created_at=START, updated_at=START,
        ))
        await s.commit()
    async with session_factory() as s:
        assert await compare_variant_to_parent(s, 1) is None  # no parent_strategy_id


async def test_compare_returns_none_if_parent_missing(session_factory):
    async with session_factory() as s:
        s.add(Strategy(
            id=2, user_id=1, name="orphan variant", code_path="x.py", params_json={},
            symbols_json=[], status=StrategyStatus.PAPER_VARIANT, parent_strategy_id=999,
            created_at=START, updated_at=START,
        ))
        await s.commit()
    async with session_factory() as s:
        assert await compare_variant_to_parent(s, 2) is None


async def test_compare_includes_trade_counts(session_factory):
    async with session_factory() as s:
        await _seed_parent_and_variant(s)
        _round_trip(s, strategy_id=1, symbol_id=1, entry=100, exit_=110)  # parent: 1 win
        _round_trip(s, strategy_id=1, symbol_id=1, entry=100, exit_=90)   # parent: 1 loss
        _round_trip(s, strategy_id=2, symbol_id=1, entry=100, exit_=120)  # variant: 1 win
        await s.commit()
    async with session_factory() as s:
        comp = await compare_variant_to_parent(s, 2)
    assert isinstance(comp, VariantComparison)
    assert comp.live_trade_count == 2
    assert comp.variant_trade_count == 1
    assert comp.live_metrics.win_rate == 0.5
    assert comp.variant_metrics.win_rate == 1.0


async def test_compare_deltas_computed(session_factory):
    async with session_factory() as s:
        await _seed_parent_and_variant(s)
        _round_trip(s, strategy_id=1, symbol_id=1, entry=100, exit_=110)  # parent win_rate 1.0
        _round_trip(s, strategy_id=2, symbol_id=1, entry=100, exit_=120)  # variant win_rate 1.0
        await s.commit()
    async with session_factory() as s:
        comp = await compare_variant_to_parent(s, 2)
    # both 100% win → 0 pp delta; keys present.
    assert comp.deltas["win_rate_delta_pp"] == 0.0
    assert set(comp.deltas) == {
        "sharpe_delta_pct", "max_drawdown_delta_pct",
        "win_rate_delta_pp", "avg_return_delta_pct",
    }


async def test_compare_falls_back_to_100k_when_no_baseline(session_factory):
    async with session_factory() as s:
        await _seed_parent_and_variant(s, baseline_equity=None)
        _round_trip(s, strategy_id=2, symbol_id=1, entry=100, exit_=110)
        await s.commit()
    async with session_factory() as s:
        comp = await compare_variant_to_parent(s, 2)
    assert comp is not None  # runs without a baseline (capital_base = $100k default)


async def test_compare_window_starts_at_variant_created_at(session_factory):
    async with session_factory() as s:
        await _seed_parent_and_variant(s)
        await s.commit()
    async with session_factory() as s:
        comp = await compare_variant_to_parent(s, 2)
    assert comp.window_start == START
    assert comp.window_end >= NOW
