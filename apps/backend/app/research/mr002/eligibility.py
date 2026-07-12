"""MR-002 PIT eligibility gates — FROZEN v1.0 §2/§4 (immutable).

Every gate is point-in-time: a decision made for execution at the session-(t+1)
open may use ONLY information available at the close of session t.

Gates implemented:
  * universe membership (monthly PIT reconstitution; long top-250 / short top-150);
  * sector resolution through the frozen identity chain:
        (permaticker, date) -> CIK  [crosswalk + countersigned predecessor overrides]
        (CIK, date)         -> PIT SIC segment  [NO forward-fill before first obs]
        (SIC, date)         -> sector ETF       [mapping v0.8 + security overrides v0.6]
    An unresolved sector at any link => INELIGIBLE (never defaulted);
  * PIT estimated earnings-risk blackout (frozen §4):
        - 70 CALENDAR DAYS after the last confirmed anchor => ineligible for new
          entry, and any open position exits at the first available official open;
        - POST-RELEASE COOLING: no entry may execute during the first two regular
          sessions following a confirmed release. BMO release on session s =>
          prohibited execution opens s and s+1. AMC => s+1 and s+2. In-session /
          ambiguous availability is treated as the PIT-safe side (s+1, s+2).
        - a security with NO prior confirmed anchor is INELIGIBLE;
        - NO retroactive exits: information learned after the last pre-event open
          exits at the first executable open thereafter (recorded as an exception).
  * announced corporate actions (announcement-dated, never outcome-dated);
  * liquidity envelope + the economic-gap filter live in the execution layer.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, timedelta

BLACKOUT_CALENDAR_DAYS = 70
COOLING_SESSIONS = 2


@dataclass(frozen=True)
class Anchor:
    """A confirmed earnings release (frozen V1 population)."""

    session_date: date          # ET calendar date of availability
    availability_class: str     # PRE_OPEN | IN_SESSION | POST_CLOSE | DATE_ONLY
    event_time_basis: str


class EarningsBlackout:
    """The frozen PIT estimated earnings-risk blackout for ONE security."""

    def __init__(self, anchors: list[Anchor], sessions: list[date]) -> None:
        self.anchors = sorted(anchors, key=lambda a: a.session_date)
        self._dates = [a.session_date for a in self.anchors]
        self.sessions = sessions                      # frozen trading calendar
        self._sidx = {d: i for i, d in enumerate(sessions)}

    def _session_index(self, d: date) -> int:
        """Index of the last session on/before d (the frozen calendar)."""
        return bisect_right(self.sessions, d) - 1

    def last_anchor_asof(self, decision_close: date) -> Anchor | None:
        """The most recent anchor AVAILABLE at the close of `decision_close`."""
        i = bisect_right(self._dates, decision_close) - 1
        return self.anchors[i] if i >= 0 else None

    def cooling_blocked_opens(self, a: Anchor) -> set[int]:
        """Session indices whose OPEN may not execute an entry (frozen wording).

        BMO (PRE_OPEN) on session s -> prohibited opens s and s+1.
        AMC (POST_CLOSE) / IN_SESSION / DATE_ONLY -> prohibited opens s+1 and s+2
        (the PIT-safe side: the s open traded before the information existed).
        """
        s = self._session_index(a.session_date)
        if s < 0:
            return set()
        if a.availability_class == "PRE_OPEN":
            start = s
        else:
            start = s + 1
        return {start + k for k in range(COOLING_SESSIONS)}

    def entry_allowed(self, decision_close: date, exec_open: date) -> tuple[bool, str]:
        """May an entry decided at `decision_close` execute at `exec_open`?"""
        a = self.last_anchor_asof(decision_close)
        if a is None:
            return False, "no_prior_confirmed_anchor"          # frozen §2
        # 70-calendar-day forward blackout (an approaching release)
        if (exec_open - a.session_date).days >= BLACKOUT_CALENDAR_DAYS:
            return False, "earnings_blackout_70d"
        # post-release cooling (the opposite risk: information-driven moves)
        ei = self._sidx.get(exec_open)
        if ei is not None and ei in self.cooling_blocked_opens(a):
            return False, "post_release_cooling"
        return True, ""

    def must_exit(self, decision_close: date, exec_open: date) -> bool:
        """An open position must exit once the 70-day blackout engages."""
        a = self.last_anchor_asof(decision_close)
        if a is None:
            return True
        return (exec_open - a.session_date).days >= BLACKOUT_CALENDAR_DAYS


def _as_date(x) -> date | None:
    """Accept str | date | datetime | None (DuckDB returns dates as objects)."""
    if x is None or x == "":
        return None
    if isinstance(x, date):
        return x
    if hasattr(x, "date"):
        return x.date()
    return date.fromisoformat(str(x)[:10])


class SectorResolver:
    """Frozen identity -> PIT SIC -> sector-ETF chain. Unresolved => ineligible."""

    def __init__(self, crosswalk: dict, sic_segments: dict, mapping: list,
                 sec_overrides: list, etf_live: dict) -> None:
        self.crosswalk = crosswalk          # permaticker -> [(from, to, cik)]
        self.segments = sic_segments        # cik -> [(from, to, sic)]
        self.mapping = mapping              # rows of the frozen mapping v0.8
        self.sec_overrides = sec_overrides  # frozen security overrides v0.6
        self.etf_live = etf_live

    def cik_at(self, perma: int, on: date) -> int | None:
        for f, t, c in self.crosswalk.get(perma, []):
            if f <= on and (t is None or on <= t):
                return c
        return None

    def sic_at(self, cik: int, on: date) -> str | None:
        for f, t, sic in self.segments.get(cik, []):
            if f <= on and (t is None or on < t):
                return sic
        return None                              # NO forward-fill before first obs

    def sector_etf(self, perma: int, on: date) -> tuple[str | None, str]:
        """-> (sector ETF, reason). None means INELIGIBLE (never defaulted)."""
        for o in self.sec_overrides:
            of, ot = _as_date(o["effective_from"]), _as_date(o["effective_to"])
            if o["permaticker"] and int(o["permaticker"]) == perma \
                    and (of is None or on >= of) and (ot is None or on <= ot):
                if o["review_status"] != "approved":
                    return None, "override_needs_revision"
                return o["sector_etf"], "security_override"
        cik = self.cik_at(perma, on)
        if cik is None:
            return None, "identity_unresolved"
        sic = self.sic_at(cik, on)
        if sic is None:
            return None, "no_pit_sic"
        code = int(sic)
        for r in self.mapping:
            rf, rt = _as_date(r["effective_from"]), _as_date(r["effective_to"])
            if int(r["sic_start"]) <= code <= int(r["sic_end"]) \
                    and (rf is None or on >= rf) and (rt is None or on <= rt):
                if r["mapping_confidence"] == "LOW":
                    return None, "excluded_low_confidence"
                live = self.etf_live.get(r["sector_etf"])
                if live and on < live:
                    return None, "sector_etf_not_yet_live"
                return r["sector_etf"], f"sic_mapping_{r['mapping_confidence']}"
        return None, "unmapped_sic"


def announced_action_block(actions: list[dict], on: date) -> str | None:
    """Announcement-dated corporate-action exclusion (never outcome-dated).

    A stock is blocked from NEW entries once a prohibited action is ANNOUNCED
    (merger / delisting / reorganization). Open positions exit at the next open.
    """
    for a in actions:
        if a["date"] <= on and a["action"] in (
                "acquisitionby", "delisted", "bankruptcy", "regulatorychange"):
            return a["action"]
    return None


def blackout_exit_date(anchor_session: date) -> date:
    """First calendar date on which the 70-day blackout engages."""
    return anchor_session + timedelta(days=BLACKOUT_CALENDAR_DAYS)
