#!/usr/bin/env python3
"""Range Top-5 execution-quality report — BUY/SELL fills vs. daily high/low, ON DEMAND.

The range-fade thesis is *buy near the low, sell near the high*. This report measures whether
our fills actually land there, via "placement":

    Buy placement  = (buy  - low) / (high - low)   0.00 = bought the exact low  (ideal)
    Sell placement = (sell - low) / (high - low)   1.00 = sold the exact high   (ideal)

Nothing is stored or scheduled: the data already lives in the database (fills in orders/fills)
and the bar cache (each day's RTH high/low, re-fetchable from Alpaca for any past date). Run it
whenever you want a report, for a single day or a range:

    # single day (the Top-5 grid)
    python /app/scripts/reports/range_price_tracker.py --date 2026-07-07

    # a window: per-fill execution records + a per-symbol placement summary
    python /app/scripts/reports/range_price_tracker.py --from 2026-07-01 --to 2026-07-31
    python /app/scripts/reports/range_price_tracker.py --days 30        # last 30 days

Runs INSIDE the backend container (reads the sqlite book + the 1Day bar-cache parquet directly;
no broker adapter needed). Fills are matched by UTC date; during RTH (13:30-20:00 UTC) the UTC and
ET calendar dates coincide, which is when the intraday range book trades.
"""
from __future__ import annotations

import argparse
import glob
from datetime import UTC, datetime, timedelta

import sqlite3

DB = "/app/data/workbench.sqlite"
CACHE_ROOT = "/app/bars_cache"
RANGE_USER_ID = 2  # the Range Trader paper book (user 2 / account 2)
FALLBACK_TOP5 = ["GOOGL", "MU", "INTC", "AMD", "TSLA"]


def _con() -> sqlite3.Connection:
    return sqlite3.connect(DB)


def top5_symbols(con: sqlite3.Connection) -> list[str]:
    """Current Range Trader Top-5 (symbols_json), falling back to a constant."""
    row = con.execute(
        "select symbols_json from strategies where name like 'Range Trader%' order by id limit 1"
    ).fetchone()
    if row and row[0]:
        import json

        try:
            syms = [s.upper() for s in json.loads(row[0])]
            if syms:
                return syms
        except (ValueError, TypeError):
            pass
    return FALLBACK_TOP5


def fills_in_range(con: sqlite3.Connection, dfrom: str, dto: str) -> list[dict]:
    """One row per (ET date, ticker, side) with the qty-weighted avg fill price."""
    rows = con.execute(
        """
        select substr(o.created_at, 1, 10) as d, sy.ticker as ticker, o.side as side,
               f.qty as qty, f.price as price
        from orders o
        join fills f on f.order_id = o.id
        join symbols sy on sy.id = o.symbol_id
        where o.user_id = ? and substr(o.created_at, 1, 10) between ? and ?
        """,
        (RANGE_USER_ID, dfrom, dto),
    ).fetchall()
    agg: dict[tuple[str, str, str], list[float]] = {}
    for d, ticker, side, qty, price in rows:
        key = (d, ticker.upper(), side)
        q, n = agg.get(key, [0.0, 0.0])
        agg[key] = [q + float(qty), n + float(qty) * float(price)]
    return [
        {"date": d, "symbol": t, "side": s, "price": n / q}
        for (d, t, s), (q, n) in sorted(agg.items())
        if q > 0
    ]


def daily_hl(symbol: str, date: str) -> tuple[float, float] | None:
    """RTH (low, high) for the symbol on the date from the 1Day bar-cache parquet."""
    import pandas as pd

    files = glob.glob(f"{CACHE_ROOT}/{symbol}/1Day/{date[:7]}.parquet")
    if not files:
        return None
    df = pd.read_parquet(files[0])
    df["d"] = pd.to_datetime(df["t"]).dt.strftime("%Y-%m-%d")
    r = df[df["d"] == date]
    if r.empty:
        return None
    row = r.iloc[0]
    return (float(row["l"]), float(row["h"]))


