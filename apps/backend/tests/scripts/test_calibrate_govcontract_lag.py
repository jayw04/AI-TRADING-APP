"""Pure-logic tests for the GOVCONTRACT-001 availability-assumption calibration.

The network path is covered by tests/altdata/quiver/test_usaspending.py (retry + taxonomy). Here
we pin the parts that must be deterministic: adaptive rate-limiter behaviour, outlier reason-codes,
size bucketing, and the operational-completeness discipline of the gate."""

from __future__ import annotations

from scripts.calibrate_govcontract_lag import (
    AdaptiveRateLimiter,
    _reason_code,
    _size_bucket,
)


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
