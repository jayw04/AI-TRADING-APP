"""SPQ-1 Phase-1 synthetic implementation qualification (executable closed-rule tests).

Covers the 37 closed Phase-0 matrix cases (as far as they apply to implementation) plus the
owner's implementation-focused cases: every emittable refusal code is reachable only from its
governed condition, the deprecated code is never emitted, output is byte-identical on repeat, and
no real-data / network / order-path import exists.
"""
from __future__ import annotations

import dataclasses
import math
import re
from pathlib import Path

import numpy as np
import pytest

from app.research.mr002.spq1 import constants
from app.research.mr002.spq1.calendar import RegisteredCalendar
from app.research.mr002.spq1.execution_enrichment import enrich_decision
from app.research.mr002.spq1.identities import InputIdentityRegistry
from app.research.mr002.spq1.models import (
    FORBIDDEN_DECISION_FIELDS,
    build_signal_decision_record,
)
from app.research.mr002.spq1.normalization import normalize_signal, r5_value
from app.research.mr002.spq1.producer import produce_decision
from app.research.mr002.spq1.publication import (
    PublicationError,
    build_publication,
    write_publication,
)
from app.research.mr002.spq1.refusals import (
    DEPRECATED_CODES,
    REFUSAL_CODES,
    SignalRefusal,
)
from app.research.mr002.spq1.residuals import stock_residual_and_beta
from app.research.mr002.spq1.returns import CellStatus
from app.research.mr002.spq1.sector_pit import SectorRecord, resolve_sector
from app.research.mr002.spq1.security_identity import (
    LineageRecord,
    PitIdentityRegistry,
)

from . import fixtures as F


def _refusal(func, code: str) -> None:
    with pytest.raises(SignalRefusal) as exc:
        func()
    assert exc.value.code == code, f"expected {code}, got {exc.value.code}"


# --------------------------------------------------------------------------- happy path

def test_valid_decision_and_fields():
    rec = produce_decision(
        F.build_market(), F.build_security(), F.build_registry(), F.build_lineage(),
        F.build_request(),
    )
    assert rec.decision_eligibility_status == "ELIGIBLE"
    assert math.isfinite(rec.registered_signal_value)
    assert rec.registered_sigma_resid > 0
    assert math.isfinite(rec.beta)
    assert rec.sector_id == "TECH"
    assert rec.warmup_return_sessions == 125
    assert rec.warmup_price_observations == 126
    assert rec.candidate_id.startswith("MR-002|B|200|PSEC-AAA|LONG|")


def test_deterministic_byte_identical_repeat():   # SPQM-27 / canonical hash stability
    a = produce_decision(F.build_market(), F.build_security(), F.build_registry(),
                         F.build_lineage(), F.build_request())
    b = produce_decision(F.build_market(), F.build_security(), F.build_registry(),
                         F.build_lineage(), F.build_request())
    assert a.record_identity == b.record_identity
    assert a.canonical() == b.canonical()


def test_z_sigma_single_pass_identity():   # SPQM-13
    rec = produce_decision(F.build_market(), F.build_security(), F.build_registry(),
                          F.build_lineage(), F.build_request())
    # z and sigma share one normalization-window + computation-record identity.
    assert len(rec.normalization_window_identity) == 64
    assert len(rec.computation_record_identity) == 64
    assert rec.normalization_window_identity != rec.computation_record_identity


def test_abc_differ_only_by_downstream_config():   # SPQM-26
    base = produce_decision(F.build_market(), F.build_security(), F.build_registry(),
                           F.build_lineage(), F.build_request(config="B"))
    other = produce_decision(F.build_market(), F.build_security(), F.build_registry(),
                            F.build_lineage(), F.build_request(config="A"))
    # Signal facts identical; only configuration_id (downstream Z_entry) + candidate_id differ.
    assert base.registered_signal_value == other.registered_signal_value
    assert base.registered_sigma_resid == other.registered_sigma_resid
    assert base.beta == other.beta
    assert base.configuration_id != other.configuration_id


