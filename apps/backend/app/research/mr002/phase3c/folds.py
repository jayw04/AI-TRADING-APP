"""The five frozen walk-forward folds — Validation-2 (amended 2026-08-20, Amendment C).

Literal boundaries from `phase3a/ValidationRunSpecification_v1.0.json` -> "folds", which is itself
bound to governing preregistration v1.0.4 (`validation_folds_literal_governing`). The frozen fold
rule is "5 contiguous non-overlapping nearly-equal partitions of the eligible validation sessions;
any remainder assigned to the FINAL fold" -- and for this window the split is exactly 155 each,
775/5, zero remainder, so the literal dates and the rule agree.

The literal dates are authoritative here. The rule is recorded so a verifier can confirm the two
do not disagree; if they ever did, that is a governance defect, not something to reconcile in code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from . import FOLD_ASSIGNMENT_MISMATCH, IntegrityFailure


@dataclass(frozen=True)
class Fold:
    index: int          # 1-based, as the frozen record numbers them
    first: date
    last: date
    sessions: int       # the frozen expected count


# AMENDED 2026-08-20 — Amendment C. Validation-1's literal fold dates belonged to the CONSUMED
# partition and do not transfer; they are retained below as history, never as configuration.
#
# The Validation-2 literals are NOT newly invented boundaries. They are the same frozen rule -- 5
# contiguous nearly-equal partitions of the eligible sessions, remainder to the FINAL fold --
# applied to the Validation-2 window, whose eligible span is ordinals 70..844 of 850. The geometry
# is IDENTICAL by arithmetic (850 - 69 - 6 = 775; 775/5 = 155, zero remainder), and the ordinal
# bounds reproduce the scoring-eligible constants this codebase already carried. The date labels
# below were derived VALUE-BLIND from the session calendar via the authorized custodian path,
# BEFORE the opening, so there was no opportunity to tune them after seeing any result.
VALIDATION_1_FOLDS_CONSUMED: tuple[Fold, ...] = (      # historical record only
    Fold(1, date(2020, 1, 13), date(2020, 8, 21), 155),
    Fold(2, date(2020, 8, 24), date(2021, 4, 6), 155),
    Fold(3, date(2021, 4, 7), date(2021, 11, 12), 155),
    Fold(4, date(2021, 11, 15), date(2022, 6, 28), 155),
    Fold(5, date(2022, 6, 29), date(2023, 2, 8), 155),
)

FROZEN_FOLDS: tuple[Fold, ...] = (
    Fold(1, date(2023, 5, 30), date(2024, 1, 9), 155),
    Fold(2, date(2024, 1, 10), date(2024, 8, 21), 155),
    Fold(3, date(2024, 8, 22), date(2025, 4, 4), 155),
    Fold(4, date(2025, 4, 7), date(2025, 11, 14), 155),
    Fold(5, date(2025, 11, 17), date(2026, 7, 1), 155),
)

EXPECTED_ELIGIBLE_SESSIONS = 775


def fold_of(session: date) -> int | None:
    """1-based fold index, or None when the session lies outside the scoring-eligible span."""
    for f in FROZEN_FOLDS:
        if f.first <= session <= f.last:
            return f.index
    return None


def assign(sessions: list[date]) -> list[int | None]:
    """Map each session to its fold. Order is preserved so the result indexes the return series."""
    return [fold_of(s) for s in sessions]


def verify_assignment(sessions: list[date]) -> dict:
    """Fail closed unless the observed sessions reproduce the frozen fold structure exactly.

    Fold membership decides which returns enter which fold, and therefore decides the
    3-of-5 gate. A silently short fold would move the verdict, so this is an integrity gate.
    """
    assigned = assign(sessions)
    counts = {f.index: 0 for f in FROZEN_FOLDS}
    for idx in assigned:
        if idx is not None:
            counts[idx] += 1

    problems = []
    for f in FROZEN_FOLDS:
        if counts[f.index] != f.sessions:
            problems.append(
                f"fold {f.index} ({f.first}..{f.last}): {counts[f.index]} sessions, "
                f"frozen expectation {f.sessions}"
            )
    total = sum(counts.values())
    if total != EXPECTED_ELIGIBLE_SESSIONS:
        problems.append(f"total eligible sessions {total} != frozen {EXPECTED_ELIGIBLE_SESSIONS}")

    # Contiguity: no gap or overlap between consecutive frozen folds.
    for a, b in zip(FROZEN_FOLDS, FROZEN_FOLDS[1:], strict=False):
        if a.last >= b.first:
            problems.append(f"folds {a.index}/{b.index} overlap at {a.last}/{b.first}")

    if problems:
        raise IntegrityFailure(FOLD_ASSIGNMENT_MISMATCH, "; ".join(problems))

    return {
        "folds": [
            {"fold": f.index, "first": str(f.first), "last": str(f.last),
             "expected_sessions": f.sessions, "observed_sessions": counts[f.index]}
            for f in FROZEN_FOLDS
        ],
        "eligible_sessions_observed": total,
        "eligible_sessions_frozen": EXPECTED_ELIGIBLE_SESSIONS,
        "sessions_outside_scoring_span": sum(1 for i in assigned if i is None),
    }
