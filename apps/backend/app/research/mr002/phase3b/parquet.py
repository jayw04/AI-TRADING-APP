"""Decode pinned parquet payloads and verify them against the precommitted structural manifest.

This is where governed bytes become tables, and it is the last place a substitution could go
unnoticed, so the decode is also a check. P9 - the value-blind structural manifest - was committed
BEFORE the partition was sealed, and it records each table's column order, row count, date bounds
and session count. Decoding a payload that does not match that commitment means the object is not
the object that was sealed, whatever its checksum said about the bytes we asked for.

Value-blind by construction: this module compares shapes, orders, counts and bounds. It never
compares a price, and it never emits one.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any


class ParquetRefused(Exception):
    """A payload that is not the committed table. Never coerced, never partially accepted."""


@dataclass(frozen=True)
class TableCommitment:
    """The P9 structural facts for one table."""

    name: str
    column_order: tuple[str, ...]
    row_count: int
    first_date: str | None = None
    last_date: str | None = None
    availability_column: str | None = None

    @classmethod
    def from_structural_manifest(cls, manifest: dict, table: str) -> TableCommitment:
        schema = manifest["schema_identity"]["tables"][table]
        structure = manifest["structure"][table]
        bounds = structure.get("date_bounds") or {}
        return cls(
            name=table,
            column_order=tuple(c["name"] for c in schema),
            row_count=int(structure["row_count"]),
            first_date=bounds.get("first"),
            last_date=bounds.get("last"),
            availability_column=bounds.get("availability_column"),
        )


def decode(payload: bytes, commitment: TableCommitment) -> Any:
    """Decode one parquet payload and refuse anything that is not the committed table.

    Column ORDER is checked, not merely membership: a reordered schema is a different table
    identity, and several downstream consumers read positionally.
    """
    import pyarrow.parquet as pq

    if not payload:
        raise ParquetRefused(f"{commitment.name}: empty payload")
    try:
        table = pq.read_table(io.BytesIO(payload))
    except Exception as exc:  # noqa: BLE001 - any decode failure is a refusal, not a partial read
        raise ParquetRefused(
            f"{commitment.name}: undecodable parquet: {type(exc).__name__}"
        ) from exc

    columns = tuple(table.column_names)
    if columns != commitment.column_order:
        raise ParquetRefused(
            f"{commitment.name}: column order {columns} != committed {commitment.column_order}"
        )
    if table.num_rows != commitment.row_count:
        raise ParquetRefused(
            f"{commitment.name}: row count {table.num_rows} != committed {commitment.row_count}"
        )
    _verify_date_bounds(table, commitment)
    return table


def _availability_date(value: Any, table_name: str) -> str:
    """One availability value as the DATE the commitment is expressed in.

    P9 commits date bounds at DATE granularity. An availability column may legitimately be a
    ``DATE`` or a timezone-aware ``TIMESTAMP`` -- ``sic_observations.accepted_utc`` is declared
    ``TIMESTAMP WITH TIME ZONE`` -- so the comparison has to reduce to a date rather than compare
    ``str(value)``. Doing the latter refused the sealed partition on 2026-08-14 with
    ``2019-10-03 10:03:29+00:00 != 2019-10-03``: the data and the commitment were both correct and
    only the rendering disagreed.

    Naive datetimes are REFUSED rather than assumed to be UTC. Assuming a zone is exactly the
    silent coercion this module exists to prevent, and a naive timestamp near midnight would
    resolve to a different date under a different assumption.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise ParquetRefused(
                f"{table_name}: naive timestamp {value!r} in the availability column; the "
                "commitment is a UTC date and a zoneless value cannot be resolved to one"
            )
        return value.astimezone(UTC).date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        # Fixture compatibility, deliberately narrow. The sealed partition declares five
        # availability columns ``DATE`` and one ``TIMESTAMP WITH TIME ZONE``, for which pyarrow
        # yields ``date`` and aware ``datetime`` objects respectively -- never a string. The
        # fixture suite, however, represents DATE columns as ISO date strings, which is why no
        # fixture run could ever have caught the 2026-08-14 timestamp defect.
        #
        # Only an EXACT ``YYYY-MM-DD`` literal is accepted: it carries no time and no zone, so
        # nothing is being assumed on its behalf. Anything longer -- notably
        # ``'2019-10-03 10:03:29+00:00'``, the shape that caused the incident -- is refused,
        # because a value with a time component must arrive as a real datetime so its zone is
        # explicit rather than parsed out of a rendering.
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            parsed = None
        if parsed is not None and len(value) == 10:
            return parsed.isoformat()
        raise ParquetRefused(
            f"{table_name}: availability value {value!r} is not a bare YYYY-MM-DD date literal; "
            "a value carrying a time component must be a timezone-aware datetime, not a string"
        )
    raise ParquetRefused(
        f"{table_name}: availability value {value!r} of unexpected type "
        f"{type(value).__name__}; expected date or timezone-aware datetime"
    )


def _verify_date_bounds(table: Any, commitment: TableCommitment) -> None:
    if not commitment.availability_column or commitment.first_date is None:
        return
    if commitment.availability_column not in table.column_names:
        raise ParquetRefused(
            f"{commitment.name}: availability column {commitment.availability_column} absent"
        )
    column = table.column(commitment.availability_column)
    dates = [
        _availability_date(v, commitment.name) for v in column.to_pylist() if v is not None
    ]
    if not dates:
        raise ParquetRefused(f"{commitment.name}: availability column carries no value")
    observed_first, observed_last = min(dates), max(dates)
    if observed_first != commitment.first_date or observed_last != commitment.last_date:
        raise ParquetRefused(
            f"{commitment.name}: date bounds {observed_first}..{observed_last} != committed "
            f"{commitment.first_date}..{commitment.last_date}"
        )


def decode_all(payloads: dict[str, bytes], manifest: dict, *, prefix: str) -> dict[str, Any]:
    """Decode every table the manifest commits to, refusing on any missing or extra payload.

    An extra payload is refused as firmly as a missing one: the run consumes the committed set and
    nothing else, so a key nobody committed to has no business being read.
    """
    committed = sorted(manifest["structure"])
    keyed = {
        k.split("/", 1)[-1].removesuffix(".parquet"): v
        for k, v in payloads.items()
        if k.startswith(f"{prefix}/")
    }
    missing = sorted(set(committed) - set(keyed))
    extra = sorted(set(keyed) - set(committed))
    if missing:
        raise ParquetRefused(f"committed tables absent from the payloads: {missing}")
    if extra:
        raise ParquetRefused(f"payloads outside the committed set: {extra}")
    return {
        table: decode(keyed[table], TableCommitment.from_structural_manifest(manifest, table))
        for table in committed
    }
