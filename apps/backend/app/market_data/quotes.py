"""Quote fetch helpers with a tiny in-process cache.

alpaca-py's data clients are sync — we wrap calls in ``run_in_executor`` so
they don't block the FastAPI event loop. The 1-second cache prevents
hammering Alpaca's free-tier rate limit if multiple components request the
same quote nearly simultaneously.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

_QUOTE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_QUOTE_TTL_SECONDS = 1.0
_lock = asyncio.Lock()


async def get_last_quote(symbol: str) -> dict[str, Any] | None:
    """Return the most recent quote for a symbol, cached for 1s.

    Returns dict with bid/ask/last/ts or None if Alpaca refuses / no IEX quote.
    """
    symbol = symbol.upper()
    now = time.time()
    cached = _QUOTE_CACHE.get(symbol)
    if cached and now - cached[0] < _QUOTE_TTL_SECONDS:
        return cached[1]

    async with _lock:
        # Double-check under the lock so we don't fire two requests for the
        # same symbol in tight succession.
        cached = _QUOTE_CACHE.get(symbol)
        if cached and now - cached[0] < _QUOTE_TTL_SECONDS:
            return cached[1]

        loop = asyncio.get_running_loop()
        try:
            from alpaca.data.enums import DataFeed
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockLatestQuoteRequest

            from app.brokers.alpaca.credentials import load_credentials

            creds = load_credentials()
            client = StockHistoricalDataClient(
                api_key=creds.api_key, secret_key=creds.api_secret
            )
            req = StockLatestQuoteRequest(
                symbol_or_symbols=symbol, feed=DataFeed.IEX
            )
            result = await loop.run_in_executor(
                None, lambda: client.get_stock_latest_quote(req)
            )
            q = result[symbol] if isinstance(result, dict) else result
            ts_obj = getattr(q, "timestamp", None)
            payload: dict[str, Any] = {
                "symbol": symbol,
                "bid": str(getattr(q, "bid_price", None) or ""),
                "ask": str(getattr(q, "ask_price", None) or ""),
                "last": str(
                    getattr(q, "ask_price", None)
                    or getattr(q, "bid_price", None)
                    or ""
                ),
                "bid_size": getattr(q, "bid_size", None),
                "ask_size": getattr(q, "ask_size", None),
                "ts": ts_obj.isoformat() if ts_obj is not None else None,
            }
            _QUOTE_CACHE[symbol] = (now, payload)
            return payload
        except Exception:
            return None
