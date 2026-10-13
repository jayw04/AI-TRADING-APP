#!/usr/bin/env python3
"""RANGE-002: write ``snapshot_manifest.json`` (``range002.snapshot_manifest.v2``) for a Sharadar pull.

    python -I build_snapshot_manifest.py --export-dir DIR --out DIR_OR_FILE/snapshot_manifest.json \\
        --table-filter SEP --coverage-start 2015-11-02 --coverage-end 2016-03-31 \\
        --decision-day 2015-12-31 --decision-day 2016-01-29 --decision-day 2016-02-29

``DIR`` is the directory written by ``sharadar_window_pull.py``: ``tickers.parquet``,
``actions.parquet``, ``sep.parquet`` and the pull's ``manifest.json``. The runner
(``run_descriptive_screen.py``) accepts that same directory as ``--daily-snapshot``
(``store_adapter.open_snapshot`` builds one view per table from ``<table>.parquet``) and takes the
manifest written here as ``--snapshot-manifest``.

HONESTY RULE. The three tables are SEQUENTIAL VENDOR API PULLS minutes apart, not one
transaction, so ``cross_table_consistent`` is ALWAYS written false and the manifest declares
``consistency_class = sequential_pulls_evidence_checked``. Nothing here can make a pull sequence
transactional and no check below changes that flag. What is recorded instead, as EVIDENCE ONLY
(``consistency_basis`` and ``integrity``): the pull window (the pull manifest records one start
and one finish for the whole pull, not per table; that is stated), per-table byte sha256, max
``lastupdated`` per table against the first request time and the count of rows at or after it,
the ACTIONS max date, referential integrity (every SEP ticker has a TICKERS row of the filtered
vendor table; permaticker present and one per ticker; firstpricedate <= lastpricedate; SEP dates
inside the ticker's interval where one exists; ACTIONS tickers present in TICKERS), issuer-interval
counts, and required session coverage (every NYSE session of the coverage window present in SEP;
every decision day present). ``integrity.all_passed`` is true only when every gating check passes;
the runner accepts the snapshot only with its explicit sequential-pulls opt-in and only when that
is true.

The tool reads bytes and column statistics only; it prints no price or volume value.
Exit codes: 0 manifest written, every integrity check passed; 3 manifest written, an integrity
check failed (the runner refuses it even with the opt-in); 2 refused (nothing written).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import duckdb  # noqa: E402

from app.research.range002.data.identity_map import (  # noqa: E402
    audit_identity,
    build_identity_map,
)
from app.research.range002.data.manifest import (  # noqa: E402
    CLASS_SEQUENTIAL_PULLS,
    MANIFEST_SCHEMA_V2,
    REQUIRED_COLUMNS,
    parse_snapshot_manifest,
    verify_snapshot_files,
)
from app.research.range002.data.store_adapter import (  # noqa: E402
    load_identity_records,
    open_snapshot,
)
from app.research.range002.screen.session_calendar import expected_sessions  # noqa: E402

EXIT_OK = 0
EXIT_REFUSED = 2
EXIT_INTEGRITY_FAILED = 3

TABLES = tuple(name for name, _ in REQUIRED_COLUMNS)  # tickers, sep, actions
#: the date column used for min_date / max_date per table (tickers has no single date column:
#: its price-date interval bounds are used and the method text says so)
_DATE_BOUNDS = {
    "sep": ("date", "date"),
    "actions": ("date", "date"),
    "tickers": ("firstpricedate", "lastpricedate"),
}
METHOD = (
    "SEQUENTIAL VENDOR PULLS: Nasdaq Data Link datatables API v3 GET pulls "
    "(sharadar_window_pull.py), one table after another, NOT a single transaction; parquet "
    "written per table; file sha256 computed from the bytes of the delivered .parquet; "
    "min_date/max_date are the `date` bounds for sep/actions and "
    "min(firstpricedate)/max(lastpricedate) for tickers"
)


class ManifestBuildError(Exception):
    """A precondition failed; nothing is written."""


def _qi(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_utc(text: Any, what: str) -> datetime:
    if not isinstance(text, str):
        raise ManifestBuildError(f"pull manifest lacks {what}")
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ManifestBuildError(f"pull manifest {what} is not a UTC timestamp: {text!r}") from exc


def _table_stats(path: Path, table: str, start: datetime) -> dict[str, Any]:
    con = duckdb.connect(":memory:")
    try:
        src = "read_parquet('" + path.as_posix().replace("'", "''") + "')"
        desc = {
            str(r[0]).lower(): (str(r[0]), str(r[1]).upper())
            for r in con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()
        }
        columns = [v[0] for v in desc.values()]
        rows = int(con.execute(f"SELECT COUNT(*) FROM {src}").fetchone()[0])  # type: ignore[index]
        lo_col, hi_col = _DATE_BOUNDS[table]
        out: dict[str, Any] = {"rows": rows, "columns": columns}
        for key, col, fn in (("min_date", lo_col, "MIN"), ("max_date", hi_col, "MAX")):
            if col not in desc:
                raise ManifestBuildError(f"table {table!r} lacks bound column {col!r}")
            v = con.execute(f"SELECT {fn}({_qi(desc[col][0])}) FROM {src}").fetchone()[0]  # type: ignore[index]
            out[key] = None if v is None else str(v)
        lu = desc.get("lastupdated")
        if lu is None:
            out["lastupdated"] = None
        else:
            name, typ = lu
            is_date = typ == "DATE"
            tz_aware = "TIME ZONE" in typ or typ.endswith("TZ")
            threshold: Any = (
                start.date() if is_date else (start if tz_aware else start.replace(tzinfo=None))
            )
            mx = con.execute(f"SELECT MAX({_qi(name)}) FROM {src}").fetchone()[0]  # type: ignore[index]
            at_or_after = int(
                con.execute(
                    f"SELECT COUNT(*) FROM {src} WHERE {_qi(name)} >= ?", [threshold]
                ).fetchone()[0]  # type: ignore[index]
            )
            nulls = int(
                con.execute(f"SELECT COUNT(*) FROM {src} WHERE {_qi(name)} IS NULL").fetchone()[0]  # type: ignore[index]
            )
            out["lastupdated"] = {
                "type": typ,
                "max": None if mx is None else str(mx),
                "compared_with": str(threshold),
                "rows_at_or_after_pull_start": at_or_after,
                "null_rows": nulls,
            }
        return out
    finally:
        con.close()


def _scalar(con: Any, sql: str, args: list[Any] | None = None) -> int:
    row = con.execute(sql, args or []).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def integrity_checks(
    export_dir: Path,
    *,
    table_filter: str,
    coverage_start: date,
    coverage_end: date,
    decision_days: list[date],
    accepted_exceptions: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    """Counts only. ``gating`` checks decide ``all_passed``; ``informational`` ones never do.

    ``accepted_exceptions`` (check name -> identities) is an EXPLICIT, named acceptance for the
    two per-ticker vendor-data checks only. A failing check passes only when every failing
    identity is named; an unnamed failing identity still fails, and every acceptance is recorded
    with its row count in the manifest."""
    accepted_exceptions = accepted_exceptions or {}
    unknown = sorted(set(accepted_exceptions) - _ACCEPTABLE_CHECKS)
    if unknown:
        raise ManifestBuildError(f"checks {unknown} cannot be accepted by name")
    con = open_snapshot(export_dir)
    try:
        tf = [table_filter]
        sel = 'FROM "tickers" WHERE "table" = ?'
        gating: dict[str, int] = {}
        accepted_record: dict[str, Any] = {}

        def per_ticker(check: str, ids_sql: str, args: list[Any], rows_sql: str) -> None:
            ids = sorted(str(r[0]) for r in con.execute(ids_sql, args).fetchall())
            named = accepted_exceptions.get(check, set())
            unnamed = [i for i in ids if i not in named]
            gating[check] = len(unnamed)
            covered = [i for i in ids if i in named]
            if covered:
                accepted_record[check] = {
                    "identities": covered,
                    "rows": _scalar(
                        con,
                        rows_sql + " AND s.ticker IN (" + ",".join("?" for _ in covered) + ")",
                        [*args, *covered],
                    ),
                    "effect": "the identity map cannot attribute these rows to a permaticker "
                    "on their dates; the runner excludes them visibly as unattributed SEP rows",
                }
            stale = sorted(named - set(ids))
            if stale:
                raise ManifestBuildError(
                    f"accepted exception(s) {stale} for {check} do not match any failing identity"
                )

        per_ticker(
            "sep_tickers_without_tickers_row",
            'SELECT DISTINCT s.ticker FROM "sep" s WHERE s.ticker IS NOT NULL AND NOT EXISTS '
            f"(SELECT 1 {sel} AND ticker = s.ticker)",
            tf,
            'SELECT COUNT(*) FROM "sep" s WHERE s.ticker IS NOT NULL AND NOT EXISTS '
            f"(SELECT 1 {sel} AND ticker = s.ticker)",
        )
        gating["tickers_rows_with_null_permaticker"] = _scalar(
            con, f"SELECT COUNT(*) {sel} AND permaticker IS NULL", tf
        )
        gating["tickers_with_more_than_one_permaticker"] = _scalar(
            con,
            f"SELECT COUNT(*) FROM (SELECT ticker {sel} GROUP BY ticker "
            "HAVING COUNT(DISTINCT permaticker) > 1)",
            tf,
        )
        gating["rows_with_firstpricedate_after_lastpricedate"] = _scalar(
            con,
            f"SELECT COUNT(*) {sel} AND firstpricedate IS NOT NULL AND lastpricedate IS NOT NULL "
            "AND firstpricedate > lastpricedate",
            tf,
        )
        interval = (
            'FROM "tickers" t WHERE t."table" = ? AND t.ticker = s.ticker '
            "AND t.firstpricedate IS NOT NULL AND t.lastpricedate IS NOT NULL"
        )
        per_ticker(
            "sep_rows_outside_every_ticker_interval",
            f'SELECT DISTINCT s.ticker FROM "sep" s WHERE EXISTS (SELECT 1 {interval}) '
            f"AND NOT EXISTS (SELECT 1 {interval} "
            "AND s.date BETWEEN t.firstpricedate AND t.lastpricedate)",
            [table_filter, table_filter],
            f'SELECT COUNT(*) FROM "sep" s WHERE EXISTS (SELECT 1 {interval}) '
            f"AND NOT EXISTS (SELECT 1 {interval} "
            "AND s.date BETWEEN t.firstpricedate AND t.lastpricedate)",
        )
        # ACTIONS names many historical tickers that were never in TICKERS (acquisition targets,
        # spin-off parents...). The gating question for this dataset is narrower: does ACTIONS
        # name a ticker that HAS prices in the window but no TICKERS row?
        actions_absent_total = _scalar(
            con,
            'SELECT COUNT(*) FROM (SELECT DISTINCT ticker FROM "actions" WHERE ticker IS NOT NULL)'
            ' a WHERE NOT EXISTS (SELECT 1 FROM "tickers" t WHERE t.ticker = a.ticker)',
        )
        gating["actions_tickers_with_sep_rows_absent_from_tickers"] = _scalar(
            con,
            'SELECT COUNT(*) FROM (SELECT DISTINCT ticker FROM "actions" WHERE ticker IS NOT NULL)'
            ' a WHERE NOT EXISTS (SELECT 1 FROM "tickers" t WHERE t.ticker = a.ticker)'
            ' AND EXISTS (SELECT 1 FROM "sep" s WHERE s.ticker = a.ticker)',
        )
        expected = sorted(expected_sessions(coverage_start, coverage_end))
        present = {
            r[0]
            for r in con.execute(
                'SELECT DISTINCT date FROM "sep" WHERE date BETWEEN ? AND ?',
                [coverage_start, coverage_end],
            ).fetchall()
        }
        missing = [d for d in expected if d not in present]
        gating["expected_sessions_missing_from_sep"] = len(missing)
        gating["decision_days_missing_from_sep"] = sum(1 for d in decision_days if d not in present)
        ident = load_identity_records(con, table_filter=table_filter)
        audit = audit_identity(build_identity_map(ident.records))
        info = {
            "expected_sessions": len(expected),
            "sep_distinct_dates_in_window": len(present),
            "sep_dates_not_expected_sessions": len(present - set(expected)),
            "missing_session_dates": [d.isoformat() for d in missing[:20]],
            "decision_days": [d.isoformat() for d in decision_days],
            "actions_tickers_absent_from_tickers_total": actions_absent_total,
            "actions_absent_note": "historical tickers named by ACTIONS that were never in "
            "TICKERS; none has prices in the window (see the gating check)",
            "identity_rows": ident.source_rows,
            "identity_refused_rows": len(ident.refused),
            "sequential_rename_candidates": len(audit.rename_candidates),
            "sequential_reuse_candidates": len(audit.reuse_candidates),
            "overlapping_permaticker_conflicts": len(audit.permaticker_overlaps),
            "overlapping_ticker_conflicts": len(audit.ticker_overlaps),
            "note": "identity overlaps are reported, not gating: they are handled by explicit "
            "exclusion (build_fetch_universe.py --inspect-identity), never silently resolved",
        }
    finally:
        con.close()
    failed = sorted(k for k, v in gating.items() if v != 0)
    return {
        "table_filter": table_filter,
        "coverage_window": [coverage_start.isoformat(), coverage_end.isoformat()],
        "gating": gating,
        "failed_checks": failed,
        "informational": info,
        "accepted_exceptions": accepted_record,
        "all_passed": not failed,
    }


_ACCEPTABLE_CHECKS = frozenset(
    {"sep_tickers_without_tickers_row", "sep_rows_outside_every_ticker_interval"}
)


def build(
    export_dir: Path,
    *,
    table_filter: str,
    coverage_start: date,
    coverage_end: date,
    decision_days: list[date],
    accepted_exceptions: dict[str, set[str]] | None = None,
) -> tuple[dict[str, Any], bool]:
    """Return (manifest document, integrity all_passed)."""
    pull_path = export_dir / "manifest.json"
    if not pull_path.is_file():
        raise ManifestBuildError(f"{pull_path} (the pull manifest) is missing")
    try:
        pull = json.loads(pull_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManifestBuildError(f"pull manifest unreadable: {type(exc).__name__}") from exc
    if not isinstance(pull, dict):
        raise ManifestBuildError("pull manifest is not an object")
    started = _parse_utc(pull.get("extraction_started_utc"), "extraction_started_utc")
    finished = _parse_utc(pull.get("extraction_finished_utc"), "extraction_finished_utc")
    if finished < started:
        raise ManifestBuildError("pull manifest finish time precedes start time")
    source = pull.get("source")
    source_text = (
        str(source.get("system")) if isinstance(source, dict) and source.get("system") else None
    )
    if not source_text:
        raise ManifestBuildError("pull manifest lacks source.system")
    pulled = {str(f.get("table")): f for f in pull.get("files", []) if isinstance(f, dict)}

    tables: dict[str, Any] = {}
    stats: dict[str, dict[str, Any]] = {}
    shas: dict[str, str] = {}
    for name in TABLES:
        path = export_dir / f"{name}.parquet"
        if not path.is_file():
            raise ManifestBuildError(f"{path.name} is missing from the export directory")
        sha = _sha256_file(path)
        rec = pulled.get(name)
        if rec is None:
            raise ManifestBuildError(f"pull manifest does not list table {name!r}")
        if rec.get("byte_sha256") != sha:
            raise ManifestBuildError(f"{path.name}: sha256 differs from the pull manifest")
        st = _table_stats(path, name, started)
        if rec.get("rows") != st["rows"]:
            raise ManifestBuildError(f"{path.name}: row count differs from the pull manifest")
        stats[name], shas[name] = st, sha
        tables[name] = {
            "rows": st["rows"],
            "min_date": st["min_date"],
            "max_date": st["max_date"],
            "columns": st["columns"],
            "files": [{"path": path.name, "sha256": sha}],
        }

    integrity = integrity_checks(
        export_dir,
        table_filter=table_filter,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        decision_days=decision_days,
        accepted_exceptions=accepted_exceptions,
    )
    integrity["pull_window_utc"] = {
        "extraction_started_utc": started.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "extraction_finished_utc": finished.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "per_table_times_recorded": False,
        "note": "the pull manifest records one start and one finish for the whole pull",
    }
    integrity["byte_sha256"] = shas
    integrity["lastupdated_evidence"] = {n: stats[n]["lastupdated"] for n in TABLES}

    parts = [
        "NOT CROSS-TABLE CONSISTENT BY CONSTRUCTION: the tables are sequential vendor API "
        "pulls, not one transaction; the following is EVIDENCE ONLY and is not proof of "
        "consistency",
        f"pull window UTC {integrity['pull_window_utc']['extraction_started_utc']} .. "
        f"{integrity['pull_window_utc']['extraction_finished_utc']} (per-table request times "
        "are not recorded)",
    ]
    for name in TABLES:
        lu = stats[name]["lastupdated"]
        if lu is None:
            parts.append(f"{name}: no lastupdated column (revisions not observable)")
        else:
            parts.append(
                f"{name}: max lastupdated {lu['max']} ({lu['type']}); rows with lastupdated >= "
                f"{lu['compared_with']} (first request time): {lu['rows_at_or_after_pull_start']}; "
                f"null: {lu['null_rows']}"
            )
    parts.append(f"actions max date {stats['actions']['max_date']}")
    parts.append(
        "integrity: "
        + (
            "all gating checks passed"
            if integrity["all_passed"]
            else f"FAILED {integrity['failed_checks']}"
        )
    )
    parts.append(
        "limits: a vendor deletion or an ACTIONS revision would not show here; lastupdated is "
        "the vendor's revision stamp, not an as-of timestamp"
    )
    doc = {
        "schema": MANIFEST_SCHEMA_V2,
        "source": source_text,
        "extracted_at_utc": finished.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": METHOD,
        "cross_table_consistent": False,
        "consistency_class": CLASS_SEQUENTIAL_PULLS,
        "consistency_basis": " | ".join(parts),
        "integrity": integrity,
        "tables": tables,
    }
    return doc, bool(integrity["all_passed"])


def _resolve_out(out: Path) -> Path:
    return out / "snapshot_manifest.json" if out.is_dir() else out


def _iso(text: str, name: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ManifestBuildError(f"{name} must be an ISO date: {text!r}") from exc


def run(
    export_dir: Path,
    out: Path,
    *,
    table_filter: str,
    coverage_start: str,
    coverage_end: str,
    decision_days: list[str],
    accept_exceptions: list[str] | None = None,
) -> int:
    accepted: dict[str, set[str]] = {}
    for item in accept_exceptions or []:
        check, sep, ident = item.partition("=")
        if not sep or not check or not ident:
            raise ManifestBuildError(f"--accept-exception needs CHECK=IDENTITY, got {item!r}")
        accepted.setdefault(check, set()).add(ident)
    if not export_dir.is_dir():
        raise ManifestBuildError(f"{export_dir} is not a directory")
    if not table_filter.strip():
        raise ManifestBuildError("--table-filter must be a vendor table name")
    c0, c1 = _iso(coverage_start, "--coverage-start"), _iso(coverage_end, "--coverage-end")
    if c0 > c1:
        raise ManifestBuildError("--coverage-start is after --coverage-end")
    days = sorted({_iso(d, "--decision-day") for d in decision_days})
    if not days:
        raise ManifestBuildError("at least one --decision-day is required")
    target = _resolve_out(out)
    if target.exists():
        raise ManifestBuildError(f"{target} already exists; never overwritten")
    if not target.parent.is_dir():
        raise ManifestBuildError(f"{target.parent} is not an existing directory")
    doc, passed = build(
        export_dir,
        table_filter=table_filter,
        coverage_start=c0,
        coverage_end=c1,
        decision_days=days,
        accepted_exceptions=accepted,
    )
    text = json.dumps(doc, indent=2, sort_keys=True) + "\n"
    # Round-trip through the runner's own parser and verifier (WITH the opt-in, so that only
    # structural and checksum defects can remain) before anything is written.
    parsed = parse_snapshot_manifest(text)
    report = verify_snapshot_files(parsed, export_dir, allow_sequential_pulls=True)
    structural = [d for d in report.defects if "integrity checks" not in d]
    if structural:
        raise ManifestBuildError(f"manifest fails the runner's verification: {structural}")
    target.write_text(text, encoding="utf-8")
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    print(f"wrote {target} sha256={sha}")
    print("cross_table_consistent=FALSE by construction (sequential vendor pulls)")
    print(f"consistency_class={CLASS_SEQUENTIAL_PULLS}")
    if passed:
        print("integrity: all gating checks PASSED")
        return EXIT_OK
    print(f"integrity: FAILED {doc['integrity']['failed_checks']}")
    print("the runner will REFUSE this manifest even with the sequential-pulls opt-in")
    return EXIT_INTEGRITY_FAILED


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0] if __doc__ else None)
    p.add_argument("--export-dir", required=True, type=Path)
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--table-filter", required=True)
    p.add_argument("--coverage-start", required=True)
    p.add_argument("--coverage-end", required=True)
    p.add_argument("--decision-day", required=True, action="append")
    p.add_argument(
        "--accept-exception",
        action="append",
        default=[],
        metavar="CHECK=IDENTITY",
        help="explicitly accept ONE named failing identity of sep_tickers_without_tickers_row or "
        "sep_rows_outside_every_ticker_interval (repeatable); recorded with its row count",
    )
    a = p.parse_args(argv)
    try:
        return run(
            a.export_dir,
            a.out,
            table_filter=a.table_filter,
            coverage_start=a.coverage_start,
            coverage_end=a.coverage_end,
            decision_days=a.decision_day,
            accept_exceptions=a.accept_exception,
        )
    except (ManifestBuildError, duckdb.Error) as exc:
        print(f"REFUSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except Exception as exc:  # parse/snapshot errors from the shared loaders
        print(f"REFUSED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())
