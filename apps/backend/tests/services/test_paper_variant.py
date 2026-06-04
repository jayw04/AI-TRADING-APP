"""P6b §2a-variant — PaperVariantService (spawn / terminate / expiry)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.enums import StrategyStatus
from app.db.models.audit_log import AuditLog
from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.db.models.user import User
from app.services.paper_variant import (
    PaperVariantService,
    run_paper_variant_expiry,
)

NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


def test_engine_runnable_includes_variant_not_active():
    from app.db.enums import (
        ACTIVE_STRATEGY_STATUSES,
        ENGINE_RUNNABLE_STATUSES,
        StrategyStatus,
    )

    # D2: variants run/resume but are NOT user-facing-active.
    assert StrategyStatus.PAPER_VARIANT in ENGINE_RUNNABLE_STATUSES
    assert StrategyStatus.PAPER_VARIANT not in ACTIVE_STRATEGY_STATUSES
    assert ACTIVE_STRATEGY_STATUSES <= ENGINE_RUNNABLE_STATUSES


class _FakeEngine:
    def __init__(self) -> None:
        self.registered: list[int] = []
        self.unregistered: list[tuple[int, str]] = []

    async def register(self, sid: int) -> None:
        self.registered.append(sid)

    async def unregister(self, sid: int, *, reason: str = "user_stop") -> None:
        self.unregistered.append((sid, reason))


async def _seed(
    session_factory,
    *,
    parent_status=StrategyStatus.LIVE,
    proposal_state=ProposalState.ACCEPTED,
    changes=None,
) -> int:
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        s.add(Strategy(
            id=1, user_id=1, name="S1", code_path="strat.py",
            params_json={"rsi": 30}, symbols_json=["AAPL"],
            status=parent_status, created_at=NOW, updated_at=NOW,
        ))
        prop = StrategyProposal(
            strategy_id=1, user_id=1, state=proposal_state,
            proposal_payload_json={"changes": changes if changes is not None
                                   else [{"param": "rsi", "from": 30, "to": 40}]},
            evidence_bundle_json={}, evaluation_results_json={},
            generated_at=NOW, transitioned_at=NOW, created_at=NOW, updated_at=NOW,
        )
        s.add(prop)
        await s.commit()
        return prop.id


async def _audit(session_factory, action: str):
    async with session_factory() as s:
        return (
            await s.execute(select(AuditLog).where(AuditLog.action == action))
        ).scalars().all()


async def test_spawn_clones_strategy_with_variant_params(session_factory):
    pid = await _seed(session_factory)
    eng = _FakeEngine()
    async with session_factory() as s:
        variant = await PaperVariantService(s, eng).spawn(proposal_id=pid, user_id=1)
    async with session_factory() as s:
        v = await s.get(Strategy, variant.id)
    assert v.parent_strategy_id == 1
    assert v.status == StrategyStatus.PAPER_VARIANT
    assert v.params_json["rsi"] == 40  # parent params merged with the change
    assert eng.registered == [variant.id]


async def test_spawn_transitions_proposal_to_evaluating(session_factory):
    pid = await _seed(session_factory)
    async with session_factory() as s:
        await PaperVariantService(s, None).spawn(proposal_id=pid, user_id=1)
    async with session_factory() as s:
        p = await s.get(StrategyProposal, pid)
    assert p.state == ProposalState.EVALUATING
    assert p.evaluation_results_json["paper_variant"]["variant_strategy_id"]


async def test_spawn_writes_spawned_audit(session_factory):
    pid = await _seed(session_factory)
    async with session_factory() as s:
        await PaperVariantService(s, None).spawn(proposal_id=pid, user_id=1)
    assert len(await _audit(session_factory, "PAPER_VARIANT_SPAWNED")) == 1


async def test_spawn_rejects_non_accepted(session_factory):
    pid = await _seed(session_factory, proposal_state=ProposalState.REVIEWING)
    async with session_factory() as s:
        with pytest.raises(ValueError, match="proposal_not_accepted"):
            await PaperVariantService(s, None).spawn(proposal_id=pid, user_id=1)


async def test_spawn_rejects_non_live_parent(session_factory):
    pid = await _seed(session_factory, parent_status=StrategyStatus.PAPER)
    async with session_factory() as s:
        with pytest.raises(ValueError, match="parent_not_live"):
            await PaperVariantService(s, None).spawn(proposal_id=pid, user_id=1)


async def test_spawn_rejects_second_variant(session_factory):
    pid = await _seed(session_factory)
    async with session_factory() as s:
        await PaperVariantService(s, None).spawn(proposal_id=pid, user_id=1)
    async with session_factory() as s:
        ts = NOW + timedelta(minutes=1)
        s.add(StrategyProposal(
            strategy_id=1, user_id=1, state=ProposalState.ACCEPTED,
            proposal_payload_json={"changes": []}, evidence_bundle_json={},
            evaluation_results_json={}, generated_at=ts, transitioned_at=ts,
            created_at=ts, updated_at=ts,
        ))
        await s.commit()
        pid2 = (await s.execute(
            select(StrategyProposal).where(StrategyProposal.state == ProposalState.ACCEPTED)
        )).scalars().first().id
    async with session_factory() as s:
        with pytest.raises(ValueError, match="variant_already_in_flight"):
            await PaperVariantService(s, None).spawn(proposal_id=pid2, user_id=1)


async def test_terminate_unregisters_audits_and_rejects(session_factory):
    pid = await _seed(session_factory)
    eng = _FakeEngine()
    async with session_factory() as s:
        v = await PaperVariantService(s, eng).spawn(proposal_id=pid, user_id=1)
    async with session_factory() as s:
        await PaperVariantService(s, eng).terminate(
            variant_strategy_id=v.id, reason="user_stopped", user_id=1
        )
    assert (v.id, "paper_variant_user_stopped") in eng.unregistered
    assert len(await _audit(session_factory, "PAPER_VARIANT_TERMINATED")) == 1
    async with session_factory() as s:
        p = await s.get(StrategyProposal, pid)
    assert p.state == ProposalState.REJECTED


async def test_terminate_no_engine_sets_idle(session_factory):
    pid = await _seed(session_factory)
    async with session_factory() as s:
        v = await PaperVariantService(s, None).spawn(proposal_id=pid, user_id=1)
    async with session_factory() as s:
        await PaperVariantService(s, None).terminate(
            variant_strategy_id=v.id, reason="user_stopped", user_id=1
        )
    async with session_factory() as s:
        vv = await s.get(Strategy, v.id)
    assert vv.status == StrategyStatus.IDLE


async def test_terminate_for_parent_no_variant_is_noop(session_factory):
    await _seed(session_factory)
    async with session_factory() as s:
        await PaperVariantService(s, None).terminate_for_parent(
            parent_strategy_id=1, reason="x", user_id=1
        )  # no raise


async def test_expiry_terminates_old_variants(session_factory):
    pid = await _seed(session_factory)
    async with session_factory() as s:
        v = await PaperVariantService(s, None).spawn(proposal_id=pid, user_id=1)
    async with session_factory() as s:
        vv = await s.get(Strategy, v.id)
        vv.created_at = datetime.now(UTC) - timedelta(days=100)
        await s.commit()
    result = await run_paper_variant_expiry(session_factory=session_factory, engine=None)
    assert result["terminated"] == 1
    async with session_factory() as s:
        vv = await s.get(Strategy, v.id)
    assert vv.status == StrategyStatus.IDLE


async def test_expiry_skips_young_variants(session_factory):
    pid = await _seed(session_factory)
    async with session_factory() as s:
        await PaperVariantService(s, None).spawn(proposal_id=pid, user_id=1)
    result = await run_paper_variant_expiry(session_factory=session_factory, engine=None)
    assert result["terminated"] == 0
