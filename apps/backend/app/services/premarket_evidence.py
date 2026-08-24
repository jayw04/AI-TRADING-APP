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
import uuid
from datetime import UTC, date, datetime
from typing import Any

from app.research.gapper_stage0.provenance import make_provenance
from app.services.premarket_gappers import NO_SOURCE_ARTIFACT, NO_SOURCE_SHA256
from app.services.premarket_scan import run_premarket_scan

# Schema tag on each record so the verdict harness (D) can evolve the format safely.
#
# /v2 (2026-08-23) adds §5.5 write-time provenance. The bump exists because /v1 carries an
# ambiguity that cannot be repaired in place, only versioned past — see the owner disposition in
# ``docs/design/Gapper/GAPPER_PremarketGateProvenance_Quarantine_Review_v1.0.md`` §5:
#
#   26 of the 51 /v1 records on the box carry a ``provenance`` STRING ("live" / "replayed") that
#   a one-off repair script inferred and wrote RETROACTIVELY in July 2026. The other 25 carry no
#   such field. Both shapes are tagged /v1. So in /v1 the ABSENCE of ``provenance`` marks the
#   NEWEST records, not the least known -- the inverse of the natural reading.
#
# ⛔ /v1 records are never repaired, stripped, or back-stamped. The ruling is: leave them
# byte-unchanged and move forward under /v2.
RECORD_SCHEMA = "scan_001_premarket_gate/v2"
LEGACY_RECORD_SCHEMA = "scan_001_premarket_gate/v1"
#: Every schema this writer has ever emitted. A reader that does not recognise a record's schema
#: must refuse to interpret it rather than guess a shape.
KNOWN_RECORD_SCHEMAS = (LEGACY_RECORD_SCHEMA, RECORD_SCHEMA)

#: Producing-code identity for the §5.5 stamp. Bump when the record shape changes.
WRITER_VERSION = "premarket_evidence/2.0.0"
#: §5.5 write class for this writer: records are produced forward by the daily ~09:25 job from a
#: contemporaneous source artifact. Never "reconstruction", "backfill", or "repair".
WRITE_CLASS = "collection"

#: Stamped into every /v2 record so no consumer can mistake the legacy /v1 ``provenance`` string
#: for the conformant /v2 structure. Required by the 2026-08-23 owner disposition, term 8.
PROVENANCE_SEMANTICS = (
    "v2: 'provenance' is a §5.5 write-time stamp (dict: created_at, source_artifact, "
    "source_sha256, code_version, run_id, write_class), written once at record creation and "
    "never repaired retroactively. It is NOT comparable to the legacy v1 'provenance' string "
    "('live'/'replayed'), which was inferred and written retroactively by a since-quarantined "
    "repair script. In v1, presence or absence of 'provenance' is not an authenticity, quality, "
    "freshness, admission, or trust indicator."
)
# Default sink; the daily job passes a durable runtime path (wiring = the deferred activation).
DEFAULT_EVIDENCE_DIR = "premarket_gate_evidence"


def _provenance_for(report: dict[str, Any], *, created_at: str, run_id: str) -> dict[str, str]:
    """The §5.5 write-time stamp for a record built from ``report``.

    The source artifact is whatever the gappers reader actually read, hashed at read time. On a
    no-scan/unreadable day the reader supplies explicit sentinels — a stamp that says "there was
    no source" is honest; a stamp carrying a plausible-looking digest of nothing is not."""
    return make_provenance(
        created_at=created_at,
        source_artifact=report.get("source_path") or NO_SOURCE_ARTIFACT,
        source_sha256=report.get("source_sha256") or NO_SOURCE_SHA256,
        run_id=run_id,
        write_class=WRITE_CLASS,
        code_version=WRITER_VERSION,
    )


def evidence_record(
    report: dict[str, Any],
    *,
    asof: date,
    created_at: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Wrap a ``run_premarket_scan`` report into a durable, back-fillable evidence record.

    ``asof`` is the scan (trading) day — it is the record's identity and filename key, so the
    record exists even when the gappers payload is empty/stale (``report['date']`` may be None).
    Outcomes are left ``pending`` for the Option-2 back-fill.

    ``created_at`` / ``run_id`` are injectable so tests are deterministic; in production they are
    this write's own clock and invocation id. The stamp is applied HERE, at creation, and by
    nothing else — that is the whole point of §5.5."""
    created_at = created_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    run_id = run_id or uuid.uuid4().hex
    return {
        "schema": RECORD_SCHEMA,
        "provenance": _provenance_for(report, created_at=created_at, run_id=run_id),
        "provenance_semantics": PROVENANCE_SEMANTICS,
        "asof": asof.isoformat(),
        "source_date": report.get("date"),
        "scanned_at": report.get("scanned_at"),
        "stale": bool(report.get("stale", True)),
        "funnel": {
            "gappers_in": report.get("gappers_in", 0),
            "store_covered": report.get("store_covered", 0),
            "eligible_panel": report.get("eligible_panel", 0),
            "eligible_count": report.get("eligible_count", 0),
            "candidate_count": report.get("candidate_count", 0),
        },
        # premarket features at selection time — the immutable left side of the forward pair
        "candidates": report.get("candidates", []),
        # the eligible baseline field (symbol + ATR) — needed for the candidate-vs-field edge
        "eligible": report.get("eligible", []),
        # back-fill targets (Option 2, ADR 0024): realized E/CM per candidate + eligible baseline
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
