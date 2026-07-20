"""/api/v1/risk-limits and /api/v1/accounts/{id}/risk/* endpoints (P5 §5)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.auth.stub import CurrentUser, get_current_user
from app.db.models.account import Account, AccountMode
from app.db.models.risk_limits import RiskLimits
from app.db.session import get_session, get_sessionmaker
from app.events import get_event_bus
from app.risk.circuit_breaker import CircuitBreakerService
from app.risk.loss_control import constants as LC
from app.risk.loss_control.recovery import RecoveryPreflightService
from app.risk.pdt_analyzer import PdtAnalyzer

router = APIRouter(tags=["risk"])


# ---------------- schemas ----------------


class RiskLimitsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    broker_mode: AccountMode
    scope_type: str
    scope_id: int | None
    max_position_qty: int | None
    max_position_notional: Decimal | None
    max_gross_exposure: Decimal | None
    max_daily_loss: Decimal | None
    max_orders_per_minute: int | None
    max_orders_per_day: int | None
    allow_short: bool


class RiskLimitsListResponse(BaseModel):
    items: list[RiskLimitsResponse]
    count: int


class UpdateRiskLimitsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_position_qty: int | None = Field(default=None, ge=0)
    max_position_notional: Decimal | None = Field(default=None, ge=0)
    max_gross_exposure: Decimal | None = Field(default=None, ge=0)
    max_daily_loss: Decimal | None = Field(default=None, ge=0)
    max_orders_per_minute: int | None = Field(default=None, ge=0)
    max_orders_per_day: int | None = Field(default=None, ge=0)
    allow_short: bool | None = None


class CircuitBreakerStatusResponse(BaseModel):
    account_id: int
    tripped: bool
    tripped_at: datetime | None
    realized_pnl_today: Decimal
    unrealized_pnl_now: Decimal
    daily_pnl: Decimal  # the trip basis: today's P&L from a start-of-day baseline (ADR 0004 v2)
    daily_pnl_basis: str  # "equity_baseline" | "cumulative_fallback"
    max_daily_loss: Decimal
    headroom: Decimal


class PdtStatusResponse(BaseModel):
    account_id: int
    is_at_risk: bool
    day_trade_count: int
    threshold: int
    window_days: int
    account_equity: Decimal | None
    equity_threshold: Decimal


class RiskStateResponse(BaseModel):
    circuit_breaker: CircuitBreakerStatusResponse
    pdt: PdtStatusResponse


class ResetCircuitBreakerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation_text: str = Field(min_length=1, max_length=64)


# ---------------- endpoints ----------------


@router.get("/risk-limits", response_model=RiskLimitsListResponse)
async def list_risk_limits(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RiskLimitsListResponse:
    rows = (
        await session.execute(
            select(RiskLimits)
            .where(RiskLimits.user_id == current_user.id)
            .order_by(RiskLimits.broker_mode, RiskLimits.scope_type)
        )
    ).scalars().all()
    return RiskLimitsListResponse(
        items=[RiskLimitsResponse.model_validate(r) for r in rows],
        count=len(rows),
    )


@router.put("/risk-limits/{limits_id}", response_model=RiskLimitsResponse)
async def update_risk_limits(
    limits_id: int,
    body: UpdateRiskLimitsRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RiskLimitsResponse:
    row = await session.get(RiskLimits, limits_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Risk limits not found")

    changes: dict[str, dict[str, str | None]] = {"old": {}, "new": {}}
    for field, new_val in body.model_dump(exclude_unset=True).items():
        old_val = getattr(row, field)
        if old_val != new_val:
            changes["old"][field] = str(old_val) if old_val is not None else None
            changes["new"][field] = str(new_val) if new_val is not None else None
            setattr(row, field, new_val)
    await session.commit()

    AuditLogger.write(
        session,
        actor_type=AuditActorType.USER,
        actor_id=str(current_user.id),
        action=AuditAction.RISK_LIMITS_UPDATED,
        target_type="risk_limits",
        target_id=limits_id,
        payload={"changes": changes, "broker_mode": row.broker_mode.value},
        user_id=current_user.id,
    )
    await session.commit()
    await session.refresh(row)
    return RiskLimitsResponse.model_validate(row)


@router.get("/accounts/{account_id}/risk-state", response_model=RiskStateResponse)
async def account_risk_state(
    account_id: int,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RiskStateResponse:
    account = await session.get(Account, account_id)
    if account is None or account.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Account not found")

    broker_registry = getattr(request.app.state, "broker_registry", None)
    cb = CircuitBreakerService(session=session, broker_registry=broker_registry)
    pdt = PdtAnalyzer(session=session, broker_registry=broker_registry)
    cb_status = await cb.status(account_id)
    pdt_status = await pdt.compute(account_id)

    return RiskStateResponse(
        circuit_breaker=CircuitBreakerStatusResponse(
            account_id=cb_status.account_id,
            tripped=cb_status.tripped,
            tripped_at=cb_status.tripped_at,
            realized_pnl_today=cb_status.realized_pnl_today,
            unrealized_pnl_now=cb_status.unrealized_pnl_now,
            daily_pnl=cb_status.daily_pnl,
            daily_pnl_basis=cb_status.daily_pnl_basis,
            max_daily_loss=cb_status.max_daily_loss,
            headroom=cb_status.headroom,
        ),
        pdt=PdtStatusResponse(
            account_id=pdt_status.account_id,
            is_at_risk=pdt_status.is_at_risk,
            day_trade_count=pdt_status.day_trade_count,
            threshold=pdt_status.threshold,
            window_days=pdt_status.window_days,
            account_equity=pdt_status.account_equity,
            equity_threshold=pdt_status.equity_threshold,
        ),
    )


@router.post("/accounts/{account_id}/risk/reset-circuit-breaker")
async def reset_circuit_breaker(
    account_id: int,
    body: ResetCircuitBreakerRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    cb = CircuitBreakerService(session=session, bus=get_event_bus())
    try:
        await cb.reset(
            account_id=account_id,
            user_id=current_user.id,
            confirmation_text=body.confirmation_text,
        )
    except PermissionError:
        raise HTTPException(status_code=404, detail="Account not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "account_id": account_id}


# ---------------- ADR 0043 PR6 — recovery preflight (control plane) ----------------


class RecoveryRequestBody(BaseModel):
    # The ONLY client input is an idempotency key. No origin, no check results, no force, no target
    # state, no path to NORMAL — those are computed/durable, never client-supplied.
    idempotency_key: str = Field(min_length=1, max_length=64)


# HTTP status per reject reason. Missing/ineligible → 409 conflict on state; authz → 403.
_RECOVERY_ERR_STATUS = {
    LC.ERR_NOT_AUTHORIZED: 403,
    LC.ERR_NOT_ELIGIBLE: 409,
    LC.ERR_IDEMPOTENCY_CONFLICT: 409,
    LC.ERR_ACTIVE_PREFLIGHT_EXISTS: 409,
}


async def _account_owner_or_404(session: AsyncSession, account_id: int) -> int:
    owner = await session.scalar(select(Account.user_id).where(Account.id == account_id))
    if owner is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return int(owner)


def _adapter_for(request: Request, account_id: int) -> object | None:
    registry = getattr(request.app.state, "broker_registry", None)
    return registry.get(account_id) if registry is not None else None


@router.post("/accounts/{account_id}/loss-control/recovery-requests")
async def create_recovery_request(
    account_id: int,
    body: RecoveryRequestBody,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    owner_id = await _account_owner_or_404(session, account_id)
    svc = RecoveryPreflightService(get_sessionmaker())
    outcome = await svc.request_recovery(
        account_id=account_id, account_owner_id=owner_id,
        idempotency_key=body.idempotency_key, requester_user_id=current_user.id,
        adapter=_adapter_for(request, account_id),
    )
    if outcome.rejected:
        raise HTTPException(
            status_code=_RECOVERY_ERR_STATUS.get(outcome.reason or "", 400),
            detail=outcome.reason or "recovery request rejected",
        )
    AuditLogger.write(
        session, actor_type=AuditActorType.USER, actor_id=str(current_user.id),
        action=AuditAction.LOSS_CONTROL_RECOVERY, target_type="account", target_id=account_id,
        payload={"phase": "request", "preflight_id": outcome.preflight_id,
                 "status": outcome.status, "aggregate_verdict": outcome.aggregate_verdict},
        user_id=current_user.id,
    )
    await session.commit()
    return {"preflight_id": outcome.preflight_id, "status": outcome.status,
            "aggregate_verdict": outcome.aggregate_verdict,
            "resulting_state": outcome.resulting_state}


@router.get("/accounts/{account_id}/loss-control/recovery-requests/{preflight_id}")
async def get_recovery_request(
    account_id: int,
    preflight_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    await _account_owner_or_404(session, account_id)
    got = await RecoveryPreflightService(get_sessionmaker()).get(account_id, preflight_id)
    if got is None:
        raise HTTPException(status_code=404, detail="Recovery request not found")
    parent, checks = got
    return {
        "preflight_id": parent.id, "account_id": parent.account_id, "status": parent.status,
        "aggregate_verdict": parent.aggregate_verdict, "origin_state": parent.origin_state,
        "authority_class": parent.authority_class, "failure_reason": parent.failure_reason,
        "checks": [{"name": c.check_name, "status": c.status} for c in checks],
    }


@router.post("/accounts/{account_id}/loss-control/recovery-requests/{preflight_id}/approve")
async def approve_recovery_request(
    account_id: int,
    preflight_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    # Approves the EXISTING evidence package (does not rerun the checks). Authorization is the
    # registered risk-operator authority; an INTEGRITY_STOP recovery requires it explicitly.
    owner_id = await _account_owner_or_404(session, account_id)
    svc = RecoveryPreflightService(get_sessionmaker())
    outcome = await svc.approve(
        account_id=account_id, account_owner_id=owner_id, preflight_id=preflight_id,
        approver_user_id=current_user.id,
    )
    if outcome.rejected:
        raise HTTPException(
            status_code=_RECOVERY_ERR_STATUS.get(outcome.reason or "", 400),
            detail=outcome.reason or "approval rejected",
        )
    AuditLogger.write(
        session, actor_type=AuditActorType.USER, actor_id=str(current_user.id),
        action=AuditAction.LOSS_CONTROL_RECOVERY, target_type="account", target_id=account_id,
        payload={"phase": "approve", "preflight_id": preflight_id, "status": outcome.status},
        user_id=current_user.id,
    )
    await session.commit()
    return {"preflight_id": preflight_id, "status": outcome.status,
            "resulting_state": outcome.resulting_state}
