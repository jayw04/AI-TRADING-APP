"""SCAN-001 premarket-data gate — increment (C): the forward-evidence accumulator.

Persists each day's premarket Candidate Report to a dated JSON record, so the gate's forward
replication (gate plan §1) can **accrue from today** — the chosen Option 3: *persist now,
back-fill outcomes later*. This adds **no** new data dependency: it records the premarket
candidate set (and the §0b funnel) exactly as selected at ~09:25.

The realized-intraday outcome join (``E`` / ``CM`` per candidate vs. the eligible-field
baseline) is the **back-fill**, and it needs a realized-outcome data source for the gappers
universe — that is Option 2 (a new feed → ADR). Until that lands, every record carries
``outcome_status = "pending"`` and ``outcomes = None``; the verdict harness (increment D) reads
these records and runs only once enough have accrued **and** been back-filled.

Boundary: read-only research evidence (SCAN-001 §0a). Writes a plain JSON file — no DB, no
order path, no LLM. Fail-soft on the scan; a write error is raised to the caller (the daily job
logs it) rather than silently swallowed, so a broken accumulator is visible.
"""

from __future__ import annotations

import json
import os
from datetime import date
from typing import Any

from app.services.premarket_scan import run_premarket_scan

# Schema tag on each record so the verdict harness (D) can evolve the format safely.
RECORD_SCHEMA = "scan_001_premarket_gate/v1"
# Default sink; the daily job passes a durable runtime path (wiring = the deferred activation).
DEFAULT_EVIDENCE_DIR = "premarket_gate_evidence"


def evidence_record(report: dict[str, Any], *, asof: date) -> dict[str, Any]:
    """Wrap a ``run_premarket_scan`` report into a durable, back-fillable evidence record.

    ``asof`` is the scan (trading) day — it is the record's identity and filename key, so the
    record exists even when the gappers payload is empty/stale (``report['date']`` may be None).
    Outcomes are left ``pending`` for the Option-2 back-fill."""
    return {
        "schema": RECORD_SCHEMA,
        "asof": asof.isoformat(),
        "source_date": report.get("date"),
        "scanned_at": report.get("scanned_at"),
        "stale": bool(report.get("stale", True)),
        "funnel": {
            "gappers_in": report.get("gappers_in", 0),
            "store_covered": report.get("store_covered", 0),
            "eligible_panel": report.get("eligible_panel", 0),
            "candidate_count": report.get("candidate_count", 0),
        },
        # premarket features at selection time — the immutable left side of the forward pair
        "candidates": report.get("candidates", []),
        # back-fill targets (Option 2): realized E/CM per candidate + eligible-field baseline
        "outcome_status": "pending",
        "outcomes": None,
    }


def record_path(directory: str, asof: date) -> str:
    """The dated record path: ``{directory}/premarket_scan_{YYYY-MM-DD}.json`` (one per day)."""
    return os.path.join(directory, f"premarket_scan_{asof.isoformat()}.json")


def persist_record(record: dict[str, Any], directory: str) -> str:
    """Write ``record`` to its dated path (creating ``directory``); idempotent per day — a
    re-run of the same scan day overwrites. Returns the path written."""
    os.makedirs(directory, exist_ok=True)
    asof = date.fromisoformat(record["asof"])
    path = record_path(directory, asof)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
    return path


def record_premarket_scan(
    store: Any, *, asof: date, directory: str = DEFAULT_EVIDENCE_DIR, top_n: int = 15
) -> dict[str, Any]:
    """Run the live premarket scan for ``asof`` and persist its evidence record. Returns the
    record (with the written path under ``_path``). The daily ~09:25 job calls this; wiring that
    job + its runtime ``directory`` is the deferred activation step (needs a backend rebuild)."""
    report = run_premarket_scan(store, asof=asof, top_n=top_n)
    record = evidence_record(report, asof=asof)
    record["_path"] = persist_record(record, directory)
    return record
