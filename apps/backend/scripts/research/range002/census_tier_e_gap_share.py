"""Disclosure helper: for every tier-E (complete-empty, same-provider) minute of a census, the share
of that day's symbols that ALSO lack a bar at that minute (read-only; presence only, no prices).

    python -I census_tier_e_gap_share.py --store STORE.duckdb --manifest M.json \\
        --classification C.json [--warn-share 0.05]

It exists because the 10% common-gap detector is a warning heuristic: this lists how many tier-E
minutes sit below it but above a lower share, so a reader can see them. Counts only.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import duckdb

TIER_E = "ACCOUNTED_FOR_EMPTY_SAME_PROVIDER"


def shares(store: Path, manifest: dict[str, Any], cls: dict[str, Any]) -> list[float]:
    by = {s["id"]: s for s in manifest["samples"]}
    con = duckdb.connect(str(store), read_only=True)
    try:
        have = {
            (d, int(m)): int(n)
            for d, m, n in con.execute(
                """SELECT strftime(l, '%Y-%m-%d'), date_part('hour', l) * 60 + date_part('minute', l),
                          count(DISTINCT symbol)
                   FROM (SELECT symbol, (ts AT TIME ZONE 'UTC') AT TIME ZONE 'America/New_York' AS l
                         FROM minute_bars)
                   WHERE date_part('hour', l) * 60 + date_part('minute', l) BETWEEN 570 AND 599
                   GROUP BY 1, 2"""
            ).fetchall()
        }
        nsym = dict(
            con.execute(
                """SELECT strftime(l, '%Y-%m-%d'), count(DISTINCT symbol)
                   FROM (SELECT symbol, (ts AT TIME ZONE 'UTC') AT TIME ZONE 'America/New_York' AS l
                         FROM minute_bars)
                   WHERE date_part('hour', l) * 60 + date_part('minute', l) BETWEEN 570 AND 959
                   GROUP BY 1"""
            ).fetchall()
        )
    finally:
        con.close()
    out: list[float] = []
    for item in cls["per_sample"]:
        day = by[item["id"]]["day"]
        for hhmm, klass in item["classes"].items():
            if klass != TIER_E:
                continue
            m = int(hhmm[:2]) * 60 + int(hhmm[3:5])
            out.append(round(1 - have.get((day, m), 0) / nsym[day], 4))
    return sorted(out)


def summary(values: list[float], warn_share: float) -> dict[str, Any]:
    n = len(values)

    def q(p: float) -> float | None:
        return values[min(n - 1, int(n * p))] if n else None

    return {
        "tier_e_minutes": n,
        "share_of_symbols_lacking_a_bar_at_that_minute": {
            "median": q(0.5),
            "p90": q(0.9),
            "p99": q(0.99),
            "max": values[-1] if n else None,
        },
        "warn_share": warn_share,
        "minutes_at_or_above_warn_share": sum(1 for v in values if v >= warn_share),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", required=True, type=Path)
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--classification", required=True, type=Path)
    ap.add_argument("--warn-share", type=float, default=0.05)
    a = ap.parse_args()
    vals = shares(
        a.store,
        json.loads(a.manifest.read_text(encoding="utf-8")),
        json.loads(a.classification.read_text(encoding="utf-8")),
    )
    print(json.dumps(summary(vals, a.warn_share), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
