"""The two frozen earnings eligibility controls, as adjudicated 2026-08-12.

Phase 2B implemented neither. `cooling_start_session` / `cooling_end_session` were declared and
never populated, so both consumers computed `excludes=False` for every anchor, and the development
run's refusal census contains no `event_blackout` outcome at all. These are the two controls:

* **post-release cooling** - no entry may execute during the first two regular sessions following a
  confirmed release (v0.4, owner-frozen wording; session mapping CORRECTED by v0.5 §1);
* **stale-anchor blackout** - beginning 70 calendar days after the anchor, the security is
  ineligible for new entry until the next confirmed release resets the anchor (v0.4 V1).

They are deliberately NOT collapsed into one boolean. Their economics run in opposite directions in
time - cooling guards the interval immediately after a release, the blackout guards the interval
long after one - so the deciding reason is preserved per (security, session).

Value-blind: this module consumes anchor timing and the registered calendar. It never reads a
price, a return or a signal, and it computes no performance.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

STALE_ANCHOR_DAYS = 70  # v0.4 V1: "beginning 70 calendar days after that release"
COOLING_SESSIONS = 2  # v0.4: "the first two regular trading sessions following a release"

PRE_OPEN = "PRE_OPEN"
IN_SESSION = "IN_SESSION"
POST_CLOSE = "POST_CLOSE"
DATE_ONLY = "DATE_ONLY"

COOLING = "post_release_cooling"
BLACKOUT = "stale_anchor_blackout"
NO_ANCHOR = "no_prior_confirmed_anchor"


class BlackoutRefused(Exception):
    """An anchor that cannot be placed on the registered calendar. Never guessed."""


@dataclass(frozen=True)
class Anchor:
    """One confirmed release, exactly as the sealed anchors table carries it."""

    cik: int
    ticker: str
    accession: str
    session_date: str
    availability_class: str
    is_amendment_origin: bool = False


@dataclass(frozen=True)
class Calendar:
    """Registered sessions, ascending. Ordinals are indices into this list."""

    sessions: tuple[str, ...]

    def first_on_or_after(self, day: str) -> int | None:
        lo, hi = 0, len(self.sessions)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.sessions[mid] < day:
                lo = mid + 1
            else:
                hi = mid
        return lo if lo < len(self.sessions) else None

    def first_strictly_after(self, day: str) -> int | None:
        idx = self.first_on_or_after(day)
        if idx is None:
            return None
        if self.sessions[idx] == day:
            return idx + 1 if idx + 1 < len(self.sessions) else None
        return idx


def first_prohibited_open(anchor: Anchor, calendar: Calendar) -> int | None:
    """The first registered open occurring AFTER the availability instant.

    This single rule reproduces the frozen v0.5 §1 mapping exactly for every anchor whose date is a
    trading session - PRE_OPEN gives `s`, IN_SESSION and POST_CLOSE give `s+1` - and extends
    deterministically to an anchor dated off the calendar, where "the open of session s" has no
    referent. It is a restatement of the frozen rule, not an additional choice.
    """
    if anchor.availability_class == PRE_OPEN:
        return calendar.first_on_or_after(anchor.session_date)
    if anchor.availability_class in (IN_SESSION, POST_CLOSE, DATE_ONLY):
        return calendar.first_strictly_after(anchor.session_date)
    raise BlackoutRefused(f"unregistered availability class: {anchor.availability_class}")


def cooling_interval(anchor: Anchor, calendar: Calendar) -> tuple[int, int] | None:
    """The two prohibited execution opens following a release, as session ordinals."""
    start = first_prohibited_open(anchor, calendar)
    if start is None:
        return None
    end = min(start + COOLING_SESSIONS - 1, len(calendar.sessions) - 1)
    return start, end


def stale_anchor_start(anchor: Anchor, calendar: Calendar) -> int | None:
    """First ineligible session under the 70-calendar-day rule.

    Adjudicated 2026-08-12: the threshold date is `anchor_date + 70 days`, INCLUSIVE, and the first
    ineligible session is the first registered session on or after it. Not `+71`, not
    "70 trading sessions", and never previous-session placement.
    """
    try:
        anchor_day = date.fromisoformat(anchor.session_date[:10])
    except ValueError as exc:
        raise BlackoutRefused(f"unparseable anchor date {anchor.session_date}") from exc
    threshold = (anchor_day + timedelta(days=STALE_ANCHOR_DAYS)).isoformat()
    return calendar.first_on_or_after(threshold)


def exclusions_for_security(anchors: list[Anchor], calendar: Calendar) -> dict[int, set[str]]:
    """Per-session exclusion reasons for one security. Reasons are kept SEPARATE, never OR-ed away.

    Anchor ordering is by session date then accession, so the result is deterministic. Every row in
    the anchors table is a confirmed-release anchor: duplicate collapse and matching amendments were
    resolved when the table was built, and an amendment without an original is itself an anchor
    representing first PIT knowledge. `amended_by` never retroactively moves an established
    interval - only a newly established anchor resets the clocks.
    """
    if not calendar.sessions:
        raise BlackoutRefused("empty registered calendar")
    ordered = sorted(anchors, key=lambda a: (a.session_date, a.accession))
    reasons: dict[int, set[str]] = {}

    def mark(lo: int, hi: int, reason: str) -> None:
        for ordinal in range(max(lo, 0), min(hi, len(calendar.sessions) - 1) + 1):
            reasons.setdefault(ordinal, set()).add(reason)

    for i, anchor in enumerate(ordered):
        window = cooling_interval(anchor, calendar)
        if window is not None:
            mark(window[0], window[1], COOLING)

        start = stale_anchor_start(anchor, calendar)
        if start is None:
            continue
        # The next confirmed release ends the blackout: it resets the anchor.
        nxt = ordered[i + 1] if i + 1 < len(ordered) else None
        if nxt is None:
            end = len(calendar.sessions) - 1
        else:
            nxt_open = first_prohibited_open(nxt, calendar)
            end = len(calendar.sessions) - 1 if nxt_open is None else nxt_open - 1
        if end >= start:
            mark(start, end, BLACKOUT)

    # Before the first anchor there is no prior confirmed release: ineligible (v0.4 §2).
    first_open = first_prohibited_open(ordered[0], calendar) if ordered else None
    horizon = len(calendar.sessions) if first_open is None else first_open
    mark(0, horizon - 1, NO_ANCHOR)
    return reasons
