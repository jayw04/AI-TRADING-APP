"""Pure-logic tests for the GOVCONTRACT-001 availability-assumption calibration.

The network path is covered by tests/altdata/quiver/test_usaspending.py (retry + taxonomy). Here
we pin the parts that must be deterministic: adaptive rate-limiter behaviour, outlier reason-codes,
size bucketing, and the operational-completeness discipline of the gate."""

from __future__ import annotations

from types import SimpleNamespace

from scripts.calibrate_govcontract_lag import (
    EXCEEDANCE_THRESHOLDS,
    AdaptiveRateLimiter,
    _gate_components,
    _reason_code,
    _size_bucket,
)


def _cal(**kw):
    """Minimal stand-in exposing only the attributes _gate_components reads."""
    base = dict(operational_failures=0, operational_completion_rate=1.0,
                recipient_reconciliation_rate=0.753, proxy_n=697,
                reconciliation_lag_proxy_days_p90=56, proxy_scope="reconciled_subpopulation",
                proxy_status="descriptive_only", policy_status="not_frozen")
    base.update(kw)
    return SimpleNamespace(**base)


def test_sensitivity_grid_includes_measured_proxy_p90_of_56():
    # owner disposition: the grid must carry the measured reconciled-subpopulation proxy p90
    assert 56 in EXCEEDANCE_THRESHOLDS
    for conventional in (21, 27, 30, 45, 60):  # legacy + pilot + conservative all retained
        assert conventional in EXCEEDANCE_THRESHOLDS


def test_gate_components_split_operational_pass_from_policy_fail():
    # the whole point: hardening PASSED even though the research-policy gate FAILED
    comps = _gate_components(_cal())
    assert comps["operational_completeness"]["status"] == "PASS"
    assert comps["true_disclosure_interpretation"]["status"] == "FAIL"
    assert comps["global_lag_policy_freeze"]["status"] == "FAIL"
    assert comps["missingness_validity"]["status"] == "PENDING"


def test_recipient_quality_is_conditional_at_75pct_not_a_flat_fail():
    assert _gate_components(_cal(recipient_reconciliation_rate=0.753))[
        "recipient_reconciliation_quality"]["status"] == "CONDITIONAL"
    assert _gate_components(_cal(recipient_reconciliation_rate=0.92))[
        "recipient_reconciliation_quality"]["status"] == "PASS"
    assert _gate_components(_cal(recipient_reconciliation_rate=0.55))[
        "recipient_reconciliation_quality"]["status"] == "FAIL"


def test_rate_limiter_backs_off_on_429_and_relaxes_on_success():
    rl = AdaptiveRateLimiter(min_interval=0.1, max_interval=2.0)
    assert rl._interval == 0.1
    rl.note_429()
    assert rl._interval == 0.2  # doubled
    rl.note_429()
    assert rl._interval == 0.4
    for _ in range(25):  # sustained success relaxes it
        rl.note_success()
    assert rl._interval < 0.4


def test_rate_limiter_is_bounded():
    rl = AdaptiveRateLimiter(min_interval=0.1, max_interval=0.3)
    for _ in range(10):
        rl.note_429()
    assert rl._interval <= 0.3  # never exceeds max


def test_size_buckets():
    assert _size_bucket(None) == "unknown"
    assert _size_bucket(50_000) == "<100K"
    assert _size_bucket(500_000) == "100K-1M"
    assert _size_bucket(5_000_000) == "1-10M"
    assert _size_bucket(50_000_000) == ">10M"


def test_reason_codes_distinguish_late_disclosure_from_linkage_error():
    assert _reason_code({"lag": 10, "agency_matched": True}) == "WITHIN_EXPECTED"
    assert _reason_code({"lag": 300, "agency_matched": True}) == "LATE_DISCLOSURE"
    # recipient matched but agency did NOT — the award identity is ambiguous, not a disclosure fact
    assert _reason_code({"lag": 300, "agency_matched": False}) == "ENTITY_LINKAGE_AMBIGUITY"
    assert _reason_code({"lag": 700, "agency_matched": True}) == "HISTORICAL_BACKFILL"
    assert _reason_code({"lag": None, "agency_matched": True}) == "NO_LAG"
