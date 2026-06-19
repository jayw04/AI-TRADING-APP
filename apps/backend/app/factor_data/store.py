"""DuckDB point-in-time factor-data store.

Schema + idempotent ingest + survivorship-free price/universe queries for the
Sharadar `SEP` / `TICKERS` / `ACTIONS` spine. Schema-on-write for clarity and
test stability (P9 §1 §4.2).

The store is a plain embedded DuckDB file under the gitignored `data/`. It holds
read-only-derived vendor data and is never committed (size + licensing, ADR 0018
§6); tests run against a tiny *derived* fixture built by the test suite, not raw
vendor bytes.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import duckdb
import pandas as pd
import structlog

from app.factor_data.config import resolve_store_path

logger = structlog.get_logger(__name__)

# Column projections kept in lock-step with the DDL below. Ingest reindexes the
# incoming vendor frame to exactly these columns (missing -> NULL) so we are
# robust to vendor column-order changes or extra columns we don't store.
_SEP_COLS = [
    "ticker", "date", "open", "high", "low", "close",
    "volume", "closeadj", "closeunadj", "lastupdated",
]
_TICKERS_COLS = [
    "ticker", "name", "exchange", "category", "sector", "industry", "isdelisted",
    "firstpricedate", "lastpricedate", "lastupdated",
]
_ACTIONS_COLS = ["date", "action", "ticker", "name", "value", "contraticker"]
_FUNDAMENTALS_COLS = [
    "ticker", "period", "fiscal_year", "period_end", "filing_date", "accepted_date",
    "revenue", "gross_profit", "operating_income", "ebitda", "net_income",
    "free_cash_flow", "total_debt", "total_equity", "total_assets",
    "shares_diluted", "enterprise_value", "lastupdated",
]
_INDEX_COLS = ["symbol", "date", "close", "lastupdated"]

_SCHEMA = """
-- survivorship-free daily prices (incl. delisted names)
CREATE TABLE IF NOT EXISTS sep (
  ticker      VARCHAR NOT NULL,
  date        DATE    NOT NULL,
  open        DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
  volume      BIGINT,
  closeadj    DOUBLE,        -- split/div-adjusted close — factors price from this
  closeunadj  DOUBLE,
  lastupdated DATE,
  PRIMARY KEY (ticker, date)
);

-- the as-of ticker universe (delisting flags + price-date bounds drive PIT eligibility)
CREATE TABLE IF NOT EXISTS tickers (
  ticker         VARCHAR PRIMARY KEY,
  name           VARCHAR, exchange VARCHAR, category VARCHAR,
  sector         VARCHAR, industry VARCHAR,   -- Sharadar classification (P10 §3 sector caps)
  isdelisted     BOOLEAN,
  firstpricedate DATE, lastpricedate DATE,
  lastupdated    DATE
);

-- corporate actions (splits / divs / delistings)
CREATE TABLE IF NOT EXISTS actions (
  date     DATE, action VARCHAR, ticker VARCHAR, name VARCHAR,
  value    DOUBLE, contraticker VARCHAR
);

-- ingest bookkeeping (idempotency; single-shot ingest — no checkpoint cursor)
CREATE TABLE IF NOT EXISTS ingest_runs (
  dataset VARCHAR, started_at TIMESTAMP, finished_at TIMESTAMP,
  rows    BIGINT, status VARCHAR   -- 'running'|'ok'|'failed'
);

-- point-in-time fundamentals (FMP /stable layer, ADR 0018). One row per
-- (ticker, period, period_end), merged across income/balance/cash-flow/key-metrics.
-- accepted_date = the SEC-acceptance timestamp = the date the statement was
-- KNOWABLE; the factor layer as-of-joins on accepted_date <= as_of (no look-ahead).
CREATE TABLE IF NOT EXISTS fundamentals (
  ticker           VARCHAR NOT NULL,
  period           VARCHAR,        -- 'FY' | 'Q1'..'Q4'
  fiscal_year      VARCHAR,
  period_end       DATE NOT NULL,  -- fiscal period end (FMP statement `date`)
  filing_date      DATE,           -- SEC filing date
  accepted_date    TIMESTAMP,      -- SEC accepted datetime (PIT knowable-on)
  revenue          DOUBLE,
  gross_profit     DOUBLE,
  operating_income DOUBLE,
  ebitda           DOUBLE,
  net_income       DOUBLE,
  free_cash_flow   DOUBLE,
  total_debt       DOUBLE,
  total_equity     DOUBLE,
  total_assets     DOUBLE,
  shares_diluted   DOUBLE,
  enterprise_value DOUBLE,
  lastupdated      TIMESTAMP,
  PRIMARY KEY (ticker, period, period_end)
);

