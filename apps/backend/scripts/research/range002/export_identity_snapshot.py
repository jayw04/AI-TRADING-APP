#!/usr/bin/env python3
"""RANGE-002 S1: bounded Sharadar identity + screening-handoff export (stdlib + duckdb only).

    python -I export_identity_snapshot.py --source <store.duckdb> --dest-root <existing dir> \\
        --export-id <id> --purpose "<text>" --executing-identity "<name or role>" \\
        --permission-ref "<record of the permission basis claimed>" \\
        --permission-scope "<scope that record is claimed to cover; name the tables>" \\
        [--no-sep-coverage] [--license-status UNKNOWN|PERSONAL|COMMERCIAL_OK] \\
        [--include-sep-daily --sep-date-from YYYY-MM-DD --sep-date-to YYYY-MM-DD \\
         --screen-start YYYY-MM-DD --required-lookback-trading-days N \\
         --lookback-calendar-days L --max-decision-gap-days G]

    python -I export_identity_snapshot.py --cleanup <export-id> --dest-root <dir> [--apply]
    python -I export_identity_snapshot.py --verify <export dir>

What it is. A bounded export of whether an existing factor store holds usable issuer identities,
ticker history and corporate-action records (default), plus, ONLY with ``--include-sep-daily``, the
explicit daily SEP columns for a caller-given inclusive date window (``sep_daily``) for RANGE-002
screening. Price/volume columns are allowed only in ``sep_daily`` and only from
``SEP_DAILY_COLUMNS``; every other table is guarded against them. ``sep_coverage`` is a per-ticker
min/max date and row count over the FULL sep table. Intraday/minute/SIP data is out of scope and
refused by name. ``sep_daily`` is refused unless the window holds at least N distinct trading dates
strictly before ``--screen-start`` (N supplied by the caller; never guessed).

Discipline.
* The source is opened ``read_only=True``; every table is copied with an explicit
  ``COPY (SELECT <explicit columns> FROM <table> ORDER BY <all columns> NULLS FIRST) TO <staging file> (FORMAT PARQUET)``
  inside ONE read transaction. No EXPORT DATABASE, no copy of the .duckdb file, no live-file hash.
* Columns are introspected from information_schema at run time. A REQUESTED column that is missing
  fails closed (no export). An OPTIONAL column that is missing is recorded as absent in the
  manifest; nothing is guessed.
* Output is staged in ``<dest-root>/.staging-<export-id>/``, validated, then published with one
  directory rename to ``<dest-root>/<export-id>/`` (same filesystem by construction, because the
  staging directory is a sibling). ``EXPORT_COMPLETE.json`` is written last inside staging, so a
  published directory always carries it; consumers must require it. A failed export leaves only the
  staging directory and is never published. An existing export or staging directory is never
  overwritten.
* Every file and the manifest get a PU-1 ``<file>.license.json`` sidecar (sources ["sharadar"],
  registry scope UNKNOWN), so the external-use seam refuses them. ``--license-status`` is recorded
  only; it grants nothing. ``--permission-ref`` and ``--permission-scope`` are required and
  recorded verbatim as ``permission_basis_claimed`` with ``permission_verified: false``: the script
  does not and cannot verify permission.
* The script performs NO deletion except ``--cleanup ... --apply`` (see ``cleanup_export``).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import sys
from collections.abc import Iterable, Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

SCRIPT_VERSION = "1.3.0"
MANIFEST_SCHEMA_VERSION = "range002.identity_export_manifest.v1"
SIDECAR_SUFFIX = ".license.json"
LICENSE_SOURCES = ["sharadar"]
LICENSE_SCOPE = "UNKNOWN"  # registry verdict for sharadar; never more permissive than the registry
LICENSE_STATUSES = ("UNKNOWN", "PERSONAL", "COMMERCIAL_OK")
EXPORT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
COMPLETE_MARKER = "EXPORT_COMPLETE.json"
FAILED_MARKER = "EXPORT_FAILED.json"
MANIFEST_NAME = "manifest.json"
README_NAME = "README_PU1.txt"
FIXED_EXTRA_FILES = (
    MANIFEST_NAME,
    MANIFEST_NAME + SIDECAR_SUFFIX,
    README_NAME,
    COMPLETE_MARKER,
    FAILED_MARKER,
    "lookback_affected_issuers.json",
    "lookback_affected_issuers.json" + SIDECAR_SUFFIX,
)
AFFECTED_FILE = "lookback_affected_issuers.json"
AFFECTED_SAMPLE_CAP = 20
#: Recorded for context only (not used by the export): current schema-pinned planning values.
PLANNING_PINS = {
    "universe.adv_window_days": 20,
    "universe.min_price": 10.0,
    "evidence": [
        "apps/backend/app/research/range002/spec/schema.py:293 adv_window_days _eq(20)",
        "apps/backend/app/research/range002/spec/schema.py:292 min_price _eq(10.0)",
        "apps/backend/scripts/research/range002/run_descriptive_screen.py --lookback-calendar-days "
        "(runner slice = [D - lookback_calendar_days, D])",
    ],
    "status": "current schema-pinned values; re-read from the frozen spec at freeze",
}

#: Price/volume column names. Allowed ONLY in table ``sep_daily`` and ONLY from SEP_DAILY_COLUMNS;
#: refused in every other table and in any sep_daily column outside the explicit list.
PRICE_VOLUME_COLUMNS = frozenset(
    {"open", "high", "low", "close", "volume", "closeadj", "closeunadj", "adj_close", "price"}
)
PRICE_VOLUME_SUBSTRINGS = ("close", "volume", "adj")
#: Explicit sep_daily projection (store.py _SEP_COLS L34-44 / DDL L137-147), in this order.
SEP_DAILY_COLUMNS = (
    "ticker", "date", "open", "high", "low", "close", "closeunadj", "closeadj", "volume",
    "lastupdated",
)  # fmt: skip
SEP_DAILY_REQUIRED = ("ticker", "date", "close", "closeunadj", "volume")
PRICE_BASIS_DECLARED = {
    "close": "vendor-documented split-adjusted (UNVERIFIED against data)",
    "closeadj": "vendor-documented split- and dividend-adjusted (UNVERIFIED)",
    "closeunadj": "vendor-documented unadjusted (UNVERIFIED)",
    "volume": "vendor-documented split-adjusted (UNVERIFIED)",
}
SEP_DAILY_LIMITATIONS = (
    "does not repair overwritten issuer history: tickers is keyed by ticker in the store DDL "
    "(store.py L150), so ticker reuse is collapsed; this file adds no identity beyond tickers",
    "contains no SIP/intraday minute bars; SEP is daily only",
    "tickers.category is as-of-latest in the store unless proven otherwise, not a historical "
    "point-in-time category",
    "price_basis_declared entries are vendor-documentation claims; this script never verifies them",
    "lookback adequacy counts distinct dates present in sep_daily, not an exchange calendar",
    "the per-issuer lookback report is informational: affected issuers are not removed here; the "
    "universe builder excludes them visibly as INSUFFICIENT_HISTORY",
    "lastupdated is a vendor revision date, not an as-of timestamp; delivered rows may include "
    "later revisions (counts reported, nothing filtered)",
    "bounded by date window, not by a symbol list; store survivorship is not established here",
)
OUT_OF_SCOPE_TABLE_RE = re.compile(
    r"(intraday|minute|\bmin\b|bars?|\bsip\b|quote|trade|tick_?data|[0-9]+min)", re.IGNORECASE
)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# (table, required columns, optional columns, table_required). The column NAMES in
# VERIFIED_IN_SCHEMA are those defined by the repository DDL / projection lists
# (app/factor_data/store.py: _TICKERS_COLS L46, _ACTIONS_COLS L63, DDL L149-L196). A requested
# column outside that set is reported in the manifest as ``columns_unverified_in_schema``.
TABLE_SPECS: tuple[tuple[str, tuple[str, ...], tuple[str, ...], bool], ...] = (
    (
        "tickers",
        (
            "permaticker",
            "ticker",
            "name",
            "exchange",
            "category",
            "isdelisted",
            "firstpricedate",
            "lastpricedate",
            "lastupdated",
        ),
        ("table",),
        True,
    ),
    ("actions", ("date", "action", "ticker", "name", "value", "contraticker"), (), True),
    (
        "ingest_runs",
        ("dataset", "started_at", "finished_at", "rows", "status"),
        ("run_id",),  # added to old stores by ALTER (store.py L325), so optional at run time
        False,
    ),
    (
        "dataset_coverage",
        (
            "dataset",
            "ingest_run_id",
            "coverage_start",
            "coverage_end",
            "artifact_sha256",
            "artifact_path",
            "source_identity",
            "rows_loaded",
            "recorded_at",
            "status",
        ),
        (),
        False,
    ),
)
VERIFIED_IN_SCHEMA: dict[str, frozenset[str]] = {
    "tickers": frozenset(
        {
            "permaticker",
            "ticker",
            "name",
            "exchange",
            "category",
            "sector",
            "industry",
            "isdelisted",
            "firstpricedate",
            "lastpricedate",
            "lastupdated",
        }
    ),  # fmt: skip
    "actions": frozenset({"date", "action", "ticker", "name", "value", "contraticker"}),
    "ingest_runs": frozenset({"dataset", "started_at", "finished_at", "rows", "status", "run_id"}),
    "dataset_coverage": frozenset(
        {
            "dataset",
            "ingest_run_id",
            "coverage_start",
            "coverage_end",
            "artifact_sha256",
            "artifact_path",
            "source_identity",
            "rows_loaded",
            "recorded_at",
            "status",
        }
    ),  # fmt: skip
    "sep": frozenset(
        {"ticker", "date", "open", "high", "low", "close", "volume", "closeadj", "closeunadj"}
        | {"lastupdated"}
    ),
}
VERIFIED_IN_SCHEMA["sep_daily"] = VERIFIED_IN_SCHEMA["sep"]
SEP_COVERAGE_COLUMNS = ("ticker", "min_date", "max_date", "n_rows")
ALL_TABLE_NAMES = tuple(t[0] for t in TABLE_SPECS) + ("sep_coverage", "sep_daily")
DATE_TYPE_PREFIXES = ("DATE", "TIMESTAMP")

REQUIRED_MANIFEST_FIELDS = (
    "schema_version", "export_id", "source", "extraction_time_utc", "executing_identity",
    "purpose", "duckdb_version", "python_version", "script_version", "script_sha256",
    "queries", "query_text_sha256", "ingest_identifiers", "files", "license_status",
    "permission_basis_claimed", "permission_verified", "destination_path", "columns_unverified_in_schema", "consistency",
)  # fmt: skip
REQUIRED_FILE_FIELDS = (
    "table", "file", "rows", "date_bounds", "columns", "byte_sha256", "logical_sha256",
)  # fmt: skip


class ExportRefused(Exception):
    """A precondition failed; nothing was published."""


def qi(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- licensing sidecar
def sidecar_path(artifact: Path) -> Path:
    return artifact.with_name(artifact.name + SIDECAR_SUFFIX)


def write_license_sidecar(artifact: Path) -> dict[str, Any]:
    """Same JSON shape and bytes as ``app.licensing.envelope.write_sidecar`` (a test asserts the
    two agree): artifact_sha256 + license_scope + license_sources, indent=2, sorted keys."""
    record = {
        "artifact_sha256": sha256_file(artifact),
        "license_scope": LICENSE_SCOPE,
        "license_sources": sorted(LICENSE_SOURCES),
    }
    sidecar_path(artifact).write_bytes(
        (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )
    return record


# ---------------------------------------------------------------- canonical logical hash
def _canon(v: Any) -> Any:
    if v is None or isinstance(v, bool | int | str):
        return v
    if isinstance(v, float):
        return v if math.isfinite(v) else f"__float__:{v!r}"
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, Decimal):
        return f"__decimal__:{v}"
    if isinstance(v, bytes):
        return f"__bytes__:{v.hex()}"
    return f"__{type(v).__name__}__:{v}"


def _digest_rows(columns: list[str], types: list[str], rows: Iterable[tuple[Any, ...]]) -> str:
    """SHA-256 over a header line (JSON ``[[name, type], ...]`` in the fixed column order) followed
    by one compact JSON array per row, in the order given (the caller reads with an explicit
    ``ORDER BY <all columns> NULLS FIRST``), each terminated by LF.

    Canonical form: NULL -> JSON ``null`` (distinct from the empty string ``""``); booleans
    ``true``/``false``; integers as JSON integers and floats via Python's shortest round-trip repr
    (so ``1`` and ``1.0`` differ; the column type is also in the header); non-finite floats as the
    string tag ``__float__:nan``; DATE/TIMESTAMP as ISO-8601; strings byte-exact (NO Unicode
    normalisation) escaped to ASCII; no locale dependence anywhere."""
    h = hashlib.sha256()
    header = [[c, t] for c, t in zip(columns, types, strict=True)]
    h.update((json.dumps(header, separators=(",", ":")) + "\n").encode("ascii"))
    for r in rows:
        line = json.dumps([_canon(v) for v in r], separators=(",", ":"), ensure_ascii=True)
        h.update((line + "\n").encode("ascii"))
    return h.hexdigest()


def canonical_rows_digest(columns: list[str], types: list[str], rows: list[tuple[Any, ...]]) -> str:
    return _digest_rows(columns, types, rows)


def order_by_clause(columns: list[str]) -> str:
    return "ORDER BY " + ", ".join(f"{qi(c)} ASC NULLS FIRST" for c in columns)


def read_parquet_summary(
    path: Path, columns: list[str], date_columns: list[str]
) -> tuple[int, dict[str, dict[str, str | None]], str]:
    con = duckdb.connect(":memory:")
    try:
        src = "read_parquet('" + path.as_posix().replace("'", "''") + "')"
        sel = ", ".join(qi(c) for c in columns)
        desc = {
            str(r[0]): str(r[1])
            for r in con.execute(f"DESCRIBE SELECT {sel} FROM {src}").fetchall()
        }
        count = [0]

        def stream() -> Iterator[tuple[Any, ...]]:
            con.execute(f"SELECT {sel} FROM {src} {order_by_clause(columns)}")
            while True:
                chunk = con.fetchmany(50_000)
                if not chunk:
                    return
                count[0] += len(chunk)
                yield from chunk

        logical = _digest_rows(columns, [desc[c] for c in columns], stream())
        bounds: dict[str, dict[str, str | None]] = {}
        for c in date_columns:
            lo, hi = con.execute(f"SELECT MIN({qi(c)}), MAX({qi(c)}) FROM {src}").fetchone() or (
                None,
                None,
            )
            bounds[c] = {
                "min": None if lo is None else str(lo),
                "max": None if hi is None else str(hi),
            }
    finally:
        con.close()
    return count[0], bounds, logical


# ---------------------------------------------------------------- copy seam (patched in tests)
def copy_query_to_parquet(con: duckdb.DuckDBPyConnection, select_sql: str, dest: Path) -> None:
    target = dest.as_posix().replace("'", "''")
    con.execute(f"COPY ({select_sql}) TO '{target}' (FORMAT PARQUET)")


# ---------------------------------------------------------------- manifest validation
def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    """Defects in a manifest dict (empty list == valid). A missing or empty field is a defect."""
    defects: list[str] = []
    for key in REQUIRED_MANIFEST_FIELDS:
        if key not in manifest:
            defects.append(f"missing field {key!r}")
        elif manifest[key] in (None, "", [], {}) and key != "columns_unverified_in_schema":
            defects.append(f"empty field {key!r}")
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        defects.append("schema_version mismatch")
    if manifest.get("permission_verified") is not False:
        defects.append("permission_verified must be exactly false")
    pb = manifest.get("permission_basis_claimed")
    if not (
        isinstance(pb, dict) and str(pb.get("ref", "")).strip() and str(pb.get("scope", "")).strip()
    ):
        defects.append("permission_basis_claimed needs non-empty ref and scope")
    if manifest.get("license_status") not in LICENSE_STATUSES:
        defects.append("license_status not one of " + "|".join(LICENSE_STATUSES))
    if not isinstance(manifest.get("columns_unverified_in_schema"), list):
        defects.append("columns_unverified_in_schema must be a list")
    ing = manifest.get("ingest_identifiers")
    if isinstance(ing, dict):
        for k in ("ingest_runs", "dataset_coverage"):
            v = ing.get(k)
            ok_list = isinstance(v, list) and len(v) > 0
            ok_unavail = (
                isinstance(v, dict)
                and v.get("value") == "unavailable"
                and isinstance(v.get("reason"), str)
                and v["reason"].strip() != ""
            )
            if not (ok_list or ok_unavail):
                defects.append(f"ingest_identifiers.{k} must be a non-empty list or 'unavailable'")
    files = manifest.get("files")
    if isinstance(files, list):
        names = [f.get("table") for f in files if isinstance(f, dict)]
        for req in ("tickers", "actions"):
            if req not in names:
                defects.append(f"files lacks required table {req!r}")
        for f in files:
            if not isinstance(f, dict):
                defects.append("file entry is not an object")
                continue
            for key in REQUIRED_FILE_FIELDS:
                if key not in f or f[key] in (None, "", []):
                    if key == "date_bounds" and f.get(key) == {}:
                        continue  # a table with no date columns present
                    if key == "rows" and f.get(key) == 0:
                        continue
                    defects.append(f"file {f.get('table')!r}: missing/empty {key!r}")
            defects.extend(column_guard_defects(f.get("table"), f.get("columns", [])))
            if (
                f.get("table") == "sep_coverage"
                and tuple(f.get("columns", ())) != SEP_COVERAGE_COLUMNS
            ):
                defects.append("sep_coverage columns are not exactly the coverage columns")
        has_daily = "sep_daily" in names
        sd = manifest.get("sep_daily")
        if has_daily != isinstance(sd, dict):
            defects.append("sep_daily file and manifest section must appear together")
        if has_daily and isinstance(sd, dict):
            for key in (
                "requested_window", "min_date_present", "max_date_present", "rows",
                "distinct_tickers", "rows_per_year", "columns_requested", "columns_present",
                "columns_missing", "price_basis_declared", "limitations", "lookback",
            ):  # fmt: skip
                if key not in sd or (sd[key] in (None, "", [], {}) and key != "columns_missing"):
                    if key == "rows" and sd.get(key) == 0:
                        continue
                    defects.append(f"sep_daily section: missing/empty {key!r}")
            if sd.get("price_basis_declared") != PRICE_BASIS_DECLARED:
                defects.append("sep_daily section: price_basis_declared is not the declared claims")
            lb = sd.get("lookback")
            if not isinstance(lb, dict) or lb.get("result") != "PASS":
                defects.append("sep_daily section: lookback check did not PASS")
            elif not lb.get("decision_days"):
                defects.append("sep_daily section: lookback.decision_days missing/empty")
            if not isinstance(manifest.get("planning_inputs"), dict) or not manifest[
                "planning_inputs"
            ].get("lookback_calendar_days"):
                defects.append("planning_inputs missing for sep_daily export")
            elif not manifest["planning_inputs"].get("max_decision_gap_days"):
                defects.append("planning_inputs.max_decision_gap_days missing")
            if isinstance(lb, dict):
                for day in lb.get("decision_days", []):
                    if day.get("gap_within_limit") is not True or not day.get(
                        "max_decision_gap_days"
                    ):
                        defects.append(
                            f"decision day {day.get('decision_day')}: gap_within_limit/"
                            "max_decision_gap_days not recorded as passing"
                        )
            if not manifest.get("report_files"):
                defects.append("report_files missing for sep_daily export")
    return defects


def column_guard_defects(table: Any, columns: Any) -> list[str]:
    """Price/volume allowlist: such columns only in ``sep_daily`` and only the explicit list."""
    cols = [str(c) for c in columns]
    if table == "sep_daily":
        extra = [c for c in cols if c not in SEP_DAILY_COLUMNS]
        return [f"file 'sep_daily': column(s) outside the explicit list {extra}"] if extra else []
    bad = sorted(
        c
        for c in cols
        if c.lower() in PRICE_VOLUME_COLUMNS or any(t in c.lower() for t in PRICE_VOLUME_SUBSTRINGS)
    )
    if bad:
        return [f"file {table!r}: price/volume column(s) {bad} are allowed only in sep_daily"]
    return []


def check_requested_tables(names: Iterable[str], include_sep_daily: bool) -> None:
    """Refuse by name any requested table outside the export scope (intraday/minute/SIP first)."""
    for n in names:
        if n in ALL_TABLE_NAMES:
            if n == "sep_daily" and not include_sep_daily:
                raise ExportRefused("table 'sep_daily' requires --include-sep-daily")
            continue
        if OUT_OF_SCOPE_TABLE_RE.search(n):
            raise ExportRefused(
                f"table {n!r} refused: intraday/minute/SIP/bar data is out of scope (daily SEP only)"
            )
        raise ExportRefused(f"table {n!r} refused: not one of {list(ALL_TABLE_NAMES)}")


def validate_export_dir(root: Path, manifest: dict[str, Any]) -> list[str]:
    """Manifest defects plus a re-check of every delivered file against its recorded hashes."""
    defects = validate_manifest(manifest)
    for f in manifest.get("files", []):
        if not isinstance(f, dict) or "file" not in f:
            continue
        p = root / f["file"]
        if not p.is_file():
            defects.append(f"file {f['file']!r} missing")
            continue
        if sha256_file(p) != f.get("byte_sha256"):
            defects.append(f"file {f['file']!r}: byte sha256 mismatch")
        rows, _, logical = read_parquet_summary(p, list(f.get("columns", [])), [])
        if rows != f.get("rows"):
            defects.append(f"file {f['file']!r}: row count mismatch")
        if logical != f.get("logical_sha256"):
            defects.append(f"file {f['file']!r}: logical sha256 mismatch")
        sc = sidecar_path(p)
        if not sc.is_file():
            defects.append(f"file {f['file']!r}: license sidecar missing")
    for rf in manifest.get("report_files", []):
        rp = root / str(rf.get("file", ""))
        if not rp.is_file():
            defects.append(f"report file {rf.get('file')!r} missing")
        elif sha256_file(rp) != rf.get("byte_sha256"):
            defects.append(f"report file {rf.get('file')!r}: byte sha256 mismatch")
        elif not sidecar_path(rp).is_file():
            defects.append(f"report file {rf.get('file')!r}: license sidecar missing")
    return defects


# ---------------------------------------------------------------- export
def _introspect(con: duckdb.DuckDBPyConnection) -> dict[str, dict[str, str]]:
    """table -> {column_name: data_type} for the main schema, read inside the transaction."""
    out: dict[str, dict[str, str]] = {}
    rows = con.execute(
        "SELECT table_name, column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'main' ORDER BY table_name, ordinal_position"
    ).fetchall()
    for t, c, d in rows:
        out.setdefault(str(t), {})[str(c)] = str(d)
    return out


def _unavailable(reason: str) -> dict[str, str]:
    return {"value": "unavailable", "reason": reason}


def _jsonable(v: Any) -> Any:
    return v.isoformat() if isinstance(v, date | datetime) else v


def _ingest_identifiers(
    con: duckdb.DuckDBPyConnection, schema: dict[str, dict[str, str]]
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    runs = schema.get("ingest_runs")
    if not runs:
        out["ingest_runs"] = _unavailable("table ingest_runs is absent from the source schema")
    elif "run_id" not in runs:
        out["ingest_runs"] = _unavailable("column ingest_runs.run_id is absent from the source")
    else:
        cols: list[str] = [c for c in ("dataset", "run_id", "status", "finished_at") if c in runs]
        rows = con.execute(
            f'SELECT {", ".join(qi(c) for c in cols)} FROM "ingest_runs" ' + order_by_clause(cols)
        ).fetchall()
        lst = [{c: _jsonable(v) for c, v in zip(cols, r, strict=True)} for r in rows]
        out["ingest_runs"] = lst or _unavailable("table ingest_runs holds no rows")
    cov = schema.get("dataset_coverage")
    if not cov:
        out["dataset_coverage"] = _unavailable("table dataset_coverage is absent from the source")
    else:
        want = (
            "dataset", "ingest_run_id", "coverage_start", "coverage_end", "artifact_sha256",
            "source_identity", "rows_loaded", "status",
        )  # fmt: skip
        cols2: list[str] = [c for c in want if c in cov]
        rows = con.execute(
            f'SELECT {", ".join(qi(c) for c in cols2)} FROM "dataset_coverage" '
            + order_by_clause(cols2)
        ).fetchall()
        lst = [{c: _jsonable(v) for c, v in zip(cols2, r, strict=True)} for r in rows]
        out["dataset_coverage"] = lst or _unavailable("table dataset_coverage holds no rows")
    return out


def plan_queries(
    schema: dict[str, dict[str, str]],
    include_sep_coverage: bool,
    sep_daily: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Resolve the explicit SELECT per table against the introspected schema. Raises
    ExportRefused when a REQUESTED column or required table is missing."""
    plans: list[dict[str, Any]] = []
    not_exported: dict[str, str] = {}
    for table, required, optional, table_required in TABLE_SPECS:
        have = schema.get(table)
        if have is None:
            if table_required:
                raise ExportRefused(f"required table {table!r} is missing from the source")
            not_exported[table] = "table absent from the source schema"
            continue
        missing = [c for c in required if c not in have]
        if missing:
            raise ExportRefused(f"table {table!r} lacks requested column(s) {missing}")
        absent_opt = [c for c in optional if c not in have]
        cols = list(required) + [c for c in optional if c in have]
        plans.append(
            {
                "table": table,
                "columns": cols,
                "optional_columns_absent": absent_opt,
                "select": f"SELECT {', '.join(qi(c) for c in cols)} FROM {qi(table)} {order_by_clause(cols)}",
                "source_types": {c: have[c] for c in cols},
            }
        )
    if include_sep_coverage:
        sep = schema.get("sep")
        if sep is None or "ticker" not in sep or "date" not in sep:
            raise ExportRefused("sep_coverage requested but sep.ticker/sep.date are not present")
        plans.append(
            {
                "table": "sep_coverage",
                "columns": list(SEP_COVERAGE_COLUMNS),
                "optional_columns_absent": [],
                "select": (
                    'SELECT "ticker" AS ticker, MIN("date") AS min_date, MAX("date") AS max_date, '
                    'COUNT(*) AS n_rows FROM "sep" GROUP BY "ticker" '
                    + order_by_clause(list(SEP_COVERAGE_COLUMNS))
                ),
                "source_types": {"ticker": sep["ticker"], "date": sep["date"]},
            }
        )
    else:
        not_exported["sep_coverage"] = "not requested (--no-sep-coverage)"
    if sep_daily is not None:
        sep = schema.get("sep")
        if sep is None:
            raise ExportRefused("sep_daily requested but table 'sep' is missing from the source")
        missing_req = [c for c in SEP_DAILY_REQUIRED if c not in sep]
        if missing_req:
            raise ExportRefused(f"table 'sep' lacks requested column(s) {missing_req}")
        present = [c for c in SEP_DAILY_COLUMNS if c in sep]
        plans.append(
            {
                "table": "sep_daily",
                "columns": present,
                "columns_requested": list(SEP_DAILY_COLUMNS),
                "columns_missing": [c for c in SEP_DAILY_COLUMNS if c not in sep],
                "optional_columns_absent": [c for c in SEP_DAILY_COLUMNS if c not in sep],
                "select": (
                    f'SELECT {", ".join(qi(c) for c in present)} FROM "sep" WHERE "date" '
                    f"BETWEEN DATE '{sep_daily['from']}' AND DATE '{sep_daily['to']}' "
                    + order_by_clause(present)
                ),
                "source_types": {c: sep[c] for c in present},
            }
        )
    else:
        not_exported["sep_daily"] = "not requested (--include-sep-daily is off)"
    for pl in plans:
        bad = column_guard_defects(pl["table"], pl["columns"])
        if bad:
            raise ExportRefused("column guard: " + "; ".join(bad))
    return plans, not_exported


