"""MKT-PROJ-001 §0 data audit (pre-registration prerequisite; read-only).

Verifies, against the live Alpaca entitlement on the box, everything the frozen
configuration assumes:

1. Daily-bar depth + row counts for SPY/QQQ/IWM/DIA + the 11 SPDR sector ETFs
   (incl. XLRE/XLC's shorter histories, which the breadth features must handle PIT).
2. Minute-bar depth for SPY (year probes) + a sample day's 15:30–15:45 coverage
   for the pre-close feature window across the basket.
3. SIP-historical entitlement (training data path) vs IEX (live path).
4. Premarket gap sample (IEX snapshots) for the pre-open features.
5. MarketSession half-day awareness (the close−15m scheduling assumption).

Run inside the backend container:

    sudo docker exec workbench-backend python3 /app/data/mkt_proj_001/data_audit.py

Prints the audit JSON and saves a copy next to itself.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, date, datetime, timedelta

PROXIES = ["SPY", "QQQ", "IWM", "DIA"]
SECTORS = ["XLK", "XLF", "XLV", "XLE", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC"]
DAILY_START = date(2014, 1, 1)  # asks earlier than needed to find the true feed floor
MINUTE_PROBE_YEARS = [2016, 2017, 2018, 2020, 2022, 2024]


def main() -> int:
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest, StockSnapshotRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    from app.brokers.alpaca.credentials import load_credentials

    creds = load_credentials()
    client = StockHistoricalDataClient(api_key=creds.api_key, secret_key=creds.api_secret)
    out: dict = {"audit": "mkt_proj_001/v1", "at": datetime.now(UTC).isoformat()}

    def bars(symbols, tf, start, end, feed):
        req = StockBarsRequest(symbol_or_symbols=symbols, timeframe=tf,
                               start=start, end=end, feed=feed)
        return client.get_stock_bars(req).data

    # 1. daily depth per symbol (SIP historical = the training path)
    daily: dict[str, dict] = {}
    for sym in PROXIES + SECTORS:
        try:
            data = bars(sym, TimeFrame.Day, DAILY_START, date.today(), DataFeed.SIP)
            rows = data.get(sym, [])
            daily[sym] = {
                "ok": bool(rows),
                "earliest": rows[0].timestamp.date().isoformat() if rows else None,
                "latest": rows[-1].timestamp.date().isoformat() if rows else None,
                "rows": len(rows),
            }
        except Exception as exc:  # noqa: BLE001
            daily[sym] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}
    out["daily_sip"] = daily

    # 2a. SPY minute-bar year probes (one January week per probe year)
    minute_probe: dict[str, dict] = {}
    for year in MINUTE_PROBE_YEARS:
        try:
            data = bars("SPY", TimeFrame(1, TimeFrameUnit.Minute),
                        date(year, 1, 5), date(year, 1, 12), DataFeed.SIP)
            rows = data.get("SPY", [])
            minute_probe[str(year)] = {"rows": len(rows),
                                       "first": rows[0].timestamp.isoformat() if rows else None}
        except Exception as exc:  # noqa: BLE001
            minute_probe[str(year)] = {"error": f"{type(exc).__name__}: {exc}"[:160]}
    out["spy_minute_probe_sip"] = minute_probe

    # 2b. pre-close window coverage on a recent full session (yesterday-ish)
    d = date.today() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    window: dict[str, int] = {}
    try:
        start = datetime(d.year, d.month, d.day, 19, 30, tzinfo=UTC)   # 15:30 ET (EDT)
        end = datetime(d.year, d.month, d.day, 19, 45, tzinfo=UTC)     # 15:45 ET
        data = bars(PROXIES + SECTORS, TimeFrame(1, TimeFrameUnit.Minute), start, end, DataFeed.SIP)
        window = {sym: len(data.get(sym, [])) for sym in PROXIES + SECTORS}
    except Exception as exc:  # noqa: BLE001
        window = {"error": f"{type(exc).__name__}: {exc}"[:160]}  # type: ignore[dict-item]
    out["preclose_window_coverage"] = {"date": d.isoformat(), "minute_rows_1530_1545_et": window}

    # 3. feed entitlement cross-check: same historical day via IEX for comparison
    try:
        data = bars("SPY", TimeFrame.Day, d - timedelta(days=7), d, DataFeed.IEX)
        out["iex_daily_ok"] = bool(data.get("SPY"))
    except Exception as exc:  # noqa: BLE001
        out["iex_daily_ok"] = f"{type(exc).__name__}: {exc}"[:160]

    # 4. premarket gap sample (IEX snapshots — the live pre-open path)
    try:
        snaps = client.get_stock_snapshot(
            StockSnapshotRequest(symbol_or_symbols=["SPY", "QQQ", "IWM"], feed=DataFeed.IEX)
        )
        gaps = {}
        for sym, snap in snaps.items():
            lt, prev = snap.latest_trade, snap.previous_daily_bar
            gaps[sym] = {
                "latest_trade_ts": lt.timestamp.isoformat() if lt else None,
                "gap_pct": round((lt.price - prev.close) / prev.close * 100, 3)
                if lt and prev else None,
            }
        out["premarket_gap_sample_iex"] = gaps
    except Exception as exc:  # noqa: BLE001
        out["premarket_gap_sample_iex"] = {"error": f"{type(exc).__name__}: {exc}"[:160]}

    # 5. MarketSession half-day awareness
    try:
        from app.market.session import MarketSession
        ms = MarketSession()
        info = ms.classify()
        out["market_session"] = {
            "now_session": str(getattr(info, "session", None) or getattr(info, "session_type", None)),
            "is_half_day": bool(getattr(info, "is_half_day", False)),
        }
    except Exception as exc:  # noqa: BLE001
        out["market_session"] = {"error": f"{type(exc).__name__}: {exc}"[:160]}

    text = json.dumps(out, indent=2, default=str)
    print(text)
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, f"data_audit_{date.today().isoformat()}.json"),
                  "w", encoding="utf-8") as fh:
            fh.write(text)
    except OSError as exc:
        print(f"WARN could not save copy: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
