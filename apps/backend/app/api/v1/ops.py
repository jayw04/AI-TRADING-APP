"""Read-only Operations & Reliability endpoints (P11 §1, ADR 0021).

Exposes the operational state of the platform's automated features (what is
enabled/running today, and is it healthy) — derived live, no persistence, no order path.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request

from app.auth.stub import CurrentUser, get_current_user
from app.ops.state import resolve_operational_state

router = APIRouter(prefix="/ops", tags=["ops"])


@router.get("/state")
async def ops_state(
    request: Request,
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Operational state of every registered feature: Implemented / Enabled / Healthy /
    Verified (P11 §1). Read-only; derived from the live strategy engine + scheduler."""
    engine = getattr(request.app.state, "strategy_engine", None)
    states = resolve_operational_state(engine)
    return {
        "as_of": datetime.now(UTC).isoformat(),
        "features": [asdict(s) for s in states],
    }
