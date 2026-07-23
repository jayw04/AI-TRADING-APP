"""ACADEMIC_12_1_MOMENTUM_FACTOR — secondary attribution benchmark (PREREG v1.0 §6.2).

**Role (recorded):** a secondary *attribution* benchmark measuring conventional cross-sectional
momentum exposure. It is **NOT** configuration-matched to production and is **NOT** an activation
gate. The production-vs-this gap attributes the value of the daily-conditional policy, the graduated
regime overlay, the §5.1 triggers, and the 5-name concentration over the raw academic factor.

**Independently specified — no production performance-selected choice is reused.** Deliberately not
matched on rebalance cadence, regime overlay, trigger logic, concentration, or number of holdings.

FROZEN construction (owner-ratified 2026-07-22):

    signal:              12-1 cross-sectional momentum
    lookback:            252 trading sessions
    skip:                21 trading sessions
    selection:           top decile by momentum score
    weighting:           equal
    rebalance:           final eligible trading session of each calendar month
    regime overlay:      none (always fully invested)
    production triggers: none
    universe:            same PIT eligibility as production
    cost model:          TURNOVER_COST_BPS (the registered base)

FROZEN missing-data rules (owner 2026-07-22 — no post-hoc choice between skipping and holding):

  1. Insufficient signal history  → the security is INELIGIBLE for selection.
  2. Missing price on a scheduled rebalance → RETAIN the existing position in that security; do NOT
     initiate or resize it; redistribute NO target weight to it.
  3. A previously-held security becomes ineligible → LIQUIDATE it on the first session with a valid
     execution price.
  4. The entire rebalance cannot be valued or executed → mark the rebalance INCOMPLETE, retain the
     previous portfolio, and record an operational exception.

⚠ Construct/equivalence structure only. NO forward performance is computed or inspected until every
benchmark SHA and the PREREG §0 bindings are countersigned (§5.4 no-peeking).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

BENCHMARK_ID = "ACADEMIC_12_1_MOMENTUM_FACTOR"

# Frozen construction constants (do not tune to results).
LOOKBACK_SESSIONS = 252
SKIP_SESSIONS = 21
SELECTION_QUANTILE = 0.10          # top decile
COST_MODEL = "TURNOVER_COST_BPS"   # the registered base rate
REGIME_OVERLAY = False
PRODUCTION_TRIGGERS = False
REBALANCE = "final_eligible_trading_session_of_each_month"
WEIGHTING = "equal"


class RebalanceStatus(StrEnum):
    OK = "OK"
    INCOMPLETE = "INCOMPLETE"       # rule 4: portfolio retained, operational exception recorded


@dataclass(frozen=True)
class MomentumScore:
    """Point-in-time factor input for one security: the 12-1 momentum and whether its signal
    history is sufficient. Supplied by the caller from the same PIT store production uses."""
    symbol: str
    momentum_12_1: float
    has_sufficient_history: bool


@dataclass(frozen=True)
class RebalanceResult:
    as_of: date
    status: RebalanceStatus
    target_weights: dict[str, float]           # equal weight across selected; {} if INCOMPLETE
    liquidations: tuple[str, ...] = ()          # rule 3: held-but-now-ineligible, priced this session
    retained_unpriced: tuple[str, ...] = ()     # rule 2: held, missing price → position retained
    exception: str | None = None


def is_month_end_rebalance(day: date, next_trading_day: date | None) -> bool:
    """True iff ``day`` is the final eligible trading session of its calendar month (the next
    trading session falls in a different month, or there is none)."""
    return next_trading_day is None or (next_trading_day.year, next_trading_day.month) != (
        day.year, day.month)


def eligible_by_history(scores: list[MomentumScore]) -> list[MomentumScore]:
    """Rule 1: a security with insufficient signal history is ineligible for selection."""
    return [s for s in scores if s.has_sufficient_history]


def select_top_decile(scores: list[MomentumScore]) -> list[str]:
    """Top-decile selection by 12-1 momentum among history-eligible securities.

    Deterministic tie handling: sort by (momentum desc, symbol asc). The decile size is
    ceil(0.10 * n_eligible), at least 1 when any security is eligible — a conventional
    non-empty top-decile."""
    import math

    elig = eligible_by_history(scores)
    if not elig:
        return []
    ranked = sorted(elig, key=lambda s: (-s.momentum_12_1, s.symbol))
    k = max(1, math.ceil(SELECTION_QUANTILE * len(ranked)))
    return [s.symbol for s in ranked[:k]]


def compute_rebalance(
    as_of: date,
    scores: list[MomentumScore],
    held: set[str],
    priced: set[str],
) -> RebalanceResult:
    """One scheduled month-end rebalance under the frozen rules.

    ``priced`` = securities with a valid execution price this session. The rules:
      * selection is top-decile of history-eligible names (rules 1, and equal weight);
      * a selected name without a price is retained-if-held / not-initiated (rule 2), and carries no
        target weight;
      * a held name that is no longer selected AND is priced is liquidated (rule 3); if unpriced it is
        retained until a priced session (rule 3 deferred);
      * if NOTHING can be valued/executed (no selected name priced and the book cannot be valued) the
        rebalance is INCOMPLETE — retain the previous portfolio, record an exception (rule 4).
    """
    selected = select_top_decile(scores)

    # rule 2: only priced selections can actually take target weight; unpriced selections carry none
    investable = [s for s in selected if s in priced]
    retained_unpriced = tuple(sorted(s for s in selected if s not in priced and s in held))

    # rule 4: the whole rebalance cannot proceed — no selected name is priced this session.
    if not investable:
        return RebalanceResult(
            as_of=as_of, status=RebalanceStatus.INCOMPLETE, target_weights={},
            retained_unpriced=retained_unpriced,
            exception="no selected security has a valid execution price this session (rule 4)")

    # rule 3: held names dropped from selection, priced this session → liquidate.
    liquidations = tuple(sorted(h for h in held if h not in selected and h in priced))

    w = 1.0 / len(investable)                      # equal weight across investable selections
    target = {s: w for s in investable}
    return RebalanceResult(
        as_of=as_of, status=RebalanceStatus.OK, target_weights=target,
        liquidations=liquidations, retained_unpriced=retained_unpriced)


@dataclass
class AcademicMomentumBook:
    """Carries the benchmark portfolio across scheduled month-end rebalances, applying the frozen
    rules. Weights only — mark-to-market / cost accounting is the caller's harness (the same cost
    model as production), consistent with the other benchmarks. NO forward performance here."""
    weights: dict[str, float] = field(default_factory=dict)
    exceptions: list[str] = field(default_factory=list)

    def held(self) -> set[str]:
        return set(self.weights)

    def apply(self, result: RebalanceResult) -> None:
        if result.status is RebalanceStatus.INCOMPLETE:
            # rule 4: retain the previous portfolio; record the exception.
            if result.exception:
                self.exceptions.append(f"{result.as_of.isoformat()}: {result.exception}")
            return
        new = dict(result.target_weights)
        # rule 2: retained-unpriced held names keep their prior weight (not resized, not dropped).
        for s in result.retained_unpriced:
            if s in self.weights and s not in new:
                new[s] = self.weights[s]
        # rule 3 liquidations are simply absent from ``new``.
        self.weights = new
