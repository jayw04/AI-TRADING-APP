"""MR-002 validation/OOS evaluator — frozen cost model (Increment 2).

Pure, synthetic-only. Implements the frozen base + stress + severe cost schedules and the two cost
primitives. Costs are computed from EXECUTED (filled) notional, never intended-order notional. Borrow
accrues only while a short position is economically held, using the frozen 360-day convention and the
holding period derived from explicit entry/exit session timestamps.

Frozen schedules (bps per side; borrow bps per year; 360-day borrow convention):
  * BASE    — 10 bps/side, 50 bps/yr borrow    (the governing base cost)
  * STRESS  — 20 bps/side, 300 bps/yr borrow   (mandatory cost-stress gate)
  * SEVERE  — 30 bps/side, 1000 bps/yr borrow  (severe diagnostic; reported, NEVER gated)

INTEGRITY_STOP codes: COST_NONFINITE, COST_NEGATIVE_NOTIONAL, BORROW_NEGATIVE_DAYS,
BORROW_LONG_SIDE (borrow requested on a non-short leg).

Increment 2 scope note: sessions serve as the day unit in synthetic fixtures (days_held = exit
session ordinal − entry session ordinal). The borrow principal is the executed short-entry notional,
held constant over the borrow period (frozen synthetic convention). Real calendar-day accrual binds
to real entry/exit timestamps when the sealed-data path is built (NOT this increment).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


class CostIntegrityStop(Exception):
    """Degenerate / out-of-domain cost input (frozen INTEGRITY_STOP with a specific code)."""


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


def _finite(x: float, code: str) -> float:
    xf = float(x)
    if not math.isfinite(xf):
        raise CostIntegrityStop(code)
    return xf


def commission_slippage_cost(executed_notional: float, schedule: CostSchedule) -> float:
    """Commission + slippage for ONE executed side (a fill). Keyed to executed notional; a round trip
    incurs this once per leg (entry fill and exit fill)."""
    n = _finite(executed_notional, "COST_NONFINITE")
    if n < 0.0:
        raise CostIntegrityStop("COST_NEGATIVE_NOTIONAL")
    return n * schedule.commission_slippage_bps_per_side / 10000.0


def borrow_cost(short_entry_notional: float, days_held: int, schedule: CostSchedule, *,
                is_short: bool) -> float:
    """Short-borrow financing over the holding period. Zero for a long leg. Principal = executed
    short-entry notional; accrual = principal · (borrow_bps/1e4) · (days_held / day_count)."""
    if not is_short:
        if float(short_entry_notional) != 0.0 or days_held != 0:
            # a borrow charge requested against a non-short leg is a modelling error
            raise CostIntegrityStop("BORROW_LONG_SIDE")
        return 0.0
    n = _finite(short_entry_notional, "COST_NONFINITE")
    if n < 0.0:
        raise CostIntegrityStop("COST_NEGATIVE_NOTIONAL")
    if int(days_held) < 0:
        raise CostIntegrityStop("BORROW_NEGATIVE_DAYS")
    return n * (schedule.borrow_bps_per_year / 10000.0) * (int(days_held) / schedule.borrow_day_count)
