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


def _verify_date_bounds(table: Any, commitment: TableCommitment) -> None:
    if not commitment.availability_column or commitment.first_date is None:
        return
    if commitment.availability_column not in table.column_names:
        raise ParquetRefused(
            f"{commitment.name}: availability column {commitment.availability_column} absent"
        )
    column = table.column(commitment.availability_column)
    values = [str(v) for v in column.to_pylist() if v is not None]
    if not values:
        raise ParquetRefused(f"{commitment.name}: availability column carries no value")
    observed_first, observed_last = min(values), max(values)
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
