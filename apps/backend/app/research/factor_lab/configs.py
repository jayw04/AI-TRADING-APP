"""Factor Lab program configs — research programs expressed as data (plan v0.2).

This is the payoff: a program that used to be a ~400-line script is now a ``ProgramSpec``.
LOW-001 is the first; its verdict tree reproduces ``low_vol_research.py``'s A/B/C/D
exactly (B on a defensive/diversifier signal, C on a clear no-edge, else D). The remaining
programs (SEC-001 baskets, TREND-001 participation, MOM-001) land with their construction
modes in the next session, alongside the real-data equivalence acceptance test.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any

from app.research.factor_lab.spec import ProgramSpec, VerdictRule, VerdictSpec


def _defensive(m: Mapping[str, Any]) -> bool:
    """LOW-001 H2/H3 defensive signal: shallower drawdown than BOTH momentum and eqw, and
    low/negative correlation with momentum (a true defensive diversifier)."""
    corr = m["corr"] if m["corr"] is not None else 1.0
    return m["dd_vs_mom"] > 0 and m["dd_vs_eqw"] > 0 and corr < 0.5


# LOW-001 verdict tree (faithful to low_vol_research.py):
#   A if standalone edge + consistent; B if blend helps OR defensive; C if clearly no edge; else D.
_LOW_VERDICT = VerdictSpec(
    rules=(
        VerdictRule(lambda m: m["h1_real"] and m["consistent"],
                    "A - Validated", "standalone defensive book candidate -> governance -> paper"),
        VerdictRule(lambda m: m["blend_helps"] or _defensive(m),
                    "B - Diversifier / Defensive",
                    "defensive sleeve / momentum+low-vol blend candidate (evidence-gated)"),
        VerdictRule(lambda m: m["h1_ci_high"] < 0 and not _defensive(m),
                    "C - Rejected", "no edge at full breadth/cycle -> knowledge base"),
    ),
    default_outcome="D - Inconclusive",
    default_action="research debt -> broader-universe V2",
)


LOW_001 = ProgramSpec(
    id="LOW-001",
    name="Low Volatility",
    philosophy="Defensive / low-volatility anomaly",
    factor="low_vol",
    factor_params={"lookback_days": 252},
    n=200,
    start=date(2000, 1, 1),
    end=date(2026, 6, 12),
    construction="quantile",
    top_quantile=0.20,
    weighting="equal_weight",
    baseline="equal_weight",
    verdict=_LOW_VERDICT,
    notes={
        "verdict_of_record": "B - Diversifier / Defensive",
        "evidence": "docs/implementation/evidence/low_001_low_volatility/low_volatility.md",
        "hypotheses": "H1 standalone vs eqw; H2 corr+blend vs momentum; H3 downside protection",
    },
)

# --- TREND-001 (participation) -------------------------------------------------------
# The verdict tree faithful to trend_research.classify_outcome (frozen plan v0.2 §4):
# B triggers on H2 OR H3 *beyond the regime filter*; C when the benefit is subsumed by
# the regime filter (not beats_regime) or everything fails. (This is the tree whose
# earlier code-only version carried the TREND-001 verdict bug — now declared as data.)
def _trend_h3_clears(m: Mapping[str, Any]) -> bool:
    """Downside shallower than BOTH momentum and eqw AND it beats the regime filter."""
    return m["dd_vs_mom"] > 0.0 and m["dd_vs_eqw"] > 0.0 and m["beats_regime"]


def _trend_b(m: Mapping[str, Any]) -> bool:
    # (H2 blend helps OR H3 clears) AND not subsumed-by-regime-filter (= beats_regime).
    return (m["blend_helps"] or _trend_h3_clears(m)) and m["beats_regime"]


def _trend_c(m: Mapping[str, Any]) -> bool:
    subsumed = not m["beats_regime"]
    h1_hi = m["h1_ci_high"]
    all_fail = (not (m["blend_helps"] or _trend_h3_clears(m))
                and (h1_hi == h1_hi and h1_hi < 0))  # NaN-safe
    return subsumed or all_fail


_TREND_VERDICT = VerdictSpec(
    rules=(
        VerdictRule(lambda m: m["h1_real"] and m["consistent"],
                    "A - Validated",
                    "standalone trend book candidate -> governance -> paper"),
        VerdictRule(_trend_b,
                    "B - Diversifier / Defensive",
                    "participation sleeve / momentum+trend blend candidate (evidence-gated)"),
        VerdictRule(_trend_c,
                    "C - Rejected",
                    "benefit subsumed by the existing portfolio-level regime filter; per-name "
                    "trend adds nothing here -> knowledge base (validates existing machinery)"),
    ),
    default_outcome="D - Inconclusive",
    default_action="research debt -> inverse-vol / multi-window V2",
)


TREND_001 = ProgramSpec(
    id="TREND-001",
    name="Trend Following",
    philosophy="Per-name time-series trend (price > 200d SMA), cash-participation book",
    factor="trend",
    factor_params={"sma_days": 200},
    n=200,
    start=date(2000, 1, 1),
    end=date(2026, 6, 12),
    construction="participation",
    baseline="regime_filter",
    turnover_cost_bps=10.0,
    verdict=_TREND_VERDICT,
    notes={
        "verdict_of_record": "B - Diversifier / Defensive",
        "evidence": "docs/implementation/evidence/trend_001_trend_following/trend_following.md",
        "hypotheses": ("H1 standalone vs eqw; H2 corr+blend vs momentum; "
                       "H3 downside/participation beyond the portfolio-level regime filter"),
    },
)

PROGRAMS: dict[str, ProgramSpec] = {LOW_001.id: LOW_001, TREND_001.id: TREND_001}
