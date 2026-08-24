"""QUARANTINED 2026-08-23 - DO NOT RESTORE. Retained as evidence, not as a utility.

The write path of this script has been REMOVED. It ran once, with ``--apply``, against the LIVE
SCAN-001 evidence corpus on ``ec2-paper`` between 2026-07-16 and 2026-07-17, stamping 26 of the
51 records with a ``provenance`` string it INFERRED from then-current disk state. That is
retroactive provenance manufacture, which GAPPER Research Design v2.1.1 §5.5 forbids: write
provenance is stamped at write time, or it does not exist.

Read before touching anything here:
  docs/design/Gapper/GAPPER_PremarketGateProvenance_Quarantine_Review_v1.0.md
  tools/quarantine/README.md

Owner disposition 2026-08-23 (review §5, Option B): the 51 legacy ``/v1`` records stay
byte-unchanged - not stripped, not back-stamped - and the writer moved forward to
``scan_001_premarket_gate/v2`` with a genuine §5.5 stamp. No supported path rewrites a ``/v1``
record's provenance, and this file must never become one again.

What remains below is a READ-ONLY inspector. It cannot write. A quarantined tool that can still
execute ``--apply`` is not quarantined.

--- original module docstring, preserved verbatim below this line ---

SCAN-001 gate evidence - one-off provenance repair.

Twenty evidence records (2026-06-08 .. 2026-07-08) were written by an off-repo replay on
2026-07-09 that read the real, contemporaneously-captured ``premarket_gappers_<date>.json``
files from the sibling ``claude-trading-view`` scanner but did not copy their ``scanned_at``
through. They therefore carry ``scanned_at: null`` while the six live records (2026-07-09
onward, written by the ``premarket_gate_scan`` job) carry it.

This script completes the twenty records and, in the same pass, makes the live/replayed
distinction explicit rather than leaving it resting on that accidental null:

* ``scanned_at``  — when the *premarket snapshot* was captured, copied per-date from the
  gappers file (``premarket_gappers.sh`` stamps it at process start). Real and
  contemporaneous for every record, live or replayed. Filling it is pure completion.
* ``recorded_at`` — the record file's last write time (UTC). NOTE: the 16:30 ET outcome
  back-fill rewrites the record, so for live records this is the back-fill time, not the
  09:25 scan time. It is a provenance signal, not the scan clock.
* ``provenance`` — ``"live"`` (produced forward by the daily job) or ``"replayed"``
  (reconstructed by the 2026-07-09 batch).

Why ``provenance`` matters: once ``scanned_at`` is filled, the replayed records become
shape-identical to the live ones (both copy the same ``12:30Z`` stamp off the gappers file),
and file mtime is not a durable discriminator — the box's gappers copies were all restamped
by a bulk ``scp``. This field is the only thing that survives transport.

Classification is derived from the CURRENT on-disk state and is order-dependent, so the
script is idempotent by construction: a record that already has ``provenance`` keeps it; a
record without one is classified by whether ``scanned_at`` is present (the pre-repair ground
truth). It refuses to guess in any other situation.

This script does NOT decide whether replayed days may count toward the gate's
``MIN_FORWARD_DAYS`` window (plan §0a / ADR 0014). That is an owner adjudication. It only
makes the evidence self-describing enough for that call to be made.

Read-only w.r.t. the order path. Dry-run by default; pass --apply to write.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from datetime import UTC, datetime
from typing import Any

_GAPPER_RE = re.compile(r"premarket_gappers_(\d{4}-\d{2}-\d{2})\.json$")

LIVE = "live"
REPLAYED = "replayed"


def gapper_scanned_at(gappers_dir: str, asof: str) -> str | None:
    """The ``scanned_at`` stamp from the gappers file for ``asof``; None if absent/unreadable."""
    path = os.path.join(gappers_dir, f"premarket_gappers_{asof}.json")
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError, ValueError):
        return None
    stamp = payload.get("scanned_at")
    return str(stamp) if stamp else None


def classify(record: dict[str, Any]) -> str:
    """Provenance of ``record`` from its current state (idempotent: an existing marker wins)."""
    existing = record.get("provenance")
    if existing in (LIVE, REPLAYED):
        return existing
    # Pre-repair ground truth: only the live daily job propagated scanned_at.
    return LIVE if record.get("scanned_at") else REPLAYED


def repair_record(path: str, gappers_dir: str) -> dict[str, Any]:
    """Compute the repair for one record. Returns a plan dict; does not write."""
    with open(path, encoding="utf-8") as fh:
        record = json.load(fh)

    asof = record.get("asof")
    provenance = classify(record)
    before = record.get("scanned_at")
    filled = before or gapper_scanned_at(gappers_dir, asof)

    mtime = datetime.fromtimestamp(os.stat(path).st_mtime, UTC)
    recorded_at = record.get("recorded_at") or mtime.strftime("%Y-%m-%dT%H:%M:%SZ")

    record["scanned_at"] = filled
    record["recorded_at"] = recorded_at
    record["provenance"] = provenance

    return {
        "path": path,
        "asof": asof,
        "provenance": provenance,
        "scanned_at_before": before,
        "scanned_at_after": filled,
        "recorded_at": recorded_at,
        "unresolved": filled is None,
        "source_mismatch": record.get("source_date") != asof,
        "record": record,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--evidence-dir", default="data/premarket_gate_evidence")
    ap.add_argument("--gappers-dir", default="/app/premarket_gappers")
    # QUARANTINED: --apply is retained ONLY to fail loudly. Anyone reaching for it is
    # reaching for the exact operation the 2026-08-23 owner disposition prohibits, so a
    # silent no-op would be the wrong kindness - it has to say why.
    ap.add_argument("--apply", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.apply:
        say = lambda m: print(m, file=sys.stderr)  # noqa: E731
        say("REFUSED: --apply is permanently disabled (quarantined 2026-08-23).")
        say("  Retroactive provenance repair is prohibited by GAPPER Research Design")
        say("  v2.1.1 §5.5, and by the owner disposition recorded in")
        say("  docs/design/Gapper/"
            "GAPPER_PremarketGateProvenance_Quarantine_Review_v1.0.md §5.")
        say("  Legacy scan_001_premarket_gate/v1 records stay byte-unchanged; new records")
        say("  are written under /v2 with a write-time §5.5 stamp by")
        say("  apps/backend/app/services/premarket_evidence.py.")
        return 2

    paths = sorted(glob.glob(os.path.join(args.evidence_dir, "premarket_scan_*.json")))
    if not paths:
        print(f"no records under {args.evidence_dir}")
        return 1

    plans = [repair_record(p, args.gappers_dir) for p in paths]

    print(f"{'asof':12} {'provenance':11} {'scanned_at':22} {'recorded_at':22} note")
    for p in plans:
        note = ""
        if p["unresolved"]:
            note = "!! NO GAPPERS FILE — scanned_at stays null"
        elif p["scanned_at_before"] is None:
            note = "filled from gappers file"
        if p["source_mismatch"]:
            note += "  !! source_date != asof"
        print(
            f"{p['asof']:12} {p['provenance']:11} {str(p['scanned_at_after']):22} "
            f"{p['recorded_at']:22} {note}"
        )

    live = sum(1 for p in plans if p["provenance"] == LIVE)
    replayed = sum(1 for p in plans if p["provenance"] == REPLAYED)
    unresolved = sum(1 for p in plans if p["unresolved"])
    print(f"\ntotal={len(plans)}  live={live}  replayed={replayed}  unresolved={unresolved}")

    print("")
    print("READ-ONLY - this tool is quarantined and has no write path.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
