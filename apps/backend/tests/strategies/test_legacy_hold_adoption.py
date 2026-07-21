"""P7 §7-B — adopt a LEGACY operational-hold marker into schema-v1 (ADR 0044).

The one governed migration for a hold that predates the schema: read the legacy marker,
write a schema-v1 ACTIVE hold preserving the legacy content verbatim, emit exactly one
retrospective STRATEGY_HOLD_PLACED. Fail-closed, idempotent, dry-run-capable.
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
    LegacyHoldAdoptionRefused,
    StrategyOnHold,
    adopt_legacy_operational_hold,
    assert_no_active_hold,
    read_hold,
)
from app.strategies.operational_hold import K_OPERATIONAL_HOLD, HoldStateInvalid

SID = 11
RC = "AWAITING_COLD_START_FIX"
PAUSED_AT = "2026-07-20T22:48:22Z"
PLACED_BY = "user:4"
PLACED = "STRATEGY_HOLD_PLACED"

# A faithful shrink of the real acct-4 legacy marker (status PAUSED, no schema_version/_rev).
LEGACY = {
    "status": "PAUSED", "reason_code": RC, "reason": "cold-start trigger gap",
    "paused_at": PAUSED_AT, "deactivation_audit_id": 5733,
    "identifiers": {"strategy_id": 11, "account_id": 4, "closed_run_id": 605},
    "evidence_snapshot_sha256": "8fa766f3deadbeef",
}


def _now() -> datetime:
    return datetime.now(UTC)


async def _seed(session_factory, value: dict) -> None:
    async with session_factory() as session, session.begin():
        session.add(StrategyState(strategy_id=SID, key=K_OPERATIONAL_HOLD, value=value,
                                  updated_at=_now()))


async def _read_raw(session_factory) -> dict | None:
    async with session_factory() as session:
        return (await session.execute(select(StrategyState.value).where(
            StrategyState.strategy_id == SID,
            StrategyState.key == K_OPERATIONAL_HOLD))).scalars().first()


async def _retro_placed_rows(session_factory) -> list[AuditLog]:
    async with session_factory() as session:
        return list((await session.execute(select(AuditLog).where(
            AuditLog.action == PLACED,
            func.json_extract(AuditLog.payload_json, "$.source") == RETRO_SOURCE,
            func.json_extract(AuditLog.payload_json, "$.strategy_id") == SID))).scalars().all())


async def _adopt(session_factory, *, apply, reason_code=RC, paused_at=PAUSED_AT,
                 legacy_status="PAUSED"):
    async with session_factory() as session, session.begin():
        return await adopt_legacy_operational_hold(
            session, strategy_id=SID, expected_reason_code=reason_code,
            expected_paused_at=paused_at, expected_legacy_status=legacy_status,
            placed_by=PLACED_BY, evidence_refs=["snapshot=8fa766f3", "run=605"], apply=apply)


# ---- dry run ----

async def test_dry_run_plans_schema_v1_active_preserving_legacy_without_writing(session_factory):
    await _seed(session_factory, LEGACY)
    res = await _adopt(session_factory, apply=False)
    assert res.action == "would_adopt" and res.audit_id is None
    b = res.planned_blob
    assert b["schema_version"] == 1 and b["_rev"] == 1 and b["status"] == "ACTIVE"
    assert b["reason_code"] == RC and b["effective_at"] == PAUSED_AT
    assert b["source"] == RETRO_SOURCE
    assert b["legacy_marker"] == LEGACY  # full legacy content preserved verbatim
    assert await _read_raw(session_factory) == LEGACY  # nothing written
    assert len(await _retro_placed_rows(session_factory)) == 0


# ---- apply ----

async def test_apply_writes_schema_v1_active_and_one_retro_audit(session_factory):
    await _seed(session_factory, LEGACY)
    res = await _adopt(session_factory, apply=True)
    assert res.action == "adopted" and res.audit_id is not None
    stored = await _read_raw(session_factory)
    assert stored["schema_version"] == 1 and stored["status"] == "ACTIVE" and stored["_rev"] == 1
    assert stored["effective_at"] == PAUSED_AT
    assert stored["legacy_marker"] == LEGACY  # preserved
    rows = await _retro_placed_rows(session_factory)
    assert len(rows) == 1
    p = json.loads(rows[0].payload_json)
    assert p["adopted_from_legacy"] is True and p["retrospective"] is True and p["rev"] == 1


async def test_after_adoption_enforcement_blocks_via_clean_path_and_clear_works(session_factory):
    await _seed(session_factory, LEGACY)
    await _adopt(session_factory, apply=True)
    # read_hold now parses it (schema-v1) and the guard blocks via StrategyOnHold, not Invalid.
    async with session_factory() as session:
        rec = await read_hold(session, SID)
        assert rec is not None and rec.is_active and rec.rev == 1
        with pytest.raises(StrategyOnHold):
            await assert_no_active_hold(session, SID)
    # and the adopted hold is now clearable via the standard service.
    r = await HoldService(session_factory).clear(
        SID, expected_rev=1, cleared_at=_now().isoformat(), cleared_by=PLACED_BY)
    assert r.changed is True and r.record.status.value == "CLEARED"


async def test_second_apply_is_idempotent_noop(session_factory):
    await _seed(session_factory, LEGACY)
    first = await _adopt(session_factory, apply=True)
    second = await _adopt(session_factory, apply=True)
    assert first.action == "adopted" and second.action == "already_adopted"
    assert second.audit_id is None
    assert len(await _retro_placed_rows(session_factory)) == 1  # no second event


# ---- fail-closed refusals ----

async def test_refuses_when_marker_absent(session_factory):
    with pytest.raises(LegacyHoldAdoptionRefused):
        await _adopt(session_factory, apply=True)


async def test_refuses_when_already_schema_v1_non_adopted(session_factory):
    # a normal schema-v1 hold (placed via the service) must NOT be adopted.
    await HoldService(session_factory).place(
        SID, reason_code=RC, reason="x", effective_at=PAUSED_AT,
        placed_at=_now().isoformat(), placed_by=PLACED_BY)
    with pytest.raises(LegacyHoldAdoptionRefused):
        await _adopt(session_factory, apply=True)


@pytest.mark.parametrize("kw", [
    {"reason_code": "SOMETHING_ELSE"},
    {"paused_at": "2020-01-01T00:00:00Z"},
    {"legacy_status": "ACTIVE"},
])
async def test_refuses_on_legacy_field_mismatch(session_factory, kw):
    await _seed(session_factory, LEGACY)
    with pytest.raises(LegacyHoldAdoptionRefused):
        await _adopt(session_factory, apply=True, **kw)
    assert await _read_raw(session_factory) == LEGACY  # untouched
    assert len(await _retro_placed_rows(session_factory)) == 0  # no audit on refusal


async def test_legacy_marker_stays_unreadable_until_adopted(session_factory):
    """Before adoption the marker is fail-closed unreadable (blocks activation)."""
    await _seed(session_factory, LEGACY)
    async with session_factory() as session:
        with pytest.raises(HoldStateInvalid):
            await read_hold(session, SID)  # schema_version absent -> fail closed


# ---- CAS: concurrent marker movement (Blocker 1) ----

async def test_concurrent_marker_change_fails_the_cas(session_factory, monkeypatch):
    """A writer that changes the marker AFTER adoption read it but BEFORE the write must
    make the value-CAS miss: no overwrite, no audit. Simulated by adoption reading the
    STALE original while the DB already holds a concurrently-modified marker."""
    import app.strategies.hold_service as hs

    modified = {**LEGACY, "reason": "CONCURRENTLY MODIFIED BY ANOTHER ACTOR"}
    await _seed(session_factory, modified)  # the DB's CURRENT value

    async def _stale(_session, _sid):  # adoption "reads" the pre-change marker
        return dict(LEGACY)
    monkeypatch.setattr(hs, "_read_raw_hold", _stale)

    with pytest.raises(LegacyHoldAdoptionRefused):
        await _adopt(session_factory, apply=True)
    assert await _read_raw(session_factory) == modified  # concurrent value UNTOUCHED
    assert len(await _retro_placed_rows(session_factory)) == 0  # NO audit written


# ---- idempotency must validate the adopted state (Blocker 2) ----

def _adopted_blob(**over) -> dict:
    b = {
        "schema_version": 1, "_rev": 1, "status": "ACTIVE", "reason_code": RC,
        "reason": "cold-start trigger gap", "effective_at": PAUSED_AT,
        "placed_at": "2026-07-21T23:00:00Z", "placed_by": PLACED_BY,
        "evidence_refs": ["snapshot=8fa766f3"], "approval_ref": None,
        "source": RETRO_SOURCE, "cleared_at": None, "cleared_by": None,
        "legacy_marker": LEGACY,
    }
    b.update(over)
    return b


async def test_already_adopted_active_is_idempotent_noop(session_factory):
    await _seed(session_factory, _adopted_blob())
    res = await _adopt(session_factory, apply=True)
    assert res.action == "already_adopted" and res.audit_id is None
    assert len(await _retro_placed_rows(session_factory)) == 0


async def test_already_adopted_then_cleared_is_reported_not_active(session_factory):
    await _seed(session_factory, _adopted_blob(status="CLEARED", _rev=2,
                                               cleared_at="2026-08-01T00:00:00Z", cleared_by=PLACED_BY))
    res = await _adopt(session_factory, apply=True)
    assert res.action == "already_adopted_and_cleared" and res.audit_id is None
    assert len(await _retro_placed_rows(session_factory)) == 0


@pytest.mark.parametrize("bad", [
    _adopted_blob(source="SOMETHING_ELSE"),                       # non-retrospective source
    _adopted_blob(reason_code="OTHER_RC"),                        # different reason_code
    _adopted_blob(effective_at="2020-01-01T00:00:00Z"),          # different effective_at
    _adopted_blob(legacy_marker={**LEGACY, "paused_at": "2020-01-01T00:00:00Z"}),  # marker mismatch
    _adopted_blob(legacy_marker={**LEGACY, "reason_code": "OTHER"}),
    {"schema_version": 1, "_rev": 1, "status": "ACTIVE", "reason_code": RC,
     "effective_at": PAUSED_AT, "source": RETRO_SOURCE},         # schema-v1 with NO legacy_marker
])
async def test_refuses_schema_v1_that_is_not_this_adoption(session_factory, bad):
    await _seed(session_factory, bad)
    with pytest.raises(LegacyHoldAdoptionRefused):
        await _adopt(session_factory, apply=True)
    assert await _read_raw(session_factory) == bad  # untouched
    assert len(await _retro_placed_rows(session_factory)) == 0  # no audit
