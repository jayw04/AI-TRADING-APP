"""CASH_OR_TBILL_RETURN — bound DGS3MO snapshot smoke test (real committed artifact).

Binds the immutable FRED DGS3MO snapshot by its SHA-256 and exercises the frozen accrual over a
contiguous run of real trading sessions. Reads the committed file only — no network. If the snapshot
bytes ever change, the digest assertion fails (the whole point of the fail-closed loader).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from app.strategies.cash_tbill_benchmark import (
    CashTbillBinding,
    InvalidCashData,
    accrue_session_returns,
    load_dgs3mo,
)

# The frozen binding (owner-supplied provenance; see CASH_OR_TBILL_RETURN_binding.md).
SNAPSHOT_SHA256 = "87d8ba2fc5981add5ea48bb5d365f79371fd457488a598e0043758c21ff825d1"
OBSERVATION_CUTOFF = "2026-07-21"
DATA_DIR = (Path(__file__).resolve().parents[4]
            / "docs/review/momentum_daily/equal_weight_validation/data")

pytestmark = pytest.mark.skipif(
    not (DATA_DIR / "DGS3MO.csv").exists(),
    reason="the committed DGS3MO snapshot is required for this binding smoke test")


def _binding() -> CashTbillBinding:
    return CashTbillBinding(raw_file="DGS3MO.csv", raw_file_sha256=SNAPSHOT_SHA256,
                            observation_cutoff=OBSERVATION_CUTOFF)


def test_bound_snapshot_matches_its_digest_and_spans_the_window():
    series = load_dgs3mo(DATA_DIR / "DGS3MO.csv", SNAPSHOT_SHA256)
    assert min(series) <= date(2004, 1, 2)                 # ≥ 1 year of pre-2005 history
    assert max(series) >= date(2026, 6, 12)                # covers the historical window end
    assert len(series) > 5000


def test_contiguous_trading_sessions_accrue_small_daily_returns():
    """A contiguous run of real sessions accrues 1–3 calendar days each → small per-session returns,
    never the multi-year artifact a sparse session list would produce."""
    binding = _binding()
    # a contiguous block of early-2005 business days
    start = date(2005, 1, 3)
    sessions = []
    d = start
    while len(sessions) < 15:
        if d.weekday() < 5:                                # business days
            sessions.append(d)
        d += timedelta(days=1)
    out = accrue_session_returns(binding, sessions, DATA_DIR)
    # first session: 0 calendar days → 0.0; the rest are small positive (2005 yields ~2%)
    assert out[sessions[0]] == 0.0
    for s in sessions[1:]:
        assert 0.0 <= out[s] < 0.001                       # ~2% annual over ≤3 days is tiny


def test_a_pre_snapshot_session_is_invalid_not_zero():
    with pytest.raises(InvalidCashData):
        accrue_session_returns(_binding(), [date(2003, 6, 2)], DATA_DIR)


def test_monday_after_a_weekend_accrues_three_calendar_days():
    binding = _binding()
    friday, monday = date(2005, 1, 7), date(2005, 1, 10)
    out = accrue_session_returns(binding, [friday, monday], DATA_DIR)
    # monday accrues 3 calendar days on the PIT-lagged (strictly-before-monday) yield
    from app.strategies.cash_tbill_benchmark import cash_session_return, load_dgs3mo, pit_yield_asof
    series = {k: v for k, v in load_dgs3mo(DATA_DIR / "DGS3MO.csv", SNAPSHOT_SHA256).items()
              if k <= date(2026, 7, 21)}
    y_mon = pit_yield_asof(series, monday)
    assert out[monday] == cash_session_return(y_mon, 3)
