"""P6b §1b-drift — POST /api/v1/strategies/{id}/drift-check."""
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
from app.db.models.user import User
from app.db.session import get_sessionmaker

BASE = "/api/v1"
_oid = 0


def _leg(s, *, sid, symbol_id, side, qty, price, at):
    global _oid
    _oid += 1
    s.add(Order(
        id=_oid, user_id=1, account_id=1, symbol_id=symbol_id, side=side,
        qty=Decimal(str(qty)), type=OrderType.MARKET, status=OrderStatus.FILLED,
        source_type=OrderSourceType.STRATEGY, source_id=str(sid),
        created_at=at, updated_at=at,
    ))
    s.add(Fill(order_id=_oid, qty=Decimal(str(qty)), price=Decimal(str(price)),
               commission=Decimal("0"), filled_at=at))


def _pairs(s, *, sid, symbol_id, pairs, base_ts):
    for i, (en, ex) in enumerate(pairs):
        _leg(s, sid=sid, symbol_id=symbol_id, side=OrderSide.BUY, qty=10, price=en,
             at=base_ts + timedelta(minutes=2 * i))
        _leg(s, sid=sid, symbol_id=symbol_id, side=OrderSide.SELL, qty=10, price=ex,
             at=base_ts + timedelta(minutes=2 * i + 1))


def _bt(pairs):
    return [{"pnl": (ex - en) * 10, "entry_price": en, "qty": 10.0} for en, ex in pairs]


async def _seed(*, status=StrategyStatus.PAPER, baseline=None, live=None):
    async with get_sessionmaker()() as s:
        now = datetime.now(UTC)
        s.add(User(id=1, email="jay@test"))
        s.add(Symbol(id=1, ticker="AAPL"))
        s.add(Strategy(
            id=1, user_id=1, name="S1", params_json={"rsi": 30},
            symbols_json=["AAPL"], status=status, created_at=now, updated_at=now,
        ))
        if baseline is not None:
            s.add(BacktestResult(
                strategy_id=1, label="b", params_json={"rsi": 30}, metrics_json={},
                equity_curve_json=[], trades_json=_bt(baseline),
                range_start=now - timedelta(days=90), range_end=now, created_at=now,
            ))
        if live is not None:
            _pairs(s, sid=1, symbol_id=1, pairs=live, base_ts=now - timedelta(days=5))
        await s.commit()


async def _audit_rows():
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                select(AuditLog).where(AuditLog.action == "STRATEGY_DRIFT_DETECTED")
            )
        ).scalars().all()


async def test_drift_check_finding_writes_audit_and_returns_drift(client):
    await _seed(baseline=[(100, 110)] * 20, live=[(100, 90)] * 20)
    r = await client.post(f"{BASE}/strategies/1/drift-check")
    assert r.status_code == 200
    assert r.json()["kind"] == "drift_detected"
    assert "win_rate" in r.json()["breached"]
    assert len(await _audit_rows()) == 1


async def test_drift_check_within_returns_within_no_audit(client):
    await _seed(baseline=[(100, 110)] * 20, live=[(100, 110)] * 20)
    r = await client.post(f"{BASE}/strategies/1/drift-check")
    assert r.json()["kind"] == "within_thresholds"
    assert await _audit_rows() == []


async def test_drift_check_skip_no_baseline(client):
    await _seed(baseline=None, live=[(100, 110)] * 20)
    r = await client.post(f"{BASE}/strategies/1/drift-check")
    assert r.json()["kind"] == "skip"
    assert r.json()["reason"] == "no_baseline"


async def test_drift_check_idle_strategy_skip_not_active(client):
    await _seed(status=StrategyStatus.IDLE, baseline=[(100, 110)] * 20, live=[(100, 90)] * 20)
    r = await client.post(f"{BASE}/strategies/1/drift-check")
    assert r.json()["kind"] == "skip"
    assert r.json()["reason"] == "not_active"


async def test_drift_check_other_user_404(client):
    async with get_sessionmaker()() as s:
        now = datetime.now(UTC)
        s.add(User(id=2, email="other@test"))
        s.add(Strategy(
            id=9, user_id=2, name="X", params_json={}, symbols_json=[],
            status=StrategyStatus.PAPER, created_at=now, updated_at=now,
        ))
        await s.commit()
    r = await client.post(f"{BASE}/strategies/9/drift-check")
    assert r.status_code == 404
