"""Acceptance guard for pull stores (BREADTH-CN-001).

A pull store (one with a `pull_log` table) may be read by breadth computation ONLY after `pull_baostock.py promote`
has recorded a passing gate-5 acceptance for exactly this content.  The acceptance row carries a content fingerprint
(row counts plus order-independent hashes of every table), so any later change to the data invalidates it.
Stores without a `pull_log` table (fixtures, other databases) are not pull stores and are not affected.
"""

from __future__ import annotations

import hashlib

import duckdb

TABLES = {
    "bars": "date, code, close, tradestatus, isst",
    "factors": "code, dividoperatedate, foreadjustfactor, backadjustfactor, adjustfactor",
    "ohlc": "date, code, open, high, low, close",
    "pull_log": "symbol, status, n_bars, n_factors, sha256, ohlc_sha256",
    "batch_log": "batch_id, n_symbols, n_bars, sha256",
}


def _has(con: duckdb.DuckDBPyConnection, table: str) -> bool:
    return bool(
        con.execute(
            "select count(*) from information_schema.tables where table_name = ?", [table]
        ).fetchone()[0]
    )


def fingerprint(con: duckdb.DuckDBPyConnection) -> str:
    """Content fingerprint: for each table, row count and the XOR of per-row hashes (order independent)."""
    parts = []
    for t, cols in TABLES.items():
        if not _has(con, t):
            parts.append(f"{t}:absent")
            continue
        n, h = con.execute(
            f"select count(*), coalesce(bit_xor(hash({cols})), 0) from {t}"
        ).fetchone()
        parts.append(f"{t}:{n}:{h}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def require_accepted(store: str) -> None:
    """Raise SystemExit unless `store` is not a pull store, or carries a passing, still-valid gate-5 acceptance."""
    con = duckdb.connect(store, read_only=True)
    try:
        if not _has(con, "pull_log"):
            return
        row = None
        if _has(con, "acceptance"):
            row = con.execute(
                "select passed, fingerprint from acceptance where gate = 'gate5' order by rowid desc limit 1"
            ).fetchone()
        if row is None or not row[0]:
            raise SystemExit(
                f"REFUSED: {store} is a pull store without a passing gate-5 acceptance. Run "
                "`pull_baostock.py promote --store ...` first; no breadth computation may read it until gate 5 passes."
            )
        if row[1] != fingerprint(con):
            raise SystemExit(
                f"REFUSED: {store} changed after its gate-5 acceptance (content fingerprint differs). Promote it again."
            )
    finally:
        con.close()
