"""Governed materialization: pinned Parquet objects -> the DuckDB representation Phase 3C reads.

This is the missing seam between the sealed store and Phase 3C, and it is deliberately the smallest
thing that can close it. It REUSES the governed Phase 3B pinned reader
(`phase3b.readers.PinnedObject` / `PinnedObjectReader`); it does not introduce a second S3 reader
and it performs no AWS call of its own.

REPRESENTATION ONLY. It changes the container, never the content. It writes each Parquet table into
DuckDB verbatim: no synthetic rows, no filtering, no imputation, no date/price/action alteration, no
column derivation, no alternative signal construction, no reordering that any consumer can observe.

WHY THE MAPPING IS UNIQUELY DETERMINED
`FrozenDataset` reads ten tables. Seven consumption sites are order-insensitive by construction:
`prices`, `etf_prices` and `sic_observations` carry ORDER BY in their own SQL; `universe` and
`actions` are consumed through dicts/sets and predicates; and `anchors` is sorted by
`EarningsBlackout.__init__`. The remaining three -- `crosswalk`, `security_sector_overrides` and
`sic_mapping` -- are consumed FIRST-MATCH-WINS over an unordered SELECT, so their answer would
depend on row order if two rows could ever match the same key on the same date.

They cannot, and this module refuses to proceed unless that remains true: `assert_determinism`
verifies zero true interval overlaps in all three, with open-ended bounds handled correctly. That
turns the determinism of the mapping from an assumption into an enforced precondition, checked
against the actual bytes read.

Nothing here reads validation or OOS data by itself; it reads exactly the objects it is handed.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import os
import tempfile
from dataclasses import dataclass

import duckdb

from app.research.mr002.phase3b.readers import PinnedObject, PinnedReadRefused

# The ten tables FrozenDataset queries, and the minimum columns each consumer touches.
REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "crosswalk": ("permaticker", "cik", "effective_from", "effective_to"),
    "predecessor_overrides": ("permaticker", "predecessor_cik", "successor_cik", "event_date",
                              "review_status"),
    "security_sector_overrides": ("permaticker", "effective_from", "effective_to",
                                  "review_status", "sector_etf"),
    "sic_mapping": ("sic_start", "sic_end", "effective_from", "effective_to", "sector_etf",
                    "mapping_confidence"),
    "sic_observations": ("cik", "accepted_utc", "sic"),
    "anchors": ("cik", "session_date", "availability_class", "event_time_basis"),
    "universe": ("universe_month", "ticker", "permaticker", "in_long_universe",
                 "in_short_universe"),
    "prices": ("ticker", "date", "open", "close", "closeadj", "volume"),
    "etf_prices": ("ticker", "date", "adjclose"),
    "actions": ("ticker", "date", "action"),
}

# The three first-match-wins tables and the (key, from, to) columns whose intervals must not overlap.
_INTERVAL_INVARIANTS: tuple[tuple[str, str, str, str], ...] = (
    ("crosswalk", "permaticker", "effective_from", "effective_to"),
    ("security_sector_overrides", "permaticker", "effective_from", "effective_to"),
)
_NEG = _dt.date(1, 1, 1)
_POS = _dt.date(9999, 12, 31)


class MaterializationRefused(Exception):
    """A precondition of the representation change failed. Never worked around."""


@dataclass(frozen=True)
class TableSource:
    table: str
    obj: PinnedObject


def _as_date(v) -> _dt.date | None:
    if v is None:
        return None
    if isinstance(v, _dt.datetime):
        return v.date()
    if isinstance(v, _dt.date):
        return v
    return _dt.date.fromisoformat(str(v)[:10])


def _overlaps(a: tuple, b: tuple) -> bool:
    return max(a[0], b[0]) <= min(a[1], b[1])


def assert_schema(table: str, columns: tuple[str, ...]) -> None:
    need = REQUIRED_COLUMNS.get(table)
    if need is None:
        raise MaterializationRefused(f"{table}: not a registered table")
    missing = [c for c in need if c not in columns]
    if missing:
        raise MaterializationRefused(f"{table}: required columns absent: {missing}")


def assert_determinism(con: duckdb.DuckDBPyConnection) -> dict:
    """Refuse unless every first-match-wins table can match at most one row per key and date."""
    report: dict = {}
    for table, key, frm, to in _INTERVAL_INVARIANTS:
        rows = con.execute(f"SELECT {key}, {frm}, {to} FROM {table}").fetchall()
        by: dict[int, list] = {}
        for k, f, t in rows:
            if k is None:
                continue
            by.setdefault(int(k), []).append((_as_date(f) or _NEG, _as_date(t) or _POS))
        overlaps = [
            (k, iv[i], iv[j])
            for k, iv in by.items()
            for i in range(len(iv))
            for j in range(i + 1, len(iv))
            if _overlaps(iv[i], iv[j])
        ]
        report[table] = {"rows": len(rows), "keys": len(by), "true_overlaps": len(overlaps)}
        if overlaps:
            raise MaterializationRefused(
                f"{table}: {len(overlaps)} overlapping intervals -- first-match resolution would "
                f"depend on row order, so the representation is not uniquely determined. "
                f"example: {overlaps[0]}"
            )

    # sic_mapping matches on a SIC RANGE crossed with a date range.
    rows = con.execute(
        "SELECT sic_start, sic_end, effective_from, effective_to FROM sic_mapping").fetchall()
    iv = [(int(a), int(b), _as_date(f) or _NEG, _as_date(t) or _POS) for a, b, f, t in rows]
    overlaps = [
        (iv[i], iv[j])
        for i in range(len(iv))
        for j in range(i + 1, len(iv))
        if _overlaps((iv[i][0], iv[i][1]), (iv[j][0], iv[j][1]))
        and _overlaps((iv[i][2], iv[i][3]), (iv[j][2], iv[j][3]))
    ]
    report["sic_mapping"] = {"rows": len(iv), "true_overlaps": len(overlaps)}
    if overlaps:
        raise MaterializationRefused(
            f"sic_mapping: {len(overlaps)} rows whose (sic-range x date-range) overlap another -- "
            f"first-match resolution would depend on row order. example: {overlaps[0]}"
        )
    return report


def materialize(sources: list[TableSource], reader, out_path: str) -> dict:
    """Read every pinned object through the governed reader and write the DuckDB representation.

    Returns the evidence: per-object bucket/key/VersionID/SHA-256/rows, in read order. That is the
    opened-object record the caller publishes; this function does not decide policy.
    """
    have = {s.table for s in sources}
    missing = sorted(set(REQUIRED_COLUMNS) - have)
    if missing:
        raise MaterializationRefused(f"no pinned object supplied for: {missing}")
    extra = sorted(have - set(REQUIRED_COLUMNS))
    if extra:
        raise MaterializationRefused(f"unregistered table supplied: {extra}")

    opened: list[dict] = []
    con = duckdb.connect(out_path)
    staging_dir = tempfile.TemporaryDirectory(prefix="mr002_materialize_")
    staging = staging_dir.name
    try:
        for src in sources:
            payload = reader.read(src.obj)
            src.obj.verify(payload)          # fail-closed on checksum, before anything is parsed
            # DuckDB reads Parquet natively, so the governed path needs no Arrow/pyarrow
            # dependency at all -- one fewer bound runtime component.
            staged = os.path.join(staging, f"{src.table}.parquet")
            with open(staged, "wb") as fh:
                fh.write(payload)
            quoted = staged.replace("'", "''")
            cols = tuple(r[0] for r in con.execute(
                f"DESCRIBE SELECT * FROM read_parquet('{quoted}')").fetchall())
            assert_schema(src.table, cols)
            # verbatim: SELECT * with no projection, filter, cast or ordering
            con.execute(
                f'CREATE TABLE "{src.table}" AS SELECT * FROM read_parquet(\'{quoted}\')')
            rows = con.execute(f'SELECT count(*) FROM "{src.table}"').fetchone()[0]
            opened.append({
                "table": src.table,
                "bucket": src.obj.bucket,
                "key": src.obj.key,
                "version_id": src.obj.version_id,
                "sha256": src.obj.sha256,
                "partition": src.obj.partition,
                "rows": int(rows),
                "columns": list(cols),
            })
        determinism = assert_determinism(con)
    finally:
        con.close()
        staging_dir.cleanup()

    chain = hashlib.sha256()
    for o in opened:
        chain.update(f"{o['key']}@{o['version_id']}:{o['sha256']}\n".encode("ascii"))
    return {
        "record_type": "MR002_Phase3C_MaterializationEvidence",
        "out_path": out_path,
        "objects_opened": opened,
        "objects_opened_count": len(opened),
        "logical_content_identity": chain.hexdigest(),
        "determinism_preconditions": determinism,
        "representation_only": True,
        "transformations_applied": "none — container change only",
    }


__all__ = [
    "MaterializationRefused",
    "PinnedReadRefused",
    "REQUIRED_COLUMNS",
    "TableSource",
    "assert_determinism",
    "assert_schema",
    "materialize",
]
