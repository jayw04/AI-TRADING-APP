"""Read-only Operations & Reliability endpoints (P11 §1, ADR 0021).

Exposes the operational state of the platform's automated features (what is
enabled/running today, and is it healthy) — derived live, no persistence, no order path.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request

from app.auth.stub import CurrentUser, get_current_user
from app.ops.state import HEALTH_ALGORITHM_VERSION, resolve_operational_state

router = APIRouter(prefix="/ops", tags=["ops"])


@router.get("/state")
async def ops_state(
    request: Request,
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Operational state of every registered feature: Implemented / Enabled / Healthy /
    Verified (P11 §1/§2). Read-only; derived from the live strategy engine + scheduler +
    the Prometheus metrics. The envelope carries `health_algorithm_version` (traceable
    health calc) and `health_calculated_at`."""
    engine = getattr(request.app.state, "strategy_engine", None)
    states = resolve_operational_state(engine)
    return {
        "as_of": datetime.now(UTC).isoformat(),
        "health_algorithm_version": HEALTH_ALGORITHM_VERSION,
        "health_calculated_at": datetime.now(UTC).isoformat(),
        "features": [asdict(s) for s in states],
    }


@router.get("/strategy-dispatch")
async def ops_strategy_dispatch(
    request: Request,
    _user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Per-strategy **dispatch liveness** — is each active bar-driven strategy actually
    receiving ``on_bar`` during RTH? Flags the silent-inertness failure (an active intraday
    strategy doing nothing because the engine isn't up through the session). Read-only;
    `degraded` is true when any bar-driven strategy is `stale`."""
    engine = getattr(request.app.state, "strategy_engine", None)
    results = engine.dispatch_health() if engine is not None else []
    return {
        "as_of": datetime.now(UTC).isoformat(),
        "degraded": any(r.health == "stale" for r in results),
        "strategies": [asdict(r) for r in results],
    }
