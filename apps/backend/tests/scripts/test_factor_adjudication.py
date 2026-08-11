"""The shared adjudication rules — the single source of truth both the refresh verifier
and the readiness watchdog now consume.

The property under test is the one that failed in production on 2026-08-11: the same
evidence artifact, store and universe must produce ONE classification and ONE coverage
figure, and that figure must be the one the gate compares against its threshold.

Every case that GRANTS an attribution has a sibling proving the attribution cannot be
widened into a suppressed check. That pairing is deliberate — the failure mode this
module exists to remove is a real outage being excused, and it is strictly worse than
the over-strictness it replaces.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_MODULE = _REPO_ROOT / "apps" / "backend" / "scripts" / "factor_adjudication.py"

pytestmark = pytest.mark.skipif(not _MODULE.exists(), reason="factor_adjudication.py absent")


def _load():
    spec = importlib.util.spec_from_file_location("factor_adjudication", _MODULE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fa = _load()

FRONTIER = datetime.date(2026, 8, 10)
CUTOFF = FRONTIER - datetime.timedelta(days=4)  # 2026-08-06
D = datetime.date


def _evidence(symbol, *, claim, rows=0, requested=True, status="ok", corr=None):
    rec = {
        "symbol": symbol,
        "expected_classification": claim,
        "requested": requested,
        "request_status": status,
        "provider_rows_after_live_frontier": rows,
    }
    if corr is not None:
        rec["corroboration"] = corr
    return rec


CONTROL_CURRENT = D(2026, 8, 11)


def _corr(last_date, *, control="AAPL", control_last=CONTROL_CURRENT, source="alpaca"):
    return {
        "source": source,
        "control_symbol": control,
        "control_last_date": control_last.isoformat(),
        "last_date": last_date.isoformat() if last_date else None,
    }


def _classify(symbol, *, live, stage, ev, held=0.0, orders=0, registered=()):
    return fa.classify_stale_symbol(
        symbol,
        live_last=live,
        stage_last=stage,
        cutoff=CUTOFF,
        evidence=ev,
        held_qty=held,
        open_orders=orders,
        registered_in=registered,
    )


# ------------------------------------------------------- case 1: not covered by provider


def test_structurally_uncovered_but_live_elsewhere_is_provider_not_covered():
    """An ETF under a Core US Equities plan: absent from the provider entirely, trading
    normally everywhere else. Held and registered, which is fine BECAUSE it is alive."""
    verdict, reason = _classify(
        "UUP",
        live=None,
        stage=None,
        ev=_evidence("UUP", claim=fa.PROVIDER_NOT_COVERED, corr=_corr(D(2026, 8, 11))),
        held=138.157392,
        registered=("9:IDLE",),
    )
    assert verdict == fa.PROVIDER_NOT_COVERED
    assert "outside provider coverage" in reason


def test_uncovered_name_that_is_NOT_live_elsewhere_is_refused():
    """The sibling. Without a current alternate source the same shape is unverifiable —
    a symbol with no history anywhere cannot be written off."""
    verdict, reason = _classify(
        "UUP",
        live=None,
        stage=None,
        ev=_evidence("UUP", claim=fa.PROVIDER_NOT_COVERED, corr=_corr(None)),
        held=0.0,
    )
    assert verdict == fa.FAILED_OR_UNEXPLAINED
    assert "unverifiable" in reason


# ---------------------------------------------------------- case 2: provider exhausted


def test_ceased_trading_everywhere_is_provider_exhausted():
    """SATS/EchoStar: stopped 2026-06-12, dead in both sources, not held, not registered."""
    verdict, reason = _classify(
        "SATS",
        live=D(2026, 6, 12),
        stage=D(2026, 6, 12),
        ev=_evidence("SATS", claim=fa.PROVIDER_EXHAUSTED, corr=_corr(None)),
    )
    assert verdict == fa.PROVIDER_EXHAUSTED
    assert "ceased trading" in reason


def test_a_dead_name_that_is_still_HELD_is_refused():
    """The sibling. A held position needs a continuing valuation and an exit path; a
    name with no live price source cannot be quietly written off while we own it."""
    verdict, reason = _classify(
        "SATS",
        live=D(2026, 6, 12),
        stage=D(2026, 6, 12),
        ev=_evidence("SATS", claim=fa.PROVIDER_EXHAUSTED, corr=_corr(None)),
        held=100.0,
    )
    assert verdict == fa.FAILED_OR_UNEXPLAINED
    assert "no proven alternate price source" in reason


def test_a_dead_name_still_REGISTERED_by_a_strategy_is_refused():
    verdict, reason = _classify(
        "SATS",
        live=D(2026, 6, 12),
        stage=D(2026, 6, 12),
        ev=_evidence("SATS", claim=fa.PROVIDER_EXHAUSTED, corr=_corr(None)),
        registered=("7:PAPER",),
    )
    assert verdict == fa.FAILED_OR_UNEXPLAINED
    assert "no alternate source" in reason


# ------------------------------------------------- case 3: genuinely stale, unexplained


def test_stale_with_no_evidence_at_all_is_unexplained():
    verdict, reason = _classify("ZZZZ", live=D(2026, 7, 1), stage=D(2026, 7, 1), ev=None)
    assert verdict == fa.FAILED_OR_UNEXPLAINED
    assert reason == "no exhaustion evidence supplied"


def test_provider_stopped_while_the_instrument_kept_trading_is_a_coverage_regression():
    """Not exhaustion — the provider dropped a live name. Deserves a look, not a pass."""
    verdict, reason = _classify(
        "EA",
        live=D(2026, 8, 5),
        stage=D(2026, 8, 5),
        ev=_evidence("EA", claim=fa.PROVIDER_EXHAUSTED, corr=_corr(D(2026, 8, 11))),
    )
    assert verdict == fa.FAILED_OR_UNEXPLAINED
    assert "coverage regression, not exhaustion" in reason


def test_provider_returned_newer_rows_means_ingestion_missed_them():
    verdict, reason = _classify(
        "ZZZZ",
        live=D(2026, 7, 1),
        stage=D(2026, 7, 1),
        ev=_evidence("ZZZZ", claim=fa.PROVIDER_EXHAUSTED, rows=14, corr=_corr(None)),
    )
    assert verdict == fa.FAILED_OR_UNEXPLAINED
    assert "ingestion missed them" in reason


def test_a_stale_corroboration_control_proves_the_alternate_path_is_broken():
    """During an outage of the corroborating source EVERY symbol would look attributable.
    The liveness control is what stops one outage writing off the whole pool."""
    verdict, reason = _classify(
        "SATS",
        live=D(2026, 6, 12),
        stage=D(2026, 6, 12),
        ev=_evidence(
            "SATS",
            claim=fa.PROVIDER_EXHAUSTED,
            corr=_corr(None, control_last=D(2026, 7, 1)),
        ),
    )
    assert verdict == fa.FAILED_OR_UNEXPLAINED
    assert "alternate source unproven" in reason


# --------------------------------------------- case 4: malformed / expired / absent evidence


def test_absent_evidence_attributes_nothing(tmp_path):
    by_symbol, note, status = fa.load_evidence(tmp_path / "nope.json")
    assert by_symbol == {}
    assert "ABSENT" in note
    assert status == "absent"


def test_malformed_evidence_attributes_nothing(tmp_path):
    p = tmp_path / "evidence.json"
    p.write_text("{not json at all", encoding="utf-8")
    by_symbol, note, status = fa.load_evidence(p)
    assert by_symbol == {}
    assert "UNREADABLE" in note
    assert status == "unreadable"


def test_evidence_without_a_symbols_list_attributes_nothing(tmp_path):
    p = tmp_path / "evidence.json"
    p.write_text(json.dumps({"generated_at_utc": "2026-08-11T00:00:00Z"}), encoding="utf-8")
    by_symbol, note, status = fa.load_evidence(p)
    assert by_symbol == {}
    assert "MALFORMED" in note
    assert status == "malformed"


def test_a_record_claiming_an_unrecognised_classification_is_dropped(tmp_path):
    """An unknown label must not become a silent exemption — the denylist-vs-allowlist
    lesson from the executor's artifact_status guard, applied here."""
    p = tmp_path / "evidence.json"
    p.write_text(
        json.dumps(
            {
                "symbols": [
                    {"symbol": "AAA", "expected_classification": "PROBABLY_FINE"},
                    {"symbol": "BBB", "expected_classification": "PROVIDER_EXHAUSTED"},
                ]
            }
        ),
        encoding="utf-8",
    )
    by_symbol, _, _ = fa.load_evidence(p)
    assert set(by_symbol) == {"BBB"}


