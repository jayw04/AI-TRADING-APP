"""P6b §1b-drift — GET /api/v1/strategies/{id}/drift-status."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.db.enums import StrategyStatus
from app.db.models.audit_log import AuditLog
from app.db.models.strategy import Strategy
from app.db.models.user import User
from app.db.session import get_sessionmaker

BASE = "/api/v1"


@pytest.fixture(autouse=True)
async def _seed(client):
    async with get_sessionmaker()() as s:
        now = datetime.now(UTC)
        s.add(User(id=1, email="jay@test"))
        s.add(User(id=2, email="other@test"))
        s.add(Strategy(id=1, user_id=1, name="S1", params_json={}, symbols_json=[],
                       status=StrategyStatus.PAPER, created_at=now, updated_at=now))
        s.add(Strategy(id=9, user_id=2, name="X", params_json={}, symbols_json=[],
                       status=StrategyStatus.PAPER, created_at=now, updated_at=now))
        await s.commit()
    return client


async def _audit(*, target_id="1", days_ago=1, payload=None, user_id=1):
    async with get_sessionmaker()() as s:
        ts = datetime.now(UTC) - timedelta(days=days_ago)
        s.add(AuditLog(
            user_id=user_id, ts=ts, actor_type="agent", actor_id="drift_detector",
            action="STRATEGY_DRIFT_DETECTED", target_type="strategy",
            target_id=target_id,
            payload_json=json.dumps(
                payload or {"strategy_id": int(target_id), "breached": ["win_rate"]}
            ),
        ))
        await s.commit()


async def test_drift_status_returns_latest_within_lookback(client):
    await _audit(days_ago=5, payload={"strategy_id": 1, "breached": ["win_rate"]})
    r = await client.get(f"{BASE}/strategies/1/drift-status?lookback_days=7")
    assert r.status_code == 200
    b = r.json()
    assert b["status"] == "drift_detected"
    assert b["payload"]["breached"] == ["win_rate"]


async def test_drift_status_no_recent_when_none(client):
    r = await client.get(f"{BASE}/strategies/1/drift-status?lookback_days=7")
    assert r.json()["status"] == "no_recent_drift"


async def test_drift_status_excludes_outside_lookback(client):
    await _audit(days_ago=30)
    r = await client.get(f"{BASE}/strategies/1/drift-status?lookback_days=7")
    assert r.json()["status"] == "no_recent_drift"


async def test_drift_status_returns_newest(client):
    await _audit(days_ago=5, payload={"strategy_id": 1, "breached": ["win_rate"]})
    await _audit(days_ago=1, payload={"strategy_id": 1, "breached": ["avg_return_per_trade"]})
    r = await client.get(f"{BASE}/strategies/1/drift-status")
    assert r.json()["payload"]["breached"] == ["avg_return_per_trade"]


async def test_drift_status_other_user_404(client):
    r = await client.get(f"{BASE}/strategies/9/drift-status")
    assert r.status_code == 404
