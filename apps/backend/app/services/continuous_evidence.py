"""Continuous Evidence Engine — Phase 1: Research Envelope + Evidence Clock (read-only).

The third pillar (charter: `Docs/implementation/TradingWorkbench_ContinuousEvidenceEngine_Charter_v0.1.md`).
It does NOT decide whether a book is good or bad — it decides whether live behavior remains consistent
with the evidence that justified deployment. Phase 1 is deliberately minimal and **skeptical by default**:
it persists each live book's Research Envelope, computes observed metrics from `EquitySnapshot`, and emits
a four-state + Evidence-Clock row per book. With only days of live history it will say "Insufficient
Evidence" almost everywhere — that restraint is the feature.

Design invariants (charter §1): observes, never optimizes; live observations accumulate evidence, they do
not rewrite research; distributions not point-thresholds; operational vs investment drift never mixed;
deterministic / statistical / explainable — no AI, no auto-action. Phase 1 stops at WATCH; the
probabilistic INVESTIGATE escalation (distribution separation, sustained drift) is Phase 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.equity_snapshot import EquitySnapshot
from app.factor_data import evidence as ev

# ---- evidence states (charter §2) — no automatic "Failure" ----
INSUFFICIENT = "Insufficient Evidence"
CONSISTENT = "Consistent"
WATCH = "Watch"
INVESTIGATE = "Investigate"  # Phase 2 only (needs sustained / probabilistic drift)

_STATE_SEVERITY = {INSUFFICIENT: 0, CONSISTENT: 1, WATCH: 2, INVESTIGATE: 3}

# ---- progressive confidence / evidence maturity (charter §3), in trading days ----
# ~21 td = 1 mo, 63 = 3 mo, 126 = 6 mo, 252 = 12 mo.
_MATURITY_INSUFFICIENT = "Insufficient"
_MATURITY_PRELIM = "Preliminary Observation"
_MATURITY_EMERGING = "Emerging Evidence"
_MATURITY_MODERATE = "Moderate Confidence"
_MATURITY_MATURE = "Mature Evidence"


def evidence_maturity(trading_days_live: int) -> str:
    """Confidence label as a pure function of accumulated live history (charter §3)."""
    if trading_days_live < 21:
        return _MATURITY_INSUFFICIENT
    if trading_days_live < 63:
        return _MATURITY_PRELIM
    if trading_days_live < 126:
        return _MATURITY_EMERGING
    if trading_days_live < 252:
        return _MATURITY_MODERATE
    return _MATURITY_MATURE


def evidence_debt(trading_days_live: int, maturity: str) -> str:
    """Governance signal: deployed a while but still little evidence -> high debt."""
    if trading_days_live >= 63 and maturity in (_MATURITY_INSUFFICIENT, _MATURITY_PRELIM):
        return "High"
    if trading_days_live >= 21 and maturity == _MATURITY_INSUFFICIENT:
        return "Moderate"
    return "Low"


def review_cadence_days(maturity: str) -> int:
    """Expected review rhythm — tighter while young, quarterly once evidence matures."""
    return 30 if maturity in (_MATURITY_INSUFFICIENT, _MATURITY_PRELIM) else 90


def classify_metric(observed: float | None, low: float, high: float, maturity: str) -> tuple[str, str]:
    """Four-state classification for one metric (charter §2/§5). Skeptical: until the
    evidence has matured past 'Insufficient', the answer is always INSUFFICIENT — no
    early Pass/Fail. Phase 1 escalates at most to WATCH; INVESTIGATE is Phase 2."""
    if observed is None or maturity == _MATURITY_INSUFFICIENT:
        return INSUFFICIENT, "Collect more live evidence."
    if low <= observed <= high:
        return CONSISTENT, "Within the research envelope."
    return WATCH, "Outside the envelope but not yet statistically meaningful — monitor."


# ---- Research Envelope (charter key terms) ----

@dataclass(frozen=True)
class ResearchEnvelope:
    """The statistically justified operating range for a validated book: expected metric
    bands from the evidence package that justified deployment. Phase 1 bands are
    declarative starting points (each cites its program); Phase 2 tightens them to the
    evidence packages' actual bootstrap CIs."""
    family: str
    source: str
    # metric -> (expected_low, expected_high)
    metrics: dict[str, tuple[float, float]]


# Keyed by normalized family; matched against the live account's strategy label by substring.
# Bands are the deployment-justifying expectations (sourced), intentionally wide in v1.
ENVELOPES: tuple[ResearchEnvelope, ...] = (
    ResearchEnvelope("momentum", "MOM-001 (Sharpe 0.48, CI [0.13,0.85]); live v1.1 vol-scaled",
                     {"sharpe": (0.10, 1.50), "max_drawdown": (-0.45, 0.0)}),
    ResearchEnvelope("low_vol", "LOW-001 (Diversifier B; Sharpe 0.59, maxDD -39%)",
                     {"sharpe": (0.30, 1.30), "max_drawdown": (-0.40, 0.0)}),
    ResearchEnvelope("sector", "SEC-001 (Diversifier B; Sharpe 0.51, maxDD -65%)",
                     {"sharpe": (0.20, 1.20), "max_drawdown": (-0.65, 0.0)}),
    ResearchEnvelope("trend", "TREND-001 (Diversifier B; Sharpe 0.46, maxDD -46%)",
                     {"sharpe": (0.20, 1.30), "max_drawdown": (-0.47, 0.0)}),
    ResearchEnvelope("combined", "FI-001 / PORT-001 (combined book: drawdown-managed)",
                     {"sharpe": (0.40, 1.40), "max_drawdown": (-0.35, 0.0)}),
    # RNG-001 is a REJECTED benchmark: the envelope expects ~no edge (Continuous Evidence
    # verifies it keeps behaving like the rejected-benchmark it is).
    ResearchEnvelope("range", "RNG-001 (rejected — no tradable edge; runs as a benchmark)",
                     {"sharpe": (-0.30, 0.50), "max_drawdown": (-0.20, 0.0)}),
)