# ----------------------------------------------------------- case 5: frontier mismatch


def test_frontier_mismatch_is_unexplained():
    """The 2026-08-11 production failure: a point-in-time adjudication pinned to an older
    frontier cannot vouch for dates after it."""
    verdict, reason = _classify(
        "DBC",
        live=D(2026, 8, 4),
        stage=D(2026, 8, 5),
        ev=_evidence("DBC", claim=fa.PROVIDER_NOT_COVERED, corr=_corr(D(2026, 8, 11))),
    )
    assert verdict == fa.FAILED_OR_UNEXPLAINED
    assert "staging frontier" in reason and "!= live" in reason


def test_a_single_store_caller_passes_the_same_frontier_for_both():
    """The watchdog has no staging copy. Passing live for both makes the equality rule
    hold trivially, which is correct: there is no pending swap to disprove."""
    verdict, _ = _classify(
        "UUP",
        live=None,
        stage=None,
        ev=_evidence("UUP", claim=fa.PROVIDER_NOT_COVERED, corr=_corr(D(2026, 8, 11))),
    )
    assert verdict == fa.PROVIDER_NOT_COVERED


# ------------------------------------------------------------- the gating coverage rule


def _production_universe():
    """The real 2026-08-11 shape: 510 names, 9 cross-asset ETFs absent from the provider
    entirely, EA stopped 08-05 and SATS 06-12, everything else fresh."""
    etfs = ["SPY", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "UUP", "KMLM"]
    dead = ["EA", "SATS"]
    fresh = [f"FRESH{i:03d}" for i in range(510 - len(etfs) - len(dead))]
    universe = sorted(fresh + etfs + dead)
    non_fresh = sorted(etfs + dead)
    stage = {s: FRONTIER for s in fresh}
    live = dict(stage)
    for s in etfs:  # absent from the provider in both stores
        stage[s] = None
        live[s] = None
    stage["EA"] = live["EA"] = D(2026, 8, 5)
    stage["SATS"] = live["SATS"] = D(2026, 6, 12)
    evidence = {
        s: _evidence(s, claim=fa.PROVIDER_NOT_COVERED, corr=_corr(D(2026, 8, 11))) for s in etfs
    }
    evidence["EA"] = _evidence("EA", claim=fa.PROVIDER_EXHAUSTED, corr=_corr(D(2026, 8, 4)))
    evidence["SATS"] = _evidence("SATS", claim=fa.PROVIDER_EXHAUSTED, corr=_corr(None))
    return universe, non_fresh, stage, live, evidence


