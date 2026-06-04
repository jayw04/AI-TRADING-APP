"""P6b §3b-promote — cooldown completion cron + mechanical promote."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.enums import StrategyStatus
from app.db.models.audit_log import AuditLog
from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.db.models.user import User
from app.jobs.promotion_completion import run_promotion_completion
from app.services.promotion import execute_mechanical_promote

NOW = datetime.now(UTC)


async def _seed(session_factory, *, transitioned_delta_h=25, parent_status=StrategyStatus.LIVE):
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        s.add(Strategy(
            id=1, user_id=1, name="S1", code_path="s.py", params_json={"rsi": 30},
            symbols_json=["AAPL"], status=parent_status,
            created_at=NOW - timedelta(days=40), updated_at=NOW,
        ))
        s.add(Strategy(
            id=2, user_id=1, name="S1 (variant)", code_path="s.py",
            params_json={"rsi": 40}, symbols_json=["AAPL"],
            status=StrategyStatus.PAPER_VARIANT, parent_strategy_id=1,
            created_at=NOW - timedelta(days=31), updated_at=NOW,
        ))
        s.add(StrategyProposal(
            id=1, strategy_id=1, user_id=1, state=ProposalState.PROMOTING,
            proposal_payload_json={"changes": [{"param": "rsi", "to": 40}]},
            evidence_bundle_json={}, evaluation_results_json={
                "paper_variant": {"variant_strategy_id": 2}, "evidence_bundle": {"x": 1},
            },
            generated_at=NOW - timedelta(days=31),
            transitioned_at=NOW - timedelta(hours=transitioned_delta_h),
            created_at=NOW - timedelta(days=31), updated_at=NOW,
        ))
        await s.commit()


async def test_cron_promotes_elapsed_proposal(session_factory):
    await _seed(session_factory, transitioned_delta_h=25)
    result = await run_promotion_completion(session_factory=session_factory, engine=None)
    assert result == {"promoted": 1, "errored": 0}
    async with session_factory() as s:
        p = await s.get(StrategyProposal, 1)
        parent = await s.get(Strategy, 1)
        variant = await s.get(Strategy, 2)
    assert p.state == ProposalState.PROMOTED
    assert parent.params_json["rsi"] == 40          # change applied
    assert parent.last_promoted_at is not None       # lockout clock starts
    assert variant.status == StrategyStatus.IDLE      # variant terminated at PROMOTED


async def test_cron_skips_not_yet_elapsed(session_factory):
    await _seed(session_factory, transitioned_delta_h=1)  # only 1h into 24h cooldown
    result = await run_promotion_completion(session_factory=session_factory, engine=None)
    assert result == {"promoted": 0, "errored": 0}
    async with session_factory() as s:
        p = await s.get(StrategyProposal, 1)
    assert p.state == ProposalState.PROMOTING


async def test_mechanical_promote_writes_strategy_promoted_marker(session_factory):
    await _seed(session_factory)
    async with session_factory() as s:
        proposal = await s.get(StrategyProposal, 1)
        promoted = await execute_mechanical_promote(s, proposal=proposal, engine=None)
    assert promoted is True
    async with session_factory() as s:
        marker = (await s.execute(
            select(AuditLog).where(AuditLog.action == "STRATEGY_PROMOTED")
        )).scalars().all()
        transitions = (await s.execute(
            select(AuditLog)
            .where(AuditLog.action == "STRATEGY_PROPOSAL_TRANSITIONED")
        )).scalars().all()
    assert len(marker) == 1
    import json
    assert json.loads(marker[0].payload_json)["applied_changes"] == [{"param": "rsi", "to": 40}]
    assert any(json.loads(t.payload_json).get("to") == "PROMOTED" for t in transitions)


async def test_mechanical_promote_skips_when_not_promoting(session_factory):
    await _seed(session_factory)
    async with session_factory() as s:
        proposal = await s.get(StrategyProposal, 1)
        proposal.state = ProposalState.REJECTED  # raced out of PROMOTING
        await s.commit()
        proposal = await s.get(StrategyProposal, 1)
        assert await execute_mechanical_promote(s, proposal=proposal, engine=None) is False


async def test_cron_isolates_parent_no_longer_live(session_factory):
    await _seed(session_factory, parent_status=StrategyStatus.IDLE)
    result = await run_promotion_completion(session_factory=session_factory, engine=None)
    assert result["promoted"] == 0
    assert result["errored"] == 1
    async with session_factory() as s:
        p = await s.get(StrategyProposal, 1)
    assert p.state == ProposalState.PROMOTING  # left intact for manual reject
