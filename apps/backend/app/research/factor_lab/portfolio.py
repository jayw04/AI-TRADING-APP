"""Portfolio Construction Engine — multi-sleeve blend + de-risk overlay + look-through evidence.

The PCE (ADR 0030 #1) is what makes PORT-001 different from single-sleeve LOW/MOM/SEC: it
blends independently-built sleeves at **equal-risk-contribution** into one book, applies the
**correlation-regime de-risk overlay**, and emits **portfolio-level evidence** the
single-factor Evidence Package lacks (gap G4) — sleeve correlation (spec §6.1, the #1 risk)
and the equity sleeve's **look-through risk-contribution fraction** (spec §6.2: ~13% of
capital but the majority of risk — the capability's most important disclosure).

Pure / deterministic over sleeve return series + each sleeve's internal weights. The
equity sleeve's crash engine rides the ADR-0020 daily overlay (live, §4); here we model only
the whole-book **correlation-regime** gross multiplier (de-risk only, never levers up).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.research.factor_lab.erc import erc_weights, risk_contributions

# Correlation-regime → whole-book gross multiplier (spec §3.3; de-risk only, never > 1.0).
REGIME_GROSS: dict[str, float] = {"GREEN": 1.0, "AMBER": 1.0, "RED": 0.6, "BLACK": 0.3}


@dataclass(frozen=True)
class PortfolioBook:
    weights: dict[str, float]            # combined book weight per symbol (post-overlay)
    sleeve_weights: dict[str, float]     # ERC sleeve weights (pre-overlay)
    gross: float                         # total invested fraction after the regime overlay
    regime: str                          # correlation-regime label applied
    regime_multiplier: float             # the de-risk gross multiplier
    sleeve_risk_contributions: dict[str, float]   # normalized RC per sleeve (sum 1)
    sleeve_correlation: float | None     # equity-vs-rest sleeve corr (None if <2 sleeves)
    equity_risk_fraction: float | None   # look-through: equity sleeve's share of total risk
    notes: list[str] = field(default_factory=list)


def regime_gross_multiplier(regime: str) -> float:
    """De-risk-only gross multiplier for a correlation regime; unknown → 1.0 (no de-risk)."""
    return REGIME_GROSS.get(str(regime).upper(), 1.0)


def construct_portfolio(
    sleeve_returns: pd.DataFrame,
    sleeve_internal_weights: dict[str, dict[str, float]],
    *,
    equity_sleeve: str,
    budgets: dict[str, float] | None = None,
    regime: str = "GREEN",
) -> PortfolioBook:
    """Blend sleeves at ERC into one book + apply the regime de-risk overlay + emit evidence.

    ``sleeve_returns`` — daily returns, columns = sleeve names. ``sleeve_internal_weights`` —
    per-sleeve {symbol: weight} (each sleeve's internal weights already carry its own de-risk
    gross). ``equity_sleeve`` — the column name of the equity sleeve (for the look-through
    metric). ``budgets`` — optional per-sleeve risk budget (default ERC = equal).
    """
    sleeves = list(sleeve_returns.columns)
    if not sleeves:
        return PortfolioBook({}, {}, 0.0, regime, regime_gross_multiplier(regime),
                             {}, None, None, notes=["no sleeves"])

    cov = sleeve_returns.cov().to_numpy()  # daily sleeve covariance
    b = None
    if budgets is not None:
        b = np.array([budgets[s] for s in sleeves], dtype=float)
    w = erc_weights(cov, b)
    sleeve_w = {s: float(wi) for s, wi in zip(sleeves, w, strict=True)}
    rc = risk_contributions(cov, w)
    sleeve_rc = {s: float(r) for s, r in zip(sleeves, rc, strict=True)}

    # --- combine sleeves into one book (net cross-sleeve names) ---
    book: dict[str, float] = defaultdict(float)
    for sleeve, iw in sleeve_internal_weights.items():
        sw = sleeve_w.get(sleeve, 0.0)
        for sym, wt in iw.items():
            book[str(sym).upper()] += sw * float(wt)

    # --- whole-book correlation-regime de-risk (never levers up) ---
    g = regime_gross_multiplier(regime)
    weights = {s: wt * g for s, wt in book.items()}
    gross = float(sum(weights.values()))

    # --- look-through evidence (gap G4) ---
    sleeve_corr = None
    if len(sleeves) >= 2 and equity_sleeve in sleeves:
        others = [s for s in sleeves if s != equity_sleeve]
        corr = sleeve_returns.corr()
        sleeve_corr = float(corr.loc[equity_sleeve, others].mean())
    equity_rc = sleeve_rc.get(equity_sleeve) if equity_sleeve in sleeves else None

    return PortfolioBook(
        weights=dict(weights), sleeve_weights=sleeve_w, gross=gross, regime=str(regime).upper(),
        regime_multiplier=g, sleeve_risk_contributions=sleeve_rc,
        sleeve_correlation=sleeve_corr, equity_risk_fraction=equity_rc,
    )
