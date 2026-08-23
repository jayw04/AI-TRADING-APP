"""DISC-001 Phase-1 CandidateFamilyEngine — frozen gates, fail-closed, badge precedence."""

from __future__ import annotations

from app.research.disc001.engine import (
    assemble_all,
    mom_near_eligible,
    mom_near_gate_observations,
    oversold_eligible,
    oversold_gate_observations,
    screen_gap,
    screen_mom_core,
    screen_mom_near,
    screen_oversold,
    shared_eligible,
    weakest_status,
)
from app.research.disc001.features import GapRow, MomCoreRow, SymbolFeatures
from app.research.disc001.spec import (
    LEDGER_ENTRY_0,
    MAX_PER_FAMILY,
    SCREEN_VERSION,
    EvidenceStatus,
    FamilyId,
)


def _feat(**over: object) -> SymbolFeatures:
    base: dict[str, object] = dict(
        symbol="GOOD",
        name="Good Inc",
        sector="Technology",
        category="Domestic Common Stock",
        close=50.0,
        sma200=40.0,
        rsi14=24.0,
        rsi14_prev=28.0,
        ret_5d=-0.10,
        ret_20d=0.08,
        ret_60d=0.02,
        rs_20_vs_spy=0.04,
        rs_60_vs_spy=0.01,
        rs_accel=0.03,
        dist_52w=0.05,
        high_52w=52.6,
        adv20=30_000_000.0,
        rvol20=2.0,
        volume_rising_20d=True,
        market_cap=2_000_000_000.0,
    )
    base.update(over)
    return SymbolFeatures(**base)  # type: ignore[arg-type]


def test_ledger_entry_0_is_product_motivated():
    assert LEDGER_ENTRY_0["entry"] == 0
    assert "product-motivated" in str(LEDGER_ENTRY_0["motivation"])
    assert LEDGER_ENTRY_0["screen_version"] == SCREEN_VERSION


def test_shared_rejects_etf_thin_and_cheap():
    assert shared_eligible(_feat())
    assert not shared_eligible(_feat(category="ETF"))
    assert not shared_eligible(_feat(close=9.0))
    assert not shared_eligible(_feat(adv20=1_000_000.0))
    assert not shared_eligible(_feat(market_cap=500_000_000.0))
    assert not shared_eligible(_feat(market_cap=None))


def test_oversold_requires_rsi_trend_and_crash_or_persist():
    assert oversold_eligible(_feat())
    assert not oversold_eligible(_feat(rsi14=31.0))
    assert not oversold_eligible(_feat(close=39.0, sma200=40.0))
    assert not oversold_eligible(_feat(ret_5d=-0.01, rsi14_prev=45.0))
    assert oversold_eligible(_feat(ret_5d=-0.02, rsi14=24.0, rsi14_prev=35.0))


def test_oversold_empty_family_is_valid():
    result = screen_oversold(
        (_feat(rsi14=55.0),),
        available=True,
        unavailable_reason=None,
        price_source="sharadar.sep",
    )
    assert result.available
    assert result.empty
    assert result.items == ()


def test_oversold_unavailable_is_not_a_partial_screen():
    result = screen_oversold(
        (_feat(),),
        available=False,
        unavailable_reason="SEP as-of 2026-08-15, expected 2026-08-18",
        price_source="sharadar.sep",
    )
    assert not result.available
    assert result.items == ()
    assert "SEP as-of" in (result.unavailable_reason or "")


def test_oversold_sorts_lowest_rsi_then_adv():
    low = _feat(symbol="LOW", rsi14=18.0, adv20=20_000_000.0)
    mid = _feat(symbol="MID", rsi14=22.0, adv20=80_000_000.0)
    tie_a = _feat(symbol="AAA", rsi14=20.0, adv20=40_000_000.0)
    tie_b = _feat(symbol="BBB", rsi14=20.0, adv20=90_000_000.0)
    result = screen_oversold(
        (mid, low, tie_a, tie_b),
        available=True,
        unavailable_reason=None,
        price_source="sharadar.sep",
    )
    assert [c.symbol for c in result.items] == ["LOW", "BBB", "AAA", "MID"]


def test_mom_near_drops_mom_core_and_requires_continuation():
    core = frozenset({"CORE"})
    assert mom_near_eligible(_feat(symbol="NEW"), core)
    assert not mom_near_eligible(_feat(symbol="CORE"), core)
    assert not mom_near_eligible(_feat(dist_52w=0.20), core)
    assert not mom_near_eligible(_feat(dist_52w=-0.01), core)
    assert not mom_near_eligible(_feat(rs_accel=-0.01), core)
    assert not mom_near_eligible(_feat(rs_20_vs_spy=0.0), core)
    assert not mom_near_eligible(_feat(rs_20_vs_spy=-0.01), core)
    assert not mom_near_eligible(_feat(rvol20=1.0, volume_rising_20d=False), core)
    assert mom_near_eligible(_feat(rvol20=1.0, volume_rising_20d=True), core)
    assert mom_near_eligible(_feat(rvol20=1.6, volume_rising_20d=False), core)


