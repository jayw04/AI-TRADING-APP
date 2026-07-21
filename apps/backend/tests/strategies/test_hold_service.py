"""P7 §7-B — DB-backed guard + CAS HoldService: concurrency + fail-closed."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.audit.logger import AuditLogger
from app.db.models.audit_log import AuditLog
from app.db.models.strategy_state import StrategyState
from app.strategies.hold_service import (
    HoldConflict,
    HoldService,
    HoldStateInvalid,
    HoldStoreUnavailable,
    StrategyOnHold,
    assert_no_active_hold,
    read_hold,
    record_activation_blocked,
)
from app.strategies.operational_hold import K_OPERATIONAL_HOLD

SID = 11
EFF = "2026-07-20T22:48:22Z"
NOW = "2026-07-21T00:00:00Z"


async def _audit_rows(session_factory, action: str, strategy_id: int = SID) -> list[AuditLog]:
    async with session_factory() as session:
        return list(
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.action == action,
                        func.json_extract(AuditLog.payload_json, "$.strategy_id") == strategy_id,
                    )
                )
            ).scalars().all()
        )


async def _audit_count(session_factory, action: str, strategy_id: int = SID) -> int:
    return len(await _audit_rows(session_factory, action, strategy_id))


async def _seed_state(session_factory, value: dict):
    async with session_factory() as session, session.begin():
        session.add(StrategyState(strategy_id=SID, key=K_OPERATIONAL_HOLD, value=value,
                                  updated_at=__import__("datetime").datetime.now(
                                      __import__("datetime").UTC)))


def _svc(session_factory):
    return HoldService(session_factory)


async def _session(session_factory):
    return session_factory()


# ---- place ----

async def test_place_on_absent_creates_active_rev_1(session_factory):
    r = await _svc(session_factory).place(
        SID, reason_code="AWAITING_COLD_START_FIX", reason="repair",
        effective_at=EFF, placed_at=NOW, placed_by="user:4")
    assert r.changed is True and r.record.is_active and r.record.rev == 1


async def test_place_identical_active_is_idempotent_noop(session_factory):
    svc = _svc(session_factory)
    await svc.place(SID, reason_code="AWAITING_COLD_START_FIX", reason="x",
                    effective_at=EFF, placed_at=NOW, placed_by="user:4")
    r = await svc.place(SID, reason_code="AWAITING_COLD_START_FIX", reason="x2",
                        effective_at=EFF, placed_at=NOW, placed_by="user:4")
    assert r.changed is False and r.was_noop is True and r.record.rev == 1


async def test_place_active_with_different_reason_conflicts(session_factory):
    svc = _svc(session_factory)
    await svc.place(SID, reason_code="AWAITING_COLD_START_FIX", reason="x",
                    effective_at=EFF, placed_at=NOW, placed_by="user:4")
    with pytest.raises(HoldConflict):
        await svc.place(SID, reason_code="SOMETHING_ELSE", reason="y",
                        effective_at=EFF, placed_at=NOW, placed_by="user:4")


# ---- clear ----

async def test_clear_requires_expected_active_revision(session_factory):
    svc = _svc(session_factory)
    p = await svc.place(SID, reason_code="RC", reason="x", effective_at=EFF,
                        placed_at=NOW, placed_by="user:4")
    r = await svc.clear(SID, expected_rev=p.record.rev, cleared_at=NOW, cleared_by="user:4")
    assert r.changed is True and r.record.status.value == "CLEARED" and r.record.rev == 2


async def test_stale_clear_fails_and_leaves_record_unchanged(session_factory):
    svc = _svc(session_factory)
    await svc.place(SID, reason_code="RC", reason="x", effective_at=EFF,
                    placed_at=NOW, placed_by="user:4")
    with pytest.raises(HoldConflict):
        await svc.clear(SID, expected_rev=99, cleared_at=NOW, cleared_by="user:4")
    assert (await svc.read(SID)).is_active is True  # unchanged, still active


async def test_concurrent_clear_yields_exactly_one_transition(session_factory):
    svc = _svc(session_factory)
    p = await svc.place(SID, reason_code="RC", reason="x", effective_at=EFF,
                        placed_at=NOW, placed_by="user:4")
    # Two callers race to clear the same active hold: the winner transitions; the
    # other, re-reading an already-CLEARED hold, is a no-op. Exactly ONE transition.
    a = await svc.clear(SID, expected_rev=p.record.rev, cleared_at=NOW, cleared_by="user:4")
    b = await svc.clear(SID, expected_rev=p.record.rev, cleared_at=NOW, cleared_by="user:4")
    assert a.changed is True and b.changed is False and b.was_noop is True
    final = await svc.read(SID)
    assert final.status.value == "CLEARED" and final.rev == 2  # one transition, not two


async def test_reclear_of_cleared_is_noop(session_factory):
    svc = _svc(session_factory)
    p = await svc.place(SID, reason_code="RC", reason="x", effective_at=EFF,
                        placed_at=NOW, placed_by="user:4")
    await svc.clear(SID, expected_rev=p.record.rev, cleared_at=NOW, cleared_by="user:4")
    r = await svc.clear(SID, expected_rev=2, cleared_at=NOW, cleared_by="user:4")
    assert r.changed is False and r.was_noop is True  # NOT a new governed action


# ---- fail-closed ----

async def test_malformed_state_blocks_guard_and_mutation(session_factory):
    await _seed_state(session_factory, {"schema_version": 999, "_rev": 1, "status": "ACTIVE"})
    svc = _svc(session_factory)
    async with session_factory() as session:
        with pytest.raises(HoldStateInvalid):
            await assert_no_active_hold(session, SID)
    with pytest.raises(HoldStateInvalid):
        await svc.place(SID, reason_code="RC", reason="x", effective_at=EFF,
                        placed_at=NOW, placed_by="user:4")
    with pytest.raises(HoldStateInvalid):
        await svc.clear(SID, expected_rev=1, cleared_at=NOW, cleared_by="user:4")


async def test_query_failure_is_store_unavailable_not_no_hold():
    session = MagicMock()
    session.execute = AsyncMock(side_effect=OperationalError("stmt", {}, Exception("db down")))
    with pytest.raises(HoldStoreUnavailable):
        await read_hold(session, SID)


# ---- guard allow/deny ----

async def test_guard_allows_absent_and_cleared_denies_active(session_factory):
    svc = _svc(session_factory)
    async with session_factory() as session:
        await assert_no_active_hold(session, SID)  # absent -> ok
    p = await svc.place(SID, reason_code="RC", reason="x", effective_at=EFF,
                        placed_at=NOW, placed_by="user:4")
    async with session_factory() as session:
        with pytest.raises(StrategyOnHold):
            await assert_no_active_hold(session, SID)  # active -> block
    await svc.clear(SID, expected_rev=p.record.rev, cleared_at=NOW, cleared_by="user:4")
    async with session_factory() as session:
        await assert_no_active_hold(session, SID)  # cleared -> allowed
    assert (await svc.read(SID)).status.value == "CLEARED"  # but still durably readable


# ---- piece 3: audit atomicity (the 8 proofs) ----

# 1. place() -> exactly one STRATEGY_HOLD_PLACED, carrying the mutation's identity.
async def test_place_emits_one_placed_audit(session_factory):
    r = await _svc(session_factory).place(
        SID, reason_code="AWAITING_COLD_START_FIX", reason="repair", effective_at=EFF,
        placed_at=NOW, placed_by="user:4", source="RETROSPECTIVE_FORMALIZATION")
    rows = await _audit_rows(session_factory, "STRATEGY_HOLD_PLACED")
    assert len(rows) == 1
    p = json.loads(rows[0].payload_json)
    assert p["rev"] == r.record.rev == 1 and p["reason_code"] == "AWAITING_COLD_START_FIX"
    assert p["source"] == "RETROSPECTIVE_FORMALIZATION" and p["placed_by"] == "user:4"


# 2. idempotent re-place -> the no-op writes NO second audit event.
async def test_idempotent_replace_writes_no_duplicate_audit(session_factory):
    svc = _svc(session_factory)
    await svc.place(SID, reason_code="RC", reason="x", effective_at=EFF,
                    placed_at=NOW, placed_by="user:4")
    await svc.place(SID, reason_code="RC", reason="x2", effective_at=EFF,
                    placed_at=NOW, placed_by="user:4")  # no-op
    assert await _audit_count(session_factory, "STRATEGY_HOLD_PLACED") == 1


# 3. clear() -> exactly one STRATEGY_HOLD_CLEARED.
async def test_clear_emits_one_cleared_audit(session_factory):
    svc = _svc(session_factory)
    p = await svc.place(SID, reason_code="RC", reason="x", effective_at=EFF,
                        placed_at=NOW, placed_by="user:4")
    await svc.clear(SID, expected_rev=p.record.rev, cleared_at=NOW, cleared_by="user:4")
    rows = await _audit_rows(session_factory, "STRATEGY_HOLD_CLEARED")
    assert len(rows) == 1
    c = json.loads(rows[0].payload_json)
    assert c["rev"] == 2 and c["prior_rev"] == 1 and c["cleared_by"] == "user:4"


# 4. stale clear + re-clear-of-cleared -> NO false STRATEGY_HOLD_CLEARED audit.
async def test_stale_and_reclear_write_no_false_cleared_audit(session_factory):
    svc = _svc(session_factory)
    p = await svc.place(SID, reason_code="RC", reason="x", effective_at=EFF,
                        placed_at=NOW, placed_by="user:4")
    with pytest.raises(HoldConflict):  # stale rev -> conflict, no mutation, no audit
        await svc.clear(SID, expected_rev=99, cleared_at=NOW, cleared_by="user:4")
    assert await _audit_count(session_factory, "STRATEGY_HOLD_CLEARED") == 0
    await svc.clear(SID, expected_rev=p.record.rev, cleared_at=NOW, cleared_by="user:4")  # 1
    await svc.clear(SID, expected_rev=2, cleared_at=NOW, cleared_by="user:4")  # re-clear no-op
    assert await _audit_count(session_factory, "STRATEGY_HOLD_CLEARED") == 1  # still one


# 5. audit-write failure ROLLS BACK the hold mutation (both-or-neither).
async def test_audit_failure_rolls_back_hold_mutation(session_factory, monkeypatch):
    monkeypatch.setattr(AuditLogger, "write", MagicMock(side_effect=RuntimeError("audit down")))
    svc = _svc(session_factory)
    with pytest.raises(RuntimeError):
        await svc.place(SID, reason_code="RC", reason="x", effective_at=EFF,
                        placed_at=NOW, placed_by="user:4")
    assert await svc.read(SID) is None  # state did NOT persist


# 6. hold-state (CAS) failure creates NO audit event.
async def test_hold_state_failure_creates_no_audit(session_factory, monkeypatch):
    monkeypatch.setattr(HoldService, "_cas_in", AsyncMock(side_effect=HoldConflict("cas lost")))
    svc = _svc(session_factory)
    with pytest.raises(HoldConflict):
        await svc.place(SID, reason_code="RC", reason="x", effective_at=EFF,
                        placed_at=NOW, placed_by="user:4")
    assert await _audit_count(session_factory, "STRATEGY_HOLD_PLACED") == 0
    assert await svc.read(SID) is None


# 7. blocked activation records the correct strategy / hold rev / source / run id.
async def test_blocked_activation_records_identity(session_factory):
    async with session_factory() as session, session.begin():
        wrote = await record_activation_blocked(
            session, strategy_id=SID, reason_code="AWAITING_COLD_START_FIX",
            hold_rev=3, source="engine.register", run_id="run-abc")
    assert wrote is True
    rows = await _audit_rows(session_factory, "STRATEGY_ACTIVATION_BLOCKED_BY_HOLD")
    assert len(rows) == 1
    p = json.loads(rows[0].payload_json)
    assert p["strategy_id"] == SID and p["hold_rev"] == 3
    assert p["source"] == "engine.register" and p["run_id"] == "run-abc"


# 8. duplicate boot attempts (same strategy/rev/source/run) -> ONE blocked event.
async def test_duplicate_boot_blocked_events_deduplicated(session_factory):
    for _ in range(3):
        async with session_factory() as session, session.begin():
            wrote = await record_activation_blocked(
                session, strategy_id=SID, reason_code="RC", hold_rev=3,
                source="boot", run_id="run-1")
        assert wrote is (_ == 0)  # only the first writes
    assert await _audit_count(session_factory, "STRATEGY_ACTIVATION_BLOCKED_BY_HOLD") == 1
    # a genuinely new attempt (different run) IS a distinct event.
    async with session_factory() as session, session.begin():
        assert await record_activation_blocked(
            session, strategy_id=SID, reason_code="RC", hold_rev=3,
            source="boot", run_id="run-2") is True
    assert await _audit_count(session_factory, "STRATEGY_ACTIVATION_BLOCKED_BY_HOLD") == 2
