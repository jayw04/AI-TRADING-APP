"""The two frozen earnings controls, tested against the adjudicated rules.

Every test names the frozen source or the 2026-08-12 adjudication it enforces, so a future change
that "simplifies" one of these has to argue with the contract rather than with a style preference.
"""

from __future__ import annotations

# Weekdays only: 2020-01-01 is a Wednesday; skip weekends so gaps are real calendar gaps.
from datetime import date, timedelta

import pytest

from app.research.mr002.phase3b.earnings_blackout import (
    BLACKOUT,
    COOLING,
    NO_ANCHOR,
    STALE_ANCHOR_DAYS,
    Anchor,
    BlackoutRefused,
    Calendar,
    cooling_interval,
    exclusions_for_security,
    first_prohibited_open,
    stale_anchor_start,
)


def _sessions(n: int, start: date = date(2020, 1, 1)) -> tuple[str, ...]:
    out, day = [], start
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day += timedelta(days=1)
    return tuple(out)


CAL = Calendar(_sessions(400))


def _anchor(session: str, cls: str = "PRE_OPEN", accession: str = "a1") -> Anchor:
    return Anchor(1, "AAA", accession, session, cls)


# --------------------------------------------------------------------- v0.5 §1 session mapping
def test_pre_open_prohibits_s_and_s_plus_one():
    a = _anchor(CAL.sessions[10], "PRE_OPEN")
    assert first_prohibited_open(a, CAL) == 10
    assert cooling_interval(a, CAL) == (10, 11)


@pytest.mark.parametrize("cls", ["IN_SESSION", "POST_CLOSE"])
def test_in_session_and_post_close_prohibit_s_plus_one_and_s_plus_two(cls):
    """v0.5 §1 corrected v0.4: the `s` open traded before the information existed."""
    a = _anchor(CAL.sessions[10], cls)
    assert first_prohibited_open(a, CAL) == 11
    assert cooling_interval(a, CAL) == (11, 12)


def test_date_only_is_treated_conservatively_like_post_close():
    a = _anchor(CAL.sessions[10], "DATE_ONLY")
    assert cooling_interval(a, CAL) == (11, 12)


def test_an_unregistered_availability_class_is_refused_not_defaulted():
    with pytest.raises(BlackoutRefused, match="unregistered availability class"):
        first_prohibited_open(_anchor(CAL.sessions[3], "SOMETHING_ELSE"), CAL)


def test_off_calendar_anchor_maps_to_the_first_open_after_availability():
    """1 of 16,357 development anchors is dated off-calendar; the rule must still be total."""
    saturday = "2020-01-04"
    assert saturday not in CAL.sessions
    monday = CAL.sessions.index("2020-01-06")
    assert first_prohibited_open(_anchor(saturday, "PRE_OPEN"), CAL) == monday
    assert first_prohibited_open(_anchor(saturday, "POST_CLOSE"), CAL) == monday


# --------------------------------------------------------------------- the 70-day rule
def test_threshold_is_inclusive_at_seventy_calendar_days():
    """Adjudicated 2026-08-12: anchor_date + 70 days, NOT +71, NOT 70 trading sessions."""
    assert STALE_ANCHOR_DAYS == 70
    anchor_day = date.fromisoformat(CAL.sessions[0])
    a = _anchor(CAL.sessions[0])
    start = stale_anchor_start(a, CAL)
    threshold = (anchor_day + timedelta(days=70)).isoformat()
    assert CAL.sessions[start] >= threshold
    assert start == 0 or CAL.sessions[start - 1] < threshold


def test_blackout_start_is_not_seventy_trading_sessions():
    a = _anchor(CAL.sessions[0])
    start = stale_anchor_start(a, CAL)
    assert start != 70, "70 calendar days is roughly 48 sessions, never 70 sessions"
    assert 44 <= start <= 52


def test_a_later_anchor_ends_the_blackout_and_resets_the_clock():
    first = _anchor(CAL.sessions[0], "PRE_OPEN", "a1")
    second = _anchor(CAL.sessions[120], "PRE_OPEN", "a2")
    reasons = exclusions_for_security([first, second], CAL)
    start = stale_anchor_start(first, CAL)
    assert BLACKOUT in reasons[start]
    assert BLACKOUT not in reasons.get(120, set()), "the new release must end the blackout"
    assert COOLING in reasons[120] and COOLING in reasons[121]


# --------------------------------------------------------------------- reasons stay separate
def test_cooling_and_blackout_are_never_collapsed_into_one_flag():
    """Their economics run in opposite directions in time; the deciding reason must survive."""
    a = _anchor(CAL.sessions[0])
    reasons = exclusions_for_security([a], CAL)
    cooling = {o for o, r in reasons.items() if COOLING in r}
    blackout = {o for o, r in reasons.items() if BLACKOUT in r}
    assert cooling and blackout
    assert cooling.isdisjoint(blackout), "cooling and blackout must not overlap for one anchor"
    assert max(cooling) < min(blackout)


def test_sessions_before_the_first_anchor_are_ineligible_for_want_of_an_anchor():
    """v0.4 §2: a stock without a prior confirmed anchor is ineligible."""
    a = _anchor(CAL.sessions[30])
    reasons = exclusions_for_security([a], CAL)
    assert NO_ANCHOR in reasons[0] and NO_ANCHOR in reasons[29]
    assert NO_ANCHOR not in reasons.get(30, set())


def test_a_security_with_no_anchor_at_all_is_ineligible_everywhere():
    reasons = exclusions_for_security([], CAL)
    assert all(NO_ANCHOR in reasons[o] for o in range(len(CAL.sessions)))


# --------------------------------------------------------------------- amendment semantics
def test_amendment_without_original_is_itself_an_anchor():
    """Adjudicated: it represents first PIT knowledge of that release."""
    a = Anchor(1, "AAA", "acc-amd", CAL.sessions[10], "PRE_OPEN", is_amendment_origin=True)
    reasons = exclusions_for_security([a], CAL)
    assert COOLING in reasons[10]
    assert stale_anchor_start(a, CAL) is not None


def test_anchor_ordering_is_deterministic_regardless_of_input_order():
    a1 = _anchor(CAL.sessions[10], "PRE_OPEN", "a1")
    a2 = _anchor(CAL.sessions[50], "PRE_OPEN", "a2")
    assert exclusions_for_security([a1, a2], CAL) == exclusions_for_security([a2, a1], CAL)


def test_empty_calendar_is_refused():
    with pytest.raises(BlackoutRefused, match="empty registered calendar"):
        exclusions_for_security([_anchor("2020-01-02")], Calendar(()))


# --------------------------------------------------------------------- non-vacuity
def test_the_controls_actually_exclude_something():
    """A control that never fires is the defect this module exists to correct."""
    a = _anchor(CAL.sessions[0])
    reasons = exclusions_for_security([a], CAL)
    excluded = {o for o, r in reasons.items() if r - {NO_ANCHOR}}
    assert len(excluded) > 100, f"only {len(excluded)} sessions excluded; the rule is not firing"
