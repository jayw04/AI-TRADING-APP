"""Pydantic models for ``/api/v1/quotes`` and ``/api/v1/bars``."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class QuoteResponse(BaseModel):
    symbol: str
    bid: Decimal | None
    ask: Decimal | None
    last: Decimal | None
    bid_size: int | None
    ask_size: int | None
    ts: datetime | None
    source: str = "alpaca-iex"  # documenting the data source


class BarResponse(BaseModel):
    t: datetime
    o: Decimal
    h: Decimal
    l: Decimal  # noqa: E741 - ambiguous name "l" matches OHLCV convention
    c: Decimal
    v: int


class BarsResponse(BaseModel):
    symbol: str
    timeframe: str
    bars: list[BarResponse]


# ---- Indicators (P2 Session 1) ----


class IndicatorSeriesPoint(BaseModel):
    t: datetime
    v: float | None


class IndicatorSeries(BaseModel):
    name: str  # e.g. "RSI14"; multi-output indicators expand to "MACD.macd" etc.
    latest: float | None
    sparkline: list[IndicatorSeriesPoint]


class IndicatorsResponse(BaseModel):
    symbol: str
    timeframe: str
    last_bar_ts: datetime | None
    indicators: list[IndicatorSeries]