def _check_id(export_id: str) -> None:
    if not EXPORT_ID_RE.match(export_id):
        raise ExportRefused(f"export id {export_id!r} must match {EXPORT_ID_RE.pattern}")


def _sep_daily_config(
    include: bool,
    date_from: str | None,
    date_to: str | None,
    screen_start: str | None,
    n_lookback: int | None,
    lookback_calendar_days: int | None = None,
    max_decision_gap_days: int | None = None,
) -> dict[str, Any] | None:
    given = [
        x is not None
        for x in (
            date_from,
            date_to,
            screen_start,
            n_lookback,
            lookback_calendar_days,
            max_decision_gap_days,
        )
    ]
    if not include:
        if any(given):
            raise ExportRefused(
                "--sep-date-from/--sep-date-to/--screen-start/--required-lookback-trading-days/"
                "--lookback-calendar-days/--max-decision-gap-days are only valid with "
                "--include-sep-daily"
            )
        return None
    if not all(given):
        raise ExportRefused(
            "--include-sep-daily requires --sep-date-from, --sep-date-to, --screen-start and "
            "--required-lookback-trading-days, --lookback-calendar-days and "
            "--max-decision-gap-days (no defaults)"
        )
    parsed: dict[str, date] = {}
    for label, val in (("sep-date-from", date_from), ("sep-date-to", date_to),
                       ("screen-start", screen_start)):  # fmt: skip
        if val is None or not DATE_RE.match(val):
            raise ExportRefused(f"--{label} must be YYYY-MM-DD")
        try:
            parsed[label] = date.fromisoformat(val)
        except ValueError as exc:
            raise ExportRefused(f"--{label} is not a valid date: {val}") from exc
    if not parsed["sep-date-from"] <= parsed["sep-date-to"]:
        raise ExportRefused("--sep-date-from must be <= --sep-date-to")
    if not parsed["sep-date-from"] < parsed["screen-start"] <= parsed["sep-date-to"]:
        raise ExportRefused(
            "--screen-start must satisfy sep-date-from < screen-start <= sep-date-to"
        )
    if n_lookback is None or isinstance(n_lookback, bool) or n_lookback < 1:
        raise ExportRefused("--required-lookback-trading-days must be an integer >= 1")
    if (
        lookback_calendar_days is None
        or isinstance(lookback_calendar_days, bool)
        or lookback_calendar_days < 1
    ):
        raise ExportRefused("--lookback-calendar-days must be an integer >= 1")
    if (
        max_decision_gap_days is None
        or isinstance(max_decision_gap_days, bool)
        or max_decision_gap_days < 1
    ):
        raise ExportRefused("--max-decision-gap-days must be an integer >= 1")
    return {
        "lookback_calendar_days": lookback_calendar_days,
        "max_decision_gap_days": max_decision_gap_days,
        "from": str(date_from),
        "to": str(date_to),
        "screen_start": str(screen_start),
        "required_lookback_trading_days": n_lookback,
    }


