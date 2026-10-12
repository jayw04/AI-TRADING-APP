"""Read-only Sharadar daily/PIT-layer diagnostic for RANGE-002 data feasibility.

    python -I scripts/research/range002/pit_coverage_ro.py /path/to/factor_data.duckdb|/path/to/parquet_dir

* The store is opened ``read_only=True``; only SELECT / information_schema are issued.
* Schema-aware: columns are discovered; a missing column yields a SKIPPED line, never a guess.
* Grain-safe: ``tickers`` may hold several rows per ticker (e.g. Sharadar's per-``table`` rows).
  Every SEP join goes through ``tk`` (one row per ticker) and SEP is aggregated per ticker
  BEFORE joining, so duplicate metadata cannot inflate SEP counts.
* These are ticker-level DIAGNOSTIC summaries. They do not construct a PIT universe: that
  needs issuer identity over effective intervals (``app.research.range002.data``). A repeated
  permanent id across tickers is reported as a rename CANDIDATE only when the intervals do not
  overlap, and as a CONFLICT when they do; neither is declared legitimate here.
* Scope: the Sharadar daily layer only. This says nothing about SIP intraday coverage of
  delisted names (F2), which is a separate finding.
* Output is a diagnostic about a specific store file; it is not evidence until the store's
  provenance (source, extraction time, bounds, checksum, object Version ID) is recorded beside it.
"""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path

import duckdb

PERM_CANDIDATES = ("permaticker", "perma_ticker", "permid", "permanent_id")

#: Mirrors app.research.range002.data.manifest.REQUIRED_COLUMNS (a test asserts equality); kept
#: local so the script runs under ``python -I`` without the application on sys.path.
PIT_REQUIRED_COLUMNS = (
    (
        "tickers",
        ("permaticker", "ticker", "category", "isdelisted", "firstpricedate", "lastpricedate"),
    ),
    ("sep", ("ticker", "date", "close", "closeunadj", "volume")),
    ("actions", ("date", "action", "ticker", "contraticker")),
)


def _qi(name: str | None) -> str | None:
    return None if name is None else '"' + name.replace('"', '""') + '"'


