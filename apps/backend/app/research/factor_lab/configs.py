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

PROGRAMS: dict[str, ProgramSpec] = {LOW_001.id: LOW_001}
