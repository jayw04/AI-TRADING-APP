"""Momentum math + insufficient-history handling (P9 §2 §4.2)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.factor_data.factors.momentum import compute_momentum


def _geometric(n: int, g: float, start_date: str = "2019-01-01") -> pd.DataFrame:
    """n business days of a geometric close path starting at 100.0, growth g/day."""
    bdays = pd.bdate_range(start_date, periods=n)
    price, rows = 100.0, []
    for d in bdays:
        rows.append({"date": d.strftime("%Y-%m-%d"), "close": price})
        price *= g
    return pd.DataFrame(rows)


def test_momentum_exact_on_geometric_path() -> None:
    # With constant daily growth g over a 105-day lookback ending 21 days back,
    # the 6-1 momentum is exactly g**105 - 1 (independent of the path length).
    g = 1.001
    prices = _geometric(400, g)
    as_of = pd.to_datetime(prices["date"]).max().date()
    mom = compute_momentum(prices, as_of, lookback_days=105, skip_days=21)
    assert mom == pytest.approx(g**105 - 1.0, rel=1e-9)


def test_skip_window_excludes_recent_days() -> None:
    # Make the most recent 21 days a sharp spike. With skip=21 the spike is
    # excluded, so momentum is unaffected; with skip=0 it changes.
    prices = _geometric(300, 1.0005)
    # overwrite last 10 closes with a spike
    prices.loc[prices.index[-10:], "close"] = 9999.0
    as_of = pd.to_datetime(prices["date"]).max().date()
    skipped = compute_momentum(prices, as_of, lookback_days=105, skip_days=21)
    not_skipped = compute_momentum(prices, as_of, lookback_days=105, skip_days=0)
    assert skipped is not None and not_skipped is not None
    assert skipped != pytest.approx(not_skipped)  # the spike leaks in without the skip


def test_insufficient_history_returns_none() -> None:
    prices = _geometric(50, 1.001)  # < 105 + 21 + 1 rows
    as_of = pd.to_datetime(prices["date"]).max().date()
    assert compute_momentum(prices, as_of, lookback_days=105, skip_days=21) is None


def test_no_lookahead_ignores_rows_after_as_of() -> None:
    prices = _geometric(400, 1.001)
    all_dates = pd.to_datetime(prices["date"])
    as_of = all_dates.iloc[250].date()
    mom_full = compute_momentum(prices, as_of)
    # truncating to <= as_of must not change the score (rows after as_of are ignored)
    truncated = prices.loc[all_dates <= pd.Timestamp(as_of)]
    mom_trunc = compute_momentum(truncated, as_of)
    assert mom_full == mom_trunc


def test_empty_and_nonpositive_guarded() -> None:
    assert compute_momentum(pd.DataFrame(columns=["date", "close"]), date(2020, 1, 1)) is None
    prices = _geometric(400, 1.001)
    prices.loc[prices.index[-1 - 21 - 105], "close"] = 0.0  # non-positive start endpoint
    as_of = pd.to_datetime(prices["date"]).max().date()
    assert compute_momentum(prices, as_of) is None


def test_rejects_bad_params() -> None:
    prices = _geometric(200, 1.001)
    as_of = pd.to_datetime(prices["date"]).max().date()
    with pytest.raises(ValueError):
        compute_momentum(prices, as_of, lookback_days=0)
    with pytest.raises(ValueError):
        compute_momentum(prices, as_of, skip_days=-1)
