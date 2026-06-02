"""P6 §1a — GET /api/v1/agent/budget (Decision 6 hard pre-call cap).

Drives real auth (``@pytest.mark.real_auth``) so the AGENT_API_KEY bearer path
runs. Cost-bearing audit rows are inserted directly with controlled ``ts`` and
``payload_json`` so the 24h window, tenant isolation, and fractional-cents
summation are all exercised without any real LLM call.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db.base import Base
from app.db.models.audit_log import AuditLog
from app.db.models.user import User
from app.db.session import get_engine, get_sessionmaker
from app.security.credential_store import CredentialKind, CredentialStore

BUDGET_URL = "/api/v1/agent/cost-envelope"
PROFILE_URL = "/api/v1/users/me/trading-profile"
AGENT_KEY = "agt-secret-key-123"


@pytest.fixture
async def app_factory():
    import os

    os.environ["WORKBENCH_ALPACA_STARTUP_ENABLED"] = "0"
    from app.db import models  # noqa: F401 - register models on Base.metadata

    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with get_sessionmaker()() as s:
        s.add(User(id=1, email="jay@test"))
        await s.commit()
        await CredentialStore(s).set(1, CredentialKind.AGENT_API_KEY, AGENT_KEY)

    clients: list[AsyncClient] = []

    async def _build() -> AsyncClient:
        from app.main import create_app

        ac = AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")
        clients.append(ac)
        return ac

    try:
        yield _build
    finally:
        for ac in clients:
            await ac.aclose()
        await engine.dispose()
        get_engine.cache_clear()
        get_sessionmaker.cache_clear()


def _bearer(key: str = AGENT_KEY) -> dict[str, str]:
    return {"Authorization": f"Bearer {key}"}


async def _add_cost_row(user_id: int, cost_cents: str, ts: datetime) -> None:
    async with get_sessionmaker()() as s:
        s.add(
            AuditLog(
                user_id=user_id,
                ts=ts,
                actor_type="system",
                actor_id=None,
                action="MORNING_BRIEF_GENERATED",
                target_type="morning_brief",
                target_id=None,
                payload_json=json.dumps({"llm": {"cost_cents": cost_cents}}),
                ip=None,
            )
        )
        await s.commit()


@pytest.mark.real_auth
async def test_budget_check_allowed_when_no_spend(app_factory) -> None:
    ac = await app_factory()
    r = await ac.get(BUDGET_URL, params={"estimated_cost_cents": 10}, headers=_bearer())
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "ALLOWED"
    assert body["current_spend_cents"] == 0
    assert body["envelope_cents"] == 200
    assert body["headroom_cents"] == 200


@pytest.mark.real_auth
async def test_budget_check_allowed_below_envelope(app_factory) -> None:
    ac = await app_factory()
    now = datetime.now(UTC)
    await _add_cost_row(1, "50", now - timedelta(hours=1))
    await _add_cost_row(1, "30", now - timedelta(hours=2))
    r = await ac.get(BUDGET_URL, params={"estimated_cost_cents": 10}, headers=_bearer())
    body = r.json()
    assert body["decision"] == "ALLOWED"
    assert body["current_spend_cents"] == 80


@pytest.mark.real_auth
async def test_budget_check_rejected_above_envelope(app_factory) -> None:
    ac = await app_factory()
    r = await ac.get(BUDGET_URL, params={"estimated_cost_cents": 999}, headers=_bearer())
    body = r.json()
    assert body["decision"] == "REJECTED"
    # An AGENT_BUDGET_REJECTED audit row was written.
    async with get_sessionmaker()() as s:
        rows = (
            await s.execute(
                select(AuditLog).where(AuditLog.action == "AGENT_BUDGET_REJECTED")
            )
        ).scalars().all()
    assert len(rows) == 1
    assert rows[0].user_id == 1
    assert rows[0].actor_type == "agent"


@pytest.mark.real_auth
async def test_budget_check_uses_custom_envelope_from_profile(app_factory) -> None:
    ac = await app_factory()
    # Set a larger envelope via the trading-profile API (Decision 4).
    put = await ac.put(
        PROFILE_URL,
        json={"agent_envelope": {"cost_envelope_cents": 500}},
        headers=_bearer(),
    )
    assert put.status_code == 200
    assert put.json()["agent_envelope"] == {"cost_envelope_cents": 500}
    # 300 would be REJECTED at the default 200 envelope; with 500 it's ALLOWED.
    r = await ac.get(BUDGET_URL, params={"estimated_cost_cents": 300}, headers=_bearer())
    body = r.json()
    assert body["envelope_cents"] == 500
    assert body["decision"] == "ALLOWED"


@pytest.mark.real_auth
async def test_budget_check_24h_window_correct(app_factory) -> None:
    ac = await app_factory()
    now = datetime.now(UTC)
    await _add_cost_row(1, "150", now - timedelta(hours=23))  # counted
    await _add_cost_row(1, "150", now - timedelta(hours=25))  # excluded
    r = await ac.get(BUDGET_URL, params={"estimated_cost_cents": 10}, headers=_bearer())
    body = r.json()
    assert body["current_spend_cents"] == 150


@pytest.mark.real_auth
async def test_budget_check_other_user_data_isolated(app_factory) -> None:
    ac = await app_factory()
    async with get_sessionmaker()() as s:
        s.add(User(id=2, email="other@test"))
        await s.commit()
    await _add_cost_row(2, "150", datetime.now(UTC) - timedelta(hours=1))
    r = await ac.get(BUDGET_URL, params={"estimated_cost_cents": 10}, headers=_bearer())
    body = r.json()
    # User 2's spend must not count toward user 1.
    assert body["current_spend_cents"] == 0


@pytest.mark.real_auth
async def test_budget_check_fractional_cents_summed(app_factory) -> None:
    ac = await app_factory()
    now = datetime.now(UTC)
    # Sub-cent rows must accumulate (no per-row truncation); 0.42 + 0.55 = 0.97
    # → rounded up to 1 whole cent (correction #3).
    await _add_cost_row(1, "0.42", now - timedelta(hours=1))
    await _add_cost_row(1, "0.55", now - timedelta(hours=1))
    r = await ac.get(BUDGET_URL, params={"estimated_cost_cents": 1}, headers=_bearer())
    body = r.json()
    assert body["current_spend_cents"] == 1


@pytest.mark.real_auth
async def test_budget_check_requires_bearer_auth(app_factory) -> None:
    ac = await app_factory()
    r = await ac.get(BUDGET_URL, params={"estimated_cost_cents": 10})
    assert r.status_code == 401


@pytest.mark.real_auth
async def test_budget_check_negative_estimated_rejected_400(app_factory) -> None:
    ac = await app_factory()
    r = await ac.get(BUDGET_URL, params={"estimated_cost_cents": -1}, headers=_bearer())
    assert r.status_code == 400
