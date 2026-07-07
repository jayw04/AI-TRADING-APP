"""LOBBY-001 study — lobbying spend-spike matched-control excess, date-clustered (EAD Phase 2; ADR 0037 §3.2).

The ``lobby_spike`` events (built in Phase 1) are already the firm-quarter spike units, each with a
PIT ``available_time`` = the quarterly LDA filing deadline. This module:

  - enters each spike on the **first trading day strictly after** ``available_time`` (like CONGRESS-001);
  - de-overlaps consecutive same-firm spikes whose holding windows would overlap (a near-no-op at
    the 20-day hold since firm-quarters are ~a quarter apart, but it guards the 60-day sensitivity);
  - runs the matched-control excess study with the **DATE-CLUSTERED bootstrap** — spikes pile onto
    only ~4 deadline dates/year, so the clustering is extreme and a pooled bootstrap would be wildly
    over-confident (the plan's most load-bearing use of it);
  - applies the shared verdict tree (≥100 gate; CI excludes zero; BH-FDR one-directional).

Long the spiking firm; a fully-negative CI is **Rejected, not a short** (plan §5). Read-only, off
the order path. Reuses the GOVCONTRACT-001 / CONGRESS-001 engine + stats helpers wholesale.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Any

from app.altdata.events.store import CorporateEvent
from app.altdata.matched_control import (
    EventPoint,
    MatchedExcessResult,
    run_matched_excess_study,
)
from app.altdata.quiver.govcontract_study import (
    SensitivityRow,
    _bh_survivors,
    is_robust,
)
from app.research.factor_lab.spec import VerdictRule, VerdictSpec
from app.research.factor_lab.verdict import classify

# --- decision gates (pre-registered) ---------------------------------------------------------
MIN_EVENTS = 100
TARGET_EVENTS = 150
FDR_Q = 0.10

# --- calibration (locked) --------------------------------------------------------------------
COST_PRIMARY_BPS = 10.0
HOLD_PRIMARY = 20

# --- sensitivity grid (one-factor-at-a-time; NO lag — entry is exact/observable) -------------
COST_SENSITIVITY_BPS = (20.0,)
HOLD_SENSITIVITY = (5, 10, 60)

LOBBY_VERDICT = VerdictSpec(
    rules=(
        VerdictRule(lambda m: m["n_benchmarked"] < MIN_EVENTS, "Insufficient Evidence",
                    "Below the pre-registered ≥100 benchmarked-spike gate; the study terminates "
                    "here. Do NOT relax the spike threshold or the $100k floor to reach it "
                    "(pre-registration v0.2)."),
        VerdictRule(lambda m: m["ci_low"] > 0, "Approved",
                    "95% date-clustered CI on the NET matched-control excess excludes zero "
                    "(positive) — residual alpha after a lobbying spend spike, not sector/size/"
                    "liquidity/momentum beta."),
        VerdictRule(lambda m: m["ci_high"] < 0, "Rejected",
                    "NET excess over matched controls is negative (wrong-signed) — and per plan §5 "
                    "a negative result is NOT a short signal."),
    ),
    default_outcome="Rejected",
    default_action=("NET excess CI spans zero — no residual alpha after a lobbying spike once "
                    "sector/size/liquidity/momentum are matched (the expected outcome per ADR 0037)."),
)


def _as_date(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return None


def dedupe_overlapping(
    events: Sequence[CorporateEvent], hold_days: int = HOLD_PRIMARY,
) -> tuple[list[CorporateEvent], frozenset[str]]:
    """Collapse consecutive same-firm spikes whose holding windows overlap into one (the earliest),
    so no drift window is double-counted. De-overlaps on ``available_time`` (the deadline). Returns
    (kept events, all spike tickers — excluded from every control basket, a firm running a lobbying
    spike is not a clean control for another)."""
    last: dict[str, date] = {}
    kept: list[CorporateEvent] = []
    tickers: set[str] = set()
    for ev in sorted(events, key=lambda e: (e.ticker or "", _as_date(e.available_time) or date.min)):
        d = _as_date(ev.available_time)
        if not ev.ticker or d is None:
            continue
        tickers.add(ev.ticker)
        prev = last.get(ev.ticker)
        if prev is not None and (d - prev).days < int(hold_days * 1.5):   # calendar approx of the hold
            continue
        last[ev.ticker] = d
        kept.append(ev)
    return kept, frozenset(tickers)


def spike_tickers(events: Sequence[CorporateEvent]) -> frozenset[str]:
    return frozenset(e.ticker for e in events if e.ticker)


def _points(events: Sequence[CorporateEvent]) -> list[EventPoint]:
    """Enter the first trading day strictly after the deadline: pass available_time+1 calendar day;
    ``forward_return`` rolls to the first trading day on/after it (same convention as CONGRESS-001)."""
    pts: list[EventPoint] = []
    for e in events:
        d = _as_date(e.available_time)
        if e.ticker and d is not None:
            pts.append(EventPoint(e.ticker, d + timedelta(days=1)))
    return pts


def _metrics(res: MatchedExcessResult) -> dict[str, Any]:
    return {"n_benchmarked": res.n_benchmarked, "ci_low": res.ci_low, "ci_high": res.ci_high,
            "mean_excess": res.mean_excess, "mean_excess_gross": res.mean_excess_gross}


def run_primary(events: Sequence[CorporateEvent], *, price_fn, feature_fn, exclude_fn=None,
                hold_days: int = HOLD_PRIMARY, cost_bps: float = COST_PRIMARY_BPS,
                n_resamples: int = 2000, **kw) -> dict[str, Any]:
    """Primary analysis at the locked calibration (hold 20, cost 10bps) with the DATE-CLUSTERED
    bootstrap → verdict."""
    res = run_matched_excess_study(
        _points(events), price_fn=price_fn, feature_fn=feature_fn, exclude_fn=exclude_fn,
        hold_days=hold_days, cost_bps_per_side=cost_bps, n_resamples=n_resamples,
        cluster_by_entry=True, **kw)
    outcome, action = classify(_metrics(res), LOBBY_VERDICT)
    return {"result": res, "metrics": _metrics(res), "outcome": outcome, "action": action,
            "hold_days": hold_days, "cost_bps": cost_bps, "target_events": TARGET_EVENTS,
            "min_events": MIN_EVENTS}


def run_sensitivity(events: Sequence[CorporateEvent], *, price_fn, feature_fn, exclude_fn=None,
                    n_resamples: int = 2000, **kw) -> dict[str, Any]:
    """One-factor-at-a-time sensitivity (cost + holding window), all date-clustered, + BH-FDR across
    the holding-window family. Confirmation only — never feeds the verdict."""
    rows: list[SensitivityRow] = []

    def _run(dim: str, value: float, *, hold: int, cost: float) -> SensitivityRow:
        r = run_matched_excess_study(
            _points(events), price_fn=price_fn, feature_fn=feature_fn, exclude_fn=exclude_fn,
            hold_days=hold, cost_bps_per_side=cost, n_resamples=n_resamples,
            cluster_by_entry=True, **kw)
        return SensitivityRow(dim, value, r.n_benchmarked, r.mean_excess, r.ci_low, r.ci_high,
                              r.p_value, r.n_benchmarked >= 2 and r.ci_low > 0)

    for cost in COST_SENSITIVITY_BPS:
        rows.append(_run("cost_bps", cost, hold=HOLD_PRIMARY, cost=cost))
    hold_rows = [_run("holding_days", float(h), hold=h, cost=COST_PRIMARY_BPS)
                 for h in (HOLD_PRIMARY, *HOLD_SENSITIVITY)]
    rows.extend(r for r in hold_rows if r.value != HOLD_PRIMARY)

    n_survive = _bh_survivors([r.p_value for r in hold_rows], q=FDR_Q)
    return {"rows": rows, "fdr_q": FDR_Q, "holding_family_n": len(hold_rows),
            "holding_family_fdr_survivors": n_survive}


__all__ = [
    "COST_PRIMARY_BPS", "FDR_Q", "HOLD_PRIMARY", "LOBBY_VERDICT", "MIN_EVENTS",
    "dedupe_overlapping", "is_robust", "run_primary", "run_sensitivity", "spike_tickers",
]
