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

v2 (2026-07-17) — FIXES THE PREMARKET-VOLUME CHECK.
------------------------------------------------------------------
v1's `controls_with_premarket_volume` asked whether the snapshot's *daily bar*
was stamped today with volume > 0. Before 09:30 today's daily bar does not exist
yet (the snapshot carries the prior session's), so that condition was
**structurally always false in the premarket window, for every symbol, on any
entitlement**. The 2026-07-13 08:50 ET run consequently reported `[]` and read as
"IEX cannot see premarket volume" — that was a measurement artifact, not a
finding, and it must not be used to justify a SIP upgrade.

v2 measures the thing the name claims: it sums **1Min bar volume from 04:00 ET
today to now** (the actual premarket session), per symbol, on the IEX feed. The
old daily-bar quantity is retained as `controls_with_today_daily_bar` — an
explicit diagnostic, labelled as NOT a premarket signal — so the v1 mis-read
stays visible in the record rather than being quietly erased.
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
PREMARKET_OPEN_ET_HOUR = 4  # US equities premarket session opens 04:00 ET


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


def _premarket_volume_1min(
    data_client: object, symbols: list[str], now_et: datetime, now_utc: datetime
) -> dict[str, object]:
    """Premarket volume per symbol = sum of 1Min bar volume from 04:00 ET today → now (IEX).

    This is the correct measurement for "is premarket volume visible?": the premarket session
    trades in minute bars, and the daily bar for today does not exist until the 09:30 open — so
    the daily bar can never answer the question in-window (that was the v1 defect).
    """
    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    start_et = now_et.replace(
        hour=PREMARKET_OPEN_ET_HOUR, minute=0, second=0, microsecond=0
    )
    result: dict[str, object] = {
        "window_start_et": start_et.isoformat(),
        "window_end_et": now_et.isoformat(),
        "feed": "iex",
        "method": "sum(1Min bar volume) from 04:00 ET today to now",
    }
    try:
        import time as _time

        _t = _time.monotonic()
        bars = data_client.get_stock_bars(  # type: ignore[attr-defined]
            StockBarsRequest(
                symbol_or_symbols=symbols,
                timeframe=TimeFrame.Minute,
                start=start_et.astimezone(UTC),
                end=now_utc,
                feed=DataFeed.IEX,
            )
        )
        result["elapsed_s"] = round(_time.monotonic() - _t, 2)
    except Exception as exc:  # noqa: BLE001 - probe records, never raises
        result["ok"] = False
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    data = getattr(bars, "data", None) or {}
    rows: dict[str, object] = {}
    for sym in symbols:
        blist = list(data.get(sym) or [])
        rows[sym] = {
            "bars": len(blist),
            "premarket_volume": sum(float(getattr(b, "volume", 0) or 0) for b in blist),
            "first_bar_ts": _iso(getattr(blist[0], "timestamp", None)) if blist else None,
            "last_bar_ts": _iso(getattr(blist[-1], "timestamp", None)) if blist else None,
        }
    result["ok"] = True
    result["rows"] = rows
    return result


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
        "probe": "gap_native_001/v2",
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

    # --- premarket volume, measured correctly (v2 fix) ---
    out["premarket_volume_1min"] = _premarket_volume_1min(data_client, symbols, now_et, now_utc)

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
    pmv = out.get("premarket_volume_1min") or {}
    pmv_rows = pmv.get("rows", {}) if isinstance(pmv, dict) else {}

    # v2: the real check — did this symbol actually trade in the 04:00 ET → now session?
    controls_with_pm_volume = [
        s for s in LIQUID_CONTROLS
        if float((pmv_rows.get(s) or {}).get("premarket_volume") or 0) > 0
    ]
    movers_with_pm_volume = [
        s for s in symbols if s not in LIQUID_CONTROLS
        and float((pmv_rows.get(s) or {}).get("premarket_volume") or 0) > 0
    ]
    # v1's quantity, retained as an explicit diagnostic ONLY. Structurally always empty before
    # 09:30 (today's daily bar does not exist yet) — it is NOT a premarket-volume signal, and it
    # is what made the 2026-07-13 run look like an entitlement failure.
    controls_with_today_daily_bar = [
        s for s in LIQUID_CONTROLS
        if str((iex_rows.get(s) or {}).get("daily_bar_ts") or "")[:10] == now_et.date().isoformat()
        and ((iex_rows.get(s) or {}).get("daily_bar_volume") or 0) > 0
    ]
    in_window = now_et.weekday() < 5 and "08:00" <= now_et.strftime("%H:%M") <= "09:30"
    out["verdict_hints"] = {
        "in_premarket_window": in_window,
        "movers_live_today": (out.get("movers") or {}).get("last_updated_is_today_et"),
        "controls_with_premarket_volume": controls_with_pm_volume,
        "movers_with_premarket_volume": movers_with_pm_volume,
        "premarket_volume_visible": bool(controls_with_pm_volume),
        "sip_entitled": bool((out.get("snapshots_sip") or {}).get("ok")),
        "controls_with_today_daily_bar": controls_with_today_daily_bar,
        "daily_bar_diagnostic_note": (
            "NOT a premarket signal — today's daily bar does not exist before 09:30, so this is "
            "structurally empty in-window on any entitlement. Retained only to document the v1 "
            "defect that produced the 2026-07-13 mis-read."
        ),
        "note": "Path A needs movers_live_today during the premarket window. Premarket-volume "
                "visibility is now measured from 1Min bars (04:00 ET → now), not the daily bar; "
                "stop-and-escalate if controls_with_premarket_volume is empty in-window "
                "(session doc §1.0).",
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
