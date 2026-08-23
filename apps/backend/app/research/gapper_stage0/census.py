"""Per-candidate-date data-sufficiency census — the K4 deliverable (memo §6.7).

For each candidate-date, classifies every data field the Stage-0 measurements
need as ``available`` / ``partial`` / ``absent``:

* ``minute_bar_coverage`` — RTH 1-min bar coverage vs the 390-minute session
* ``premarket_bars`` — raw premarket prints (the reconstruction input)
* ``first_bar_ts`` / ``last_bar_ts`` — session boundary observability
* ``missing_bar_count`` — computable gap count vs the expected session
* ``quote_data`` — bid/ask (currently expected ABSENT; gapper_shadow.py
  documents spread as unobservable from OHLCV — MDQ collector would supply)
* ``halt_data`` — LULD/halt channel (ABSENT; SIP ws ``s``/``l`` not captured)
* ``locate_ssr_data`` — locate/borrow/SSR (ABSENT; no source in repo)

The aggregate report counts each field's statuses and compares the number of
**sufficient event-days** against the §3.1 contract target (≥250, preferred
500+) — the honest-shortfall measurement the scoping memo names as the correct
deliverable. Pure classification: all bars arrive by injection.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, time
from typing import Any

import pandas as pd

from app.research.gapper_stage0.dataset_contract import DatasetContract

_ET = "America/New_York"
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)

#: Expected 1-min bars in a full regular session (09:30–16:00 ET).
RTH_EXPECTED_MINUTES = 390
#: Conservative: coverage below this fraction is only "partial".
COVERAGE_AVAILABLE_MIN_FRACTION = 0.95
#: Conservative: fewer premarket prints than this is only "partial".
PREMARKET_AVAILABLE_MIN_BARS = 30

AVAILABLE = "available"
PARTIAL = "partial"
ABSENT = "absent"
STATUSES = (AVAILABLE, PARTIAL, ABSENT)

CENSUS_FIELDS = (
    "minute_bar_coverage",
    "premarket_bars",
    "first_bar_ts",
    "last_bar_ts",
    "missing_bar_count",
    "quote_data",
    "halt_data",
    "locate_ssr_data",
)

#: A candidate-date is "sufficient" only when every core reconstruction field
#: is fully available. Quote/halt/locate are censused but not required here —
#: their absence is reported per-field (they gate specific §3.3 measurements,
#: e.g. friction and halt frequency, not the event reconstruction itself).
CORE_SUFFICIENCY_FIELDS = (
    "minute_bar_coverage",
    "premarket_bars",
    "first_bar_ts",
    "last_bar_ts",
    "missing_bar_count",
)

CENSUS_SCHEMA = "gapper_stage0/census_report/v1"


def _presence(flag: bool) -> str:
    return AVAILABLE if flag else ABSENT


def census_day(
    symbol: str,
    day: date,
    minute_bars: pd.DataFrame | None,
    *,
    quote_data_present: bool = False,
    halt_data_present: bool = False,
    locate_ssr_data_present: bool = False,
) -> dict[str, Any]:
    """Classify one candidate-date's data availability. Pure; bars injected."""
    fields: dict[str, str] = {}
    details: dict[str, Any] = {}

    if minute_bars is None or len(minute_bars) == 0:
        day_bars = pd.DataFrame(columns=["t", "_et"])
    else:
        day_bars = minute_bars.copy()
        day_bars["_et"] = pd.to_datetime(day_bars["t"], utc=True).dt.tz_convert(_ET)
        day_bars = day_bars[day_bars["_et"].dt.date == day].sort_values("_et")

    et_times = day_bars["_et"].dt.time if len(day_bars) else pd.Series([], dtype=object)
    rth_count = int(((et_times >= RTH_OPEN) & (et_times < RTH_CLOSE)).sum()) if len(day_bars) else 0
    pm_count = int((et_times < RTH_OPEN).sum()) if len(day_bars) else 0

    coverage_fraction = rth_count / RTH_EXPECTED_MINUTES
    if rth_count == 0:
        fields["minute_bar_coverage"] = ABSENT
    elif coverage_fraction >= COVERAGE_AVAILABLE_MIN_FRACTION:
        fields["minute_bar_coverage"] = AVAILABLE
    else:
        fields["minute_bar_coverage"] = PARTIAL
    details["rth_bar_count"] = rth_count
    details["coverage_fraction"] = round(coverage_fraction, 4)

    if pm_count == 0:
        fields["premarket_bars"] = ABSENT
    elif pm_count >= PREMARKET_AVAILABLE_MIN_BARS:
        fields["premarket_bars"] = AVAILABLE
    else:
        fields["premarket_bars"] = PARTIAL
    details["premarket_bar_count"] = pm_count

    if len(day_bars):
        fields["first_bar_ts"] = AVAILABLE
        fields["last_bar_ts"] = AVAILABLE
        details["first_bar_ts"] = day_bars["_et"].iloc[0].isoformat()
        details["last_bar_ts"] = day_bars["_et"].iloc[-1].isoformat()
    else:
        fields["first_bar_ts"] = ABSENT
        fields["last_bar_ts"] = ABSENT
        details["first_bar_ts"] = None
        details["last_bar_ts"] = None

    if rth_count > 0:
        fields["missing_bar_count"] = AVAILABLE
        details["missing_bar_count"] = max(RTH_EXPECTED_MINUTES - rth_count, 0)
    else:
        fields["missing_bar_count"] = ABSENT
        details["missing_bar_count"] = None

    fields["quote_data"] = _presence(quote_data_present)
    fields["halt_data"] = _presence(halt_data_present)
    fields["locate_ssr_data"] = _presence(locate_ssr_data_present)

    sufficient = all(fields[f] == AVAILABLE for f in CORE_SUFFICIENCY_FIELDS)
    return {
        "symbol": symbol,
        "day": day.isoformat(),
        "fields": fields,
        "details": details,
        "sufficient": sufficient,
    }


def census_report(rows: Sequence[dict[str, Any]], contract: DatasetContract) -> dict[str, Any]:
    """Aggregate per-candidate-date rows into the field-availability report.

    ``sufficient_event_days`` counts distinct days holding at least one
    sufficient candidate-date (§3.1 counts event-*days*); the per-row count is
    also reported. ``meets_target`` compares event-days to the contract target.
    """
    field_counts: dict[str, dict[str, int]] = {f: dict.fromkeys(STATUSES, 0) for f in CENSUS_FIELDS}
    for row in rows:
        for f in CENSUS_FIELDS:
            status = row["fields"][f]
            if status not in STATUSES:
                raise ValueError(f"row {row['symbol']}/{row['day']}: bad status {status!r} for {f}")
            field_counts[f][status] += 1

    sufficient_rows = [r for r in rows if r["sufficient"]]
    sufficient_days = sorted({r["day"] for r in sufficient_rows})
    target = contract.target_event_days
    return {
        "schema": CENSUS_SCHEMA,
        "candidate_dates": len(rows),
        "distinct_days": len({r["day"] for r in rows}),
        "field_counts": field_counts,
        "sufficient_candidate_dates": len(sufficient_rows),
        "sufficient_event_days": len(sufficient_days),
        "target_event_days": target,
        "meets_target": len(sufficient_days) >= target,
        "shortfall_event_days": max(target - len(sufficient_days), 0),
        "contract_sha256": contract.sha256(),
        "contract_complete": contract.is_complete(),
        "rows": list(rows),
    }
