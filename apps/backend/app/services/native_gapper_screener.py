"""Box-native premarket gapper screener (GAP-NATIVE-001, ADR 0041).

Produces the day's ``premarket_gappers_<YYYY-MM-DD>.json`` **on the box** from
Alpaca market data, replacing the laptop scanner as the authoritative source
(owner directive 2026-07-10: operational inputs must not depend on the PC).
The output is byte-compatible with the external scanner's schema — the SCAN-001
premarket scan and the Opportunities panel consume it unchanged — plus a
``source`` field so gate evidence carries its provenance.

Pipeline (session doc §1.2):

1. **Discovery** — Alpaca movers screener, gainers side (path A). If it yields
   nothing and a factor store is available, degrade to a dollar-volume-universe
   snapshot sweep (path B; honest scope: the store is small-cap-sparse).
2. **Verification** — one snapshot call per 200-symbol batch (IEX): the gap is
   recomputed as latest_trade vs previous close, so even a stale movers ranking
   cannot fake a gap. Names whose latest IEX print is not from today are dropped
   (the 2026-07-10 probe found months-old "latest" trades on illiquid names).
3. **Filter + rank** — the external scanner's exact thresholds (strictly
   greater: gap > 5%, price > $3, premarket volume > 50k), top 10 by gap.

Boundaries (mirroring ``premarket_gappers.py``): read-only market data via the
already-approved Alpaca dependency; advisory only — never the OrderRouter, no
LLM import (``catalyst`` is ``null`` by design); fail-soft — ``scan_native_gappers``
returns ``{"ok": False, ...}`` on any error, it never raises into the scheduler.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import UTC, date, datetime
from typing import Any

import structlog

from app.utils.time import EASTERN

logger = structlog.get_logger(__name__)

# Filter parity with the external scanner (claude-trading-view/premarket_gappers.sh:40-42).
# Same thresholds, same strict-greater semantics — parity is what lets the SCAN-001 accrual
# survive the source change (ADR 0041).
MIN_GAP_PCT = 5.0
MIN_PRICE = 3.0
MIN_PREMARKET_VOL = 50_000
TOP_N = 10

MOVERS_TOP = 50  # API ceiling for the movers screener
SNAPSHOT_BATCH = 200
STORE_SWEEP_N = 1000  # path-B universe size (top-N by trailing dollar volume)
STORE_SWEEP_LOOKBACK_DAYS = 30
SOURCE = "box_native_alpaca_v1"

# Plain common-stock tickers only: the movers tape includes warrants/units
# (EONR.WS, MVSTW) and sub-penny instruments the external scanner's Yahoo
# gainers table never surfaced. Suffixed symbols are dropped at discovery.
_PLAIN_SYMBOL_RE = re.compile(r"^[A-Z]{1,5}$")


def _default_clients() -> tuple[Any, Any]:
    """Screener + historical-data clients from the app's Alpaca credentials (sync)."""
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.historical.screener import ScreenerClient

    from app.brokers.alpaca.credentials import load_credentials

    creds = load_credentials()
    return (
        ScreenerClient(api_key=creds.api_key, secret_key=creds.api_secret),
        StockHistoricalDataClient(api_key=creds.api_key, secret_key=creds.api_secret),
    )


def _discover_movers(screener: Any) -> list[str]:
    """Path A: gainers side of the movers screener, plain symbols only."""
    from alpaca.data.requests import MarketMoversRequest

    movers = screener.get_market_movers(MarketMoversRequest(top=MOVERS_TOP))
    gainers = getattr(movers, "gainers", None) or []
    return [m.symbol for m in gainers if _PLAIN_SYMBOL_RE.match(str(m.symbol or ""))]


def _discover_store_sweep(factor_store: Any, today: date) -> list[str]:
    """Path B: the store's dollar-volume universe, anchored to its own latest close
    (the store only ever reaches the prior close — the #406 re-anchor pattern)."""
    row = factor_store.con.execute("SELECT max(date) FROM sep").fetchone()
    latest = row[0] if row else None
    if latest is None:
        return []
    eff = latest if isinstance(latest, date) else latest.date()
    as_of = min(eff, today)
    return list(
        factor_store.dollar_volume_universe(as_of, STORE_SWEEP_N, STORE_SWEEP_LOOKBACK_DAYS)
    )


def _gapper_row(symbol: str, snap: Any, *, today: date) -> dict[str, Any] | None:
    """One snapshot → an unranked gapper row, or None if it cannot be gap-verified.

    Drops: missing/zero prices, and any name whose latest IEX print is not from
    ``today`` (ET) — a stale print makes the computed gap fiction, not evidence.
    Premarket volume counts only when today's daily bar has started accumulating."""
    lt = getattr(snap, "latest_trade", None)
    prev = getattr(snap, "previous_daily_bar", None)
    daily = getattr(snap, "daily_bar", None)
    price = float(getattr(lt, "price", 0) or 0)
    prev_close = float(getattr(prev, "close", 0) or 0)
    ts = getattr(lt, "timestamp", None)
    if price <= 0 or prev_close <= 0 or not isinstance(ts, datetime):
        return None
    if ts.astimezone(EASTERN).date() != today:
        return None
    dts = getattr(daily, "timestamp", None)
    pm_vol = (
        float(getattr(daily, "volume", 0) or 0)
        if isinstance(dts, datetime) and dts.astimezone(EASTERN).date() == today
        else 0.0
    )
    gap_pct = (price - prev_close) / prev_close * 100.0
    return {
        "symbol": symbol,
        "price": price,
        "gap_pct": round(gap_pct, 2),
        "premarket_volume": int(pm_vol),
    }


