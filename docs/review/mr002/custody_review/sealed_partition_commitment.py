"""WP-C — the custodian sealing-process producer for P9 and P6.

Authorized by the owner on 2026-08-10
(``docs/review/mr002/MR002_PrerequisiteProduction_Authorization_v1.0.json``,
Execution Order Step 3, WP-C) and sequenced by the owner direction of
2026-08-11 (``docs/review/mr002/MR002_ExecutionSequencing_Direction_v1.0.json``,
D-S2), which also records that the owner authorized the operational custodian to
execute this producer directly.

Produces two runtime instances:

  * **P9** ``MR002_ValidationStructuralManifest`` -- the precommitted
    value-blind structural manifest. Register title: "Precommitted value-blind
    structural manifest for the validation partition". Produced BEFORE sealing,
    which is why it is produced now, before the sealed store exists.
  * **P6** ``ValidationPartitionContentCommitment`` -- SHA-256 over canonical
    (sorted) partition content.

===============================================================================
CLASSIFICATION -- VALUE-BLIND
===============================================================================

This producer emits ONLY the fields ``ValidationStructuralManifestSpecification
_v1.0.json`` enumerates as value-blind: schema identity, table names, row
counts, date bounds, session count, symbol/security counts, factor-series
coverage, null-count summaries, latest source date -- plus content hashes.

It never emits, prints, returns, or logs a row value. Row content reaches
memory only inside :func:`_hash_partition`, where it is folded into a SHA-256
and discarded. No returns, prices, signals, scores, or P&L are computed. This
is not an unsealing of economic data.

The specification permits these reads ONLY for the sealing/custodian process
and NEVER as a direct developer query. The distinction is not the SQL, it is
the producer: a fixed, reviewed, audit-bound procedure run under the
operational-custodian appointment, not ad-hoc interrogation. The emitted
records carry the custodian identity and the access event so a reviewer can
check that claim rather than take it.

===============================================================================
WHY THE CANONICAL FORM IS BUILT THE WAY IT IS
===============================================================================

The commitment is worthless unless it recomputes identically inside the bound
evaluator image months from now, on different hardware, under a different
DuckDB build. Four things would otherwise drift silently:

1. **Row order.** Unordered SQL has no order. Every partition is read
   ``ORDER BY ALL`` with the null ordering pinned explicitly, so ties cannot
   reorder between runs.
2. **Float formatting.** ``str(float)`` is not a stable contract. Floats are
   encoded ``.17g``, which round-trips IEEE-754 doubles exactly, with NaN and
   the infinities spelled out rather than left to the platform.
3. **Time zone.** DuckDB renders ``TIMESTAMP WITH TIME ZONE`` in the session
   time zone, which is a property of the HOST. The session is pinned to UTC
   before any read; otherwise the same corpus commits to different hashes on a
   Chicago laptop and a UTC container.
4. **Field delimiters.** Any separator character can occur inside a VARCHAR.
   Fields are length-prefixed instead of delimited, so the encoding is
   injective and no value can forge a row boundary.

===============================================================================
FAIL-CLOSED
===============================================================================

The snapshot digest is verified BEFORE the connection opens and again AFTER it
closes. A mismatch in either direction raises; there is no partial emission and
no "warn and continue". A drifted corpus is not a degraded input, it is a
different corpus, and a commitment over it would be a false precommitment.

Declared window session counts are likewise asserted against the frozen design.
If the observed session count for a window does not equal the frozen figure,
this refuses rather than committing to whatever it found.

===============================================================================
SCOPE
===============================================================================

Opens the registered snapshot READ-ONLY. Writes nothing to it, releases no
credentials, grants no execution authority, and does not touch
``validation_authorization``. Producing these records satisfies prerequisites;
it does not open the validation partition for research use.
"""

from __future__ import annotations

import argparse
import datetime
import decimal
import hashlib
import json
import sys
from contextlib import contextmanager

import duckdb

# --------------------------------------------------------------------------------------
# Frozen bindings -- transcribed from the sealed manifest section_8a_frozen_window and
# prereg v1.0.4 windows_literal. These are declarations to be CHECKED, never inferred.
# --------------------------------------------------------------------------------------

SNAPSHOT = "apps/backend/data/mr002_research.duckdb"
SNAPSHOT_SHA256 = "24e5153cc0ebed77c7b422562e5a8ebfa147aad3019b27035b5314aaaacfad5a"

