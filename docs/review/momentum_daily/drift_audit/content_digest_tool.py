#!/usr/bin/env python3
"""§8 drift-audit — deterministic content digest of the EXACT audit-consumed inputs.

Read-only. Does NOT modify the source DuckDB or the harness. Produces a separate provenance
artifact binding the audit to the precise rows consumed (not the mutable whole file).

Canonicalization (drift_audit_content_digest/v1):
  * explicit, ordered column list per table (only columns the audit reads);
  * dates normalized to 'YYYY-MM-DD'; nulls -> '\\N'; floats -> repr() (round-trip exact,
    full stored float64 precision); ints -> str; bools -> 'true'/'false';
  * rows sorted by the full logical key (sep: date,ticker; tickers: ticker);
  * fixed '|' field delimiter with '\\'/'|' escaping; '\\n' row terminator;
  * FAIL-CLOSED on any duplicate logical key (nondeterministic ties);
  * sha256 over the streamed canonical rows; stats + SQL text recorded.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys

import duckdb

DB = r"C:\LLM-RAG-APP\ai-trading-app\apps\backend\data\factor_data_full.duckdb"
START, END = "2005-01-03", "2026-06-12"
CANON_VERSION = "drift_audit_content_digest/v1"

SEP_COLS = ["ticker", "date", "open", "high", "low", "closeadj", "volume"]
SEP_SQL = (f"SELECT {', '.join(SEP_COLS)} FROM sep "
           f"WHERE date BETWEEN DATE '{START}' AND DATE '{END}' ORDER BY date, ticker")
SEP_DUP_SQL = (f"SELECT date, ticker, COUNT(*) c FROM sep "
               f"WHERE date BETWEEN DATE '{START}' AND DATE '{END}' "
               f"GROUP BY date, ticker HAVING COUNT(*) > 1 LIMIT 1")

TKR_COLS = ["ticker", "sector", "industry", "category", "isdelisted",
            "firstpricedate", "lastpricedate"]
TKR_SQL = (f"SELECT {', '.join(TKR_COLS)} FROM tickers WHERE ticker IN "
           f"(SELECT DISTINCT ticker FROM sep WHERE date BETWEEN DATE '{START}' AND DATE '{END}') "
           f"ORDER BY ticker")
TKR_DUP_SQL = ("SELECT ticker, COUNT(*) c FROM tickers WHERE ticker IN "
               f"(SELECT DISTINCT ticker FROM sep WHERE date BETWEEN DATE '{START}' AND DATE '{END}') "
               "GROUP BY ticker HAVING COUNT(*) > 1 LIMIT 1")


def _canon(v) -> str:
    if v is None:
        return r"\N"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, float):
        return repr(v)                       # round-trip-exact full float64 precision
    if isinstance(v, int):
        return str(v)
    s = str(v)
    return s.replace("\\", "\\\\").replace("|", "\\|")


def _digest(con, sql: str, dup_sql: str, cols: list[str]) -> dict:
    dup = con.execute(dup_sql).fetchone()
    if dup is not None:
        raise SystemExit(f"FAIL-CLOSED: duplicate logical key {dup} for query:\n{sql}")
    h = hashlib.sha256()
    rows = 0
    cur = con.execute(sql)
    while True:
        batch = cur.fetchmany(200_000)
        if not batch:
            break
        for r in batch:
            h.update(("|".join(_canon(v) for v in r) + "\n").encode("utf-8"))
        rows += len(batch)
    return {"sha256": h.hexdigest(), "rows": rows, "columns": cols,
            "canonicalization": CANON_VERSION, "algorithm": "sha256",
            "query": " ".join(sql.split())}


def main() -> int:
    con = duckdb.connect(DB, read_only=True)
    print("computing tickers digest...", flush=True)
    tkr = _digest(con, TKR_SQL, TKR_DUP_SQL, TKR_COLS)
    tkr["distinct_tickers"] = tkr["rows"]
    print("  tickers:", tkr["sha256"], f"({tkr['rows']} rows)", flush=True)

    print("computing sep audit-window digest (this streams ~30.7M rows)...", flush=True)
    sep = _digest(con, SEP_SQL, SEP_DUP_SQL, SEP_COLS)
    st = con.execute(
        f"SELECT COUNT(DISTINCT date), COUNT(DISTINCT ticker), MIN(date), MAX(date) "
        f"FROM sep WHERE date BETWEEN DATE '{START}' AND DATE '{END}'").fetchone()
    sep.update({"distinct_sessions": st[0], "distinct_tickers": st[1],
                "date_min": str(st[2]), "date_max": str(st[3])})
    print("  sep:", sep["sha256"], f"({sep['rows']} rows, {st[0]} sessions, {st[1]} tickers)",
          flush=True)
    con.close()

    artifact = {
        "schema": "drift_audit_content_digest/v1",
        "source_db": {"abs_path": DB,
                      "whole_file_sha256":
                      "022ffd01b52b04aacac1932448413d042f68d0bb37ddf4ccdec39292484a7831"},
        "window": {"start_date": START, "end_date": END},
        "universe_id": "momentum_daily_stage2_4:top200_PIT_universe_asof_n200",
        "sep_audit_window": sep,
        "tickers_audit_relevant": tkr,
        "caveat": ("The original validation did not record a whole-file digest. The identified "
                   "source file was later modified in NON-audit tables (index_prices). Governing "
                   "reproducibility is established through file identity plus deterministic "
                   "content digests of the exact audit-consumed sep and tickers inputs."),
    }
    out = sys.argv[1] if len(sys.argv) > 1 else "content_digest_artifact.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2, default=str)
    print("artifact written:", out, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