# --------------------------------------------------------------------------- warm-up boundary

def test_first_scoreable_boundary_ok_and_too_early():   # SPQM-32 / SPQM-33
    # With warm factors, the stock needs PRESENT status over the 125-return window [t-124, t].
    # first-present ordinal 76 == t-124 (t=200) -> OK; 77 == t-123 -> one session too early.
    ok_st = [CellStatus.YOUNG] * 76 + [CellStatus.PRESENT] * (F.N - 76)
    produce_decision(F.build_market(), F.build_security(statuses=ok_st), F.build_registry(),
                     F.build_lineage(), F.build_request())
    early_st = [CellStatus.YOUNG] * 77 + [CellStatus.PRESENT] * (F.N - 77)
    _refusal(
        lambda: produce_decision(F.build_market(), F.build_security(statuses=early_st),
                                 F.build_registry(), F.build_lineage(), F.build_request()),
        "INELIGIBLE:OLS_WINDOW_INSUFFICIENT",
    )


def test_warmup_guard_rejects_too_early_ordinal():   # explicit 125-session guard
    early = dataclasses.replace(F.build_request(), t=124)
    _refusal(
        lambda: produce_decision(F.build_market(), F.build_security(), F.build_registry(),
                                 F.build_lineage(), early),
        "INELIGIBLE:OLS_WINDOW_INSUFFICIENT",
    )


# --------------------------------------------------------------------------- missing-input taxonomy

def test_young_security_insufficient_history():   # SPQM-02
    st = [CellStatus.PRESENT] * F.N
    st[100] = CellStatus.YOUNG   # inside [t-124,t]
    _refusal(
        lambda: produce_decision(F.build_market(), F.build_security(statuses=st),
                                 F.build_registry(), F.build_lineage(), F.build_request()),
        "INELIGIBLE:OLS_WINDOW_INSUFFICIENT",
    )


def test_interior_hole_without_evidence_fails_closed():   # SPQM-29 / SPQM-41
    st = [CellStatus.PRESENT] * F.N
    st[150] = CellStatus.UNEXPLAINED_HOLE
    _refusal(
        lambda: produce_decision(F.build_market(), F.build_security(statuses=st),
                                 F.build_registry(), F.build_lineage(), F.build_request()),
        "INTEGRITY_STOP:OLS_WINDOW_INCOMPLETE",
    )


def test_governed_halt_with_evidence_is_ineligible():   # SPQM-36 / SPQM-40
    st = [CellStatus.PRESENT] * F.N
    st[150] = CellStatus.HALT_WITH_EVIDENCE
    _refusal(
        lambda: produce_decision(F.build_market(), F.build_security(statuses=st),
                                 F.build_registry(), F.build_lineage(), F.build_request()),
        "INELIGIBLE:KNOWN_MARKET_ABSENCE",
    )


def test_missing_factor_is_identity_mismatch():   # SPQM-06
    m = F.build_market()
    spy = m.spy_ret.copy()
    spy[50] = np.nan   # inside a needed sector-factor window
    m = dataclasses.replace(m, spy_ret=spy)
    _refusal(
        lambda: produce_decision(m, F.build_security(), F.build_registry(),
                                 F.build_lineage(), F.build_request()),
        "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH",
    )


def test_deprecated_return_input_missing_never_emittable():   # Correction 2
    assert "DEPRECATED_NON_EMITTABLE:RETURN_INPUT_MISSING" in DEPRECATED_CODES
    assert "INELIGIBLE:RETURN_INPUT_MISSING" not in REFUSAL_CODES
    with pytest.raises(AssertionError):
        SignalRefusal("DEPRECATED_NON_EMITTABLE:RETURN_INPUT_MISSING", "must never emit")


# --------------------------------------------------------------------------- OLS / residual

