"""GAP-NATIVE-001 transition parity report (review §3, ADR 0041).

Compares the box-native and external (laptop) gappers files day by day during
the dual-source transition window, so the source switch's effect on the
SCAN-001/GAPPER-001 candidate population is measured, not assumed. Read-only.

Run inside the backend container (defaults match the container layout):

    python3 scripts/compare_gappers_sources.py [--days 14]

Per overlapping day: native/external counts, symbol overlap (of the external
list — "what would we have missed"), top-10 rank overlap, mean |gap_pct| and
premarket-volume deltas on overlapping symbols, and which of the day's gate-
record candidates each source contained. Interpretation rule (comments.md):
consistently low overlap ⇒ the sources are different candidate populations and
the native source starts a NEW evidence tranche — no pooled GAPPER verdict.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
from typing import Any

_DATE_RE = re.compile(r"premarket_gappers_(\d{4}-\d{2}-\d{2})\.json$")


def _dates(directory: str) -> set[str]:
    out = set()
    for p in glob.glob(os.path.join(directory, "premarket_gappers_*.json")):
        m = _DATE_RE.search(p.replace("\\", "/"))
        if m:
            out.add(m.group(1))
    return out


def _load(directory: str, date: str) -> list[dict[str, Any]]:
    path = os.path.join(directory, f"premarket_gappers_{date}.json")
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh).get("gappers") or []
    except (OSError, json.JSONDecodeError, ValueError):
        return []


def _gate_candidates(evidence_dir: str, date: str) -> tuple[list[str], str | None]:
    path = os.path.join(evidence_dir, f"premarket_scan_{date}.json")
    try:
        with open(path, encoding="utf-8") as fh:
            rec = json.load(fh)
        return [c.get("symbol") for c in rec.get("candidates") or []], rec.get("gappers_source")
    except (OSError, json.JSONDecodeError, ValueError):
        return [], None


def compare_day(
    native: list[dict[str, Any]], external: list[dict[str, Any]]
) -> dict[str, Any]:
    n_syms = {str(g.get("symbol") or "").upper() for g in native if g.get("symbol")}
    e_syms = {str(g.get("symbol") or "").upper() for g in external if g.get("symbol")}
    overlap = n_syms & e_syms
    n_by = {str(g["symbol"]).upper(): g for g in native if g.get("symbol")}
    e_by = {str(g["symbol"]).upper(): g for g in external if g.get("symbol")}
    gap_deltas, vol_deltas = [], []
    for s in overlap:
        try:
            gap_deltas.append(abs(float(n_by[s]["gap_pct"]) - float(e_by[s]["gap_pct"])))
            vol_deltas.append(
                abs(float(n_by[s]["premarket_volume"]) - float(e_by[s]["premarket_volume"]))
            )
        except (KeyError, TypeError, ValueError):
            continue
    top_n = {s for s, g in n_by.items() if (g.get("rank") or 99) <= 10}
    top_e = {s for s, g in e_by.items() if (g.get("rank") or 99) <= 10}
    return {
        "native_count": len(n_syms),
        "external_count": len(e_syms),
        "overlap_count": len(overlap),
        "overlap_pct_of_external": round(100 * len(overlap) / len(e_syms), 1) if e_syms else None,
        "top10_rank_overlap": len(top_n & top_e),
        "mean_gap_pct_delta": round(sum(gap_deltas) / len(gap_deltas), 2) if gap_deltas else None,
        "mean_pm_volume_delta": round(sum(vol_deltas) / len(vol_deltas)) if vol_deltas else None,
        "native_only": sorted(n_syms - e_syms),
        "external_only": sorted(e_syms - n_syms),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--native-dir", default="data/premarket_gappers_native")
    ap.add_argument("--external-dir", default="/app/premarket_gappers")
    ap.add_argument("--evidence-dir", default="data/premarket_gate_evidence")
    ap.add_argument("--days", type=int, default=14, help="most recent N shared dates")
    args = ap.parse_args()

    shared = sorted(_dates(args.native_dir) & _dates(args.external_dir), reverse=True)
    if not shared:
        print(json.dumps({"note": "no dates with BOTH native and external files yet"}))
        return 0

    days, overlaps = [], []
    for date in shared[: args.days]:
        native, external = _load(args.native_dir, date), _load(args.external_dir, date)
        row = {"date": date, **compare_day(native, external)}
        candidates, source = _gate_candidates(args.evidence_dir, date)
        n_syms = {str(g.get("symbol") or "").upper() for g in native}
        e_syms = {str(g.get("symbol") or "").upper() for g in external}
        row["gate"] = {
            "gappers_source": source,
            "candidates": candidates,
            "candidates_in_native": [c for c in candidates if c and c.upper() in n_syms],
            "candidates_in_external": [c for c in candidates if c and c.upper() in e_syms],
        }
        days.append(row)
        if row["overlap_pct_of_external"] is not None:
            overlaps.append(row["overlap_pct_of_external"])

    summary = {
        "days_compared": len(days),
        "mean_overlap_pct_of_external": round(sum(overlaps) / len(overlaps), 1)
        if overlaps
        else None,
        "interpretation": (
            "consistently low overlap ⇒ treat native and external as DIFFERENT candidate "
            "sources: no pooled GAPPER/SCAN verdict; the native source starts a new evidence "
            "tranche (ADR 0041 / comments.md §2)"
        ),
    }
    print(json.dumps({"summary": summary, "days": days}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
