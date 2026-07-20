"""Materialize a hash-bound development-only snapshot (Phase 2A partition isolation).

Reads the registered DBs ONCE (through the PartitionGuard, recording each ACTUAL completed read with
its result row count, actual min/max date, and result hash), filters strictly to the development
window and the preregistered sample, and writes a dev-only DuckDB the adapters read exclusively.
Validation/OOS rows never enter the snapshot. The crosswalk is PIT-bounded (effective_from <= DEV_END;
pre-window rows retained, future rows excluded). Source identifiers are passed as bound parameters,
not string-concatenated. The snapshot identity is the SHA-256 of its canonical (sorted) content.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from ..identities import canonical_sha256
from . import (
    DEV_END,
    DEV_START,
    REGISTERED_PROVENANCE_DB,
    REGISTERED_RESEARCH_DB,
    abs_path,
)
from .manifests import sha256_file
from .partition_guard import PartitionGuard

PRE_WINDOW_LOWER = "0001-01-01"  # sentinel min for pre-existing identity/PIT rows


@dataclass(frozen=True)
class DevSnapshot:
    path: str
    content_sha256: str


def materialize(
    duckdb_module,  # noqa: ANN001
    out_path: str,
    sample_tickers: list[str],
    sample_etfs: list[str],
    sample_ciks: list[int],
    guard: PartitionGuard,
    reader: str,
    completion_timestamp: str = "",
) -> DevSnapshot:
    """Build the dev-only snapshot; returns its path + canonical content hash."""
    if os.path.exists(out_path):
        os.remove(out_path)
    research_sha = sha256_file(abs_path(REGISTERED_RESEARCH_DB))
    prov_sha = sha256_file(abs_path(REGISTERED_PROVENANCE_DB))
    research = duckdb_module.connect(abs_path(REGISTERED_RESEARCH_DB), read_only=True)
    prov = duckdb_module.connect(abs_path(REGISTERED_PROVENANCE_DB), read_only=True)
    out = duckdb_module.connect(out_path)
    content: dict[str, list] = {}
    tickers = sorted(set(sample_tickers))
    etfs = sorted(set(sample_etfs))
    ciks = sorted(set(sample_ciks))

    def copy(con, src_db, src_sha, table, where, params, date_col, take_date_prefix,
             allow_pre_window):  # noqa: ANN001
        token = guard.authorize_read(
            src_db, PRE_WINDOW_LOWER if allow_pre_window else DEV_START, DEV_END,
            f"materialize:{table}", reader, allow_pre_window=allow_pre_window)
        cols = [d[0] for d in con.execute(f"select * from {table} limit 0").description]
        rows = con.execute(f"select * from {table} where {where}", params).fetchall()
        srows = sorted([[None if v is None else str(v) for v in r] for r in rows])
        di = cols.index(date_col)
        dates = [str(r[di])[:10] if take_date_prefix else str(r[di]) for r in srows
                 if r[di] is not None]
        result_hash = canonical_sha256(srows)
        guard.record_completed_read(
            token, src_sha, f"{table}:{where}", min(dates) if dates else None,
            max(dates) if dates else None, len(srows), result_hash, completion_timestamp,
            allow_pre_window=allow_pre_window,
        )
        col_ddl = ", ".join('"' + c + '" VARCHAR' for c in cols)
        out.execute(f'create table "{table}" ({col_ddl})')
        for r in srows:
            out.execute(f'insert into "{table}" values ({", ".join(["?"] * len(cols))})', r)
        content[table] = srows

    copy(research, REGISTERED_RESEARCH_DB, research_sha, "prices",
         "ticker = ANY($t) and \"date\" between $a and $b", {"t": tickers, "a": DEV_START, "b": DEV_END},
         "date", False, False)
    copy(research, REGISTERED_RESEARCH_DB, research_sha, "etf_prices",
         "ticker = ANY($t) and \"date\" between $a and $b", {"t": etfs, "a": DEV_START, "b": DEV_END},
         "date", False, False)
    copy(research, REGISTERED_RESEARCH_DB, research_sha, "actions",
         "ticker = ANY($t) and \"date\" between $a and $b", {"t": tickers + etfs, "a": DEV_START, "b": DEV_END},
         "date", False, False)
    # crosswalk: PIT-bounded to effective_from <= DEV_END (pre-window retained, future excluded).
    copy(research, REGISTERED_RESEARCH_DB, research_sha, "crosswalk",
         "cik = ANY($c) and effective_from <= $b", {"c": ciks, "b": DEV_END},
         "effective_from", False, True)
    # PIT provenance: only records available (accepted) by dev end.
    copy(prov, REGISTERED_PROVENANCE_DB, prov_sha, "sic_observations",
         "cik = ANY($c) and cast(accepted_utc as date) <= $b", {"c": ciks, "b": DEV_END},
         "accepted_utc", True, True)
    copy(prov, REGISTERED_PROVENANCE_DB, prov_sha, "earnings_anchors",
         "cik = ANY($c) and session_date between $a and $b", {"c": ciks, "a": DEV_START, "b": DEV_END},
         "session_date", False, False)
    out.close()
    research.close()
    prov.close()
    return DevSnapshot(path=out_path, content_sha256=canonical_sha256(content))
