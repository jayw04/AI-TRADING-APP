"""``GET /api/v1/indicators/{symbol}`` — computed indicators for a symbol.

Pulls bars from :class:`app.market_data.bar_cache.BarCache`, runs them
through :class:`app.indicators.IndicatorComputer`, returns the latest value
plus a short trailing sparkline for each requested indicator.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request

from app.api.v1.schemas.market_data import (
    IndicatorSeries,
    IndicatorSeriesPoint,
    IndicatorsResponse,
)
from app.indicators import CORE_INDICATORS

router = APIRouter(prefix="/indicators", tags=["market-data"])


# Bars to pull per timeframe. Tuned so the slowest indicator (SMA200) has
# headroom on every timeframe, with room for the sparkline window.
_LOOKBACK_DAYS_BY_TF: dict[str, int] = {
    "1Min": 2,
    "5Min": 5,
    "15Min": 7,
    "1Hour": 14,
    "1Day": 365,
}


@router.get("/{symbol}", response_model=IndicatorsResponse)
async def get_indicators(
    symbol: str,
    request: Request,
    timeframe: str = Query(default="1Min"),
    names: str | None = Query(
        default=None,
        description="Comma-separated indicator names. Defaults to the core set.",
    ),
    sparkline_points: int = Query(default=30, ge=1, le=200),
) -> IndicatorsResponse:
    symbol = symbol.upper()

    if names is None or names.strip() == "":
        requested = list(CORE_INDICATORS)
    else:
        requested = [n.strip() for n in names.split(",") if n.strip()]
        unknown = [n for n in requested if n not in CORE_INDICATORS]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown indicators: {unknown}. Supported: {CORE_INDICATORS}",
            )

    bar_cache = getattr(request.app.state, "bar_cache", None)
    computer = getattr(request.app.state, "indicator_computer", None)
    if bar_cache is None or computer is None:
        raise HTTPException(
            status_code=503, detail="Indicator service not initialized"
        )

    end = datetime.now(UTC)
    start = end - timedelta(days=_LOOKBACK_DAYS_BY_TF.get(timeframe, 5))

    try:
        bars = await bar_cache.get_bars(symbol, timeframe, start, end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if bars.empty:
        return IndicatorsResponse(
            symbol=symbol,
            timeframe=timeframe,
            last_bar_ts=None,
            indicators=[],
        )

    computed = computer.compute(
        bars, names=requested, symbol=symbol, timeframe=timeframe
    )

    series_out: list[IndicatorSeries] = []
    for name in requested:
        value = computed.get(name)
        if isinstance(value, dict):
            # Multi-output: expand into "NAME.sub" entries.
            for sub_name, sub_series in value.items():
                series_out.append(
                    _build_series(f"{name}.{sub_name}", sub_series, bars, sparkline_points)
                )
        else:
            series_out.append(_build_series(name, value, bars, sparkline_points))

    return IndicatorsResponse(
        symbol=symbol,
        timeframe=timeframe,
        last_bar_ts=bars["t"].iloc[-1],
        indicators=series_out,
    )


def _build_series(
    name: str,
    series: pd.Series | None,
    bars: pd.DataFrame,
    points: int,
) -> IndicatorSeries:
    if series is None or series.empty:
        return IndicatorSeries(name=name, latest=None, sparkline=[])
    tail = series.tail(points)
    tail_t = bars["t"].tail(points).to_list()
    sparkline = [
        IndicatorSeriesPoint(
            t=pd.Timestamp(t).to_pydatetime(),
            v=None if pd.isna(v) else float(v),
        )
        for t, v in zip(tail_t, tail.to_list(), strict=False)
    ]
    latest_val = series.iloc[-1]
    latest = None if pd.isna(latest_val) else float(latest_val)
    return IndicatorSeries(name=name, latest=latest, sparkline=sparkline)
