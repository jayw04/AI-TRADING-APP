"""``GET /api/v1/range-insight/{symbol}`` — the Range Insight panel feed (P8 §5).

Deterministic statistical summaries of a symbol's recent daily behavior. No LLM,
no forecasting (Direction Decision 2) — the response carries a disclaimer. The
Charts-rail panel (§6) consumes this.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.range_insight import (
    RangeCandidatesResponse,
    RangeInsightResponse,
)
from app.auth.stub import CurrentUser, get_current_user
from app.db.session import get_session
from app.services.range_auto_select import load_range_backtest_evidence
from app.services.range_insight import (
    DEFAULT_CANDIDATE_UNIVERSE,
    compute_range_insight,
    rank_range_candidates,
)

router = APIRouter(prefix="/range-insight", tags=["range-insight"])


@router.get("/candidates", response_model=RangeCandidatesResponse)
async def get_range_candidates(
    request: Request,
    symbols: str | None = None,
    _user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RangeCandidatesResponse:
    """Rank a universe so a user can pick the best symbol(s) to range-trade today.
    EVIDENCE-FIRST: symbols with a realized range backtest rank by their win rate (then
    Sharpe); the rest fall back to the structural Range Score (normalized ATR% × how
    range-bound). ``symbols`` is an optional comma-separated override; otherwise the
    default liquid-large-cap universe.

    Declared before ``/{symbol}`` so the literal path wins the route match.
    """
    bar_cache = getattr(request.app.state, "bar_cache", None)
    if bar_cache is None:
        raise HTTPException(
            status_code=503, detail="range insight unavailable (bar cache not wired)"
        )
    universe = (
        [s for s in (symbols.split(",")) if s.strip()]
        if symbols
        else list(DEFAULT_CANDIDATE_UNIVERSE)
    )
    evidence = await load_range_backtest_evidence(session, universe)
    ranked = await rank_range_candidates(
        universe, bar_cache=bar_cache, now=datetime.now(UTC), evidence=evidence
    )
    return RangeCandidatesResponse(
        as_of=datetime.now(UTC),
        candidates=[asdict(c) for c in ranked],  # type: ignore[misc]
    )


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
