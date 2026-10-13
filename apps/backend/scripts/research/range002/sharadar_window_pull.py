#!/usr/bin/env python3
"""RANGE-002 S1b: bounded Sharadar retrieval for 2016-Q1 screening (read-only HTTP GETs).

    python -I sharadar_window_pull.py --dest-root <existing dir> --export-id <id> \\
        --purpose "<text>" --executing-identity "<name or role>" \\
        --permission-ref "<record of the permission basis claimed>" \\
        --permission-scope "<scope that record is claimed to cover; name the tables>" \\
        --sep-date-from YYYY-MM-DD --sep-date-to YYYY-MM-DD --max-pages N [--dry-plan]

Retrieves, through the Nasdaq Data Link v3 datatables API (the same endpoints and ``cursor_id``
pagination as ``app/factor_data/providers/sharadar.py``):

  tickers.parquet   SHARADAR/TICKERS  full table, every ``table`` value, every column returned, NO filter
  actions.parquet   SHARADAR/ACTIONS  full table, all dates, every column returned
  sep.parquet       SHARADAR/SEP      all tickers, ``date`` in [--sep-date-from, --sep-date-to] inclusive

Discipline (mirrors ``export_identity_snapshot.py``).
* The API key is read ONLY from the environment variable ``NASDAQ_DATA_LINK_API_KEY`` (the variable
  ``app.config.Settings`` aliases). It is never taken from argv, never written to the manifest, a
  marker, a log line or an exception text (every message passes through ``redact``); the only thing
  reported about it is that it is present. The API accepts the key as a query parameter (as the
  repository provider does), so exceptions raised by the HTTP library, which embed the URL, are
  never propagated: they are re-raised as ``PullError`` with the key scrubbed.
* Only GET requests are issued. Pagination follows ``meta.next_cursor_id``. Transport errors, 429
  and 5xx are retried with bounded exponential backoff; other 4xx fail fast.
* ``--max-pages`` is a REQUIRED per-table safety cap: a table whose cursor is still open after that
  many pages fails the whole pull closed (nothing is published).
* Output is staged in ``<dest-root>/.staging-<export-id>/`` and published with one directory
  rename to ``<dest-root>/<export-id>/``. ``EXPORT_COMPLETE.json`` is written last inside staging.
  An existing export or staging directory is never overwritten. A failed pull leaves only the
  staging directory (with ``EXPORT_FAILED.json``) and is never published.
* Every file and the manifest get a PU-1 ``<file>.license.json`` sidecar (sources ["sharadar"],
  registry scope UNKNOWN), so the external-use seam refuses them. ``--permission-ref`` and
  ``--permission-scope`` are recorded verbatim with ``permission_verified: false``; this tool does
  not and cannot verify permission. License status is fixed at UNKNOWN.
* The TICKERS feasibility block in the manifest is informational. It does NOT assert that issuer
  identity is reconstructed.
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
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import httpx
import pyarrow as pa

SCRIPT_VERSION = "1.0.0"
MANIFEST_SCHEMA_VERSION = "range002.sharadar_window_pull_manifest.v1"
KEY_ENV = "NASDAQ_DATA_LINK_API_KEY"
NDL_BASE = "https://data.nasdaq.com/api/v3/datatables/SHARADAR"
SIDECAR_SUFFIX = ".license.json"
LICENSE_SOURCES = ["sharadar"]
LICENSE_SCOPE = "UNKNOWN"
LICENSE_STATUS = "UNKNOWN"
EXPORT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
COMPLETE_MARKER = "EXPORT_COMPLETE.json"
FAILED_MARKER = "EXPORT_FAILED.json"
MANIFEST_NAME = "manifest.json"
README_NAME = "README_PU1.txt"

MAX_RETRIES = 4
RETRY_BACKOFF_BASE_S = 1.0
RETRYABLE_STATUS_LIMIT = 600
DEFAULT_PAGE_DELAY_S = 0.25
DEFAULT_TIMEOUT_S = 60.0
ERROR_BODY_CHARS = 200

#: (table name in the URL, parquet stem). Parquet stems match ``pit_coverage_ro`` view names.
TABLES: tuple[tuple[str, str], ...] = (
    ("TICKERS", "tickers"),
    ("ACTIONS", "actions"),
    ("SEP", "sep"),
)
SEP_COLUMNS = (
    "ticker", "date", "open", "high", "low", "close", "volume", "closeadj", "closeunadj",
    "lastupdated",
)  # fmt: skip
REQUIRED_MANIFEST_FIELDS = (
    "schema_version", "export_id", "source", "requests", "extraction_started_utc",
    "extraction_finished_utc", "executing_identity", "purpose", "tool_version", "script_sha256",
    "files", "license_status", "permission_basis_claimed", "permission_verified",
    "destination_path", "pages", "vendor_lastupdated_bounds", "tickers_feasibility",
)  # fmt: skip
REQUIRED_FILE_FIELDS = (
    "table", "file", "rows", "date_bounds", "columns", "byte_sha256", "logical_sha256",
)  # fmt: skip


class PullError(Exception):
    """A precondition or the retrieval failed; nothing was published. Messages are key-free."""


# ---------------------------------------------------------------- key hygiene
_KEY_PARAM_RE = re.compile(r"(api_key=)[^&\s'\"]+", re.IGNORECASE)


def redact(text: str, key: str | None = None) -> str:
    """Scrub the key value and any ``api_key=`` query parameter from ``text``."""
    out = _KEY_PARAM_RE.sub(r"\1***", text)
    if key:
        out = out.replace(key, "***")
    return out


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


def qi(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


# ---------------------------------------------------------------- licensing sidecar
def sidecar_path(artifact: Path) -> Path:
    return artifact.with_name(artifact.name + SIDECAR_SUFFIX)


def write_license_sidecar(artifact: Path) -> dict[str, Any]:
    """Same JSON shape and bytes as ``app.licensing.envelope.write_sidecar`` (a test asserts it)."""
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
# Copied from export_identity_snapshot.py (same canonical form: header [[name,type],..] then one
# compact JSON array per row ordered by all columns ASC NULLS FIRST). That script is not importable
# from this tree, so the minimum is duplicated here.
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


# ---------------------------------------------------------------- request plan
@dataclass(frozen=True)
class TableRequest:
    table: str  # URL name, e.g. SEP
    stem: str  # parquet stem, e.g. sep
    filters: dict[str, str] = field(default_factory=dict)  # never includes the key
    per_page: int | None = None

    @property
    def url(self) -> str:
        return f"{NDL_BASE}/{self.table}.json"

    def params(self) -> dict[str, str]:
        out = dict(self.filters)
        if self.per_page is not None:
            out["qopts.per_page"] = str(self.per_page)
        return out


def parse_date(label: str, val: str) -> date:
    if not DATE_RE.match(val):
        raise PullError(f"--{label} must be YYYY-MM-DD")
    try:
        return date.fromisoformat(val)
    except ValueError as exc:
        raise PullError(f"--{label} is not a valid date: {val}") from exc


def build_plan(sep_from: str, sep_to: str, per_page: int | None = None) -> list[TableRequest]:
    d_from, d_to = parse_date("sep-date-from", sep_from), parse_date("sep-date-to", sep_to)
    if d_from > d_to:
        raise PullError("--sep-date-from must be <= --sep-date-to")
    if per_page is not None and not 1 <= per_page <= 10_000:
        raise PullError("--per-page must be in 1..10000")
    sep_filters = {"date.gte": str(d_from), "date.lte": str(d_to)}
    return [
        TableRequest("TICKERS", "tickers", {}, per_page),
        TableRequest("ACTIONS", "actions", {}, per_page),
        TableRequest("SEP", "sep", sep_filters, per_page),
    ]


def render_plan(plan: list[TableRequest], max_pages: int) -> str:
    lines = ["DRY PLAN: no network call is made, nothing is written."]
    for r in plan:
        q = "&".join(f"{k}={v}" for k, v in {**r.params(), "api_key": "***REDACTED***"}.items())
        lines.append(f"GET {r.url}?{q}")
        lines.append(
            "    then repeat with qopts.cursor_id=<meta.next_cursor_id> until it is empty "
            f"(expected pages: unknown; cap {max_pages} pages for this table)"
        )
        ps = "vendor default" if r.per_page is None else str(r.per_page)
        lines.append(
            f"    page size: {ps} rows/page (explicit qopts.per_page only if --per-page given)"
        )
    lines.append(
        f"retries per request: {MAX_RETRIES}, backoff base {RETRY_BACKOFF_BASE_S}s doubling"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------- HTTP
_sleep: Callable[[float], None] = time.sleep  # patched in tests


def make_client(
    transport: httpx.BaseTransport | None, timeout: float = DEFAULT_TIMEOUT_S
) -> httpx.Client:
    if transport is None and os.environ.get("WORKBENCH_TLS_USE_OS_TRUST", "1") != "0":
        try:  # same OS-trust-store injection as app.utils.tls_trust (ADR 0017); never fatal
            import truststore

            truststore.inject_into_ssl()
        except Exception:  # noqa: BLE001
            pass
    return httpx.Client(follow_redirects=True, timeout=timeout, transport=transport)


def get_json_with_retry(
    client: httpx.Client, url: str, params: dict[str, str], *, key: str, table: str
) -> dict[str, Any]:
    """GET with bounded retry. Any failure is re-raised as a key-free ``PullError``."""
    last = "unknown error"
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = client.get(url, params=params)
        except httpx.TransportError as exc:
            last = f"transport error {type(exc).__name__}"
        else:
            status = resp.status_code
            if status == 200:
                try:
                    payload = resp.json()
                except ValueError:
                    raise PullError(f"{table}: response is not JSON") from None
                if not isinstance(payload, dict):
                    raise PullError(f"{table}: response JSON is not an object")
                return payload
            body = redact(resp.text[:ERROR_BODY_CHARS], key)
            last = f"HTTP {status}: {body}"
            if not (status == 429 or 500 <= status < RETRYABLE_STATUS_LIMIT):
                raise PullError(f"{table}: non-retryable {last}")
        if attempt >= MAX_RETRIES:
            break
        _sleep(RETRY_BACKOFF_BASE_S * (2**attempt))
    raise PullError(f"{table}: failed after {MAX_RETRIES + 1} attempts ({redact(last, key)})")


@dataclass
class FetchedTable:
    request: TableRequest
    columns: list[str]
    api_types: list[str]
    data: dict[str, list[Any]]
    pages: int
    rows: int
    cursors_seen: int


def fetch_table(
    client: httpx.Client,
    req: TableRequest,
    *,
    key: str,
    max_pages: int,
    page_delay_s: float,
) -> FetchedTable:
    columns: list[str] | None = None
    api_types: list[str] = []
    data: dict[str, list[Any]] = {}
    cursor: str | None = None
    seen: set[str] = set()
    pages = rows = 0
    while True:
        if pages >= max_pages:
            raise PullError(
                f"{req.table}: --max-pages cap {max_pages} reached with the cursor still open; "
                "nothing published (raise the cap deliberately if the table is larger)"
            )
        params = req.params()
        params["api_key"] = key
        if cursor:
            params["qopts.cursor_id"] = cursor
        payload = get_json_with_retry(client, req.url, params, key=key, table=req.table)
        dt = payload.get("datatable")
        if not isinstance(dt, dict) or "columns" not in dt or "data" not in dt:
            raise PullError(f"{req.table}: response lacks datatable.columns/data")
        names = [str(c["name"]) for c in dt["columns"]]
        if columns is None:
            columns = names
            api_types = [str(c.get("type", "")) for c in dt["columns"]]
            data = {c: [] for c in columns}
        elif names != columns:
            raise PullError(f"{req.table}: column list changed between pages")
        for row in dt["data"]:
            if len(row) != len(columns):
                raise PullError(f"{req.table}: row width {len(row)} != {len(columns)} columns")
            for c, v in zip(columns, row, strict=True):
                data[c].append(v)
        rows += len(dt["data"])
        pages += 1
        meta = payload.get("meta") or {}
        nxt = meta.get("next_cursor_id") if isinstance(meta, dict) else None
        if not nxt:
            break
        if str(nxt) in seen:
            raise PullError(f"{req.table}: cursor repeated; refusing a looping pull")
        seen.add(str(nxt))
        cursor = str(nxt)
        if page_delay_s > 0:
            _sleep(page_delay_s)
    assert columns is not None
    if rows == 0:
        raise PullError(f"{req.table}: zero rows returned; refusing an empty extract")
    return FetchedTable(req, columns, api_types, data, pages, rows, len(seen))


# ---------------------------------------------------------------- typing and parquet
def sql_type_for(api_type: str) -> str:
    t = api_type.strip().lower()
    if t.startswith(("datetime", "timestamp")):
        return "TIMESTAMP"
    if t.startswith("date"):
        return "DATE"
    if t.startswith(("integer", "int", "bigint", "long")):
        return "BIGINT"
    if t.startswith(("bigdecimal", "decimal", "double", "float", "real", "number", "numeric")):
        return "DOUBLE"
    return "VARCHAR"


def _as_text(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return "true" if v else "false"
    return v if isinstance(v, str) else repr(v) if isinstance(v, float) else str(v)


def write_parquet(ft: FetchedTable, dest: Path) -> dict[str, str]:
    """Typed, deterministic (ORDER BY all columns) Parquet via DuckDB. Cell values travel as text
    and are CAST strictly (a malformed value fails the pull). Returns column -> SQL type."""
    types = {c: sql_type_for(t) for c, t in zip(ft.columns, ft.api_types, strict=True)}
    arrow = pa.table(
        {c: pa.array([_as_text(v) for v in ft.data[c]], type=pa.string()) for c in ft.columns}
    )
    con = duckdb.connect(":memory:")
    try:
        con.register("raw_page", arrow)
        sel = ", ".join(f"CAST({qi(c)} AS {types[c]}) AS {qi(c)}" for c in ft.columns)
        con.execute(f"CREATE TABLE typed AS SELECT {sel} FROM raw_page")
        target = dest.as_posix().replace("'", "''")
        con.execute(
            f"COPY (SELECT * FROM typed {order_by_clause(ft.columns)}) TO '{target}' "
            "(FORMAT PARQUET)"
        )
    finally:
        con.close()
    return types


# ---------------------------------------------------------------- feasibility (informational)
def tickers_feasibility(path: Path) -> dict[str, Any]:
    con = duckdb.connect(":memory:")
    try:
        src = "read_parquet('" + path.as_posix().replace("'", "''") + "')"
        cols = {
            str(r[0]).lower(): str(r[0])
            for r in con.execute(f"DESCRIBE SELECT * FROM {src}").fetchall()
        }
        n = int(con.execute(f"SELECT COUNT(*) FROM {src}").fetchone()[0])  # type: ignore[index]
        out: dict[str, Any] = {
            "note": "informational only; identity is NOT asserted to be reconstructed",
            "rows": n,
            "columns_present": sorted(cols.values()),
        }
        perm, tick = cols.get("permaticker"), cols.get("ticker")
        if perm and tick:
            q = con.execute(
                f"SELECT COUNT(DISTINCT {qi(perm)}), COUNT(DISTINCT {qi(tick)}) FROM {src}"
            ).fetchone()
            out["distinct_permaticker"], out["distinct_ticker"] = int(q[0]), int(q[1])  # type: ignore[index]
            out["tickers_under_more_than_one_permaticker"] = int(
                con.execute(
                    f"SELECT COUNT(*) FROM (SELECT {qi(tick)} FROM {src} GROUP BY {qi(tick)} "
                    f"HAVING COUNT(DISTINCT {qi(perm)}) > 1)"
                ).fetchone()[0]  # type: ignore[index]
            )
            out["permatickers_with_more_than_one_ticker"] = int(
                con.execute(
                    f"SELECT COUNT(*) FROM (SELECT {qi(perm)} FROM {src} GROUP BY {qi(perm)} "
                    f"HAVING COUNT(DISTINCT {qi(tick)}) > 1)"
                ).fetchone()[0]  # type: ignore[index]
            )
        else:
            out["identity_counts"] = "unavailable: permaticker/ticker column absent"
        tbl = cols.get("table")
        if tbl:
            out["rows_by_table"] = {
                str(k): int(v)
                for k, v in con.execute(
                    f"SELECT {qi(tbl)}, COUNT(*) FROM {src} GROUP BY 1 ORDER BY 1"
                ).fetchall()
            }
        else:
            out["rows_by_table"] = "unavailable: table column absent"
        fp, lp = cols.get("firstpricedate"), cols.get("lastpricedate")
        if fp and lp:
            q2 = con.execute(
                f"SELECT COUNT(*) FILTER (WHERE {qi(fp)} IS NOT NULL), "
                f"COUNT(*) FILTER (WHERE {qi(lp)} IS NOT NULL), "
                f"COUNT(*) FILTER (WHERE {qi(fp)} IS NOT NULL AND {qi(lp)} IS NOT NULL) FROM {src}"
            ).fetchone()
            out["per_row_price_date_interval"] = {
                "columns_present": True,
                "rows_with_firstpricedate": int(q2[0]),  # type: ignore[index]
                "rows_with_lastpricedate": int(q2[1]),  # type: ignore[index]
                "rows_with_both": int(q2[2]),  # type: ignore[index]
                "rows_total": n,
            }
        else:
            out["per_row_price_date_interval"] = {"columns_present": False}
    finally:
        con.close()
    return out


# ---------------------------------------------------------------- manifest validation
def column_defects(table: Any, columns: Any) -> list[str]:
    cols = [str(c) for c in columns]
    if table == "sep":
        missing = [c for c in SEP_COLUMNS if c not in cols]
        return [f"file 'sep': requested column(s) missing {missing}"] if missing else []
    return []


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    defects: list[str] = []
    for key in REQUIRED_MANIFEST_FIELDS:
        if key not in manifest:
            defects.append(f"missing field {key!r}")
        elif manifest[key] in (None, "", [], {}):
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
    if manifest.get("license_status") != LICENSE_STATUS:
        defects.append(f"license_status must be {LICENSE_STATUS}")
    files = manifest.get("files")
    if isinstance(files, list):
        names = [f.get("table") for f in files if isinstance(f, dict)]
        for _, stem in TABLES:
            if stem not in names:
                defects.append(f"files lacks required table {stem!r}")
        for f in files:
            if not isinstance(f, dict):
                defects.append("file entry is not an object")
                continue
            for key in REQUIRED_FILE_FIELDS:
                if key not in f or f[key] in (None, "", []):
                    if key == "date_bounds" and f.get(key) == {}:
                        continue
                    defects.append(f"file {f.get('table')!r}: missing/empty {key!r}")
            defects.extend(column_defects(f.get("table"), f.get("columns", [])))
    blob = json.dumps(manifest)
    if re.search(r"api_key=(?!\*\*\*)", blob):
        defects.append("manifest contains an api_key query parameter")
    return defects


def validate_export_dir(root: Path, manifest: dict[str, Any]) -> list[str]:
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
        if not sidecar_path(p).is_file():
            defects.append(f"file {f['file']!r}: license sidecar missing")
    return defects


# ---------------------------------------------------------------- pull
def run_pull(
    *,
    dest_root: Path,
    export_id: str,
    purpose: str,
    executing_identity: str,
    permission_ref: str,
    permission_scope: str,
    sep_date_from: str,
    sep_date_to: str,
    max_pages: int,
    per_page: int | None = None,
    page_delay_s: float = DEFAULT_PAGE_DELAY_S,
    transport: httpx.BaseTransport | None = None,
    api_key: str | None = None,
) -> Path:
    for label, val in (
        ("purpose", purpose),
        ("executing-identity", executing_identity),
        ("permission-ref", permission_ref),
        ("permission-scope", permission_scope),
    ):
        if not val or not val.strip():
            raise PullError(f"--{label} is required and must not be empty")
    if not EXPORT_ID_RE.match(export_id):
        raise PullError(f"export id {export_id!r} must match {EXPORT_ID_RE.pattern}")
    if isinstance(max_pages, bool) or max_pages < 1:
        raise PullError("--max-pages must be an integer >= 1")
    plan = build_plan(sep_date_from, sep_date_to, per_page)
    if not dest_root.is_dir():
        raise PullError(f"--dest-root {str(dest_root)!r} is not an existing directory")
    final = dest_root / export_id
    staging = dest_root / f".staging-{export_id}"
    if os.path.lexists(final):
        raise PullError(f"export {str(final)!r} already exists; never overwritten")
    if os.path.lexists(staging):
        raise PullError(f"staging {str(staging)!r} already exists; never overwritten")
    key = api_key if api_key is not None else os.environ.get(KEY_ENV, "")
    if not key:
        raise PullError(f"{KEY_ENV} is not set in the environment; nothing was requested")

    staging.mkdir()
    try:
        _pull_into_staging(
            plan=plan, staging=staging, final=final, key=key, export_id=export_id,
            purpose=purpose, executing_identity=executing_identity,
            permission_ref=permission_ref, permission_scope=permission_scope,
            sep_from=sep_date_from, sep_to=sep_date_to, max_pages=max_pages,
            page_delay_s=page_delay_s, transport=transport,
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
                json.dumps(
                    {
                        "export_id": export_id,
                        "failed_utc": utc_now(),
                        "error": redact(f"{type(exc).__name__}: {exc}", key),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (staging / COMPLETE_MARKER).unlink(missing_ok=True)
        except OSError:
            pass
        if isinstance(exc, PullError | KeyboardInterrupt | SystemExit):
            raise
        raise PullError(redact(f"{type(exc).__name__}: {exc}", key)) from None
    return final


def _pull_into_staging(
    *,
    plan: list[TableRequest],
    staging: Path,
    final: Path,
    key: str,
    export_id: str,
    purpose: str,
    executing_identity: str,
    permission_ref: str,
    permission_scope: str,
    sep_from: str,
    sep_to: str,
    max_pages: int,
    page_delay_s: float,
    transport: httpx.BaseTransport | None,
) -> None:
    started = utc_now()
    files: list[dict[str, Any]] = []
    pages: dict[str, int] = {}
    requests_rec: dict[str, Any] = {}
    lastupdated: dict[str, Any] = {}
    feasibility: dict[str, Any] = {}
    client = make_client(transport)
    try:
        for req in plan:
            ft = fetch_table(client, req, key=key, max_pages=max_pages, page_delay_s=page_delay_s)
            if req.stem == "sep":
                missing = [c for c in SEP_COLUMNS if c not in ft.columns]
                if missing:
                    raise PullError(f"SEP response lacks requested column(s) {missing}")
            path = staging / f"{req.stem}.parquet"
            types = write_parquet(ft, path)
            ft.data = {}  # release memory before the next table
            date_cols = [c for c in ft.columns if types[c] in ("DATE", "TIMESTAMP")]
            rows, bounds, logical = read_parquet_summary(path, ft.columns, date_cols)
            if rows != ft.rows:
                raise PullError(f"{req.table}: parquet rows {rows} != fetched rows {ft.rows}")
            if req.stem == "sep":
                dmin, dmax = bounds.get("date", {}).get("min"), bounds.get("date", {}).get("max")
                if dmin is None or dmax is None or dmin < sep_from or dmax > sep_to:
                    raise PullError(
                        f"SEP rows lie outside the requested window [{sep_from}, {sep_to}]: "
                        f"present [{dmin}, {dmax}]"
                    )
            if "lastupdated" in bounds:
                lastupdated[req.stem] = bounds["lastupdated"]
            if req.stem == "tickers":
                feasibility = tickers_feasibility(path)
            pages[req.stem] = ft.pages
            requests_rec[req.stem] = {
                "endpoint": req.url,
                "method": "GET",
                "params": req.params(),
                "cursor_param": "qopts.cursor_id",
                "page_size": "vendor default" if req.per_page is None else req.per_page,
                "max_pages_cap": max_pages,
            }
            extra = [c for c in ft.columns if c not in SEP_COLUMNS] if req.stem == "sep" else []
            files.append(
                {
                    "table": req.stem,
                    "vendor_table": f"SHARADAR/{req.table}",
                    "file": path.name,
                    "rows": rows,
                    "date_bounds": bounds,
                    "columns": ft.columns,
                    "api_column_types": dict(zip(ft.columns, ft.api_types, strict=True)),
                    "parquet_column_types": types,
                    "columns_extra_vs_requested": extra,
                    "byte_sha256": sha256_file(path),
                    "logical_sha256": logical,
                    "bytes": path.stat().st_size,
                    "pages": ft.pages,
                    "license_sidecar": sidecar_path(path).name,
                }
            )
            write_license_sidecar(path)
    finally:
        client.close()
    finished = utc_now()
    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "export_id": export_id,
        "source": {
            "system": "Nasdaq Data Link datatables API v3, SHARADAR (read-only GET)",
            "endpoints": [r.url for r in plan],
            "key": f"read from environment variable {KEY_ENV}; value never recorded",
        },
        "requests": requests_rec,
        "pages": pages,
        "extraction_started_utc": started,
        "extraction_finished_utc": finished,
        "executing_identity": executing_identity,
        "purpose": purpose,
        "tool_version": SCRIPT_VERSION,
        "script_sha256": sha256_file(Path(__file__)),
        "python_version": platform.python_version(),
        "duckdb_version": duckdb.__version__,
        "httpx_version": httpx.__version__,
        "pyarrow_version": pa.__version__,
        "files": files,
        "requested_sep_window": {"from": sep_from, "to": sep_to, "inclusive": True},
        "vendor_lastupdated_bounds": lastupdated or {"value": "unavailable"},
        "tickers_feasibility": feasibility,
        "typing_note": "API types are mapped Date->DATE, Integer->BIGINT, BigDecimal/double->DOUBLE "
        "(precision beyond IEEE double is not preserved), everything else VARCHAR; values are "
        "CAST strictly so a malformed value fails the pull",
        "limitations": [
            "lastupdated is a vendor revision date, not an as-of timestamp; rows may include later "
            "revisions (bounds reported, nothing filtered)",
            "TICKERS is as delivered by the API now; this tool does not reconstruct issuer history",
            "SEP is daily only; no intraday/SIP data",
            "date filter semantics (date.gte/date.lte inclusive) are the vendor API's; the delivered "
            "min/max date is checked against the window and reported",
        ],
        "license_status": LICENSE_STATUS,
        "license_note": "classification is not permission; the sidecars carry scope "
        f"{LICENSE_SCOPE} for sources {LICENSE_SOURCES}",
        "permission_basis_claimed": {
            "ref": permission_ref,
            "scope": permission_scope,
            "tables_named_in_scope": sorted(
                f["table"] for f in files if f["table"] in permission_scope.lower()
            ),
            "tables_not_named_in_scope": sorted(
                f["table"] for f in files if f["table"] not in permission_scope.lower()
            ),
        },
        "permission_verified": False,
        "permission_note": "operator-supplied text recorded verbatim; this script does not and "
        "cannot verify permission, and a non-empty string is not verified permission",
        "destination_path": str(final),
        "marker": COMPLETE_MARKER,
    }
    defects = validate_manifest(manifest)
    if defects:
        raise PullError("manifest validation failed: " + "; ".join(defects))
    man_path = staging / MANIFEST_NAME
    man_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_license_sidecar(man_path)
    (staging / README_NAME).write_text(
        "PU-1 NOTICE\n"
        f"License status recorded: {LICENSE_STATUS} (Sharadar registry scope UNKNOWN).\n"
        "Internal screening inputs only. Not for presentation, redistribution or any external "
        "use. A label or sidecar does not establish permission to share.\n"
        f"Consumers must require {COMPLETE_MARKER}; a directory without it is incomplete.\n",
        encoding="utf-8",
    )
    again = validate_export_dir(staging, json.loads(man_path.read_text(encoding="utf-8")))
    if again:
        raise PullError("post-write validation failed: " + "; ".join(again))
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


# ---------------------------------------------------------------- CLI
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Bounded read-only Sharadar retrieval (TICKERS, ACTIONS, SEP window)."
    )
    p.add_argument("--dest-root", required=True, type=Path)
    p.add_argument("--export-id", required=True)
    p.add_argument("--purpose", required=True)
    p.add_argument("--executing-identity", required=True)
    p.add_argument("--permission-ref", required=True)
    p.add_argument("--permission-scope", required=True)
    p.add_argument("--sep-date-from", required=True, help="YYYY-MM-DD inclusive")
    p.add_argument("--sep-date-to", required=True, help="YYYY-MM-DD inclusive")
    p.add_argument("--max-pages", required=True, type=int, help="per-table page cap (fail closed)")
    p.add_argument("--per-page", type=int, default=None, help="explicit qopts.per_page (optional)")
    p.add_argument("--page-delay-s", type=float, default=DEFAULT_PAGE_DELAY_S)
    p.add_argument("--dry-plan", action="store_true", help="print requests; no network, no write")
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    try:
        if a.dry_plan:
            if not EXPORT_ID_RE.match(a.export_id):
                raise PullError(f"export id {a.export_id!r} must match {EXPORT_ID_RE.pattern}")
            if a.max_pages < 1:
                raise PullError("--max-pages must be an integer >= 1")
            print(render_plan(build_plan(a.sep_date_from, a.sep_date_to, a.per_page), a.max_pages))
            print(f"destination (not created): {a.dest_root / a.export_id}")
            present = "present" if os.environ.get(KEY_ENV) else "NOT present"
            print(f"{KEY_ENV}: {present} in the environment (value never printed)")
            return 0
        final = run_pull(
            dest_root=a.dest_root, export_id=a.export_id, purpose=a.purpose,
            executing_identity=a.executing_identity, permission_ref=a.permission_ref,
            permission_scope=a.permission_scope, sep_date_from=a.sep_date_from,
            sep_date_to=a.sep_date_to, max_pages=a.max_pages, per_page=a.per_page,
            page_delay_s=a.page_delay_s,
        )  # fmt: skip
    except PullError as exc:
        print(f"REFUSED: {redact(str(exc), os.environ.get(KEY_ENV))}", file=sys.stderr)
        return 2
    print(f"PUBLISHED: {final}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
