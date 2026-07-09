"""GAPPER-001 intraday auto-cache (pre-registration v0.2 §7).

For each daily gapper candidate, cache the **same-day** intraday (1-min + 5-min) bars for the three
series the entry rule needs: the **candidate**, **SPY**, and the candidate's **GICS sector SPDR**
(the 30-min OR break + VWAP + "market & sector positive" test). Sector is resolved from the factor
store's ``tickers.sector``; per v0.2 §7 an **unresolved sector excludes the candidate from the primary
replay** (no SPY-only fallback), so this reports that status rather than silently degrading.

Read-only research infrastructure: no order path, no LLM. Fetch failures are logged and surfaced
(fail-soft), never raised into a scheduler.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# Sharadar sector → SPDR sector ETF (the 11 GICS sectors).
SECTOR_SPDR: dict[str, str] = {
    "Technology": "XLK",
    "Communication Services": "XLC",
    "Financial Services": "XLF",
    "Healthcare": "XLV",
    "Industrials": "XLI",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Energy": "XLE",
    "Utilities": "XLU",
    "Basic Materials": "XLB",
    "Real Estate": "XLRE",
}
MARKET_ETF = "SPY"
INTRADAY_TFS = ("1Min", "5Min")


def resolve_sector_etf(con: Any, ticker: str) -> str | None:
    """The SPDR sector ETF for ``ticker`` via the factor store's ``tickers.sector``; ``None`` if the
    ticker or its sector cannot be resolved (⇒ the candidate is excluded from the primary replay)."""
    row = con.execute(
        "SELECT sector FROM tickers WHERE ticker = ? LIMIT 1", [ticker]
    ).fetchone()
    sector = row[0] if row else None
    return SECTOR_SPDR.get(sector) if sector else None


async def cache_symbol_day(bar_cache: Any, symbol: str, day: date) -> int:
    """Fetch + cache one day of 1-min and 5-min bars for ``symbol`` (the cache re-fetches only what it
    is missing). Returns the total bars now available for the day; 0 on a fetch failure."""
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    total = 0
    for tf in INTRADAY_TFS:
        try:
            df = await bar_cache.get_bars(symbol, tf, start, end)
            total += 0 if df is None or getattr(df, "empty", True) else int(len(df))
        except Exception as e:  # noqa: BLE001 — fail-soft; surface, don't raise
            logger.warning(
                "gapper_intraday_fetch_failed",
                symbol=symbol, timeframe=tf, day=str(day), error=str(e)[:120],
            )
    return total


async def cache_candidate_event(bar_cache: Any, con: Any, ticker: str, day: date) -> dict[str, Any]:
    """Cache the candidate + SPY + sector-ETF intraday bars for one ``(candidate, day)`` event.

    Returns a status dict: ``{ticker, day, sector_etf, cached, bars, excluded_reason}``. ``cached`` is
    True only when all three series have bars; ``excluded_reason`` is set (and the candidate dropped
    from the primary replay) when the sector is unresolved or the candidate's own intraday is missing."""
    sector_etf = resolve_sector_etf(con, ticker)
    if sector_etf is None:
        return {"ticker": ticker, "day": str(day), "sector_etf": None,
                "cached": False, "bars": {}, "excluded_reason": "sector_etf_unresolved"}
    bars: dict[str, int] = {}
    for sym in (ticker, MARKET_ETF, sector_etf):
        bars[sym] = await cache_symbol_day(bar_cache, sym, day)
    reason: str | None = None
    if bars.get(ticker, 0) == 0:
        reason = "candidate_intraday_missing"
    elif bars.get(MARKET_ETF, 0) == 0 or bars.get(sector_etf, 0) == 0:
        reason = "market_or_sector_intraday_missing"
    return {"ticker": ticker, "day": str(day), "sector_etf": sector_etf,
            "cached": reason is None, "bars": bars, "excluded_reason": reason}
