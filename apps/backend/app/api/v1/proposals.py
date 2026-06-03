"""Strategy-proposals API (P6 §1b).

Endpoints:
- POST /api/v1/strategies/{strategy_id}/propose
    Create a DRAFT proposal, then synchronously invoke the agent service to
    populate it. Returns the populated proposal (REVIEWING on success) or
    cleans up the DRAFT and surfaces an error.
- PATCH /api/v1/proposals/{proposal_id}
    Lifecycle transitions: DRAFT→REVIEWING (agent), REVIEWING→ACCEPTED|REJECTED
    (user). APPLIED has its own endpoint (Decision 3).
- GET /api/v1/proposals?strategy_id=&state=&limit=
- POST /api/v1/proposals/{proposal_id}/apply
    The APPLIED transition: merge the proposal's parameter changes into the
    strategy's params_json (mirrors PUT /strategies/{id}: requires the strategy
    be IDLE). Per §1b validation correction #4, params live in params_json — NOT
    top-level columns — so there is no column whitelist.

No new migration, no new audit actions: §1a's strategy_proposals table and the
three audit actions cover this surface.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.auth.stub import CurrentUser, get_current_user
from app.db.enums import OrderSourceType, StrategyStatus
from app.db.models.order import Order
from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.db.session import get_session

logger = structlog.get_logger(__name__)

# Two routers, one file: /strategies/{id}/propose hangs under /strategies
# (alongside the strategies + activation routers); the rest under /proposals.
strategies_router = APIRouter(prefix="/strategies", tags=["proposals"])
proposals_router = APIRouter(prefix="/proposals", tags=["proposals"])

_DEFAULT_AGENT_URL = "http://127.0.0.1:8767"


# ----- Pydantic models -----


class ProposalResponse(BaseModel):
    id: int
    strategy_id: int
    user_id: int
    state: str
    proposal_payload: dict[str, Any]
    evidence_bundle: dict[str, Any]
    evaluation_results: dict[str, Any]
    generated_at: datetime
    transitioned_at: datetime


class ProposalListResponse(BaseModel):
    items: list[ProposalResponse]


class ProposeRequest(BaseModel):
    """P6 §2a: optional ``trigger`` distinguishes cadence-driven from user-driven
    proposals. Recorded in the DRAFT-creation audit row's ``payload.trigger``.
    Backward-compatible — an empty body / unset trigger is treated as "manual"."""

    trigger: str | None = None  # "manual" | "cadence" | None (treated as manual)


class PatchProposalRequest(BaseModel):
    target_state: str  # "REVIEWING" | "ACCEPTED" | "REJECTED"
    # Agent-only fields (DRAFT → REVIEWING):
    proposal_payload: dict[str, Any] | None = None
    evidence_bundle: dict[str, Any] | None = None
    llm_usage: dict[str, Any] | None = None
    # User-only fields (REVIEWING → ACCEPTED|REJECTED):
    review_notes: str | None = None
    rejection_reason: str | None = None


class ApplyProposalResponse(BaseModel):
    proposal_id: int
    state: str  # "APPLIED"
    applied_changes: list[dict[str, Any]]


class ProposalEvalSummaryResponse(BaseModel):
    strategy_id: int
    window_days: int
    n_proposals: int
    n_eval_complete: int
    n_eval_pending: int
    n_eval_skipped: int
    n_eval_failed: int
    n_above_baseline: int
    n_below_baseline: int
    recent_metrics_summary: dict[str, Any] | None


# ----- Helpers -----


def _to_response(row: StrategyProposal) -> ProposalResponse:
    return ProposalResponse(
        id=row.id,
        strategy_id=row.strategy_id,
        user_id=row.user_id,
        state=row.state.value,
        proposal_payload=row.proposal_payload_json or {},
        evidence_bundle=row.evidence_bundle_json or {},
        evaluation_results=row.evaluation_results_json or {},
        generated_at=row.generated_at,
        transitioned_at=row.transitioned_at,
    )


def _agent_url(request: Request) -> str:
    return (
        getattr(request.app.state, "agent_url", None)
        or os.environ.get("AGENT_URL")
        or _DEFAULT_AGENT_URL
    )


async def _invoke_agent(agent_url: str, proposal_id: int) -> dict[str, Any]:
    """POST to the agent control-plane. Extracted as a module-level function so
    tests can monkeypatch it (mocking the agent without a live service). Raises
    httpx.HTTPError on transport/HTTP failure."""
    async with httpx.AsyncClient(timeout=90.0) as client:
        resp = await client.post(
            f"{agent_url}/generate-proposal", json={"proposal_id": proposal_id}
        )
        resp.raise_for_status()
        return resp.json()


# ----- Endpoints -----


@strategies_router.get("/{strategy_id}/history")
async def strategy_history(
    strategy_id: int,
    limit: int = 30,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Read-only context for proposal generation (P6 §1b): a strategy snapshot
    plus a lightweight recent-orders summary. Detailed performance metrics
    (Sharpe / return / drawdown) are Decision 8 / Session 2.

    Lives here (not in strategies.py) so the §1b addition doesn't perturb the
    P2 branch-coverage gate on api/v1/strategies.py — see §1b validation note.
    """
    if limit < 1 or limit > 90:
        limit = max(1, min(limit, 90))
    row = await session.get(Strategy, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")

    orders = (
        await session.execute(
            select(Order)
            .where(
                Order.source_type == OrderSourceType.STRATEGY,
                Order.source_id == str(strategy_id),
            )
            .order_by(Order.id.desc())
            .limit(limit)
        )
    ).scalars().all()

    return {
        "snapshot": {
            "id": row.id,
            "name": row.name,
            "version": row.version,
            "type": row.type.value,
            "status": row.status.value,
            "params": row.params_json or {},
            "symbols": row.symbols_json or [],
        },
        "performance": {
            "recent_orders_considered": len(orders),
            "recent_order_statuses": [o.status.value for o in orders],
            "note": (
                "Detailed performance metrics (Sharpe / return / drawdown) "
                "arrive in P6 Session 2 (Decision 8 backtest eval)."
            ),
        },
    }


@strategies_router.get(
    "/{strategy_id}/proposal-eval-summary",
    response_model=ProposalEvalSummaryResponse,
)
async def proposal_eval_summary(
    strategy_id: int,
    window: int = Query(default=30, ge=1, le=365),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ProposalEvalSummaryResponse:
    """Aggregate proposal-eval data for a strategy over the last N days
    (P6 §2b-backtest / Decision 8). Lives on strategies_router (not
    strategies.py) per the §1b coverage-gate lesson."""
    strategy = await session.get(Strategy, strategy_id)
    if strategy is None or strategy.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")

    cutoff = datetime.now(UTC) - timedelta(days=window)
    rows = (
        await session.execute(
            select(StrategyProposal)
            .where(
                StrategyProposal.strategy_id == strategy_id,
                StrategyProposal.user_id == current_user.id,
                StrategyProposal.generated_at >= cutoff,
            )
            .order_by(StrategyProposal.generated_at.desc())
        )
    ).scalars().all()

    n_complete = n_pending = n_skipped = n_failed = n_above = n_below = 0
    latest_complete: dict[str, Any] | None = None
    for r in rows:
        eval_state = r.evaluation_results_json or {}
        status = eval_state.get("status")
        if status == "complete":
            n_complete += 1
            verdict = eval_state.get("verdict")
            if verdict == "above_baseline":
                n_above += 1
            elif verdict == "below_baseline":
                n_below += 1
            if latest_complete is None:  # rows are desc → first complete is latest
                latest_complete = {
                    "proposal_id": r.id,
                    "generated_at": r.generated_at.isoformat(),
                    "verdict": verdict,
                    "delta_metrics": eval_state.get("delta_metrics", {}),
                }
        elif status in ("pending", "running"):
            n_pending += 1
        elif status == "skipped":
            n_skipped += 1
        elif status == "failed":
            n_failed += 1

    return ProposalEvalSummaryResponse(
        strategy_id=strategy_id,
        window_days=window,
        n_proposals=len(rows),
        n_eval_complete=n_complete,
        n_eval_pending=n_pending,
        n_eval_skipped=n_skipped,
        n_eval_failed=n_failed,
        n_above_baseline=n_above,
        n_below_baseline=n_below,
        recent_metrics_summary=latest_complete,
    )


@strategies_router.post("/{strategy_id}/propose", response_model=ProposalResponse)
async def propose(
    strategy_id: int,
    body: ProposeRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ProposalResponse:
    """Create a DRAFT proposal + synchronously invoke the agent. By the time
    this returns, the proposal is REVIEWING (success) or the DRAFT was cleaned
    up (failure)."""
    strategy = await session.get(Strategy, strategy_id)
    if strategy is None or strategy.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")

    now = datetime.now(UTC)
    row = StrategyProposal(
        strategy_id=strategy_id,
        user_id=current_user.id,
        state=ProposalState.DRAFT,
        proposal_payload_json={},
        evidence_bundle_json={},
        evaluation_results_json={},
        generated_at=now,
        transitioned_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    try:
        await session.flush()  # populate row.id; may hit the per-minute index
    except Exception as exc:
        await session.rollback()
        raise HTTPException(
            status_code=409,
            detail=(
                "Another proposal for this strategy was just generated. "
                "Wait a minute and try again."
            ),
        ) from exc

    # P6 §2a: a cadence-driven propose (cron, via the user's AGENT_API_KEY) is
    # attributed to actor_type=AGENT; a user-clicked propose is USER. The
    # bearer caller IS the user either way, so user_id is unchanged.
    trigger = body.trigger or "manual"
    is_cadence = trigger == "cadence"
    AuditLogger.write(
        session,
        actor_type=AuditActorType.AGENT if is_cadence else AuditActorType.USER,
        actor_id="cron_scheduler" if is_cadence else str(current_user.id),
        action=AuditAction.STRATEGY_PROPOSAL_TRANSITIONED,
        target_type="strategy_proposal",
        target_id=row.id,
        payload={"from": None, "to": "DRAFT", "strategy_id": strategy_id, "trigger": trigger},
        user_id=current_user.id,
    )
    await session.commit()
    proposal_id = row.id

    # Synchronously invoke the agent (it calls back via PATCH → REVIEWING).
    agent_url = _agent_url(request)
    try:
        agent_result = await _invoke_agent(agent_url, proposal_id)
    except httpx.HTTPError as exc:
        logger.warning("agent_invocation_failed", proposal_id=proposal_id, error=str(exc))
        await _delete_proposal(session, proposal_id)
        raise HTTPException(
            status_code=502, detail=f"Agent service unavailable: {exc}"
        ) from exc

    if agent_result.get("error"):
        logger.warning(
            "agent_generation_error",
            proposal_id=proposal_id,
            error=agent_result["error"],
        )
        await _delete_proposal(session, proposal_id)
        raise HTTPException(
            status_code=502,
            detail=f"Agent generation failed: {agent_result['error']}",
        )

    refreshed = await session.get(StrategyProposal, proposal_id)
    if refreshed is None:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail="Proposal vanished mid-generation")
    await session.refresh(refreshed)
    return _to_response(refreshed)


async def _delete_proposal(session: AsyncSession, proposal_id: int) -> None:
    row = await session.get(StrategyProposal, proposal_id)
    if row is not None:
        await session.delete(row)
        await session.commit()


@proposals_router.patch("/{proposal_id}", response_model=ProposalResponse)
async def patch_proposal(
    proposal_id: int,
    body: PatchProposalRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ProposalResponse:
    """Lifecycle transitions. APPLIED has its own endpoint."""
    row = await session.get(StrategyProposal, proposal_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Proposal not found")

    old_state = row.state.value
    target = body.target_state.upper()

    valid = {
        ("DRAFT", "REVIEWING"),
        ("REVIEWING", "ACCEPTED"),
        ("REVIEWING", "REJECTED"),
    }
    if (old_state, target) not in valid:
        raise HTTPException(
            status_code=400, detail=f"Invalid transition: {old_state} -> {target}"
        )

    actor_type = AuditActorType.USER
    actor_id = str(current_user.id)
    audit_payload: dict[str, Any] = {"from": old_state, "to": target}

    if target == "REVIEWING":
        if not (body.proposal_payload and body.evidence_bundle and body.llm_usage):
            raise HTTPException(
                status_code=400,
                detail="DRAFT -> REVIEWING requires proposal_payload, evidence_bundle, llm_usage",
            )
        row.proposal_payload_json = body.proposal_payload
        row.evidence_bundle_json = body.evidence_bundle
        actor_type = AuditActorType.AGENT
        actor_id = "proposal_generation"
        audit_payload["llm"] = body.llm_usage
        audit_payload["confidence"] = body.proposal_payload.get("confidence")

        # P6 §2b-backtest: enqueue the backtest eval (baseline + variant jobs)
        # atomically with the transition. Eval is judgment fuel, not a gate — if
        # the enqueue itself fails, the proposal still transitions to REVIEWING
        # with eval status=failed; the user can still ACCEPT/REJECT.
        from app.services.proposal_evaluation import enqueue_eval_for_proposal

        try:
            eval_fragment = await enqueue_eval_for_proposal(session, proposal_id=row.id)
        except Exception as exc:  # noqa: BLE001 - non-fatal for the transition
            logger.warning(
                "eval_enqueue_failed_proceeding_with_transition",
                proposal_id=row.id,
                error=str(exc),
            )
            eval_fragment = {
                "status": "failed",
                "failure_reason": f"enqueue_failed: {str(exc)[:200]}",
            }
        row.evaluation_results_json = eval_fragment
        audit_payload["eval_status"] = eval_fragment.get("status")
    elif target == "ACCEPTED" and body.review_notes:
        audit_payload["review_notes"] = body.review_notes
    elif target == "REJECTED" and body.rejection_reason:
        audit_payload["rejection_reason"] = body.rejection_reason

    row.state = ProposalState[target]
    row.transitioned_at = datetime.now(UTC)
    row.updated_at = row.transitioned_at

    AuditLogger.write(
        session,
        actor_type=actor_type,
        actor_id=actor_id,
        action=AuditAction.STRATEGY_PROPOSAL_TRANSITIONED,
        target_type="strategy_proposal",
        target_id=row.id,
        payload=audit_payload,
        user_id=row.user_id,
    )
    await session.commit()
    await session.refresh(row)
    return _to_response(row)


@proposals_router.get("", response_model=ProposalListResponse)
async def list_proposals(
    strategy_id: int | None = None,
    state: str | None = None,
    limit: int = 20,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ProposalListResponse:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="limit must be 1-100")

    q = select(StrategyProposal).where(StrategyProposal.user_id == current_user.id)
    if strategy_id is not None:
        q = q.where(StrategyProposal.strategy_id == strategy_id)
    if state is not None:
        try:
            q = q.where(StrategyProposal.state == ProposalState[state.upper()])
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid state: {state}") from exc
    q = q.order_by(StrategyProposal.generated_at.desc()).limit(limit)

    rows = (await session.execute(q)).scalars().all()
    return ProposalListResponse(items=[_to_response(r) for r in rows])


@proposals_router.get("/{proposal_id}", response_model=ProposalResponse)
async def get_proposal(
    proposal_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ProposalResponse:
    row = await session.get(StrategyProposal, proposal_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Proposal not found")
    return _to_response(row)


@proposals_router.post("/{proposal_id}/apply", response_model=ApplyProposalResponse)
async def apply_proposal(
    proposal_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApplyProposalResponse:
    """APPLIED transition: merge the proposal's parameter changes into the
    strategy's params_json. Only callable on ACCEPTED proposals, and only when
    the strategy is IDLE (mirrors PUT /strategies/{id})."""
    row = await session.get(StrategyProposal, proposal_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if row.state != ProposalState.ACCEPTED:
        raise HTTPException(
            status_code=400,
            detail=f"Can only apply ACCEPTED proposals (current state: {row.state.value})",
        )

    strategy = await session.get(Strategy, row.strategy_id)
    if strategy is None or strategy.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if strategy.status != StrategyStatus.IDLE:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Strategy is in status {strategy.status.value}; "
                "stop it before applying a proposal."
            ),
        )

    # Merge parameter changes into params_json. The change list is the safety
    # boundary — same surface PUT /strategies/{id} already exposes (params_json
    # is a free-form dict of strategy-defined params).
    changes = row.proposal_payload_json.get("changes", []) if row.proposal_payload_json else []
    new_params = dict(strategy.params_json or {})
    applied_changes: list[dict[str, Any]] = []
    for change in changes:
        param = change.get("param")
        if not param:
            continue
        new_params[param] = change.get("to")
        applied_changes.append({"param": param, "to": change.get("to")})

    strategy.params_json = new_params
    strategy.updated_at = datetime.now(UTC)

    old_state = row.state.value
    row.state = ProposalState.APPLIED
    row.transitioned_at = datetime.now(UTC)
    row.updated_at = row.transitioned_at

    AuditLogger.write(
        session,
        actor_type=AuditActorType.USER,
        actor_id=str(current_user.id),
        action=AuditAction.STRATEGY_PROPOSAL_TRANSITIONED,
        target_type="strategy_proposal",
        target_id=row.id,
        payload={"from": old_state, "to": "APPLIED", "applied_changes": applied_changes},
        user_id=current_user.id,
    )
    await session.commit()

    return ApplyProposalResponse(
        proposal_id=proposal_id, state="APPLIED", applied_changes=applied_changes
    )
