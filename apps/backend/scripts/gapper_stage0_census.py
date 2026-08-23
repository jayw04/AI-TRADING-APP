"""GAPPER v2.1.1 Stage-0 data-sufficiency census CLI (preparation harness).

Wires: design latch → dataset-contract load → per-candidate-date census over a
bar-cache root (+ optional duckdb daily-store metadata) → provenance-stamped
JSON report in the output directory. Emits NO verdict — census output is a
measurement (memo §6.7/K4) and never requires the G4/§9 execution token.

The latch runs FIRST: the approved design DOCX
(docs/design/Gapper/GAPPER_Research_Design_v2_1_1.docx) is gitignored /
S3-resident (ADR 0050), so on dev machines and CI without the DOCX this script
exits non-zero with a clear "design artifact not present" error — that is the
expected, correct behavior, distinct from a hash mismatch (see --help epilog).

Usage:
    cd apps/backend && .venv/Scripts/python.exe scripts/gapper_stage0_census.py \
        --design-docx ../../docs/design/Gapper/GAPPER_Research_Design_v2_1_1.docx \
        --bar-cache-root ./bars_cache \
        --duckdb ./data/factor_data.duckdb \
        --out ./stage0_census_out
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

# Run against THIS checkout's `app` package, not whatever an editable install
# resolved elsewhere (worktree gotcha: the venv maps `app` to the main checkout).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.research.gapper_stage0 import __version__  # noqa: E402
from app.research.gapper_stage0.census import census_day, census_report  # noqa: E402
from app.research.gapper_stage0.dataset_contract import DatasetContract  # noqa: E402
from app.research.gapper_stage0.design_latch import (  # noqa: E402
    DEFAULT_DESIGN_DOCX_PATH,
    DesignArtifactMissingError,
    DesignHashMismatchError,
    SupersededDesignError,
    latch_design,
)
from app.research.gapper_stage0.provenance import make_provenance, stamp  # noqa: E402

_DAY_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.parquet$")

EXIT_DESIGN_MISSING = 2
EXIT_DESIGN_SUPERSEDED = 3
EXIT_DESIGN_MISMATCH = 4

_EPILOG = """\
exit codes:
  2  design artifact not present — the approved DOCX is gitignored/S3-resident
     (ADR 0050) and simply absent on this machine. Expected on dev/CI boxes;
     fetch the artifact to proceed. NOT a hash problem.
  3  design artifact is the SUPERSEDED (never-approved) round-2 design.
  4  design artifact hash matches neither constant — the approval is invalid.

