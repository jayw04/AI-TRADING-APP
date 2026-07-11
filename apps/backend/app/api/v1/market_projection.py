"""GET /api/v1/market-projection — the §4 read-only surface (FR-011, owner-capped).

Serves ONLY the validated claim: primary-horizon elevated move-risk. Per the
owner decision (2026-07-10/11): **no directional fields, labels, tooltips, or
hidden outputs** — the response carries P(MATERIAL) and never the UP/DOWN
split (which stays in the DB for research/grading only). PRE_OPEN is not
served; asking for it returns an explicit no-claim response. Badge degrades
automatically when the drift ladder has downgraded (guardrail 8); restoration
is operator-only.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.stub import CurrentUser, get_current_user
from app.db.models.market_projection_run import MarketProjectionRun
from app.db.session import get_session
from app.services.market_projection.outcomes import drift_state
from app.services.market_projection.schemas import (
    BADGE_DEGRADED,
    BADGE_VALIDATED,
    DISCLAIMER,
    REGIME_LIMITATION,
    ProjectionType,
)

router = APIRouter(prefix="/market-projection", tags=["market-projection"])


@router.get("")
async def get_market_projection(
    projection_type: str = ProjectionType.PRE_CLOSE_TOMORROW.value,
    current_user: CurrentUser = Depends(get_current_user),  # noqa: ARG001 — auth gate only
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if projection_type != ProjectionType.PRE_CLOSE_TOMORROW.value:
        return {
            "available": False,
            "reason": "not served — no validated claim for this horizon (ModelCard v1.0)",
        }

    latest_success = (await session.execute(
        select(MarketProjectionRun).where(
            MarketProjectionRun.projection_type == projection_type,
            MarketProjectionRun.run_status == "SUCCESS",
        ).order_by(MarketProjectionRun.target_date.desc(),
                   MarketProjectionRun.attempt_number.desc()).limit(1)
    )).scalars().first()

    if latest_success is None:
        latest_any = (await session.execute(
            select(MarketProjectionRun).where(
                MarketProjectionRun.projection_type == projection_type,
            ).order_by(MarketProjectionRun.as_of.desc()).limit(1)
        )).scalars().first()
        return {
            "available": False,
            "reason": (latest_any.unavailable_reason or latest_any.run_status).lower()
            if latest_any else "no_runs_yet",
            "disclaimer": DISCLAIMER,
        }

    drift = drift_state()
    badge = BADGE_DEGRADED if drift.get("status") == "downgraded" else BADGE_VALIDATED
    return {
        "available": True,
        "badge": badge,
        "drift_status": drift.get("status", "ok"),
        "projection_type": projection_type,
        "market_proxy": latest_success.market_proxy,
        "as_of": latest_success.as_of,
        "target_date": latest_success.target_date,
        # the ONLY probability served (owner Q1): move-risk, never the UP/DOWN split
        "p_material": latest_success.prob_material,
        "elevated": latest_success.elevated,
        "display_phrase": latest_success.display_phrase,
        "confidence": latest_success.confidence,
        "material_threshold_pct": latest_success.material_threshold_pct,
        "drivers": latest_success.drivers_json,   # raises/lowers_move_risk only
        "model_version": latest_success.model_version,
        "feature_version": latest_success.feature_version,
        "label_version": latest_success.label_version,
        "source": latest_success.source_json,
        "regime_limitation": REGIME_LIMITATION,
        "disclaimer": DISCLAIMER,
    }
