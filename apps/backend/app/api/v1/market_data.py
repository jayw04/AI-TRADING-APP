"""REST endpoints for quotes + historical bars (IEX free feed)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query

from app.api.v1.schemas.market_data import BarResponse, BarsResponse, QuoteResponse
from app.market_data.quotes import get_last_quote

router = APIRouter(tags=["market-data"])


@router.get("/quotes/{symbol}", response_model=QuoteResponse)
async def get_quote(symbol: str) -> QuoteResponse:
    q = await get_last_quote(symbol)
    if q is None:
        raise HTTPException(
            status_code=503, detail="Quote unavailable (IEX free tier)"
        )
    return QuoteResponse(
        symbol=q["symbol"],
        bid=Decimal(q["bid"]) if q["bid"] else None,
        ask=Decimal(q["ask"]) if q["ask"] else None,
        last=Decimal(q["last"]) if q["last"] else None,
        bid_size=q.get("bid_size"),
        ask_size=q.get("ask_size"),
        ts=datetime.fromisoformat(q["ts"]) if q.get("ts") else None,
    )


@router.get("/bars/{symbol}", response_model=BarsResponse)
async def get_bars(
    symbol: str,
    timeframe: str = Query(
        default="1Min", description="1Min | 5Min | 15Min | 1Hour | 1Day"
    ),
    start: str | None = None,
    end: str | None = None,
    limit: int = Query(default=100, ge=1, le=10_000),
) -> BarsResponse:
    """Return historical OHLCV bars for one symbol (Alpaca free IEX feed)."""
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    from app.brokers.alpaca.credentials import load_credentials

    tf_map = {
        "1Min": TimeFrame(1, TimeFrameUnit.Minute),
        "5Min": TimeFrame(5, TimeFrameUnit.Minute),
        "15Min": TimeFrame(15, TimeFrameUnit.Minute),
        "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
        "1Day": TimeFrame(1, TimeFrameUnit.Day),
    }
    if timeframe not in tf_map:
        raise HTTPException(
            status_code=400, detail=f"Unsupported timeframe: {timeframe}"
        )

    end_dt = datetime.fromisoformat(end) if end else datetime.now(UTC)
    start_dt = datetime.fromisoformat(start) if start else (end_dt - timedelta(days=5))

    creds = load_credentials()
    client = StockHistoricalDataClient(
        api_key=creds.api_key, secret_key=creds.api_secret
    )
    req = StockBarsRequest(
        symbol_or_symbols=symbol.upper(),
        timeframe=tf_map[timeframe],
        start=start_dt,
        end=end_dt,
        feed=DataFeed.IEX,
        limit=limit,
    )
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(None, lambda: client.get_stock_bars(req))
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Bars unavailable: {exc}"
        ) from exc

    bars_raw = result.data.get(symbol.upper(), []) if hasattr(result, "data") else []
    return BarsResponse(
        symbol=symbol.upper(),
        timeframe=timeframe,
        bars=[
            BarResponse(
                t=b.timestamp,
                o=Decimal(str(b.open)),
                h=Decimal(str(b.high)),
                l=Decimal(str(b.low)),
                c=Decimal(str(b.close)),
                v=int(b.volume),
            )
            for b in bars_raw
        ],
    )
