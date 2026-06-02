"""Pre-call budget check for the agent service (P6 §1a).

Per Decision 6 (P6 Architectural Decisions v0.1):
- Hard cap, not soft alert.
- Per-user 24h envelope, default $2.00 (200 cents), tunable via
  ``trading_profiles.agent_envelope_json.cost_envelope_cents``.

Route is ``GET /api/v1/agent/cost-envelope`` — NOT ``/agent/budget``, which the
P3 chat router already owns (a different concept: chat-session USD budget). The
collision was caught during §1a validation; this is the proposal cost envelope.
- Queries the audit_log for the user's cost-bearing rows over the last 24h.
- On REJECTED, writes an AGENT_BUDGET_REJECTED audit row before responding.

§1a ships the enforcement layer with no caller; §1b's proposal-generation path
is the first to invoke it. See the §1a validation corrections doc for the audit
column names (``ts`` / ``payload_json``) and the fractional-cents handling
(sum as Decimal, round the total up to whole cents — never under-report).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.auth.stub import CurrentUser, get_current_user
from app.db.models.audit_log import AuditLog
from app.db.session import get_session
from app.services.trading_profile import TradingProfileService

router = APIRouter(prefix="/agent", tags=["agent"])

DEFAULT_ENVELOPE_CENTS = 200  # $2.00/user/day — Decision 6's initial number


class BudgetCheckResponse(BaseModel):
    current_spend_cents: int
    envelope_cents: int
    headroom_cents: int
    decision: str  # "ALLOWED" or "REJECTED"
    rejection_audit_id: int | None = None


def _row_cost_cents(stored_value: str | float | int | None) -> Decimal:
    """Parse one audit row's payload_json.llm.cost_cents — a *fractional*-cents
    stringified Decimal (e.g. ``"0.0800"`` for 0.08 cents). Returns Decimal(0)
    on absence/garbage. No per-row truncation; rounding happens once on the sum.
    """
    if stored_value is None:
        return Decimal(0)
    try:
        return Decimal(str(stored_value))
    except (InvalidOperation, ValueError):
        return Decimal(0)


async def _sum_cost_cents_24h(session: AsyncSession, user_id: int) -> int:
    """Sum cost_cents from this user's audit rows in the last 24h where
    ``payload_json.llm.cost_cents`` is present, returned as whole cents rounded
    UP.

    Built with SQLAlchemy Core against the mapped ``AuditLog.ts`` column on
    purpose: the same DateTime bind processor that wrote ``ts`` formats the
    cutoff, so the comparison is format-consistent (a raw ``ts >= :iso_string``
    would mismatch SQLite's stored "YYYY-MM-DD HH:MM:SS.ffffff" against an
    isoformat "...T...+00:00" and silently exclude every row). ``func.json_extract``
    is SQLite-only (project posture); a Postgres move swaps it for
    ``jsonb_extract_path_text``.
    """
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    cost_path = func.json_extract(AuditLog.payload_json, "$.llm.cost_cents")
    result = await session.execute(
        select(AuditLog.payload_json).where(
            AuditLog.user_id == user_id,
            AuditLog.ts >= cutoff,
            cost_path.is_not(None),
        )
    )
    total = Decimal(0)
    for (payload_json,) in result:
        if isinstance(payload_json, str):
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                continue
        else:
            payload = payload_json
        llm = (payload or {}).get("llm") or {}
        total += _row_cost_cents(llm.get("cost_cents"))
    # Round the TOTAL up to whole cents — conservative (never under-reports).
    return int(total.to_integral_value(rounding=ROUND_CEILING))


@router.get("/cost-envelope", response_model=BudgetCheckResponse)
async def check_budget(
    estimated_cost_cents: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BudgetCheckResponse:
    """Pre-call budget check. Returns ALLOWED or REJECTED (both HTTP 200).

    REJECTED writes an AGENT_BUDGET_REJECTED audit row (single commit at end);
    ALLOWED writes nothing — the LLM call itself records spend later.
    """
    if estimated_cost_cents < 0:
        raise HTTPException(
            status_code=400, detail="estimated_cost_cents must be >= 0"
        )

    # Read the user's envelope from the trading profile (Decision 4).
    profile = await TradingProfileService(session).get(current_user.id)
    envelope = profile.agent_envelope or {}
    try:
        envelope_cents = int(envelope.get("cost_envelope_cents", DEFAULT_ENVELOPE_CENTS))
    except (TypeError, ValueError):
        envelope_cents = DEFAULT_ENVELOPE_CENTS

    current_spend = await _sum_cost_cents_24h(session, current_user.id)
    headroom = envelope_cents - current_spend

    would_exceed = (current_spend + estimated_cost_cents) > envelope_cents
    decision = "REJECTED" if would_exceed else "ALLOWED"

    if decision == "REJECTED":
        # The agent acts on behalf of the user; AGENT is a first-class actor.
        # Single commit (§1+§2 pattern) — one audit row per transaction keeps the
        # §8 hash chain well-formed.
        AuditLogger.write(
            session,
            actor_type=AuditActorType.AGENT,
            actor_id=str(current_user.id),
            action=AuditAction.AGENT_BUDGET_REJECTED,
            target_type="user_budget",
            target_id=current_user.id,
            payload={
                "estimated_cost_cents": estimated_cost_cents,
                "current_spend_cents": current_spend,
                "envelope_cents": envelope_cents,
                "headroom_cents": headroom,
            },
            user_id=current_user.id,
        )
        await session.commit()
        # rejection_audit_id left None for 1a — clients correlate via the audit
        # endpoint. Resolving the just-written id needs a refresh; not critical.

    return BudgetCheckResponse(
        current_spend_cents=current_spend,
        envelope_cents=envelope_cents,
        headroom_cents=headroom,
        decision=decision,
        rejection_audit_id=None,
    )
