"""One-time: convert UTC-authored strategy schedules to Eastern-time hours.

Before ``engine.py`` pinned ``CronTrigger.from_crontab`` to ``America/New_York``, strategy
cron schedules were evaluated in the container's local tz (UTC). The live momentum/factor
books were authored as ``X 14 * * mon`` to fire at 10:00 EDT (== 14:00 UTC). Now that
strategy schedules are ET, ``X 14`` would mean 14:00 ET (2 PM); this rewrites the legacy
UTC hour 14 -> ET hour 10 so the effective time stays 10:00 ET (and no longer drifts to
09:00 ET in winter).

Idempotent: only rewrites 5-field crontabs whose HOUR field is exactly "14" (the legacy
UTC-authored books). Run ``--apply`` to commit; default is a dry run. Off the order path.

Usage (from apps/backend, inside the container):
    python scripts/migrate_strategy_schedules_to_et.py            # dry run
    python scripts/migrate_strategy_schedules_to_et.py --apply
"""

from __future__ import annotations

import argparse
import sqlite3
import sys

LEGACY_UTC_HOUR = "14"   # 14:00 UTC == 10:00 EDT, how the books were authored
ET_HOUR = "10"           # 10:00 ET, the market-clock intent


def _converted(schedule: str) -> str | None:
    """Return the ET-hour schedule if ``schedule`` is a 5-field crontab at UTC hour 14,
    else None (leave untouched — wildcards, other hours, non-5-field are not legacy books)."""
    parts = schedule.split()
    if len(parts) != 5 or parts[1] != LEGACY_UTC_HOUR:
        return None
    parts[1] = ET_HOUR
    return " ".join(parts)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="/app/data/workbench.sqlite")
    ap.add_argument("--apply", action="store_true", help="commit changes (default: dry run)")
    args = ap.parse_args(argv)

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT id, name, schedule FROM strategies ORDER BY id").fetchall()

    changes: list[tuple[int, str, str, str]] = []
    for r in rows:
        new = _converted(r["schedule"] or "")
        if new is not None and new != r["schedule"]:
            changes.append((r["id"], r["name"], r["schedule"], new))

    if not changes:
        print("no legacy UTC-hour-14 schedules found — nothing to migrate.")
        return 0

    print(f"{'APPLYING' if args.apply else 'DRY RUN'} — {len(changes)} schedule(s):")
    for sid, name, old, new in changes:
        print(f"  id={sid:<3} {str(name)[:24]:24s} {old!r} -> {new!r}")

    if args.apply:
        for sid, _name, _old, new in changes:
            con.execute("UPDATE strategies SET schedule = ? WHERE id = ?", (new, sid))
        con.commit()
        print("committed. Restart the backend so strategies re-register at the new ET times.")
    else:
        print("dry run — re-run with --apply to commit.")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
