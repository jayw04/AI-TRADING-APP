"""MR-002 validation/OOS evaluator — frozen cost model (Increment 2, hardened v1.1).

Pure, synthetic-only. Implements the frozen base + stress + severe cost schedules and the two cost
primitives. Costs are computed from EXECUTED (filled) notional, never intended-order notional. Borrow
accrues only while a short position is economically held, over the ELAPSED CALENDAR DAYS between the
explicit entry and exit dates, using the frozen 360-day convention.

Frozen schedules (bps per side; borrow bps per year; 360-day borrow convention):
  * BASE    — 10 bps/side, 50 bps/yr borrow    (the governing base cost, GATE)
  * STRESS  — 20 bps/side, 300 bps/yr borrow   (mandatory cost-stress gate)
  * SEVERE  — 30 bps/side, 1000 bps/yr borrow  (severe diagnostic; reported, NEVER gated)

v1.1 hardening (adjudication 2026-07-20):
  * `validate_schedule` fail-closes any schedule that is not EXACTLY one of the three governing
    specs (name, both rates, day_count == 360, classification) -> CostRefused
    (REFUSED_CODE_OR_DATA_IDENTITY:COST_SCHEDULE). The low-level primitives still accept an arbitrary
    schedule; only the evaluator-facing execution layer enforces identity.
  * `borrow_cost` takes `days_held` as ELAPSED CALENDAR DAYS (computed by the execution layer from
    explicit entry/exit dates) and rejects non-int / bool day counts.

INTEGRITY_STOP codes: COST_NONFINITE, COST_NEGATIVE_NOTIONAL, BORROW_NEGATIVE_DAYS,
BORROW_DAYS_NOT_INT, BORROW_LONG_SIDE. REFUSED code: REFUSED_CODE_OR_DATA_IDENTITY:COST_SCHEDULE.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


class CostIntegrityStop(Exception):
    """Degenerate / out-of-domain cost input (frozen INTEGRITY_STOP with a specific code)."""


class CostRefused(Exception):
    """REFUSED_CODE_OR_DATA_IDENTITY — a cost schedule failed governing-identity validation."""


@dataclass(frozen=True)
class CostSchedule:
    name: str
    commission_slippage_bps_per_side: float
    borrow_bps_per_year: float
    borrow_day_count: int = 360
    classification: str = "GATE"          # GATE | DIAGNOSTIC


BASE = CostSchedule("BASE", 10.0, 50.0, 360, "GATE")
STRESS = CostSchedule("STRESS", 20.0, 300.0, 360, "GATE")
SEVERE = CostSchedule("SEVERE", 30.0, 1000.0, 360, "DIAGNOSTIC")

SCHEDULES = {s.name: s for s in (BASE, STRESS, SEVERE)}

# frozen governing specs: name -> (bps_per_side, borrow_bps_per_year, day_count, classification)
_GOVERNING_SPECS = {
    "BASE": (10.0, 50.0, 360, "GATE"),
    "STRESS": (20.0, 300.0, 360, "GATE"),
    "SEVERE": (30.0, 1000.0, 360, "DIAGNOSTIC"),
}


def _finite(x: float, code: str) -> float:
    xf = float(x)
    if not math.isfinite(xf):
        raise CostIntegrityStop(code)
    return xf


def validate_schedule(schedule: CostSchedule) -> CostSchedule:
    """Fail-closed: the schedule must be EXACTLY one of the three governing specs. Any unknown name,
    field mismatch, non-finite/negative rate, day_count != 360, or classification mismatch refuses
    with REFUSED_CODE_OR_DATA_IDENTITY:COST_SCHEDULE."""
    def refuse(detail: str):
        raise CostRefused(f"REFUSED_CODE_OR_DATA_IDENTITY:COST_SCHEDULE:{detail}")

    spec = _GOVERNING_SPECS.get(getattr(schedule, "name", None))
    if spec is None:
        refuse(f"UNKNOWN_NAME:{getattr(schedule, 'name', None)!r}")
    bps, borrow, day_count, classification = spec
    for field, value in (("bps_per_side", schedule.commission_slippage_bps_per_side),
                         ("borrow_bps_per_year", schedule.borrow_bps_per_year)):
        if not math.isfinite(float(value)) or float(value) < 0.0:
            refuse(f"RATE_NONFINITE_OR_NEGATIVE:{field}:{value!r}")
    if float(schedule.commission_slippage_bps_per_side) != bps:
        refuse(f"BPS_PER_SIDE:{schedule.commission_slippage_bps_per_side}!={bps}")
    if float(schedule.borrow_bps_per_year) != borrow:
        refuse(f"BORROW_BPS:{schedule.borrow_bps_per_year}!={borrow}")
    if schedule.borrow_day_count != 360 or schedule.borrow_day_count != day_count:
        refuse(f"DAY_COUNT:{schedule.borrow_day_count}!=360")
    if schedule.classification != classification:
        refuse(f"CLASSIFICATION:{schedule.classification}!={classification}")
    return schedule


def commission_slippage_cost(executed_notional: float, schedule: CostSchedule) -> float:
    """Commission + slippage for ONE executed side (a fill). Keyed to executed notional; a round trip
    incurs this once per leg (entry fill and exit fill). Low-level primitive: accepts any schedule."""
    n = _finite(executed_notional, "COST_NONFINITE")
    if n < 0.0:
        raise CostIntegrityStop("COST_NEGATIVE_NOTIONAL")
    return n * schedule.commission_slippage_bps_per_side / 10000.0


def borrow_cost(short_entry_notional: float, days_held: int, schedule: CostSchedule, *,
                is_short: bool) -> float:
    """Short-borrow financing over the holding period. Zero for a long leg. Principal = executed
    short-entry notional; accrual = principal · (borrow_bps/1e4) · (calendar_days / day_count).
    `days_held` MUST be an exact integer count of elapsed CALENDAR days (bool rejected)."""
    if not is_short:
        if float(short_entry_notional) != 0.0 or days_held != 0:
            # a borrow charge requested against a non-short leg is a modelling error
            raise CostIntegrityStop("BORROW_LONG_SIDE")
        return 0.0
    n = _finite(short_entry_notional, "COST_NONFINITE")
    if n < 0.0:
        raise CostIntegrityStop("COST_NEGATIVE_NOTIONAL")
    if isinstance(days_held, bool) or not isinstance(days_held, int):
        raise CostIntegrityStop(f"BORROW_DAYS_NOT_INT:{days_held!r}")
    if days_held < 0:
        raise CostIntegrityStop("BORROW_NEGATIVE_DAYS")
    return n * (schedule.borrow_bps_per_year / 10000.0) * (days_held / schedule.borrow_day_count)
