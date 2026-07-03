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

from app.research.factor_lab.spec import (
    PortfolioSpec,
    ProgramSpec,
    SleeveSpec,
    VerdictRule,
    VerdictSpec,
)


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

# --- SEC-001 (sector_baskets) --------------------------------------------------------
# The verdict tree faithful to sector_rotation_v2_research.py: A if the V2 baskets beat
# the all-sector-baskets control (H1) consistently; B if the momentum+sector blend helps
# (or V2 is shallower-drawdown AND low-correlation); C if H1 clearly excludes a positive
# edge; else D. The runner assembles `blend_helps` (incl. the maxDD/corr fallback), so
# the tree only reads flat metrics. `h1_ci_high` is the all-sector-control CI's high.
_SEC_VERDICT = VerdictSpec(
    rules=(
        VerdictRule(lambda m: m["h1_real"] and m["consistent"],
                    "A — Validated standalone",
                    "construction turned B->A: standalone Strategy #2 candidate -> "
                    "governance -> paper"),
        VerdictRule(lambda m: m["blend_helps"],
                    "B — Diversifier (confirmed)",
                    "momentum+sector blend / overlay candidate (evidence-gated)"),
        VerdictRule(lambda m: m["h1_ci_high"] < 0,
                    "C — Rejected", "no edge; archive as a knowledge-base evidence package"),
    ),
    default_outcome="D — Inconclusive",
    default_action="research debt",
)


SEC_001 = ProgramSpec(
    id="SEC-001",
    name="Sector Rotation (V2 pure baskets)",
    philosophy="Sector-neutral top-K equal-weight baskets on 12-1 sector momentum",
    factor="sector_momentum",
    factor_params={"lookback_days": 252, "skip_days": 21, "k": 3, "k_band": [2, 4]},
    n=200,
    start=date(2000, 1, 1),
    end=date(2026, 6, 12),
    construction="sector_baskets",
    top_quantile=0.20,            # the V1 stock-level construction quantile (H3 isolation)
    weighting="equal_weight",
    baseline="equal_weight",      # the continuity benchmark (the H1 control is all-sector)
    turnover_cost_bps=10.0,
    verdict=_SEC_VERDICT,
    notes={
        "verdict_of_record": "B - Diversifier",
        "evidence": ("docs/implementation/evidence/sec_001_v2_pure_baskets/"
                     "sector_rotation_v2.md"),
        "hypotheses": ("H1 V2 vs all-sector baskets (primary) + vs eqw universe; "
                       "H2 corr(sector,single-name momentum)+blend; "
                       "H3 V2-vs-V1 construction isolation (read-only, stopping rule)"),
    },
)

# PORT-001 verdict — a portfolio program, not a standalone-edge factor program: the verdict is
# DESCRIPTIVE (crash-protected beta + diversification, alpha refuted under PIT — spec §6), and
# flags the #1 operational risk (the diversification thesis weakening, spec §6.1).
_PORT_VERDICT = VerdictSpec(
    rules=(
        VerdictRule(
            lambda m: (m.get("sleeve_correlation") or 0.0) > 0.8,
            "B - Diversifier (correlation weakening)",
            "diversification thinning (sleeve corr > 0.8) -> re-weight toward surviving "
            "diversifiers (spec §6.1 / §11.1)",
        ),
    ),
    default_outcome="B - Diversifier (crash-protected beta)",
    default_action="risk-managed beta; alpha refuted under PIT -> size as crash-protected beta",
)


# PORT-001 "Risk-Balanced Multi-Asset Portfolio" (the Combined Book), onboarded from the
# sibling system. Multi-sleeve ERC (ADR 0030 #1); the equity sleeve's crash engine rides the
# ADR-0020 daily overlay live (§4). `factor` carries the equity sleeve's factor for continuity;
# construction="portfolio" routes to the Portfolio Construction Engine.
PORT_001 = ProgramSpec(
    id="PORT-001",
    name="Risk-Balanced Multi-Asset Portfolio",
    philosophy="Multi-sleeve ERC: crash-protected equity momentum + cross-asset TSMOM",
    factor="momentum",
    factor_params={"lookback_days": 252, "skip_days": 21},
    n=150,  # the sibling production equity universe (max_names=150); reproduce current config first
    start=date(2016, 1, 1),
    end=date(2026, 1, 1),
    construction="portfolio",
    portfolio=PortfolioSpec(
        sleeves=(
            SleeveSpec("equity", "equity_momentum", {
                "lookback_days": 252, "skip_days": 21, "top_quantile": 0.40,
                "max_position_pct": 0.04, "max_sector_pct": 0.25, "vol_target": 0.12,
            }),
            SleeveSpec("cross_asset", "cross_asset_tsmom", {
                "lookback": 252, "skip": 21, "vol_lookback": 60, "vol_target": 0.10,
                # v1.1 refresh (§5.6/§11 #1): 9-asset universe (+KMLM, via CROSS_ASSET_UNIVERSE) +
                # correlation-aware tilt λ=0.5 — matches the live combined-book template.
                "corr_aware": True, "corr_lambda": 0.5,
            }),
        ),
        equity_sleeve="equity",
    ),
    verdict=_PORT_VERDICT,
    notes={
        "honest_verdict": "crash-protected BETA + diversification, NOT alpha (combined alpha "
                          "t=0.82 insignificant; stock-selection alpha refuted under PIT, spec §6.4)",
        "onboarding": "reproduce-first; status 'planned' until the Onboarding Gate passes (ADR 0030)",
    },
)


PROGRAMS: dict[str, ProgramSpec] = {
    LOW_001.id: LOW_001, TREND_001.id: TREND_001, SEC_001.id: SEC_001,
    PORT_001.id: PORT_001,
}
