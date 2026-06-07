"""``GET /api/v1/discovery/feeds`` — Alpaca most-actives + market-movers (P8 §1).

The candidate-symbol seed source for the Discovery screener (§2) and view (§3).
Backed by a 5-minute in-memory TTL cache; never 5xx on an Alpaca blip — see
``app/market_data/discovery.py`` for the stale-on-error semantics.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.v1.schemas.discovery import DiscoveryFeedsResponse
from app.auth.stub import CurrentUser, get_current_user
from app.market_data.discovery import get_discovery_feeds

router = APIRouter(prefix="/discovery", tags=["discovery"])


@router.get("/feeds", response_model=DiscoveryFeedsResponse)
async def get_feeds(
    top: int = Query(20, ge=1, le=100, description="feed depth per list"),
    _user: CurrentUser = Depends(get_current_user),
) -> DiscoveryFeedsResponse:
    return DiscoveryFeedsResponse(**await get_discovery_feeds(top))
