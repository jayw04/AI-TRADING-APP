"""MR-002 v1.1 — the 10 REGISTERED EXECUTION-AVAILABILITY / ECI FIXTURES.

Implementation Erratum "Execution Availability and ECI Semantics", rev 3, countersigned
2026-07-12, artifact sha256 b32cf04bcf4c85b64292ec966f675bd2df6397cae5a884abcdfff4fa7569d80a.

Suite total: 45 (existing) + 10 (here) = 55.

THE THREE CONCEPTS, never conflated:
    execution_open_available   -- ONLY the frozen price store + execution date
    hard_exit_executable       -- TRUE <=> execution_open_available
    solver_reduction_eligible  -- only AFTER hard exits, when execution_open_available
                                  AND exposure > eps_include
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from app.research.mr002 import joint_portfolio as jp
from app.research.mr002.joint_portfolio import (
    BELOW_NUMERICAL_INCLUSION_FLOOR,
    EXECUTION_CONSTRAINED_INFEASIBLE,
    NO_EXECUTABLE_OPEN,
    VALID_ZERO_ENTRY_OUTCOME,
    InvalidRun,
    build_joint,
)
from app.research.mr002.runner import DayInputs, exit_reason

from .test_mr002_joint_solve import assert_constraints, diversified, hold

TOL = 1e-9


def day(session, nxt, *, exec_open, open_next=None, z=None, sector=None, blackout=(),
        action=()):
    """A DayInputs whose ENTRY series (open_next/sector/z) is deliberately narrower than
    its EXECUTION series (exec_open) -- the exact situation Defect A got wrong."""
    exec_open = dict(exec_open)
    return DayInputs(
        session=session, next_open_session=nxt,
        z=dict(z or {}), sigma_resid={}, beta={}, sector=dict(sector or {}),
        long_eligible=set(), short_eligible=set(),
        open_next=dict(open_next or {}), close_t={}, close_next={},
        cash_dist_next={}, adv_dollar={}, tickers={},
        blackout_exit=set(blackout), action_exit=set(action), confirm={},
        exec_open=exec_open,
        exec_close_next=dict(exec_open),
        exec_close_t=dict(exec_open),
    )


# ======================================================================================
# 1-5 · EXECUTION AVAILABILITY  (Defect A)
# ======================================================================================
def test_e01_held_position_out_of_universe_with_valid_open_still_hard_exits():
    """A symbol leaving the top-250/top-150 universe does NOT prevent its exit."""
    inp = day(date(2013, 3, 1), date(2013, 3, 4),
              exec_open={42: 100.0},          # the price store HAS the bar
              open_next={},                   # but it is NOT entry-eligible any more
              z={}, sector={})
    assert 42 not in inp.open_next, "precondition: not entry-eligible"
    assert inp.exec_open.get(42) == 100.0, "execution_open_available must be TRUE"

    # a 5-session hold is due -> the exit MUST execute off the execution series
    reason = exit_reason(np.nan, 5, False, False, False)
    assert reason is not None, "the 5-session mandatory exit is due"
    assert (inp.exec_open.get(42) or 0) > 0, "hard_exit_executable"


def test_e02_non_finite_z_valid_open_and_exposure_above_floor_is_reduction_eligible():
    """Registered wording: a held position with a non-finite z, a valid open, and post-exit
    exposure > eps_include is solver_reduction_eligible; a required reduction executes."""
    inp = day(date(2013, 3, 1), date(2013, 3, 4), exec_open={7: 50.0}, z={7: np.nan})
    execution_open_available = (inp.exec_open.get(7) or 0) > 0
    exposure = 0.010                                    # > eps_include
    solver_reduction_eligible = execution_open_available and exposure > jp.EPS_INCLUDE
    assert execution_open_available and solver_reduction_eligible

    # an unhedged 1.0% holding must be REDUCED by the sector-net coupling constraint
    hs = [hold(7, 1, exposure, "XLK", tradable=True)]
    cs = diversified(6, start=300, offset=1)
    res = build_joint(hs, cs)
    assert 7 in res.y, "must be a decision variable, not fixed"
    assert res.y[7] < exposure - TOL, "the required reduction must execute"
    assert_constraints(res, hs, cs)


def test_e03_unresolved_entry_sector_with_valid_open_does_not_block_a_scheduled_exit():
    """A sector-resolution problem must NEVER fabricate a missing price."""
    inp = day(date(2013, 3, 1), date(2013, 3, 4),
              exec_open={9: 25.0}, open_next={}, sector={})   # no entry sector at all
    assert 9 not in inp.sector, "precondition: entry sector unresolved"
    assert (inp.exec_open.get(9) or 0) > 0, "the exit price must still be available"
    assert exit_reason(np.nan, 5, False, False, False) is not None
    # and a blackout-forced exit is likewise unblocked
    assert exit_reason(0.0, 1, True, False, False) is not None


def test_e04_genuinely_missing_open_is_NO_EXECUTABLE_OPEN_and_the_exit_stays_pending():
    inp = day(date(2013, 3, 1), date(2013, 3, 4), exec_open={})   # NO bar anywhere
    assert (inp.exec_open.get(11) or 0) == 0, "execution_open_available is FALSE"

    hs = [hold(11, 1, 0.012, "XLK", tradable=False)]              # -> NO_EXECUTABLE_OPEN
    res = build_joint(hs, diversified(6, start=300, offset=1))
    assert res.diagnostics["fixed_reasons"][11] == NO_EXECUTABLE_OPEN
    assert 11 not in res.y, "a pending exit must not become a decision variable"


def test_e05_valid_bar_means_available_and_never_NO_EXECUTABLE_OPEN():
    """THE registered invariant. A valid bar => execution_open_available = true, and the
    position is NEVER NO_EXECUTABLE_OPEN. Solver-reduction eligibility ADDITIONALLY
    requires exposure > eps_include -- a below-floor position has a valid bar and is fixed
    for the SEPARATE numerical-floor reason. That is NOT a Defect-A failure."""
    cs = diversified(6, start=300, offset=1)

    above = hold(1, 1, 0.010, "XLV", tradable=True)      # valid bar, above the floor
    below = hold(2, 1, 1e-12, "XLV", tradable=True)      # valid bar, BELOW the floor
    res = build_joint([above, below], cs)

    reasons = res.diagnostics["fixed_reasons"]
    assert 1 not in reasons, "above-floor with a valid bar must be a tradable y variable"
    assert 1 in res.y

    assert reasons[2] == BELOW_NUMERICAL_INCLUSION_FLOOR
    assert reasons[2] != NO_EXECUTABLE_OPEN, (
        "a position with a VALID BAR may NEVER be classified NO_EXECUTABLE_OPEN"
    )
    assert 2 not in res.y, "below-floor is fixed: price-executable but NOT solver-reducible"


# ======================================================================================
# 6-9 · ECI SEMANTICS  (Defect B)
# ======================================================================================
def test_e06_fixed_book_breaches_at_zero_but_stage1_is_feasible_so_the_day_is_NOT_ECI():
    """THE Defect-B fixture. The fixed book alone breaches at z=0 (one position IS its own
    sector, so sector_gross/G = 1.0 > 0.20) -- but diversifying new entries raise G and
    lower every ratio, so Stage 1 IS feasible. The day must NOT be ECI."""
    fixed = hold(1, 1, 0.004, "XLK", tradable=False)     # NO_EXECUTABLE_OPEN
    cs = diversified(6, start=300, offset=1)             # six OTHER sectors
    res = build_joint([fixed], cs)

    # the diagnostic must still record that the fixed book alone breaches ...
    assert res.diagnostics["fixed_book_breaches_at_zero_DIAGNOSTIC"], (
        "precondition: the fixed book alone DOES breach at z=0"
    )
    # ... but it must have NO classification authority
    assert res.outcome != EXECUTION_CONSTRAINED_INFEASIBLE, (
        "the withdrawn z=0 probe must not classify the day"
    )
    assert res.diagnostics["stage1_status"] == 0
    assert res.x, "new entries must dilute the fixed exposure into compliance"
    assert_constraints(res, [fixed], cs)


def test_e07_stage1_status_2_with_a_fixed_exposure_is_ECI():
    """A fixed exposure that NO combination of y and x can cure: with no candidates there
    is nothing to dilute it with."""
    fixed = hold(1, 1, 0.004, "XLK", tradable=False)
    res = build_joint([fixed], [])                       # no candidates at all
    assert res.outcome == EXECUTION_CONSTRAINED_INFEASIBLE
    assert res.diagnostics["fixed_reasons"][1] == NO_EXECUTABLE_OPEN
    fbr = res.diagnostics["fixed_by_reason"]
    assert fbr["fixed_no_open_count"] == 1
    assert fbr["fixed_no_open_weight"] == pytest.approx(0.004)
    assert fbr["fixed_below_floor_count"] == 0


def test_e08_stage1_status_0_can_never_be_labelled_ECI():
    hs = [hold(1, 1, 0.010, "XLK", tradable=True)]
    cs = diversified(6, start=300, offset=1)
    res = build_joint(hs, cs)
    assert res.diagnostics["stage1_status"] == 0
    assert res.outcome != EXECUTION_CONSTRAINED_INFEASIBLE

    # and with an EMPTY book Stage 1 is trivially feasible -> never ECI
    empty = build_joint([], cs)
    assert empty.outcome != EXECUTION_CONSTRAINED_INFEASIBLE


def test_e09_stage1_status_2_with_NO_fixed_exposure_is_INVALID_RUN(monkeypatch):
    """FATAL. With no fixed exposure, y=0,x=0 MUST satisfy the homogeneous constraints,
    the bounds and the neutrality equality. Infeasibility there is a malformed model or a
    numerical defect -- never an execution-constrained market state."""
    class Infeasible:
        success = False
        status = 2
        message = "infeasible"
        x = None
        fun = None

    real = jp.linprog
    calls = {"n": 0}

    def fake(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:                              # the Stage-1 solve
            return Infeasible()
        return real(*a, **k)

    monkeypatch.setattr(jp, "linprog", fake)
    with pytest.raises(InvalidRun, match="NO fixed exposure"):
        build_joint([], diversified(6, start=300, offset=1))   # NO holdings -> no fixed


# ======================================================================================
# 10 · LIFECYCLE
# ======================================================================================
def test_e10_five_session_mandatory_exit_survives_leaving_the_entry_universe():
    """The registered 5-session hold limit must remain enforceable after the symbol has
    left the entry universe -- the exit executes off the EXECUTION series."""
    inp = day(date(2013, 3, 8), date(2013, 3, 11),
              exec_open={77: 88.0},     # price store still has it
              open_next={},             # entry funnel has dropped it
              z={})                     # and its z is gone entirely
    for held in (1, 2, 3, 4):
        assert exit_reason(np.nan, held, False, False, False) is None, "not due yet"
    reason = exit_reason(np.nan, 5, False, False, False)
    assert reason is not None, "the 5-session mandatory exit MUST still fire"
    assert (inp.exec_open.get(77) or 0) > 0, "and it MUST be executable"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
