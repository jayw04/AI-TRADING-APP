"""Closed vocabularies shared by the governance modules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

# The one upper bound on a pre-registered P3A / P3B attempt limit lives in the spec package
# (single source of truth, shared with the manifest and schema validators). It is re-exported here
# so ``governance.model.MAX_ATTEMPT_LIMIT`` keeps working: ``mark_capability_issued`` and
# ``results_guard`` both enforce it (NF4); a larger manifest limit is refused by name.
from app.research.range002.spec.limits import MAX_ATTEMPT_LIMIT

__all__ = ["MAX_ATTEMPT_LIMIT", "DateRange", "Partition", "Phase"]


class Partition(StrEnum):
    """Plan WP0.4: the partition set is closed."""

    DEVELOPMENT_SELECTION = "DEVELOPMENT_SELECTION"  # P3a
    DEVELOPMENT_CONFIRMATION = "DEVELOPMENT_CONFIRMATION"  # P3b
    HOLDOUT = "HOLDOUT"  # P4
    PAPER = "PAPER"  # P5
    # Exposed 2026 data, engine validation only; never citable as evidence.
    REPLAY_RNG001 = "REPLAY_RNG001"


class Phase(StrEnum):
    P2 = "P2"
    P3A = "P3A"
    P3B = "P3B"
    P4 = "P4"
    P5 = "P5"


#: Which partitions each phase may run on. One partition per phase by design.
PHASE_PARTITIONS: dict[Phase, frozenset[Partition]] = {
    Phase.P2: frozenset({Partition.REPLAY_RNG001}),
    Phase.P3A: frozenset({Partition.DEVELOPMENT_SELECTION}),
    Phase.P3B: frozenset({Partition.DEVELOPMENT_CONFIRMATION}),
    Phase.P4: frozenset({Partition.HOLDOUT}),
    Phase.P5: frozenset({Partition.PAPER}),
}

DEVELOPMENT_PARTITIONS = frozenset(
    {Partition.DEVELOPMENT_SELECTION, Partition.DEVELOPMENT_CONFIRMATION}
)


@dataclass(frozen=True)
class DateRange:
    """Inclusive calendar-date range."""

    start: date
    end: date

    def __post_init__(self) -> None:
        # type(...) is date: a datetime is a date subclass and would silently compare as a
        # moment, shifting the inclusive-day semantics.
        if type(self.start) is not date or type(self.end) is not date:
            raise TypeError("DateRange bounds must be datetime.date values (not datetime)")
        if self.start > self.end:
            raise ValueError(f"DateRange start {self.start} is after end {self.end}")

    def overlaps(self, other: DateRange) -> bool:
        return self.start <= other.end and other.start <= self.end

    def contains(self, other: DateRange) -> bool:
        return self.start <= other.start and other.end <= self.end

    def as_dict(self) -> dict[str, str]:
        return {"start": self.start.isoformat(), "end": self.end.isoformat()}


#: Plan R2: 2026-01-01 -> 2026-07-31 may never be used in a decisive run. This is
#: a hard plan rule (not a ``P0:`` decision value), enforced independently of
#: whatever the spec or the exposure ledger say.
R2_EXCLUDED_WINDOW = DateRange(date(2026, 1, 1), date(2026, 7, 31))
