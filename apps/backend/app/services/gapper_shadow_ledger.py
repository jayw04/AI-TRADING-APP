"""GAPPER-001 shadow-ledger service (pre-registration v0.2 §8).

For a trading day, apply the **locked primary design** to the cached intraday bars of that day's
candidates and persist a shadow-ledger record: per-candidate outcomes + the daily equal-weight book
(slippage grid + breakeven). **Forward observation only (Backtest Pending)** — no CI, no promotion.
Read-only / fail-soft. Reused by the ~16:40 ET daily job and the historical backfill.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd
import structlog

from app.factor_data.gapper_intraday import MARKET_ETF, resolve_sector_etf
from app.factor_data.gapper_shadow import candidate_outcome, day_book

logger = structlog.get_logger(__name__)
LEDGER_SCHEMA = "gapper_001_shadow_ledger/v1"


async def _prev_close(bar_cache: Any, symbol: str, day: date) -> float | None:
    """The prior trading day's daily close for ``symbol`` (for the market/sector-positive test)."""
    start = datetime(day.year, day.month, day.day, tzinfo=UTC) - timedelta(days=12)
    end = datetime(day.year, day.month, day.day, tzinfo=UTC)
    try:
        df = await bar_cache.get_bars(symbol, "1Day", start, end)
    except Exception:  # noqa: BLE001
        return None
    if df is None or getattr(df, "empty", True):
        return None
    d = df.copy()
    d["_d"] = pd.to_datetime(d["t"], utc=True).dt.date
    prior = d[d["_d"] < day]
    return float(prior.iloc[-1]["c"]) if not prior.empty else None


async def _day_bars(bar_cache: Any, symbol: str, day: date) -> pd.DataFrame | None:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    try:
        return await bar_cache.get_bars(symbol, "1Min", start, end)
    except Exception:  # noqa: BLE001
        return None


def _persist(record: dict, ledger_dir: str, asof: date) -> str:
    os.makedirs(ledger_dir, exist_ok=True)
    path = os.path.join(ledger_dir, f"shadow_{asof.isoformat()}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, default=str)
    return path


async def compute_day_ledger(
    bar_cache: Any, con: Any, *, evidence_dir: str, ledger_dir: str, asof: date
) -> dict | None:
    """Compute + persist the shadow ledger for ``asof``. Returns the record, or ``None`` if there is no
    premarket candidate record for the day (a clean no-op)."""
    rec_path = os.path.join(evidence_dir, f"premarket_scan_{asof.isoformat()}.json")
    if not os.path.exists(rec_path):
        return None
    with open(rec_path, encoding="utf-8") as fh:
        candidates = json.load(fh).get("candidates", [])

    spy_prev = await _prev_close(bar_cache, MARKET_ETF, asof)
    spy_bars = await _day_bars(bar_cache, MARKET_ETF, asof)
    sector_cache: dict[str, tuple] = {}
    rows: list[dict] = []
    confidences: dict[str, float] = {}
    for c in candidates:
        ticker = c.get("symbol")
        if not ticker:
            continue
        confidences[ticker] = float(c.get("confidence") or 0.0)
        sector_etf = resolve_sector_etf(con, ticker)
        if sector_etf is None:
            rows.append({"ticker": ticker, "triggered": False, "reason": "sector_etf_unresolved"})
            continue
        if sector_etf not in sector_cache:
            sector_cache[sector_etf] = (
                await _day_bars(bar_cache, sector_etf, asof),
                await _prev_close(bar_cache, sector_etf, asof),
            )
        sec_bars, sec_prev = sector_cache[sector_etf]
        outcome = candidate_outcome(
            await _day_bars(bar_cache, ticker, asof), spy_bars, sec_bars,
            spy_prev_close=spy_prev, sector_prev_close=sec_prev,
        )
        outcome.update({"ticker": ticker, "sector_etf": sector_etf})
        rows.append(outcome)

    book = day_book(rows, confidences=confidences)
    record = {
        "schema": LEDGER_SCHEMA, "asof": asof.isoformat(), "status": "Backtest Pending",
        "note": "Forward observation only — not a validated trading signal; entry-spread deferred to a "
                "quote-data source, cost via the pre-registered slippage grid.",
        "spy_prev_close": spy_prev, "rows": rows, "book": book,
    }
    path = _persist(record, ledger_dir, asof)
    logger.info(
        "gapper_shadow_ledger_day", asof=str(asof), candidates=len(candidates),
        triggered=book["n_triggered"], book_gross_bps=book["book_gross_bps"], path=path,
    )
    return record