def test_singular_design_fails_closed():   # SPQM-05 / SPQM-20
    m = F.build_market()
    spy = np.full(F.N, 0.01)   # constant SPY -> singular sector regression design
    m = dataclasses.replace(m, spy_ret=spy)
    _refusal(
        lambda: produce_decision(m, F.build_security(), F.build_registry(),
                                 F.build_lineage(), F.build_request()),
        "INTEGRITY_STOP:OLS_DESIGN_SINGULAR",
    )


def test_residual_nonfinite_guard():   # RESIDUAL_NONFINITE
    idx = np.arange(80, dtype=np.float64)
    stock = 0.01 * np.sin(idx)             # non-collinear window inputs
    spy = 0.01 * np.cos(idx / 2.0)
    u = 0.01 * np.sin(idx / 3.0 + 1.0)
    u[70] = math.inf   # day-t sector factor non-finite -> residual non-finite
    _refusal(lambda: stock_residual_and_beta(stock, spy, u, 70),
             "INTEGRITY_STOP:RESIDUAL_NONFINITE")


def test_registered_solver_identity_and_tolerance():   # impl: solver / rank-tolerance identity
    assert constants.SOLVER_IDENTITY == "numpy.linalg.lstsq[LAPACK_gelsd_SVD,float64]"
    assert constants.RANK_TOLERANCE == 1e-10


# --------------------------------------------------------------------------- R5 / z / sigma units

def test_r5_requires_five_consecutive():
    assert r5_value([1.0, 2.0, 3.0, 4.0, 5.0]) == 15.0
    assert r5_value([1.0, 2.0, None, 4.0, 5.0]) is None   # missing middle -> no bridge
    assert r5_value([1.0, 2.0, 3.0, 4.0]) is None


def test_normalize_current_r5_missing():   # R5_WINDOW_INSUFFICIENT
    _refusal(lambda: normalize_signal([1.0] * 60, None, list(range(60))),
             "INELIGIBLE:R5_WINDOW_INSUFFICIENT")


def test_normalize_window_incomplete():   # ZSCORE_WINDOW_INSUFFICIENT
    hist = [1.0] * 59 + [None]
    _refusal(lambda: normalize_signal(hist, 2.0, list(range(60))),
             "INTEGRITY_STOP:ZSCORE_WINDOW_INSUFFICIENT")


def test_normalize_zero_variance():   # SPQM-10 ZSCORE_VARIANCE_INVALID
    _refusal(lambda: normalize_signal([1.0] * 60, 2.0, list(range(60))),
             "INELIGIBLE:ZSCORE_VARIANCE_INVALID")


def test_normalize_sigma_nonfinite():   # SIGMA_RESID_NONFINITE
    hist = [1e200 if i % 2 == 0 else -1e200 for i in range(60)]
    _refusal(lambda: normalize_signal(hist, 1.0, list(range(60))),
             "INTEGRITY_STOP:SIGMA_RESID_NONFINITE")


def test_normalize_excludes_current_r5():
    # mu/sigma computed only from the 60 historical values; current R5 not folded in.
    hist = [float(i) for i in range(60)]
    ns = normalize_signal(hist, 999.0, list(range(60)))
    mean = sum(hist) / 60
    assert abs(ns.mu - mean) < 1e-12


# --------------------------------------------------------------------------- calendar / sector / lineage

def test_calendar_mismatch_unsorted():   # SESSION_CALENDAR_MISMATCH
    _refusal(lambda: RegisteredCalendar(("S2", "S1")), "INTEGRITY_STOP:SESSION_CALENDAR_MISMATCH")


def test_sector_missing_pit():   # SECTOR_PIT_IDENTITY_MISSING
    _refusal(lambda: resolve_sector([], "2020-01-13T00:00:00Z"),
             "INELIGIBLE:SECTOR_PIT_IDENTITY_MISSING")


def test_sector_published_after_cutoff_excluded():   # SPQM-34
    recs = [
        SectorRecord("TECH", "2019-01-01T00:00:00Z", 1, "ev1"),
        SectorRecord("FIN", "2020-06-01T00:00:00Z", 1, "ev2"),  # after cutoff -> ignored
    ]
    assert resolve_sector(recs, "2020-01-13T00:00:00Z").sector_id == "TECH"