def run_export(
    *,
    source: Path,
    dest_root: Path,
    export_id: str,
    purpose: str,
    executing_identity: str,
    permission_ref: str,
    permission_scope: str,
    include_sep_coverage: bool = True,
    license_status: str = "UNKNOWN",
    include_sep_daily: bool = False,
    sep_date_from: str | None = None,
    sep_date_to: str | None = None,
    screen_start: str | None = None,
    required_lookback_trading_days: int | None = None,
    lookback_calendar_days: int | None = None,
    max_decision_gap_days: int | None = None,
    requested_tables: Iterable[str] = (),
) -> Path:
    for label, val in (
        ("purpose", purpose),
        ("executing-identity", executing_identity),
        ("permission-ref", permission_ref),
        ("permission-scope", permission_scope),
    ):
        if not val or not val.strip():
            raise ExportRefused(f"--{label} is required and must not be empty")
    if license_status not in LICENSE_STATUSES:
        raise ExportRefused(f"--license-status must be one of {LICENSE_STATUSES}")
    _check_id(export_id)
    check_requested_tables(requested_tables, include_sep_daily)
    sep_daily_cfg = _sep_daily_config(
        include_sep_daily,
        sep_date_from,
        sep_date_to,
        screen_start,
        required_lookback_trading_days,
        lookback_calendar_days,
        max_decision_gap_days,
    )
    if not dest_root.is_dir():
        raise ExportRefused(f"--dest-root {str(dest_root)!r} is not an existing directory")
    if not source.is_file():
        raise ExportRefused(f"--source {str(source)!r} is not an existing file")
    final = dest_root / export_id
    staging = dest_root / f".staging-{export_id}"
    if os.path.lexists(final):
        raise ExportRefused(f"export {str(final)!r} already exists; never overwritten")
    if os.path.lexists(staging):
        raise ExportRefused(f"staging {str(staging)!r} already exists; never overwritten")

    staging.mkdir()
    try:
        _build_into_staging(
            source=source, staging=staging, final=final, export_id=export_id, purpose=purpose,
            executing_identity=executing_identity, permission_ref=permission_ref,
            permission_scope=permission_scope, include_sep_coverage=include_sep_coverage,
            license_status=license_status, sep_daily_cfg=sep_daily_cfg,
        )  # fmt: skip
        marker = staging / COMPLETE_MARKER
        try:
            os.rename(staging, final)
        except OSError:
            marker.unlink(missing_ok=True)
            raise
    except BaseException as exc:
        try:
            (staging / FAILED_MARKER).write_text(
                json.dumps({"export_id": export_id, "failed_utc": utc_now(), "error": repr(exc)})
                + "\n",
                encoding="utf-8",
            )
            (staging / COMPLETE_MARKER).unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return final


