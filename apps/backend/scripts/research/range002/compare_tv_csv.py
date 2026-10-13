"""Compare a TradingView chart CSV export with the stored SIP minute bars for one symbol-day.

    python -I compare_tv_csv.py --csv EXPORT.csv --store STORE.duckdb --symbol AAPL --day 2017-03-01 \\
        --tv-symbol "NASDAQ:AAPL" --tv-feed "<as shown on the chart>" --tv-interval 1 \\
        --tv-timezone "America/New_York" --tv-session "regular" --tv-adjustment "none" --out OUT.json

Supported input only: the CSV the chart's own "Export chart data" produces (columns ``time``,
``open``, ``high``, ``low``, ``close`` and a volume column). The recorded provenance arguments are
required (no defaults) and are copied into the output; the output is private to the owner and is
stamped as personal-use data. Counts only: minutes in both, minutes only on TradingView (a
discrepancy finding: TradingView has a bar where the stored provider has none), minutes only in
the store, and exact OHLCV agreement counts. Absence in both proves nothing about trading.
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb

_ET = ZoneInfo("America/New_York")


def parse_tv_time(text: str) -> datetime:
    """ISO 8601 with offset ('2017-03-01T09:30:00-05:00') or a UNIX epoch (seconds)."""
    t = text.strip()
    if t.isdigit():
        return datetime.fromtimestamp(int(t), tz=UTC).astimezone(_ET)
    dt = datetime.fromisoformat(t.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError(f"timestamp {text!r} has no UTC offset; export with timezone information")
    return dt.astimezone(_ET)


def read_csv(path: Path, day: date) -> dict[str, tuple[float, float, float, float, float]]:
    out: dict[str, tuple[float, float, float, float, float]] = {}
    with open(path, newline="", encoding="utf-8") as fh:
        rd = csv.DictReader(fh)
        cols = {c.lower(): c for c in (rd.fieldnames or [])}
        vol_col = next((cols[c] for c in ("volume", "vol") if c in cols), None)
        for need in ("time", "open", "high", "low", "close"):
            if need not in cols:
                raise ValueError(f"CSV lacks a {need!r} column (found {list(cols)})")
        for row in rd:
            ts = parse_tv_time(row[cols["time"]])
            if ts.date() != day:
                continue
            out[ts.strftime("%H:%M")] = (
                float(row[cols["open"]]),
                float(row[cols["high"]]),
                float(row[cols["low"]]),
                float(row[cols["close"]]),
                float(row[vol_col]) if vol_col else float("nan"),
            )
    return out


def read_store(
    store: Path, symbol: str, day: date
) -> dict[str, tuple[float, float, float, float, float]]:
    con = duckdb.connect(str(store), read_only=True)
    try:
        rows = con.execute(
            "SELECT ts, open, high, low, close, volume FROM minute_bars WHERE symbol = ?", [symbol]
        ).fetchall()
    finally:
        con.close()
    out: dict[str, tuple[float, float, float, float, float]] = {}
    for ts, o, h, low, c, v in rows:
        local = ts.replace(tzinfo=UTC).astimezone(_ET)
        if local.date() == day:
            out[local.strftime("%H:%M")] = (float(o), float(h), float(low), float(c), float(v))
    return out


def compare(
    tv: dict[str, tuple[float, ...]], store: dict[str, tuple[float, ...]], *, rth_only: bool = True
) -> dict[str, Any]:
    def regular(m: str) -> bool:
        return "09:30" <= m <= "15:59"

    tv_m = {m for m in tv if regular(m)} if rth_only else set(tv)
    st_m = {m for m in store if regular(m)} if rth_only else set(store)
    both = sorted(tv_m & st_m)
    price_eq = sum(1 for m in both if tv[m][:4] == store[m][:4])
    vol_eq = sum(1 for m in both if tv[m][4] == store[m][4])
    return {
        "minutes_tradingview": len(tv_m),
        "minutes_store": len(st_m),
        "minutes_in_both": len(both),
        "minutes_only_tradingview": sorted(tv_m - st_m),
        "minutes_only_store": sorted(st_m - tv_m),
        "ohlc_exact_equal_in_both": price_eq,
        "volume_exact_equal_in_both": vol_eq,
        "note": "a minute only on TradingView is a discrepancy finding; absence in both proves "
        "nothing about whether trades occurred",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ("csv", "store", "out"):
        ap.add_argument(f"--{name}", required=True, type=Path)
    for name in (
        "symbol",
        "day",
        "tv-symbol",
        "tv-feed",
        "tv-interval",
        "tv-timezone",
        "tv-session",
        "tv-adjustment",
    ):
        ap.add_argument(f"--{name}", required=True)
    a = ap.parse_args()
    if a.out.exists():
        raise SystemExit(f"{a.out} exists; never overwritten")
    day = date.fromisoformat(a.day)
    res = compare(read_csv(a.csv, day), read_store(a.store, a.symbol, day))
    res["provenance"] = {
        "tradingview": {
            "symbol": a.tv_symbol,
            "feed": a.tv_feed,
            "interval": a.tv_interval,
            "timezone": a.tv_timezone,
            "session": a.tv_session,
            "adjustment": a.tv_adjustment,
            "csv": a.csv.name,
        },
        "store": {"symbol": a.symbol, "day": a.day, "path": a.store.name},
        "license_scope": "PERSONAL (alpaca_market_data + TradingView data): private to the owner",
    }
    a.out.write_text(json.dumps(res, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"wrote {a.out}: both={res['minutes_in_both']} tv_only={len(res['minutes_only_tradingview'])} "
        f"store_only={len(res['minutes_only_store'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