GOVERNED_FIRST = "2013-01-02"
GOVERNED_LAST = "2026-07-10"
GOVERNED_SESSIONS = 3400
GOVERNED_SESSION_LIST_SHA256 = "b873421516ba5c4bbeb4ff3859e574f64f7251a956a2ba6ddea0e753981dad3f"

WINDOWS = {
    "development": ("2013-01-02", "2019-10-02", 1700),
    "validation": ("2019-10-03", "2023-02-16", 850),
    "oos": ("2023-02-17", "2026-07-10", 850),
}

# Availability column = the column that determines WHEN a row's information became
# knowable, and therefore which window owns it. Tables with no such column are
# interval-valid reference registries: they are committed separately and are NOT part of
# any sealed partition. That carve-out is disclosed in the emitted records rather than
# assumed, because those registries do contain rows whose validity intervals extend into
# the sealed windows.
OBSERVATION_TABLES = {
    "prices": "date",
    "etf_prices": "date",
    "actions": "date",
    "universe": "universe_month",
    "anchors": "session_date",
    "sic_observations": "accepted_utc",
}

REFERENCE_TABLES = (
    "crosswalk",
    "predecessor_overrides",
    "security_sector_overrides",
    "sic_mapping",
)

# The session calendar authority, per sealed manifest section_8a.
SESSION_TABLE = "prices"
SESSION_COLUMN = "date"

# Factor-series coverage is the sector-ETF series; naming them leaks nothing (they are
# registered in the countersigned sector mapping). Security tickers are counted, never
# listed, because the membership of the sealed universe is not value-blind.
FACTOR_SERIES_TABLE = "etf_prices"

_ROW_COUNT_BATCH = 20000

REFUSAL = "INTEGRITY_STOP:SEALED_PARTITION_COMMITMENT"


class CommitmentRefused(Exception):
    """A precondition failed. Never caught to retry, never downgraded to a warning."""


# --------------------------------------------------------------------------------------
# Canonical encoding
# --------------------------------------------------------------------------------------


def canonical_scalar(value: object) -> str:
    """Encode one scalar to a stable string, independent of host and DuckDB build."""
    if value is None:
        raise ValueError("NULL is encoded by canonical_field, not here")
    if isinstance(value, bool):
        # bool before int: bool IS an int in Python, and True would encode as "1"
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value:
            return "NaN"
        if value == float("inf"):
            return "Infinity"
        if value == float("-inf"):
            return "-Infinity"
        # .17g round-trips an IEEE-754 double exactly and does not vary by platform
        return format(value, ".17g")
    if isinstance(value, decimal.Decimal):
        if value.is_nan():
            return "NaN"
        return format(value.normalize(), "f")
    if isinstance(value, datetime.datetime):
        if value.tzinfo is None:
            return "naive:" + value.isoformat()
        return "utc:" + value.astimezone(datetime.timezone.utc).isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, datetime.time):
        return "time:" + value.isoformat()
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "hex:" + bytes(value).hex()
    if isinstance(value, str):
        return value
    raise CommitmentRefused(f"{REFUSAL}:unencodable_type:{type(value).__name__}")


def canonical_field(value: object) -> bytes:
    """Length-prefixed field encoding. Injective: no value can forge a field boundary."""
    if value is None:
        return b"N;"
    encoded = canonical_scalar(value).encode("utf-8")
    return b"V" + str(len(encoded)).encode("ascii") + b":" + encoded


def canonical_row(values) -> bytes:
    return b"".join(canonical_field(v) for v in values) + b"\n"


# --------------------------------------------------------------------------------------
# Snapshot handling
# --------------------------------------------------------------------------------------


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def open_snapshot(path: str, expected_sha256: str):
    """Read-only snapshot access with a digest proof on both sides of the read."""
    before = sha256_file(path)
    if before != expected_sha256:
        raise CommitmentRefused(f"{REFUSAL}:snapshot_digest_mismatch_before:{before}")
    con = duckdb.connect(path, read_only=True)
    try:
        # Pin every session setting the canonical form depends on.
        con.execute("SET TimeZone='UTC'")
        con.execute("SET default_null_order='nulls_first'")
        con.execute("SET default_order='asc'")
        yield con
    finally:
        con.close()
    after = sha256_file(path)
    if after != expected_sha256:
        raise CommitmentRefused(f"{REFUSAL}:snapshot_digest_mismatch_after:{after}")


def table_columns(con, table: str) -> list:
    rows = con.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_name = ? ORDER BY ordinal_position",
        [table],
    ).fetchall()
    if not rows:
        raise CommitmentRefused(f"{REFUSAL}:table_absent:{table}")
    return [{"name": name, "type": dtype} for name, dtype in rows]