def _build_into_staging(
    *,
    source: Path,
    staging: Path,
    final: Path,
    export_id: str,
    purpose: str,
    executing_identity: str,
    permission_ref: str,
    permission_scope: str,
    include_sep_coverage: bool,
    license_status: str,
    sep_daily_cfg: dict[str, Any] | None = None,
) -> None:
    con = duckdb.connect(str(source), read_only=True)
    try:
        con.execute("BEGIN TRANSACTION")
        extraction_time = utc_now()
        schema = _introspect(con)
        plans, not_exported = plan_queries(
            schema,
            include_sep_coverage,
            None if sep_daily_cfg is None else {k: str(v) for k, v in sep_daily_cfg.items()},
        )
        structural: list[dict[str, Any]] | None = None
        if sep_daily_cfg is not None:
            win = (
                f'(SELECT * FROM "sep" WHERE "date" BETWEEN DATE \'{sep_daily_cfg["from"]}\' '
                f"AND DATE '{sep_daily_cfg['to']}')"
            )
            structural = lookback_structural(con, win, sep_daily_cfg)
        ingest = _ingest_identifiers(con, schema)
        for p in plans:
            copy_query_to_parquet(con, p["select"], staging / f"{p['table']}.parquet")
        con.execute("COMMIT")
    finally:
        con.close()

    unverified = sorted(
        f"{p['table']}.{c}"
        for p in plans
        for c in p["columns"]
        if p["table"] in VERIFIED_IN_SCHEMA and c not in VERIFIED_IN_SCHEMA[p["table"]]
    )
    files: list[dict[str, Any]] = []
    for p in plans:
        path = staging / f"{p['table']}.parquet"
        date_cols = [
            c
            for c in p["columns"]
            if p["source_types"].get(c, "").upper().startswith(DATE_TYPE_PREFIXES)
        ]
        if p["table"] == "sep_coverage":
            date_cols = ["min_date", "max_date"]
        rows, bounds, logical = read_parquet_summary(path, p["columns"], date_cols)
        files.append(
            {
                "table": p["table"],
                "file": path.name,
                "rows": rows,
                "date_bounds": bounds,
                "columns": p["columns"],
                "optional_columns_absent": p["optional_columns_absent"],
                "columns_missing": p.get("columns_missing", []),
                "byte_sha256": sha256_file(path),
                "logical_sha256": logical,
                "bytes": path.stat().st_size,
                "license_sidecar": sidecar_path(path).name,
            }
        )
        write_license_sidecar(path)
    queries = {p["table"]: p["select"] for p in plans}
    sep_daily_section: dict[str, Any] | None = None
    report_files: list[dict[str, Any]] = []
    if sep_daily_cfg is not None:
        sp = next(p for p in plans if p["table"] == "sep_daily")
        assert structural is not None
        sep_daily_section, report_files = _sep_daily_section(staging, sp, sep_daily_cfg, structural)
    joined = "\n".join(queries[t] for t in ALL_TABLE_NAMES if t in queries)
    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "export_id": export_id,
        "source": {
            "system": "Sharadar-derived factor store (DuckDB), opened read_only",
            "path_as_given": str(source),
            "note": "no hash of the live .duckdb file is recorded or required",
        },
        "extraction_time_utc": extraction_time,
        "executing_identity": executing_identity,
        "purpose": purpose,
        "duckdb_version": duckdb.__version__,
        "python_version": platform.python_version(),
        "script_version": SCRIPT_VERSION,
        "script_sha256": sha256_file(Path(__file__)),
        "queries": queries,
        "copy_template": "COPY (<query>) TO '<staging file>' (FORMAT PARQUET)",
        "query_text_sha256": sha256_bytes(joined.encode("utf-8")),
        "ingest_identifiers": ingest,
        "files": files,
        "tables_not_exported": not_exported,
        "license_status": license_status,
        "license_note": "recorded only; classification is not permission; the sidecars carry "
        f"scope {LICENSE_SCOPE} for sources {LICENSE_SOURCES}",
        "permission_basis_claimed": {
            "ref": permission_ref,
            "scope": permission_scope,
            "tables_named_in_scope": sorted(
                p["table"] for p in plans if p["table"] in permission_scope
            ),
            "tables_not_named_in_scope": sorted(
                p["table"] for p in plans if p["table"] not in permission_scope
            ),
        },
        "permission_verified": False,
        "permission_note": "operator-supplied text recorded verbatim; this script does not and "
        "cannot verify permission, and a non-empty string is not verified permission",
        "destination_path": str(final),
        "columns_unverified_in_schema": unverified,
        "consistency": {
            "basis": "one DuckDB read transaction on a read_only connection; all COPY queries, "
            "the schema introspection and the ingest identifiers ran inside it",
            "limits": "snapshot consistency is that of DuckDB MVCC for this connection; the store "
            "is not quiesced by this script and no external writer coordination is performed",
        },
        "marker": COMPLETE_MARKER,
    }
    if sep_daily_section is not None and sep_daily_cfg is not None:
        manifest["sep_daily"] = sep_daily_section
        manifest["report_files"] = report_files
        manifest["planning_inputs"] = {
            "universe.adv_window_days": sep_daily_cfg["required_lookback_trading_days"],
            "adv_window_matches_schema_pin": sep_daily_cfg["required_lookback_trading_days"]
            == PLANNING_PINS["universe.adv_window_days"],
            "universe.min_price": PLANNING_PINS["universe.min_price"],
            "min_price_note": "recorded for context; not used by the export",
            "lookback_calendar_days": sep_daily_cfg["lookback_calendar_days"],
            "max_decision_gap_days": sep_daily_cfg["max_decision_gap_days"],
            "export_window": {"from": sep_daily_cfg["from"], "to": sep_daily_cfg["to"]},
            "screen_start": sep_daily_cfg["screen_start"],
            "evidence": PLANNING_PINS["evidence"],
            "status": PLANNING_PINS["status"],
        }
    defects = validate_manifest(manifest)
    if defects:
        raise ExportRefused("manifest validation failed: " + "; ".join(defects))
    man_path = staging / MANIFEST_NAME
    man_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_license_sidecar(man_path)
    (staging / README_NAME).write_text(
        "PU-1 NOTICE\n"
        f"License status recorded by the operator: {license_status} (scope UNKNOWN/PERSONAL for "
        "Sharadar in the registry).\n"
        "Internal diagnostics / screening inputs only. Not for presentation, redistribution or any external "
        "use. A label or sidecar does not establish permission to share.\n"
        f"Consumers must require {COMPLETE_MARKER}; a directory without it is incomplete.\n",
        encoding="utf-8",
    )
    # Re-validate what was actually written, then write the completion marker last.
    again = validate_export_dir(staging, json.loads(man_path.read_text(encoding="utf-8")))
    if again:
        raise ExportRefused("post-write validation failed: " + "; ".join(again))
    (staging / COMPLETE_MARKER).write_text(
        json.dumps(
            {
                "export_id": export_id,
                "manifest_sha256": sha256_file(man_path),
                "files": sorted(f["file"] for f in files),
                "report_files": sorted(str(r["file"]) for r in report_files),
                "completed_utc": utc_now(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _month_starts(screen_start: date, to: date) -> list[date]:
    y, m = screen_start.year, screen_start.month
    if screen_start.day != 1:
        m += 1
    out: list[date] = []
    while True:
        if m == 13:
            y, m = y + 1, 1
        d = date(y, m, 1)
        if d > to:
            return out
        out.append(d)
        m += 1


def _as_date(v: Any) -> date:
    return v.date() if isinstance(v, datetime) else v


def lookback_structural(
    con: duckdb.DuckDBPyConnection, src: str, cfg: dict[str, Any]
) -> list[dict[str, Any]]:
    """Structural lookback check, fail closed. For each month start M in the screening range the
    decision day D is the last date present strictly before M; the runner slice is the calendar
    range [D - lookback_calendar_days, D] inclusive and must hold at least N distinct dates by
    itself (history outside the slice never counts). ``src`` is a FROM-able SQL source."""
    need = int(cfg["required_lookback_trading_days"])
    span = int(cfg["lookback_calendar_days"])
    max_gap = int(cfg["max_decision_gap_days"])
    months = _month_starts(date.fromisoformat(cfg["screen_start"]), date.fromisoformat(cfg["to"]))
    if not months:
        raise ExportRefused("no month start lies in [screen-start, sep-date-to]; no decision day")
    out: list[dict[str, Any]] = []
    for m in months:
        row = con.execute(f'SELECT MAX("date") FROM {src} WHERE "date" < DATE \'{m}\'').fetchone()
        if row is None or row[0] is None:
            raise ExportRefused(
                f"lookback inadequate: no session before month start {m} in the exported window; "
                "the decision day is undefined (nothing exported)"
            )
        d = _as_date(row[0])
        gap = (m - d).days
        if gap > max_gap:
            raise ExportRefused(
                f"decision-day gap too large: decision day {d} (month start {m}): gap {gap} "
                f"calendar days > maximum {max_gap} (data hole or short window; nothing exported)"
            )
        start = d - timedelta(days=span)
        cnt = con.execute(
            f'SELECT COUNT(DISTINCT "date") FROM {src} '
            f"WHERE \"date\" BETWEEN DATE '{start}' AND DATE '{d}'"
        ).fetchone()
        n = int(cnt[0]) if cnt else 0
        if n < need:
            raise ExportRefused(
                f"lookback inadequate: decision day {d} (month start {m}): the runner slice "
                f"[{start}, {d}] holds {n} distinct trading dates < required {need}; history "
                "outside the slice does not count (nothing exported)"
            )
        out.append(
            {
                "month_start": str(m),
                "decision_day": str(d),
                "decision_day_gap_calendar_days": gap,
                "max_decision_gap_days": max_gap,
                "gap_within_limit": True,
                "d_precedes_month_start": d < m,
                "slice_start": str(start),
                "slice_end": str(d),
                "distinct_trading_dates_in_slice": n,
            }
        )
    return out


def _issuer_report(
    con: duckdb.DuckDBPyConnection, src: str, day: dict[str, Any], need: int, has_lu: bool
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    d, start = day["decision_day"], day["slice_start"]
    rows = con.execute(
        f"""SELECT "ticker",
               COUNT(DISTINCT "date"),
               COUNT(DISTINCT "date") FILTER (WHERE "close" > 0 AND "closeunadj" > 0 AND "volume" > 0),
               COUNT(*) FILTER (WHERE "close" IS NULL OR "closeunadj" IS NULL OR "volume" IS NULL),
               COUNT(*) FILTER (WHERE "volume" = 0),
               COUNT(*) FILTER (WHERE "close" <= 0 OR "closeunadj" <= 0)
            FROM {src}
            WHERE "date" BETWEEN DATE '{start}' AND DATE '{d}'
              AND "ticker" IN (SELECT "ticker" FROM {src} WHERE "date" = DATE '{d}')
            GROUP BY "ticker" ORDER BY "ticker" """
    ).fetchall()
    affected: list[dict[str, Any]] = []
    for t, n_rows, usable, nulls, zero_vol, nonpos in rows:
        if usable >= need:
            continue
        reasons = []
        if n_rows < need:
            reasons.append(f"ROWS_IN_SLICE_LT_{need}")
        if nulls:
            reasons.append("NULL_FIELD")
        if zero_vol:
            reasons.append("ZERO_VOLUME")
        if nonpos:
            reasons.append("NONPOSITIVE_PRICE")
        affected.append(
            {
                "ticker": t,
                "reasons": reasons,
                "rows_in_slice": int(n_rows),
                "usable_in_slice": int(usable),
            }
        )
    by_reason: dict[str, int] = {}
    for a in affected:
        for r in a["reasons"]:
            by_reason[r] = by_reason.get(r, 0) + 1
    in_slice = con.execute(
        f'SELECT COUNT(*), MAX("date"), COUNT(*) FILTER (WHERE "date" > DATE \'{d}\') FROM {src} '
        f"WHERE \"date\" BETWEEN DATE '{start}' AND DATE '{d}'"
    ).fetchone()
    after = con.execute(f"SELECT COUNT(*) FROM {src} WHERE \"date\" > DATE '{d}'").fetchone()
    lastupd: dict[str, Any]
    if has_lu:
        lu = con.execute(
            f"SELECT COUNT(*) FILTER (WHERE CAST(\"lastupdated\" AS DATE) > DATE '{d}'), "
            f'MIN("lastupdated"), MAX("lastupdated") FROM {src} '
            f"WHERE \"date\" BETWEEN DATE '{start}' AND DATE '{d}'"
        ).fetchone()
        lastupd = {
            "rows_in_slice_with_lastupdated_after_decision_day": int(lu[0]) if lu else 0,
            "lastupdated_min": None if not lu or lu[1] is None else str(lu[1]),
            "lastupdated_max": None if not lu or lu[2] is None else str(lu[2]),
            "caveat": "vendor lastupdated is not an as-of timestamp: later revisions may be "
            "present in delivered rows; report only, nothing filtered or changed",
        }
    else:
        lastupd = _unavailable("column lastupdated is absent from the export")
    summary = {
        **day,
        "required_trading_days": need,
        "tickers_on_decision_day": len(rows),
        "affected_issuers_count": len(affected),
        "affected_by_reason": dict(sorted(by_reason.items())),
        "affected_sample": [a["ticker"] for a in affected[:AFFECTED_SAMPLE_CAP]],
        "rows_in_slice": int(in_slice[0]) if in_slice else 0,
        "max_date_in_slice": None if not in_slice or in_slice[1] is None else str(in_slice[1]),
        "rows_in_slice_with_date_after_decision_day": int(in_slice[2]) if in_slice else 0,
        "exported_rows_after_decision_day_not_in_slice": int(after[0]) if after else 0,
        "lastupdated_vs_decision_day": lastupd,
    }
    return summary, affected


def _sep_daily_section(
    staging: Path, plan: dict[str, Any], cfg: dict[str, Any], structural: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Window statistics, the structural lookback check re-run on the delivered file (must equal the
    in-transaction result) and the per-issuer / availability report."""
    path = staging / "sep_daily.parquet"
    src = "read_parquet('" + path.as_posix().replace("'", "''") + "')"
    need = int(cfg["required_lookback_trading_days"])
    con = duckdb.connect(":memory:")
    try:
        n, lo, hi, tickers, dates = con.execute(
            f'SELECT COUNT(*), MIN("date"), MAX("date"), COUNT(DISTINCT "ticker"), '
            f'COUNT(DISTINCT "date") FROM {src}'
        ).fetchone() or (0, None, None, 0, 0)
        per_year = {
            str(y): int(c)
            for y, c in con.execute(
                f'SELECT year("date"), COUNT(*) FROM {src} GROUP BY 1 ORDER BY 1'
            ).fetchall()
        }
        again = lookback_structural(con, src, cfg)
        if again != structural:
            raise ExportRefused("lookback structural result differs between source and file")
        has_lu = "lastupdated" in plan["columns"]
        days: list[dict[str, Any]] = []
        affected_by_day: dict[str, list[dict[str, Any]]] = {}
        for day in again:
            summary, affected = _issuer_report(con, src, day, need, has_lu)
            days.append(summary)
            affected_by_day[day["decision_day"]] = affected
    finally:
        con.close()
    report = {
        "schema": "range002.lookback_affected_issuers.v1",
        "note": "informational: these issuers will be excluded visibly by the universe builder as "
        "INSUFFICIENT_HISTORY; this export changes no universe and removes no row",
        "usable_definition": "close, closeunadj and volume non-null and > 0 on a date in the slice",
        "required_trading_days": need,
        "lookback_calendar_days": cfg["lookback_calendar_days"],
        "decision_days": affected_by_day,
    }
    rp = staging / AFFECTED_FILE
    rp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_license_sidecar(rp)
    report_files = [
        {
            "file": AFFECTED_FILE,
            "byte_sha256": sha256_file(rp),
            "bytes": rp.stat().st_size,
            "license_sidecar": sidecar_path(rp).name,
        }
    ]
    section = {
        "requested_window": {"from": cfg["from"], "to": cfg["to"], "inclusive": True},
        "screen_start": cfg["screen_start"],
        "min_date_present": None if lo is None else str(lo),
        "max_date_present": None if hi is None else str(hi),
        "rows": int(n),
        "distinct_tickers": int(tickers),
        "distinct_trading_dates": int(dates),
        "rows_per_year": per_year,
        "columns_requested": plan["columns_requested"],
        "columns_present": plan["columns"],
        "columns_missing": plan["columns_missing"],
        "price_basis_declared": dict(PRICE_BASIS_DECLARED),
        "price_basis_note": "claims transcribed from vendor documentation; never verified here",
        "provenance_fields_present": [c for c in ("lastupdated",) if c in plan["columns"]],
        "provenance_note": "ingest run ids and dataset_coverage rows are in ingest_identifiers",
        "lookback": {
            "rule": "per month start M: D = last date in sep_daily < M; runner slice "
            "[D - lookback_calendar_days, D] must hold >= required distinct dates by itself",
            "required_trading_days": need,
            "lookback_calendar_days": cfg["lookback_calendar_days"],
            "found_trading_days_min": min(d["distinct_trading_dates_in_slice"] for d in days),
            "decision_days": days,
            "affected_issuers_file": AFFECTED_FILE,
            "affected_issuers_note": report["note"],
            "result": "PASS",
        },
        "limitations": list(SEP_DAILY_LIMITATIONS),
    }
    return section, report_files


# ---------------------------------------------------------------- cleanup
def _known_names(directory: Path) -> set[str]:
    names = set(FIXED_EXTRA_FILES)
    for t in ALL_TABLE_NAMES:
        names.add(f"{t}.parquet")
        names.add(f"{t}.parquet{SIDECAR_SUFFIX}")
    man = directory / MANIFEST_NAME
    if man.is_file():
        try:
            data = json.loads(man.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ExportRefused(f"{str(man)!r} is unreadable: {exc}") from exc
        for f in data.get("files", []):
            if isinstance(f, dict) and isinstance(f.get("file"), str):
                names.add(f["file"])
                names.add(f["file"] + SIDECAR_SUFFIX)
    return names


def plan_cleanup(dest_root: Path, export_id: str) -> list[Path]:
    """Files that cleanup would remove, after every safety check. Raises ExportRefused."""
    _check_id(export_id)
    if not dest_root.is_dir():
        raise ExportRefused(f"--dest-root {str(dest_root)!r} is not an existing directory")
    root_real = dest_root.resolve()
    victims: list[Path] = []
    candidates = [dest_root / export_id, dest_root / f".staging-{export_id}"]
    present = [c for c in candidates if os.path.lexists(c)]
    if not present:
        raise ExportRefused(f"no export or staging directory for {export_id!r} under dest-root")
    for d in present:
        if d.is_symlink() or (hasattr(d, "is_junction") and d.is_junction()):
            raise ExportRefused(f"{str(d)!r} is a symlink/junction; refused")
        if not d.is_dir():
            raise ExportRefused(f"{str(d)!r} is not a directory; refused")
        if d.resolve().parent != root_real:
            raise ExportRefused(f"{str(d)!r} resolves outside dest-root; refused")
        man = d / MANIFEST_NAME
        is_staging = d.name.startswith(".staging-")
        if man.is_file():
            try:
                declared = json.loads(man.read_text(encoding="utf-8")).get("export_id")
            except (OSError, ValueError) as exc:
                raise ExportRefused(f"{str(man)!r} is unreadable: {exc}") from exc
            if declared != export_id:
                raise ExportRefused(
                    f"{str(man)!r} export_id {declared!r} does not match {export_id!r}"
                )
        elif not is_staging:
            raise ExportRefused(f"{str(d)!r} has no manifest; not recognised as an export")
        known = _known_names(d)
        for entry in sorted(d.iterdir()):
            if entry.is_symlink() or (hasattr(entry, "is_junction") and entry.is_junction()):
                raise ExportRefused(f"{str(entry)!r} is a symlink/junction; refused")
            if not entry.is_file():
                raise ExportRefused(f"{str(entry)!r} is not a regular file; unknown content")
            if entry.name not in known:
                raise ExportRefused(
                    f"{str(entry)!r} is not listed in the manifest; unknown content"
                )
            victims.append(entry)
    return victims


def cleanup_export(dest_root: Path, export_id: str, *, apply: bool) -> list[Path]:
    """Dry-run by default. With ``apply`` removes exactly the planned files, then the (now empty)
    export/staging directories. Nothing outside ``<dest-root>/<export-id>`` and
    ``<dest-root>/.staging-<export-id>`` is touched."""
    victims = plan_cleanup(dest_root, export_id)
    if not apply:
        return victims
    dirs: set[Path] = set()
    for v in victims:
        dirs.add(v.parent)
        v.unlink()
    for d in dirs:
        d.rmdir()
    return victims


# ---------------------------------------------------------------- CLI
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--source", help="DuckDB store path (opened read_only)")
    ap.add_argument("--dest-root", help="existing directory (required; no default)")
    ap.add_argument("--export-id")
    ap.add_argument("--purpose")
    ap.add_argument("--executing-identity")
    ap.add_argument("--permission-ref")
    ap.add_argument("--permission-scope")
    ap.add_argument(
        "--no-sep-coverage",
        action="store_true",
        help="omit sep_coverage (default: included; ticker/min/max/count only, no prices)",
    )
    ap.add_argument("--license-status", default="UNKNOWN", choices=LICENSE_STATUSES)
    ap.add_argument("--include-sep-daily", action="store_true")
    ap.add_argument(
        "--sep-date-from", help="YYYY-MM-DD inclusive; required with --include-sep-daily"
    )
    ap.add_argument("--sep-date-to", help="YYYY-MM-DD inclusive; required with --include-sep-daily")
    ap.add_argument("--screen-start", help="YYYY-MM-DD first date of the screening quarter")
    ap.add_argument("--required-lookback-trading-days", type=int)
    ap.add_argument(
        "--max-decision-gap-days",
        type=int,
        help="max calendar days between each decision day D and its month start; required "
        "with --include-sep-daily",
    )
    ap.add_argument(
        "--lookback-calendar-days",
        type=int,
        help="runner slice length: [D - L, D]; required with --include-sep-daily",
    )
    ap.add_argument(
        "--table",
        action="append",
        default=[],
        help="assert a table in scope; out-of-scope (e.g. intraday/minute) names are refused",
    )
    ap.add_argument("--cleanup", metavar="EXPORT_ID", help="dry-run removal of one export")
    ap.add_argument("--apply", action="store_true", help="with --cleanup: really delete")
    ap.add_argument("--verify", metavar="EXPORT_DIR", help="re-validate a published export")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    a = ap.parse_args(argv)
    try:
        if a.verify:
            root = Path(a.verify)
            if not (root / COMPLETE_MARKER).is_file():
                print(f"REFUSED: {COMPLETE_MARKER} missing; export is incomplete")
                return 2
            man = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
            defects = validate_export_dir(root, man)
            for d in defects:
                print("DEFECT:", d)
            print("verify:", "FAILED" if defects else "OK")
            return 1 if defects else 0
        if a.cleanup:
            if not a.dest_root:
                ap.error("--cleanup requires --dest-root")
            victims = cleanup_export(Path(a.dest_root), a.cleanup, apply=a.apply)
            print(("REMOVED" if a.apply else "DRY-RUN (nothing removed); would remove") + ":")
            for v in victims:
                print("  ", v)
            if not a.apply:
                print("re-run with --apply to delete exactly these files")
            return 0
        missing = [
            f"--{n}"
            for n in (
                "source",
                "dest-root",
                "export-id",
                "purpose",
                "executing-identity",
                "permission-ref",
                "permission-scope",
            )  # fmt: skip
            if not getattr(a, n.replace("-", "_"))
        ]
        if missing:
            ap.error("required for export: " + ", ".join(missing))
        final = run_export(
            source=Path(a.source), dest_root=Path(a.dest_root), export_id=a.export_id,
            purpose=a.purpose, executing_identity=a.executing_identity,
            permission_ref=a.permission_ref, permission_scope=a.permission_scope,
            include_sep_coverage=not a.no_sep_coverage,
            include_sep_daily=a.include_sep_daily, sep_date_from=a.sep_date_from,
            sep_date_to=a.sep_date_to, screen_start=a.screen_start,
            required_lookback_trading_days=a.required_lookback_trading_days,
            lookback_calendar_days=a.lookback_calendar_days,
            max_decision_gap_days=a.max_decision_gap_days,
            requested_tables=a.table,
            license_status=a.license_status,
        )  # fmt: skip
        print(f"published: {final}")
        return 0
    except ExportRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    except (duckdb.Error, OSError) as exc:
        print(
            f"FAILED: {exc!r} (staging directory, if any, left in place and unpublished)",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