def report(path: str) -> str:
    p = Path(path)
    lines: list[str] = []
    files = sorted(p.rglob("*.parquet")) if p.is_dir() else [p]
    for f in files:
        digest = hashlib.sha256()
        with f.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        st = f.stat()
        lines.append(
            f"file: {f.name} | bytes: {st.st_size} | sha256: {digest.hexdigest()} | mtime(UTC): "
            + time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(st.st_mtime))
            + " | mtime is NOT provenance or freshness"
        )
    if p.is_dir():
        # A Parquet export directory: <table>.parquet or <table>/*.parquet, exposed as views.
        con = duckdb.connect(":memory:")
        for table in ("tickers", "sep", "actions", "ingest_runs", "dataset_coverage"):
            single, many = p / f"{table}.parquet", p / table
            glob = single if single.is_file() else many / "*.parquet"
            try:
                con.execute(
                    f"CREATE VIEW \"{table}\" AS SELECT * FROM read_parquet('{glob.as_posix()}')"
                )
                con.execute(f'SELECT * FROM "{table}" LIMIT 0')
            except duckdb.Error:
                con.execute(f'DROP VIEW IF EXISTS "{table}"')
    else:
        con = duckdb.connect(path, read_only=True)

    def cols(table: str) -> dict[str, str]:
        rows = con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ?", [table]
        ).fetchall()
        return {r[0].lower(): r[0] for r in rows}

    def q(title: str, sql: str) -> None:
        lines.append(f"\n## {title}")
        try:
            cur = con.execute(sql)
            lines.append(" | ".join(d[0] for d in cur.description))
            lines.extend(" | ".join(str(x) for x in row) for row in cur.fetchall())
        except Exception as exc:  # noqa: BLE001 - a diagnostic reports, it does not abort
            lines.append(f"ERR: {exc}")

    tables = [
        r[0]
        for r in con.execute(
            "SELECT table_name FROM information_schema.tables ORDER BY 1"
        ).fetchall()
    ]
    tk_c, sep_c = cols("tickers"), cols("sep")
    lines.append(f"tables: {tables}")
    if not tk_c or not sep_c:
        lines.append("BLOCKED: tickers/sep table missing")
        return "\n".join(lines)

    t = _qi(tk_c["ticker"])
    perm_name = next((tk_c[c] for c in PERM_CANDIDATES if c in tk_c), None)
    perm = _qi(perm_name)
    dl_name = tk_c.get("isdelisted")
    dl = (
        f"(CASE WHEN UPPER(CAST({_qi(dl_name)} AS VARCHAR)) IN ('Y','TRUE','T','1') THEN TRUE "
        f"WHEN UPPER(CAST({_qi(dl_name)} AS VARCHAR)) IN ('N','FALSE','F','0') THEN FALSE END)"
        if dl_name
        else None
    )
    fp, lp = _qi(tk_c.get("firstpricedate")), _qi(tk_c.get("lastpricedate"))
    tbl = _qi(tk_c.get("table"))
    lines.append(
        f"resolved: ticker={t} perm={perm} isdelisted={'normalised' if dl else None} "
        f"first={fp} last={lp} table={tbl}"
    )

    for table, needed in PIT_REQUIRED_COLUMNS:
        have = cols(table)
        miss = [c for c in needed if c not in have]
        lines.append(
            f"PIT-required columns {table}: " + ("all present" if not miss else f"MISSING {miss}")
        )

    sel = [f"{t} AS ticker"]
    sel.append(
        f"BOOL_OR({dl}) AS any_delisted, BOOL_AND({dl}) AS all_delisted"
        if dl
        else "NULL::BOOLEAN AS any_delisted, NULL::BOOLEAN AS all_delisted"
    )
    sel.append(
        f"MIN({fp}) AS firstpricedate, MAX({lp}) AS lastpricedate"
        if fp and lp
        else "NULL AS firstpricedate, NULL AS lastpricedate"
    )
    sel.append(f"COUNT(DISTINCT {perm}) AS n_perm" if perm else "NULL AS n_perm")
    sel.append("COUNT(*) AS n_meta_rows")
    tk = f"WITH tk AS (SELECT {', '.join(sel)} FROM tickers GROUP BY {t})"

    q(
        "SEP bounds / rows / distinct tickers",
        "SELECT MIN(date), MAX(date), COUNT(*), COUNT(DISTINCT ticker) FROM sep",
    )
    q(
        "tickers grain",
        f"SELECT COUNT(*) AS meta_rows, COUNT(DISTINCT {t}) AS distinct_tickers, "
        f"COUNT(*) - COUNT(DISTINCT {t}) AS surplus_rows FROM tickers",
    )
    if tbl:
        q(
            "tickers rows by table value",
            f"SELECT {tbl}, COUNT(*) FROM tickers GROUP BY 1 ORDER BY 2 DESC",
        )
    q(
        "tickers with >1 meta row (sample)",
        f"{tk} SELECT ticker, n_meta_rows, any_delisted, all_delisted FROM tk "
        "WHERE n_meta_rows > 1 ORDER BY n_meta_rows DESC, ticker LIMIT 25",
    )
    if dl:
        q(
            "tickers with CONFLICTING delisted flags across meta rows",
            f"{tk} SELECT COUNT(*) FROM tk WHERE any_delisted AND NOT all_delisted",
        )
        q(
            "delisted / active / null-flag tickers (deduped)",
            f"{tk} SELECT COUNT(*) FILTER (WHERE any_delisted), COUNT(*) FILTER (WHERE NOT any_delisted), "
            "COUNT(*) FILTER (WHERE any_delisted IS NULL) FROM tk",
        )
        if lp:
            q(
                "delisted tickers by lastpricedate year",
                f"{tk} SELECT year(lastpricedate) AS y, COUNT(*) FROM tk WHERE any_delisted GROUP BY 1 ORDER BY 1",
            )
        q(
            "SEP coverage delisted vs active (SEP aggregated per ticker first)",
            f"{tk}, s AS (SELECT ticker, COUNT(*) AS n, MIN(date) AS d0, MAX(date) AS d1 FROM sep GROUP BY ticker) "
            "SELECT tk.any_delisted AS delisted, COUNT(*) AS tickers, COUNT(s.ticker) AS with_sep, "
            "COUNT(*) - COUNT(s.ticker) AS no_sep, SUM(s.n) AS sep_rows, MEDIAN(s.n) AS median_rows, "
            "MIN(s.d0) AS min_first, MAX(s.d1) AS max_last FROM tk LEFT JOIN s USING (ticker) GROUP BY 1 ORDER BY 1",
        )
        if lp:
            q(
                "delisted: SEP last date vs metadata lastpricedate (gap > 5 days)",
                f"{tk}, s AS (SELECT ticker, MAX(date) AS d1 FROM sep GROUP BY ticker) "
                "SELECT COUNT(*) FILTER (WHERE date_diff('day', s.d1, tk.lastpricedate) > 5) AS meta_later_than_sep, "
                "COUNT(*) FILTER (WHERE date_diff('day', tk.lastpricedate, s.d1) > 5) AS sep_later_than_meta, "
                "COUNT(*) AS n FROM tk JOIN s USING (ticker) WHERE tk.any_delisted",
            )
    q(
        "SEP tickers absent from metadata",
        f"{tk} SELECT COUNT(DISTINCT ticker) FROM sep WHERE ticker NOT IN (SELECT ticker FROM tk)",
    )

    if perm and fp and lp:
        iv = (
            f"WITH iv AS (SELECT {perm} AS pid, {t} AS ticker, MIN({fp}) AS f, MAX({lp}) AS l "
            f"FROM tickers WHERE {perm} IS NOT NULL GROUP BY 1, 2)"
        )
        ov = "a.f <= COALESCE(b.l, DATE '9999-12-31') AND b.f <= COALESCE(a.l, DATE '9999-12-31')"
        q(
            "permanent id: rows / non-null / distinct",
            f"SELECT COUNT(*), COUNT({perm}), COUNT(DISTINCT {perm}) FROM tickers",
        )
        q(
            "ticker -> several issuers: reuse candidates (no overlap) vs CONFLICTS (overlap)",
            f"{iv}, multi AS (SELECT ticker FROM iv GROUP BY 1 HAVING COUNT(DISTINCT pid) > 1), "
            "clash AS (SELECT DISTINCT a.ticker FROM iv a JOIN iv b ON a.ticker = b.ticker AND a.pid < b.pid "
            f"AND {ov}) SELECT (SELECT COUNT(*) FROM multi) AS multi_issuer_tickers, "
            "(SELECT COUNT(*) FROM clash) AS overlapping_conflicts, "
            "(SELECT COUNT(*) FROM multi WHERE ticker NOT IN (SELECT ticker FROM clash)) AS sequential_reuse_candidates",
        )
        q(
            "issuer -> several tickers: rename candidates (no overlap) vs CONFLICTS (overlap)",
            f"{iv}, multi AS (SELECT pid FROM iv GROUP BY 1 HAVING COUNT(DISTINCT ticker) > 1), "
            "clash AS (SELECT DISTINCT a.pid FROM iv a JOIN iv b ON a.pid = b.pid AND a.ticker < b.ticker "
            f"AND {ov}) SELECT (SELECT COUNT(*) FROM multi) AS multi_ticker_issuers, "
            "(SELECT COUNT(*) FROM clash) AS overlapping_conflicts, "
            "(SELECT COUNT(*) FROM multi WHERE pid NOT IN (SELECT pid FROM clash)) AS sequential_rename_candidates",
        )
        q(
            "reuse sample (ticker -> issuers)",
            f"{iv} SELECT ticker, COUNT(DISTINCT pid) c, MIN(pid), MAX(pid) FROM iv GROUP BY 1 "
            "HAVING COUNT(DISTINCT pid) > 1 ORDER BY c DESC, 1 LIMIT 25",
        )
    else:
        lines.append(
            "\n## identity / temporal checks: SKIPPED - need a permanent id and first/last price dates"
        )

    for name in tables:
        if any(k in name.lower() for k in ("ingest", "manifest", "provenance")):
            q(f"{name} (up to 20 rows)", f'SELECT * FROM "{name}" LIMIT 20')
    if "lastupdated" in tk_c:
        q(
            "tickers lastupdated bounds",
            f"SELECT MIN({_qi(tk_c['lastupdated'])}), MAX({_qi(tk_c['lastupdated'])}) FROM tickers",
        )
    con.close()
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    print(report(argv[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
