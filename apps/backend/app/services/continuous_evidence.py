"""Continuous Evidence Engine — Research Envelope + Evidence Clock + probabilistic drift.

The third pillar (charter: `Docs/implementation/TradingWorkbench_ContinuousEvidenceEngine_Charter_v0.1.md`).
It does NOT decide whether a book is good or bad — it decides whether live behavior remains consistent
with the evidence that justified deployment. It is deliberately minimal and **skeptical by default**:
it persists each live book's Research Envelope, computes observed metrics from `EquitySnapshot`, and emits
a four-state + Evidence-Clock row per book. With only days of live history it will say "Insufficient
Evidence" almost everywhere — that restraint is the feature.

- **Phase 1 (read-only envelope + clock):** the four-state + Evidence-Clock scaffold, point-in-band
  classification capped at WATCH.
- **Phase 2 (probabilistic drift, this module):** the observed side becomes a *distribution*, not a point —
  each live metric is block-bootstrapped into a CI (reusing `app/factor_data/evidence.block_bootstrap_ci`,
  charter §6). A metric escalates Consistent → Watch → **Investigate** only when the observed CI *separates*
  from the research envelope AND the progressive-confidence clock has matured (charter §5). Operational
  drift (stale data, observation gaps) is tracked on a **separate track** and never mixed into the
  investment verdict (charter §4).

Design invariants (charter §1): observes, never optimizes; live observations accumulate evidence, they do
not rewrite research; distributions not point-thresholds; operational vs investment drift never mixed;
deterministic / statistical / explainable — no AI, no auto-action.
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
INVESTIGATE = "Investigate"  # reached only on sustained / probabilistic drift (Phase 2)

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
    """Point-in-band classification for one metric (charter §2/§5), the Phase-1 primitive and
    the Phase-2 fallback when no observed *distribution* is available yet. Skeptical: until the
    evidence has matured past 'Insufficient', the answer is always INSUFFICIENT — no early
    Pass/Fail. Without a distribution it escalates at most to WATCH; INVESTIGATE requires the
    probabilistic path (:func:`classify_metric_probabilistic`)."""
    if observed is None or maturity == _MATURITY_INSUFFICIENT:
        return INSUFFICIENT, "Collect more live evidence."
    if low <= observed <= high:
        return CONSISTENT, "Within the research envelope."
    return WATCH, "Outside the envelope but not yet statistically meaningful — monitor."


# ---- Phase 2: observed distribution + probabilistic drift (charter §5) ----

# A returns-based estimator per metric so every metric gets a bootstrap CI. Sharpe is already a
# returns aggregate; max-drawdown is a *path* metric, so we reconstruct a unit curve from the
# resampled returns and read its drawdown — the same quantity, expressible over a return series.
def _drawdown_from_returns(returns) -> float:
    eq, peak, worst = 1.0, 1.0, 0.0
    for r in returns:
        eq *= 1.0 + r
        peak = max(peak, eq)
        if peak > 0:
            worst = min(worst, eq / peak - 1.0)
    return worst


_METRIC_ESTIMATORS = {"sharpe": ev.sharpe, "max_drawdown": _drawdown_from_returns}

# Below this many daily returns we don't attempt a bootstrap CI (too few points to resample
# meaningfully); the metric falls back to the point-in-band path. Kept < the ~20 returns implied
# by the first maturity tier (21 trading days) so a matured book always gets a distribution.
_MIN_RETURNS_FOR_CI = 15


def _bootstrap_block(n: int) -> int:
    """Circular-block length. Use the platform-canonical ~1-month (21) once there is a quarter of
    history to resample; scale it down for younger series so resamples aren't near-degenerate."""
    return 21 if n >= 63 else max(3, n // 5)


@dataclass(frozen=True)
class ObservedDistribution:
    """The observed side of a metric as a *distribution* (charter §5): the point estimate on the
    live series plus a block-bootstrap CI. This is what separates (or not) from the envelope."""
    point: float
    ci_low: float
    ci_high: float
    n: int  # daily returns the CI was built from


def observed_distribution(observed_point: float, returns, metric_fn, *, seed: int = 17
                          ) -> ObservedDistribution | None:
    """Block-bootstrap CI for one metric on the live return series, or None if too short.
    ``point`` is pinned to the real-curve observation (``observed_point``) so display and
    classification agree; the bootstrap supplies only the interval. Deterministic (seeded)."""
    if len(returns) < _MIN_RETURNS_FOR_CI:
        return None
    res = ev.block_bootstrap_ci(returns, metric_fn, seed=seed, block=_bootstrap_block(len(returns)))
    return ObservedDistribution(round(observed_point, 4), round(res.ci_low, 4),
                                round(res.ci_high, 4), len(returns))


def _separated(obs: ObservedDistribution, low: float, high: float) -> bool:
    """True iff the observed CI lies *entirely* outside the research band (no overlap) — the
    'excludes-zero' non-overlap logic used across the platform, applied to an envelope."""
    return obs.ci_high < low or obs.ci_low > high


def classify_metric_probabilistic(
    obs: ObservedDistribution | None, low: float, high: float, maturity: str
) -> tuple[str, str]:
    """Distribution-vs-envelope classification (charter §5). A metric graduates
    Consistent → Watch → Investigate only when the observed CI *separates* from the research
    envelope, and only reaches Investigate once the confidence clock has matured. Skeptical
    default (Insufficient) still dominates."""
    if obs is None or maturity == _MATURITY_INSUFFICIENT:
        return INSUFFICIENT, "Collect more live evidence."
    if _separated(obs, low, high):
        if maturity in (_MATURITY_MODERATE, _MATURITY_MATURE):
            return INVESTIGATE, ("Observed distribution separates from the research envelope with "
                                 "mature evidence — investigate.")
        return WATCH, "Observed distribution outside the envelope — monitor; evidence not yet mature."
    if low <= obs.point <= high:
        return CONSISTENT, "Within the research envelope."
    return WATCH, "Point estimate drifting but the distribution still overlaps the envelope — monitor."


# ---- Phase 2: operational drift (charter §4 — a separate track, never mixed) ----

_OP_OK = "OK"
_OP_DEGRADED = "Degraded"

# Staleness/gap tolerances in *calendar* days: a normal Fri→Mon weekend is 3 days and a holiday
# can push a legitimate gap to 4, so we only flag 5+ (a genuinely missed observation).
_STALE_LIMIT_DAYS = 4
_GAP_LIMIT_DAYS = 4


@dataclass(frozen=True)
class OperationalDrift:
    """Is the *machine* healthy? (charter §4). Kept strictly separate from the investment verdict:
    a stale feed or a missed snapshot is a fix-the-system signal, not evidence about the edge."""
    state: str            # OK / Degraded
    stale_days: int       # calendar days since the last observation
    max_gap_days: int     # largest gap between consecutive observations
    reasons: list[str] = field(default_factory=list)


def operational_drift_from_curve(
    curve: list[tuple[datetime, float]], as_of: datetime
) -> OperationalDrift:
    """Operational-health read from the observation cadence alone (no new data source): how stale
    the latest snapshot is, and the largest gap between consecutive observations."""
    if not curve:
        return OperationalDrift(_OP_OK, 0, 0, [])
    stale = (as_of.date() - curve[-1][0].date()).days
    gaps = [(curve[i][0].date() - curve[i - 1][0].date()).days for i in range(1, len(curve))]
    max_gap = max(gaps) if gaps else 0
    reasons: list[str] = []
    if stale > _STALE_LIMIT_DAYS:
        reasons.append(f"data stale {stale}d")
    if max_gap > _GAP_LIMIT_DAYS:
        reasons.append(f"observation gap {max_gap}d")
    return OperationalDrift(_OP_DEGRADED if reasons else _OP_OK, stale, max_gap, reasons)


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
    obs_ci_low: float | None = None   # observed bootstrap CI (Phase 2); None until enough history
    obs_ci_high: float | None = None
    separated: bool = False           # observed CI lies entirely outside the envelope


@dataclass
class BookEvidence:
    book: str
    account_id: int
    days_live: int                 # trading-day observations accrued
    maturity: str                  # evidence maturity (charter §3)
    evidence_debt: str
    review_cadence_days: int
    state: str                     # overall INVESTMENT verdict (worst metric; INSUFFICIENT dominates)
    envelope_source: str | None
    metrics: list[MetricObservation] = field(default_factory=list)
    operational: OperationalDrift = field(  # separate track — never folded into ``state`` (§4)
        default_factory=lambda: OperationalDrift(_OP_OK, 0, 0, []))


def _difference(observed: float, low: float, high: float) -> float:
    if observed < low:
        return round(observed - low, 4)
    if observed > high:
        return round(observed - high, 4)
    return 0.0


def book_evidence_from_curve(
    book: str, account_id: int, curve: list[tuple[datetime, float]],
    envelope: ResearchEnvelope | None, as_of: datetime | None = None,
) -> BookEvidence:
    """Pure core: given a live equity curve + envelope, build the Evidence-Clock row.
    ``curve`` is one (datetime, equity) point per trading day, ascending. ``as_of`` anchors the
    operational-drift staleness check (defaults to the last observation, i.e. 'fresh')."""
    days_live = len(curve)
    maturity = evidence_maturity(days_live)
    debt = evidence_debt(days_live, maturity)
    cadence = review_cadence_days(maturity)
    when = as_of or (curve[-1][0] if curve else datetime.now(UTC))
    operational = operational_drift_from_curve(curve, when)

    rets = ev.daily_returns(curve) if days_live >= 2 else []
    observed: dict[str, float | None] = {"sharpe": None, "max_drawdown": None}
    if rets:
        observed["sharpe"] = round(ev.sharpe(rets), 3)
        observed["max_drawdown"] = round(ev.max_drawdown(curve), 4)

    metrics: list[MetricObservation] = []
    overall = INSUFFICIENT
    if envelope is not None:
        for name, (lo, hi) in envelope.metrics.items():
            obs = observed.get(name)
            # Phase 2: build the observed *distribution* and classify by separation; fall back to
            # the point-in-band primitive when there isn't enough history for a CI yet.
            dist = (observed_distribution(obs, rets, _METRIC_ESTIMATORS[name])
                    if obs is not None and name in _METRIC_ESTIMATORS else None)
            if dist is not None:
                state, rec = classify_metric_probabilistic(dist, lo, hi, maturity)
            else:
                state, rec = classify_metric(obs, lo, hi, maturity)
            metrics.append(MetricObservation(
                metric=name, observed=obs, expected_low=lo, expected_high=hi,
                difference=(_difference(obs, lo, hi) if obs is not None else None),
                state=state, recommendation=rec,
                obs_ci_low=(dist.ci_low if dist else None),
                obs_ci_high=(dist.ci_high if dist else None),
                separated=(_separated(dist, lo, hi) if dist else False)))
            if _STATE_SEVERITY[state] > _STATE_SEVERITY[overall]:
                overall = state
    return BookEvidence(
        book=book, account_id=account_id, days_live=days_live, maturity=maturity,
        evidence_debt=debt, review_cadence_days=cadence, state=overall,
        envelope_source=(envelope.source if envelope else None), metrics=metrics,
        operational=operational)


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
    now = datetime.now(UTC)
    results: list[BookEvidence] = []
    for account_id, label in books:
        env = match_envelope(label)
        results.append(book_evidence_from_curve(
            label, account_id, curves.get(account_id, []), env, as_of=now))
    return results
