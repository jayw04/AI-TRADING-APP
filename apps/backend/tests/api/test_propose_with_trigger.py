"""P6 §2a — the propose endpoint's optional ``trigger`` field.

cadence-driven proposes attribute the DRAFT audit row to actor_type=AGENT /
actor_id=cron_scheduler with payload.trigger='cadence'; user-driven (empty body)
stay actor_type=USER / trigger='manual'. The agent HTTP call is mocked.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.api.v1 import proposals as proposals_mod
from app.db.models.audit_log import AuditLog
from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.db.models.user import User
from app.db.session import get_sessionmaker

BASE = "/api/v1"


@pytest.fixture(autouse=True)
async def _seed(client, monkeypatch):
    async with get_sessionmaker()() as s:
        now = datetime.now(UTC)
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        s.add(
            Strategy(
                id=1, user_id=1, name="S1", params_json={}, symbols_json=[],
                created_at=now, updated_at=now,
            )
        )
        await s.commit()

    async def fake(agent_url, proposal_id):
        async with get_sessionmaker()() as s:
            row = await s.get(StrategyProposal, proposal_id)
            row.state = ProposalState.REVIEWING
            row.proposal_payload_json = {"confidence": "MEDIUM", "summary": "x", "changes": []}
            row.transitioned_at = datetime.now(UTC)
            await s.commit()
        return {"proposal_id": proposal_id, "state": "REVIEWING", "error": None}

    monkeypatch.setattr(proposals_mod, "_invoke_agent", fake)
    return client


async def _draft_audit_row():
    async with get_sessionmaker()() as s:
        rows = (
            await s.execute(
                select(AuditLog).where(AuditLog.action == "STRATEGY_PROPOSAL_TRANSITIONED")
            )
        ).scalars().all()
    # The DRAFT-creation row is the one with payload.to == "DRAFT".
    for r in rows:
        if json.loads(r.payload_json).get("to") == "DRAFT":
            return r
    return None


async def test_propose_trigger_cadence_attributes_to_agent(client):
    r = await client.post(f"{BASE}/strategies/1/propose", json={"trigger": "cadence"})
    assert r.status_code == 200
    row = await _draft_audit_row()
    assert row.actor_type == "agent"
    assert row.actor_id == "cron_scheduler"
    assert json.loads(row.payload_json)["trigger"] == "cadence"


async def test_propose_trigger_manual_attributes_to_user(client):
    r = await client.post(f"{BASE}/strategies/1/propose", json={})
    assert r.status_code == 200
    row = await _draft_audit_row()
    assert row.actor_type == "user"
    assert json.loads(row.payload_json)["trigger"] == "manual"


async def test_propose_unknown_trigger_treated_as_manual(client):
    r = await client.post(f"{BASE}/strategies/1/propose", json={"trigger": "foo"})
    assert r.status_code == 200
    row = await _draft_audit_row()
    # Any non-"cadence" trigger is attributed to the user (treated as manual).
    assert row.actor_type == "user"
    assert json.loads(row.payload_json)["trigger"] == "foo"
