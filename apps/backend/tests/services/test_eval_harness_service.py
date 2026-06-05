"""P6b §4 — eval-harness lifecycle service (start / stop / mutual exclusion /
invalidation) and its mutual exclusion with the §2 paper variant.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.db.enums import StrategyStatus
from app.db.models.audit_log import AuditLog
from app.db.models.eval_harness import (
    HARNESS_ACTIVE,
    HARNESS_TERMINATED,
    EvalHarness,
)
from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.db.models.user import User
from app.services.eval_harness.service import (
    find_active_harness,
    start_eval_harness,
    stop_eval_harness,
    terminate_harness_for_parent,
)
from app.services.paper_variant import PaperVariantService

NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


class _FakeEngine:
    def __init__(self) -> None:
        self.registered: list[int] = []
        self.unregistered: list[tuple[int, str]] = []

    async def register(self, sid: int) -> None:
        self.registered.append(sid)

    async def unregister(self, sid: int, *, reason: str = "stop") -> None:
        self.unregistered.append((sid, reason))


async def _seed_parent(session_factory, *, status=StrategyStatus.LIVE) -> None:
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        s.add(Strategy(
            id=1, user_id=1, name="S1", code_path="strat.py",
            params_json={"rsi": 30}, symbols_json=["AAPL"],
            status=status, created_at=NOW, updated_at=NOW,
        ))
        await s.commit()


async def _audit(session_factory, action: str):
    async with session_factory() as s:
        return (
            await s.execute(select(AuditLog).where(AuditLog.action == action))
        ).scalars().all()


async def test_start_spawns_mode_a_paper_variant_and_mode_b_idle(session_factory):
    await _seed_parent(session_factory)
    eng = _FakeEngine()
    async with session_factory() as s:
        harness = await start_eval_harness(
            s, parent_strategy_id=1, user_id=1, engine=eng
        )
    async with session_factory() as s:
        a = await s.get(Strategy, harness.mode_a_strategy_id)
        b = await s.get(Strategy, harness.mode_b_strategy_id)
    assert a.status == StrategyStatus.PAPER_VARIANT
    assert a.harness_role == "mode_a"
    assert b.status == StrategyStatus.IDLE       # bucket, never registered
    assert b.harness_role == "mode_b"
    assert eng.registered == [harness.mode_a_strategy_id]  # only A registered
    assert harness.state == HARNESS_ACTIVE


async def test_start_writes_started_audit(session_factory):
    await _seed_parent(session_factory)
    async with session_factory() as s:
        await start_eval_harness(s, parent_strategy_id=1, user_id=1, engine=None)
    assert len(await _audit(session_factory, "EVAL_HARNESS_STARTED")) == 1


async def test_start_rejects_non_live_parent(session_factory):
    await _seed_parent(session_factory, status=StrategyStatus.PAPER)
    async with session_factory() as s:
        with pytest.raises(ValueError, match="parent_not_live"):
            await start_eval_harness(s, parent_strategy_id=1, user_id=1)


async def test_start_rejects_other_user(session_factory):
    await _seed_parent(session_factory)
    async with session_factory() as s:
        with pytest.raises(ValueError, match="parent_not_found"):
            await start_eval_harness(s, parent_strategy_id=1, user_id=2)


async def test_start_rejects_second_harness(session_factory):
    await _seed_parent(session_factory)
    async with session_factory() as s:
        await start_eval_harness(s, parent_strategy_id=1, user_id=1)
    async with session_factory() as s:
        with pytest.raises(ValueError, match="eval_harness_already_active"):
            await start_eval_harness(s, parent_strategy_id=1, user_id=1)


async def test_start_rejects_when_paper_variant_in_flight(session_factory):
    await _seed_parent(session_factory)
    async with session_factory() as s:
        s.add(StrategyProposal(
            id=1, strategy_id=1, user_id=1, state=ProposalState.ACCEPTED,
            proposal_payload_json={"changes": [{"param": "rsi", "to": 40}]},
            evidence_bundle_json={}, evaluation_results_json={},
            generated_at=NOW, transitioned_at=NOW, created_at=NOW, updated_at=NOW,
        ))
        await s.commit()
        await PaperVariantService(s, None).spawn(proposal_id=1, user_id=1)
    async with session_factory() as s:
        with pytest.raises(ValueError, match="paper_variant_in_flight"):
            await start_eval_harness(s, parent_strategy_id=1, user_id=1)


async def test_paper_variant_spawn_rejected_when_harness_active(session_factory):
    """Mutual exclusion the other direction: a §2 variant can't spawn while an
    eval harness is running."""
    await _seed_parent(session_factory)
    async with session_factory() as s:
        await start_eval_harness(s, parent_strategy_id=1, user_id=1)
    async with session_factory() as s:
        s.add(StrategyProposal(
            id=1, strategy_id=1, user_id=1, state=ProposalState.ACCEPTED,
            proposal_payload_json={"changes": [{"param": "rsi", "to": 40}]},
            evidence_bundle_json={}, evaluation_results_json={},
            generated_at=NOW, transitioned_at=NOW, created_at=NOW, updated_at=NOW,
        ))
        await s.commit()
        with pytest.raises(ValueError, match="eval_harness_active"):
            await PaperVariantService(s, None).spawn(proposal_id=1, user_id=1)


async def test_stop_unregisters_mode_a_and_terminates(session_factory):
    await _seed_parent(session_factory)
    eng = _FakeEngine()
    async with session_factory() as s:
        harness = await start_eval_harness(
            s, parent_strategy_id=1, user_id=1, engine=eng
        )
    async with session_factory() as s:
        await stop_eval_harness(s, harness_id=harness.id, user_id=1, engine=eng)
    async with session_factory() as s:
        h = await s.get(EvalHarness, harness.id)
    assert h.state == HARNESS_TERMINATED
    assert h.terminated_reason == "user_stopped"
    assert (harness.mode_a_strategy_id, "eval_harness_user_stopped") in eng.unregistered


async def test_stop_no_engine_sets_mode_a_idle(session_factory):
    await _seed_parent(session_factory)
    async with session_factory() as s:
        harness = await start_eval_harness(s, parent_strategy_id=1, user_id=1)
    async with session_factory() as s:
        await stop_eval_harness(s, harness_id=harness.id, user_id=1, engine=None)
    async with session_factory() as s:
        a = await s.get(Strategy, harness.mode_a_strategy_id)
    assert a.status == StrategyStatus.IDLE


async def test_stop_other_user_raises(session_factory):
    await _seed_parent(session_factory)
    async with session_factory() as s:
        harness = await start_eval_harness(s, parent_strategy_id=1, user_id=1)
    async with session_factory() as s:
        with pytest.raises(ValueError, match="harness_not_found"):
            await stop_eval_harness(s, harness_id=harness.id, user_id=2)


async def test_terminate_for_parent_invalidates(session_factory):
    await _seed_parent(session_factory)
    async with session_factory() as s:
        await start_eval_harness(s, parent_strategy_id=1, user_id=1)
    async with session_factory() as s:
        await terminate_harness_for_parent(
            s, parent_strategy_id=1, engine=None, reason="parent_deactivated"
        )
    async with session_factory() as s:
        assert await find_active_harness(s, 1) is None


async def test_terminate_for_parent_noop_when_none(session_factory):
    await _seed_parent(session_factory)
    async with session_factory() as s:
        await terminate_harness_for_parent(
            s, parent_strategy_id=1, engine=None, reason="x"
        )  # no raise


async def test_stop_is_idempotent(session_factory):
    await _seed_parent(session_factory)
    async with session_factory() as s:
        harness = await start_eval_harness(s, parent_strategy_id=1, user_id=1)
    async with session_factory() as s:
        await stop_eval_harness(s, harness_id=harness.id, user_id=1)
    async with session_factory() as s:  # second stop is a no-op (already terminated)
        await stop_eval_harness(s, harness_id=harness.id, user_id=1)
    async with session_factory() as s:
        h = await s.get(EvalHarness, harness.id)
    assert h.state == HARNESS_TERMINATED
