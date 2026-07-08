"""EAD reference-only guardrail — rejected EAD event labels stay out of ranking/sizing/order-path.

Guard behavior + registry sync (the mapped programs really are 'rejected') + CI-script wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.altdata.reference_only import (
    REFERENCE_ONLY_EVENT_TYPES,
    REFERENCE_ONLY_PROGRAMS,
    ReferenceOnlyViolation,
    assert_usable_for_ranking,
    is_reference_only,
    partition_reference_only,
)


def test_rejected_event_types_are_reference_only():
    for et in ("insider_buy", "gov_contract_award", "congress_trade", "lobby_spike"):
        assert is_reference_only(et)
    assert not is_reference_only("mom_score")


def test_assert_usable_for_ranking_blocks_reference_only():
    for et in REFERENCE_ONLY_EVENT_TYPES:
        with pytest.raises(ReferenceOnlyViolation):
            assert_usable_for_ranking(et)
    assert_usable_for_ranking("some_validated_signal")  # non-reference-only → no raise


def test_partition_separates_usable_from_reference_only():
    usable, ref = partition_reference_only(["mom_score", "lobby_spike", "congress_trade"])
    assert usable == ["mom_score"]
    assert set(ref) == {"lobby_spike", "congress_trade"}


def test_reference_only_programs_are_rejected_in_registry():
    """Sync: every reference-only event type maps to a program that is actually 'rejected'. If a
    program is ever un-rejected (a new pre-registered hypothesis proved value), this flags that the
    event type must leave REFERENCE_ONLY_PROGRAMS before it can feed ranking."""
    from app.research.programs import RESEARCH_PROGRAMS

    status_by_id = {p.id: p.status for p in RESEARCH_PROGRAMS}
    for event_type, program_id in REFERENCE_ONLY_PROGRAMS.items():
        assert status_by_id.get(program_id) == "rejected", (
            f"{event_type} → {program_id} is {status_by_id.get(program_id)!r}, not 'rejected'"
        )


def test_ci_invariant_script_wired_to_the_module():
    """The 15th CI invariant derives its pattern from this module (single source of truth)."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "check_reference_only_invariant.sh"
    assert script.exists()
    text = script.read_text()
    assert "REFERENCE_ONLY_EVENT_TYPES" in text and "app.altdata.reference_only" in text
