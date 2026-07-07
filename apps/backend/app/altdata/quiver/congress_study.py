"""CONGRESS-001 study — Purchase-only matched-control excess, date-clustered (EAD Phase 3; ADR 0037 §3.2).

Pre-registration (plan v0.2, owner-approved 9.8/10):

  PRIMARY: PURCHASE (buy) disclosures only. Sales are a DIAGNOSTIC (liquidity/tax-driven, plus a
    short would carry borrow cost) — never the verdict (plan §8).
  ENTRY:   first trading day STRICTLY AFTER the OBSERVABLE ``ReportDate`` (``available_time``). No
    disclosure-lag calibration — the disclosure date is directly observable (the CONGRESS-001 edge
    over gov-contracts, whose ``Date`` was a useless snapshot needing a calibrated lag).
  MATERIALITY: CLUSTER-level. Collapse same-ticker Purchase disclosures whose holding windows would
    overlap into ONE cluster, SUM the Range lower-bounds, and keep clusters ≥ $50k. A lone small
    trade is immaterial; a coordinated cluster is the signal (plan §2/§8).
  BOOTSTRAP: DATE-CLUSTERED by entry date — MANDATORY. Reports cluster on dates; a pooled i.i.d.
    bootstrap treats same-day events as independent and OVERSTATES confidence (the RNG-001 lesson).
  GATES (pre-registered): ≥100 benchmarked clusters (< 100 ⇒ Insufficient Evidence); the 95% CI on
    the NET matched-control excess excludes zero; BH-FDR ≤ 0.10 across the holding-window family
    (one-directional — robustness can only confirm or caveat, never upgrade).

The verdict comes from the PRIMARY analysis; SENSITIVITY is one-factor-at-a-time over {cost, holding}
and asks only "would a reasonable alternative flip it?" There is NO disclosure-lag dimension — entry
is exact. Materiality is a single locked threshold (no sweep — that would be data dredging).
Read-only, off the order path.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from app.altdata.events.store import CorporateEvent
from app.altdata.matched_control import (
    EventPoint,
    MatchedExcessResult,
    run_matched_excess_study,
)

# Reuse the pure stats helpers from the sibling program (identical semantics; DRY).
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

# --- calibration parameters (locked) ---------------------------------------------------------
MATERIALITY_CLUSTER_USD = 50_000.0   # summed Range lower-bounds within a de-overlapped cluster
COST_PRIMARY_BPS = 10.0
HOLD_PRIMARY = 20
PRIMARY_DIRECTION = "buy"            # Purchases are primary; sales are diagnostic only

# --- sensitivity grid (one-factor-at-a-time; NO lag — entry is exact/observable) -------------
COST_SENSITIVITY_BPS = (20.0,)
HOLD_SENSITIVITY = (5, 10, 60)

# Verdict tree — evaluated on the PRIMARY (Purchase) analysis only. "Insufficient Evidence" is a
# first-class pre-registered outcome (the cluster-count gate), not a fallback.
CONGRESS_VERDICT = VerdictSpec(
    rules=(
        VerdictRule(lambda m: m["n_benchmarked"] < MIN_EVENTS, "Insufficient Evidence",
                    "Below the pre-registered ≥100 benchmarked-cluster gate; the study terminates "
                    "here. Do NOT relax cluster-materiality to reach it (pre-registration v0.2)."),
        VerdictRule(lambda m: m["ci_low"] > 0, "Approved",
                    "95% date-clustered CI on the NET matched-control excess excludes zero "
                    "(positive) — residual alpha, not sector/size/liquidity/momentum beta (§8)."),
        VerdictRule(lambda m: m["ci_high"] < 0, "Rejected",
                    "NET excess over matched controls is negative (wrong-signed)."),
    ),
    default_outcome="Rejected",
    default_action=("NET excess CI spans zero — no residual alpha over matched controls once "
                    "sector/size/liquidity/momentum are matched (the expected outcome per ADR 0037)."),
)


@dataclass(frozen=True)
class Cluster:
    """A de-overlapped same-ticker directional cluster: entered once, materiality = summed floors."""
    ticker: str
    available_time: date   # earliest disclosure (ReportDate) in the cluster — the PIT anchor
    entry_date: date       # first trading day strictly after available_time
    range_low_sum: float   # summed Range lower-bounds → cluster materiality
    n_trades: int
    direction: str


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _entry_after(available_time: date) -> date:
    """First trading day STRICTLY after the observable disclosure date. We pass available_time + 1
    calendar day; ``matched_control.forward_return`` starts from the first trading day ON/AFTER
    that, so a Fri/weekend ``ReportDate`` enters the following Mon — 'strictly after' for any
    disclosure date, trading-calendar-exact via the price series (no hard-coded calendar)."""
    return available_time + timedelta(days=1)


def _finish(ticker: str, evs: list[CorporateEvent], direction: str) -> Cluster:
    anchor = min(_as_date(e.available_time) for e in evs)  # earliest disclosure = PIT anchor
    assert anchor is not None
    rl_sum = sum(float((e.payload or {}).get("range_low") or 0.0) for e in evs)
    return Cluster(ticker, anchor, _entry_after(anchor), rl_sum, len(evs), direction)


def build_clusters(
    events: Sequence[CorporateEvent], *, direction: str = PRIMARY_DIRECTION,
    hold_days: int = HOLD_PRIMARY, materiality_usd: float = MATERIALITY_CLUSTER_USD,
) -> list[Cluster]:
    """Filter to ``direction`` disclosures, collapse same-ticker disclosures whose holding windows
    would overlap into one cluster (summing Range lower-bounds so a coordinated cluster is one
    event, not many double-counted overlapping windows), and keep clusters clearing the materiality
    floor. Entry anchors on the cluster's EARLIEST (PIT-honest) disclosure."""
    by_ticker: dict[str, list[CorporateEvent]] = {}
    for ev in events:
        adate = _as_date(ev.available_time)
        if not ev.ticker or adate is None:
            continue
        if (ev.payload or {}).get("direction") != direction:
            continue
        by_ticker.setdefault(ev.ticker, []).append(ev)

    clusters: list[Cluster] = []
    for ticker, evs in by_ticker.items():
        evs.sort(key=lambda e: _as_date(e.available_time) or date.min)
        cur: list[CorporateEvent] = []
        anchor: date | None = None
        for ev in evs:
            adate = _as_date(ev.available_time)
            if anchor is not None and adate is not None and (adate - anchor).days >= int(hold_days * 1.5):
                clusters.append(_finish(ticker, cur, direction))
                cur, anchor = [], None
            if anchor is None:
                anchor = adate
            cur.append(ev)
        if cur:
            clusters.append(_finish(ticker, cur, direction))

    return [c for c in clusters if c.range_low_sum >= materiality_usd]


