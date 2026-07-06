"""GOVCONTRACT-001 study — locked-calibration verdict (Approved/Rejected/Insufficient Evidence),
materiality gate, and robustness logic. Synthetic; no factor store."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.altdata.events.store import CorporateEvent
from app.altdata.quiver.govcontract_study import (
    MATERIALITY_ABS_USD,
    SensitivityRow,
    filter_material,
    is_material,
    is_robust,
    run_primary,
)

HOLD = 20


def _cands():
    from app.altdata.matched_control import CandidateFeatures
    return [CandidateFeatures(f"T{i:02d}", "Tech", float(i), float(i), float(i)) for i in range(20)]


def _feature_fn():
    cands = _cands()
    return lambda _as_of: cands


def _price_fn(event_ticker, event_ret, control_ret):
    def price_fn(ticker, start, _end):
        r = event_ret if ticker == event_ticker else control_ret
        return [(start + timedelta(days=i), 100.0 * (1 + r * i / HOLD)) for i in range(HOLD + 5)]
    return price_fn


def _events(ticker, k):
    return [CorporateEvent(cik=1, ticker=ticker, event_type="gov_contract_award", source="quiver",
                           accession=f"a{i}", filed_at=datetime(2026, 1, 1, tzinfo=UTC),
                           event_date=date(2026, 1, 1) + timedelta(days=15 * i), payload={"amount": 1e9})
            for i in range(k)]


def _primary(ret, k):
    return run_primary(_events("T10", k), price_fn=_price_fn("T10", ret, 0.02),
                       feature_fn=_feature_fn(), min_controls=3, n_resamples=300)


# --- verdict outcomes -------------------------------------------------------------------------

def test_approved_positive_edge_meets_gate():
    out = _primary(0.10, 120)                 # gross +8%, net ~+7.6% after cost; 120 ≥ 100
    assert out["metrics"]["n_benchmarked"] == 120
    assert out["outcome"] == "Approved"
    assert out["metrics"]["mean_excess"] < out["metrics"]["mean_excess_gross"]   # cost applied


def test_insufficient_evidence_below_event_gate():
    out = _primary(0.10, 10)                   # positive but only 10 events
    assert out["outcome"] == "Insufficient Evidence"


def test_rejected_negative_edge():
    out = _primary(-0.05, 120)                  # gross −7%
    assert out["outcome"] == "Rejected"


# --- materiality (locked threshold) -----------------------------------------------------------

def test_materiality_requires_both_relative_and_absolute():
    assert is_material(1_000_000, 100_000_000)         # 1M ≥ 250k AND ≥ 0.25%*100M(=250k)
    assert not is_material(200_000, 100_000_000)       # below $250k absolute
    assert not is_material(1_000_000, 500_000_000)     # 1M < 0.25%*500M(=1.25M)
    assert not is_material(1_000_000, None)            # unknown mktcap -> excluded (conservative)
    assert not is_material(None, 100_000_000)


def test_filter_material_drops_immaterial_events():
    evs = _events("T10", 3)
    evs[0] = CorporateEvent(cik=1, ticker="T10", event_type="gov_contract_award", source="quiver",
                            accession="small", filed_at=datetime(2026, 1, 1, tzinfo=UTC),
                            event_date=date(2026, 2, 1), payload={"amount": MATERIALITY_ABS_USD - 1})
    kept = filter_material(evs, mktcap_fn=lambda _t, _d: 100_000_000.0)
    assert len(kept) == 2 and all((e.payload or {}).get("amount", 0) >= MATERIALITY_ABS_USD for e in kept)


# --- robustness (one-directional; confirmation only) ------------------------------------------

def _row(sig):
    return SensitivityRow("disclosure_lag", 14, 120, 0.05, 0.01 if sig else -0.01, 0.09, 0.01, sig)


def test_robust_approved_requires_all_alternatives_significant():
    assert is_robust("Approved", {"rows": [_row(True), _row(True)]})
    assert not is_robust("Approved", {"rows": [_row(True), _row(False)]})   # one flips -> fragile


def test_robust_rejected_requires_no_alternative_manufactures_edge():
    assert is_robust("Rejected", {"rows": [_row(False), _row(False)]})
    assert not is_robust("Rejected", {"rows": [_row(False), _row(True)]})   # an alt makes it sig+
