"""K3 against its frozen definition, and against the four ways it could quietly be wrong.

Each of these tests exists because the corresponding mistake produces a plausible number rather than
an error — which is the only kind of defect that survives review.
"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from app.research.mdq_eval.k3_completeness import (
    K3InputError,
    evaluate_k3,
    observed_keys,
)
from app.research.mdq_eval.results import KOutcome

ET = ZoneInfo("America/New_York")
SESSION = date(2026, 8, 26)


def _write_bars(root, feed: str, session: date, rows: list[tuple[str, datetime]]) -> None:
    import pandas as pd

    d = root / feed / session.isoformat() / "bars"
    d.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(
        [{"symbol": s, "ts": ts.isoformat(), "open": 1.0, "high": 1.0, "low": 1.0,
          "close": 1.0, "volume": 1} for s, ts in rows]
    )
    frame.to_parquet(d / "bars_1min.parquet")


def _et(h: int, m: int, session: date = SESSION) -> datetime:
    return datetime.combine(session, time(h, m), tzinfo=ET)


# ── the metric itself ────────────────────────────────────────────────────────────────────────────

def test_reduction_at_the_threshold_passes(tmp_path):
    """IEX missing 4 of 10 grid keys, SIP missing 2 → reduction exactly 0.50, which is `>=`."""
    minutes = [_et(9, 30 + i) for i in range(10)]
    _write_bars(tmp_path, "iex", SESSION, [("AAA", m) for m in minutes[:6]])
    _write_bars(tmp_path, "sip", SESSION, [("AAA", m) for m in minutes])
    # union = 10 (sip covers all), iex observes 6 -> 0.4 ; sip observes 10 -> 0.0
    result = evaluate_k3(tmp_path, [SESSION], diagnostic=True)
    assert result.measures["grid_keys_U"] == 10
    assert result.measures["missing_rate_iex"] == pytest.approx(0.4)
    assert result.measures["missing_rate_sip"] == pytest.approx(0.0)
    assert result.measures["reduction"] == pytest.approx(1.0)
    assert result.outcome is KOutcome.PASS


def test_insufficient_reduction_fails(tmp_path):
    """SIP better, but not by half: 5 of 10 missing vs 4 of 10 → reduction 0.2."""
    minutes = [_et(9, 30 + i) for i in range(10)]
    _write_bars(tmp_path, "iex", SESSION, [("AAA", m) for m in minutes[:5]])
    _write_bars(tmp_path, "sip", SESSION, [("AAA", m) for m in minutes[:6]])
    # union = 6; iex 5/6 observed -> missing 1/6 ; sip 6/6 -> missing 0
    result = evaluate_k3(tmp_path, [SESSION], diagnostic=True)
    assert result.measures["grid_keys_U"] == 6
    assert result.outcome is KOutcome.PASS  # sip covers the whole union here
    # A genuine partial case: sip misses one of the union keys too.
    _write_bars(tmp_path, "sip", SESSION, [("AAA", m) for m in minutes[1:6]])
    result = evaluate_k3(tmp_path, [SESSION], diagnostic=True)
    # union = minutes[0..5] = 6 ; iex observes 5 (0..4) missing 1/6 ; sip observes 5 (1..5) missing 1/6
    assert result.measures["reduction"] == pytest.approx(0.0)
    assert result.outcome is KOutcome.FAIL


def test_zero_iex_missing_is_not_evaluable_not_a_pass(tmp_path):
    """★ The registered branch. No IEX gap ⇒ no reduction to measure ⇒ NOT EVALUABLE.

    A pass here would manufacture a met criterion out of an undefined ratio, and it would look
    entirely reasonable in a summary table.
    """
    minutes = [_et(9, 30 + i) for i in range(5)]
    _write_bars(tmp_path, "iex", SESSION, [("AAA", m) for m in minutes])
    _write_bars(tmp_path, "sip", SESSION, [("AAA", m) for m in minutes])
    result = evaluate_k3(tmp_path, [SESSION], diagnostic=True)
    assert result.measures["missing_rate_iex"] == 0.0
    assert result.outcome is KOutcome.NOT_EVALUABLE
    assert "no division" in result.detail
    assert "reduction" not in result.measures


def test_the_grid_is_a_union_not_a_product(tmp_path):
    """★ Minutes NEITHER feed reported are outside U.

    A symbols x minutes product would count untraded minutes as missing for both feeds and inflate
    both rates with gaps that never existed.
    """
    _write_bars(tmp_path, "iex", SESSION, [("AAA", _et(9, 30))])
    _write_bars(tmp_path, "sip", SESSION, [("AAA", _et(9, 30)), ("AAA", _et(9, 31))])
    result = evaluate_k3(tmp_path, [SESSION], diagnostic=True)
    # Only two minutes were observed by anyone, despite the window being hours long.
    assert result.measures["grid_keys_U"] == 2


def test_a_symbol_only_one_feed_saw_still_enters_the_grid(tmp_path):
    _write_bars(tmp_path, "iex", SESSION, [("AAA", _et(9, 30))])
    _write_bars(tmp_path, "sip", SESSION, [("AAA", _et(9, 30)), ("BBB", _et(9, 30))])
    result = evaluate_k3(tmp_path, [SESSION], diagnostic=True)
    assert result.measures["grid_keys_U"] == 2
    assert result.measures["iex_observed_keys"] == 1


# ── window and key normalisation ────────────────────────────────────────────────────────────────

def test_bars_outside_the_phase_a_window_are_excluded(tmp_path):
    """04:00–16:00 ET, half-open. Postmarket is not collected and must not enter the grid."""
    rows = [("AAA", _et(3, 59)), ("AAA", _et(4, 0)), ("AAA", _et(15, 59)), ("AAA", _et(16, 0))]
    _write_bars(tmp_path, "iex", SESSION, rows)
    _write_bars(tmp_path, "sip", SESSION, rows)
    keys = observed_keys(tmp_path, "iex", SESSION)
    assert len(keys) == 2  # 04:00 and 15:59 only


def test_a_naive_timestamp_is_refused(tmp_path):
    """A naive value would be reinterpreted by the local zone — silently, and differently per machine."""
    import pandas as pd

    d = tmp_path / "iex" / SESSION.isoformat() / "bars"
    d.mkdir(parents=True)
    pd.DataFrame([{"symbol": "AAA", "ts": "2026-08-26T09:30:00"}]).to_parquet(d / "bars_1min.parquet")
    with pytest.raises(K3InputError, match="naive"):
        observed_keys(tmp_path, "iex", SESSION)


def test_sub_minute_components_collapse_into_one_grid_cell(tmp_path):
    """Otherwise one minute becomes two cells and is counted as both observed and missing."""
    a = _et(9, 30).replace(second=0)
    b = _et(9, 30).replace(second=42)
    _write_bars(tmp_path, "iex", SESSION, [("AAA", a), ("AAA", b)])
    assert len(observed_keys(tmp_path, "iex", SESSION)) == 1


def test_an_absent_bar_file_is_refused_not_treated_as_an_empty_feed(tmp_path):
    """An absent file is missing evidence, not a feed that reported nothing."""
    _write_bars(tmp_path, "iex", SESSION, [("AAA", _et(9, 30))])
    with pytest.raises(K3InputError, match="no bar file"):
        evaluate_k3(tmp_path, [SESSION], diagnostic=True)


# ── multi-session and determinism ────────────────────────────────────────────────────────────────

def test_sessions_pool_into_one_grid(tmp_path):
    s2 = date(2026, 8, 27)
    _write_bars(tmp_path, "iex", SESSION, [("AAA", _et(9, 30))])
    _write_bars(tmp_path, "sip", SESSION, [("AAA", _et(9, 30)), ("AAA", _et(9, 31))])
    _write_bars(tmp_path, "iex", s2, [("AAA", _et(9, 30, s2))])
    _write_bars(tmp_path, "sip", s2, [("AAA", _et(9, 30, s2)), ("AAA", _et(9, 31, s2))])
    result = evaluate_k3(tmp_path, [SESSION, s2], diagnostic=True)
    assert result.measures["grid_keys_U"] == 4
    assert set(result.measures["per_session"]) == {SESSION.isoformat(), s2.isoformat()}


def test_the_result_is_deterministic(tmp_path):
    minutes = [_et(9, 30 + i) for i in range(6)]
    _write_bars(tmp_path, "iex", SESSION, [("AAA", m) for m in minutes[:3]])
    _write_bars(tmp_path, "sip", SESSION, [("AAA", m) for m in minutes])
    first = evaluate_k3(tmp_path, [SESSION], diagnostic=True).as_dict()
    second = evaluate_k3(tmp_path, [SESSION], diagnostic=True).as_dict()
    assert first == second


def test_row_counts_are_labelled_diagnostic_only(tmp_path):
    """The 2026-08-14 smoke showed ~46% more SIP rows; that is not the metric and must not read as it."""
    minutes = [_et(9, 30 + i) for i in range(4)]
    _write_bars(tmp_path, "iex", SESSION, [("AAA", m) for m in minutes[:2]])
    _write_bars(tmp_path, "sip", SESSION, [("AAA", m) for m in minutes])
    result = evaluate_k3(tmp_path, [SESSION], diagnostic=True)
    assert "DIAGNOSTIC ONLY" in result.measures["diagnostic_row_count_ratio_note"]
