"""P7 §7-B — retrospective STRATEGY_HOLD_PLACED formalization (ADR 0044).

The sanctioned way to back-record an already-ACTIVE hold: emit exactly one
STRATEGY_HOLD_PLACED audit (source=RETROSPECTIVE_FORMALIZATION) WITHOUT mutating the
hold blob, validated against operator expectations, fail-closed, deduplicated.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.db.models.audit_log import AuditLog
from app.db.models.strategy_state import StrategyState
from app.strategies.hold_service import (
    RETRO_SOURCE,
    HoldService,
    RetroFormalizationRefused,
    formalize_retrospective_hold_placed,
)
from app.strategies.operational_hold import K_OPERATIONAL_HOLD, HoldStateInvalid

SID = 11
RC = "AWAITING_COLD_START_FIX"
EFF = "2026-07-20T22:48:22Z"
NOW = "2026-07-21T00:00:00Z"
PLACED = "STRATEGY_HOLD_PLACED"


def _now() -> datetime:
    return datetime.now(UTC)


async def _place_active(session_factory, *, rev_to: int = 1):
    """Establish a real schema-v1 ACTIVE hold (rev 1) via the sanctioned service."""
    return await HoldService(session_factory).place(
        SID, reason_code=RC, reason="cold-start repair", effective_at=EFF,
        placed_at=NOW, placed_by="user:4")


async def _seed_raw(session_factory, key: str, value: dict):
    async with session_factory() as session, session.begin():
        session.add(StrategyState(strategy_id=SID, key=key, value=value, updated_at=_now()))


async def _read_raw(session_factory, key: str) -> dict | None:
    async with session_factory() as session:
        return (await session.execute(select(StrategyState.value).where(
            StrategyState.strategy_id == SID, StrategyState.key == key))).scalars().first()


async def _retro_audit_rows(session_factory) -> list[AuditLog]:
    async with session_factory() as session:
        return list((await session.execute(select(AuditLog).where(
            AuditLog.action == PLACED,
            func.json_extract(AuditLog.payload_json, "$.source") == RETRO_SOURCE,
            func.json_extract(AuditLog.payload_json, "$.strategy_id") == SID,
        ))).scalars().all())


async def _run(session_factory, *, apply: bool, expected_rev=1,
               expected_reason_code=RC, expected_effective_at=EFF,
               evidence_refs=None, approval_ref=None):
    async with session_factory() as session, session.begin():
        return await formalize_retrospective_hold_placed(
            session, strategy_id=SID, expected_rev=expected_rev,
            expected_reason_code=expected_reason_code,
            expected_effective_at=expected_effective_at,
            evidence_refs=evidence_refs, approval_ref=approval_ref, apply=apply)


# ---- dry run ----

async def test_dry_run_plans_retrospective_event_without_writing(session_factory):
    await _place_active(session_factory)
    res = await _run(session_factory, apply=False,
                     evidence_refs=["snapshot=8fa766f3", "run=605"])
    assert res.action == "would_write" and res.audit_id is None and res.hold_rev == 1
    assert res.planned_payload["source"] == RETRO_SOURCE
    assert res.planned_payload["retrospective"] is True
    assert res.planned_payload["reason_code"] == RC
    assert res.planned_payload["effective_at"] == EFF
    assert res.planned_payload["evidence_refs"] == ["snapshot=8fa766f3", "run=605"]
    assert len(await _retro_audit_rows(session_factory)) == 0  # nothing written


# ---- apply ----

async def test_apply_writes_exactly_one_retrospective_event(session_factory):
    await _place_active(session_factory)
    res = await _run(session_factory, apply=True, evidence_refs=["run=605"])
    assert res.action == "wrote" and res.audit_id is not None
    rows = await _retro_audit_rows(session_factory)
    assert len(rows) == 1
    p = json.loads(rows[0].payload_json)
    assert p["source"] == RETRO_SOURCE and p["retrospective"] is True and p["rev"] == 1


async def test_apply_never_mutates_the_hold_blob(session_factory):
    await _place_active(session_factory)
    before = await _read_raw(session_factory, K_OPERATIONAL_HOLD)
    await _run(session_factory, apply=True)
    after = await _read_raw(session_factory, K_OPERATIONAL_HOLD)
    assert json.dumps(before, sort_keys=True) == json.dumps(after, sort_keys=True)


async def test_second_apply_is_idempotent_noop(session_factory):
    await _place_active(session_factory)
    first = await _run(session_factory, apply=True)
    second = await _run(session_factory, apply=True)
    assert second.action == "already_formalized" and second.audit_id == first.audit_id
    assert len(await _retro_audit_rows(session_factory)) == 1  # no second event


# ---- fail-closed refusals ----

async def test_refuses_when_no_hold(session_factory):
    # a strategy_state row for deployment exists, but no operational_hold
    with pytest.raises(RetroFormalizationRefused):
        await _run(session_factory, apply=True)


async def test_refuses_when_hold_cleared(session_factory):
    p = await _place_active(session_factory)
    await HoldService(session_factory).clear(
        SID, expected_rev=p.record.rev, cleared_at=NOW, cleared_by="user:4")
    with pytest.raises(RetroFormalizationRefused):
        await _run(session_factory, apply=True, expected_rev=1)
    assert len(await _retro_audit_rows(session_factory)) == 0


@pytest.mark.parametrize("kw", [
    {"expected_rev": 99},
    {"expected_reason_code": "SOMETHING_ELSE"},
    {"expected_effective_at": "2020-01-01T00:00:00Z"},
])
async def test_refuses_on_expectation_mismatch(session_factory, kw):
    await _place_active(session_factory)
    with pytest.raises(RetroFormalizationRefused):
        await _run(session_factory, apply=True, **kw)
    assert len(await _retro_audit_rows(session_factory)) == 0  # no audit on refusal


async def test_refuses_fail_closed_on_malformed_hold(session_factory):
    await _seed_raw(session_factory, K_OPERATIONAL_HOLD,
                    {"schema_version": 999, "_rev": 1, "status": "ACTIVE"})
    with pytest.raises(HoldStateInvalid):
        await _run(session_factory, apply=True)
    assert len(await _retro_audit_rows(session_factory)) == 0