def _adjudicate(universe, non_fresh, stage, live, evidence, operational=None):
    return fa.adjudicate(
        universe,
        stage_effective=stage,
        live_effective=live,
        non_fresh=non_fresh,
        cutoff=CUTOFF,
        evidence=evidence,
        operational=operational or {},
    )


def test_validly_adjudicated_names_stop_consuming_the_coverage_budget():
    """THE regression. On 2026-08-11 these eleven names put raw coverage at 0.9784 and
    froze the live store, although nine of them can never be fresh in this provider and
    two had genuinely ceased trading."""
    result = _adjudicate(*_production_universe())
    assert result["attributed_count"] == 11
    assert set(result["provider_not_covered_symbols"]) == {
        "SPY",
        "EFA",
        "EEM",
        "TLT",
        "IEF",
        "GLD",
        "DBC",
        "UUP",
        "KMLM",
    }
    assert set(result["provider_exhausted_symbols"]) == {"EA", "SATS"}
    assert result["failed_or_unexplained_symbols"] == []
    assert fa.gating_coverage(result) == pytest.approx(1.0)
    # ...and the honest figure is still reported, unchanged, so attribution can never
    # hide how much the provider actually delivered.
    assert result["raw_coverage"] == pytest.approx(499 / 510, abs=1e-6)


