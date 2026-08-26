"""Incremental stop-early control, and the contract acquisition must satisfy to use it.

The sealed manifest does not authorize "download all 452 and then see what happened". Its
``stop_early_rule`` is:

    stop acquiring binding evidence as soon as, counting ONLY already-qualified
    LINEAGE_STABLE excluded_low cells as permanently unresolved and treating EVERY
    unreviewed or unproven candidate as RESOLVED, every admissible >=20-year span fails O-2

⛔⛔ **THIS CONTROLLER IS NOT AUTHORITATIVE. Tranche stop-early is HOLD / UNSOUND.**

An earlier revision of this docstring claimed the rule is **monotone** — that the
qualified-unresolved set only grows, so once every admissible span fails no later evidence
can rescue one. **That claim is false, and the binding layer proves it.** A permanent
security with one covering CIK binding qualifies; a later *authorized* filing that reveals a
second overlapping binding makes ``security_cik_binding_covers_week`` return ``COMPETING``,
and the cell **un-qualifies**. Demonstrated: with partial evidence a span showed 5 failing
weeks and STOP was declared, refusing the next request; one further authorized filing took it
to 2 failing weeks and STOP retracted. The controller could therefore refuse to acquire the
very document that removes the cells its STOP rested on — the opposite of the frozen rule
that unreviewed candidates are credited RESOLVED.

There is a second unsafe enlargement. ``LINEAGE_STABLE`` is the conjunction of **three**
predicates — ``CIK_FILING_SPAN_BRACKETS_WEEK AND SECURITY_CIK_BINDING_COVERS_WEEK AND
NO_COMPETING_SECURITY_CIK_BINDING`` — and the manifest says the cover-page tranche supplies
evidence for the **middle term only**. ``_recompute`` promotes a successful coverage result
straight into the stable set without consuming an independently qualified filing-span-bracket
mask. Dropping a conjunct can only *enlarge* the qualified set, so the error runs in the
unsafe direction: it makes STOP easier, not harder.

Both must be fixed before any multi-accession tranche. A cell may only join the permanent
unresolved set once **all three** conjuncts hold *and* the evidence scope capable of
revealing a competitor for that security is closed — a per-security closure property, not a
per-accession one. That closure predicate is deliberately **not frozen here**: proving what
"all evidence capable of revealing a competitor" means must not accidentally settle for less
than the full authorized scope.

Until then ``may_spend_next_request`` is retained as a **non-authoritative** contract sketch.
Nothing calls it in the acquisition path, and a one-accession canary cannot consult it
because there is no next request.

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
            # NOTE: named `covered`, not `stable` -- it is not LINEAGE_STABLE. The
            # filing-span-bracket conjunct is not consumed here; see the module docstring.
            stable: set[int] = set()
            for pt in permatickers:
                covered, _status = security_cik_binding_covers_week(
                    bindings, self.links, pt, week, self.policy
                )
                if covered:
                    stable.add(pt)
            self._qualified[week] = stable

    # ---- the optimistic test ----------------------------------------------------------
    def qualified_unresolved(self, week: datetime) -> int:
        """Cells currently covered by a unique binding.

        ⛔ **Provisional, and NOT yet ``LINEAGE_STABLE``**: this consumes the middle and third
        conjuncts only, omitting ``CIK_FILING_SPAN_BRACKETS_WEEK``, and a later filing can
        remove a member by revealing a competing binding.
        """
        return len(self._qualified.get(week, ()))

    def week_fails(self, week: datetime) -> bool:
        return self.qualified_unresolved(week) > self.grid.weekly_unresolved_budget

    def span_fails_o2(self, span: AdmissibleSpan) -> bool:
        failing = sum(1 for w in span.weeks if self.week_fails(w))
        return failing > span.max_failing_weeks

    def stop_is_invariant(self) -> bool:
        """True when EVERY admissible span currently fails under the optimistic credit.

        ⛔ **"Currently", not "invariantly".** The name is retained for continuity with the
        frozen vocabulary, but this result is **provisional**: it can flip back to False when
        further authorized evidence reveals a competing binding. See the module docstring.
        Do not treat a True here as a verdict, and do not gate acquisition on it until the
        three-conjunct, closure-aware rule is implemented.
        """
        return bool(self.grid.spans) and all(self.span_fails_o2(s) for s in self.grid.spans)

    def may_spend_next_request(self) -> tuple[bool, str]:
        """⛔ NON-AUTHORITATIVE contract sketch. Not wired into the acquisition path.

        The shape is right — consulted *before* a request so a verdict cannot be overrun —
        but the underlying qualification is unsound (module docstring), so this must not gate
        real acquisition. It is kept so the integration contract stays visible and testable
        while the closure-aware rule is designed.
        """
        if self.stop_is_invariant():
            return False, "G0A_STOP_PROVISIONAL_UNDER_OPTIMISTIC_CREDIT"
        return True, "CONTINUE"

    def report(self) -> dict[str, object]:
        return {
            "authoritative": False,
            "hold_reason": (
                "qualification is not monotone (a later authorized filing can reveal a "
                "competing binding and un-qualify cells) and omits the "
                "CIK_FILING_SPAN_BRACKETS_WEEK conjunct"
            ),
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
