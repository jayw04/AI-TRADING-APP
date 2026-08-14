"""Qualification of the parquet decode-and-verify layer.

Fixture parquet only. Verifies that a payload which is not the committed table is refused for every
way it can differ - column order, row count, date bounds, missing table, extra table - because a
decoder that only checks checksums proves the bytes arrived, not that they are the sealed table.
"""

from __future__ import annotations

from datetime import date

import pytest

pa = pytest.importorskip("pyarrow")
import pyarrow.parquet as pq  # noqa: E402

from app.research.mr002.phase3b.parquet import (  # noqa: E402
    ParquetRefused,
    TableCommitment,
    decode,
    decode_all,
)

MANIFEST = {
    "schema_identity": {
        "tables": {
            "prices": [
                {"name": "ticker", "type": "VARCHAR"},
                {"name": "date", "type": "DATE"},
                {"name": "close", "type": "DOUBLE"},
            ],
            "actions": [
                {"name": "date", "type": "DATE"},
                {"name": "action", "type": "VARCHAR"},
            ],
        }
    },
    "structure": {
        "prices": {
            "row_count": 3,
            "date_bounds": {
                "availability_column": "date",
                "first": "2019-10-03",
                "last": "2019-10-07",
            },
        },
        "actions": {"row_count": 2},
    },
}


def _prices(rows=None) -> bytes:
    rows = rows or [
        ("AAA", "2019-10-03", 10.0),
        ("AAA", "2019-10-04", 11.0),
        ("AAA", "2019-10-07", 12.0),
    ]
    table = pa.table(
        {
            "ticker": [r[0] for r in rows],
            # A real Arrow DATE column: the sealed partition declares this column DATE, and a
            # string fixture is what made the suite structurally weaker than the sealed data.
            "date": pa.array([date.fromisoformat(r[1]) for r in rows], type=pa.date32()),
            "close": [r[2] for r in rows],
        }
    )
    return _to_bytes(table)


def _actions() -> bytes:
    return _to_bytes(
        pa.table({"date": pa.array([date(2019, 10, 3), date(2019, 10, 4)], type=pa.date32()),
                  "action": ["dividend", "split"]})
    )


def _to_bytes(table) -> bytes:
    import io

    buf = io.BytesIO()
    pq.write_table(table, buf)
    return buf.getvalue()


def _commitment(name="prices"):
    return TableCommitment.from_structural_manifest(MANIFEST, name)


def test_committed_table_decodes():
    table = decode(_prices(), _commitment())
    assert table.num_rows == 3
    assert tuple(table.column_names) == ("ticker", "date", "close")


def test_empty_payload_is_refused():
    with pytest.raises(ParquetRefused, match="empty payload"):
        decode(b"", _commitment())


def test_undecodable_payload_is_refused():
    with pytest.raises(ParquetRefused, match="undecodable"):
        decode(b"not a parquet file at all", _commitment())


def test_reordered_columns_are_refused():
    table = pa.table(
        {"date": pa.array([date(2019, 10, 3)], type=pa.date32()),
         "ticker": ["AAA"], "close": [10.0]}  # order swapped
    )
    with pytest.raises(ParquetRefused, match="column order"):
        decode(_to_bytes(table), _commitment())


def test_wrong_row_count_is_refused():
    short = _prices(rows=[("AAA", "2019-10-03", 10.0)])
    with pytest.raises(ParquetRefused, match="row count"):
        decode(short, _commitment())


def test_shifted_date_bounds_are_refused():
    shifted = _prices(
        rows=[
            ("AAA", "2019-10-03", 10.0),
            ("AAA", "2019-10-04", 11.0),
            ("AAA", "2023-02-16", 12.0),  # last date outside the commitment
        ]
    )
    with pytest.raises(ParquetRefused, match="date bounds"):
        decode(shifted, _commitment())


def test_decode_all_refuses_a_missing_committed_table():
    with pytest.raises(ParquetRefused, match="absent from the payloads"):
        decode_all({"validation/prices.parquet": _prices()}, MANIFEST, prefix="validation")


def test_decode_all_refuses_an_uncommitted_extra_table():
    payloads = {
        "validation/prices.parquet": _prices(),
        "validation/actions.parquet": _actions(),
        "validation/surprise.parquet": _actions(),
    }
    with pytest.raises(ParquetRefused, match="outside the committed set"):
        decode_all(payloads, MANIFEST, prefix="validation")


def test_decode_all_returns_every_committed_table():
    payloads = {
        "validation/prices.parquet": _prices(),
        "validation/actions.parquet": _actions(),
    }
    tables = decode_all(payloads, MANIFEST, prefix="validation")
    assert sorted(tables) == ["actions", "prices"]
    assert tables["prices"].num_rows == 3 and tables["actions"].num_rows == 2


def test_commitment_is_read_from_the_structural_manifest_not_invented():
    c = _commitment()
    assert c.column_order == ("ticker", "date", "close")
    assert c.row_count == 3
    assert (c.first_date, c.last_date) == ("2019-10-03", "2019-10-07")
