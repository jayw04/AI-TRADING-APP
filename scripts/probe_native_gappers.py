"""GAP-NATIVE-001 §1.0 pre-flight probe (read-only).

Answers Q1 of Docs/implementation/TradingWorkbench_GAP-NATIVE-001_Session1_v0.1.md:
does the Alpaca movers screener reflect *premarket* trading under our data
entitlement, and is premarket volume visible in snapshots (IEX)?

Run inside the backend container on the box, ideally 08:45-09:15 ET on a
trading day (off-hours it shows last-session data — still validates plumbing):

    sudo docker exec workbench-backend python3 /app/data/native_gapper_probe/probe_native_gappers.py

Read-only: market-data GETs only. No orders, no DB, no LLM, no writes outside
its own output file. Prints the probe JSON to stdout and saves a copy next to
itself as probe_<ET-date>_<HHMM>.json.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")
LIQUID_CONTROLS = ["AAPL", "TSLA", "NVDA", "SPY", "AMD"]
MOVERS_TOP = 20
SNAPSHOT_MOVERS = 5  # top-N movers to snapshot alongside the controls


def _iso(ts: object) -> str | None:
    return ts.isoformat() if isinstance(ts, datetime) else (str(ts) if ts else None)


def _snapshot_row(snap: object) -> dict[str, object]:
    lt = getattr(snap, "latest_trade", None)
    prev = getattr(snap, "previous_daily_bar", None)
    daily = getattr(snap, "daily_bar", None)
    row: dict[str, object] = {
        "latest_trade_price": getattr(lt, "price", None),
        "latest_trade_ts": _iso(getattr(lt, "timestamp", None)),
        "prev_close": getattr(prev, "close", None),
        "prev_bar_ts": _iso(getattr(prev, "timestamp", None)),
        "daily_bar_volume": getattr(daily, "volume", None),
        "daily_bar_ts": _iso(getattr(daily, "timestamp", None)),
    }
    price, prev_close = row["latest_trade_price"], row["prev_close"]
    if price and prev_close:
        row["computed_gap_pct"] = round((float(price) - float(prev_close)) / float(prev_close) * 100, 2)
    return row


def main() -> int:
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.historical.screener import ScreenerClient
    from alpaca.data.requests import MarketMoversRequest, StockSnapshotRequest

    from app.brokers.alpaca.credentials import load_credentials

    creds = load_credentials()
    now_utc = datetime.now(UTC)
    now_et = now_utc.astimezone(EASTERN)
    out: dict[str, object] = {
        "probe": "gap_native_001/v1",
        "at_utc": now_utc.isoformat(),
        "at_et": now_et.isoformat(),
        "paper": creds.paper,
    }

    # --- movers (discovery path A candidate) ---
    import time as _time

    try:
        screener = ScreenerClient(api_key=creds.api_key, secret_key=creds.api_secret)
        _t = _time.monotonic()
        movers = screener.get_market_movers(MarketMoversRequest(top=MOVERS_TOP))
        _movers_elapsed = round(_time.monotonic() - _t, 2)
        gainers = list(getattr(movers, "gainers", []) or [])
        last_updated = getattr(movers, "last_updated", None)
        out["movers"] = {
            "ok": True,
            "elapsed_s": _movers_elapsed,
            "last_updated": _iso(last_updated),
            "last_updated_is_today_et": (
                last_updated.astimezone(EASTERN).date() == now_et.date()
                if isinstance(last_updated, datetime) else None
            ),
            "gainers": [
                {"symbol": m.symbol, "percent_change": m.percent_change, "price": m.price}
                for m in gainers
            ],
        }
    except Exception as exc:  # noqa: BLE001 - probe records, never raises
        gainers = []
        out["movers"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    # --- snapshots (verification stage + path-B feasibility) ---
    symbols = [m.symbol for m in gainers[:SNAPSHOT_MOVERS]] + LIQUID_CONTROLS
    symbols = list(dict.fromkeys(symbols))  # dedupe, keep order
    data_client = StockHistoricalDataClient(api_key=creds.api_key, secret_key=creds.api_secret)
    for feed in (DataFeed.IEX, DataFeed.SIP):  # SIP attempt = entitlement check only
        key = f"snapshots_{feed.value}"
        try:
            _t = _time.monotonic()
            snaps = data_client.get_stock_snapshot(
                StockSnapshotRequest(symbol_or_symbols=symbols, feed=feed)
            )
            out[key] = {
                "ok": True,
                "elapsed_s": round(_time.monotonic() - _t, 2),
                "rows": {s: _snapshot_row(snap) for s, snap in snaps.items()},
            }
        except Exception as exc:  # noqa: BLE001
            out[key] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    # --- path-B timing sample (review §4): one full 200-unique-symbol snapshot batch ---
    try:
        batch: list[str] = []
        try:  # real store tickers when available (box); measures a representative batch
            import duckdb

            con = duckdb.connect("/app/data/factor_data.duckdb", read_only=True)
            batch = [r[0] for r in con.execute(
                "SELECT DISTINCT ticker FROM sep WHERE date = (SELECT max(date) FROM sep) "
                "ORDER BY ticker LIMIT 200"
            ).fetchall()]
            con.close()
        except Exception:  # noqa: BLE001 - store absent (laptop run) → skip
            pass
        if len(batch) >= 50:
            _t = _time.monotonic()
            data_client.get_stock_snapshot(
                StockSnapshotRequest(symbol_or_symbols=batch, feed=DataFeed.IEX)
            )
            out["path_b_batch_timing"] = {
                "ok": True,
                "batch_size": len(batch),
                "elapsed_s": round(_time.monotonic() - _t, 2),
                "note": "path B = ~5 such batches for a 1000-name sweep",
            }
        else:
            out["path_b_batch_timing"] = {"ok": False, "error": "factor store unavailable"}
    except Exception as exc:  # noqa: BLE001
        out["path_b_batch_timing"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    # --- verdict hints (decision matrix, session doc §1.0) ---
    iex = out.get("snapshots_iex") or {}
    iex_rows = iex.get("rows", {}) if isinstance(iex, dict) else {}
    controls_with_pm_volume = [
        s for s in LIQUID_CONTROLS
        if str((iex_rows.get(s) or {}).get("daily_bar_ts") or "")[:10] == now_et.date().isoformat()
        and ((iex_rows.get(s) or {}).get("daily_bar_volume") or 0) > 0
    ]
    in_window = now_et.weekday() < 5 and "08:00" <= now_et.strftime("%H:%M") <= "09:30"
    out["verdict_hints"] = {
        "in_premarket_window": in_window,
        "movers_live_today": (out.get("movers") or {}).get("last_updated_is_today_et"),
        "controls_with_premarket_volume": controls_with_pm_volume,
        "sip_entitled": bool((out.get("snapshots_sip") or {}).get("ok")),
        "note": "Path A needs movers_live_today during the premarket window; stop-and-escalate "
                "if controls_with_premarket_volume is empty in-window (session doc §1.0).",
    }

    text = json.dumps(out, indent=2, default=str)
    print(text)
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        fname = f"probe_{now_et.date().isoformat()}_{now_et.strftime('%H%M')}.json"
        with open(os.path.join(here, fname), "w", encoding="utf-8") as fh:
            fh.write(text)
    except OSError as exc:
        print(f"WARN could not save copy: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