def cluster_tickers(events: Sequence[CorporateEvent]) -> frozenset[str]:
    """All tickers with a directional disclosure — excluded from every event's control basket
    (a ticker Congress traded is not a clean control for another such ticker)."""
    return frozenset(ev.ticker for ev in events if ev.ticker and (ev.payload or {}).get("direction"))


def _points(clusters: Sequence[Cluster]) -> list[EventPoint]:
    return [EventPoint(c.ticker, c.entry_date) for c in clusters]


def _metrics(res: MatchedExcessResult) -> dict[str, Any]:
    return {"n_benchmarked": res.n_benchmarked, "ci_low": res.ci_low, "ci_high": res.ci_high,
            "mean_excess": res.mean_excess, "mean_excess_gross": res.mean_excess_gross}


def run_primary(clusters: Sequence[Cluster], *, price_fn, feature_fn, exclude_fn=None,
                hold_days: int = HOLD_PRIMARY, cost_bps: float = COST_PRIMARY_BPS,
                n_resamples: int = 2000, **kw) -> dict[str, Any]:
    """Primary analysis at the locked calibration (hold 20, cost 10bps) with the DATE-CLUSTERED
    bootstrap → verdict."""
    res = run_matched_excess_study(
        _points(clusters), price_fn=price_fn, feature_fn=feature_fn, exclude_fn=exclude_fn,
        hold_days=hold_days, cost_bps_per_side=cost_bps, n_resamples=n_resamples,
        cluster_by_entry=True, **kw)
    outcome, action = classify(_metrics(res), CONGRESS_VERDICT)
    return {"result": res, "metrics": _metrics(res), "outcome": outcome, "action": action,
            "hold_days": hold_days, "cost_bps": cost_bps, "target_events": TARGET_EVENTS,
            "min_events": MIN_EVENTS}


def run_sensitivity(clusters: Sequence[Cluster], *, price_fn, feature_fn, exclude_fn=None,
                    n_resamples: int = 2000, **kw) -> dict[str, Any]:
    """One-factor-at-a-time sensitivity from the primary (cost + holding window), plus BH-FDR across
    the holding-window family. All runs use the date-clustered bootstrap. Confirmation only — never
    feeds the verdict."""
    rows: list[SensitivityRow] = []

    def _run(dim: str, value: float, *, hold: int, cost: float) -> SensitivityRow:
        r = run_matched_excess_study(
            _points(clusters), price_fn=price_fn, feature_fn=feature_fn, exclude_fn=exclude_fn,
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
    "CONGRESS_VERDICT", "COST_PRIMARY_BPS", "FDR_Q", "HOLD_PRIMARY", "MATERIALITY_CLUSTER_USD",
    "MIN_EVENTS", "PRIMARY_DIRECTION", "Cluster", "build_clusters", "cluster_tickers", "is_robust",
    "run_primary", "run_sensitivity",
]
