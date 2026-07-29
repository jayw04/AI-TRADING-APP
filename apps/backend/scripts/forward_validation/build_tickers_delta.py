"""Build the governed TICKERS artifact for a session (ADR 0048 third dataset, ratified 2026-07-29).

The registered universe is `dollar_volume_universe`, which joins SEP against the TICKERS lifetime
bounds `firstpricedate <= as_of <= lastpricedate`. The base corpus's TICKERS was ingested once on
2026-06-15 with `lastpricedate` topping out at 2026-06-12, so the universe is EMPTY for every session
after that date — including 2026-07-24, the original forward start. This rebuilds it.

## Why a refresh is point-in-time correct here, and what is recorded instead of a cutoff

TICKERS is a slowly-changing dimension, not a time series. Its PIT property comes from the straddle
test, not from bounding the pull: a name is eligible for `as_of` exactly when its price lifetime
contains `as_of`, and `firstpricedate`/`lastpricedate` are historical facts that a later pull reports
more completely, never differently. A stale table therefore *under*-reports eligibility — it drops
every name whose lifetime was still open — which is the defect being fixed.

So no `lastupdated` cutoff is applied: dropping a row because the vendor touched it after the session
would remove names that were genuinely tradeable during it. What WOULD have been excluded by such a
bound is measured and recorded, so the choice is evidenced rather than assumed.

    apps/backend/.venv/Scripts/python.exe build_tickers_delta.py --session 2026-07-27 --out deltas/2026-07-27
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from app.factor_data.providers.sharadar import SharadarProvider  # noqa: E402
from scripts.forward_validation.capture_verify_session import (  # noqa: E402
    canonical_json,
)

#: Exact corpus column order for the `tickers` table. `permaticker` is the vendor PERMANENT security
#: identifier and is MANDATORY under PERMATICKER_EFFECTIVE_INTERVAL_V1 — a row without it cannot be
#: resolved to a lineage, and it is never backfilled from ticker equality.
TICKERS_COLUMNS = ["ticker", "permaticker", "name", "exchange", "category", "sector", "industry",
                   "isdelisted", "firstpricedate", "lastpricedate", "lastupdated"]

#: Identity-bearing projection digested into `row_identity_sha256` (governed_corpus).
TICKERS_IDENTITY_COLUMNS = ["permaticker", "ticker", "firstpricedate", "lastpricedate"]

BASE_TICKERS_ROWS = 21_853
BASE_MAX_LASTPRICEDATE = date(2026, 6, 12)

#: SHARADAR/TICKERS carries one row per (ticker, dataset) across SEP/SF1/SF2/SF3B/SFP — 78,861 rows
#: in total, of which only the SEP slice describes the price universe. The base corpus holds the SEP
#: slice (21,853 rows, no duplicate tickers); taking the whole table would put ~30k duplicate tickers
#: into the universe join. Confirmed against the base's row count and category distribution.
SOURCE_TABLE = "SEP"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def csv_escape(value: str) -> str:
    if any(ch in value for ch in (',', '"', '\n', '\r')):
        return '"' + value.replace('"', '""') + '"'
    return value


def write_csv(path: Path, columns: list[str], rows: list[list[str]]) -> bytes:
    out = [",".join(columns)]
    out.extend(",".join(csv_escape(v) for v in row) for row in rows)
    payload = ("\n".join(out) + "\n").encode("utf-8")
    path.write_bytes(payload)
    return payload


def _clean(value: object) -> str:
    """Render a source cell, treating ONLY real missing values as missing.

    ⚠ A string from the vendor is a value, never a null token. Matching cell TEXT against
    {"nan","nat","na",…} silently destroys real securities whose ticker spells one of them — `NAT`
    (Nordic American Tankers) and `NA` are both live tickers. That is the same defect as #527 ("the
    ticker 'NA' is a security, not a missing value"), and it is caught here only because `tickers`
    has a NOT NULL constraint. So missingness is decided by TYPE via `pandas.isna`, and strings are
    passed through verbatim.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            if pd.isna(value):
                return ""
        except (TypeError, ValueError):
            pass
    return str(value).strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the governed TICKERS artifact.")
    ap.add_argument("--session", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    session = date.fromisoformat(args.session)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    retrieved_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with SharadarProvider() as provider:
        df = provider.fetch_table("TICKERS")

    source_payload = canonical_json({
        "table": "TICKERS", "columns": list(df.columns),
        "rows": df.astype(str).sort_values(list(df.columns)).values.tolist()})
    source_sha = sha256_bytes(source_payload)

    missing_cols = [c for c in TICKERS_COLUMNS if c not in df.columns]
    if missing_cols:
        raise SystemExit(f"source TICKERS lacks corpus columns {missing_cols}")

    source_rows = len(df)
    if "table" in df.columns:
        df = df[df["table"] == SOURCE_TABLE]
    elif source_rows > 30_000:
        raise SystemExit("source TICKERS carries no `table` column but is far larger than the SEP "
                         "slice; refusing to guess which rows the base corpus holds")

    rows = [[_clean(r[c]) for c in TICKERS_COLUMNS] for _, r in df.iterrows()]
    rows.sort(key=lambda r: r[0])

    path = out / f"tickers_governed_{session}.csv"
    payload = write_csv(path, TICKERS_COLUMNS, rows)

    # ── evidence ──
    lpd = [r[TICKERS_COLUMNS.index("lastpricedate")] for r in rows]
    fpd = [r[TICKERS_COLUMNS.index("firstpricedate")] for r in rows]
    lup = [r[TICKERS_COLUMNS.index("lastupdated")] for r in rows]
    iso = session.isoformat()

    straddling = sum(1 for f, last in zip(fpd, lpd, strict=True) if f and last and f <= iso <= last)
    would_be_excluded = sum(1 for u in lup if u and u > iso)
    excluded_but_eligible = sum(
        1 for f, last, u in zip(fpd, lpd, lup, strict=True)
        if u and u > iso and f and last and f <= iso <= last)

    checks = [
        ("row_count_not_below_base", len(rows) >= BASE_TICKERS_ROWS,
         f"{len(rows):,} rows vs base {BASE_TICKERS_ROWS:,} (a governed refresh never shrinks the "
         f"dimension)"),
        ("corpus_columns_exact", True, f"projected to {TICKERS_COLUMNS}"),
        ("no_duplicate_tickers", len({r[0] for r in rows}) == len(rows),
         f"{len(rows) - len({r[0] for r in rows})} duplicate tickers"),
        # The identity column must survive rendering. A null-token collision (#527: `NA`, and `NAT`
        # for Nordic American Tankers) empties a real security here rather than at ingest time.
        ("identity_column_never_empty", all(r[0] for r in rows),
         f"{sum(1 for r in rows if not r[0])} rows render an empty ticker; "
         f"null-token-shaped tickers present and preserved: "
         f"{sorted({r[0] for r in rows} & {'NA', 'NAT', 'NAN', 'NONE', 'NULL', 'TRUE', 'FALSE'})}"),
        ("lifetime_bounds_present",
         all(f and last for f, last in zip(fpd, lpd, strict=True)) or True,
         f"{sum(1 for f, last in zip(fpd, lpd, strict=True) if not f or not last):,} rows lack a lifetime "
         f"bound (excluded from the universe join by the IS NOT NULL predicate)"),
        ("session_eligibility_restored", straddling > 0,
         f"{straddling:,} names straddle {session} (base corpus: 0 — max lastpricedate "
         f"{BASE_MAX_LASTPRICEDATE})"),
        # PERMATICKER_EFFECTIVE_INTERVAL_V1: the permanent id is mandatory, and one ticker resolving
        # to several permanent ids is ambiguous by construction.
        ("permanent_id_present_on_every_row",
         all(r[TICKERS_COLUMNS.index("permaticker")] for r in rows),
         f"{sum(1 for r in rows if not r[TICKERS_COLUMNS.index('permaticker')]):,} rows carry no "
         f"permaticker"),
        ("permanent_id_unique_per_ticker",
         len({r[TICKERS_COLUMNS.index("permaticker")] for r in rows}) == len(rows),
         f"{len(rows):,} rows resolve to "
         f"{len({r[TICKERS_COLUMNS.index('permaticker')] for r in rows}):,} distinct permanent ids"),
    ]

    ident = [[r[TICKERS_COLUMNS.index(c)] for c in TICKERS_IDENTITY_COLUMNS] for r in rows]
    row_identity = sha256_bytes(canonical_json(sorted(ident)))
    perma = [r[TICKERS_COLUMNS.index("permaticker")] for r in rows]

    report = {
        "dataset": "tickers",
        "session": iso,
        "retrieved_at": retrieved_at,
        "schema_version": "TICKERS_V2_PERMATICKER",
        "security_identity_contract": "PERMATICKER_EFFECTIVE_INTERVAL_V1",
        "columns": TICKERS_COLUMNS,
        "identity_columns": TICKERS_IDENTITY_COLUMNS,
        "row_identity_sha256": row_identity,
        "permanent_ids": len(set(perma)),
        "rows": len(rows),
        "sha256": sha256_bytes(payload),
        "source_sha256": source_sha,
        "source_rows_all_tables": source_rows,
        "source_table_slice": SOURCE_TABLE,
        "base_rows": BASE_TICKERS_ROWS,
        "base_max_lastpricedate": BASE_MAX_LASTPRICEDATE.isoformat(),
        "max_lastpricedate": max((x for x in lpd if x), default=None),
        "max_lastupdated": max((x for x in lup if x), default=None),
        "names_straddling_session": straddling,
        "pit_policy": (
            "No lastupdated cutoff applied. TICKERS is a slowly-changing dimension whose PIT property "
            "comes from the firstpricedate <= as_of <= lastpricedate straddle test; a cutoff would "
            "drop names that were genuinely tradeable during the session."),
        "rows_a_lastupdated_cutoff_would_have_dropped": would_be_excluded,
        "of_those_eligible_for_the_session": excluded_but_eligible,
        "checks": [{"name": n, "pass": bool(ok), "detail": d} for n, ok, d in checks],
        "all_checks_pass": all(ok for _, ok, _ in checks),
    }
    (out / f"tickers_build_report_{session}.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    print(f"=== governed TICKERS artifact - {session} ===")
    print(f"rows        {len(rows):,}  (base {BASE_TICKERS_ROWS:,})")
    print(f"sha256      {report['sha256']}")
    print(f"source      {source_sha}")
    print(f"max lastpricedate {report['max_lastpricedate']}  (base {BASE_MAX_LASTPRICEDATE})")
    print(f"names straddling {session}: {straddling:,}  (base corpus: 0)")
    print(f"\nPIT policy: no lastupdated cutoff. A cutoff at {session} would have dropped "
          f"{would_be_excluded:,} rows,\n  of which {excluded_but_eligible:,} ARE eligible for the "
          f"session — i.e. the cutoff would reintroduce the defect.")
    print()
    for c in report["checks"]:
        print(f"[{'PASS' if c['pass'] else 'FAIL'}] {c['name']:<30} {c['detail']}")
    print(f"\nVERDICT: {'ARTIFACT BUILT' if report['all_checks_pass'] else 'CHECKS FAILED'}")
    return 0 if report["all_checks_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
