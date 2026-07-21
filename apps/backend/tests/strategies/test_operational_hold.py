"""P7 §7-B — operational hold record schema + FAIL-CLOSED validation (pure)."""

from __future__ import annotations

import pytest

from app.strategies.operational_hold import (
    HOLD_SCHEMA_VERSION,
    HoldStateInvalid,
    HoldStatus,
    StrategyOnHold,
    load_hold_record,
)


def _hold(**over) -> dict:
    base = {
        "schema_version": HOLD_SCHEMA_VERSION, "_rev": 1, "status": "ACTIVE",
        "reason_code": "AWAITING_COLD_START_FIX", "reason": "cold-start repair required",
        "effective_at": "2026-07-20T22:48:22Z", "placed_at": "2026-07-21T00:00:00Z",
        "placed_by": "user:4", "evidence_refs": [], "approval_ref": None,
    }
    base.update(over)
    return base


def test_absent_row_is_no_hold():
    assert load_hold_record(None) is None


def test_non_dict_is_invalid():
    with pytest.raises(HoldStateInvalid):
        load_hold_record("nope")  # type: ignore[arg-type]


def test_unsupported_schema_version_is_invalid():
    with pytest.raises(HoldStateInvalid):
        load_hold_record(_hold(schema_version=999))


def test_missing_rev_is_invalid():
    d = _hold()
    del d["_rev"]
    with pytest.raises(HoldStateInvalid):
        load_hold_record(d)


def test_bad_status_is_invalid():
    with pytest.raises(HoldStateInvalid):
        load_hold_record(_hold(status="PAUSEDish"))


@pytest.mark.parametrize("field", ["reason_code", "effective_at", "placed_at"])
def test_missing_required_field_is_invalid(field):
    d = _hold()
    d[field] = ""
    with pytest.raises(HoldStateInvalid):
        load_hold_record(d)


def test_valid_active_hold_is_active():
    h = load_hold_record(_hold(status="ACTIVE"))
    assert h is not None and h.is_active is True and h.status == HoldStatus.ACTIVE
    assert h.reason_code == "AWAITING_COLD_START_FIX"


def test_valid_cleared_hold_is_not_active():
    h = load_hold_record(_hold(status="CLEARED", cleared_at="2026-08-01T00:00:00Z",
                               cleared_by="user:4"))
    assert h is not None and h.is_active is False


def test_round_trip_is_stable():
    h = load_hold_record(_hold())
    assert load_hold_record(h.to_dict()).to_dict() == h.to_dict()


def test_strategy_on_hold_carries_context():
    exc = StrategyOnHold(strategy_id=11, reason_code="AWAITING_COLD_START_FIX", rev=1)
    assert exc.strategy_id == 11 and exc.reason_code == "AWAITING_COLD_START_FIX" and exc.rev == 1
    assert "11" in str(exc) and "AWAITING_COLD_START_FIX" in str(exc)
