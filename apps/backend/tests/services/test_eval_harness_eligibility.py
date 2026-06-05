"""P6b §4 — opt-in eligibility double-floor (≥50 Mode-B trades AND ≥30 days AND
harness still ACTIVE).
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
from app.db.models.eval_harness import (
    HARNESS_ACTIVE,
    HARNESS_TERMINATED,
    EvalHarness,
)
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.strategy import Strategy
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.services.eval_harness.eligibility import check_eligibility

NOW = datetime.now(UTC)
MODE_B_ID = 11
_OID = 0


def _b_round_trips(s, n: int, *, base_at: datetime) -> None:
    """n long round-trips attributed to Mode B's source_id."""
    global _OID
    for i in range(n):
        when = base_at + timedelta(minutes=i)
        for side, price, off in ((OrderSide.BUY, 100, 0), (OrderSide.SELL, 101, 1)):
            _OID += 1
            s.add(Order(
                id=_OID, user_id=1, account_id=1, symbol_id=1, side=side,
                qty=Decimal("10"), type=OrderType.MARKET, status=OrderStatus.FILLED,
                source_type=OrderSourceType.STRATEGY, source_id=str(MODE_B_ID),
                created_at=when, updated_at=when,
            ))
            s.add(Fill(
                order_id=_OID, qty=Decimal("10"), price=Decimal(str(price)),
                commission=Decimal("0"), filled_at=when + timedelta(seconds=off),
            ))


async def _seed(
    session_factory, *, started_days_ago: int, b_trades: int,
    state: str = HARNESS_ACTIVE,
) -> int:
    start = NOW - timedelta(days=started_days_ago)
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        s.add(Symbol(id=1, ticker="AAPL"))
        s.add(Strategy(
            id=MODE_B_ID, user_id=1, name="mode_b", code_path="s.py",
            params_json={}, symbols_json=["AAPL"], status=StrategyStatus.IDLE,
            harness_role="mode_b", parent_strategy_id=1,
            created_at=start, updated_at=start,
        ))
        _b_round_trips(s, b_trades, base_at=start + timedelta(hours=1))
        h = EvalHarness(
            id=1, user_id=1, parent_strategy_id=1,
            mode_a_strategy_id=99, mode_b_strategy_id=MODE_B_ID,
            state=state, started_at=start,
        )
        s.add(h)
        await s.commit()
        return h.id


async def test_eligible_when_both_floors_met(session_factory):
    hid = await _seed(session_factory, started_days_ago=40, b_trades=50)
    async with session_factory() as s:
        v = await check_eligibility(s, await s.get(EvalHarness, hid))
    assert v.eligible is True
    assert v.b_trade_count == 50
    assert v.window_days >= 30
    assert v.reasons == []


async def test_ineligible_insufficient_trades(session_factory):
    hid = await _seed(session_factory, started_days_ago=40, b_trades=10)
    async with session_factory() as s:
        v = await check_eligibility(s, await s.get(EvalHarness, hid))
    assert v.eligible is False
    assert "insufficient_trades" in v.reasons


async def test_ineligible_insufficient_window(session_factory):
    hid = await _seed(session_factory, started_days_ago=5, b_trades=50)
    async with session_factory() as s:
        v = await check_eligibility(s, await s.get(EvalHarness, hid))
    assert v.eligible is False
    assert "insufficient_window" in v.reasons


async def test_ineligible_when_not_active(session_factory):
    hid = await _seed(
        session_factory, started_days_ago=40, b_trades=50, state=HARNESS_TERMINATED
    )
    async with session_factory() as s:
        v = await check_eligibility(s, await s.get(EvalHarness, hid))
    assert v.eligible is False
    assert v.harness_active is False
    assert "harness_not_active" in v.reasons
