"""P10 R2 — ingest FMP /stable fundamentals into the DuckDB factor store.

Host-venv entrypoint (no Docker, no stack), same posture as ingest_sharadar.py.
Idempotent: fundamentals are keyed by (ticker, period, period_end) → re-running
converges. For each ticker it pulls income / balance-sheet / cash-flow /
key-metrics from FMP's /stable API, merges them per fiscal period, maps to the
store's `fundamentals` schema, and upserts. The SEC `acceptedDate` is preserved as
the point-in-time "knowable-on" timestamp the factor layer as-of-joins against.

    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
        apps/backend/scripts/ingest_fmp.py --tickers AAPL,MSFT,NVDA --period annual

Scope: pass an explicit ticker list/file (or --universe-from-store N to take the
store's top-N liquid names). FMP statements are per-symbol; mind the tier rate
limit on a broad universe.

Key hygiene (ADR 0018 §5): the key is read from FMP_API_KEY and never logged.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import truststore  # ADR 0017 — OS trust store before any HTTPS

truststore.inject_into_ssl()

try:
    from dotenv import load_dotenv

    _root = Path(__file__).resolve().parents[3]
    for _env in (_root / ".env", _root / "apps" / "backend" / ".env"):
        if _env.exists():
            load_dotenv(_env, override=False)
except Exception:
    pass

import pandas as pd  # noqa: E402

from app.factor_data.providers.fmp import FMPConfigError, FMPProvider  # noqa: E402
from app.factor_data.store import FactorDataStore  # noqa: E402

# FMP /stable field name → store column. Split by statement so a missing
# statement (a ticker FMP lacks balance-sheet for) just leaves those columns NULL.
_INCOME_MAP = {
    "date": "period_end", "period": "period", "fiscalYear": "fiscal_year",
    "filingDate": "filing_date", "acceptedDate": "accepted_date",
    "revenue": "revenue", "grossProfit": "gross_profit",
    "operatingIncome": "operating_income", "ebitda": "ebitda",
    "netIncome": "net_income", "weightedAverageShsOutDil": "shares_diluted",
}
_BALANCE_MAP = {
    "totalDebt": "total_debt", "totalStockholdersEquity": "total_equity",
    "totalAssets": "total_assets",
}
_CASHFLOW_MAP = {"freeCashFlow": "free_cash_flow"}
_KEYMETRICS_MAP = {"enterpriseValue": "enterprise_value"}


def build_fundamentals_frame(
    ticker: str,
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cashflow: pd.DataFrame,
    key_metrics: pd.DataFrame,
) -> pd.DataFrame:
    """Merge the four FMP statements for one ticker into a store-shaped frame.

    Income is the base (it carries the PIT dates); balance/cash-flow/key-metrics
    are left-merged on the fiscal period (`date` + `period`). Pure (no I/O), so
    the field mapping is unit-testable. Returns an empty frame if `income` is empty.
    """
    if income is None or income.empty:
        return pd.DataFrame(columns=["ticker", "period_end", "period"])
    base = income.reindex(columns=list(_INCOME_MAP)).rename(columns=_INCOME_MAP)
    base["ticker"] = ticker

    def _merge(df: pd.DataFrame, mapping: dict[str, str]) -> None:
        nonlocal base
        if df is None or df.empty:
            for c in mapping.values():
                if c not in base:
                    base[c] = pd.NA
            return
        keep = ["date", "period", *mapping]
        right = df.reindex(columns=keep).rename(
            columns={"date": "period_end", **mapping}
        )
        base = base.merge(right, on=["period_end", "period"], how="left")

    _merge(balance, _BALANCE_MAP)
    _merge(cashflow, _CASHFLOW_MAP)
    _merge(key_metrics, _KEYMETRICS_MAP)
    return base


def _parse_tickers(args: argparse.Namespace, store: FactorDataStore) -> list[str]:
    raw: list[str] = []
    if args.tickers:
        raw += [t.strip() for t in args.tickers.split(",")]
    if args.tickers_file:
        text = Path(args.tickers_file).read_text(encoding="utf-8")
        raw += [line.strip() for line in text.replace(",", "\n").splitlines()]
    if args.universe_from_store:
        _, latest = store.price_date_bounds()
        if latest is not None:
            raw += store.dollar_volume_universe(latest, n=args.universe_from_store, lookback_days=63)
    seen: dict[str, None] = {}
    for t in raw:
        t = t.upper()
        if t and t not in seen:
            seen[t] = None
    return list(seen)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Ingest FMP /stable fundamentals into DuckDB.")
    ap.add_argument("--tickers", help="comma-separated tickers")
    ap.add_argument("--tickers-file", help="file of tickers (comma- or newline-separated)")
    ap.add_argument("--universe-from-store", type=int, metavar="N",
                    help="also ingest the store's top-N liquid names (latest date)")
    ap.add_argument("--period", default="annual", choices=["annual", "quarter"])
    ap.add_argument("--limit", type=int, default=40, help="statements per ticker (default 40)")
    ap.add_argument("--db", help="override store path (default: WORKBENCH_FACTOR_DATA_DB_PATH)")
    args = ap.parse_args(argv)

    try:
        provider = FMPProvider()
    except FMPConfigError as e:
        print(str(e), file=sys.stderr)
        return 1

    store = FactorDataStore(db_path=args.db)
    try:
        tickers = _parse_tickers(args, store)
        if not tickers:
            print("no tickers — pass --tickers/--tickers-file/--universe-from-store", file=sys.stderr)
            return 2
        total = len(tickers)
        now = datetime.now()
        for i, tk in enumerate(tickers, 1):
            started = datetime.now()
            try:
                p = args.period
                lim = args.limit
                frame = build_fundamentals_frame(
                    tk,
                    provider.income_statement(tk, period=p, limit=lim),
                    provider.balance_sheet(tk, period=p, limit=lim),
                    provider.cash_flow(tk, period=p, limit=lim),
                    provider.key_metrics(tk, period=p, limit=lim),
                )
                frame["lastupdated"] = now
                rows = store.ingest_fundamentals(frame)
                store.record_ingest_run(f"fmp_fundamentals:{tk}", started, datetime.now(), rows, "ok")
                print(f"[{i}/{total}] {tk}: {rows} periods")
            except Exception as e:  # noqa: BLE001 — log + continue so one bad ticker doesn't abort the run
                store.record_ingest_run(f"fmp_fundamentals:{tk}", started, datetime.now(), 0, "failed")
                print(f"[{i}/{total}] {tk}: FAILED {e!r}", file=sys.stderr)
        print(f"\nfundamentals rows in store: {store.row_count('fundamentals')}")
    finally:
        store.close()
        provider.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
