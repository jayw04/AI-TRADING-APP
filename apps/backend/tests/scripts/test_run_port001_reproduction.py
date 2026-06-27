"""PORT-001 self-stack builders — the pure data-machine helpers (no data env needed).

The self-stack real-data path needs a non-Norton machine with Sharadar + Alpaca, but its
building blocks — trade counting, curve→returns, the Sharadar distributions parser — are pure
and CI-guarded here. They live in the importable ``app.research.factor_lab.reproduction`` module
(shared by the CLI harness's ``--db`` mode and the Factor Lab runner's ``_run_portfolio``)."""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.research.factor_lab.reproduction import (
    SharadarDistributions,
    count_trades,
    curve_returns,
)


def test_count_trades_counts_opens_reweights_and_closes():
    # rebalance 1 opens A+B (2); rb 2 closes B (1); rb 3 opens C (1); rb 4 reweights A (1) → 5.
    history = [{"A": 0.5, "B": 0.5}, {"A": 0.5}, {"A": 0.5, "C": 0.5}, {"A": 0.7, "C": 0.5}]
    assert count_trades(history) == 5


def test_count_trades_ignores_subthreshold_drift():
    history = [{"A": 0.5}, {"A": 0.5 + 1e-9}]   # below tol → not a trade
    assert count_trades(history) == 1           # only the initial open


def test_curve_returns_simple_returns_drop_first():
    curve = [(date(2020, 1, 1), 100.0), (date(2020, 1, 2), 110.0), (date(2020, 1, 3), 99.0)]
    r = curve_returns(curve)
    assert [round(x, 4) for x in r.tolist()] == [0.1, -0.1]
    assert len(r) == 2                            # first (no-prior) point dropped


def test_curve_returns_empty_for_short_curve():
    assert curve_returns([(date(2020, 1, 1), 100.0)]).empty


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeCon:
    """Minimal DuckDB-connection stand-in: returns canned actions rows, ignores the SQL/params."""
    def __init__(self, rows):
        self._rows = rows

    def execute(self, _sql, _params):
        return _FakeResult(self._rows)


class _FakeStore:
    def __init__(self, rows):
        self.con = _FakeCon(rows)


def test_sharadar_distributions_parses_dividends_and_splits():
    rows = [
        (date(2021, 3, 19), "dividend", 1.23),
        (date(2021, 6, 18), "Dividend", 0.50),     # case-insensitive
        (date(2021, 8, 25), "split", 4.0),         # share multiplier
        (date(2021, 9, 1), "spinoff", 5.0),        # neither div nor split → ignored
        (date(2021, 9, 2), "dividend", None),      # null value → skipped
    ]
    prov = SharadarDistributions(_FakeStore(rows))
    div, spl = prov.distributions("TLT", pd.Timestamp("2021-01-01"), pd.Timestamp("2021-12-31"))
    assert div.to_dict() == {pd.Timestamp("2021-03-19"): 1.23, pd.Timestamp("2021-06-18"): 0.50}
    assert spl.to_dict() == {pd.Timestamp("2021-08-25"): 4.0}


def test_sharadar_distributions_failsoft_on_missing_table():
    class _Boom:
        con = type("C", (), {"execute": lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError())})()

    div, spl = SharadarDistributions(_Boom()).distributions(
        "SPY", pd.Timestamp("2020-01-01"), pd.Timestamp("2020-12-31"))
    assert div.empty and spl.empty               # no actions table → price-return leg, no crash
