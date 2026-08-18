"""The two frozen VALIDATION-stage gates, and nothing else.

`phase3a/MR002_Phase3A_ValidationStageDecisionSpecification_v1.0.json` -> `validation_gates`:

    validation_positive_folds_ge_3_of_5   Config B net-positive in >= 3 of 5 folds
                                          (gates_frozen.validation_positive_folds_min_of_5,
                                           positive_folds_sample = "validation, config B")
    parameter_stability_A_and_C_net_profitable
                                          Configs A and C both net-profitable
                                          (gates_frozen.parameter_stability,
                                           stability_sample = "validation")

"net-profitable" is registered in PreRegistration v0.4: "cumulative net return > 0 over the named
evaluation sample, after all registered execution, transaction-cost, and borrow assumptions".
STRICTLY greater than zero, no margin, and the same definition supplies "fold net-positive".

DELIBERATELY ABSENT, because every one of these carries sample_stage "sealed OOS" and is listed
under `oos_only_metrics_prohibited_during_validation`: net_oos_sharpe >= 0.70, the stationary
bootstrap lower bound, DSR significance, Calmar, max drawdown, net annualized return, cost stress,
breadth, trade concentration, regime gates, annual profile.

Config-A/B/C annualized net Sharpes ARE computed, but only as the frozen input to the DSR trial
dispersion artifact. `ValidationStageDecisionSpecification` is explicit that this is "NOT a
validation pass/fail".
"""

from __future__ import annotations

import math

from . import (
    INTEGRITY_FAILURE,
    NAV0,
    VALIDATION_ADVANCE_REQUEST,
    VALIDATION_DO_NOT_ADVANCE,
    VERDICT_CONFIG,
)
from .folds import FROZEN_FOLDS

POSITIVE_FOLDS_MIN_OF_5 = 3      # gates_frozen.validation_positive_folds_min_of_5


def cumulative_net_return(nav_curve: list[float], nav_start: float = NAV0) -> float:
    """The accepted convention: final NAV over starting NAV, minus one."""
    if not nav_curve:
        return 0.0
    return float(nav_curve[-1]) / float(nav_start) - 1.0


def fold_net_returns(sessions: list, nav_curve: list[float],
                     nav_start: float = NAV0) -> dict[int, dict]:
    """Per-fold cumulative net return, as the NAV ratio across the fold's sessions.

    `nav_t == nav_{t-1} * (1 + r_t)` holds exactly in the accepted roll-forward, so the NAV ratio
    and the compounded daily-return product are the same quantity; the ratio is used because it is
    the form the accepted runner already reports.
    """
    if len(sessions) != len(nav_curve):
        raise ValueError(f"sessions/nav_curve length mismatch: {len(sessions)} vs {len(nav_curve)}")

    out: dict[int, dict] = {}
    for f in FROZEN_FOLDS:
        idx = [i for i, s in enumerate(sessions) if f.first <= s <= f.last]
        if not idx:
            out[f.index] = {"fold": f.index, "sessions": 0, "net_return": None,
                            "net_positive": False, "reason": "no sessions in fold"}
            continue
        first_i, last_i = idx[0], idx[-1]
        nav_before = float(nav_curve[first_i - 1]) if first_i > 0 else float(nav_start)
        nav_end = float(nav_curve[last_i])
        ret = nav_end / nav_before - 1.0 if nav_before > 0 else 0.0
        out[f.index] = {
            "fold": f.index,
            "first": str(f.first),
            "last": str(f.last),
            "sessions": len(idx),
            "nav_before": nav_before,
            "nav_end": nav_end,
            "net_return": float(ret),
            "net_positive": bool(ret > 0.0),
        }
    return out


def annualized_net_sharpe(daily_ret: list[float]) -> float:
    """Frozen estimator: daily, arithmetic mean, simple net returns, ddof=1, x sqrt(252), rf = 0.

    NOT a validation gate. Its only sanctioned use at this stage is as the frozen input to the DSR
    trial-dispersion artifact that a later OOS stage consumes.
    """
    n = len(daily_ret)
    if n < 2:
        return 0.0
    mean = sum(daily_ret) / n
    var = sum((r - mean) ** 2 for r in daily_ret) / (n - 1)
    sd = math.sqrt(var)
    if sd <= 0.0:
        return 0.0
    return float(mean / sd * math.sqrt(252.0))


def evaluate(per_config: dict, integrity_ok: bool, integrity_detail: str = "") -> dict:
    """Apply the two frozen gates and return the validation-stage verdict.

    `per_config` maps "A"/"B"/"C" -> {"sessions": [date], "nav_curve": [float],
    "daily_ret": [float]}.

    An integrity stop short-circuits to INTEGRITY_FAILURE. A replay-definition failure is never
    reported as an economic verdict.
    """
    if not integrity_ok:
        return {
            "verdict": INTEGRITY_FAILURE,
            "reason": integrity_detail or "replay integrity not admissible",
            "gates_evaluated": False,
            "note": "an integrity stop is NEVER VALIDATION_DO_NOT_ADVANCE",
        }

    b = per_config[VERDICT_CONFIG]
    folds = fold_net_returns(b["sessions"], b["nav_curve"])
    positive = sum(1 for v in folds.values() if v["net_positive"])
    gate_folds = positive >= POSITIVE_FOLDS_MIN_OF_5

    stability = {}
    for name in ("A", "C"):
        c = per_config[name]
        ret = cumulative_net_return(c["nav_curve"])
        stability[name] = {"cumulative_net_return": ret, "net_profitable": bool(ret > 0.0)}
    gate_stability = all(v["net_profitable"] for v in stability.values())

    advance = gate_folds and gate_stability
    return {
        "verdict": VALIDATION_ADVANCE_REQUEST if advance else VALIDATION_DO_NOT_ADVANCE,
        "gates_evaluated": True,
        "gate_validation_positive_folds_ge_3_of_5": {
            "config": VERDICT_CONFIG,
            "required": POSITIVE_FOLDS_MIN_OF_5,
            "observed_positive_folds": positive,
            "passed": gate_folds,
            "per_fold": [folds[f.index] for f in FROZEN_FOLDS],
        },
        "gate_parameter_stability_A_and_C_net_profitable": {
            "rule": "cumulative net return > 0, strictly, for BOTH A and C",
            "per_config": stability,
            "passed": gate_stability,
        },
        "meaning": (
            "VALIDATION_ADVANCE_REQUEST authorizes a REQUEST for separate OOS authorization; it "
            "does NOT open OOS, does NOT evaluate any OOS gate, and is NOT a final profitability "
            "claim."
        ),
        "oos_gates_not_evaluated": [
            "net_oos_sharpe_ge_0.70", "stationary_bootstrap_lower_bound", "dsr_significance",
            "cost_stress", "calmar", "max_drawdown", "breadth", "trade_concentration",
            "regime_gates", "annual_profile",
        ],
    }
