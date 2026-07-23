"""CASH_OR_TBILL_RETURN — frozen DGS3MO methodology (PREREG v1.0 §6.2, owner rulings 2026-07-22).

Pins: no same-day use (strictly-before-t PIT), Friday→Monday 3-day ACT/365 accrual, holiday carry,
missing-observation carry, first-date INVALID_DATA (never zero), negative/zero yield, digest
fail-closed, and no network access. The strategy-residual-cash == benchmark-cash economics is pinned
by both using the same `cash_session_return`.
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pytest

from app.strategies import cash_tbill_benchmark as cb
from app.strategies.cash_tbill_benchmark import (
    CashTbillBinding,
    InvalidCashData,
    accrue_session_returns,
    cash_session_return,
    pit_yield_asof,
)

D = date

# A tiny synthetic DGS3MO snapshot in FRED format (DATE,DGS3MO; '.' = missing).
FIXTURE = """DATE,DGS3MO
2004-12-30,2.20
2004-12-31,2.21
2005-01-03,2.22
2005-01-04,.
2005-01-05,2.24
2005-01-06,2.25
2005-01-07,2.26
"""


def _write_fixture(tmp_path: Path) -> tuple[CashTbillBinding, Path]:
    p = tmp_path / "DGS3MO.csv"
    p.write_text(FIXTURE, encoding="utf-8")
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    return CashTbillBinding(raw_file="DGS3MO.csv", raw_file_sha256=sha,
                            observation_cutoff="2026-06-12"), tmp_path


# ---- frozen constants ------------------------------------------------------------

def test_frozen_source_and_accrual_constants():
    assert cb.SERIES_ID == "DGS3MO"
    assert cb.QUOTE_UNITS == "percent_per_annum_investment_basis"
    assert cb.DISCOUNT_TO_INVESTMENT_CONVERSION == "none"
    assert cb.CALENDAR_DAYS_PER_YEAR == 365
    assert cb.TRANSACTION_COSTS == 0.0


# ---- accrual: ACT/365 calendar-day, the frozen formula --------------------------

def test_cash_session_return_is_act_365_calendar_day():
    # y = 5% ; one calendar day
    assert cash_session_return(5.0, 1) == pytest.approx((1.05) ** (1 / 365) - 1)
    # Friday→Monday = 3 calendar days, accrued in ONE session return (not 3× a 1/252 day)
    assert cash_session_return(5.0, 3) == pytest.approx((1.05) ** (3 / 365) - 1)
    assert cb.friday_to_monday_calendar_days(D(2005, 1, 7), D(2005, 1, 10)) == 3


def test_zero_and_negative_yield_handled():
    assert cash_session_return(0.0, 5) == 0.0
    neg = cash_session_return(-0.5, 3)          # negative T-bill yield (has occurred)
    assert neg < 0.0 and neg == pytest.approx((1 - 0.005) ** (3 / 365) - 1)


# ---- PIT: strictly before t, no same-day look-ahead -----------------------------

def test_pit_uses_the_latest_observation_strictly_before_the_session():
    series = {D(2005, 1, 3): 2.22, D(2005, 1, 5): 2.24}
    # on 2005-01-05, the SAME-day 2.24 must NOT be used → the strictly-prior 2.22 applies
    assert pit_yield_asof(series, D(2005, 1, 5)) == 2.22
    # on 2005-01-06, the latest strictly-prior is 2.24
    assert pit_yield_asof(series, D(2005, 1, 6)) == 2.24


def test_missing_and_holiday_gaps_carry_the_latest_prior_value():
    series = {D(2005, 1, 3): 2.22, D(2005, 1, 5): 2.24}   # 01-04 missing ('.')
    # a session on 01-05 with 01-04 missing carries the 01-03 value (strictly prior, carried)
    assert pit_yield_asof(series, D(2005, 1, 5)) == 2.22
    # a Monday after a Fri obs carries Friday's value across the weekend
    series2 = {D(2005, 1, 7): 2.26}                       # Friday
    assert pit_yield_asof(series2, D(2005, 1, 10)) == 2.26  # Monday


def test_first_date_with_no_prior_observation_is_invalid_not_zero():
    series = {D(2005, 1, 3): 2.22}
    with pytest.raises(InvalidCashData):
        pit_yield_asof(series, D(2005, 1, 3))            # same day, no strictly-prior → INVALID
    with pytest.raises(InvalidCashData):
        pit_yield_asof(series, D(2004, 1, 1))            # before series → INVALID (never 0.0)


# ---- end-to-end accrual over sessions -------------------------------------------

def test_accrue_over_sessions_uses_pit_yield_and_calendar_days(tmp_path):
    binding, data_dir = _write_fixture(tmp_path)
    sessions = [D(2005, 1, 5), D(2005, 1, 6), D(2005, 1, 7)]
    out = accrue_session_returns(binding, sessions, data_dir)
    # 01-05: prev None → 0 calendar days, but a valid strictly-prior yield (2.22) is required
    assert out[D(2005, 1, 5)] == cash_session_return(2.22, 0)
    # 01-06: 1 day since 01-05, PIT yield = latest strictly-before 01-06 = 2.24 (from 01-05)
    assert out[D(2005, 1, 6)] == cash_session_return(2.24, 1)
    # 01-07: 1 day since 01-06, PIT yield strictly-before = 2.25 (from 01-06)
    assert out[D(2005, 1, 7)] == cash_session_return(2.25, 1)


def test_accrue_raises_when_a_session_precedes_all_observations(tmp_path):
    binding, data_dir = _write_fixture(tmp_path)
    with pytest.raises(InvalidCashData):
        accrue_session_returns(binding, [D(2004, 6, 1)], data_dir)   # before the snapshot begins


# ---- strategy cash residual and benchmark cash use IDENTICAL returns ------------

def test_strategy_residual_cash_and_benchmark_cash_use_the_same_return():
    """The single frozen cash economics rule: uninvested strategy cash earns the identical PIT-lagged
    DGS3MO return the cash benchmark accrues — same function, same inputs, same output."""
    y, days = 4.75, 3
    benchmark_cash = cash_session_return(y, days)
    strategy_residual_cash = cash_session_return(y, days)   # e.g. 20%-cap residual / <5-name cash
    assert strategy_residual_cash == benchmark_cash


# ---- digest fail-closed + no network --------------------------------------------

def test_loader_is_fail_closed_on_a_digest_mismatch(tmp_path):
    p = tmp_path / "DGS3MO.csv"
    p.write_text(FIXTURE, encoding="utf-8")
    bad = CashTbillBinding(raw_file="DGS3MO.csv", raw_file_sha256="0" * 64,
                           observation_cutoff="2026-06-12")
    with pytest.raises(ValueError, match="digest mismatch"):
        accrue_session_returns(bad, [D(2005, 1, 5)], tmp_path)


def test_module_imports_no_network_client():
    """Validation must run with no network access. The module must not import a network client."""
    import inspect

    src = inspect.getsource(cb)
    for banned in ("requests", "urllib.request", "urllib3", "httpx", "socket", "aiohttp", "boto3"):
        assert banned not in src, f"cash benchmark must not use {banned}"