# Order matters — the first substring hit wins, so specific families precede generic ones.
# The momentum Risk Profiles are all literally "momentum-conservative/-growth/-balanced/-portfolio",
# so the "momentum" token alone matches them (and must be checked before "portfolio" so the momentum
# book isn't mis-mapped to the combined family).
_FAMILY_ALIASES = {
    "momentum": "momentum",
    "low_vol": "low_vol", "lowvol": "low_vol", "low-vol": "low_vol", "low volatility": "low_vol",
    "sector": "sector", "rotation": "sector",
    "trend": "trend",
    "risk-balanced": "combined", "multi-asset": "combined", "combined": "combined", "portfolio": "combined",
    "range": "range", "rng": "range",
}


def match_envelope(label: str) -> ResearchEnvelope | None:
    """Map a live strategy label to its Research Envelope family (substring match)."""
    low = (label or "").lower()
    by_family = {e.family: e for e in ENVELOPES}
    for token, family in _FAMILY_ALIASES.items():
        if token in low:
            return by_family[family]
    return None


# ---- results ----

@dataclass
class MetricObservation:
    metric: str
    observed: float | None
    expected_low: float
    expected_high: float
    difference: float | None  # signed distance outside the band; 0 if inside; None if no obs
    state: str
    recommendation: str


@dataclass
class BookEvidence:
    book: str
    account_id: int
    days_live: int                 # trading-day observations accrued
    maturity: str                  # evidence maturity (charter §3)
    evidence_debt: str
    review_cadence_days: int
    state: str                     # overall (worst metric; INSUFFICIENT dominates)
    envelope_source: str | None
    metrics: list[MetricObservation] = field(default_factory=list)


def _difference(observed: float, low: float, high: float) -> float:
    if observed < low:
        return round(observed - low, 4)
    if observed > high:
        return round(observed - high, 4)
    return 0.0


def book_evidence_from_curve(
    book: str, account_id: int, curve: list[tuple[datetime, float]],
    envelope: ResearchEnvelope | None,
) -> BookEvidence:
    """Pure core: given a live equity curve + envelope, build the Evidence-Clock row.
    ``curve`` is one (datetime, equity) point per trading day, ascending."""
    days_live = len(curve)
    maturity = evidence_maturity(days_live)
    debt = evidence_debt(days_live, maturity)
    cadence = review_cadence_days(maturity)

    observed: dict[str, float | None] = {"sharpe": None, "max_drawdown": None}
    if days_live >= 2:
        rets = ev.daily_returns(curve)
        observed["sharpe"] = round(ev.sharpe(rets), 3) if rets else None
        observed["max_drawdown"] = round(ev.max_drawdown(curve), 4)

    metrics: list[MetricObservation] = []
    overall = INSUFFICIENT
    if envelope is not None:
        for name, (lo, hi) in envelope.metrics.items():
            obs = observed.get(name)
            state, rec = classify_metric(obs, lo, hi, maturity)
            metrics.append(MetricObservation(
                metric=name, observed=obs, expected_low=lo, expected_high=hi,
                difference=(_difference(obs, lo, hi) if obs is not None else None),
                state=state, recommendation=rec))
            if _STATE_SEVERITY[state] > _STATE_SEVERITY[overall]:
                overall = state
    return BookEvidence(
        book=book, account_id=account_id, days_live=days_live, maturity=maturity,
        evidence_debt=debt, review_cadence_days=cadence, state=overall,
        envelope_source=(envelope.source if envelope else None), metrics=metrics)


async def _load_curves(
    session: AsyncSession, account_ids: list[int], window_days: int
) -> dict[int, list[tuple[datetime, float]]]:
    """Daily (end-of-day) equity curve per account from EquitySnapshot, ascending."""
    since = datetime.now(UTC) - timedelta(days=window_days)
    out: dict[int, list[tuple[datetime, float]]] = {}
    for aid in account_ids:
        rows = (await session.execute(
            select(EquitySnapshot.ts, EquitySnapshot.equity)
            .where(EquitySnapshot.account_id == aid, EquitySnapshot.ts >= since)
            .order_by(EquitySnapshot.ts.asc())
        )).all()
        # collapse to one point per calendar day (last snapshot of the day)
        by_day: dict[str, tuple[datetime, float]] = {}
        for ts, eq in rows:
            by_day[ts.date().isoformat()] = (ts, float(eq))
        out[aid] = [by_day[k] for k in sorted(by_day)]
    return out


async def compute(
    session: AsyncSession,
    books: list[tuple[int, str]],   # (account_id, strategy_label)
    window_days: int = 400,
) -> list[BookEvidence]:
    """Phase 1 read-only pass: Research Envelope vs observed, per live book, with the
    Evidence Clock. Books without a matched envelope are still reported (as
    INSUFFICIENT / no-envelope) so nothing is silently dropped."""
    curves = await _load_curves(session, [a for a, _ in books], window_days)
    results: list[BookEvidence] = []
    for account_id, label in books:
        env = match_envelope(label)
        results.append(book_evidence_from_curve(
            label, account_id, curves.get(account_id, []), env))
    return results
