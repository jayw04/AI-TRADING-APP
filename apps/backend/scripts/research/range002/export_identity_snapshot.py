#!/usr/bin/env python3
"""RANGE-002 S1: bounded Sharadar IDENTITY DIAGNOSTIC export (stdlib + duckdb only).

    python -I export_identity_snapshot.py --source <store.duckdb> --dest-root <existing dir> \\
        --export-id <id> --purpose "<text>" --executing-identity "<name or role>" \\
        --permission-ref "<record of the permission basis claimed>" \\
        --permission-scope "<scope that record is claimed to cover; name the tables>" \\
        [--no-sep-coverage] [--license-status UNKNOWN|PERSONAL|COMMERCIAL_OK]

    python -I export_identity_snapshot.py --cleanup <export-id> --dest-root <dir> [--apply]
    python -I export_identity_snapshot.py --verify <export dir>

What it is. A diagnostic of whether an existing factor store holds usable issuer identities, ticker
history and corporate-action records. It is NOT a strategy-performance dataset: no price or volume
column is ever selected (the optional ``sep_coverage`` is a per-ticker min/max date and row count).

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
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

SCRIPT_VERSION = "1.0.0"
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
)

#: Never exported, in any file. A guard on the delivered columns, not on the request.
FORBIDDEN_COLUMNS = frozenset(
    {"open", "high", "low", "close", "volume", "closeadj", "closeunadj", "adj_close", "price"}
)

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
SEP_COVERAGE_COLUMNS = ("ticker", "min_date", "max_date", "n_rows")
ALL_TABLE_NAMES = tuple(t[0] for t in TABLE_SPECS) + ("sep_coverage",)
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


def canonical_rows_digest(columns: list[str], types: list[str], rows: list[tuple[Any, ...]]) -> str:
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


def order_by_clause(columns: list[str]) -> str:
    return "ORDER BY " + ", ".join(f"{qi(c)} ASC NULLS FIRST" for c in columns)


def read_parquet_summary(
    path: Path, columns: list[str], date_columns: list[str]
) -> tuple[int, dict[str, dict[str, str | None]], str]:
    con = duckdb.connect(":memory:")
    try:
        src = "read_parquet('" + path.as_posix().replace("'", "''") + "')"
        sel = ", ".join(qi(c) for c in columns)
        order = order_by_clause(columns)
        rows = con.execute(f"SELECT {sel} FROM {src} {order}").fetchall()
        desc = {
            str(r[0]): str(r[1])
            for r in con.execute(f"DESCRIBE SELECT {sel} FROM {src}").fetchall()
        }
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
    return len(rows), bounds, canonical_rows_digest(columns, [desc[c] for c in columns], rows)


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
            bad = FORBIDDEN_COLUMNS & {str(c).lower() for c in f.get("columns", [])}
            if bad:
                defects.append(f"file {f.get('table')!r}: forbidden column(s) {sorted(bad)}")
            if (
                f.get("table") == "sep_coverage"
                and tuple(f.get("columns", ())) != SEP_COVERAGE_COLUMNS
            ):
                defects.append("sep_coverage columns are not exactly the coverage columns")
    return defects


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
    schema: dict[str, dict[str, str]], include_sep_coverage: bool
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
    return plans, not_exported


def _check_id(export_id: str) -> None:
    if not EXPORT_ID_RE.match(export_id):
        raise ExportRefused(f"export id {export_id!r} must match {EXPORT_ID_RE.pattern}")


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
            permission_scope=permission_scope, include_sep_coverage=include_sep_coverage, license_status=license_status,
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
) -> None:
    con = duckdb.connect(str(source), read_only=True)
    try:
        con.execute("BEGIN TRANSACTION")
        extraction_time = utc_now()
        schema = _introspect(con)
        plans, not_exported = plan_queries(schema, include_sep_coverage)
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
                "byte_sha256": sha256_file(path),
                "logical_sha256": logical,
                "bytes": path.stat().st_size,
                "license_sidecar": sidecar_path(path).name,
            }
        )
        write_license_sidecar(path)
    queries = {p["table"]: p["select"] for p in plans}
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
        "Internal identity diagnostics only. Not for presentation, redistribution or any external "
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
                "completed_utc": utc_now(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


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
