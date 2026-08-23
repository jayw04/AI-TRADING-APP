"""DISC-001 adapter fail-closed behavior without a factor store."""

from __future__ import annotations

from datetime import date

from app.research.disc001.adapter import build_watchlist
from app.research.disc001.spec import FamilyId


def test_missing_store_marks_sep_families_unavailable_gap_can_still_run():
    payload = {
        "gappers": [{"rank": 1, "symbol": "ABC", "gap_pct": 4.2, "catalyst": "news"}],
        "stale": False,
    }
    result = build_watchlist(None, gappers_payload=payload, today=date(2026, 8, 19))
    assert not result.families[FamilyId.OVERSOLD].available
    assert not result.families[FamilyId.MOM_NEAR].available
    assert not result.families[FamilyId.MOM_CORE].available
    assert result.families[FamilyId.GAP].available
    assert result.families[FamilyId.GAP].items[0].symbol == "ABC"
    assert result.all_items[0].symbol == "ABC"


def test_missing_gappers_marks_gap_unavailable_not_empty_valid():
    result = build_watchlist(None, gappers_payload=None, today=date(2026, 8, 19))
    assert not result.families[FamilyId.GAP].available
    assert result.families[FamilyId.GAP].items == ()


def test_empty_gappers_list_is_valid_empty_family():
    result = build_watchlist(None, gappers_payload={"gappers": []}, today=date(2026, 8, 19))
    assert result.families[FamilyId.GAP].available
    assert result.families[FamilyId.GAP].empty
