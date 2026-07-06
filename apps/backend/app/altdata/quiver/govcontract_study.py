"""GOVCONTRACT-001 study — Primary → Sensitivity → Decision (EAD Phase 2; ADR 0037 §3.2).

Pre-registration v0.2 structure:

  CALIBRATION PARAMETERS (locked; NOT adjusted unless the study terminates Insufficient Evidence):
    - disclosure lag = 21 trading-calendar days (in the ingested available_time; see govcontracts.py)
    - materiality    = award ≥ 0.25% of market-cap (as-of available_time) AND ≥ $250k absolute
    - transaction cost = 10 bps per side

  DECISION GATES (pre-registered):
    - ≥ 100 eligible, de-overlapped, material, benchmarked events  (< 100 ⇒ Insufficient Evidence)
    - the 95% CI on the NET matched-control excess return excludes zero
    - Benjamini-Hochberg FDR ≤ 0.10 across the holding-window family

  ORDER: the verdict comes from the PRIMARY analysis. SENSITIVITY is one-factor-at-a-time over
  {disclosure lag, cost, holding period} and asks only "would a reasonable alternative flip the
  conclusion?" — never "which parameter gives the best result." Materiality is a single locked
  threshold (no sweep — that would be data dredging). Read-only, off the order path.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.altdata.events.store import CorporateEvent
from app.altdata.matched_control import (
    CandidateFeatures,
    EventPoint,
    MatchedExcessResult,
    run_matched_excess_study,
)
from app.research.factor_lab.spec import VerdictRule, VerdictSpec
from app.research.factor_lab.verdict import classify

# --- decision gates (pre-registered) ---------------------------------------------------------
MIN_EVENTS = 100
TARGET_EVENTS = 150
FDR_Q = 0.10

# --- calibration parameters (pre-registered; locked v0.2) ------------------------------------
DISCLOSURE_LAG_PRIMARY = 21
MATERIALITY_PCT_MKTCAP = 0.0025      # 0.25%
MATERIALITY_ABS_USD = 250_000.0
COST_PRIMARY_BPS = 10.0
HOLD_PRIMARY = 20

# --- sensitivity grid (one-factor-at-a-time from the primary; NOT a cross-product) -----------
LAG_SENSITIVITY = (14, 46)
COST_SENSITIVITY_BPS = (20.0,)
HOLD_SENSITIVITY = (5, 10, 60)

MktCapFn = Callable[[str, date], "float | None"]

# Verdict tree — evaluated on the PRIMARY analysis only. "Insufficient Evidence" is a first-class
# pre-registered outcome (event-count gate), not a fallback.
GOVCONTRACT_VERDICT = VerdictSpec(
    rules=(
        VerdictRule(lambda m: m["n_benchmarked"] < MIN_EVENTS, "Insufficient Evidence",
                    "Below the pre-registered ≥100 benchmarked-event gate; the study terminates here. "
                    "Do NOT relax materiality to reach it (pre-registration v0.2, plan §5)."),
        VerdictRule(lambda m: m["ci_low"] > 0, "Approved",
                    "95% CI on the NET matched-control excess return excludes zero (positive) — residual "
                    "alpha, not sector/size/liquidity/momentum beta (plan §8)."),
        VerdictRule(lambda m: m["ci_high"] < 0, "Rejected",
                    "NET excess return over matched controls is negative (wrong-signed)."),
    ),
    default_outcome="Rejected",
    default_action=("NET excess-return CI spans zero — no residual alpha over matched controls (the "
                    "expected-and-fine outcome per ADR 0037). A Diversifier re-check needs the "
                    "correlation-to-live-books analysis (data-gated, plan §8)."),
)


def is_material(amount: Any, market_cap: float | None, *, pct: float = MATERIALITY_PCT_MKTCAP,
                abs_usd: float = MATERIALITY_ABS_USD) -> bool:
    """Locked materiality: award ≥ ``pct`` of market cap AND ≥ ``abs_usd``. Unknown market cap ⇒
    cannot assess relative materiality ⇒ excluded (conservative)."""
    if amount is None or float(amount) < abs_usd:
        return False
    if not market_cap or market_cap <= 0:
        return False
    return float(amount) >= pct * market_cap


def filter_material(events: Sequence[CorporateEvent], *, mktcap_fn: MktCapFn,
                    lag_days: int = DISCLOSURE_LAG_PRIMARY) -> list[CorporateEvent]:
    """Keep only events clearing the locked materiality threshold (market cap looked up as-of the
    event's available_time = event_date + lag)."""
    kept: list[CorporateEvent] = []
    for ev in events:
        if ev.event_date is None or not ev.ticker:
            continue
        entry = ev.event_date + timedelta(days=lag_days)
        if is_material((ev.payload or {}).get("amount"), mktcap_fn(ev.ticker, entry)):
            kept.append(ev)
    return kept


def _points(events: Sequence[CorporateEvent], lag_days: int) -> list[EventPoint]:
    """Re-time material events to EventPoints at a given disclosure lag (entry = event_date + lag)."""
    return [EventPoint(ev.ticker or "", ev.event_date + timedelta(days=lag_days))
            for ev in events if ev.event_date and ev.ticker]


def _metrics(res: MatchedExcessResult) -> dict[str, Any]:
    return {"n_benchmarked": res.n_benchmarked, "ci_low": res.ci_low, "ci_high": res.ci_high,
            "mean_excess": res.mean_excess, "mean_excess_gross": res.mean_excess_gross}


@dataclass(frozen=True)
class SensitivityRow:
    dimension: str          # 'disclosure_lag' | 'cost_bps' | 'holding_days'
    value: float
    n_benchmarked: int
    mean_excess: float
    ci_low: float
    ci_high: float
    p_value: float
    significant_positive: bool


def run_primary(events: Sequence[CorporateEvent], *, price_fn, feature_fn, exclude_fn=None,
                lag_days: int = DISCLOSURE_LAG_PRIMARY, hold_days: int = HOLD_PRIMARY,
                cost_bps: float = COST_PRIMARY_BPS, n_resamples: int = 2000, **kw) -> dict[str, Any]:
    """Primary analysis at the locked calibration (lag 21, hold 20, cost 10bps) → verdict."""
    res = run_matched_excess_study(
        _points(events, lag_days), price_fn=price_fn, feature_fn=feature_fn, exclude_fn=exclude_fn,
        hold_days=hold_days, cost_bps_per_side=cost_bps, n_resamples=n_resamples, **kw)
    outcome, action = classify(_metrics(res), GOVCONTRACT_VERDICT)
    return {"result": res, "metrics": _metrics(res), "outcome": outcome, "action": action,
            "lag_days": lag_days, "hold_days": hold_days, "cost_bps": cost_bps,
            "target_events": TARGET_EVENTS, "min_events": MIN_EVENTS}


def run_sensitivity(events: Sequence[CorporateEvent], *, price_fn, feature_fn, exclude_fn=None,
                    n_resamples: int = 2000, **kw) -> dict[str, Any]:
    """One-factor-at-a-time sensitivity from the primary, plus BH-FDR across the holding-window
    family. Confirmation only — never feeds the verdict."""
    rows: list[SensitivityRow] = []

    def _run(dim: str, value: float, *, lag: int, hold: int, cost: float) -> SensitivityRow:
        r = run_matched_excess_study(
            _points(events, lag), price_fn=price_fn, feature_fn=feature_fn, exclude_fn=exclude_fn,
            hold_days=hold, cost_bps_per_side=cost, n_resamples=n_resamples, **kw)
        return SensitivityRow(dim, value, r.n_benchmarked, r.mean_excess, r.ci_low, r.ci_high,
                              r.p_value, r.n_benchmarked >= 2 and r.ci_low > 0)

    for lag in LAG_SENSITIVITY:
        rows.append(_run("disclosure_lag", lag, lag=lag, hold=HOLD_PRIMARY, cost=COST_PRIMARY_BPS))
    for cost in COST_SENSITIVITY_BPS:
        rows.append(_run("cost_bps", cost, lag=DISCLOSURE_LAG_PRIMARY, hold=HOLD_PRIMARY, cost=cost))
    hold_rows = [_run("holding_days", float(h), lag=DISCLOSURE_LAG_PRIMARY, hold=h,
                      cost=COST_PRIMARY_BPS) for h in (HOLD_PRIMARY, *HOLD_SENSITIVITY)]
    rows.extend(r for r in hold_rows if r.value != HOLD_PRIMARY)

    # BH-FDR across the holding-window family {primary 20, 5, 10, 60}
    n_survive = _bh_survivors([r.p_value for r in hold_rows], q=FDR_Q)
    return {"rows": rows, "fdr_q": FDR_Q, "holding_family_n": len(hold_rows),
            "holding_family_fdr_survivors": n_survive}


def _bh_survivors(pvalues: Sequence[float], *, q: float) -> int:
    """Benjamini-Hochberg: number of hypotheses rejected at FDR ≤ q."""
    m = len(pvalues)
    if m == 0:
        return 0
    ordered = sorted(pvalues)
    survive = 0
    for i, p in enumerate(ordered, start=1):
        if p <= (i / m) * q:
            survive = i
    return survive


def is_robust(primary_outcome: str, sensitivity: dict[str, Any]) -> bool:
    """Would a reasonable alternative flip the conclusion? For an Approved primary, robust ⇔ every
    OFAT alternative still shows a significant positive net excess. For a non-Approved primary,
    robust ⇔ no alternative manufactures a significant positive edge. (One-directional: robustness
    can only *confirm* or *caveat*, never upgrade — no cherry-picking.)"""
    sig = [r.significant_positive for r in sensitivity["rows"]]
    if primary_outcome == "Approved":
        return all(sig)
    return not any(sig)


# --- factor-store adapters (DATA-GATED — need the factor spine; not unit-tested) --------------

def _adv(factor_store: Any, ticker: str, as_of: date, lookback: int) -> float | None:
    """Average dollar volume over the trailing ``lookback`` trading days (no store accessor)."""
    df = factor_store.get_prices(ticker, as_of - timedelta(days=lookback * 2 + 10), as_of)
    if df is None or df.empty:
        return None
    dv = (df["close"] * df["volume"]).tail(lookback)
    return float(dv.mean()) if len(dv) else None


def factor_feature_fn(factor_store: Any, *, n_universe: int = 500, universe_lookback: int = 63,
                      momentum_lookback: int = 126, adv_lookback: int = 63):
    """``feature_fn(as_of) -> list[CandidateFeatures]`` over the factor spine (Sharadar sector, not
    GICS; ADV computed from ``sep``). Cached per as-of date. Data-gated."""
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


def factor_mktcap_fn(factor_store: Any) -> MktCapFn:
    """``mktcap_fn(ticker, as_of) -> market cap | None`` from the factor spine, for the materiality
    filter. Cached per (ticker, as_of). Data-gated."""
    cache: dict[tuple[str, date], float | None] = {}

    def mktcap_fn(ticker: str, as_of: date) -> float | None:
        key = (ticker, as_of)
        if key in cache:
            return cache[key]
        try:
            df = factor_store.get_sf1_asof([ticker], as_of)
            v = (float(df.loc[ticker, "marketcap"])
                 if (hasattr(df, "index") and ticker in df.index and "marketcap" in df.columns)
                 else None)
        except Exception:  # noqa: BLE001 — missing fundamentals ⇒ unknown mcap ⇒ event excluded
            v = None
        cache[key] = v
        return v

    return mktcap_fn