def test_halt_ca_gate_is_explicitly_deferred():
    from app.research.disc001.spec import HALT_CA_GATE, LEDGER_ENTRY_0

    assert HALT_CA_GATE == "deferred_phase1b"
    frozen = LEDGER_ENTRY_0["frozen_conditions"]
    assert frozen["halt_ca_gate"] == "deferred_phase1b"
    assert frozen["oversold_crash_filter"]
    assert frozen["mom_near_rs_20_vs_spy_min"] == 0.0
    assert frozen["mom_near_drop_mom_core"] is True
    assert frozen["snapshot_max_files"] == 90


def test_mom_near_sorts_by_accel_then_rvol():
    a = _feat(symbol="A", rs_accel=0.10, rvol20=1.6)
    b = _feat(symbol="B", rs_accel=0.20, rvol20=1.6)
    c = _feat(symbol="C", rs_accel=0.20, rvol20=3.0)
    result = screen_mom_near(
        (a, b, c),
        frozenset(),
        available=True,
        unavailable_reason=None,
        price_source="sharadar.sep",
    )
    assert [x.symbol for x in result.items] == ["C", "B", "A"]


def test_gap_keeps_file_rank():
    rows = (
        GapRow(rank=2, symbol="BBB", gap_pct=3.0),
        GapRow(rank=1, symbol="AAA", gap_pct=5.0),
    )
    result = screen_gap(
        rows, available=True, unavailable_reason=None, price_source="scan.premarket"
    )
    assert [c.symbol for c in result.items] == ["AAA", "BBB"]
    assert result.items[0].status is EvidenceStatus.BACKTEST_PENDING


def test_mom_core_badge_is_source_not_stock_validated():
    rows = (MomCoreRow(rank=1, symbol="NVDA", score=1.2),)
    result = screen_mom_core(
        rows, available=True, unavailable_reason=None, price_source="sharadar.sep"
    )
    assert result.items[0].status is EvidenceStatus.SOURCE_MOM001
    assert "this card is still Watch-only" in result.items[0].why


def test_weakest_badge_when_name_in_mom_core_and_oversold():
    oversold = screen_oversold(
        (_feat(symbol="NVDA"),),
        available=True,
        unavailable_reason=None,
        price_source="sharadar.sep",
    )
    core = screen_mom_core(
        (MomCoreRow(rank=1, symbol="NVDA"),),
        available=True,
        unavailable_reason=None,
        price_source="sharadar.sep",
    )
    merged = assemble_all({FamilyId.OVERSOLD: oversold, FamilyId.MOM_CORE: core})
    assert len(merged) == 1
    assert merged[0].status is EvidenceStatus.WATCH
    assert FamilyId.OVERSOLD in merged[0].family_ids
    assert FamilyId.MOM_CORE in merged[0].family_ids


def test_unavailable_family_excluded_from_all_count():
    oversold = screen_oversold(
        (_feat(),),
        available=False,
        unavailable_reason="stale",
        price_source="sharadar.sep",
    )
    gap = screen_gap(
        (GapRow(rank=1, symbol="XYZ", gap_pct=4.0),),
        available=True,
        unavailable_reason=None,
        price_source="scan.premarket",
    )
    merged = assemble_all({FamilyId.OVERSOLD: oversold, FamilyId.GAP: gap})
    assert [c.symbol for c in merged] == ["XYZ"]


def test_family_capped_at_fifteen():
    feats = tuple(_feat(symbol=f"S{i:02d}", rsi14=10.0 + i * 0.1) for i in range(20))
    result = screen_oversold(
        feats, available=True, unavailable_reason=None, price_source="sharadar.sep"
    )
    assert len(result.items) == MAX_PER_FAMILY


def test_weakest_status_ordering():
    assert (
        weakest_status([EvidenceStatus.SOURCE_MOM001, EvidenceStatus.WATCH]) is EvidenceStatus.WATCH
    )
    assert (
        weakest_status([EvidenceStatus.BACKTEST_PENDING, EvidenceStatus.WATCH])
        is EvidenceStatus.WATCH
    )


def test_admission_eligibility_is_observation_conjunction_not_a_second_formula():
    recovered = _feat(rsi14=31.0)
    assert oversold_eligible(recovered) is all(
        obs.passed for obs in oversold_gate_observations(recovered)
    )
    core = frozenset({"CORE"})
    dropped = _feat(symbol="CORE")
    assert mom_near_eligible(dropped, core) is all(
        obs.passed for obs in mom_near_gate_observations(dropped, core)
    )