def test_sector_same_timestamp_conflict():   # SPQM-15 SECTOR_EFFECTIVE_DATE_CONFLICT
    recs = [
        SectorRecord("TECH", "2019-01-01T00:00:00Z", 1, "ev1"),
        SectorRecord("FIN", "2019-01-01T00:00:00Z", 1, "ev2"),
    ]
    _refusal(lambda: resolve_sector(recs, "2020-01-13T00:00:00Z"),
             "INTEGRITY_STOP:SECTOR_EFFECTIVE_DATE_CONFLICT")


def test_ticker_change_continuity_vs_merger_no_continuity():   # SPQM-17 / SPQM-35
    reg = PitIdentityRegistry(lineage={
        "TICK": (LineageRecord(None, "PSEC-1", 0, "ticker_change", True, "ev"),),
        "MERG": (LineageRecord("PSEC-OLD", "PSEC-NEW", 0, "merger", False, "ev"),),
    })
    assert reg.resolve_permanent_id("TICK", 200) == "PSEC-1"      # history continues
    assert reg.resolve_permanent_id("MERG", 200) == "PSEC-NEW"    # new identity, not predecessor


def test_lineage_ambiguous():   # SECURITY_IDENTITY_AMBIGUOUS
    reg = PitIdentityRegistry(lineage={
        "AMB": (
            LineageRecord(None, "PSEC-A", 5, "merger", False, "ev"),
            LineageRecord(None, "PSEC-B", 5, "merger", False, "ev"),
        ),
    })
    _refusal(lambda: reg.resolve_permanent_id("AMB", 200),
             "INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS")


# --------------------------------------------------------------------------- identity / eligibility / ADV

def test_identity_mismatch_calendar():   # impl: calendar identity mismatch
    ids = dict(F.build_registry().as_dict())
    ids["registered_exchange_calendar"] = "wrong-calendar-id"
    reg = InputIdentityRegistry(ids)
    _refusal(
        lambda: produce_decision(F.build_market(), F.build_security(), reg,
                                 F.build_lineage(), F.build_request()),
        "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH",
    )


def test_schema_version_mismatch_refused_at_construction():   # impl: schema-version mismatch
    ids = dict(F.build_registry().as_dict())
    ids["schema_identity"] = "stale-schema"
    _refusal(lambda: InputIdentityRegistry(ids),
             "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH")


def test_eligibility_evidence_missing():   # ELIGIBILITY_EVIDENCE_MISSING
    sec = F.build_security()
    bad = dataclasses.replace(sec.eligibility_checks[0], evidence_present=False)
    sec = dataclasses.replace(sec, eligibility_checks=[bad])
    _refusal(
        lambda: produce_decision(F.build_market(), sec, F.build_registry(),
                                 F.build_lineage(), F.build_request()),
        "INELIGIBLE:ELIGIBILITY_EVIDENCE_MISSING",
    )


def test_eligibility_liquidity_exclusion_status():
    sec = F.build_security(excludes_liquidity=True)
    rec = produce_decision(F.build_market(), sec, F.build_registry(),
                          F.build_lineage(), F.build_request())
    assert rec.decision_eligibility_status == "INELIGIBLE"
    assert rec.eligibility_precedence_rank == 5


def test_adv_window_insufficient():   # ADV_WINDOW_INSUFFICIENT
    sec = F.build_security()
    rc = sec.raw_close.copy()
    rc[190] = np.nan   # inside [t-20, t-1]; independent of stock returns
    sec = dataclasses.replace(sec, raw_close=rc)
    _refusal(
        lambda: produce_decision(F.build_market(), sec, F.build_registry(),
                                 F.build_lineage(), F.build_request()),
        "INELIGIBLE:ADV_WINDOW_INSUFFICIENT",
    )


# --------------------------------------------------------------------------- decision/execution seam

