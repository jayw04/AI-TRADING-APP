"""GET /api/v1/audit — recent audit_log entries for the current user (P5.5 §3).

Read-only. Scoped to ``current_user.id`` (each user sees only their own chain).
Newest-first. Deliberately omits ``row_hash``/``prev_hash`` (integrity internals,
not user-facing). Added in §3 because the workbench-mcp ``workbench_audit_recent``
tool and the CLAUDE.md "what happened overnight / what did the brief cost" rows
need it — there was no audit read endpoint before.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.stub import CurrentUser, get_current_user
from app.db.models.audit_log import AuditLog
from app.db.session import get_session

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ts: datetime
    actor_type: str
    actor_id: str | None
    action: str  # UPPER name, e.g. MORNING_BRIEF_GENERATED
    target_type: str | None
    target_id: str | None
    payload_json: str | None  # stringified JSON; callers parse (incl. payload.llm)


class AuditListResponse(BaseModel):
    items: list[AuditEntryResponse]
    count: int


@router.get("", response_model=AuditListResponse)
async def list_audit(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> AuditListResponse:
    rows = (
        await session.execute(
            select(AuditLog)
            .where(AuditLog.user_id == current_user.id)
            .order_by(AuditLog.id.desc())
            .limit(limit)
        )
    ).scalars().all()
    return AuditListResponse(
        items=[AuditEntryResponse.model_validate(r) for r in rows],
        count=len(rows),
    )
