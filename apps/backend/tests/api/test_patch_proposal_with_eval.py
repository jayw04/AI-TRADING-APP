"""P6 §2b-backtest — PATCH DRAFT→REVIEWING enqueues backtest eval atomically."""
from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models.audit_log import AuditLog
from app.db.models.backtest_job import BacktestJob
from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.db.models.user import User
from app.db.session import get_sessionmaker

BASE = "/api/v1"
_PAYLOAD = {"confidence": "MEDIUM", "summary": "x", "changes": [{"param": "rsi_min", "to": 55}]}
_BODY = {
    "target_state": "REVIEWING",
    "proposal_payload": _PAYLOAD,
    "evidence_bundle": {"k": "v"},
    "llm_usage": {"model": "claude-sonnet-4-6", "cost_cents": "1.5"},
}


async def _seed_proposal(*, code_path="strat.py", symbols=("AAPL",)) -> int:
    async with get_sessionmaker()() as s:
        now = datetime.now(UTC)
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        s.add(
            Strategy(
                id=1, user_id=1, name="S1", code_path=code_path,
                params_json={"rsi_min": 50}, symbols_json=list(symbols),
                created_at=now, updated_at=now,
            )
        )
        prop = StrategyProposal(
            strategy_id=1, user_id=1, state=ProposalState.DRAFT,
            proposal_payload_json={}, evidence_bundle_json={},
            evaluation_results_json={},
            generated_at=now, transitioned_at=now, created_at=now, updated_at=now,
        )
        s.add(prop)
        await s.commit()
        return prop.id


async def test_patch_to_reviewing_enqueues_eval(client):
    pid = await _seed_proposal()
    r = await client.patch(f"{BASE}/proposals/{pid}", json=_BODY)
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "REVIEWING"
    assert r.json()["evaluation_results"]["status"] == "pending"
    async with get_sessionmaker()() as s:
        jobs = (await s.execute(select(BacktestJob))).scalars().all()
    assert {j.label for j in jobs} == {f"proposal_{pid}_baseline", f"proposal_{pid}_variant"}


async def test_patch_to_reviewing_skips_eval_for_non_python(client):
    pid = await _seed_proposal(code_path=None)
    r = await client.patch(f"{BASE}/proposals/{pid}", json=_BODY)
    assert r.status_code == 200
    assert r.json()["state"] == "REVIEWING"  # still transitions
    assert r.json()["evaluation_results"]["status"] == "skipped"
    assert r.json()["evaluation_results"]["skipped_reason"] == "non_python_strategy"


async def test_patch_eval_enqueue_failure_is_non_fatal(client, monkeypatch):
    pid = await _seed_proposal()

    async def boom(session, *, proposal_id):
        raise RuntimeError("backtest model exploded")

    monkeypatch.setattr(
        "app.services.proposal_evaluation.enqueue_eval_for_proposal", boom
    )
    r = await client.patch(f"{BASE}/proposals/{pid}", json=_BODY)
    assert r.status_code == 200
    assert r.json()["state"] == "REVIEWING"
    assert r.json()["evaluation_results"]["status"] == "failed"


async def test_patch_audit_carries_eval_status(client):
    pid = await _seed_proposal()
    await client.patch(f"{BASE}/proposals/{pid}", json=_BODY)
    async with get_sessionmaker()() as s:
        rows = (
            await s.execute(
                select(AuditLog).where(AuditLog.action == "STRATEGY_PROPOSAL_TRANSITIONED")
            )
        ).scalars().all()
    review_row = [r for r in rows if json.loads(r.payload_json).get("to") == "REVIEWING"][-1]
    assert json.loads(review_row.payload_json)["eval_status"] == "pending"