This tool emits measurements only (census report, write_class=reconstruction).
It never emits a GO/HOLD/STOP verdict and accepts no execution token.
"""


def discover_candidate_dates(
    bar_cache_root: Path, events: list[dict[str, str]] | None
) -> list[tuple[str, date]]:
    """(symbol, day) pairs to census: the supplied event list, or every
    <ROOT>/<SYMBOL>/1Min/<YYYY-MM-DD>.parquet day-file found in the cache."""
    if events is not None:
        return [(str(e["symbol"]).upper(), date.fromisoformat(str(e["date"]))) for e in events]
    pairs: list[tuple[str, date]] = []
    if not bar_cache_root.is_dir():
        return pairs
    for sym_dir in sorted(p for p in bar_cache_root.iterdir() if p.is_dir()):
        min_dir = sym_dir / "1Min"
        if not min_dir.is_dir():
            continue
        for f in sorted(min_dir.iterdir()):
            m = _DAY_FILE_RE.match(f.name)
            if m:
                pairs.append((sym_dir.name.upper(), date.fromisoformat(m.group(1))))
    return pairs


def load_minute_bars(bar_cache_root: Path, symbol: str, day: date) -> Any:
    """Read one cached 1-min day file directly (no BarCache — that class binds
    the Alpaca adapter; this harness reads local parquet only). None if absent."""
    path = bar_cache_root / symbol / "1Min" / f"{day.isoformat()}.parquet"
    if not path.is_file():
        return None
    import pandas as pd

    return pd.read_parquet(path)


def daily_store_metadata(duckdb_path: Path | None) -> dict[str, Any]:
    """Read-only metadata about the factor store's daily spine (context for the
    census report; the census matrix itself is minute-bar based)."""
    if duckdb_path is None:
        return {"path": None, "present": False}
    meta: dict[str, Any] = {"path": str(duckdb_path), "present": duckdb_path.is_file()}
    if not meta["present"]:
        return meta
    try:
        import duckdb

        con = duckdb.connect(str(duckdb_path), read_only=True)
        try:
            row = con.execute("SELECT max(date), count(*) FROM sep").fetchone()
            meta["sep_max_date"] = str(row[0]) if row and row[0] is not None else None
            meta["sep_rows"] = int(row[1]) if row else 0
        finally:
            con.close()
    except Exception as exc:  # noqa: BLE001 — metadata is best-effort context
        meta["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="GAPPER v2.1.1 Stage-0 data-sufficiency census (preparation harness; "
        "measurements only, no verdict)",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--design-docx",
        default=DEFAULT_DESIGN_DOCX_PATH,
        help="path to the approved v2.1.1 design DOCX (latched by SHA-256 FIRST)",
    )
    parser.add_argument(
        "--contract",
        default=None,
        help="path to a §3.1 dataset-contract JSON; omitted => the default "
        "contract with source_vendor=UNSET_OWNER_DECISION (incomplete)",
    )
    parser.add_argument("--bar-cache-root", required=True, help="bars_cache/ root directory")
    parser.add_argument(
        "--duckdb", default=None, help="factor_data.duckdb path (read-only metadata)"
    )
    parser.add_argument(
        "--events",
        default=None,
        help='optional JSON file: [{"symbol": "XYZ", "date": "YYYY-MM-DD"}, ...]; '
        "omitted => census every cached 1Min day-file",
    )
    parser.add_argument("--out", required=True, help="output directory for the census report")
    parser.add_argument(
        "--created-at",
        default=None,
        help="ISO timestamp for the provenance stamp (default: now UTC)",
    )
    args = parser.parse_args(argv)

    # 1. Latch FIRST — nothing runs against an unverified design.
    try:
        design_sha = latch_design(args.design_docx)
    except DesignArtifactMissingError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_DESIGN_MISSING
    except SupersededDesignError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_DESIGN_SUPERSEDED
    except DesignHashMismatchError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_DESIGN_MISMATCH

    # 2. Contract.
    if args.contract:
        contract = DatasetContract.from_json(Path(args.contract).read_text(encoding="utf-8"))
    else:
        contract = DatasetContract()

    # 3. Census.
    bar_root = Path(args.bar_cache_root)
    events = None
    if args.events:
        events = json.loads(Path(args.events).read_text(encoding="utf-8"))
    pairs = discover_candidate_dates(bar_root, events)
    rows = [
        census_day(symbol, day, load_minute_bars(bar_root, symbol, day)) for symbol, day in pairs
    ]
    report = census_report(rows, contract)
    report["daily_store"] = daily_store_metadata(Path(args.duckdb) if args.duckdb else None)

    # 4. Provenance + write.
    created_at = args.created_at or datetime.now(UTC).isoformat()
    prov = make_provenance(
        created_at=created_at,
        source_artifact=str(args.design_docx),
        source_sha256=design_sha,
        run_id=uuid.uuid4().hex,
        code_version=__version__,
    )
    stamped = stamp(report, prov)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"gapper_stage0_census_{created_at[:10]}_{prov['run_id'][:8]}.json"
    out_path.write_text(json.dumps(stamped, indent=2), encoding="utf-8")
    print(
        f"census written: {out_path} — {report['candidate_dates']} candidate-dates, "
        f"{report['sufficient_event_days']} sufficient event-days "
        f"(target {report['target_event_days']}, meets_target={report['meets_target']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
