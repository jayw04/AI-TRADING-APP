"""Onboarding Gate + Lifecycle Fidelity scorecard (ADR 0030 #4; plan §Gate).

The objective bar a capability must clear to be promoted from *reproduction* to a live
paper book. Promotion is **measurable, not a judgment call**: the platform's Workbench
reproduction is compared to the origin (sibling) book and must match within tolerance on
every criterion. The standout checks are **daily-return correlation** (proves it is the
*same* book, not merely similar summary stats) and **determinism** (identical inputs →
identical outputs). A miss is *attributed*, not waived.

Pure / deterministic. Emits the **Lifecycle Fidelity** scorecard (a composite closeness
score that drills into each criterion) — the onboarding's own evidence artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# Default tolerances (ADR 0030 #4 / plan §Gate). Turnover/trade-count tol is a fraction.
SHARPE_TOL = 0.05
MAXDD_TOL = 0.02            # 2.0 percentage points
RETURN_CORR_MIN = 0.98
WEIGHT_CORR_MIN = 0.99
TRADE_TOL_FRAC = 0.10      # trade count within ±10% of the reference


@dataclass(frozen=True)
class Criterion:
    name: str
    passed: bool
    value: float
    threshold: float
    closeness: float           # [0, 1] — how close to the reference (1 = identical)


@dataclass(frozen=True)
class GateResult:
    passed: bool                       # ALL criteria pass
    fidelity: float                    # composite Lifecycle Fidelity score [0, 1]
    criteria: list[Criterion]
    notes: list[str] = field(default_factory=list)

    def as_scorecard(self) -> dict[str, object]:
        """Customer-legible dict for the Evidence Dashboard / Capability Certificate."""
        return {
            "passed": self.passed,
            "fidelity_pct": round(100.0 * self.fidelity, 1),
            "criteria": [
                {"name": c.name, "passed": c.passed, "value": round(c.value, 6),
                 "threshold": c.threshold} for c in self.criteria
            ],
            "notes": list(self.notes),
        }


def _corr(a: pd.Series, b: pd.Series) -> float:
    """Pearson correlation over the aligned, jointly-present points; NaN-safe → 0.0."""
    df = pd.concat([pd.Series(a), pd.Series(b)], axis=1, join="inner").dropna()
    if len(df) < 2:
        return 0.0
    c = float(np.corrcoef(df.iloc[:, 0], df.iloc[:, 1])[0, 1])
    return 0.0 if np.isnan(c) else c


def onboarding_gate(
    *,
    ref_sharpe: float, cand_sharpe: float,
    ref_maxdd: float, cand_maxdd: float,            # positive fractions, e.g. 0.119
    ref_daily_returns: pd.Series, cand_daily_returns: pd.Series,
    ref_weights: pd.Series | np.ndarray, cand_weights: pd.Series | np.ndarray,
    ref_trades: int, cand_trades: int,
    deterministic: bool,
    sharpe_tol: float = SHARPE_TOL, maxdd_tol: float = MAXDD_TOL,
    return_corr_min: float = RETURN_CORR_MIN, weight_corr_min: float = WEIGHT_CORR_MIN,
    trade_tol_frac: float = TRADE_TOL_FRAC,
) -> GateResult:
    """Compare a Workbench reproduction (``cand``) to the origin book (``ref``)."""
    d_sharpe = abs(cand_sharpe - ref_sharpe)
    d_maxdd = abs(cand_maxdd - ref_maxdd)
    ret_corr = _corr(pd.Series(ref_daily_returns), pd.Series(cand_daily_returns))
    w_corr = _corr(pd.Series(np.asarray(ref_weights, dtype=float).ravel()),
                   pd.Series(np.asarray(cand_weights, dtype=float).ravel()))
    trade_ref = max(1, int(ref_trades))
    d_trades_frac = abs(cand_trades - ref_trades) / trade_ref

    criteria = [
        Criterion("sharpe", d_sharpe <= sharpe_tol, d_sharpe, sharpe_tol,
                  max(0.0, 1.0 - d_sharpe / sharpe_tol) if sharpe_tol else 0.0),
        Criterion("maxdd", d_maxdd <= maxdd_tol, d_maxdd, maxdd_tol,
                  max(0.0, 1.0 - d_maxdd / maxdd_tol) if maxdd_tol else 0.0),
        Criterion("daily_return_corr", ret_corr >= return_corr_min, ret_corr, return_corr_min,
                  max(0.0, min(1.0, ret_corr))),
        Criterion("weight_corr", w_corr >= weight_corr_min, w_corr, weight_corr_min,
                  max(0.0, min(1.0, w_corr))),
        Criterion("trade_count", d_trades_frac <= trade_tol_frac, d_trades_frac, trade_tol_frac,
                  max(0.0, 1.0 - d_trades_frac / trade_tol_frac) if trade_tol_frac else 0.0),
        Criterion("determinism", bool(deterministic), 1.0 if deterministic else 0.0, 1.0,
                  1.0 if deterministic else 0.0),
    ]
    passed = all(c.passed for c in criteria)
    fidelity = float(np.mean([c.closeness for c in criteria]))
    notes: list[str] = []
    for c in criteria:
        if not c.passed:
            notes.append(f"FAIL {c.name}: {c.value:.4f} vs threshold {c.threshold} — attribute the drift")
    return GateResult(passed=passed, fidelity=fidelity, criteria=criteria, notes=notes)
