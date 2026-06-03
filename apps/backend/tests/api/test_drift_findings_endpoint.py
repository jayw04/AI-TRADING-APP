"""P6b §1b-drift — GET /api/v1/drift-findings (user-level)."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from app.db.models.audit_log import AuditLog
from app.db.models.user import User
from app.db.session import get_sessionmaker

BASE = "/api/v1"
_seq = 0


@pytest.fixture(autouse=True)
async def _seed(client):
    async with get_sessionmaker()() as s:
        s.add(User(id=1, email="jay@test"))
        s.add(User(id=2, email="other@test"))
        await s.commit()
    return client


async def _finding(*, target_id="1", user_id=1, breached=None):
    global _seq
    _seq += 1
    async with get_sessionmaker()() as s:
        ts = datetime.now(UTC) - timedelta(minutes=_seq)
        s.add(AuditLog(
            user_id=user_id, ts=ts, actor_type="agent", actor_id="drift_detector",
            action="STRATEGY_DRIFT_DETECTED", target_type="strategy",
            target_id=target_id,
            payload_json=json.dumps({
                "strategy_id": int(target_id),
                "breached": breached or ["win_rate"],
                "win_rate": {"live": 0.4, "baseline": 0.6, "delta_pp": -20.0},
                "avg_return_per_trade": {"live": 0.0, "baseline": 0.0, "delta_pct": 0.0},
                "trade_count": 25,
                "detected_at": ts.isoformat(),
            }),
        ))
        await s.commit()


async def _ids(client, extra=""):
    r = await client.get(f"{BASE}/drift-findings{extra}")
    assert r.status_code == 200
    return [it["strategy_id"] for it in r.json()["items"]]


async def test_list_returns_user_findings_newest_first(client):
    await _finding(target_id="1")
    await _finding(target_id="2")
    ids = await _ids(client)
    assert set(ids) == {1, 2}
    # newest-first: the second-seeded (more recent ts) appears first
    assert ids[0] == 2


async def test_list_filters_by_strategy_id(client):
    await _finding(target_id="1")
    await _finding(target_id="2")
    assert await _ids(client, "?strategy_id=1") == [1]


async def test_list_excludes_other_users_findings(client):
    await _finding(target_id="1", user_id=1)
    await _finding(target_id="5", user_id=2)
    assert await _ids(client) == [1]


async def test_list_empty_returns_empty(client):
    r = await client.get(f"{BASE}/drift-findings")
    assert r.json()["items"] == []


async def test_list_respects_limit(client):
    for _ in range(5):
        await _finding(target_id="1")
    r = await client.get(f"{BASE}/drift-findings?limit=2")
    assert len(r.json()["items"]) == 2


async def test_list_parses_payload_fields(client):
    await _finding(target_id="3", breached=["win_rate", "avg_return_per_trade"])
    r = await client.get(f"{BASE}/drift-findings?strategy_id=3")
    item = r.json()["items"][0]
    assert item["breached"] == ["win_rate", "avg_return_per_trade"]
    assert item["win_rate"]["delta_pp"] == -20.0
    assert item["trade_count"] == 25
