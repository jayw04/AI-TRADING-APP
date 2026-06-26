"""Production Confidence Score (P13.5) — a single 0–100 measure of how trustworthy the live book is.

The score composes the **operational / safety / verifiability** signals the evidence tools already
capture (``live_evidence.py`` / ``monthly_evidence.py``) into one number that **rises with clean
operation over time** and **falls when the discipline visibly fails**. It is deliberately
conservative: a brand-new book scores low (no track record yet), an incident-free mature book scores
high, and an unrecovered breaker trip / replay mismatch / reconciliation discrepancy each cut it.

Four weighted components, each 0–100:

| Component | Weight | What it measures |
|---|---|---|
| **Verifiability** | 0.30 | replay + reconciliation clean (every automated decision replays, every position reconciles) |
| **Safety** | 0.25 | the risk gates demonstrably fire, and any breaker trip recovered |
| **Maturity** | 0.25 | length of the clean track record (saturating in time — this is what makes the score *rise*) |
| **Operational** | 0.20 | the book is actually running (fills ingesting, reconciliation cycling), no broker rejects |

Pure: no DB, no clock — the caller passes a ``ConfidenceSignals`` snapshot. Deterministic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

# component weights (sum to 1.0)
W_VERIFIABILITY = 0.30
W_SAFETY = 0.25
W_MATURITY = 0.25
W_OPERATIONAL = 0.20

# maturity saturates: 100*(1-exp(-days/TAU)) → ~0 at 0d, ~49 at 30d, ~80 at 75d, ~89 at 100d
MATURITY_TAU_DAYS = 45.0


@dataclass(frozen=True)
class ConfidenceSignals:
    """A point-in-time snapshot of the live book's operational record (all counts cumulative)."""
    track_record_days: int            # days the book has been accruing (maturity)
    replay_mismatches: int            # 0 = every decision replayed (verifiability)
    reconciliation_discrepancies: int # 0 = every position reconciled
    reconciliation_runs: int          # >0 = reconciliation is actually running (else unproven)
    breaker_trips: int
    breaker_resets: int               # trips == resets → all recovered
    orders_risk_passed: int
    orders_rejected_by_risk: int      # >0 = the gate demonstrably rejects (a GOOD signal)
    orders_rejected_by_broker: int
    fills_ingested: int


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _verifiability(s: ConfidenceSignals) -> float:
    score = 100.0 - 40.0 * s.replay_mismatches - 25.0 * s.reconciliation_discrepancies
    if s.reconciliation_runs == 0:
        score = min(score, 60.0)  # can't claim "reconciled" if reconciliation never ran
    return _clamp(score)


def _safety(s: ConfidenceSignals) -> float:
    unrecovered = max(0, s.breaker_trips - s.breaker_resets)
    score = 100.0 - 35.0 * unrecovered
    total_orders = s.orders_risk_passed + s.orders_rejected_by_risk
    if total_orders == 0:
        score = min(score, 70.0)  # gates unexercised — not yet demonstrated
    return _clamp(score)


def _maturity(s: ConfidenceSignals) -> float:
    days = max(0, s.track_record_days)
    return _clamp(100.0 * (1.0 - math.exp(-days / MATURITY_TAU_DAYS)))


def _operational(s: ConfidenceSignals) -> float:
    if s.reconciliation_runs == 0 and s.fills_ingested == 0:
        return 40.0  # nothing has happened yet
    return _clamp(100.0 - 20.0 * s.orders_rejected_by_broker)


def _band(score: float) -> str:
    if score >= 90:
        return "Production-ready"
    if score >= 75:
        return "Strong"
    if score >= 60:
        return "Building"
    if score >= 40:
        return "Early"
    return "Provisional"


def compute_confidence(signals: ConfidenceSignals) -> dict[str, Any]:
    """Compute the 0–100 Production Confidence Score + its component breakdown and rationale."""
    components = {
        "verifiability": round(_verifiability(signals), 1),
        "safety": round(_safety(signals), 1),
        "maturity": round(_maturity(signals), 1),
        "operational": round(_operational(signals), 1),
    }
    weights = {"verifiability": W_VERIFIABILITY, "safety": W_SAFETY,
               "maturity": W_MATURITY, "operational": W_OPERATIONAL}
    score = round(sum(components[k] * weights[k] for k in components), 1)

    rationale: list[str] = []
    if signals.replay_mismatches or signals.reconciliation_discrepancies:
        rationale.append(
            f"verifiability dinged: {signals.replay_mismatches} replay mismatch(es), "
            f"{signals.reconciliation_discrepancies} reconciliation discrepancy(ies)")
    else:
        rationale.append("replay + reconciliation clean")
    unrec = max(0, signals.breaker_trips - signals.breaker_resets)
    rationale.append(
        f"{unrec} unrecovered breaker trip(s)" if unrec
        else f"breaker: {signals.breaker_trips} trip(s), all recovered")
    if signals.orders_rejected_by_risk:
        rationale.append(f"risk gate demonstrably rejects ({signals.orders_rejected_by_risk})")
    rationale.append(f"{signals.track_record_days}-day track record")

    return {
        "score": score, "band": _band(score),
        "components": components, "weights": weights,
        "rationale": rationale,
    }
