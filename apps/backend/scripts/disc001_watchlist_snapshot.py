#!/usr/bin/env python3
"""Build the DISC-001 Phase-1 candidate watchlist snapshot (manual / operator).

Reads the local Sharadar factor store and the premarket gappers file. Does not
touch the order path. Empty families are valid; stale/missing SEP fails closed.

  python apps/backend/scripts/disc001_watchlist_snapshot.py
  python apps/backend/scripts/disc001_watchlist_snapshot.py --inspect
  python apps/backend/scripts/disc001_watchlist_snapshot.py --ingest-history
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def main() -> int:
    from app.factor_data.store import FactorDataStore
    from app.jobs.disc001_watchlist import run_disc001_watchlist_snapshot
    from app.research.disc001.snapshot import (
        inspect_payload,
        latest_snapshot_date,
        read_snapshot,
        resolve_snapshot_dir,
    )

    inspect_only = "--inspect" in sys.argv
    ingest_only = "--ingest-history" in sys.argv
    directory = resolve_snapshot_dir()
    if ingest_only:
        from app.services.opportunity_history import ingest_snapshot_dir

        result = ingest_snapshot_dir(directory)
        print(
            json.dumps(
                {
                    "inserted": result.inserted,
                    "skipped": result.skipped,
                    "conflicts": result.conflicts,
                    "snapshot_dir": str(directory),
                },
                indent=2,
            )
        )
        return 0
    if not inspect_only:
        try:
            store = FactorDataStore(read_only=True)
        except Exception as exc:
            print(f"factor store unavailable: {exc}", file=sys.stderr)
            store = None
        try:
            run_disc001_watchlist_snapshot(factor_store=store, snapshot_dir=str(directory))
        finally:
            if store is not None:
                store.close()
    payload = read_snapshot(directory)
    report = inspect_payload(payload)
    report["snapshot_dir"] = str(directory)
    report["latest_as_of"] = latest_snapshot_date(directory)
    print(json.dumps(report, indent=2))
    return 0 if payload is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
