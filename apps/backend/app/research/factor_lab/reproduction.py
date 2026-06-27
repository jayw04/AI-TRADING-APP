"""PORT-001 reproduction engine (the §2 reproduce-first core; ADR 0030 #4).

Turns the built-but-data-gated PCE into a runnable reproduction: backtest each sleeve into a
daily return series, ERC-blend them into the Workbench Evidence Package, and compare it to the
**sibling reference** through the objective **Onboarding Gate**. On pass (within tolerance,
drift attributed), the capability advances L1→L2.

Pure / deterministic over the inputs:
  - ``backtest_cross_asset_sleeve`` rolls the §1 cross-asset TSMOM sleeve over a total-return
    panel → its daily return series (tested with a synthetic panel).
  - ``run_reproduction`` blends the sleeve return series + compares to the reference (tested
    with synthetic sleeves + a matching reference).

The *real* sleeve return series (equity momentum over the Sharadar store; cross-asset over the
§1 Total-Return Adapter) are built by the CLI harness `scripts/run_port001_reproduction.py` on
a non-Norton machine with the data. This module is the engine that harness drives.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.research.factor_lab.cross_asset import cross_asset_tsmom
from app.research.factor_lab.onboarding_gate import GateResult, onboarding_gate
from app.research.factor_lab.portfolio import construct_portfolio, portfolio_evidence_package
from app.research.factor_lab.spec import VerdictSpec


def cross_asset_rebalance_weights(
    panel: pd.DataFrame, *, rebalance_freq: str = "W-FRI", **sleeve_kwargs: Any
) -> pd.DataFrame:
    """Per-rebalance as-of sleeve weights (rows = panel dates, cols = tickers): the cross-asset
    TSMOM weights recomputed at each rebalance date, NaN before the first qualifying rebalance.
    The basis for both ``backtest_cross_asset_sleeve`` (ffill → held weights) and the harness's
    internal-weights/trade-count needs. Pure."""
    px = panel.sort_index()
    cols = list(px.columns)
    reb_dates = pd.Series(px.index, index=px.index).resample(rebalance_freq).last().dropna()
    weights = pd.DataFrame(index=px.index, columns=cols, dtype=float)  # NaN until first rebalance
    for d in reb_dates:
        pos = int(px.index.get_loc(d))
        sleeve = cross_asset_tsmom(px, asof=pos, **sleeve_kwargs)
        if sleeve.status == "ok":
            weights.loc[d] = [sleeve.weights.get(c, 0.0) for c in cols]
    return weights


def backtest_cross_asset_sleeve(
    panel: pd.DataFrame, *, rebalance_freq: str = "W-FRI", **sleeve_kwargs: Any
) -> pd.Series:
    """Roll the cross-asset TSMOM sleeve over a **total-return** price panel → the sleeve's daily
    return series. At each rebalance date the as-of weights are computed and held until the next
    rebalance; daily return = Σ (prior-day weights × asset daily total-returns). Pure."""
    px = panel.sort_index()
    rets = px.pct_change().fillna(0.0)
    weights = cross_asset_rebalance_weights(px, rebalance_freq=rebalance_freq, **sleeve_kwargs)
    weights = weights.ffill().fillna(0.0)  # hold weights between rebalances; cash before the first
    return (weights.shift(1).fillna(0.0) * rets).sum(axis=1)


def _aligned(ref: dict[str, float], cand: dict[str, float]) -> tuple[np.ndarray, np.ndarray]:
    """Align two {symbol: weight} maps onto the union of symbols (absent → 0) for weight corr.
    Symbol keys are upper-cased first: ``construct_portfolio`` canonicalizes tickers to upper
    case, so a reference keyed in any case must still align (else identical books anti-correlate)."""
    ru = {str(k).upper(): float(v) for k, v in ref.items()}
    cu = {str(k).upper(): float(v) for k, v in cand.items()}
    keys = sorted(set(ru) | set(cu))
    return (np.array([ru.get(k, 0.0) for k in keys]),
            np.array([cu.get(k, 0.0) for k in keys]))


def run_reproduction(
    *,
    sleeve_returns: pd.DataFrame,
    sleeve_internal_weights: dict[str, dict[str, float]],
    equity_sleeve: str,
    reference: dict[str, Any],
    cand_trades: int,
    regime: str = "GREEN",
    initial_equity: float = 100_000.0,
    deterministic: bool = True,
    verdict: VerdictSpec | None = None,
) -> dict[str, Any]:
    """Build the Workbench Evidence Package from the sleeve returns and run the Onboarding Gate
    against the sibling ``reference`` (keys: ``sharpe``, ``max_drawdown``, ``trades``,
    ``daily_returns`` {date: ret}, ``weights`` {symbol: weight}). Returns the package, the gate
    result, and the pass/fail. Pure/deterministic."""
    pkg = portfolio_evidence_package(
        sleeve_returns, sleeve_internal_weights, equity_sleeve=equity_sleeve,
        regime=regime, initial_equity=initial_equity, verdict=verdict,
    )
    m = pkg["metrics"]

    # the Workbench combined daily-return series (for the daily-return correlation criterion)
    book = construct_portfolio(
        sleeve_returns, sleeve_internal_weights, equity_sleeve=equity_sleeve, regime=regime,
    )
    cols = list(sleeve_returns.columns)
    w = np.array([book.sleeve_weights.get(s, 0.0) for s in cols], dtype=float)
    cand_daily = pd.Series(
        book.regime_multiplier * (sleeve_returns[cols].to_numpy(dtype=float) @ w),
        index=sleeve_returns.index,
    )

    ref_w, cand_w = _aligned(reference.get("weights", {}), book.weights)
    ref_daily = pd.Series(reference.get("daily_returns", {}), dtype=float)
    if not ref_daily.empty:
        ref_daily.index = pd.to_datetime(ref_daily.index)  # align ISO-date keys to cand timestamps
    gate: GateResult = onboarding_gate(
        ref_sharpe=float(reference["sharpe"]), cand_sharpe=float(m["sharpe"]),
        # compare drawdown MAGNITUDES — be robust to the caller's sign convention (the candidate
        # package reports max_drawdown as a negative fraction; references may be either sign).
        ref_maxdd=abs(float(reference["max_drawdown"])), cand_maxdd=abs(float(m["max_drawdown"])),
        ref_daily_returns=ref_daily,
        cand_daily_returns=cand_daily,
        ref_weights=ref_w, cand_weights=cand_w,
        ref_trades=int(reference["trades"]), cand_trades=int(cand_trades),
        deterministic=deterministic,
    )
    return {
        "evidence_package": pkg,
        "gate": gate.as_scorecard(),
        "passed": gate.passed,
        "candidate": {"sharpe": m["sharpe"], "max_drawdown": m["max_drawdown"],
                      "trades": int(cand_trades)},
        "reference": {"sharpe": reference["sharpe"], "max_drawdown": reference["max_drawdown"],
                      "trades": reference["trades"]},
    }
