"""Return-blind data-coverage and within-OR completeness reports.

Two DIFFERENT checks, implemented and reported separately:

1. **Dataset coverage** (the 98% requirement, Plan WP1.8). Denominator = EVERY point-in-time
   eligible symbol-day expected to have a regular session, including symbol-days for which the
   vendor returned no bars at all. There is deliberately NO "at least one print" eligibility
   condition: a completely missing symbol-day is a coverage failure, not an exclusion.
   Legitimate exclusions (``LEGITIMATE_EXCLUSIONS``) are documented independently by the caller
   and reported by reason. Anything else that is missing is reported as UNRESOLVED missingness,
   split into identity/ticker-mapping failures and plain missing data. Nothing is silently
   dropped.
2. **Within-OR completeness** of a symbol-day that HAS data: the number of confirmed DATA_GAP
   minutes in the opening range against the frozen rule (``or_max_gap_minutes``). It is reported
   with two denominators (observed symbol-days, and all expected symbol-days).

Inputs carry presence facts only (bar counts, minute stamps, gap minutes). No price, volume or
return field is read, so these functions are usable before any run is authorised.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, time

#: Reasons that legitimately remove a symbol-day from the coverage denominator. Each must be
#: documented independently of the bar data (calendar, listing record, halt notice).
LEGITIMATE_EXCLUSIONS = (
    "NO_REGULAR_SESSION",
    "NOT_YET_LISTED",
    "DELISTED_BEFORE_DAY",
    "VERIFIED_FULL_DAY_HALT",
)
MISSING_IDENTITY_MAPPING = "IDENTITY_MAPPING_FAILURE"
MISSING_NO_DATA = "NO_DATA_RETURNED"


@dataclass(frozen=True)
class DayPresence:
    """Presence facts for one observed symbol-day (no prices)."""

    bar_count: int
    or_bar_count: int
    or_gap_minutes: int


@dataclass(frozen=True)
class CoverageReport:
    expected: int
    legitimate_exclusions: dict[str, int]
    denominator: int
    observed: int
    missing_no_data: int
    missing_identity_mapping: int
    unresolved_unexplained: int
    coverage_rate: float | None
    meets_threshold: bool
    threshold: float
    by_year: dict[int, dict[str, int]]
    or_complete_of_observed: float | None
    or_complete_of_expected: float | None
    or_complete_count: int


PURE_FUNCTIONS = ("presence_from_minutes", "coverage_report")


def presence_from_minutes(
    bar_starts: Sequence[time], gap_minutes: Sequence[time], or_start: time, or_end: time
) -> DayPresence:
    in_or = sum(1 for t in bar_starts if or_start <= t <= or_end)
    gaps = sum(1 for t in set(gap_minutes) if or_start <= t <= or_end)
    return DayPresence(len(bar_starts), in_or, gaps)


def coverage_report(
    expected: Sequence[tuple[str, date]],
    observed: Mapping[tuple[str, date], DayPresence],
    *,
    exclusions: Mapping[tuple[str, date], str],
    missing_causes: Mapping[tuple[str, date], str],
    or_max_gap_minutes: int,
    threshold: float,
) -> CoverageReport:
    """Build the two reports.

    ``expected``: every PIT-eligible (symbol, day) expected to have a regular session.
    ``observed``: presence for symbol-days with at least one bar.
    ``exclusions``: documented legitimate exclusions (value must be in ``LEGITIMATE_EXCLUSIONS``).
    ``missing_causes``: optional diagnosis of a missing symbol-day
    (``IDENTITY_MAPPING_FAILURE`` / ``NO_DATA_RETURNED``); missing and undiagnosed counts as
    unexplained.

    Raises ``ValueError`` for duplicate expected rows, an exclusion with an unknown reason,
    observed rows that were never expected (a loader/universe mismatch is reported, not hidden),
    or an exclusion that also appears in ``observed`` is allowed (a verified halt day may still
    carry stray prints) and counted as excluded.
    """
    if len(set(expected)) != len(expected):
        raise ValueError("duplicate symbol-day in the expected set")
    exp = set(expected)
    unknown = [k for k, why in exclusions.items() if why not in LEGITIMATE_EXCLUSIONS]
    if unknown:
        raise ValueError(f"exclusion reasons not in LEGITIMATE_EXCLUSIONS: {sorted(unknown)[:3]}")
    stray = [k for k in observed if k not in exp]
    if stray:
        raise ValueError(f"observed symbol-days that were never expected: {sorted(stray)[:3]}")
    excl = {k: why for k, why in exclusions.items() if k in exp}
    reasons: dict[str, int] = {}
    for why in excl.values():
        reasons[why] = reasons.get(why, 0) + 1
    in_denominator = [k for k in expected if k not in excl]
    seen = [k for k in in_denominator if k in observed]
    missing = [k for k in in_denominator if k not in observed]
    ident = sum(1 for k in missing if missing_causes.get(k) == MISSING_IDENTITY_MAPPING)
    nodata = sum(1 for k in missing if missing_causes.get(k) == MISSING_NO_DATA)
    unexplained = len(missing) - ident - nodata
    denominator = len(in_denominator)
    rate = (len(seen) / denominator) if denominator else None
    by_year: dict[int, dict[str, int]] = {}
    for sym, day in in_denominator:
        row = by_year.setdefault(day.year, {"expected": 0, "observed": 0})
        row["expected"] += 1
        row["observed"] += 1 if (sym, day) in observed else 0
    or_ok = [k for k in seen if observed[k].or_gap_minutes <= or_max_gap_minutes]
    return CoverageReport(
        expected=len(exp),
        legitimate_exclusions=reasons,
        denominator=denominator,
        observed=len(seen),
        missing_no_data=nodata,
        missing_identity_mapping=ident,
        unresolved_unexplained=unexplained,
        coverage_rate=rate,
        meets_threshold=rate is not None and rate >= threshold,
        threshold=threshold,
        by_year=by_year,
        or_complete_of_observed=(len(or_ok) / len(seen)) if seen else None,
        or_complete_of_expected=(len(or_ok) / denominator) if denominator else None,
        or_complete_count=len(or_ok),
    )
