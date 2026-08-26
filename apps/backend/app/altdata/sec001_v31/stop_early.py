"""Incremental stop-early control, and the contract acquisition must satisfy to use it.

The sealed manifest does not authorize "download all 452 and then see what happened". Its
``stop_early_rule`` is:

    stop acquiring binding evidence as soon as, counting ONLY already-qualified
    LINEAGE_STABLE excluded_low cells as permanently unresolved and treating EVERY
    unreviewed or unproven candidate as RESOLVED, every admissible >=20-year span fails O-2

Two properties of that rule shape this module. It is **optimistic** — everything unproven is
credited as resolved, so the unresolved set only ever grows as evidence arrives — and it is
therefore **monotone**: once every admissible span fails, no later evidence can rescue one.
That is what makes stopping safe rather than merely cheap, and it is why the controller can
be consulted between requests instead of only at the end.

The controller is deliberately *injected* with the governed grid rather than reaching for it:
the weekly grid, the ``excluded_low`` cell set and the admissible spans are sealed inputs
whose hashes belong to the adjudication, not to this file. What lives here is the mechanism
and the pre-acquisition integration contract:

    for each authorized accession, in the frozen order:
        if controller.stop_is_invariant(): STOP -- do not spend the next request
        acquire -> seal -> controller.admit(observations)

``stop_is_invariant`` is consulted **before** each request, so the verdict cannot be reached
and then overrun by requests already in flight.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from app.altdata.sec001_v31.bindings import (
    ClassIdentityLink,
    FirstHopAdmissionPolicy,
    build_declared_class_episodes,
    build_security_cik_bindings,
    security_cik_binding_covers_week,
)
from app.altdata.sec001_v31.layers import Observation


@dataclass(frozen=True)
class AdmissibleSpan:
    """One admissible >=20-year span and its O-2 failure budget."""

    label: str
    rebalances: int
    max_failing_weeks: int
    weeks: tuple[datetime, ...]


@dataclass(frozen=True)
class GovernedGrid:
    """The sealed inputs the stop test consumes. Injected, never fetched here."""

    spans: tuple[AdmissibleSpan, ...]
    #: week -> permatickers whose cells are ``excluded_low`` in that week
    excluded_low: dict[datetime, frozenset[int]]
    #: the per-week unresolved budget (theta_name): a week fails when the qualified
    #: permanently-unresolved count exceeds this.
    weekly_unresolved_budget: int = 10


class CoverageModel(Protocol):
    def qualified_unresolved(self, week: datetime) -> int: ...


@dataclass
class StopEarlyController:
    """Accumulates sealed evidence and answers one question: may the next request be spent?"""

    grid: GovernedGrid
    links: list[ClassIdentityLink]
    to_utc: object
    policy: FirstHopAdmissionPolicy = field(default_factory=FirstHopAdmissionPolicy)
    observations: list[Observation] = field(default_factory=list)
    _qualified: dict[datetime, set[int]] = field(default_factory=dict, init=False)

    # ---- evidence intake --------------------------------------------------------------
    def admit(self, observations: list[Observation]) -> None:
        """Consume one newly sealed accession's observations and re-derive the stable set."""
        self.observations.extend(observations)
        self._recompute()

    def _recompute(self) -> None:
        episodes = build_declared_class_episodes(self.observations, to_utc=self.to_utc)
        bindings = build_security_cik_bindings(episodes, self.links, self.policy)
        self._qualified = {}
        for week, permatickers in self.grid.excluded_low.items():
            stable: set[int] = set()
            for pt in permatickers:
                covered, _status = security_cik_binding_covers_week(
                    bindings, self.links, pt, week, self.policy
                )
                if covered:
                    # LINEAGE_STABLE and excluded_low => permanently unresolved, and now
                    # QUALIFIED as such by evidence rather than assumed.
                    stable.add(pt)
            self._qualified[week] = stable

    # ---- the optimistic test ----------------------------------------------------------
    def qualified_unresolved(self, week: datetime) -> int:
        """Only cells PROVEN lineage-stable count. Everything unproven is credited resolved."""
        return len(self._qualified.get(week, ()))

    def week_fails(self, week: datetime) -> bool:
        return self.qualified_unresolved(week) > self.grid.weekly_unresolved_budget

    def span_fails_o2(self, span: AdmissibleSpan) -> bool:
        failing = sum(1 for w in span.weeks if self.week_fails(w))
        return failing > span.max_failing_weeks

    def stop_is_invariant(self) -> bool:
        """True when EVERY admissible span already fails under the optimistic credit.

        Monotone: the qualified-unresolved set only grows as evidence arrives, so a span
        that fails here cannot be rescued by a later observation. Stopping is therefore
        sound, not merely economical.
        """
        return bool(self.grid.spans) and all(self.span_fails_o2(s) for s in self.grid.spans)

    def may_spend_next_request(self) -> tuple[bool, str]:
        """The pre-acquisition gate. Consulted BEFORE each request, never after."""
        if self.stop_is_invariant():
            return False, "G0A_STOP_INVARIANT_UNDER_OPTIMISTIC_CREDIT"
        return True, "CONTINUE"

    def report(self) -> dict[str, object]:
        return {
            "observations_admitted": len(self.observations),
            "spans": [
                {
                    "label": s.label,
                    "rebalances": s.rebalances,
                    "max_failing_weeks": s.max_failing_weeks,
                    "failing_weeks": sum(1 for w in s.weeks if self.week_fails(w)),
                    "fails_o2": self.span_fails_o2(s),
                }
                for s in self.grid.spans
            ],
            "stop_is_invariant": self.stop_is_invariant(),
        }
