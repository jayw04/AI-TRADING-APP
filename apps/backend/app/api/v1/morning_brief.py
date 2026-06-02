"""/api/v1/morning-brief endpoints (P5.5 §2).

Mounted via app/api/v1/__init__.py (the /api/v1 prefix is applied there).
POST /generate and GET /today read bar_cache + indicator_computer off
request.app.state (same as /api/v1/indicators).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.stub import CurrentUser, get_current_user
from app.db.session import get_session
from app.services.morning_brief import MorningBriefData, MorningBriefService

router = APIRouter(prefix="/morning-brief", tags=["morning_brief"])


class SymbolObservationResponse(BaseModel):
    symbol: str
    bias: str
    key_level: float | None
    watch_for: str
    indicators: dict[str, Any]


class MorningBriefResponse(BaseModel):
    user_id: int
    brief_date: date
    symbols: list[SymbolObservationResponse]
    overall_note: str
    agent_used: bool
    trigger: str
    generated_at: datetime


def _to_response(brief: MorningBriefData) -> MorningBriefResponse:
    return MorningBriefResponse(
        user_id=brief.user_id,
        brief_date=brief.brief_date,
        symbols=[
            SymbolObservationResponse(
                symbol=o.symbol,
                bias=o.bias,
                key_level=o.key_level,
                watch_for=o.watch_for,
                indicators=o.indicators,
            )
            for o in brief.symbols
        ],
        overall_note=brief.overall_note,
        agent_used=brief.agent_used,
        trigger=brief.trigger,
        generated_at=brief.generated_at,
    )


def _service(request: Request, session: AsyncSession) -> MorningBriefService:
    return MorningBriefService(
        session=session,
        bar_cache=getattr(request.app.state, "bar_cache", None),
        indicator_computer=getattr(request.app.state, "indicator_computer", None),
    )


@router.post("/generate", response_model=MorningBriefResponse)
async def generate_brief(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MorningBriefResponse:
    svc = _service(request, session)
    brief = await svc.generate(current_user.id, trigger="manual")
    await svc.save(brief)
    return _to_response(brief)


@router.get("/today", response_model=MorningBriefResponse | None)
async def todays_brief(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MorningBriefResponse | None:
    from app.utils.time import today_eastern

    svc = MorningBriefService(session=session)
    brief = await svc.get(current_user.id, today_eastern())
    return _to_response(brief) if brief else None


@router.get("/recent", response_model=list[MorningBriefResponse])
async def recent_briefs(
    limit: int = 7,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[MorningBriefResponse]:
    if limit < 1 or limit > 30:
        raise HTTPException(status_code=400, detail="limit must be 1-30")
    svc = MorningBriefService(session=session)
    return [_to_response(b) for b in await svc.get_recent(current_user.id, limit=limit)]


@router.get("/{brief_date}", response_model=MorningBriefResponse | None)
async def brief_by_date(
    brief_date: date,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MorningBriefResponse | None:
    svc = MorningBriefService(session=session)
    brief = await svc.get(current_user.id, brief_date)
    return _to_response(brief) if brief else None
