"""P6 §1b — strategy-proposals API.

Uses the conftest autouse auth override (every request is user id=1). The agent
HTTP call is mocked by monkeypatching ``proposals._invoke_agent`` — the fake
simulates the agent's DRAFT→REVIEWING PATCH via a separate session (the real
flow's data path) so ``propose`` exercises create → invoke → refresh → return.
"""
from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import select

from app.api.v1 import proposals as proposals_mod
from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.db.models.user import User
from app.db.session import get_sessionmaker

BASE = "/api/v1"


@pytest.fixture(autouse=True)
async def _seed(client):
    async with get_sessionmaker()() as s:
        now = datetime.now(UTC)
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        s.add(User(id=2, email="other@test"))
        s.add(
            Strategy(
                id=1, user_id=1, name="S1",
                params_json={"rsi_min": 50}, symbols_json=["AAPL"],
                created_at=now, updated_at=now,
            )
        )
        s.add(
            Strategy(
                id=2, user_id=2, name="OtherS",
                params_json={}, symbols_json=[],
                created_at=now, updated_at=now,
            )
        )
        await s.commit()
    return client


async def _mk_proposal(
    *, strategy_id: int = 1, user_id: int = 1,
    state: ProposalState = ProposalState.DRAFT, payload: dict | None = None,
) -> int:
    async with get_sessionmaker()() as s:
        now = datetime.now(UTC)
        row = StrategyProposal(
            strategy_id=strategy_id, user_id=user_id, state=state,
            proposal_payload_json=payload or {}, evidence_bundle_json={},
            evaluation_results_json={},
            generated_at=now, transitioned_at=now, created_at=now, updated_at=now,
        )
        s.add(row)
        await s.commit()
        return row.id


def _fake_agent_success(monkeypatch):
    async def fake(agent_url: str, proposal_id: int) -> dict:
        async with get_sessionmaker()() as s:
            row = await s.get(StrategyProposal, proposal_id)
            row.state = ProposalState.REVIEWING
            row.proposal_payload_json = {
                "proposal_type": "parameter_adjustment",
                "confidence": "MEDIUM",
                "summary": "Tune RSI",
                "rationale": "evidence",
                "changes": [{"param": "rsi_min", "from": 50, "to": 55, "reason": "r"}],
            }
            row.evidence_bundle_json = {"recent_orders": []}
            row.transitioned_at = datetime.now(UTC)
            await s.commit()
        return {"proposal_id": proposal_id, "state": "REVIEWING", "error": None}

    monkeypatch.setattr(proposals_mod, "_invoke_agent", fake)


# ----- propose -----


