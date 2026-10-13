"""Build the FROZEN missing-minute census manifest from stored bars (read-only, return-blind).

    python -I build_census_manifest.py --store STORE.duckdb --universe-report REPORT.json \\
        --mapping MAPPING.json --out MANIFEST.json

For every monthly-member day whose stored opening range (09:30-09:59 ET) lacks one or more
minute bars it emits sample intervals (clusters of missing minutes separated by at most
``CLUSTER_GAP_MIN`` minutes), each with its query window (one minute of boundary on each side),
the dated request symbol and ``asof`` from the verified mapping, the missing minutes, the
CONTROL minutes (stored bars inside the window: a trades query that is correctly constructed
must return eligible trades for them) and the SUSPECTED-PROVIDER-GAP minutes (at least
``OUTAGE_SHARE`` of the symbols with data that day lack a bar at that minute).

Only bar presence is read; no price or volume value is selected. The selection order is a fixed
hash order (seed below) so a capped census checkpoints deterministically.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from datetime import time
from pathlib import Path
from typing import Any

import duckdb

SEED = "RANGE002-CENSUS-v1"
OR_FIRST, OR_LAST = 570, 599  # 09:30 .. 09:59 ET
CLUSTER_GAP_MIN = 5
OUTAGE_SHARE = 0.10


def _hms(minute_of_day: int) -> str:
    return time(minute_of_day // 60, minute_of_day % 60).isoformat()


def _request_symbol(entry: dict[str, Any], day: str) -> tuple[str, str]:
    seg = None
    for s in entry["schedule"]:
        if s["from"] <= day:
            seg = s
    if seg is None:  # day before every segment: refuse rather than guess
        raise ValueError(f"{entry['vendor_ticker']}: no mapping segment covers {day}")
    asof = "-" if entry.get("asof_policy") == "-" else seg["from"]
    return seg["request_symbol"], asof


def build(store: Path, report: dict[str, Any], mapping: Any) -> dict[str, Any]:
    entries = {
        e["vendor_ticker"]: e
        for e in (mapping["entries"] if isinstance(mapping, dict) else mapping)
    }
    members: dict[str, set[str]] = {}
    for m in report["months"]:
        ranked = m["members_ranked"]
        members[m["month_start"][:7]] = {
            (x if isinstance(x, str) else x.get("ticker") or x.get("vendor_ticker")) for x in ranked
        }
    con = duckdb.connect(str(store), read_only=True)
    rows = con.execute(
        """
        SELECT symbol,
               strftime(local_ts, '%Y-%m-%d') AS day,
               date_part('hour', local_ts) * 60 + date_part('minute', local_ts) AS mod
        FROM (SELECT symbol, (ts AT TIME ZONE 'UTC') AT TIME ZONE 'America/New_York' AS local_ts
              FROM minute_bars)
        WHERE date_part('hour', local_ts) * 60 + date_part('minute', local_ts) BETWEEN ? AND ?
        """,
        [OR_FIRST - 1, 959],
    ).fetchall()
    con.close()
    present: dict[tuple[str, str], set[int]] = defaultdict(set)
    regular_days: dict[tuple[str, str], bool] = {}
    for sym, day, mod in rows:
        present[(sym, day)].add(int(mod))
        if mod >= OR_FIRST:
            regular_days[(sym, day)] = True
    syms_by_day: dict[str, set[str]] = defaultdict(set)
    for (sym, day), ok in regular_days.items():
        if ok:
            syms_by_day[day].add(sym)
    outage: dict[str, set[int]] = defaultdict(set)
    for day, syms in syms_by_day.items():
        n = len(syms)
        for m in range(OR_FIRST, OR_LAST + 1):
            have = sum(1 for s in syms if m in present[(s, day)])
            if n and (n - have) / n >= OUTAGE_SHARE:
                outage[day].add(m)

    samples: list[dict[str, Any]] = []
    member_days_total = member_days_incomplete = 0
    missing_minutes_total = 0
    for (sym, day), ok in sorted(regular_days.items()):
        if not ok or sym not in members.get(day[:7], set()):
            continue
        member_days_total += 1
        miss = [m for m in range(OR_FIRST, OR_LAST + 1) if m not in present[(sym, day)]]
        if not miss:
            continue
        member_days_incomplete += 1
        missing_minutes_total += len(miss)
        clusters: list[list[int]] = [[miss[0]]]
        for m in miss[1:]:
            if m - clusters[-1][-1] <= CLUSTER_GAP_MIN:
                clusters[-1].append(m)
            else:
                clusters.append([m])
        for cl in clusters:
            lo, hi = cl[0], cl[-1]
            w0, w1 = lo - 1, hi + 1  # window minutes inclusive
            rs, asof = _request_symbol(entries[sym], day)
            missing = [m for m in cl if m not in present[(sym, day)]]
            control = [m for m in range(w0, w1 + 1) if m in present[(sym, day)]]
            samples.append(
                {
                    "stratum": "census_missing_or_minutes",
                    "symbol": sym,
                    "request_symbol": rs,
                    "asof": asof,
                    "endpoint": "trades",
                    "day": day,
                    "interval_start_et": _hms(lo),
                    "interval_end_et": _hms(hi + 1),
                    "window_start_et": _hms(w0),
                    "window_end_et": _hms(w1 + 1),
                    "missing_minutes": [_hms(m) for m in missing],
                    "control_minutes": [_hms(m) for m in control],
                    "suspected_provider_gap_minutes": [
                        _hms(m) for m in missing if m in outage[day]
                    ],
                }
            )
    samples.sort(
        key=lambda s: hashlib.sha256(
            f"{SEED}|{s['symbol']}|{s['day']}|{s['interval_start_et']}".encode()
        ).hexdigest()
    )
    for i, s in enumerate(samples, 1):
        s["id"] = f"C{i:04d}"
    return {
        "schema": "range002.trades_probe_manifest.v1",
        "kind": "range002.missing_minute_census_manifest.v1",
        "seed": SEED,
        "selection": "member-days with missing OR minutes; hash order; bar presence only",
        "parameters": {
            "cluster_gap_min": CLUSTER_GAP_MIN,
            "outage_share": OUTAGE_SHARE,
            "or_window_et": [_hms(OR_FIRST), _hms(OR_LAST)],
        },
        "summary": {
            "member_days": member_days_total,
            "incomplete_member_days": member_days_incomplete,
            "missing_or_minutes": missing_minutes_total,
            "samples": len(samples),
            "suspected_provider_gap_minutes": sum(
                len(s["suspected_provider_gap_minutes"]) for s in samples
            ),
        },
        "samples": samples,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--store", required=True, type=Path)
    ap.add_argument("--universe-report", required=True, type=Path)
    ap.add_argument("--mapping", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    if a.out.exists():
        raise SystemExit(f"{a.out} exists; never overwritten")
    doc = build(
        a.store,
        json.loads(a.universe_report.read_text(encoding="utf-8")),
        json.loads(a.mapping.read_text(encoding="utf-8")),
    )
    text = json.dumps(doc, indent=1, sort_keys=True) + "\n"
    a.out.write_text(text, encoding="utf-8")
    print(f"wrote {a.out} sha256={hashlib.sha256(text.encode()).hexdigest()} {doc['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