def test_evidence_state_governs_each_name_independently():
    """EA and SATS remain governed by THEIR evidence. Break EA's corroboration and only
    EA falls back — the ETFs are unaffected."""
    universe, non_fresh, stage, live, evidence = _production_universe()
    evidence["EA"] = _evidence("EA", claim=fa.PROVIDER_EXHAUSTED, corr=_corr(D(2026, 8, 11)))
    result = _adjudicate(universe, non_fresh, stage, live, evidence)
    assert result["failed_or_unexplained_symbols"] == ["EA"]
    assert result["attributed_count"] == 10
    # 499 fresh of 500 assessable — EA is now measured and it is not fresh.
    assert fa.gating_coverage(result) == pytest.approx(499 / 500, abs=1e-6)


def test_without_evidence_the_gate_fails_exactly_as_it_did_in_production():
    universe, non_fresh, stage, live, _ = _production_universe()
    result = _adjudicate(universe, non_fresh, stage, live, {})
    assert result["attributed_count"] == 0
    assert len(result["failed_or_unexplained_symbols"]) == 11
    assert fa.gating_coverage(result) == pytest.approx(499 / 510, abs=1e-6)
    assert fa.gating_coverage(result) < 0.98


def test_attribution_above_the_ceiling_is_voided_entirely():
    """An evidence file excusing a large slice of the pool is a suppressed check. Voiding
    is all-or-nothing: trimming to the ceiling by sort order would be arbitrary."""
    universe = [f"S{i:03d}" for i in range(100)]
    non_fresh = universe[:20]  # ceiling is max(5, 5) = 5
    stage = {s: (None if s in non_fresh else FRONTIER) for s in universe}
    evidence = {
        s: _evidence(s, claim=fa.PROVIDER_NOT_COVERED, corr=_corr(D(2026, 8, 11)))
        for s in non_fresh
    }
    result = _adjudicate(universe, non_fresh, stage, dict(stage), evidence)
    assert result["attributed_count"] == 0
    assert len(result["failed_or_unexplained_symbols"]) == 20
    assert any("DATA_EXEMPTION_IMPLAUSIBLE" in p for p in result["problems"])
    assert fa.gating_coverage(result) == pytest.approx(80 / 100)


def test_a_wholly_attributed_universe_measures_nothing_and_scores_zero():
    universe = ["A", "B", "C"]
    stage = {s: None for s in universe}
    evidence = {
        s: _evidence(s, claim=fa.PROVIDER_NOT_COVERED, corr=_corr(D(2026, 8, 11))) for s in universe
    }
    result = _adjudicate(universe, universe, stage, dict(stage), evidence)
    assert result["assessable_count"] == 0
    assert fa.gating_coverage(result) == 0.0
    assert any("DATA_PER_NAME_UNASSESSABLE" in p for p in result["problems"])


def test_fresh_prices_with_a_lagging_lastpricedate_are_not_fresh_for_gating():
    """Effective freshness is min(sep_max, lastpricedate).

    ``dollar_volume_universe`` filters on ``lastpricedate``, so such a name is dropped
    from the ranking pool OUTRIGHT — strictly worse than being ranked on old data, and
    invisible to any check that looks only at ``sep``. A gate that scored it healthy would
    be measuring something the books do not consume. Caller-side ``min()`` is what the two
    consumers both apply; this pins the consequence at the gate.
    """
    universe = ["AAA", "BBB", "LAGGY"]
    sep_max = {"AAA": FRONTIER, "BBB": FRONTIER, "LAGGY": FRONTIER}
    lastpricedate = {"AAA": FRONTIER, "BBB": FRONTIER, "LAGGY": D(2026, 6, 12)}
    effective = {t: min(sep_max[t], lastpricedate[t]) for t in universe}
    assert effective["LAGGY"] == D(2026, 6, 12), "the earlier of the two must win"

    non_fresh = sorted(t for t in universe if effective[t] < CUTOFF)
    assert non_fresh == ["LAGGY"], "current prices must not rescue a lagging lastpricedate"

    # Unadjudicated, it drags the gate down — it is not quietly counted as healthy.
    result = _adjudicate(universe, non_fresh, effective, dict(effective), {})
    assert result["failed_or_unexplained_symbols"] == ["LAGGY"]
    assert fa.gating_coverage(result) == pytest.approx(2 / 3)


def test_the_exemption_ceiling_has_a_floor_for_small_universes():
    assert fa.exemption_ceiling(10) == 5
    assert fa.exemption_ceiling(510) == 25
