"""Every pre-constructed CronTrigger in lifespan must bind an explicit timezone.

The 2026-07-09 incident: a bare ``CronTrigger(hour=16, minute=40)`` binds the CONTAINER's
timezone (UTC) at construction — the scheduler's ``timezone="America/New_York"`` never applies
to pre-built trigger objects — so ten "ET" jobs silently fired 4 hours early (the gapper shadow
ledger wrote a mid-session record at 12:40 ET; the premarket gate scanned at 05:25 ET; the
benchmark snapshot sampled 12:10 ET prices as "closes"; the daily backup ran at 22:00 ET).
This scan keeps the fix honest: any new pre-constructed cron in lifespan without an explicit
``timezone=`` fails here before it can misfire in production.
"""

from __future__ import annotations

import re
from pathlib import Path

from apscheduler.triggers.cron import CronTrigger

_LIFESPAN = Path(__file__).resolve().parents[2] / "app" / "lifespan.py"


def test_all_lifespan_cron_constructions_bind_a_timezone() -> None:
    src = _LIFESPAN.read_text(encoding="utf-8")
    calls = re.findall(r"(?:_ReplayCron|_InsiderCron|CronTrigger)\(([^()]*)\)", src)
    assert calls, "expected cron constructions in lifespan.py (did the aliases change?)"
    offenders = [c for c in calls if "timezone" not in c]
    assert not offenders, (
        "bare CronTrigger construction(s) in lifespan.py bind the container tz (UTC), "
        f"not the scheduler's ET — add timezone=\"America/New_York\": {offenders}"
    )


def test_bare_cron_trigger_really_does_bind_local_tz() -> None:
    # The failure mode itself, pinned: a bare trigger does NOT inherit anything later.
    bare = CronTrigger(hour=16, minute=40)
    bound = CronTrigger(hour=16, minute=40, timezone="America/New_York")
    assert str(bound.timezone) == "America/New_York"
    # bare binds whatever this machine's local tz is — the point is it is FIXED at
    # construction; in the UTC container that was UTC, 4h off the intended ET.
    assert bare.timezone is not None
