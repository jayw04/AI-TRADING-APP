"""P7 §8 — GET /strategies/author/budget (daily headroom)."""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from app.db.models.audit_log import AuditLog
from app.db.models.user import User
from app.db.session import get_sessionmaker

BASE = "/api/v1"


@pytest.fixture(autouse=True)
async def _seed(client):
    async with get_sessionmaker()() as s:
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        await s.commit()
    return client


async def test_budget_zero_spend(client):
    r = await client.get(f"{BASE}/strategies/author/budget")
    assert r.status_code == 200
    body = r.json()
    assert body["daily_cap_usd"] == 2.0  # AGENT_DAILY_BUDGET_USD default
    assert body["spent_today_usd"] == 0.0
    assert body["remaining_usd"] == 2.0


async def test_budget_reflects_authoring_spend(client):
    async with get_sessionmaker()() as s:
        s.add(AuditLog(
            user_id=1, ts=datetime.now(UTC), actor_type="user", actor_id="1",
            action="STRATEGY_GENERATED", target_type="strategy_authoring", target_id=None,
            payload_json=json.dumps({"cost_usd": 0.5}),
        ))
        await s.commit()
    r = await client.get(f"{BASE}/strategies/author/budget")
    body = r.json()
    assert body["spent_today_usd"] == 0.5
    assert body["remaining_usd"] == 1.5


async def test_budget_remaining_floored_at_zero(client):
    async with get_sessionmaker()() as s:
        s.add(AuditLog(
            user_id=1, ts=datetime.now(UTC), actor_type="user", actor_id="1",
            action="STRATEGY_GENERATED", target_type="strategy_authoring", target_id=None,
            payload_json=json.dumps({"cost_usd": 5.0}),  # over the $2 cap
        ))
        await s.commit()
    r = await client.get(f"{BASE}/strategies/author/budget")
    assert r.json()["remaining_usd"] == 0.0