def test_decision_record_rejects_future_field():   # SPQM-04 FUTURE_INFORMATION_DETECTED
    rec = produce_decision(F.build_market(), F.build_security(), F.build_registry(),
                          F.build_lineage(), F.build_request())
    data = dict(rec.canonical())
    # canonical() hex-encodes floats; rebuild from raw fields for the structural test.
    raw = {f: getattr(rec, f) for f in rec.__dataclass_fields__}
    raw["official_next_open_price"] = 101.0
    _refusal(lambda: build_signal_decision_record(raw),
             "INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED")
    assert "gap_filter_result" in FORBIDDEN_DECISION_FIELDS
    assert data  # canonical produced


def test_enrichment_admissible_gap_and_missing_open():   # SPQM-42 / §13
    rec = produce_decision(F.build_market(), F.build_security(), F.build_registry(),
                          F.build_lineage(), F.build_request())
    ok = enrich_decision(rec, 201, official_next_open_price=100.0,
                         distribution_adjusted_close_t=100.0)
    assert ok.execution_admissibility_status == "ADMISSIBLE"
    gap = enrich_decision(rec, 201, official_next_open_price=120.0,
                          distribution_adjusted_close_t=100.0)
    assert gap.execution_admissibility_status == "CANCELLED_GAP"
    miss = enrich_decision(rec, 201, official_next_open_price=None,
                           distribution_adjusted_close_t=100.0)
    assert miss.execution_admissibility_status == "CANCELLED_MISSING_OPEN"


def test_enrichment_cannot_mutate_decision():   # impl: decision-record mutation during enrichment
    rec = produce_decision(F.build_market(), F.build_security(), F.build_registry(),
                          F.build_lineage(), F.build_request())
    enriched = enrich_decision(rec, 201, 100.0, 100.0)
    assert enriched.decision_record_identity == rec.record_identity
    tampered = dataclasses.replace(
        enriched, decision_record_identity="0" * 64,
    )
    _refusal(lambda: tampered.verify_decision_unchanged(rec),
             "INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED")


# --------------------------------------------------------------------------- publication

def _publish(decisions):
    reg = F.build_registry()
    enr = [enrich_decision(d, d.decision_session + 1, 100.0, 100.0) for d in decisions]
    return build_publication(
        decisions, enr, reg.as_dict(), F.PRODUCER_CODE_VERSION,
        {"schema_identity": F.PHASE0_SCHEMA_SHA256}, F.CUTOFF,
    )


def test_publication_deterministic_ordering():   # impl: non-deterministic input ordering
    d1 = produce_decision(F.build_market(), F.build_security(symbol="AAA"), F.build_registry(),
                         F.build_lineage("AAA", "PSEC-AAA"), F.build_request())
    d2 = produce_decision(F.build_market(), F.build_security(symbol="BBB", sector_id="FIN"),
                         F.build_registry(), F.build_lineage("BBB", "PSEC-BBB"), F.build_request())
    a = _publish([d1, d2])
    b = _publish([d2, d1])   # reversed input order
    assert a.manifest_sha256 == b.manifest_sha256
    # distinct securities -> distinct candidate ids (no cross-security contamination)
    assert d1.candidate_id != d2.candidate_id
    assert d1.permanent_security_id != d2.permanent_security_id


def test_publication_overwrite_and_partial_refusal(tmp_path):   # impl: overwrite / partial refusal
    d = produce_decision(F.build_market(), F.build_security(), F.build_registry(),
                        F.build_lineage(), F.build_request())
    pkg = _publish([d])
    out = tmp_path / "pub.json"
    h1 = write_publication(pkg, str(out))
    assert out.exists() and len(h1) == 64
    with pytest.raises(PublicationError):
        write_publication(pkg, str(out))   # non-overwriting
    # no stray partial files remain
    assert list(tmp_path.glob("*.partial")) == []


# --------------------------------------------------------------------------- coverage / isolation

