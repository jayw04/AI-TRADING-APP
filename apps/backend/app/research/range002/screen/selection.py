"""Deterministic exit-candidate selection (A-SCREEN section 6c proposal), synthetic-tested.

Not adopted: the amendment says the rule is "implemented only after this amendment is adopted",
so this is configurable logic with every parameter explicit and nothing chosen. A candidate must
first pass the eligibility floor (boundary operators, stated: profit factor must be STRICTLY
GREATER than ``min_pf``, so PF == min_pf is ineligible; trades must be >= ``min_trades``); among eligible candidates the best score wins; any candidate
within ``delta`` R of the best is a tie resolved by the declared complexity order (first listed
wins) and by nothing else, so the same inputs always give the same winner. ``delta = 0`` means
exact ties only. Selection stability is reported as the margin to the runner-up, separately.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.research.range002.governance.results_guard import requires_capability


@dataclass(frozen=True)
class CandidateScore:
    candidate: str
    score: float | None
    trades: int
    profit_factor: float | None


@dataclass(frozen=True)
class Selection:
    winner: str | None
    ineligible: Mapping[str, str]
    tied_within_delta: tuple[str, ...]
    margin_to_runner_up: float | None
    reason: str


@requires_capability
def select_candidate(
    capability: object,
    scores: Sequence[CandidateScore],
    complexity_order: Sequence[str],
    *,
    min_trades: int,
    min_pf: float,
    delta: float,
) -> Selection:
    if delta < 0 or min_trades < 0:
        raise ValueError("delta and min_trades must be non-negative")
    ids = [s.candidate for s in scores]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate candidate")
    unknown = [c for c in ids if c not in complexity_order]
    if unknown:
        raise ValueError(f"candidates missing from complexity_order: {unknown}")
    ineligible: dict[str, str] = {}
    live: list[CandidateScore] = []
    for s in scores:
        if s.score is None:
            ineligible[s.candidate] = "NO_SCORE"
        elif s.trades < min_trades:
            ineligible[s.candidate] = "TOO_FEW_TRADES"
        elif (
            s.profit_factor is None or s.profit_factor <= min_pf
        ):  # strict: PF must EXCEED the floor
            ineligible[s.candidate] = "PF_BELOW_FLOOR"
        else:
            live.append(s)
    if not live:
        return Selection(None, ineligible, (), None, "NO_ELIGIBLE_CANDIDATE")
    best = max(s.score for s in live if s.score is not None)
    tied = [s for s in live if s.score is not None and s.score >= best - delta]
    order = {c: i for i, c in enumerate(complexity_order)}
    tied.sort(key=lambda s: order[s.candidate])
    ranked = sorted((s.score for s in live if s.score is not None), reverse=True)
    margin = (ranked[0] - ranked[1]) if len(ranked) > 1 else None
    reason = "UNIQUE_BEST" if len(tied) == 1 else "TIE_BROKEN_BY_COMPLEXITY_ORDER"
    return Selection(
        tied[0].candidate, ineligible, tuple(s.candidate for s in tied), margin, reason
    )
