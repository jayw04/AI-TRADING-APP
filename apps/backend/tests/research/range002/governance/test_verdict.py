from __future__ import annotations

import pytest

from app.research.range002.governance.errors import VerdictError
from app.research.range002.governance.verdict import (
    INCONCLUSIVE,
    Stage,
    Verdict,
    allowed_next,
    is_valid_transition,
    parse_verdict,
    require_transition,
)

PLAN_5_2_VALUES = {
    "UNTESTED",
    "EXIT_SELECTED",
    "STOP",
    "ADVANCE_TO_P4",
    "PASS_HISTORICAL_PENDING_PROSPECTIVE",
    "REJECT",
    "PAPER_PASS",
    "PAPER_FAIL",
    "PAPER_EXTEND",
    "PAPER_HALTED_OPS",
    "LIVE_PILOT_APPROVED",
    "PAPER_EXTENDED",
    "RETIRED",
    "INCONCLUSIVE_DATA",
    "INCONCLUSIVE_HOLDOUT_CONTAMINATED",
    "INCONCLUSIVE_ENGINE",
    "INCONCLUSIVE_TECHNICAL",
}


def test_enum_is_exactly_the_closed_set() -> None:
    assert {v.value for v in Verdict} == PLAN_5_2_VALUES
    assert len(INCONCLUSIVE) == 4


@pytest.mark.parametrize("bad", ["PASS", "pass", "", None, 3, "INCONCLUSIVE_OTHER"])
def test_parse_rejects_anything_outside_the_set(bad: object) -> None:
    with pytest.raises(VerdictError):
        parse_verdict(bad)


def test_parse_accepts_enum_and_exact_string() -> None:
    assert parse_verdict("STOP") is Verdict.STOP
    assert parse_verdict(Verdict.REJECT) is Verdict.REJECT


@pytest.mark.parametrize(
    ("cur", "stage", "nxt"),
    [
        (Verdict.UNTESTED, Stage.P3A, Verdict.STOP),
        (Verdict.UNTESTED, Stage.P3A, Verdict.EXIT_SELECTED),
        (Verdict.UNTESTED, Stage.P3A, Verdict.INCONCLUSIVE_ENGINE),
        (Verdict.EXIT_SELECTED, Stage.P3B, Verdict.ADVANCE_TO_P4),
        (Verdict.EXIT_SELECTED, Stage.P3B, Verdict.STOP),
        (Verdict.EXIT_SELECTED, Stage.P3B, Verdict.INCONCLUSIVE_DATA),
        (Verdict.ADVANCE_TO_P4, Stage.P4, Verdict.PASS_HISTORICAL_PENDING_PROSPECTIVE),
        (Verdict.ADVANCE_TO_P4, Stage.P4, Verdict.REJECT),
        (Verdict.ADVANCE_TO_P4, Stage.P4, Verdict.INCONCLUSIVE_HOLDOUT_CONTAMINATED),
        (Verdict.PASS_HISTORICAL_PENDING_PROSPECTIVE, Stage.P5, Verdict.PAPER_PASS),
        (Verdict.PASS_HISTORICAL_PENDING_PROSPECTIVE, Stage.P5, Verdict.PAPER_FAIL),
        (Verdict.PASS_HISTORICAL_PENDING_PROSPECTIVE, Stage.P5, Verdict.PAPER_EXTEND),
        (Verdict.PASS_HISTORICAL_PENDING_PROSPECTIVE, Stage.P5, Verdict.PAPER_HALTED_OPS),
        (Verdict.PAPER_PASS, Stage.P6, Verdict.LIVE_PILOT_APPROVED),
        (Verdict.PAPER_PASS, Stage.P6, Verdict.PAPER_EXTENDED),
        (Verdict.PAPER_PASS, Stage.P6, Verdict.RETIRED),
    ],
)
def test_drawn_arrows_are_valid(cur: Verdict, stage: Stage, nxt: Verdict) -> None:
    assert is_valid_transition(cur, stage, nxt)
    assert require_transition(cur, stage, nxt) is nxt


@pytest.mark.parametrize(
    ("cur", "stage", "nxt"),
    [
        (Verdict.UNTESTED, Stage.P3B, Verdict.EXIT_SELECTED),  # wrong stage
        (Verdict.UNTESTED, Stage.P3A, Verdict.ADVANCE_TO_P4),  # skips P3b
        (Verdict.UNTESTED, Stage.P4, Verdict.REJECT),  # skips straight to holdout
        (Verdict.STOP, Stage.P3B, Verdict.ADVANCE_TO_P4),  # terminal
        (Verdict.REJECT, Stage.P4, Verdict.PASS_HISTORICAL_PENDING_PROSPECTIVE),  # terminal
        (Verdict.INCONCLUSIVE_ENGINE, Stage.P3A, Verdict.EXIT_SELECTED),  # not a soft pass
        (Verdict.ADVANCE_TO_P4, Stage.P5, Verdict.PAPER_PASS),
        (Verdict.PAPER_PASS, Stage.P5, Verdict.LIVE_PILOT_APPROVED),
        (Verdict.PAPER_FAIL, Stage.P6, Verdict.RETIRED),
        (Verdict.EXIT_SELECTED, Stage.P3B, Verdict.PAPER_PASS),
    ],
)
def test_undrawn_arrows_are_invalid(cur: Verdict, stage: Stage, nxt: Verdict) -> None:
    assert not is_valid_transition(cur, stage, nxt)
    with pytest.raises(VerdictError):
        require_transition(cur, stage, nxt)


def test_unknown_strings_are_invalid_not_errors() -> None:
    assert not is_valid_transition("UNTESTED", Stage.P3A, "MAYBE")
    assert not is_valid_transition("NOPE", Stage.P3A, "STOP")
    assert not is_valid_transition("UNTESTED", "P9", "STOP")  # type: ignore[arg-type]


def test_terminal_states_have_no_exits() -> None:
    terminal = {Verdict.STOP, Verdict.REJECT, Verdict.PAPER_FAIL, Verdict.RETIRED, *INCONCLUSIVE}
    for v in terminal:
        for stage in Stage:
            assert allowed_next(v, stage) == frozenset()


def test_transition_table_is_deterministic() -> None:
    assert allowed_next(Verdict.UNTESTED, Stage.P3A) == allowed_next(Verdict.UNTESTED, Stage.P3A)
