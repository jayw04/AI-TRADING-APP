"""REST endpoints under ``/api/v1/agent`` (P3 Session 4).

Six endpoints implement the chat-panel contract:

* ``POST /sessions`` — start a new session (schema rejects B3 per ADR 0006).
* ``GET /sessions`` — list the user's sessions, optionally filtered by status.
* ``GET /sessions/{id}`` — session detail + ordered conversation.
* ``POST /sessions/{id}/messages`` — append a user message, run the agent
  turn, return the persisted user message id. Assistant responses arrive
  via the ``agent`` WS topic.
* ``POST /sessions/{id}/end`` — mark the session ENDED.
* ``GET /budget`` — today's cumulative spend across the user's sessions
  vs the configured daily cap.
"""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.agent import (
    AppendMessageRequest,
    AppendMessageResponse,
    BudgetResponse,
    EndSessionRequest,
    MessageResponse,
    SessionDetail,
    SessionListResponse,
    SessionSummary,
    StartSessionRequest,
)
from app.auth.stub import CurrentUser, get_current_user
from app.config import get_settings
from app.db.enums import ACTIVE_AGENT_STATUSES, AgentMessageRole, AgentSessionStatus
from app.db.models.agent_message import AgentMessage
from app.db.models.agent_session import AgentSession
from app.db.session import get_session
from app.llm.anthropic_client import AnthropicClientNotConfigured
from app.llm.pricing import DailyBudgetResolver
from app.llm.runtime import AgentRuntime, AgentRuntimeError

router = APIRouter(prefix="/agent", tags=["agent"])


def _get_runtime(request: Request) -> AgentRuntime:
    runtime = getattr(request.app.state, "agent_runtime", None)
    if runtime is None:
        raise HTTPException(
            status_code=503, detail="Agent runtime not initialized"
        )
    return runtime


def _to_summary(row: AgentSession, message_count: int) -> SessionSummary:
    return SessionSummary(
        id=row.id,
        user_id=row.user_id,
        mode=row.mode,
        status=row.status,
        model=row.model,
        total_input_tokens=row.total_input_tokens,
        total_output_tokens=row.total_output_tokens,
        total_cost_usd=row.total_cost_usd,
        daily_budget_usd=row.daily_budget_usd,
        started_at=row.started_at,
        ended_at=row.ended_at,
        end_reason=row.end_reason,
        message_count=message_count,
    )


# ---------- POST /sessions ----------


@router.post("/sessions", response_model=SessionSummary)
async def start_session(
    body: StartSessionRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SessionSummary:
    runtime = _get_runtime(request)
    try:
        new_id = await runtime.start_session(
            user_id=current_user.id, mode=body.mode, model=body.model,
        )
    except AnthropicClientNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AgentRuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    row = await session.get(AgentSession, new_id)
    if row is None:
        raise HTTPException(
            status_code=500, detail="Session row not found after create"
        )
    return _to_summary(row, message_count=0)


# ---------- GET /sessions ----------


@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    status: AgentSessionStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SessionListResponse:
    stmt = select(AgentSession).where(AgentSession.user_id == current_user.id)
    if status is not None:
        stmt = stmt.where(AgentSession.status == status)
    stmt = stmt.order_by(AgentSession.started_at.desc()).limit(limit)

    rows = (await session.execute(stmt)).scalars().all()

    counts: dict[int, int] = {}
    if rows:
        id_list = [r.id for r in rows]
        count_rows = (
            await session.execute(
                select(AgentMessage.session_id, func.count(AgentMessage.id))
                .where(AgentMessage.session_id.in_(id_list))
                .group_by(AgentMessage.session_id)
            )
        ).all()
        for sid, c in count_rows:
            counts[sid] = c

    items = [_to_summary(r, counts.get(r.id, 0)) for r in rows]
    return SessionListResponse(items=items, count=len(items))


# ---------- GET /sessions/{id} ----------


@router.get("/sessions/{session_id}", response_model=SessionDetail)
async def get_session_detail(
    session_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SessionDetail:
    row = await session.get(AgentSession, session_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    msg_rows = (
        await session.execute(
            select(AgentMessage)
            .where(AgentMessage.session_id == session_id)
            .order_by(AgentMessage.ts.asc())
        )
    ).scalars().all()

    summary = _to_summary(row, message_count=len(msg_rows))
    messages = [MessageResponse.model_validate(m) for m in msg_rows]
    return SessionDetail(**summary.model_dump(), messages=messages)


# ---------- POST /sessions/{id}/messages ----------


@router.post(
    "/sessions/{session_id}/messages", response_model=AppendMessageResponse
)
async def append_message(
    session_id: int,
    body: AppendMessageRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AppendMessageResponse:
    row = await session.get(AgentSession, session_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    if row.status not in ACTIVE_AGENT_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Session is {row.status.value}; "
                "start a new session to continue"
            ),
        )

    runtime = _get_runtime(request)
    try:
        await runtime.append_user_message(session_id=session_id, text=body.text)
    except AgentRuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # The runtime persists the user message FIRST, then runs the turn —
    # within the per-session lock. Re-query for the latest USER message
    # by ts to grab its id. No race because we just held the only lock
    # that could write a user message to this session.
    latest_user = (
        await session.execute(
            select(AgentMessage)
            .where(
                AgentMessage.session_id == session_id,
                AgentMessage.role == AgentMessageRole.USER,
            )
            .order_by(AgentMessage.ts.desc())
            .limit(1)
        )
    ).scalars().first()
    if latest_user is None:
        raise HTTPException(
            status_code=500, detail="User message not persisted"
        )

    return AppendMessageResponse(
        session_id=session_id, user_message_id=latest_user.id
    )


# ---------- POST /sessions/{id}/end ----------


@router.post("/sessions/{session_id}/end", response_model=SessionSummary)
async def end_session(
    session_id: int,
    body: EndSessionRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SessionSummary:
    row = await session.get(AgentSession, session_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    runtime = _get_runtime(request)
    await runtime.end_session(session_id=session_id, reason=body.reason)

    # Re-read to reflect the runtime's mutation.
    await session.refresh(row)
    count = (
        await session.execute(
            select(func.count(AgentMessage.id)).where(
                AgentMessage.session_id == session_id
            )
        )
    ).scalar() or 0
    return _to_summary(row, message_count=count)


# ---------- GET /budget ----------


@router.get("/budget", response_model=BudgetResponse)
async def get_budget(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BudgetResponse:
    settings = get_settings()
    budget = Decimal(str(settings.agent_daily_budget_usd)).quantize(
        Decimal("0.0001")
    )
    resolver = DailyBudgetResolver(daily_budget_usd=budget)
    spent = await resolver.spent_today(session, user_id=current_user.id)
    remaining = (budget - spent).quantize(Decimal("0.0001"))
    pct_used = float((spent / budget) * 100) if budget > 0 else 0.0
    return BudgetResponse(
        spent_usd=spent,
        budget_usd=budget,
        remaining_usd=remaining,
        pct_used=pct_used,
    )
