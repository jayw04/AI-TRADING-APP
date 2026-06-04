"""P6b §3b-promote — promote / reject-promotion endpoints + lockout + additive fields."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db.enums import StrategyStatus
from app.db.models.audit_log import AuditLog
from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.db.models.user import User
from app.db.session import get_sessionmaker

BASE = "/api/v1"
NOW = datetime.now(UTC)
START = NOW - timedelta(days=31)

_BUNDLE = {
    "captured_at": START.isoformat(),
    "all_criteria_passed": True,
    "gate_results": {
        "duration": {"name": "duration", "passed": True, "details": {}},
        "sharpe_margin": {"name": "sharpe_margin", "passed": True, "details": {}},
        "absolute_return": {"name": "absolute_return", "passed": True, "details": {}},
        "drawdown_divergence": {"name": "drawdown_divergence", "passed": True, "details": {}},
    },
}


async def _seed(
    *, proposal_state=ProposalState.EVIDENCE_READY, parent_status=StrategyStatus.LIVE,
    last_promoted_at=None, with_bundle=True, with_variant=True,
):
    async with get_sessionmaker()() as s:
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        s.add(User(id=2, email="other@test"))
        s.add(Strategy(
            id=1, user_id=1, name="S1", code_path="s.py", params_json={"rsi": 30},
            symbols_json=["AAPL"], status=parent_status,
            last_promoted_at=last_promoted_at, created_at=START, updated_at=START,
        ))
        if with_variant:
            s.add(Strategy(
                id=2, user_id=1, name="S1 (variant)", code_path="s.py",
                params_json={"rsi": 40}, symbols_json=["AAPL"],
                status=StrategyStatus.PAPER_VARIANT, parent_strategy_id=1,
                created_at=START, updated_at=START,
            ))
        eval_json = {"paper_variant": {"variant_strategy_id": 2}, "status": "complete"}
        if with_bundle:
            eval_json["evidence_bundle"] = _BUNDLE
        s.add(StrategyProposal(
            id=1, strategy_id=1, user_id=1, state=proposal_state,
            proposal_payload_json={"changes": [{"param": "rsi", "to": 40}]},
            evidence_bundle_json={}, evaluation_results_json=eval_json,
            generated_at=START, transitioned_at=START, created_at=START, updated_at=START,
        ))
        await s.commit()


async def _proposal():
    async with get_sessionmaker()() as s:
        return await s.get(StrategyProposal, 1)


async def _variant():
    async with get_sessionmaker()() as s:
        return await s.get(Strategy, 2)


# ---- the load-bearing invariant ----


def test_no_auto_promote_in_codebase():
    """ADR 0007 forbids auto-promotion. No `auto_promote` symbol may exist in the
    backend app code (the only 'auto' is §2c's `auto_validate_proposals`)."""
    app_dir = Path(__file__).resolve().parents[2] / "app"
    offenders = [
        str(py.relative_to(app_dir))
        for py in app_dir.rglob("*.py")
        if "auto_promote" in py.read_text(encoding="utf-8")
    ]
    assert offenders == [], f"auto_promote found in: {offenders}"


# ---- promote ----


async def test_promote_transitions_to_promoting(client):
    await _seed()
    r = await client.post(f"{BASE}/proposals/1/promote")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "promoting"
    p = await _proposal()
    assert p.state == ProposalState.PROMOTING
    assert p.transitioned_at is not None


async def test_promote_does_not_terminate_variant(client):
    # A1: variant stays alive through the cooldown (terminated at PROMOTED).
    await _seed()
    await client.post(f"{BASE}/proposals/1/promote")
    v = await _variant()
    assert v.status == StrategyStatus.PAPER_VARIANT


async def test_promote_writes_audit_with_bundle_hash(client):
    await _seed()
    await client.post(f"{BASE}/proposals/1/promote")
    async with get_sessionmaker()() as s:
        rows = (await s.execute(
            select(AuditLog).where(AuditLog.action == "STRATEGY_PROPOSAL_TRANSITIONED")
        )).scalars().all()
    import json
    payloads = [json.loads(a.payload_json) for a in rows]
    promoting = [p for p in payloads if p.get("to") == "PROMOTING"]
    assert len(promoting) == 1
    h = promoting[0]["evidence_bundle_hash"]
    assert isinstance(h, str) and len(h) == 64  # sha256 hex


async def test_promote_400_when_not_evidence_ready(client):
    await _seed(proposal_state=ProposalState.EVALUATING)
    r = await client.post(f"{BASE}/proposals/1/promote")
    assert r.status_code == 400


async def test_promote_409_when_parent_not_live(client):
    await _seed(parent_status=StrategyStatus.PAPER)
    r = await client.post(f"{BASE}/proposals/1/promote")
    assert r.status_code == 409


async def test_promote_409_when_in_lockout(client):
    await _seed(last_promoted_at=NOW - timedelta(days=5))
    r = await client.post(f"{BASE}/proposals/1/promote")
    assert r.status_code == 409
    assert "lockout" in r.json()["detail"].lower()


async def test_promote_409_when_no_bundle(client):
    await _seed(with_bundle=False)
    r = await client.post(f"{BASE}/proposals/1/promote")
    assert r.status_code == 409


async def test_promote_404_other_user(client):
    async with get_sessionmaker()() as s:
        s.add(User(id=2, email="other@test"))
        s.add(Strategy(id=9, user_id=2, name="X", code_path="s.py", params_json={},
                       symbols_json=[], status=StrategyStatus.LIVE,
                       created_at=START, updated_at=START))
        s.add(StrategyProposal(
            id=9, strategy_id=9, user_id=2, state=ProposalState.EVIDENCE_READY,
            proposal_payload_json={}, evidence_bundle_json={},
            evaluation_results_json={"evidence_bundle": _BUNDLE},
            generated_at=START, transitioned_at=START, created_at=START, updated_at=START,
        ))
        await s.commit()
    r = await client.post(f"{BASE}/proposals/9/promote")
    assert r.status_code == 404


# ---- reject-promotion ----


async def test_reject_from_evidence_ready(client):
    await _seed()
    r = await client.post(f"{BASE}/proposals/1/reject-promotion")
    assert r.status_code == 200
    assert r.json()["from_state"] == "EVIDENCE_READY"
    p = await _proposal()
    assert p.state == ProposalState.REJECTED
    v = await _variant()
    assert v.status == StrategyStatus.IDLE  # terminated


async def test_reject_from_promoting_cancels(client):
    await _seed(proposal_state=ProposalState.PROMOTING)
    r = await client.post(f"{BASE}/proposals/1/reject-promotion")
    assert r.status_code == 200
    assert r.json()["from_state"] == "PROMOTING"
    p = await _proposal()
    assert p.state == ProposalState.REJECTED
    v = await _variant()
    assert v.status == StrategyStatus.IDLE


async def test_reject_400_from_other_state(client):
    await _seed(proposal_state=ProposalState.EVALUATING)
    r = await client.post(f"{BASE}/proposals/1/reject-promotion")
    assert r.status_code == 400


# ---- additive fields on /variant-comparison ----


async def test_variant_comparison_additive_fields_evidence_ready(client):
    await _seed()
    r = await client.get(f"{BASE}/strategies/1/variant-comparison")
    assert r.status_code == 200
    comp = r.json()["comparison"]
    assert comp["proposal_state"] == "EVIDENCE_READY"
    assert comp["evidence_bundle"]["all_criteria_passed"] is True
    assert comp["eligible_for_promotion"] is True
    assert comp["parent_last_promoted_at"] is None


async def test_eligible_for_promotion_false_in_lockout(client):
    await _seed(last_promoted_at=NOW - timedelta(days=5))
    r = await client.get(f"{BASE}/strategies/1/variant-comparison")
    comp = r.json()["comparison"]
    assert comp["eligible_for_promotion"] is False


async def test_no_active_variant_still_carries_last_promoted_at(client):
    await _seed(last_promoted_at=NOW - timedelta(days=5), with_variant=False)
    r = await client.get(f"{BASE}/strategies/1/variant-comparison")
    body = r.json()
    assert body["status"] == "no_active_variant"
    assert body["parent_last_promoted_at"] is not None


# ---- lockout enforcement on /validate ----


@pytest.fixture
async def _accepted_in_lockout(client):
    async with get_sessionmaker()() as s:
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        s.add(Strategy(
            id=1, user_id=1, name="S1", code_path="s.py", params_json={"rsi": 30},
            symbols_json=["AAPL"], status=StrategyStatus.LIVE,
            last_promoted_at=NOW - timedelta(days=5), created_at=START, updated_at=START,
        ))
        s.add(StrategyProposal(
            id=1, strategy_id=1, user_id=1, state=ProposalState.ACCEPTED,
            proposal_payload_json={"changes": []}, evidence_bundle_json={},
            evaluation_results_json={},
            generated_at=NOW, transitioned_at=NOW, created_at=NOW, updated_at=NOW,
        ))
        await s.commit()
    return client


async def test_validate_409_in_lockout(client, _accepted_in_lockout):
    r = await client.post(f"{BASE}/proposals/1/validate")
    assert r.status_code == 409
    assert "lockout" in r.json()["detail"].lower()


async def test_validate_succeeds_after_lockout_expires(client):
    async with get_sessionmaker()() as s:
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        s.add(Strategy(
            id=1, user_id=1, name="S1", code_path="s.py", params_json={"rsi": 30},
            symbols_json=["AAPL"], status=StrategyStatus.LIVE,
            last_promoted_at=NOW - timedelta(days=31), created_at=START, updated_at=START,
        ))
        s.add(StrategyProposal(
            id=1, strategy_id=1, user_id=1, state=ProposalState.ACCEPTED,
            proposal_payload_json={"changes": []}, evidence_bundle_json={},
            evaluation_results_json={},
            generated_at=NOW, transitioned_at=NOW, created_at=NOW, updated_at=NOW,
        ))
        await s.commit()
    r = await client.post(f"{BASE}/proposals/1/validate")
    # No lockout 409 — spawn proceeds (200 with EVALUATING).
    assert r.status_code == 200
