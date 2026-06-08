"""``GET /api/v1/range-insight/{symbol}`` — the Range Insight panel feed (P8 §5).

Deterministic statistical summaries of a symbol's recent daily behavior. No LLM,
no forecasting (Direction Decision 2) — the response carries a disclaimer. The
Charts-rail panel (§6) consumes this.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.v1.schemas.range_insight import RangeInsightResponse
from app.auth.stub import CurrentUser, get_current_user
from app.services.range_insight import compute_range_insight

router = APIRouter(prefix="/range-insight", tags=["range-insight"])


@router.get("/{symbol}", response_model=RangeInsightResponse)
async def get_range_insight(
    symbol: str,
    request: Request,
    _user: CurrentUser = Depends(get_current_user),
) -> RangeInsightResponse:
    bar_cache = getattr(request.app.state, "bar_cache", None)
    if bar_cache is None:
        raise HTTPException(
            status_code=503, detail="range insight unavailable (bar cache not wired)"
        )
    insight = await compute_range_insight(
        symbol, bar_cache=bar_cache, now=datetime.now(UTC)
    )
    return RangeInsightResponse(**asdict(insight))
