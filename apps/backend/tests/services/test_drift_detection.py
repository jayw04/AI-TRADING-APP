"""P6b §1a-drift — drift_detection service.

Seeds Order + Fill + Symbol rows (Fill is the round-trip source; Order has no
fill aggregates) plus Strategy / BacktestResult / TradingProfile. The two
non-negotiables (shared formulas, sizing-invariant avg-return) have dedicated
tests.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    StrategyStatus,
)
from app.db.models.audit_log import AuditLog
from app.db.models.backtest_result import BacktestResult
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.strategy import Strategy
from app.db.models.symbol import Symbol
from app.db.models.trading_profile import TradingProfile
from app.db.models.user import User
from app.services import drift_detection as dd

NOW = datetime(2026, 6, 15, 16, 0, tzinfo=UTC)
_oid = 0


def _leg(session, *, strategy_id, symbol_id, side, qty, price, filled_at, commission=0.0):
    global _oid
    _oid += 1
    session.add(
        Order(
            id=_oid, user_id=1, account_id=1, symbol_id=symbol_id,
            side=side, qty=Decimal(str(qty)), type=OrderType.MARKET,
            status=OrderStatus.FILLED, source_type=OrderSourceType.STRATEGY,
            source_id=str(strategy_id), created_at=filled_at, updated_at=filled_at,
        )
    )
    session.add(
        Fill(
            order_id=_oid, qty=Decimal(str(qty)), price=Decimal(str(price)),
            commission=Decimal(str(commission)), filled_at=filled_at,
        )
    )


def _seed_pairs(session, *, strategy_id, symbol_id, pairs, base_ts):
    """Each (entry_price, exit_price) → a buy leg then a sell leg (one round-trip)."""
    for i, (entry, exit_) in enumerate(pairs):
        _leg(session, strategy_id=strategy_id, symbol_id=symbol_id, side=OrderSide.BUY,
             qty=10, price=entry, filled_at=base_ts + timedelta(minutes=2 * i))
        _leg(session, strategy_id=strategy_id, symbol_id=symbol_id, side=OrderSide.SELL,
             qty=10, price=exit_, filled_at=base_ts + timedelta(minutes=2 * i + 1))


def _bt_trades(pairs):
    """Backtest trades_json mirroring (entry, exit) pairs (qty 10)."""
    return [
        {"pnl": (ex - en) * 10, "entry_price": en, "qty": 10.0} for en, ex in pairs
    ]


# ---- non-negotiables ----


def test_drift_imports_shared_metric_functions():
    from app.strategies import metrics as m

    assert dd.win_rate is m.win_rate
    assert dd.avg_return_per_trade is m.avg_return_per_trade


def test_avg_return_is_sizing_invariant():
    # +1000 on qty 500 @ 100 → ret 0.02; +20 on qty 10 @ 100 → ret 0.02 (SAME).
    big = dd._baseline_metrics_from_trades_json(
        [{"pnl": 1000.0, "entry_price": 100.0, "qty": 500.0}]
    )
    small = dd._baseline_metrics_from_trades_json(
        [{"pnl": 20.0, "entry_price": 100.0, "qty": 10.0}]
    )
    assert abs(big.avg_return_per_trade - 0.02) < 1e-9
    assert big.avg_return_per_trade == small.avg_return_per_trade


def test_baseline_metrics_derived_from_trades_json():
    m = dd._baseline_metrics_from_trades_json(
        [
            {"pnl": 10.0, "entry_price": 100.0, "qty": 1.0},  # ret +0.10, win
            {"pnl": -5.0, "entry_price": 100.0, "qty": 1.0},  # ret -0.05, loss
        ]
    )
    assert m.trade_count == 2
    assert m.win_rate == 0.5
    assert abs(m.avg_return_per_trade - 0.025) < 1e-9


def test_canonical_params_normalizes_type_drift():
    assert dd._canonical_params({"a": 1}) == dd._canonical_params({"a": "1"})


# ---- round-trip reconstruction (fill-level) ----


async def test_reconstruct_round_trips_long_only_one_pair(session_factory):
    async with session_factory() as s:
        s.add(Symbol(id=1, ticker="AAPL"))
        _seed_pairs(s, strategy_id=1, symbol_id=1, pairs=[(100, 110)], base_ts=NOW - timedelta(days=2))
        await s.commit()
    async with session_factory() as s:
        trips = await dd.reconstruct_round_trips(s, 1, NOW - timedelta(days=30))
    assert len(trips) == 1
    assert trips[0].side == "long"
    assert trips[0].pnl == (110 - 100) * 10
    assert abs(trips[0].ret - 0.10) < 1e-9


async def test_reconstruct_round_trips_short_only_one_pair(session_factory):
    async with session_factory() as s:
        s.add(Symbol(id=1, ticker="AAPL"))
        # sell-to-open then buy-to-cover → short round-trip
        _leg(s, strategy_id=1, symbol_id=1, side=OrderSide.SELL, qty=10, price=110, filled_at=NOW - timedelta(days=2))
        _leg(s, strategy_id=1, symbol_id=1, side=OrderSide.BUY, qty=10, price=100, filled_at=NOW - timedelta(days=1))
        await s.commit()
    async with session_factory() as s:
        trips = await dd.reconstruct_round_trips(s, 1, NOW - timedelta(days=30))
    assert len(trips) == 1
    assert trips[0].side == "short"
    assert trips[0].pnl == (110 - 100) * 10  # short profits when exit < entry


async def test_reconstruct_round_trips_pnl_net_of_commission(session_factory):
    async with session_factory() as s:
        s.add(Symbol(id=1, ticker="AAPL"))
        _leg(s, strategy_id=1, symbol_id=1, side=OrderSide.BUY, qty=10, price=100, filled_at=NOW - timedelta(days=2), commission=3.0)
        _leg(s, strategy_id=1, symbol_id=1, side=OrderSide.SELL, qty=10, price=110, filled_at=NOW - timedelta(days=1), commission=2.0)
        await s.commit()
    async with session_factory() as s:
        trips = await dd.reconstruct_round_trips(s, 1, NOW - timedelta(days=30))
    # gross 100 - (3 + 2) commission = 95
    assert trips[0].pnl == 95.0


async def test_reconstruct_round_trips_partial_exit_leaves_open_position(session_factory):
    async with session_factory() as s:
        s.add(Symbol(id=1, ticker="AAPL"))
        _leg(s, strategy_id=1, symbol_id=1, side=OrderSide.BUY, qty=10, price=100, filled_at=NOW - timedelta(days=3))
        _leg(s, strategy_id=1, symbol_id=1, side=OrderSide.SELL, qty=4, price=110, filled_at=NOW - timedelta(days=2))
        await s.commit()
    async with session_factory() as s:
        trips = await dd.reconstruct_round_trips(s, 1, NOW - timedelta(days=30))
    assert len(trips) == 1
    assert trips[0].qty == 4
    assert trips[0].pnl == (110 - 100) * 4


async def test_reconstruct_round_trips_multiple_symbols_isolated(session_factory):
    async with session_factory() as s:
        s.add(Symbol(id=1, ticker="AAPL"))
        s.add(Symbol(id=2, ticker="MSFT"))
        _seed_pairs(s, strategy_id=1, symbol_id=1, pairs=[(100, 110)], base_ts=NOW - timedelta(days=3))
        _seed_pairs(s, strategy_id=1, symbol_id=2, pairs=[(200, 190)], base_ts=NOW - timedelta(days=2))
        await s.commit()
    async with session_factory() as s:
        trips = await dd.reconstruct_round_trips(s, 1, NOW - timedelta(days=30))
    assert len(trips) == 2
    assert {t.symbol for t in trips} == {"AAPL", "MSFT"}


async def test_reconstruct_round_trips_no_fills_returns_empty(session_factory):
    async with session_factory() as s:
        s.add(Symbol(id=1, ticker="AAPL"))
        await s.commit()
    async with session_factory() as s:
        trips = await dd.reconstruct_round_trips(s, 1, NOW - timedelta(days=30))
    assert trips == []


# ---- detect_drift (pure) ----


def _m(win_rate, avg_return, n=20):
    return dd.DriftMetrics(trade_count=n, win_rate=win_rate, avg_return_per_trade=avg_return)


def test_detect_drift_within_thresholds_returns_false():
    th = dd._read_thresholds(None)
    is_drift, _, _, breached = dd.detect_drift(_m(0.60, 0.020), _m(0.62, 0.021), th)
    assert is_drift is False
    assert breached == []


def test_detect_drift_win_rate_drop_breached():
    th = dd._read_thresholds(None)
    is_drift, wr_delta, _, breached = dd.detect_drift(_m(0.40, 0.02), _m(0.65, 0.02), th)
    assert is_drift is True
    assert "win_rate" in breached
    assert wr_delta == (0.40 - 0.65) * 100


def test_detect_drift_avg_return_drop_breached():
    th = dd._read_thresholds(None)
    is_drift, _, ret_delta, breached = dd.detect_drift(_m(0.60, 0.005), _m(0.60, 0.020), th)
    assert is_drift is True
    assert "avg_return_per_trade" in breached
    assert ret_delta < 0


def test_detect_drift_baseline_zero_return_skips_check_safely():
    th = dd._read_thresholds(None)
    is_drift, _, ret_delta, breached = dd.detect_drift(_m(0.60, 0.02), _m(0.60, 0.0), th)
    assert "avg_return_per_trade" not in breached
    assert ret_delta == 0.0
    assert is_drift is False


# ---- orchestrator ----


def _seed_strategy(session, *, sid=1, status=StrategyStatus.PAPER, params=None):
    session.add(
        Strategy(
            id=sid, user_id=1, name=f"S{sid}", params_json=params or {"rsi": 30},
            symbols_json=["AAPL"], status=status, created_at=NOW, updated_at=NOW,
        )
    )


def _seed_baseline(session, *, sid=1, pairs, params=None):
    session.add(
        BacktestResult(
            strategy_id=sid, label="baseline", params_json=params or {"rsi": 30},
            metrics_json={}, equity_curve_json=[], trades_json=_bt_trades(pairs),
            range_start=NOW - timedelta(days=90), range_end=NOW, created_at=NOW,
        )
    )


async def test_run_drift_idle_strategy_skips_not_active(session_factory):
    async with session_factory() as s:
        _seed_strategy(s, status=StrategyStatus.IDLE)
        await s.commit()
        strat = await s.get(Strategy, 1)
        result = await dd.run_drift_detection_for_strategy(s, strat, {})
    assert isinstance(result, dd.DriftSkip)
    assert result.reason == "not_active"


async def test_run_drift_no_baseline_skips(session_factory):
    async with session_factory() as s:
        _seed_strategy(s)
        await s.commit()
        strat = await s.get(Strategy, 1)
        result = await dd.run_drift_detection_for_strategy(s, strat, {})
    assert isinstance(result, dd.DriftSkip)
    assert result.reason == "no_baseline"


async def test_run_drift_insufficient_trades_skips(session_factory):
    async with session_factory() as s:
        s.add(Symbol(id=1, ticker="AAPL"))
        _seed_strategy(s)
        _seed_baseline(s, pairs=[(100, 110)] * 20)
        _seed_pairs(s, strategy_id=1, symbol_id=1, pairs=[(100, 110)] * 3,
                    base_ts=datetime.now(UTC) - timedelta(days=2))
        await s.commit()
        strat = await s.get(Strategy, 1)
        result = await dd.run_drift_detection_for_strategy(s, strat, {})
    assert isinstance(result, dd.DriftSkip)
    assert result.reason == "insufficient_trades"


async def test_run_drift_within_thresholds(session_factory):
    pairs = [(100, 110)] * 20  # all winners, ret +0.10
    async with session_factory() as s:
        s.add(Symbol(id=1, ticker="AAPL"))
        _seed_strategy(s)
        _seed_baseline(s, pairs=pairs)
        _seed_pairs(s, strategy_id=1, symbol_id=1, pairs=pairs,
                    base_ts=datetime.now(UTC) - timedelta(days=5))
        await s.commit()
        strat = await s.get(Strategy, 1)
        result = await dd.run_drift_detection_for_strategy(s, strat, {})
    assert isinstance(result, dd.DriftWithin)
    assert result.live_metrics.trade_count == 20


async def test_run_drift_breached_returns_finding(session_factory):
    # baseline all winners; live all losers → win_rate -100pp → breach.
    async with session_factory() as s:
        s.add(Symbol(id=1, ticker="AAPL"))
        _seed_strategy(s)
        _seed_baseline(s, pairs=[(100, 110)] * 20)
        _seed_pairs(s, strategy_id=1, symbol_id=1, pairs=[(100, 90)] * 20,
                    base_ts=datetime.now(UTC) - timedelta(days=5))
        await s.commit()
        strat = await s.get(Strategy, 1)
        result = await dd.run_drift_detection_for_strategy(s, strat, {})
    assert isinstance(result, dd.DriftFinding)
    assert "win_rate" in result.breached


async def test_run_drift_respects_envelope_thresholds(session_factory):
    # A custom min_trades makes 20 trips "insufficient".
    async with session_factory() as s:
        s.add(Symbol(id=1, ticker="AAPL"))
        _seed_strategy(s)
        _seed_baseline(s, pairs=[(100, 110)] * 20)
        _seed_pairs(s, strategy_id=1, symbol_id=1, pairs=[(100, 110)] * 20,
                    base_ts=datetime.now(UTC) - timedelta(days=5))
        await s.commit()
        strat = await s.get(Strategy, 1)
        result = await dd.run_drift_detection_for_strategy(
            s, strat, {"drift_thresholds": {"min_trades": 999}}
        )
    assert isinstance(result, dd.DriftSkip)
    assert result.reason == "insufficient_trades"


# ---- per-user pass + audit ----


async def test_run_drift_for_user_writes_audit_per_finding(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        s.add(
            TradingProfile(
                user_id=1, watchlist_json={}, bias_criteria_json={},
                bias_thresholds_json={}, session_preferences_json={},
                risk_preferences_json={}, agent_envelope_json={},
                created_at=NOW, updated_at=NOW,
            )
        )
        s.add(Symbol(id=1, ticker="AAPL"))
        _seed_strategy(s)
        _seed_baseline(s, pairs=[(100, 110)] * 20)
        _seed_pairs(s, strategy_id=1, symbol_id=1, pairs=[(100, 90)] * 20,
                    base_ts=datetime.now(UTC) - timedelta(days=5))
        await s.commit()

    async with session_factory() as s:
        counts = await dd.run_drift_detection_for_user(s, 1)

    assert counts["drifted"] == 1
    async with session_factory() as s:
        rows = (
            await s.execute(
                select(AuditLog).where(AuditLog.action == "STRATEGY_DRIFT_DETECTED")
            )
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].actor_type == "agent"
    assert rows[0].target_id == "1"


async def test_run_drift_for_user_no_audit_when_within(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        s.add(
            TradingProfile(
                user_id=1, watchlist_json={}, bias_criteria_json={},
                bias_thresholds_json={}, session_preferences_json={},
                risk_preferences_json={}, agent_envelope_json={},
                created_at=NOW, updated_at=NOW,
            )
        )
        s.add(Symbol(id=1, ticker="AAPL"))
        _seed_strategy(s)
        _seed_baseline(s, pairs=[(100, 110)] * 20)
        _seed_pairs(s, strategy_id=1, symbol_id=1, pairs=[(100, 110)] * 20,
                    base_ts=datetime.now(UTC) - timedelta(days=5))
        await s.commit()

    async with session_factory() as s:
        counts = await dd.run_drift_detection_for_user(s, 1)

    assert counts["drifted"] == 0
    assert counts["within"] == 1
    async with session_factory() as s:
        rows = (await s.execute(select(AuditLog))).scalars().all()
    assert rows == []
