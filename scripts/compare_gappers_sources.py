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
import json

# Single source of truth: the comparison logic lives in the service so the daily
# accrual job (app/jobs/gapper_parity.py) and this ad-hoc report can never drift
# into measuring parity two different ways.
from app.services.gapper_source_parity import (
    compare_day,
    dates_present as _dates,
    gate_candidates as _gate_candidates,
    load_gappers as _load,
)


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