async def test_propose_creates_draft_then_agent_completes_to_reviewing(client, monkeypatch):
    _fake_agent_success(monkeypatch)
    r = await client.post(f"{BASE}/strategies/1/propose", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "REVIEWING"
    assert body["proposal_payload"]["confidence"] == "MEDIUM"


async def test_propose_agent_failure_cleans_up_draft(client, monkeypatch):
    async def fake(agent_url, pid):
        return {"proposal_id": pid, "state": "DRAFT", "error": "LLM call failed"}

    monkeypatch.setattr(proposals_mod, "_invoke_agent", fake)
    r = await client.post(f"{BASE}/strategies/1/propose", json={})
    assert r.status_code == 502
    async with get_sessionmaker()() as s:
        rows = (await s.execute(select(StrategyProposal))).scalars().all()
    assert rows == []


async def test_propose_agent_unreachable_cleans_up_draft(client, monkeypatch):
    async def fake(agent_url, pid):
        raise httpx.ConnectError("agent down")

    monkeypatch.setattr(proposals_mod, "_invoke_agent", fake)
    r = await client.post(f"{BASE}/strategies/1/propose", json={})
    assert r.status_code == 502
    async with get_sessionmaker()() as s:
        rows = (await s.execute(select(StrategyProposal))).scalars().all()
    assert rows == []


async def test_propose_other_users_strategy_404(client, monkeypatch):
    _fake_agent_success(monkeypatch)
    r = await client.post(f"{BASE}/strategies/2/propose", json={})
    assert r.status_code == 404


async def test_propose_minute_collision_returns_409(client, monkeypatch):
    _fake_agent_success(monkeypatch)
    r1 = await client.post(f"{BASE}/strategies/1/propose", json={})
    assert r1.status_code == 200
    r2 = await client.post(f"{BASE}/strategies/1/propose", json={})
    assert r2.status_code == 409


# ----- patch transitions -----


async def test_patch_draft_to_reviewing_with_payload(client):
    pid = await _mk_proposal(state=ProposalState.DRAFT)
    r = await client.patch(
        f"{BASE}/proposals/{pid}",
        json={
            "target_state": "REVIEWING",
            "proposal_payload": {"confidence": "HIGH", "changes": []},
            "evidence_bundle": {"k": "v"},
            "llm_usage": {"model": "claude-sonnet-4-6", "cost_cents": "1.5"},
        },
    )
    assert r.status_code == 200
    assert r.json()["state"] == "REVIEWING"
    from app.db.models.audit_log import AuditLog
    async with get_sessionmaker()() as s:
        row = (
            await s.execute(
                select(AuditLog).where(AuditLog.action == "STRATEGY_PROPOSAL_TRANSITIONED")
            )
        ).scalars().all()[-1]
    assert row.actor_type == "agent"


async def test_patch_draft_to_reviewing_missing_payload_400(client):
    pid = await _mk_proposal(state=ProposalState.DRAFT)
    r = await client.patch(f"{BASE}/proposals/{pid}", json={"target_state": "REVIEWING"})
    assert r.status_code == 400


async def test_patch_reviewing_to_accepted(client):
    pid = await _mk_proposal(state=ProposalState.REVIEWING)
    r = await client.patch(
        f"{BASE}/proposals/{pid}",
        json={"target_state": "ACCEPTED", "review_notes": "ok"},
    )
    assert r.status_code == 200
    assert r.json()["state"] == "ACCEPTED"


async def test_patch_reviewing_to_rejected_with_reason(client):
    pid = await _mk_proposal(state=ProposalState.REVIEWING)
    r = await client.patch(
        f"{BASE}/proposals/{pid}",
        json={"target_state": "REJECTED", "rejection_reason": "conflicts"},
    )
    assert r.status_code == 200
    assert r.json()["state"] == "REJECTED"


async def test_patch_invalid_transition_400(client):
    pid = await _mk_proposal(state=ProposalState.DRAFT)
    r = await client.patch(f"{BASE}/proposals/{pid}", json={"target_state": "ACCEPTED"})
    assert r.status_code == 400


# ----- list / get -----


async def test_list_filters_by_strategy_and_only_current_user(client):
    await _mk_proposal(strategy_id=1, user_id=1, state=ProposalState.REVIEWING)
    await _mk_proposal(strategy_id=99, user_id=2, state=ProposalState.REVIEWING)
    r = await client.get(f"{BASE}/proposals?strategy_id=1")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["strategy_id"] == 1


async def test_list_invalid_state_400(client):
    r = await client.get(f"{BASE}/proposals?state=BOGUS")
    assert r.status_code == 400


# ----- apply -----


async def test_apply_only_works_on_accepted(client):
    pid = await _mk_proposal(state=ProposalState.REVIEWING)
    r = await client.post(f"{BASE}/proposals/{pid}/apply")
    assert r.status_code == 400


async def test_apply_merges_params_json(client):
    pid = await _mk_proposal(
        state=ProposalState.ACCEPTED,
        payload={"changes": [{"param": "rsi_min", "from": 50, "to": 55}]},
    )
    r = await client.post(f"{BASE}/proposals/{pid}/apply")
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "APPLIED"
    assert r.json()["applied_changes"] == [{"param": "rsi_min", "to": 55}]
    async with get_sessionmaker()() as s:
        strat = await s.get(Strategy, 1)
        assert strat.params_json["rsi_min"] == 55


async def test_apply_requires_idle_strategy_409(client):
    from app.db.enums import StrategyStatus

    async with get_sessionmaker()() as s:
        strat = await s.get(Strategy, 1)
        strat.status = StrategyStatus.PAPER
        await s.commit()
    pid = await _mk_proposal(
        state=ProposalState.ACCEPTED,
        payload={"changes": [{"param": "rsi_min", "to": 55}]},
    )
    r = await client.post(f"{BASE}/proposals/{pid}/apply")
    assert r.status_code == 409