def schema_identity(con, tables) -> dict:
    """SHA-256 over the ordered (table, column, type) triples -- the schema identity."""
    schema = {t: table_columns(con, t) for t in sorted(tables)}
    payload = json.dumps(schema, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return {
        "tables": schema,
        "schema_identity_sha256": hashlib.sha256(payload.encode("ascii")).hexdigest(),
    }


# --------------------------------------------------------------------------------------
# Window predicates
# --------------------------------------------------------------------------------------


def _window_bounds(window: str):
    if window not in WINDOWS:
        raise CommitmentRefused(f"{REFUSAL}:unknown_window:{window}")
    start, end, sessions = WINDOWS[window]
    return start, end, sessions


def window_predicate(table: str, window: str) -> str:
    """Inclusive availability-date predicate for a table within a window.

    ``sic_observations`` is timestamped rather than dated; it is cast to a UTC date so
    the same inclusive boundary rule applies to every observation table.
    """
    column = OBSERVATION_TABLES[table]
    start, end, _ = _window_bounds(window)
    if table == "sic_observations":
        expr = f"CAST({column} AS DATE)"
    else:
        expr = column
    return f"{expr} >= DATE '{start}' AND {expr} <= DATE '{end}'"


# --------------------------------------------------------------------------------------
# Content commitment
# --------------------------------------------------------------------------------------


def _hash_partition(con, table: str, predicate: str | None) -> dict:
    """Stream the partition through SHA-256. Row values never leave this function."""
    columns = [c["name"] for c in table_columns(con, table)]
    projection = ", ".join(f'"{c}"' for c in columns)
    where = f" WHERE {predicate}" if predicate else ""
    sql = f"SELECT {projection} FROM {table}{where} ORDER BY ALL"
    digest = hashlib.sha256()
    rows = 0
    cursor = con.execute(sql)
    while True:
        batch = cursor.fetchmany(_ROW_COUNT_BATCH)
        if not batch:
            break
        for row in batch:
            digest.update(canonical_row(row))
            rows += 1
    return {
        "row_count": rows,
        "column_order": columns,
        "content_sha256": digest.hexdigest(),
    }


def _null_counts(con, table: str, predicate: str | None) -> dict:
    columns = [c["name"] for c in table_columns(con, table)]
    parts = ", ".join(f'SUM(CASE WHEN "{c}" IS NULL THEN 1 ELSE 0 END)' for c in columns)
    where = f" WHERE {predicate}" if predicate else ""
    row = con.execute(f"SELECT {parts} FROM {table}{where}").fetchone()
    return {c: int(v or 0) for c, v in zip(columns, row)}


def _date_bounds(con, table: str, predicate: str | None) -> dict:
    column = OBSERVATION_TABLES[table]
    expr = f"CAST({column} AS DATE)" if table == "sic_observations" else column
    where = f" WHERE {predicate}" if predicate else ""
    lo, hi, distinct = con.execute(
        f"SELECT MIN({expr}), MAX({expr}), COUNT(DISTINCT {expr}) FROM {table}{where}"
    ).fetchone()
    return {
        "availability_column": column,
        "first": str(lo) if lo is not None else None,
        "last": str(hi) if hi is not None else None,
        "distinct_availability_dates": int(distinct or 0),
    }


def _security_counts(con, table: str, predicate: str | None) -> dict:
    """Counts only. Ticker LISTS are withheld: sealed universe membership is not
    value-blind, and a manifest that leaked it would defeat its own purpose."""
    columns = {c["name"] for c in table_columns(con, table)}
    where = f" WHERE {predicate}" if predicate else ""
    out = {}
    for column in ("ticker", "permaticker", "cik"):
        if column in columns:
            (count,) = con.execute(
                f"SELECT COUNT(DISTINCT \"{column}\") FROM {table}{where}"
            ).fetchone()
            out[f"distinct_{column}"] = int(count or 0)
    return out


def _session_list(con, window: str) -> dict:
    start, end, expected = _window_bounds(window)
    dates = [
        r[0]
        for r in con.execute(
            f"SELECT DISTINCT {SESSION_COLUMN} FROM {SESSION_TABLE} "
            f"WHERE {SESSION_COLUMN} >= DATE '{start}' AND {SESSION_COLUMN} <= DATE '{end}' "
            f"ORDER BY {SESSION_COLUMN}"
        ).fetchall()
    ]
    if len(dates) != expected:
        raise CommitmentRefused(
            f"{REFUSAL}:session_count_mismatch:{window}:expected={expected}:observed={len(dates)}"
        )
    # Same construction as the registered session-index extraction, so the window hashes
    # are comparable with the governed list hash rather than a private convention.
    listing = "|".join(str(d) for d in dates)
    return {
        "declared_start": start,
        "declared_end": end,
        "expected_sessions": expected,
        "observed_sessions": len(dates),
        "first_session": str(dates[0]),
        "last_session": str(dates[-1]),
        "session_list_sha256": hashlib.sha256(listing.encode()).hexdigest(),
    }


def _governed_session_check(con) -> dict:
    dates = [
        r[0]
        for r in con.execute(
            f"SELECT DISTINCT {SESSION_COLUMN} FROM {SESSION_TABLE} "
            f"WHERE {SESSION_COLUMN} >= DATE '{GOVERNED_FIRST}' "
            f"AND {SESSION_COLUMN} <= DATE '{GOVERNED_LAST}' ORDER BY {SESSION_COLUMN}"
        ).fetchall()
    ]
    listing = hashlib.sha256("|".join(str(d) for d in dates).encode()).hexdigest()
    return {
        "governed_sessions_observed": len(dates),
        "governed_sessions_expected": GOVERNED_SESSIONS,
        "governed_session_list_sha256_observed": listing,
        "governed_session_list_sha256_registered": GOVERNED_SESSION_LIST_SHA256,
        "reproduces_registered_calendar": (
            listing == GOVERNED_SESSION_LIST_SHA256 and len(dates) == GOVERNED_SESSIONS
        ),
    }


def _factor_series_coverage(con, window: str) -> dict:
    predicate = window_predicate(FACTOR_SERIES_TABLE, window)
    rows = con.execute(
        f"SELECT ticker, COUNT(*), MIN(date), MAX(date) FROM {FACTOR_SERIES_TABLE} "
        f"WHERE {predicate} GROUP BY ticker ORDER BY ticker"
    ).fetchall()
    return {
        "series_count": len(rows),
        "series": [
            {"ticker": t, "sessions": int(n), "first": str(lo), "last": str(hi)}
            for t, n, lo, hi in rows
        ],
    }


def commit_window(con, window: str) -> dict:
    """Per-table content commitment plus value-blind structure for one window."""
    tables = {}
    for table in sorted(OBSERVATION_TABLES):
        predicate = window_predicate(table, window)
        entry = _hash_partition(con, table, predicate)
        entry["date_bounds"] = _date_bounds(con, table, predicate)
        entry["null_counts"] = _null_counts(con, table, predicate)
        entry["security_counts"] = _security_counts(con, table, predicate)
        tables[table] = entry
    # The partition commitment binds table identity, row count and content together, so a
    # table cannot be swapped, dropped or renamed under a matching aggregate hash.
    roll = [
        {"table": t, "row_count": e["row_count"], "content_sha256": e["content_sha256"]}
        for t, e in sorted(tables.items())
    ]
    payload = json.dumps(roll, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return {
        "window": window,
        "tables": tables,
        "partition_content_sha256": hashlib.sha256(payload.encode("ascii")).hexdigest(),
        "total_rows": sum(e["row_count"] for e in tables.values()),
    }


def _completeness(con, windows: dict) -> dict:
    """Prove the three windows partition the governed corpus exactly.

    Without this the commitment answers "is what I committed unchanged?" but never "did
    I commit everything?". A sealed row that fell outside all three predicates -- a NULL
    availability date, an off-by-one boundary, a row past the governed end -- would be
    uncommitted and therefore unverifiable, while every hash still matched. This refuses
    on any such gap rather than reporting one.
    """
    tables = {}
    for table in sorted(OBSERVATION_TABLES):
        column = OBSERVATION_TABLES[table]
        expr = f"CAST({column} AS DATE)" if table == "sic_observations" else column
        total, before, after = con.execute(
            f"SELECT COUNT(*), "
            f"SUM(CASE WHEN {expr} < DATE '{GOVERNED_FIRST}' THEN 1 ELSE 0 END), "
            f"SUM(CASE WHEN {expr} > DATE '{GOVERNED_LAST}' THEN 1 ELSE 0 END) "
            f"FROM {table}"
        ).fetchone()
        total, before, after = int(total), int(before or 0), int(after or 0)
        in_window = total - before - after
        committed = sum(
            windows[w]["tables"][table]["row_count"]
            for w in ("development", "validation", "oos")
        )
        if committed != in_window:
            raise CommitmentRefused(
                f"{REFUSAL}:partition_incomplete:{table}:"
                f"in_window={in_window}:committed={committed}"
            )
        tables[table] = {
            "total_rows": total,
            "before_governed_window": before,
            "after_governed_window": after,
            "in_governed_window": in_window,
            "committed_across_windows": committed,
        }
    return {
        "tables": tables,
        "every_in_window_row_committed_exactly_once": True,
        "total_rows": sum(t["total_rows"] for t in tables.values()),
        "in_governed_window": sum(t["in_governed_window"] for t in tables.values()),
        "before_governed_window": sum(t["before_governed_window"] for t in tables.values()),
        "after_governed_window": sum(t["after_governed_window"] for t in tables.values()),
        "note": (
            "Rows before the governed window are pre-2013 warm-up history carried by the "
            "snapshot and used by no window. They are excluded from every partition "
            "commitment by construction, and counted here so the exclusion is visible "
            "rather than silent."
        ),
    }


def commit_reference_tables(con) -> dict:
    tables = {}
    for table in REFERENCE_TABLES:
        entry = _hash_partition(con, table, None)
        entry["null_counts"] = _null_counts(con, table, None)
        entry["security_counts"] = _security_counts(con, table, None)
        tables[table] = entry
    roll = [
        {"table": t, "row_count": e["row_count"], "content_sha256": e["content_sha256"]}
        for t, e in sorted(tables.items())
    ]
    payload = json.dumps(roll, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return {
        "tables": tables,
        "reference_content_sha256": hashlib.sha256(payload.encode("ascii")).hexdigest(),
        "disclosure": (
            "Interval-valid reference registries. NOT part of any sealed partition and "
            "NOT under the OOS DENY: their validity intervals span all three windows by "
            "construction, so they cannot be sliced by availability date. They are "
            "committed here so their identity is pinned, and disclosed so a reviewer can "
            "see exactly what the sealed boundary does and does not cover."
        ),
    }


# --------------------------------------------------------------------------------------
# Record emission
# --------------------------------------------------------------------------------------


def _provenance(custodian: str, authority: str, produced_at: str, snapshot_sha: str) -> dict:
    return {
        "custodian": custodian,
        "custodian_appointment": (
            "docs/review/mr002/MR002_OperationalCustodian_Appointment_v1.0.json"
        ),
        "execution_authority": authority,
        "producer": "scripts/mr002_custody/sealed_partition_commitment.py",
        "producer_sha256": sha256_file(__file__),
        "produced_at_utc": produced_at,
        "snapshot": SNAPSHOT,
        "snapshot_sha256": snapshot_sha,
        "snapshot_unchanged_across_read": True,
        "read_mode": "READ_ONLY",
        "session_settings": {
            "TimeZone": "UTC",
            "default_null_order": "nulls_first",
            "default_order": "asc",
        },
    }


def build_records(con, *, custodian: str, authority: str, produced_at: str) -> dict:
    """Produce P9 and P6 for validation, plus the commitments the sealed store needs."""
    governed = _governed_session_check(con)
    if not governed["reproduces_registered_calendar"]:
        raise CommitmentRefused(
            f"{REFUSAL}:governed_calendar_mismatch:"
            f"{governed['governed_session_list_sha256_observed']}"
        )

    all_tables = sorted(set(OBSERVATION_TABLES) | set(REFERENCE_TABLES))
    schema = schema_identity(con, all_tables)
    windows = {name: commit_window(con, name) for name in ("development", "validation", "oos")}
    sessions = {name: _session_list(con, name) for name in WINDOWS}
    reference = commit_reference_tables(con)
    completeness = _completeness(con, windows)
    provenance = _provenance(custodian, authority, produced_at, SNAPSHOT_SHA256)

    (latest_source,) = con.execute(
        f"SELECT MAX({SESSION_COLUMN}) FROM {SESSION_TABLE}"
    ).fetchone()

    p9 = {
        "record_type": "MR002_ValidationStructuralManifest",
        "version": "1.0",
        "artifact_kind": "RUNTIME_INSTANCE",
        "prerequisite_id": "P9",
        "prerequisite_title": (
            "Precommitted value-blind structural manifest for the validation partition"
        ),
        "produced_before_sealing": True,
        "sealing_note": (
            "Produced before the sealed store exists, which is the required order: P9 is "
            "the sole input the structural preflight may read pre-authorization, and it "
            "must be committed before the partition is sealed behind the access boundary."
        ),
        "value_blind": True,
        "value_blind_fields_emitted": [
            "schema identity",
            "table names",
            "row counts",
            "date bounds",
            "session count",
            "symbol/security counts",
            "factor-series coverage",
            "null-count summaries",
            "latest source date",
        ],
        "withheld_deliberately": (
            "Ticker lists for sealed partitions. Counts are value-blind; membership is not."
        ),
        "provenance": provenance,
        "governed_calendar": governed,
        "schema_identity": schema,
        "window": "validation",
        "window_sessions": sessions["validation"],
        "all_window_sessions": sessions,
        "structure": {
            table: {
                "row_count": entry["row_count"],
                "date_bounds": entry["date_bounds"],
                "null_counts": entry["null_counts"],
                "security_counts": entry["security_counts"],
            }
            for table, entry in windows["validation"]["tables"].items()
        },
        "factor_series_coverage": _factor_series_coverage(con, "validation"),
        "latest_source_date": str(latest_source),
        "reference_layer_disclosure": reference["disclosure"],
        "boundary": (
            "This manifest grants nothing. validation_authorization remains false and the "
            "single validation opening remains unconsumed."
        ),
    }
    p9["manifest_identity_sha256"] = _identity(p9)

    p6 = {
        "record_type": "ValidationPartitionContentCommitment",
        "version": "1.0",
        "artifact_kind": "RUNTIME_INSTANCE",
        "prerequisite_id": "P6",
        "prerequisite_title": "ValidationPartitionContentCommitment (runtime instance)",
        "commitment_scheme": {
            "algorithm": "SHA-256 over canonical (sorted) partition content",
            "row_order": "ORDER BY ALL with default_null_order=nulls_first",
            "field_encoding": (
                "length-prefixed; NULL distinct from empty string; floats .17g; "
                "TIMESTAMPTZ normalized to UTC"
            ),
            "partition_roll_up": (
                "SHA-256 over the ascii JSON list of {table,row_count,content_sha256} "
                "sorted by table"
            ),
        },
        "provenance": provenance,
        "committed_before_authorization": True,
        "validation_partition": windows["validation"],
        "oos_partition": windows["oos"],
        "development_partition": windows["development"],
        "reference_tables": reference,
        "partition_completeness": completeness,
        "oos_note": (
            "The OOS commitment is included because the sealed store must physically "
            "separate OOS objects to make the DENY enforceable, and that export has to be "
            "verifiable. Committing to OOS CONTENT HASHES is not an OOS opening: no OOS "
            "value is emitted, and oos_openings remains 0."
        ),
        "boundary": (
            "This commitment grants nothing. validation_authorization remains false; the "
            "OOS partition remains under DENY."
        ),
    }
    p6["commitment_identity_sha256"] = _identity(p6)

    return {"P9": p9, "P6": p6}


def _identity(record: dict) -> str:
    body = {k: v for k, v in record.items() if not k.endswith("_identity_sha256")}
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def write_record(record: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(record, handle, indent=1, sort_keys=True, ensure_ascii=True)
        handle.write("\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="WP-C P9/P6 custodian producer")
    parser.add_argument("--snapshot", default=SNAPSHOT)
    parser.add_argument("--snapshot-sha256", default=SNAPSHOT_SHA256)
    parser.add_argument("--custodian", required=True)
    parser.add_argument("--authority", required=True)
    parser.add_argument("--produced-at", required=True, help="UTC ISO-8601 timestamp")
    parser.add_argument("--emit-p9", required=True)
    parser.add_argument("--emit-p6", required=True)
    args = parser.parse_args(argv)

    try:
        with open_snapshot(args.snapshot, args.snapshot_sha256) as con:
            records = build_records(
                con,
                custodian=args.custodian,
                authority=args.authority,
                produced_at=args.produced_at,
            )
    except CommitmentRefused as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
        return 2

    write_record(records["P9"], args.emit_p9)
    write_record(records["P6"], args.emit_p6)
    print(
        json.dumps(
            {
                "status": "PRODUCED",
                "P9": args.emit_p9,
                "P9_manifest_identity_sha256": records["P9"]["manifest_identity_sha256"],
                "P6": args.emit_p6,
                "P6_commitment_identity_sha256": records["P6"]["commitment_identity_sha256"],
                "validation_partition_content_sha256": (
                    records["P6"]["validation_partition"]["partition_content_sha256"]
                ),
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