def test_all_emittable_refusal_codes_reachable():
    # Every code raised somewhere in this suite; assert the taxonomy has exactly the frozen set.
    assert len(REFUSAL_CODES) == 18
    assert "INTEGRITY_STOP:EXECUTION_PRICE_INPUT_INVALID" in REFUSAL_CODES
    classes = set(REFUSAL_CODES.values())
    assert classes == {"INTEGRITY_STOP", "REFUSED_CODE_OR_DATA_IDENTITY", "INELIGIBLE"}


def test_no_real_data_or_network_or_orderpath_imports():
    pkg_dir = Path(__file__).resolve().parents[3] / "app" / "research" / "mr002" / "spq1"
    forbidden = re.compile(
        r"\b(requests|boto3|botocore|urllib|httpx|socket|alpaca|anthropic|sqlalchemy|"
        r"order_router|broker|app\.services|app\.risk|pandas)\b"
    )
    for src in pkg_dir.glob("*.py"):
        text = src.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith(("import ", "from ")):
                assert not forbidden.search(line), f"{src.name}:{lineno} forbidden import: {line}"


# --------------------------------------------------------------------------- direct guard coverage

def test_calendar_duplicate_and_ordinal_and_window():
    _refusal(lambda: RegisteredCalendar(("S1", "S1")),
             "INTEGRITY_STOP:SESSION_CALENDAR_MISMATCH")
    cal = RegisteredCalendar(("S0", "S1", "S2"))
    assert cal.ordinal("S1") == 1
    _refusal(lambda: cal.ordinal("SX"), "INTEGRITY_STOP:SESSION_CALENDAR_MISMATCH")
    assert list(cal.window_ordinals(2, 2)) == [0, 1]
    _refusal(lambda: cal.window_ordinals(1, 3), "INELIGIBLE:OLS_WINDOW_INSUFFICIENT")


def test_registry_missing_slot_and_unregistered_verify():
    ids = dict(F.build_registry().as_dict())
    ids.pop("spy_total_return_series")
    _refusal(lambda: InputIdentityRegistry(ids),
             "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH")
    reg = F.build_registry()
    _refusal(lambda: reg.verify("not_a_slot", "x"),
             "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH")


def test_model_unknown_and_missing_field_rejected():
    rec = produce_decision(F.build_market(), F.build_security(), F.build_registry(),
                          F.build_lineage(), F.build_request())
    raw = {f: getattr(rec, f) for f in rec.__dataclass_fields__}
    unknown = dict(raw, some_future_metric=1.0)
    _refusal(lambda: build_signal_decision_record(unknown),
             "INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED")
    incomplete = {k: v for k, v in raw.items() if k != "beta"}
    _refusal(lambda: build_signal_decision_record(incomplete),
             "INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED")


def test_liquidity_short_window_and_sector_factor_no_history():
    from app.research.mr002.spq1.liquidity import dollar_volume_median
    from app.research.mr002.spq1.sector_factor import sector_factor_at
    rc = np.arange(1.0, 11.0)
    vol = np.arange(1.0, 11.0)
    _refusal(lambda: dollar_volume_median(rc, vol, t=5, window=20),
             "INELIGIBLE:ADV_WINDOW_INSUFFICIENT")
    spy = np.linspace(-0.01, 0.01, 10)
    sec = np.linspace(-0.02, 0.02, 10)
    _refusal(lambda: sector_factor_at(spy, sec, s=5),   # window would run before ordinal 0
             "REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH")


def test_eligibility_unknown_category_missing_evidence():
    from app.research.mr002.spq1.eligibility import ExclusionCheck, evaluate_eligibility
    bad = ExclusionCheck("R", "not_a_category", True, "v", "th", "src", "2020-01-01", True)
    _refusal(lambda: evaluate_eligibility([bad], "2020-06-01"),
             "INELIGIBLE:ELIGIBILITY_EVIDENCE_MISSING")