-- index / regime daily series (e.g. ^VIX) sourced from FMP (P10 §5, ADR 0022).
-- Generic by `symbol` so future index series ride the same table. Point-in-time
-- by `date`; idempotent upsert keyed by (symbol, date).
CREATE TABLE IF NOT EXISTS index_prices (
  symbol      VARCHAR NOT NULL,
  date        DATE    NOT NULL,
  close       DOUBLE,
  lastupdated TIMESTAMP,
  PRIMARY KEY (symbol, date)
);
"""


def _to_bool(series: pd.Series) -> pd.Series:
    """Sharadar `isdelisted` arrives as 'Y'/'N' (or already bool). Normalize."""
    return series.map(
        lambda v: str(v).strip().upper() in {"Y", "TRUE", "1"} if v is not None else None
    )


class FactorDataStore:
    """Connection + schema + queries for the local DuckDB factor-data store."""

    def __init__(self, db_path: str | None = None, *, read_only: bool = False) -> None:
        self.path: Path = resolve_store_path(db_path)
        self.read_only = read_only
        # A read-only open of a non-existent file fails loudly — that's the point
        # (a missing store is an operator error, not a silent empty result).
        self.con = duckdb.connect(str(self.path), read_only=read_only)
        if not read_only:
            self.con.execute(_SCHEMA)
            # Additive migration for pre-sector stores (P10 §3): idempotent, so an
            # already-current schema is a no-op. Read-only opens skip it and rely
            # on get_sectors() degrading when the column is absent.
            for col in ("sector", "industry"):
                self.con.execute(f"ALTER TABLE tickers ADD COLUMN IF NOT EXISTS {col} VARCHAR")
        logger.info("factor_data_store_open", path=str(self.path), read_only=read_only)

    def __enter__(self) -> FactorDataStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self.con.close()

    # ---- ingest (idempotent) ------------------------------------------------

    def ingest_sep(self, df: pd.DataFrame) -> int:
        """Upsert daily prices. Keyed by (ticker, date) → re-ingest converges."""
        df = df.reindex(columns=_SEP_COLS)
        self.con.register("incoming", df)
        self.con.execute(
            """
            INSERT OR REPLACE INTO sep
            SELECT ticker, TRY_CAST(date AS DATE),
                   TRY_CAST(open AS DOUBLE), TRY_CAST(high AS DOUBLE),
                   TRY_CAST(low AS DOUBLE), TRY_CAST(close AS DOUBLE),
                   TRY_CAST(volume AS BIGINT), TRY_CAST(closeadj AS DOUBLE),
                   TRY_CAST(closeunadj AS DOUBLE), TRY_CAST(lastupdated AS DATE)
            FROM incoming
            WHERE ticker IS NOT NULL AND date IS NOT NULL
            """
        )
        self.con.unregister("incoming")
        return len(df)

    def ingest_tickers(self, df: pd.DataFrame) -> int:
        """Upsert the ticker reference table. Keyed by ticker → converges."""
        df = df.reindex(columns=_TICKERS_COLS).copy()
        df["isdelisted"] = _to_bool(df["isdelisted"])
        self.con.register("incoming", df)
        self.con.execute(
            """
            INSERT OR REPLACE INTO tickers
            SELECT ticker, name, exchange, category, sector, industry,
                   TRY_CAST(isdelisted AS BOOLEAN),
                   TRY_CAST(firstpricedate AS DATE), TRY_CAST(lastpricedate AS DATE),
                   TRY_CAST(lastupdated AS DATE)
            FROM incoming
            WHERE ticker IS NOT NULL
            """
        )
        self.con.unregister("incoming")
        return len(df)

    def ingest_actions(self, df: pd.DataFrame) -> int:
        """Replace corporate actions for the ingested tickers, then insert.

        `actions` has no natural primary key, so idempotency is scoped: rows for
        every ticker present in `df` are deleted before insert, so re-ingesting
        the same slice converges to the same state.
        """
        df = df.reindex(columns=_ACTIONS_COLS)
        self.con.register("incoming", df)
        self.con.execute(
            "DELETE FROM actions WHERE ticker IN (SELECT DISTINCT ticker FROM incoming)"
        )
        self.con.execute(
            """
            INSERT INTO actions
            SELECT TRY_CAST(date AS DATE), action, ticker, name,
                   TRY_CAST(value AS DOUBLE), contraticker
            FROM incoming
            WHERE ticker IS NOT NULL
            """
        )
        self.con.unregister("incoming")
        return len(df)

    def ingest_fundamentals(self, df: pd.DataFrame) -> int:
        """Upsert point-in-time fundamentals. Keyed by (ticker, period, period_end)
        → re-ingesting the same periods converges. ``df`` columns are reindexed to
        ``_FUNDAMENTALS_COLS`` (missing → NULL), so a caller that only has some
        statements still ingests cleanly."""
        df = df.reindex(columns=_FUNDAMENTALS_COLS)
        self.con.register("incoming", df)
        self.con.execute(
            """
            INSERT OR REPLACE INTO fundamentals
            SELECT ticker, period, fiscal_year, TRY_CAST(period_end AS DATE),
                   TRY_CAST(filing_date AS DATE), TRY_CAST(accepted_date AS TIMESTAMP),
                   TRY_CAST(revenue AS DOUBLE), TRY_CAST(gross_profit AS DOUBLE),
                   TRY_CAST(operating_income AS DOUBLE), TRY_CAST(ebitda AS DOUBLE),
                   TRY_CAST(net_income AS DOUBLE), TRY_CAST(free_cash_flow AS DOUBLE),
                   TRY_CAST(total_debt AS DOUBLE), TRY_CAST(total_equity AS DOUBLE),
                   TRY_CAST(total_assets AS DOUBLE), TRY_CAST(shares_diluted AS DOUBLE),
                   TRY_CAST(enterprise_value AS DOUBLE), TRY_CAST(lastupdated AS TIMESTAMP)
            FROM incoming
            WHERE ticker IS NOT NULL AND period_end IS NOT NULL
            """
        )
        self.con.unregister("incoming")
        return len(df)

    def ingest_index_prices(self, df: pd.DataFrame) -> int:
        """Upsert an index/regime daily series (e.g. ``^VIX``; P10 §5, ADR 0022).
        Keyed by (symbol, date) → re-ingesting the same dates converges. ``df`` is
        reindexed to ``_INDEX_COLS`` (missing → NULL)."""
        df = df.reindex(columns=_INDEX_COLS)
        self.con.register("incoming", df)
        self.con.execute(
            """
            INSERT OR REPLACE INTO index_prices
            SELECT symbol, TRY_CAST(date AS DATE), TRY_CAST(close AS DOUBLE),
                   TRY_CAST(lastupdated AS TIMESTAMP)
            FROM incoming
            WHERE symbol IS NOT NULL AND date IS NOT NULL
            """
        )
        self.con.unregister("incoming")
        return len(df)

    def record_ingest_run(
        self, dataset: str, started_at: datetime, finished_at: datetime,
        rows: int, status: str,
    ) -> None:
        self.con.execute(
            "INSERT INTO ingest_runs VALUES (?, ?, ?, ?, ?)",
            [dataset, started_at, finished_at, rows, status],
        )

    # ---- queries ------------------------------------------------------------

    def row_count(self, table: str) -> int:
        if table not in {"sep", "tickers", "actions", "ingest_runs", "fundamentals", "index_prices"}:
            raise ValueError(f"unknown table: {table}")
        row = self.con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        assert row is not None
        return int(row[0])

    def price_date_bounds(self) -> tuple[date | None, date | None]:
        """(min, max) date present in `sep`, or (None, None) if empty."""
        row = self.con.execute("SELECT MIN(date), MAX(date) FROM sep").fetchone()
        assert row is not None  # an aggregate query always returns one row
        return (row[0], row[1])

    def trading_days(self, start: date, end: date) -> list[date]:
        """Distinct `sep` trading dates in [start, end], ascending — the union
        trading calendar across all names (drives the backtest's day loop)."""
        rows = self.con.execute(
            "SELECT DISTINCT date FROM sep WHERE date BETWEEN ? AND ? ORDER BY date",
            [start, end],
        ).fetchall()
        return [r[0] for r in rows]

    def get_sectors(self, tickers: list[str]) -> dict[str, str | None]:
        """Map each requested ticker → its Sharadar `sector` (None if unknown).

        Defensive: a pre-sector store (no `sector` column yet, before the TICKERS
        re-ingest) yields all-None rather than raising, so the strategy's sector
        cap fails open. Every requested ticker is present in the result."""
        if not tickers:
            return {}
        cols = {r[1] for r in self.con.execute("PRAGMA table_info(tickers)").fetchall()}
        if "sector" not in cols:
            return {t: None for t in tickers}
        placeholders = ",".join(["?"] * len(tickers))
        rows = self.con.execute(
            f"SELECT ticker, sector FROM tickers WHERE ticker IN ({placeholders})",
            tickers,
        ).fetchall()
        found = {r[0]: r[1] for r in rows}
        return {t: found.get(t) for t in tickers}

    def get_prices(
        self, ticker: str, start: date, end: date, *, adjusted: bool = True
    ) -> pd.DataFrame:
        """Daily prices for `ticker` in [start, end].

        Returns history for DELISTED names too (the survivorship-free guarantee):
        a name absent from today's listings is *not* an unknown ticker, it is a
        name with a finite price history ending at its delisting. `adjusted=True`
        returns the split/dividend-adjusted close as `close`; raw otherwise.
        Empty frame (not an error) if no rows.
        """
        close_expr = "closeadj" if adjusted else "closeunadj"
        return self.con.execute(
            f"""
            SELECT ticker, date, open, high, low,
                   {close_expr} AS close, volume
            FROM sep
            WHERE ticker = ? AND date BETWEEN ? AND ?
            ORDER BY date
            """,
            [ticker, start, end],
        ).df()

    def get_index_series(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Daily closes for an index/regime series (e.g. ``^VIX``) in ``[start, end]``,
        ascending by date (P10 §5, ADR 0022). Columns ``[date, close]``; empty frame
        (not an error) if the symbol/window has no rows."""
        return self.con.execute(
            """
            SELECT date, close FROM index_prices
            WHERE symbol = ? AND date BETWEEN ? AND ?
            ORDER BY date
            """,
            [symbol, start, end],
        ).df()

    def get_fundamentals(
        self, ticker: str, as_of: date | None = None, *, period: str | None = None
    ) -> pd.DataFrame:
        """Point-in-time fundamentals for `ticker`, newest period first.

        When `as_of` is given, only rows **knowable on that date** are returned —
        ``accepted_date <= as_of`` (falling back to ``filing_date <= as_of`` when
        the acceptance timestamp is missing). This is the no-look-ahead guarantee:
        a statement filed after `as_of` is invisible. `period` optionally filters
        to 'FY' or a specific quarter. The factor layer typically takes the first
        (latest-known) row, or the trailing four for TTM. Empty frame if none.
        """
        clauses = ["ticker = ?"]
        params: list[object] = [ticker]
        if as_of is not None:
            clauses.append("COALESCE(accepted_date, filing_date) <= ?")
            params.append(as_of)
        if period is not None:
            clauses.append("period = ?")
            params.append(period)
        where = " AND ".join(clauses)
        return self.con.execute(
            f"SELECT * FROM fundamentals WHERE {where} ORDER BY period_end DESC",
            params,
        ).df()

    def dollar_volume_universe(
        self, as_of: date, n: int, lookback_days: int
    ) -> list[str]:
        """Top-`n` tickers by trailing dollar volume, tradeable as of `as_of`.

        Eligibility is point-in-time and survivorship-free: a ticker qualifies
        only if `as_of` falls within its [firstpricedate, lastpricedate] lifetime
        (so a name delisted before `as_of` is excluded, and a name delisted after
        but liquid *then* is included). Ranking is `SUM(close * volume)` over the
        trailing `lookback_days` calendar-day window. Deterministic: ties broken
        by ticker ascending.
        """
        window_start = pd.Timestamp(as_of) - pd.Timedelta(days=lookback_days)
        rows = self.con.execute(
            """
            WITH dv AS (
                SELECT ticker, SUM(close * volume) AS dollar_volume
                FROM sep
                WHERE date BETWEEN ? AND ?
                GROUP BY ticker
            )
            SELECT dv.ticker
            FROM dv
            JOIN tickers t ON t.ticker = dv.ticker
            WHERE t.firstpricedate IS NOT NULL
              AND t.lastpricedate IS NOT NULL
              AND t.firstpricedate <= ?
              AND t.lastpricedate >= ?
              AND dv.dollar_volume > 0
            ORDER BY dv.dollar_volume DESC, dv.ticker ASC
            LIMIT ?
            """,
            [window_start.date(), as_of, as_of, as_of, n],
        ).fetchall()
        return [r[0] for r in rows]
