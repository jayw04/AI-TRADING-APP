"""SCAN-001 premarket-data gate — increment (D): the forward replication verdict.

Reads the back-filled daily evidence records and tests the gate's frozen hypothesis (plan §3):
*the candidate-set mean expansion `E` beats the eligible-field baseline on real premarket data*,
via the same seeded circular-block bootstrap used in v0.2–v0.5. Pure read-only analysis — no
order path, no LLM.

Verdict (frozen §3): **TRANSFERS** (edge CI-separated > 0 → recommend L4) · **DOES-NOT-TRANSFER**
(CI includes/below 0 → the engine is a liquid-universe tool; document the boundary) ·
**INSUFFICIENT** (< the minimum forward window, or too few filled days → keep accruing). Until
the window clears the verdict is INSUFFICIENT and the live Candidate Report stays advisory
(ADR 0014 — partial forward data is not edge evidence).
"""

from __future__ import annotations

import glob
import json
import os
from typing import Any

from app.factor_data import evidence as ev

# Forward floor (gate plan §3): ~2 months of filled scan days before a pass/fail is allowed.
MIN_FORWARD_DAYS = 40


def gate_verdict(
    records: list[dict[str, Any]], *, min_days: int = MIN_FORWARD_DAYS, bootstrap: int = 2000
) -> dict[str, Any]:
    """Pure: classify the forward replication from back-filled records. Uses each filled record's
    candidate-vs-field ``edge_E`` as the daily series."""
    edges = [
        r["outcomes"]["edge_E"]
        for r in records
        if r.get("outcome_status") == "filled" and r.get("outcomes")
    ]
    filled_days = len(edges)
    if filled_days < min_days:
        return {
            "verdict": "INSUFFICIENT",
            "filled_days": filled_days, "min_days": min_days,
            "note": f"{filled_days}/{min_days} filled forward days — keep accruing; "
                    "Candidate Report stays advisory (ADR 0014).",
        }
    ci = ev.block_bootstrap_ci(edges, ev._mean, n_resamples=bootstrap)
    if ci.ci_low > 0:
        verdict = "TRANSFERS"
        note = "edge CI-separated > 0 on real premarket data → recommend L4 (owner-gated)."
    else:
        verdict = "DOES-NOT-TRANSFER"
        note = ("edge CI includes/below 0 → the validated edge does not transfer to the gappers "
                "universe; the engine remains a liquid-universe tool (a citable boundary).")
    return {
        "verdict": verdict, "filled_days": filled_days, "min_days": min_days,
        "edge_E": {"point": round(ci.point, 4), "ci_low": round(ci.ci_low, 4),
                   "ci_high": round(ci.ci_high, 4), "p_value": round(ci.p_value, 4)},
        "note": note,
    }


def load_records(directory: str) -> list[dict[str, Any]]:
    """Load all ``premarket_scan_*.json`` records from ``directory`` (sorted by date); empty on a
    missing directory (fail-soft)."""
    records: list[dict[str, Any]] = []
    for path in sorted(glob.glob(os.path.join(directory, "premarket_scan_*.json"))):
        try:
            with open(path, encoding="utf-8") as fh:
                records.append(json.load(fh))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
    return records


def run_gate_verdict(
    directory: str, *, min_days: int = MIN_FORWARD_DAYS, bootstrap: int = 2000
) -> dict[str, Any]:
    """Load the accrued records and return the gate verdict (the increment-D entry point)."""
    return gate_verdict(load_records(directory), min_days=min_days, bootstrap=bootstrap)
