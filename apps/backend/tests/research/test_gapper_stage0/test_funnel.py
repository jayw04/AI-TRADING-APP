"""Funnel record + the unexplained-collapse detector (the v1 defect, first-class)."""

from __future__ import annotations

import pytest

from app.research.gapper_stage0.funnel import (
    STAGE_COVERAGE,
    STAGE_ELIGIBILITY,
    STAGE_TRADABILITY,
    Exclusion,
    build_funnel_record,
)


def _record(exclusions: list[Exclusion], panel: int = 8, eligible: int = 5):
    return build_funnel_record(
        asof="2026-08-14",
        gappers_in=20,
        store_covered=12,
        eligible_panel=panel,
        eligible_count=eligible,
        candidate_count=min(eligible, 5),
        exclusions=exclusions,
    )


def test_fully_explained_collapse_is_valid() -> None:
    exc = [
        Exclusion("AAA", STAGE_ELIGIBILITY, "price_below_min"),
        Exclusion("BBB", STAGE_ELIGIBILITY, "premarket_volume_below_min"),
        Exclusion("CCC", STAGE_ELIGIBILITY, "gap_below_min"),
    ]
    r = _record(exc, panel=8, eligible=5)
    assert r.collapse_unexplained == 0
    assert r.valid is True


def test_unexplained_collapse_is_a_first_class_hard_failure() -> None:
    # panel 8 → eligible 5 with only ONE reason-coded eligibility exclusion:
    # 2 names vanished without a rule — the exact v1 defect (16/42 dates).
    r = _record([Exclusion("AAA", STAGE_ELIGIBILITY, "price_below_min")], panel=8, eligible=5)
    assert r.collapse_unexplained == 2
    assert r.valid is False
    d = r.to_dict()
    assert d["collapse_unexplained"] == 2
    assert d["valid"] is False


def test_over_explained_collapse_is_also_invalid() -> None:
    exc = [
        Exclusion("AAA", STAGE_ELIGIBILITY, "a"),
        Exclusion("BBB", STAGE_ELIGIBILITY, "b"),
    ]
    r = _record(exc, panel=6, eligible=5)  # only 1 name collapsed, 2 "explained"
    assert r.collapse_unexplained == -1
    assert r.valid is False


def test_other_stage_exclusions_do_not_explain_the_eligibility_collapse() -> None:
    exc = [
        Exclusion("AAA", STAGE_TRADABILITY, "security_type_excluded"),
        Exclusion("BBB", STAGE_COVERAGE, "no_prior_close"),
    ]
    r = _record(exc, panel=6, eligible=5)
    assert r.collapse_unexplained == 1
    assert r.valid is False


def test_exclusion_requires_known_stage_and_reason() -> None:
    with pytest.raises(ValueError, match="stage"):
        Exclusion("AAA", "vibes", "x")
    with pytest.raises(ValueError, match="reason"):
        Exclusion("AAA", STAGE_ELIGIBILITY, "")
    with pytest.raises(ValueError, match="symbol"):
        Exclusion(" ", STAGE_ELIGIBILITY, "x")


def test_negative_counters_rejected() -> None:
    with pytest.raises(ValueError, match="eligible_panel"):
        build_funnel_record(
            asof="2026-08-14",
            gappers_in=1,
            store_covered=1,
            eligible_panel=-1,
            eligible_count=0,
            candidate_count=0,
        )


def test_v1_counter_names_preserved_for_comparability() -> None:
    d = _record([], panel=5, eligible=5).to_dict()
    for name in (
        "gappers_in",
        "store_covered",
        "eligible_panel",
        "eligible_count",
        "candidate_count",
    ):
        assert name in d
