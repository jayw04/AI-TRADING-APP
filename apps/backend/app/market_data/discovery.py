"""Alpaca discovery feeds (most-actives + market-movers) with a short cache.

The candidate-symbol seed source for the P8 Discovery screener (§2) and the
Discovery view (§3). Alpaca's screener endpoints are intraday-volatile and the
free tier is rate-limited, so fetches sit behind a 5-minute in-process TTL
cache — the same shape ``app/market_data/quotes.py`` uses for latest quotes
(in-process dict + TTL + ``asyncio.Lock`` + lazy SDK import + ``run_in_executor``).

On a fetch failure the last cached payload is served with ``stale=True``; if
there is no cache at all an empty feed with ``error`` set is returned. The
Discovery feed never hard-fails the page.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

# Cache keyed by ``top`` (the requested feed depth). Each entry is
# ``(fetched_at_monotonic_walltime, payload)``.
_FEED_CACHE: dict[int, tuple[float, dict[str, Any]]] = {}
_FEED_TTL_SECONDS = 300.0
_lock = asyncio.Lock()

# Generic, fixed error string — we never surface a raw exception (it can carry
# internal / credential-adjacent detail) in the API response.
_UNAVAILABLE = "discovery feeds unavailable"


def _iso(value: Any) -> str | None:
    """Best-effort ISO string for Alpaca's feed ``last_updated`` timestamp."""
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return isoformat()
    return str(value)


def _mover(m: Any) -> dict[str, Any]:
    return {
        "symbol": m.symbol,
        "percent_change": m.percent_change,
        "change": m.change,
        "price": m.price,
    }


def _fetch_from_alpaca(top: int) -> dict[str, Any]:
    """Synchronously fetch both screener feeds. Wrapped in an executor by the
    caller (alpaca-py's clients are sync). Lazy-imports the SDK like quotes.py.
    """
    from typing import cast

    from alpaca.data.historical.screener import ScreenerClient
    from alpaca.data.models.screener import MostActives, Movers
    from alpaca.data.requests import MarketMoversRequest, MostActivesRequest

    from app.brokers.alpaca.credentials import load_credentials

    creds = load_credentials()
    # raw_data=False (default) → the client returns the typed models, not dicts.
    client = ScreenerClient(api_key=creds.api_key, secret_key=creds.api_secret)
    actives = cast(MostActives, client.get_most_actives(MostActivesRequest(top=top)))
    movers = cast(Movers, client.get_market_movers(MarketMoversRequest(top=top)))
    return {
        "most_actives": [
            {"symbol": a.symbol, "volume": a.volume, "trade_count": a.trade_count}
            for a in actives.most_actives
        ],
        "gainers": [_mover(m) for m in movers.gainers],
        "losers": [_mover(m) for m in movers.losers],
        "last_updated": _iso(getattr(actives, "last_updated", None)),
    }


def _empty(error: str | None) -> dict[str, Any]:
    return {
        "most_actives": [],
        "gainers": [],
        "losers": [],
        "last_updated": None,
        "stale": False,
        "error": error,
    }


async def get_discovery_feeds(top: int = 20) -> dict[str, Any]:
    """Return the cached most-actives + movers feeds.

    Shape: ``{most_actives, gainers, losers, last_updated, stale, error}``.
    Fresh cache hit → returned as-is (``stale=False``). On a live-fetch error,
    a warm cache is served with ``stale=True``; a cold cache yields an empty
    feed with ``error`` set. Never raises.
    """
    now = time.time()
    cached = _FEED_CACHE.get(top)
    if cached and now - cached[0] < _FEED_TTL_SECONDS:
        return {**cached[1], "stale": False, "error": None}

    async with _lock:
        # Double-check under the lock so we don't fire two fetches at once.
        cached = _FEED_CACHE.get(top)
        if cached and now - cached[0] < _FEED_TTL_SECONDS:
            return {**cached[1], "stale": False, "error": None}

        loop = asyncio.get_running_loop()
        try:
            payload = await loop.run_in_executor(
                None, lambda: _fetch_from_alpaca(top)
            )
        except Exception:
            stale = _FEED_CACHE.get(top)
            if stale is not None:
                return {**stale[1], "stale": True, "error": _UNAVAILABLE}
            return _empty(_UNAVAILABLE)

        _FEED_CACHE[top] = (now, payload)
        return {**payload, "stale": False, "error": None}
