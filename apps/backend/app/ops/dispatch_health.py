"""Strategy-dispatch liveness health (P11 ops).

Detects an **active, bar-driven strategy that is not being dispatched** (``on_bar``) during
regular trading hours — the silent-inertness failure mode where a "live PAPER" intraday
strategy does nothing for weeks because the engine isn't actually up through the session
(e.g. the Range Trader: 0 trades while the stack was down outside market hours). This is a
**read-only** health signal: it never touches the order path.

The check is deliberately conservative (large staleness multiple + a startup grace) so a
single missed tick or a fresh process never false-alarms — it fires only on a *sustained*
absence of dispatch during RTH, which is the real "the strategy isn't running" condition.

Pure functions over primitives (timestamps, a session bool) so they're trivially testable;
the engine adapter that snapshots running strategies lives in ``app/strategies/engine.py``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

EVENT_SCHEDULE_SENTINEL = "event"

# A bar-driven strategy is "stale" once it has gone this many expected cadences without a
# dispatch (floored at MIN_STALE_AFTER_S) — three missed intervals, not one.
STALE_CADENCE_MULTIPLE = 3
MIN_STALE_AFTER_S = 15 * 60        # never flag faster than 15 min, however short the cadence
STARTUP_GRACE_S = 5 * 60           # within this window of engine start, report `unknown`

# Health states (mirrors app/ops/state.py vocabulary).
OK, STALE, UNKNOWN, NA = "ok", "stale", "unknown", "n_a"


@dataclass(frozen=True)
class DispatchHealth:
    """Per-strategy dispatch-liveness verdict."""

    strategy_id: int
    name: str
    schedule: str
    cadence_minutes: float | None      # None => not a liveness-checked (bar-driven) strategy
    last_dispatch_age_s: float | None  # None => never dispatched (this process)
    health: str                        # ok | stale | unknown | n_a
    reason: str


@dataclass(frozen=True)
class DispatchSnapshot:
    """What the engine reports per running strategy (one snapshot row)."""

    strategy_id: int
    name: str
    schedule: str
    timeframe: str
    last_dispatch_at: float | None     # epoch seconds of the last successful on_bar, or None


def parse_timeframe_minutes(timeframe: str) -> float | None:
    """``"5Min" -> 5``, ``"1Min" -> 1``, ``"1Hour" -> 60``, ``"1Day" -> 1440``. ``None`` if
    unparseable (so an unknown timeframe degrades to "not liveness-checked", never a crash)."""
    if not timeframe:
        return None
    m = re.fullmatch(r"\s*(\d+)\s*(min|m|hour|h|day|d)\s*", timeframe.strip(), re.IGNORECASE)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    if unit in ("min", "m"):
        return float(n)
    if unit in ("hour", "h"):
        return float(n * 60)
    return float(n * 1440)  # day


def dispatch_cadence_minutes(schedule: str, timeframe: str) -> float | None:
    """Expected dispatch interval in minutes for a **bar-driven** strategy, else ``None``.

    - ``"event"`` → derived from the timeframe (the WS/bar cadence).
    - cron with an *intraday minute field* (``"*"`` or ``"*/N"``) → ``N`` (``1`` for ``"*"``).
    - a fixed daily/weekly cron (fixed minute **and** hour, e.g. ``"0 14 * * mon"``) → ``None``
      — those dispatch on their schedule, so "no dispatch since Monday" is *normal*, not a fault.
    - hourly (fixed minute, wildcard hour) → ``60``.

    Returns ``None`` (not liveness-checked) for anything we can't confidently treat as a
    per-bar cadence — fail toward *not* alarming on shapes we don't understand.
    """
    sched = (schedule or "").strip()
    if sched == EVENT_SCHEDULE_SENTINEL:
        return parse_timeframe_minutes(timeframe)
    fields = sched.split()
    if len(fields) != 5:
        return None
    minute, hour = fields[0], fields[1]
    if minute == "*":
        return 1.0
    if minute.startswith("*/"):
        try:
            step = int(minute[2:])
        except ValueError:
            return None
        return float(step) if step > 0 else None
    # minute is a fixed value (or list/range): intraday only if it repeats hourly.
    if hour == "*":
        return 60.0
    return None  # fixed minute + fixed hour => daily/weekly schedule, not per-bar


def _stale_after_s(cadence_minutes: float) -> float:
    return max(STALE_CADENCE_MULTIPLE * cadence_minutes * 60.0, MIN_STALE_AFTER_S)


def evaluate_one(
    snap: DispatchSnapshot, *, now: float, is_regular_session: bool, engine_uptime_s: float
) -> DispatchHealth:
    """Verdict for a single strategy. See module docstring for the state machine."""
    cadence = dispatch_cadence_minutes(snap.schedule, snap.timeframe)
    age = None if snap.last_dispatch_at is None else max(0.0, now - snap.last_dispatch_at)

    def out(health: str, reason: str) -> DispatchHealth:
        return DispatchHealth(
            strategy_id=snap.strategy_id, name=snap.name, schedule=snap.schedule,
            cadence_minutes=cadence, last_dispatch_age_s=age, health=health, reason=reason,
        )

    if cadence is None:
        return out(NA, "not a bar-driven strategy (scheduled dispatch); liveness not checked")
    if not is_regular_session:
        return out(NA, "market not in a regular session; dispatch not expected")
    if engine_uptime_s < STARTUP_GRACE_S:
        return out(UNKNOWN, "within engine startup grace; not yet evaluable")

    stale_after = _stale_after_s(cadence)
    if snap.last_dispatch_at is None:
        return out(STALE, f"never dispatched this session (expected every ~{cadence:g}m)")
    assert age is not None
    if age > stale_after:
        return out(
            STALE,
            f"no on_bar dispatch for {age / 60:.0f}m (cadence ~{cadence:g}m, "
            f"stale after {stale_after / 60:.0f}m) — is the engine up + fed bars?",
        )
    return out(OK, f"dispatched {age / 60:.0f}m ago (cadence ~{cadence:g}m)")


def evaluate_dispatch_health(
    snapshots: Iterable[DispatchSnapshot],
    *,
    now: float,
    is_regular_session: bool,
    engine_uptime_s: float,
) -> list[DispatchHealth]:
    """Evaluate every running strategy's dispatch liveness."""
    return [
        evaluate_one(
            s, now=now, is_regular_session=is_regular_session, engine_uptime_s=engine_uptime_s
        )
        for s in snapshots
    ]


def stale_dispatch(results: Iterable[DispatchHealth]) -> list[DispatchHealth]:
    """The subset that is actively stale (what an alert/monitor should surface)."""
    return [r for r in results if r.health == STALE]
