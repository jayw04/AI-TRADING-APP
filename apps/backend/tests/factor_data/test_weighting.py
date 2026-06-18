"""Backtester weighting extension (P10 Phase 3A §4.4): equal_weight (inert),
inverse_vol, risk_parity_diagonal — invariants, no-look-ahead, and the load-bearing
equal-weight regression guard."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.factor_data.backtest import (
    _trailing_vol,
    _weigh,
    run_momentum_backtest,
)
from app.factor_data.portfolio import PortfolioInvariantError, assert_valid_weights
from app.factor_data.store import FactorDataStore

from .conftest import build_momentum_frames

_START = date(2018, 7, 1)
_END = date(2020, 12, 31)


@pytest.fixture
def bt_store(tmp_path) -> FactorDataStore:
    sep, tk = build_momentum_frames()
    s = FactorDataStore(db_path=str(tmp_path / "bt.duckdb"))
    s.ingest_sep(sep)
    s.ingest_tickers(tk)
    yield s
    s.close()


# ---- the regression guard: equal_weight is byte-for-byte unchanged ---------------

def test_equal_weight_unchanged(bt_store: FactorDataStore) -> None:
    """★ The §5 step-2 guard: the new weighting code path with equal_weight reproduces
    the legacy book exactly — default == explicit equal_weight, and every rebalance is
    uniformly 1/k. The backtester is the eval ground truth (ADR 0014); equal_weight
    must stay inert."""
    default = run_momentum_backtest(bt_store, _START, _END, top_quantile=0.2)
    explicit = run_momentum_backtest(bt_store, _START, _END, top_quantile=0.2,
                                     weighting="equal_weight")
    assert default.equity_curve == explicit.equity_curve
    assert default.metrics == explicit.metrics
    for h in default.holdings:
        k = len(h.tickers)
        assert h.weights == pytest.approx({t: 1.0 / k for t in h.tickers})


# ---- all three methods run end-to-end and satisfy the invariants -----------------

@pytest.mark.parametrize("method", ["equal_weight", "inverse_vol", "risk_parity_diagonal"])
def test_each_weighting_runs_and_holds_invariants(bt_store: FactorDataStore, method: str) -> None:
    r = run_momentum_backtest(bt_store, _START, _END, top_quantile=0.2, weighting=method)
    assert len(r.equity_curve) > 0
    assert len(r.holdings) > 50
    for h in r.holdings:
        # the weigher already asserted these, but re-check the persisted vector
        assert_valid_weights(h.weights, cash=0.0, target_gross=1.0, long_only=True)


def test_risk_parity_diagonal_equals_inverse_vol(bt_store: FactorDataStore) -> None:
    """Gotcha 5: risk_parity_diagonal IS inverse_vol in v1 (diagonal covariance).
    Documented equality, not a bug — they must produce the identical book."""
    iv = run_momentum_backtest(bt_store, _START, _END, top_quantile=0.2, weighting="inverse_vol")
    rp = run_momentum_backtest(bt_store, _START, _END, top_quantile=0.2,
                               weighting="risk_parity_diagonal")
    assert iv.equity_curve == rp.equity_curve


def test_rejects_unknown_weighting(bt_store: FactorDataStore) -> None:
    with pytest.raises(ValueError):
        run_momentum_backtest(bt_store, _START, _END, weighting="mean_variance")


# ---- inverse_vol tilts toward the calmer name (direct _weigh unit test) -----------

def _two_vol_store(tmp_path, *, extra_days: int = 0) -> tuple[FactorDataStore, date]:
    """CALM alternates ±0.2%; WILD alternates ±5% (much higher realized vol). Both have
    a small positive drift so neither σ degenerates to zero."""
    days = [d.date() for d in pd.bdate_range("2020-01-02", periods=60 + extra_days)]
    rows = []
    calm = wild = 100.0
    for i, d in enumerate(days):
        calm *= 1.003 if i % 2 == 0 else 0.999     # ~0.2% swings
        wild *= 1.06 if i % 2 == 0 else 0.95        # ~5% swings
        for tk, px in (("CALM", calm), ("WILD", wild)):
            rows.append(dict(ticker=tk, date=d.strftime("%Y-%m-%d"), open=px, high=px,
                             low=px, close=px, volume=1_000_000, closeadj=px,
                             closeunadj=px, lastupdated="2026-01-01"))
    s = FactorDataStore(db_path=str(tmp_path / f"vol{extra_days}.duckdb"))
    s.ingest_sep(pd.DataFrame(rows))
    return s, days[59]  # the 60th day — fixed regardless of extra_days


def test_inverse_vol_overweights_low_vol_name(tmp_path) -> None:
    store, last = _two_vol_store(tmp_path)
    try:
        w = _weigh(store, ["CALM", "WILD"], last, method="inverse_vol", vol_lookback_days=20)
        assert w["CALM"] > w["WILD"]                 # 1/σ tilt toward the calm name
        assert sum(w.values()) == pytest.approx(1.0)
    finally:
        store.close()


def test_trailing_vol_no_lookahead(tmp_path) -> None:
    """★ σ at date d uses only prices strictly before d, so extending the store with
    later data never moves σ at d (mirrors test_backtest_no_lookahead_prefix_matches)."""
    short, d = _two_vol_store(tmp_path, extra_days=0)
    long, d2 = _two_vol_store(tmp_path, extra_days=40)
    assert d == d2
    try:
        v_short = _trailing_vol(short, "WILD", d, 20)
        v_long = _trailing_vol(long, "WILD", d, 20)
        assert v_short is not None and v_short > 0
        assert v_short == pytest.approx(v_long)      # future bars don't change σ at d
    finally:
        short.close()
        long.close()


def test_weigh_fallback_to_equal_when_no_history(tmp_path) -> None:
    """No price history → σ unavailable for every name → graceful equal-weight fallback,
    never a divide-by-zero or invariant violation."""
    s = FactorDataStore(db_path=str(tmp_path / "empty.duckdb"))
    s.ingest_sep(pd.DataFrame([dict(
        ticker="AAA", date="2020-01-02", open=1, high=1, low=1, close=1, volume=1,
        closeadj=1.0, closeunadj=1.0, lastupdated="2026-01-01")]))
    try:
        w = _weigh(s, ["AAA", "BBB"], date(2019, 1, 1), method="inverse_vol",
                   vol_lookback_days=20)
        assert w == pytest.approx({"AAA": 0.5, "BBB": 0.5})
    finally:
        s.close()


def test_assert_valid_weights_catches_violations() -> None:
    with pytest.raises(PortfolioInvariantError):
        assert_valid_weights({"A": 0.6, "B": 0.6})         # sums to 1.2
    with pytest.raises(PortfolioInvariantError):
        assert_valid_weights({"A": -0.1, "B": 1.1})        # negative in long-only
    with pytest.raises(PortfolioInvariantError):
        assert_valid_weights({"A": float("nan"), "B": 1.0})  # non-finite