def _snapshot_rows(
    data_client: Any, symbols: list[str], *, today: date
) -> tuple[list[dict[str, Any]], int]:
    """Verify discovered symbols via batched IEX snapshots.

    Returns ``(rows, with_snapshot)``: verified rows (current-print names only)
    plus how many symbols returned any snapshot at all — the difference is the
    stale/missing-print drop, surfaced in the morning funnel (review §5)."""
    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockSnapshotRequest

    rows: list[dict[str, Any]] = []
    with_snapshot = 0
    for i in range(0, len(symbols), SNAPSHOT_BATCH):
        batch = symbols[i : i + SNAPSHOT_BATCH]
        snaps = data_client.get_stock_snapshot(
            StockSnapshotRequest(symbol_or_symbols=batch, feed=DataFeed.IEX)
        )
        for sym, snap in (snaps or {}).items():
            with_snapshot += 1
            row = _gapper_row(str(sym), snap, today=today)
            if row is not None:
                rows.append(row)
    return rows, with_snapshot


def _filter_rank(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """External-scanner-parity filter (strict >) → top-N by gap, ranked 1..N.

    Gainers only (positive gap): the external scanner reads the *gainers* table,
    and the SCAN-001 Candidate Engine was framed on up-gaps. Also returns the
    per-criterion pass counts (independent, not sequential — the criteria are
    conjunctive) for the morning funnel."""
    counts = {
        "passing_gap": sum(1 for r in rows if r["gap_pct"] > MIN_GAP_PCT),
        "passing_price": sum(1 for r in rows if r["price"] > MIN_PRICE),
        "passing_volume": sum(1 for r in rows if r["premarket_volume"] > MIN_PREMARKET_VOL),
    }
    kept = [
        r
        for r in rows
        if r["gap_pct"] > MIN_GAP_PCT
        and r["price"] > MIN_PRICE
        and r["premarket_volume"] > MIN_PREMARKET_VOL
    ]
    kept.sort(key=lambda r: (-r["gap_pct"], r["symbol"]))
    ranked = [
        {"rank": i, **r, "catalyst": None, "headlines": []}
        for i, r in enumerate(kept[:TOP_N], start=1)
    ]
    return ranked, counts


async def scan_native_gappers(
    *,
    factor_store: Any = None,
    now: datetime | None = None,
    screener_client: Any = None,
    data_client: Any = None,
) -> dict[str, Any]:
    """Discover → verify → filter → rank. Returns a status dict; never raises.

    On success: ``{"ok": True, "date", "discovery_path", "count", "funnel",
    "payload"}`` where ``payload`` is the file-ready gappers document and
    ``funnel`` is the morning diagnostic (review §5): symbols_discovered →
    symbols_with_snapshot → symbols_with_current_premarket_trade → per-criterion
    pass counts → final_count. Clients are injectable for tests; by default both
    are built from the app's Alpaca credentials. Sync SDK calls run in the
    default executor."""
    import time as _time

    now_utc = now or datetime.now(UTC)
    today = now_utc.astimezone(EASTERN).date()
    loop = asyncio.get_running_loop()
    t0 = _time.monotonic()
    try:
        if screener_client is None or data_client is None:
            screener_client, data_client = await loop.run_in_executor(None, _default_clients)

        discovery_path = "movers"
        try:
            symbols = await loop.run_in_executor(None, _discover_movers, screener_client)
        except Exception:
            logger.exception("native_gapper_movers_failed")
            symbols = []
        if not symbols and factor_store is not None:
            discovery_path = "store_sweep"
            symbols = await loop.run_in_executor(
                None, _discover_store_sweep, factor_store, today
            )
        if not symbols:
            return {"ok": False, "reason": "no_discovery_symbols",
                    "discovery_path": discovery_path}

        rows, with_snapshot = await loop.run_in_executor(
            None, lambda: _snapshot_rows(data_client, symbols, today=today)
        )
        gappers, pass_counts = _filter_rank(rows)
        funnel = {
            "discovery_path": discovery_path,
            "symbols_discovered": len(symbols),
            "symbols_with_snapshot": with_snapshot,
            "symbols_with_current_premarket_trade": len(rows),
            **pass_counts,
            "final_count": len(gappers),
            "elapsed_s": round(_time.monotonic() - t0, 1),
        }
        return {
            "ok": True,
            "date": today.isoformat(),
            "discovery_path": discovery_path,
            "count": len(gappers),
            "funnel": funnel,
            "payload": {
                "scanned_at": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "source": SOURCE,
                "gappers": gappers,
            },
        }
    except Exception as exc:  # noqa: BLE001 - fail-soft boundary (scheduler-facing)
        logger.exception("native_gapper_scan_error")
        return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}


def write_gappers_file(payload: dict[str, Any], directory: str, *, date_str: str) -> str:
    """Atomically write ``premarket_gappers_<date>.json`` (tmp + replace, same
    directory so the rename never crosses filesystems): the 09:25 consumer globs
    the directory, so a half-written file must be impossible. ``source`` is a
    required contract of every native file (ADR 0041 provenance)."""
    if not payload.get("source"):
        raise ValueError("native gappers payload must carry a 'source' (ADR 0041)")
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"premarket_gappers_{date_str}.json")
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    os.replace(tmp, path)
    return path
