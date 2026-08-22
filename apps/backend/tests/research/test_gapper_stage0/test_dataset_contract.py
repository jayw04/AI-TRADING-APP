"""§3.1 dataset contract: sentinel default, completeness, JSON + sha identity."""

from __future__ import annotations

import pytest

from app.research.gapper_stage0.dataset_contract import (
    TARGET_EVENT_DAYS_MINIMUM,
    TARGET_EVENT_DAYS_PREFERRED,
    UNSET_OWNER_DECISION,
    DatasetContract,
)


def _complete() -> DatasetContract:
    return DatasetContract(
        date_range=("2024-01-02", "2026-06-30"),
        target_event_days=500,
        source_vendor="OWNER-DECIDED-VENDOR",
        survivorship_rules="point-in-time universe, delisted names retained",
        corporate_action_handling="split/dividend adjusted per vendor closeadj",
        pit_rules="features strictly date < asof",
        min_analyzable_sample=100,
    )


def test_source_vendor_defaults_to_owner_decision_sentinel() -> None:
    c = DatasetContract()
    assert c.source_vendor == UNSET_OWNER_DECISION
    assert not c.is_complete()
    assert "source_vendor" in c.unset_terms()


def test_default_contract_lists_every_unset_term() -> None:
    unset = DatasetContract().unset_terms()
    for term in (
        "date_range",
        "source_vendor",
        "survivorship_rules",
        "corporate_action_handling",
        "pit_rules",
        "min_analyzable_sample",
    ):
        assert term in unset


def test_partial_contract_is_incomplete() -> None:
    c = DatasetContract(date_range=("2024-01-02", "2026-06-30"), source_vendor="X")
    assert not c.is_complete()


def test_complete_contract() -> None:
    c = _complete()
    assert c.is_complete()
    assert c.unset_terms() == []


def test_target_event_days_floor_and_preference() -> None:
    assert TARGET_EVENT_DAYS_MINIMUM == 250
    assert TARGET_EVENT_DAYS_PREFERRED == 500
    assert DatasetContract().target_event_days == 250
    # A below-floor target is an unset/invalid term, not a quiet relaxation.
    low = DatasetContract(target_event_days=40)
    assert "target_event_days" in low.unset_terms()


def test_frozen() -> None:
    with pytest.raises(AttributeError):
        DatasetContract().source_vendor = "IEX"  # type: ignore[misc]


def test_json_round_trip_and_sha() -> None:
    c = _complete()
    again = DatasetContract.from_json(c.to_json())
    assert again == c
    assert again.sha256() == c.sha256()
    # Any term change changes the identity hash.
    changed = DatasetContract.from_dict({**c.to_dict(), "source_vendor": "OTHER"})
    assert changed.sha256() != c.sha256()


def test_from_dict_rejects_bad_range_and_schema() -> None:
    with pytest.raises(ValueError, match="date_range"):
        DatasetContract.from_dict({"date_range": ["2024-01-02"]})
    with pytest.raises(ValueError, match="schema"):
        DatasetContract.from_dict({"schema": "something/else"})
