"""P6b §4 — eval-harness endpoints: start-eval / eval-harness (GET) / stop."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.db.enums import StrategyStatus
from app.db.models.strategy import Strategy
from app.db.models.user import User
from app.db.session import get_sessionmaker

BASE = "/api/v1"


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture(autouse=True)
async def _seed(client):
    async with get_sessionmaker()() as s:
        now = _now()
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        s.add(User(id=2, email="other@test"))
        s.add(Strategy(
            id=1, user_id=1, name="S1", code_path="strat.py", params_json={"rsi": 30},
            symbols_json=["AAPL"], status=StrategyStatus.LIVE,
            created_at=now, updated_at=now,
        ))
        await s.commit()
    return client


async def _set_status(status):
    async with get_sessionmaker()() as s:
        strat = await s.get(Strategy, 1)
        strat.status = status
        await s.commit()


async def test_start_eval_returns_active(client):
    r = await client.post(f"{BASE}/strategies/1/start-eval")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "active"
    assert body["mode_a_strategy_id"] != body["mode_b_strategy_id"]


async def test_start_eval_non_live_409(client):
    await _set_status(StrategyStatus.PAPER)
    r = await client.post(f"{BASE}/strategies/1/start-eval")
    assert r.status_code == 409
    assert r.json()["detail"] == "parent_not_live"


async def test_start_eval_twice_409(client):
    await client.post(f"{BASE}/strategies/1/start-eval")
    r = await client.post(f"{BASE}/strategies/1/start-eval")
    assert r.status_code == 409
    assert r.json()["detail"] == "eval_harness_already_active"


async def test_start_eval_unknown_strategy_404(client):
    r = await client.post(f"{BASE}/strategies/999/start-eval")
    assert r.status_code == 404


async def test_get_eval_harness_no_active(client):
    r = await client.get(f"{BASE}/strategies/1/eval-harness")
    assert r.status_code == 200
    assert r.json()["status"] == "no_active_harness"


async def test_get_eval_harness_returns_metrics_and_eligibility(client):
    await client.post(f"{BASE}/strategies/1/start-eval")
    r = await client.get(f"{BASE}/strategies/1/eval-harness")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "active"
    assert "comparison" in body
    assert "eligibility" in body
    assert body["eligibility"]["eligible"] is False  # fresh harness, no trades


async def test_get_eval_harness_other_user_404(client):
    async with get_sessionmaker()() as s:
        now = _now()
        s.add(Strategy(
            id=9, user_id=2, name="X", code_path="s.py", params_json={},
            symbols_json=[], status=StrategyStatus.LIVE, created_at=now, updated_at=now,
        ))
        await s.commit()
    r = await client.get(f"{BASE}/strategies/9/eval-harness")
    assert r.status_code == 404


async def test_stop_eval_terminates(client):
    start = await client.post(f"{BASE}/strategies/1/start-eval")
    hid = start.json()["harness_id"]
    r = await client.post(f"{BASE}/eval-harness/{hid}/stop")
    assert r.status_code == 200
    assert r.json()["status"] == "terminated"
    # after stop, GET shows no active harness
    g = await client.get(f"{BASE}/strategies/1/eval-harness")
    assert g.json()["status"] == "no_active_harness"


async def test_stop_eval_unknown_404(client):
    r = await client.post(f"{BASE}/eval-harness/999/stop")
    assert r.status_code == 404
