"""P6b §4 — the six ADR-0006-v2 comparison metrics (3 equity deltas + 3 decision
metrics), incl. the derived-outcome FIFO attribution used for B's skip scoring.
"""
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
from app.db.models.eval_harness import HARNESS_ACTIVE, EvalHarness, EvalHarnessDecision
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.strategy import Strategy
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.services.eval_harness.metrics import (
    _order_realized_pnl,
    compute_eval_harness_comparison,
)

NOW = datetime.now(UTC)
START = NOW - timedelta(days=10)
TRADE_AT = NOW - timedelta(days=5)

MODE_A_ID, MODE_B_ID = 10, 11


def _rt(s, *, strategy_id, oid_buy, oid_sell, entry, exit_, when, qty=10):
    """One long round-trip (buy then sell) attributed to a strategy's source_id.
    The BUY is the entry order (`_order_realized_pnl` attributes the trip to it)."""
    for oid, side, price, off in (
        (oid_buy, OrderSide.BUY, entry, 0),
        (oid_sell, OrderSide.SELL, exit_, 1),
    ):
        s.add(Order(
            id=oid, user_id=1, account_id=1, symbol_id=1, side=side,
            qty=Decimal(str(qty)), type=OrderType.MARKET, status=OrderStatus.FILLED,
            source_type=OrderSourceType.STRATEGY, source_id=str(strategy_id),
            created_at=when, updated_at=when,
        ))
        s.add(Fill(
            order_id=oid, qty=Decimal(str(qty)), price=Decimal(str(price)),
            commission=Decimal("0"), filled_at=when + timedelta(minutes=off),
        ))


async def _seed(session_factory) -> int:
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        s.add(Symbol(id=1, ticker="AAPL"))
        for sid, role, status in (
            (MODE_A_ID, "mode_a", StrategyStatus.PAPER_VARIANT),
            (MODE_B_ID, "mode_b", StrategyStatus.IDLE),
        ):
            s.add(Strategy(
                id=sid, user_id=1, name=role, code_path="s.py", params_json={},
                symbols_json=["AAPL"], status=status, harness_role=role,
                parent_strategy_id=1, created_at=START, updated_at=START,
            ))
        # A: one winner (entry order 1), one loser (entry order 3).
        _rt(s, strategy_id=MODE_A_ID, oid_buy=1, oid_sell=2,
            entry=100, exit_=110, when=TRADE_AT)
        _rt(s, strategy_id=MODE_A_ID, oid_buy=3, oid_sell=4,
            entry=100, exit_=90, when=TRADE_AT + timedelta(hours=1))
        # B: one winner.
        _rt(s, strategy_id=MODE_B_ID, oid_buy=5, oid_sell=6,
            entry=100, exit_=120, when=TRADE_AT + timedelta(hours=2))
        h = EvalHarness(
            id=1, user_id=1, parent_strategy_id=1,
            mode_a_strategy_id=MODE_A_ID, mode_b_strategy_id=MODE_B_ID,
            state=HARNESS_ACTIVE, started_at=START,
        )
        s.add(h)
        # Decisions: 1 agreement (act), 2 disagreements (B skipped).
        s.add(EvalHarnessDecision(
            harness_id=1, signal_uuid="d1", signal_payload_json={},
            mode_a_decision="act", mode_b_decision="act",
            mode_a_order_id=1, mode_b_order_id=5,
            llm_cost_cents=Decimal("1"), recorded_at=TRADE_AT,
        ))
        s.add(EvalHarnessDecision(  # B skipped A's loser → B was right
            harness_id=1, signal_uuid="d2", signal_payload_json={},
            mode_a_decision="act", mode_b_decision="skip",
            mode_a_order_id=3, mode_b_order_id=None,
            llm_cost_cents=Decimal("1"), recorded_at=TRADE_AT,
        ))
        s.add(EvalHarnessDecision(  # B skipped A's winner → B was wrong
            harness_id=1, signal_uuid="d3", signal_payload_json={},
            mode_a_decision="act", mode_b_decision="skip",
            mode_a_order_id=1, mode_b_order_id=None,
            llm_cost_cents=Decimal("1"), recorded_at=TRADE_AT,
        ))
        await s.commit()
        return h.id


async def test_order_realized_pnl_attributes_to_entry(session_factory):
    await _seed(session_factory)
    async with session_factory() as s:
        pnl = await _order_realized_pnl(s, MODE_A_ID, START)
    assert pnl[1] == 100.0   # winner: (110-100)*10
    assert pnl[3] == -100.0  # loser: (90-100)*10


async def test_comparison_equity_and_decision_metrics(session_factory):
    hid = await _seed(session_factory)
    async with session_factory() as s:
        h = await s.get(EvalHarness, hid)
        c = await compute_eval_harness_comparison(s, h)
    # Equity side.
    assert c.mode_a.trade_count == 2
    assert c.mode_b.trade_count == 1
    assert c.mode_a.win_rate == 0.5
    assert c.mode_b.win_rate == 1.0
    assert c.win_rate_delta == 0.5  # B − A
    # Decision side.
    assert c.total_decisions == 3
    assert c.decision_agreement_rate == 1 / 3   # only d1 agrees (act==act)
    assert c.disagreement_asymmetry == 0.0       # 1 right, 1 wrong
    assert c.worst_single_divergence == 100.0    # |±100| among B's skips


async def test_comparison_to_dict_shape(session_factory):
    from app.services.eval_harness.metrics import comparison_to_dict

    hid = await _seed(session_factory)
    async with session_factory() as s:
        h = await s.get(EvalHarness, hid)
        d = comparison_to_dict(await compute_eval_harness_comparison(s, h))
    assert set(d) == {
        "window_start", "window_end", "mode_a", "mode_b", "deltas",
        "decision_metrics",
    }
    assert set(d["deltas"]) == {
        "win_rate_delta", "sharpe_delta", "max_drawdown_delta"
    }
    assert set(d["decision_metrics"]) == {
        "total_decisions", "decision_agreement_rate",
        "disagreement_asymmetry", "worst_single_divergence",
    }