def _pl(price: float | None, low: float, high: float) -> float | None:
    if price is None or high <= low:
        return None
    return (price - low) / (high - low)


def _f(x: float | None, nd: int = 2) -> str:
    return f"{x:.{nd}f}" if x is not None else "—"


def report_single_day(date: str) -> str:
    con = _con()
    syms = top5_symbols(con)
    fills = {(f["symbol"], f["side"]): f["price"] for f in fills_in_range(con, date, date)}
    con.close()
    wd = datetime.strptime(date, "%Y-%m-%d").strftime("%a")
    out = [f"## Range Top-5 — {date} ({wd})", "",
           "| Symbol | Buy | Sell | Low | High | Buy pl. | Sell pl. |",
           "|---|---|---|---|---|---|---|"]
    for s in syms:
        buy, sell = fills.get((s, "BUY")), fills.get((s, "SELL"))
        hl = daily_hl(s, date)
        if hl is None:
            out.append(f"| {s} | {_f(buy)} | {_f(sell)} | ? | ? | — | — |")
            continue
        low, high = hl
        out.append(f"| {s} | {_f(buy)} | {_f(sell)} | {low:.2f} | {high:.2f} | "
                   f"{_f(_pl(buy, low, high))} | {_f(_pl(sell, low, high))} |")
    out += ["", "*Buy placement 0.00 = bought the low (ideal fade); "
            "Sell placement 1.00 = sold the high (ideal).*"]
    return "\n".join(out)


def report_range(dfrom: str, dto: str) -> str:
    con = _con()
    records = fills_in_range(con, dfrom, dto)
    con.close()
    for r in records:
        hl = daily_hl(r["symbol"], r["date"])
        r["low"], r["high"] = (hl if hl else (None, None))
        r["pl"] = _pl(r["price"], r["low"], r["high"]) if hl else None

    out = [f"# Range Top-5 execution vs. daily range — {dfrom} … {dto}", ""]
    if not records:
        return "\n".join(out + ["_No range fills in this window._"])
    out += ["| Date | Symbol | Side | Fill | Low | High | Placement |",
            "|---|---|---|---|---|---|---|"]
    for r in records:
        out.append(f"| {r['date']} | {r['symbol']} | {r['side']} | {r['price']:.2f} | "
                   f"{_f(r['low'])} | {_f(r['high'])} | {_f(r['pl'])} |")

    # Per-symbol placement summary.
    out += ["", "## Summary — average placement per symbol", "",
            "| Symbol | Buys | Avg buy pl. | Sells | Avg sell pl. |",
            "|---|---|---|---|---|"]
    syms = sorted({r["symbol"] for r in records})
    for s in syms:
        buys = [r["pl"] for r in records if r["symbol"] == s and r["side"] == "BUY" and r["pl"] is not None]
        sells = [r["pl"] for r in records if r["symbol"] == s and r["side"] == "SELL" and r["pl"] is not None]
        avb = sum(buys) / len(buys) if buys else None
        avs = sum(sells) / len(sells) if sells else None
        out.append(f"| {s} | {len(buys)} | {_f(avb)} | {len(sells)} | {_f(avs)} |")
    out += ["", "*Lower avg buy-placement = buying nearer the low (good fade entries); "
            "higher avg sell-placement = selling nearer the high.*"]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", help="Single ET date YYYY-MM-DD (Top-5 grid).")
    ap.add_argument("--from", dest="dfrom", help="Range start YYYY-MM-DD.")
    ap.add_argument("--to", dest="dto", help="Range end YYYY-MM-DD.")
    ap.add_argument("--days", type=int, help="Range = last N days ending today.")
    args = ap.parse_args()

    today = datetime.now(UTC).strftime("%Y-%m-%d")
    if args.days:
        dfrom = (datetime.now(UTC) - timedelta(days=args.days)).strftime("%Y-%m-%d")
        print(report_range(dfrom, today))
    elif args.dfrom or args.dto:
        print(report_range(args.dfrom or "2000-01-01", args.dto or today))
    else:
        print(report_single_day(args.date or today))


if __name__ == "__main__":
    main()
