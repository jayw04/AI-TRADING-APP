"""PORT-001 reproduction engine (§2 reproduce-first core) — sleeve backtest + the gate runner."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.research.factor_lab.portfolio import construct_portfolio
from app.research.factor_lab.reproduction import (
    backtest_cross_asset_sleeve,
    run_reproduction,
)


def _series(n: int, drift: float, vol: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return 100.0 * np.cumprod(1.0 + drift + vol * rng.standard_normal(n))


def _panel(specs: dict[str, tuple[float, float, int]], n: int = 600) -> pd.DataFrame:
    idx = pd.date_range("2022-01-01", periods=n, freq="B")
    return pd.DataFrame({k: _series(n, d, v, s) for k, (d, v, s) in specs.items()}, index=idx)


# --------------------------------------------------------------------------- Sleeve-B backtest
def test_cross_asset_backtest_returns_daily_series_aligned_to_panel():
    panel = _panel({"SPY": (0.0008, 0.008, 1), "TLT": (0.0003, 0.006, 2),
                    "GLD": (0.0005, 0.007, 3), "UUP": (0.0001, 0.004, 4)})
    ret = backtest_cross_asset_sleeve(panel)
    assert isinstance(ret, pd.Series)
    assert ret.index.equals(panel.index)        # one return per panel day
    assert ret.notna().all()


def test_cross_asset_backtest_cash_before_first_rebalance_is_flat():
    panel = _panel({"SPY": (0.0008, 0.008, 1), "TLT": (0.0003, 0.006, 2)})
    ret = backtest_cross_asset_sleeve(panel)
    # No weights are held until the first rebalance with enough history → early returns are 0.
    assert float(ret.iloc[:252].abs().sum()) == 0.0


def test_cross_asset_backtest_all_downtrend_is_all_cash_flat():
    # Every leg trends DOWN → the sleeve is always flat → zero return throughout.
    panel = _panel({"A": (-0.0015, 0.008, 1), "B": (-0.0020, 0.006, 2)})
    ret = backtest_cross_asset_sleeve(panel)
    assert float(ret.abs().sum()) == 0.0


# --------------------------------------------------------------------------- run_reproduction
def _inputs(seed: int = 7):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2019-01-01", periods=800, freq="B")
    sleeve_returns = pd.DataFrame(
        {"equity": 0.0006 + 0.010 * rng.standard_normal(len(idx)),
         "cross_asset": 0.0004 + 0.008 * rng.standard_normal(len(idx))},
        index=idx,
    )
    internal = {"equity": {"AAPL": 0.5, "MSFT": 0.5}, "cross_asset": {"TLT": 0.6, "GLD": 0.4}}
    return sleeve_returns, internal


def _matching_reference(sleeve_returns, internal, *, trades):
    """A reference == the Workbench candidate, so the gate must pass (exercises every criterion)."""
    book = construct_portfolio(sleeve_returns, internal, equity_sleeve="equity")
    w = np.array([book.sleeve_weights[s] for s in sleeve_returns.columns])
    cand_daily = pd.Series(sleeve_returns.to_numpy() @ w, index=sleeve_returns.index)
    from app.factor_data.evidence import daily_returns as _dr  # local import
    from app.factor_data.evidence import max_drawdown, sharpe
    curve = list(zip(sleeve_returns.index.date,
                     100_000.0 * (1.0 + cand_daily).cumprod(), strict=True))
    return {
        "sharpe": sharpe(_dr(curve)), "max_drawdown": max_drawdown(curve), "trades": trades,
        "daily_returns": {d.strftime("%Y-%m-%d"): float(v) for d, v in cand_daily.items()},
        "weights": dict(book.weights),
    }, book


def test_run_reproduction_passes_against_matching_reference():
    sleeve_returns, internal = _inputs()
    reference, _ = _matching_reference(sleeve_returns, internal, trades=120)
    res = run_reproduction(
        sleeve_returns=sleeve_returns, sleeve_internal_weights=internal,
        equity_sleeve="equity", reference=reference, cand_trades=120,
    )
    assert res["passed"] is True
    sc = res["gate"]
    assert sc["fidelity_pct"] >= 99.0
    by = {c["name"]: c for c in sc["criteria"]}
    assert by["daily_return_corr"]["passed"] and by["weight_corr"]["passed"]
    assert by["determinism"]["passed"] and by["trade_count"]["passed"]


def test_run_reproduction_fails_when_trade_count_drifts():
    sleeve_returns, internal = _inputs()
    reference, _ = _matching_reference(sleeve_returns, internal, trades=100)
    res = run_reproduction(
        sleeve_returns=sleeve_returns, sleeve_internal_weights=internal,
        equity_sleeve="equity", reference=reference, cand_trades=200,  # +100% → fails ±10%
    )
    assert res["passed"] is False
    by = {c["name"]: c for c in res["gate"]["criteria"]}
    assert by["trade_count"]["passed"] is False


def test_run_reproduction_is_deterministic():
    sleeve_returns, internal = _inputs()
    reference, _ = _matching_reference(sleeve_returns, internal, trades=120)
    kw = dict(sleeve_returns=sleeve_returns, sleeve_internal_weights=internal,
              equity_sleeve="equity", reference=reference, cand_trades=120)
    a = run_reproduction(**kw)
    b = run_reproduction(**kw)
    assert a["candidate"] == b["candidate"]
    assert a["gate"]["fidelity_pct"] == b["gate"]["fidelity_pct"]
