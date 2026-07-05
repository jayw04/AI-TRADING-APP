"""GOVCONTRACT-001 study wiring (EAD Phase 2; ADR 0037 §3.2).

Ties the reusable matched-control engine to the pre-registered GOVCONTRACT-001 verdict tree
(``…GOVCONTRACT001_Plan_v0.1.md`` §8) and provides the factor-store adapter that assembles
per-candidate matching features. The verdict + study wrapper are pure/testable; the factor
adapter is data-gated (needs the factor spine + ingested events — run, not unit-tested).
Read-only, off the order path.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from app.altdata.matched_control import (
    CandidateFeatures,
    EventPoint,
    MatchedExcessResult,
    run_matched_excess_study,
)
from app.research.factor_lab.spec import VerdictRule, VerdictSpec
from app.research.factor_lab.verdict import classify

MIN_EVENTS = 100  # pre-registered floor (plan §5) — do NOT weaken to reach it

# Pre-registered verdict tree (plan §8). Diversifier (B) is intentionally NOT auto-decided here:
# it needs the correlation-to-live-books analysis, which is data-gated — so a CI that spans zero
# defaults to Rejected with an explicit pointer to that follow-up.
GOVCONTRACT_VERDICT = VerdictSpec(
    rules=(
        VerdictRule(lambda m: m["n_benchmarked"] < MIN_EVENTS, "D - Insufficient-Data",
                    "Below the pre-registered ≥100 benchmarked-event floor; do not weaken the gates to reach it (plan §5)."),
        VerdictRule(lambda m: m["ci_low"] > 0, "A - Approved",
                    "Net excess-return 95% CI excludes zero (positive) over matched controls — residual alpha, not sector/size/liquidity/momentum beta (plan §8)."),
        VerdictRule(lambda m: m["ci_high"] < 0, "C - Rejected",
                    "Excess return over matched controls is negative (wrong-signed)."),
    ),
    default_outcome="C - Rejected",
    default_action=("No residual alpha over matched controls (CI spans zero) — the expected-and-fine "
                    "outcome per ADR 0037. A Diversifier (B) re-check requires the correlation-to-live-"
                    "books analysis (data-gated, plan §8)."),
)


def study_metrics(res: MatchedExcessResult) -> dict[str, Any]:
    return {
        "n_events": res.n_events, "n_benchmarked": res.n_benchmarked, "n_thin": res.n_thin,
        "mean_excess": res.mean_excess, "ci_low": res.ci_low, "ci_high": res.ci_high,
        "p_value": res.p_value, "hold_days": res.hold_days,
    }


def run_govcontract_study(
    events: Sequence[EventPoint], *, price_fn, feature_fn, exclude_fn=None,
    hold_days: int = 20, n_target: int = 20, min_controls: int = 10, decile_band: int = 1,
    seed: int = 17, n_resamples: int = 2000,
) -> dict[str, Any]:
    """Run the matched-control excess study and apply the pre-registered verdict tree. Returns a
    verdict-as-data Evidence dict (ADR 0026)."""
    res = run_matched_excess_study(
        events, price_fn=price_fn, feature_fn=feature_fn, exclude_fn=exclude_fn,
        hold_days=hold_days, n_target=n_target, min_controls=min_controls,
        decile_band=decile_band, seed=seed, n_resamples=n_resamples)
    metrics = study_metrics(res)
    outcome, action = classify(metrics, GOVCONTRACT_VERDICT)
    return {"program": "GOVCONTRACT-001", "hold_days": hold_days, "metrics": metrics,
            "outcome": outcome, "action": action}


# --- factor-store feature adapter (DATA-GATED — needs the factor spine; not unit-tested) -------

def _adv(factor_store: Any, ticker: str, as_of: date, lookback: int) -> float | None:
    """Average dollar volume over the trailing ``lookback`` trading days (no store accessor exists)."""
    df = factor_store.get_prices(ticker, as_of - timedelta(days=lookback * 2 + 10), as_of)
    if df is None or df.empty:
        return None
    dv = (df["close"] * df["volume"]).tail(lookback)
    return float(dv.mean()) if len(dv) else None


def factor_feature_fn(
    factor_store: Any, *, n_universe: int = 500, universe_lookback: int = 63,
    momentum_lookback: int = 126, adv_lookback: int = 63,
):
    """Build a ``feature_fn(as_of) -> list[CandidateFeatures]`` over the factor spine (Sharadar).
    Caches per as-of date (the same universe features serve every event on that date). NOTE:
    Sharadar sector/industry (not GICS); ADV computed from `sep` (no accessor). Data-gated."""
    from app.factor_data.factors.momentum import compute_momentum_batch
    from app.factor_data.universe import universe_asof

    cache: dict[date, list[CandidateFeatures]] = {}

    def feature_fn(as_of: date) -> list[CandidateFeatures]:
        if as_of in cache:
            return cache[as_of]
        tickers = universe_asof(factor_store, as_of, n=n_universe, lookback_days=universe_lookback)
        sectors = factor_store.get_sectors(tickers)
        sf1 = factor_store.get_sf1_asof(tickers, as_of)
        mom = compute_momentum_batch(factor_store, tickers, as_of, lookback_days=momentum_lookback)
        feats: list[CandidateFeatures] = []
        for t in tickers:
            mcap = (float(sf1.loc[t, "marketcap"])
                    if (hasattr(sf1, "index") and t in sf1.index and "marketcap" in sf1.columns)
                    else None)
            feats.append(CandidateFeatures(t, sectors.get(t), mcap, _adv(factor_store, t, as_of, adv_lookback), mom.get(t)))
        cache[as_of] = feats
        return feats

    return feature_fn
