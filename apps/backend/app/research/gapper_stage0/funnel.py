"""Funnel instrumentation + the unexplained-collapse detector (memo §6.3–6.4).

Per-date record of the frozen funnel::

    scanner/event field → tradability exclusions → coverage exclusions
        → eligible field → ranking → selected

reusing the EXISTING v1 counter names (``gappers_in`` → ``store_covered`` →
``eligible_panel`` → ``eligible_count`` → ``candidate_count``,
``app/services/premarket_scan.py``) so v2 records are directly comparable with
the v1 census. Every excluded name carries a reason code.

The v1 defect (approval record §3 amendment 3): on 16 of 42 dates
``eligible_panel`` exceeded ``eligible_count`` with no attributable rule —
contrast reached the funnel and was silently collapsed. The detector here makes
that a **first-class hard failure**:

    sum(eligibility-stage reason-coded exclusions) == eligible_panel - eligible_count

per date. Any residual is recorded as ``collapse_unexplained`` (signed) and the
record is ``valid=False`` — never just a log line.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Frozen stage names, in funnel order.
STAGE_TRADABILITY = "tradability"
STAGE_COVERAGE = "coverage"
STAGE_ELIGIBILITY = "eligibility"
STAGE_RANKING = "ranking"
STAGES = (STAGE_TRADABILITY, STAGE_COVERAGE, STAGE_ELIGIBILITY, STAGE_RANKING)

FUNNEL_SCHEMA = "gapper_stage0/funnel_record/v1"


@dataclass(frozen=True)
class Exclusion:
    """One excluded name at one funnel stage, with its frozen reason code."""

    symbol: str
    stage: str
    reason: str

    def __post_init__(self) -> None:
        if self.stage not in STAGES:
            raise ValueError(f"unknown funnel stage {self.stage!r}; expected one of {STAGES}")
        if not self.symbol or not self.symbol.strip():
            raise ValueError("exclusion requires a symbol")
        if not self.reason or not self.reason.strip():
            raise ValueError(
                f"exclusion of {self.symbol!r} at {self.stage!r} requires a reason code"
            )

    def to_dict(self) -> dict[str, str]:
        return {"symbol": self.symbol, "stage": self.stage, "reason": self.reason}


@dataclass(frozen=True)
class FunnelRecord:
    """One date's funnel counters + reason-coded exclusions + collapse detector."""

    asof: str  # ISO date
    gappers_in: int
    store_covered: int
    eligible_panel: int
    eligible_count: int
    candidate_count: int
    exclusions: tuple[Exclusion, ...] = ()
    #: eligible_panel - eligible_count - (# eligibility-stage exclusions).
    #: Signed: >0 unexplained collapse, <0 over-explained. 0 ⇔ valid.
    collapse_unexplained: int = 0
    valid: bool = True
    schema: str = field(default=FUNNEL_SCHEMA)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "asof": self.asof,
            "gappers_in": self.gappers_in,
            "store_covered": self.store_covered,
            "eligible_panel": self.eligible_panel,
            "eligible_count": self.eligible_count,
            "candidate_count": self.candidate_count,
            "exclusions": [e.to_dict() for e in self.exclusions],
            "collapse_unexplained": self.collapse_unexplained,
            "valid": self.valid,
        }


def build_funnel_record(
    *,
    asof: str,
    gappers_in: int,
    store_covered: int,
    eligible_panel: int,
    eligible_count: int,
    candidate_count: int,
    exclusions: list[Exclusion] | tuple[Exclusion, ...] = (),
) -> FunnelRecord:
    """Assemble one date's record and run the unexplained-collapse detector.

    The contraction ``eligible_panel → eligible_count`` must be exactly the sum
    of eligibility-stage reason-coded exclusions. A nonzero residual marks the
    record invalid — a first-class hard failure, per the §3 acceptance
    condition ("no unexplained eligible_panel → eligible_count collapse").
    """
    for name, value in (
        ("gappers_in", gappers_in),
        ("store_covered", store_covered),
        ("eligible_panel", eligible_panel),
        ("eligible_count", eligible_count),
        ("candidate_count", candidate_count),
    ):
        if value < 0:
            raise ValueError(f"{name} must be >= 0, got {value}")
    explained = sum(1 for e in exclusions if e.stage == STAGE_ELIGIBILITY)
    residual = (eligible_panel - eligible_count) - explained
    return FunnelRecord(
        asof=asof,
        gappers_in=gappers_in,
        store_covered=store_covered,
        eligible_panel=eligible_panel,
        eligible_count=eligible_count,
        candidate_count=candidate_count,
        exclusions=tuple(exclusions),
        collapse_unexplained=residual,
        valid=residual == 0,
    )