def test_eligibility_post_cutoff_evidence_is_missing_both_directions():   # Correction 1
    from app.research.mr002.spq1.eligibility import ExclusionCheck, evaluate_eligibility
    cutoff = "2020-01-13T00:00:00Z"
    # post-cutoff record that says "clear" (excludes=False) -> still EVIDENCE_MISSING
    clear = ExclusionCheck("EARN", "event_blackout", False, "v", "th", "src",
                           "2021-01-01T00:00:00Z", True)
    _refusal(lambda: evaluate_eligibility([clear], cutoff),
             "INELIGIBLE:ELIGIBILITY_EVIDENCE_MISSING")
    # post-cutoff record that says "exclude" -> same disposition; future fact not consulted
    exclude = ExclusionCheck("EARN", "event_blackout", True, "v", "th", "src",
                             "2021-01-01T00:00:00Z", True)
    _refusal(lambda: evaluate_eligibility([exclude], cutoff),
             "INELIGIBLE:ELIGIBILITY_EVIDENCE_MISSING")


def test_eligibility_earlier_valid_record_used_when_later_unavailable():   # Correction 1
    from app.research.mr002.spq1.eligibility import ExclusionCheck, evaluate_eligibility
    cutoff = "2020-01-13T00:00:00Z"
    earlier = ExclusionCheck("EARN", "event_blackout", False, "clear", "th", "src-a",
                             "2020-01-05T00:00:00Z", True)
    later = ExclusionCheck("EARN", "event_blackout", True, "exclude", "th", "src-b",
                           "2021-06-01T00:00:00Z", True)   # not yet available
    res = evaluate_eligibility([earlier, later], cutoff)
    assert res.status == "ELIGIBLE"   # earlier valid record used; future record ignored
    assert res.evidence[0].availability_timestamp == "2020-01-05T00:00:00Z"
    assert res.evidence[0].reason == "cleared"


def test_enrichment_invalid_open_and_close_and_session():   # Correction 2
    rec = produce_decision(F.build_market(), F.build_security(), F.build_registry(),
                          F.build_lineage(), F.build_request())
    t1 = rec.decision_session + 1
    for bad_open in (0.0, -5.0, math.inf):
        _refusal(lambda bo=bad_open: enrich_decision(rec, t1, bo, 100.0),
                 "INTEGRITY_STOP:EXECUTION_PRICE_INPUT_INVALID")
    for bad_close in (0.0, -1.0, math.nan):
        _refusal(lambda bc=bad_close: enrich_decision(rec, t1, 100.0, bc),
                 "INTEGRITY_STOP:EXECUTION_PRICE_INPUT_INVALID")
    _refusal(lambda: enrich_decision(rec, t1 + 5, 100.0, 100.0),
             "INTEGRITY_STOP:SESSION_CALENDAR_MISMATCH")
    # boundary: exactly 6% cancels; just below admits
    at = enrich_decision(rec, t1, 106.0, 100.0)
    assert at.execution_admissibility_status == "CANCELLED_GAP"
    below = enrich_decision(rec, t1, 105.99, 100.0)
    assert below.execution_admissibility_status == "ADMISSIBLE"


def test_registered_ols_malformed_input():   # Correction 3
    from app.research.mr002.spq1.stock_regression import registered_ols
    _refusal(lambda: registered_ols(np.zeros((3, 2)), np.zeros((3, 1))),
             "INTEGRITY_STOP:OLS_DESIGN_SINGULAR")   # y not 1-D
    _refusal(lambda: registered_ols(np.zeros(5), np.zeros((4, 1))),
             "INTEGRITY_STOP:OLS_DESIGN_SINGULAR")   # row mismatch
    _refusal(lambda: registered_ols(np.zeros(0), np.zeros((0, 1))),
             "INTEGRITY_STOP:OLS_DESIGN_SINGULAR")   # empty
    _refusal(lambda: registered_ols(np.zeros(2), np.zeros((2, 3))),
             "INTEGRITY_STOP:OLS_DESIGN_SINGULAR")   # fewer obs than params


def test_lineage_missing_symbol():
    reg = PitIdentityRegistry(lineage={})
    _refusal(lambda: reg.resolve_permanent_id("NOPE", 10),
             "INTEGRITY_STOP:SECURITY_IDENTITY_AMBIGUOUS")
