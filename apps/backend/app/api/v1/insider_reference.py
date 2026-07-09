"""GET /api/v1/insider-reference — the Insider Activity Monitor (Reference Only).

A display-only context surface over the PIT Event Store's ``insider_buy`` events. INSIDER-001
rejected the standalone signal (beta-not-alpha); this endpoint exists under the
``rejected_reference_only`` invariant: every row and the envelope carry ``reference_only: true``,
rows sort by ``filed_at`` DESC ONLY, and this module (transitively) imports nothing from
orders / risk / ranking / sizing / strategy selection — test-pinned. Filters are display
hygiene, not selection. Plan: TradingWorkbench_InsiderReferenceMonitor_ImplementationPlan v1.0.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.altdata.insider_monitor import (
    EVIDENCE_DOC,
    EVIDENCE_NOTE,
    load_latest_manifest,
    recent_reference_rows,
)
from app.auth.stub import CurrentUser, get_current_user

router = APIRouter(prefix="/insider-reference", tags=["insider-reference"])


@router.get("")
async def get_insider_reference(
    window_days: int = Query(default=14, ge=1, le=90),
    min_value: float = Query(default=10_000.0, ge=0),
    open_market_only: bool = Query(default=True),
    current_user: CurrentUser = Depends(get_current_user),  # noqa: ARG001 — auth gate only
) -> dict[str, Any]:
    """Recent open-market insider purchases with display context (materiality, cluster, role,
    sector, freshness). Reference only — never a signal, never an input to trading."""
    from app.altdata.events.store import EventStore

    try:
        events_store = EventStore(read_only=True)
    except Exception:  # noqa: BLE001 — no store yet (first boot): serve the empty surface
        rows = []
    else:
        try:
            try:
                from app.factor_data.store import FactorDataStore

                factor_store: Any = FactorDataStore(read_only=True)
            except Exception:  # noqa: BLE001 — context degrades, the surface still serves
                factor_store = None
            rows = recent_reference_rows(
                events_store, factor_store,
                window_days=window_days, min_value=min_value, open_market_only=open_market_only,
            )
        finally:
            events_store.close()

    manifest = load_latest_manifest()
    return {
        "reference_only": True,
        "evidence_note": EVIDENCE_NOTE,
        "evidence_doc": EVIDENCE_DOC,
        "universe_size": (manifest or {}).get("count"),
        "universe_as_of": (manifest or {}).get("date"),
        "count": len(rows),
        "rows": [r.to_dict() for r in rows],
    }
