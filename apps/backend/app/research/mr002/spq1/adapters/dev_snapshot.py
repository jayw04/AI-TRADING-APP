"""Materialize a hash-bound development-only snapshot (Phase 2A partition isolation).

Reads the registered DBs ONCE (through the PartitionGuard, logging every read), filters strictly to
the development window and the preregistered sample, and writes a dev-only DuckDB the adapters read
exclusively. Validation/OOS rows never enter the snapshot. The snapshot identity is the SHA-256 of
its canonical (sorted) content, not the raw file bytes (so it is reproducible).
"""
from __future__ import annotations

from dataclasses import dataclass

from ..identities import canonical_sha256
from . import (
    DEV_END,
    DEV_START,
    REGISTERED_PROVENANCE_DB,
    REGISTERED_RESEARCH_DB,
    abs_path,
)
from .partition_guard import PartitionGuard

# Tables copied into the dev snapshot and their date-bound column (for guard range checks).
_PRICE_TABLES = {"prices": "date", "etf_prices": "date", "actions": "date"}
_TS_TABLES = {"sic_observations": "accepted_utc", "earnings_anchors": "acceptance_utc"}
_IDENTITY_TABLES = ("crosswalk",)


@dataclass(frozen=True)
class DevSnapshot:
    path: str
    content_sha256: str


def _connect_readonly(duckdb_module, path: str):  # noqa: ANN001 - duckdb passed in
    return duckdb_module.connect(path, read_only=True)


def materialize(
    duckdb_module,  # noqa: ANN001
    out_path: str,
    sample_tickers: list[str],
    sample_etfs: list[str],
    sample_ciks: list[int],
    guard: PartitionGuard,
    reader: str,
    retrieval_timestamp: str = "",
) -> DevSnapshot:
    """Build the dev-only snapshot; returns its path + canonical content hash."""
    import os

    if os.path.exists(out_path):
        os.remove(out_path)
    tick = ",".join(f"'{t}'" for t in sorted(set(sample_tickers)))
    etfs = ",".join(f"'{t}'" for t in sorted(set(sample_etfs)))
    ciks = ",".join(str(c) for c in sorted(set(sample_ciks)))

    research = _connect_readonly(duckdb_module, abs_path(REGISTERED_RESEARCH_DB))
    prov = _connect_readonly(duckdb_module, abs_path(REGISTERED_PROVENANCE_DB))
    out = duckdb_module.connect(out_path)
    content: dict[str, list] = {}
    try:
        def copy(con, src_db: str, table: str, where: str, first: str, last: str) -> None:
            guard.guarded_read(src_db, first, last, f"materialize:{table}", reader, 0,
                               retrieval_timestamp)
            rows = con.execute(f"select * from {table} where {where}").fetchall()
            names = [d[0] for d in con.description]
            col_defs = ", ".join(f'"{n}" VARCHAR' for n in names)
            out.execute(f'create table "{table}" ({col_defs})')
            for r in rows:
                out.execute(
                    f'insert into "{table}" values ({", ".join(["?"] * len(names))})',
                    [None if v is None else str(v) for v in r],
                )
            content[table] = sorted([[None if v is None else str(v) for v in r] for r in rows])

        for table, _col in _PRICE_TABLES.items():
            names = etfs if table == "etf_prices" else tick
            copy(research, REGISTERED_RESEARCH_DB, table,
                 f"ticker in ({names}) and date between '{DEV_START}' and '{DEV_END}'",
                 DEV_START, DEV_END)
        copy(research, REGISTERED_RESEARCH_DB, "crosswalk",
             f"cik in ({ciks}) or permaticker in (select permaticker from crosswalk where cik in ({ciks}))",
             DEV_START, DEV_END)
        # PIT provenance: only records available (accepted) by dev end.
        copy(prov, REGISTERED_PROVENANCE_DB, "sic_observations",
             f"cik in ({ciks}) and cast(accepted_utc as date) <= '{DEV_END}'", DEV_START, DEV_END)
        copy(prov, REGISTERED_PROVENANCE_DB, "earnings_anchors",
             f"cik in ({ciks}) and session_date between '{DEV_START}' and '{DEV_END}'",
             DEV_START, DEV_END)
        out.close()
    finally:
        research.close()
        prov.close()
    content_hash = canonical_sha256(content)
    return DevSnapshot(path=out_path, content_sha256=content_hash)
