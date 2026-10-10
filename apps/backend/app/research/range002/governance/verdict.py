"""RANGE-002 verdict states -- the closed set of plan section 5.2.

``Verdict`` is the only legal vocabulary; ``parse_verdict`` rejects any other
string. ``is_valid_transition`` encodes the section 5.2 state diagram. The
diagram defines no exit from a terminal state, and none is invented here:

* ``STOP``, ``REJECT``, ``PAPER_FAIL`` are terminal for the registered spec;
* ``INCONCLUSIVE_*`` is "not a soft pass" -- a repair and retest goes through a
  separate governance decision, so it is also terminal in this function;
* ``PAPER_EXTEND`` is listed as a P5 outcome but the diagram gives it no
  successor (open question for the owner), so it is terminal here too.
"""

from __future__ import annotations

from enum import StrEnum

from app.research.range002.governance.errors import VerdictError


class Verdict(StrEnum):
    UNTESTED = "UNTESTED"
    EXIT_SELECTED = "EXIT_SELECTED"
    STOP = "STOP"
    ADVANCE_TO_P4 = "ADVANCE_TO_P4"
    PASS_HISTORICAL_PENDING_PROSPECTIVE = "PASS_HISTORICAL_PENDING_PROSPECTIVE"
    REJECT = "REJECT"
    PAPER_PASS = "PAPER_PASS"
    PAPER_FAIL = "PAPER_FAIL"
    PAPER_EXTEND = "PAPER_EXTEND"
    PAPER_HALTED_OPS = "PAPER_HALTED_OPS"
    LIVE_PILOT_APPROVED = "LIVE_PILOT_APPROVED"
    PAPER_EXTENDED = "PAPER_EXTENDED"
    RETIRED = "RETIRED"
    INCONCLUSIVE_DATA = "INCONCLUSIVE_DATA"
    INCONCLUSIVE_HOLDOUT_CONTAMINATED = "INCONCLUSIVE_HOLDOUT_CONTAMINATED"
    INCONCLUSIVE_ENGINE = "INCONCLUSIVE_ENGINE"
    INCONCLUSIVE_TECHNICAL = "INCONCLUSIVE_TECHNICAL"


class Stage(StrEnum):
    """The step that produces a verdict transition (section 5.2 arrows)."""

    P3A = "P3A"
    P3B = "P3B"
    P4 = "P4"
    P5 = "P5"
    P6 = "P6"  # human decision


INCONCLUSIVE = frozenset(v for v in Verdict if v.value.startswith("INCONCLUSIVE_"))

_TRANSITIONS: dict[tuple[Verdict, Stage], frozenset[Verdict]] = {
    (Verdict.UNTESTED, Stage.P3A): frozenset({Verdict.STOP, Verdict.EXIT_SELECTED}) | INCONCLUSIVE,
    (Verdict.EXIT_SELECTED, Stage.P3B): frozenset({Verdict.STOP, Verdict.ADVANCE_TO_P4})
    | INCONCLUSIVE,
    (Verdict.ADVANCE_TO_P4, Stage.P4): frozenset(
        {Verdict.PASS_HISTORICAL_PENDING_PROSPECTIVE, Verdict.REJECT}
    )
    | INCONCLUSIVE,
    (Verdict.PASS_HISTORICAL_PENDING_PROSPECTIVE, Stage.P5): frozenset(
        {
            Verdict.PAPER_PASS,
            Verdict.PAPER_FAIL,
            Verdict.PAPER_EXTEND,
            Verdict.PAPER_HALTED_OPS,
        }
    ),
    (Verdict.PAPER_PASS, Stage.P6): frozenset(
        {Verdict.LIVE_PILOT_APPROVED, Verdict.PAPER_EXTENDED, Verdict.RETIRED}
    ),
}


def parse_verdict(value: object) -> Verdict:
    """Accept a ``Verdict`` or its exact string; anything else is refused."""
    if isinstance(value, Verdict):
        return value
    if isinstance(value, str):
        try:
            return Verdict(value)
        except ValueError:
            pass
    raise VerdictError(f"{value!r} is not in the closed verdict set (plan section 5.2)")


def allowed_next(current: Verdict, stage: Stage) -> frozenset[Verdict]:
    """Verdicts reachable from ``current`` at ``stage`` (empty if none)."""
    return _TRANSITIONS.get((current, stage), frozenset())


def is_valid_transition(current: object, stage: Stage, new: object) -> bool:
    """True only for an arrow drawn in section 5.2. Unknown strings are False."""
    try:
        cur, nxt = parse_verdict(current), parse_verdict(new)
        st = Stage(stage)
    except (VerdictError, ValueError):
        return False
    return nxt in allowed_next(cur, st)


def require_transition(current: object, stage: Stage, new: object) -> Verdict:
    """Like :func:`is_valid_transition` but raises ``VerdictError`` and returns the new verdict."""
    if not is_valid_transition(current, stage, new):
        raise VerdictError(f"invalid verdict transition {current!r} --({stage})--> {new!r}")
    return parse_verdict(new)
