"""User-level drift read surface (P6b §1b-drift).

GET /api/v1/drift-findings — recent STRATEGY_DRIFT_DETECTED audit rows for the
user (newest first; optional strategy filter), parsed into structured findings.
Audit-log-backed (the §1a system of record); no new table. The per-strategy
status/check endpoints live on proposals.py::strategies_router; this user-level
list serves the morning-brief drift section in a single call (no fan-out).

A fresh module (not strategies.py) keeps these endpoints off the P2 branch-
coverage gate, the same reason §1b/§2b put strategies-scoped endpoints on
proposals.py::strategies_router.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.stub import CurrentUser, get_current_user
from app.db.models.audit_log import AuditLog
from app.db.session import get_session

router = APIRouter(tags=["drift"])


class DriftFindingResponse(BaseModel):
    strategy_id: int
    detected_at: str | None
    breached: list[str]
    win_rate: dict[str, Any]
    avg_return_per_trade: dict[str, Any]
    trade_count: int | None
    audit_id: int


class DriftFindingsListResponse(BaseModel):
    items: list[DriftFindingResponse]


@router.get("/drift-findings", response_model=DriftFindingsListResponse)
async def list_drift_findings(
    strategy_id: int | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DriftFindingsListResponse:
    """Recent STRATEGY_DRIFT_DETECTED findings for the user (newest first).
    Optional ``strategy_id`` filter (the audit target_id is ``str(strategy_id)``)."""
    q = (
        select(AuditLog)
        .where(AuditLog.user_id == current_user.id)
        .where(AuditLog.action == "STRATEGY_DRIFT_DETECTED")
    )
    if strategy_id is not None:
        q = q.where(AuditLog.target_id == str(strategy_id))
    q = q.order_by(AuditLog.id.desc()).limit(limit)

    rows = (await session.execute(q)).scalars().all()
    items: list[DriftFindingResponse] = []
    for r in rows:
        p = json.loads(r.payload_json or "{}")
        items.append(
            DriftFindingResponse(
                strategy_id=int(p.get("strategy_id", r.target_id or 0)),
                detected_at=p.get("detected_at"),
                breached=p.get("breached", []),
                win_rate=p.get("win_rate", {}),
                avg_return_per_trade=p.get("avg_return_per_trade", {}),
                trade_count=p.get("trade_count"),
                audit_id=r.id,
            )
        )
    return DriftFindingsListResponse(items=items)
