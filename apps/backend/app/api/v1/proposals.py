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

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.auth.stub import CurrentUser, get_current_user
from app.db.enums import OrderSourceType, StrategyStatus
from app.db.models.audit_log import AuditLog
from app.db.models.order import Order
from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.db.session import get_session
from app.services.activation import ACTIVATION_COOLDOWN_HOURS
from app.services.drift_detection import (
    DriftFinding,
    DriftSkip,
    DriftWithin,
    run_drift_detection_for_strategy,
    write_drift_audit,
)
from app.services.paper_variant import (
    PaperVariantService,
    VariantComparison,
    VariantSideMetrics,
    compare_variant_to_parent,
    find_in_flight_variant,
)
from app.services.promotion import (
    PROMOTION_LOCKOUT_DAYS,
    in_lockout,
    lockout_expires_at,
)
from app.services.trading_profile import TradingProfileService

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
    # P6 §2b-review: human-review aggregates (additive — defaults keep the
    # response shape backward-compatible for existing callers + the MCP tool).
    n_reviewed: int = 0
    n_thumbs_up: int = 0
    n_thumbs_down: int = 0


class ReviewRequest(BaseModel):
    """P6 §2b-review: a thumbs-up/down review of a sampled proposal. ``reason``
    is always optional (even on thumbs_down — don't make rejection harder than
    acceptance)."""

    rating: str  # "thumbs_up" | "thumbs_down"
    reason: str | None = None


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
    n_reviewed = n_thumbs_up = n_thumbs_down = 0
    latest_complete: dict[str, Any] | None = None
    for r in rows:
        eval_state = r.evaluation_results_json or {}
        status = eval_state.get("status")

        # P6 §2b-review: human-review aggregates (independent of eval status —
        # a skipped/failed eval can still be human-reviewed).
        rating = (eval_state.get("human_review") or {}).get("rating")
        if rating == "thumbs_up":
            n_reviewed += 1
            n_thumbs_up += 1
        elif rating == "thumbs_down":
            n_reviewed += 1
            n_thumbs_down += 1

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
        n_reviewed=n_reviewed,
        n_thumbs_up=n_thumbs_up,
        n_thumbs_down=n_thumbs_down,
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
    request: Request,
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

    # P6b §2b-variant D5: auto-spawn a paper variant on ACCEPT when the user's
    # envelope opts in. Best-effort, AFTER the transition commits — never fail
    # the transition because auto-spawn raced (one row per transaction holds).
    if target == "ACCEPTED":
        await _maybe_auto_validate_proposal(request, session, row, current_user.id)
        await session.refresh(row)

    return _to_response(row)


async def _maybe_auto_validate_proposal(
    request: Request,
    session: AsyncSession,
    proposal: StrategyProposal,
    user_id: int,
) -> None:
    """P6b §2b-variant D5: if ``agent_envelope_json.auto_validate_proposals`` is
    enabled and the parent is LIVE with no in-flight variant, spawn the paper
    variant. Best-effort — ``spawn`` self-guards (raises plain ValueError on
    parent_not_live / variant_already_in_flight / proposal_not_accepted), which
    we swallow so a raced/ineligible auto-spawn never fails the ACCEPT."""
    profile = await TradingProfileService(session).get(user_id)
    envelope = profile.agent_envelope or {}
    if not envelope.get("auto_validate_proposals", False):
        return

    # P6b §3b: don't start a new evaluation cycle during post-promotion lockout
    # (ADR 0007). Silent skip — the ACCEPT still succeeds; only the auto-spawn is
    # held back. The manual /validate returns a 409 instead.
    parent = await session.get(Strategy, proposal.strategy_id)
    if parent is not None and in_lockout(parent, datetime.now(UTC)):
        logger.info(
            "auto_validate_skipped_lockout",
            proposal_id=proposal.id, strategy_id=parent.id,
        )
        return

    engine = getattr(request.app.state, "strategy_engine", None)
    try:
        await PaperVariantService(session, engine).spawn(
            proposal_id=proposal.id, user_id=user_id
        )
    except ValueError as exc:
        logger.info(
            "auto_validate_proposals_skipped",
            proposal_id=proposal.id, reason=str(exc),
        )
    except Exception as exc:  # noqa: BLE001 - best-effort; never fail the ACCEPT
        logger.warning(
            "auto_validate_proposals_failed",
            proposal_id=proposal.id, error=str(exc),
        )


@proposals_router.get("", response_model=ProposalListResponse)
async def list_proposals(
    strategy_id: int | None = None,
    state: str | None = None,
    awaiting_review: bool = False,
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
    if awaiting_review:
        # P6 §2b-review: sampled but not yet rated. Both predicates via
        # func.json_extract (SQLAlchemy Core, the §1a/§2b-backtest pattern).
        # json_extract(...".rating") IS NULL is True when the path is absent
        # OR holds JSON null — both mean "not rated yet".
        q = q.where(
            func.json_extract(
                StrategyProposal.evaluation_results_json,
                "$.human_review.sampled_at",
            ).isnot(None)
        ).where(
            func.json_extract(
                StrategyProposal.evaluation_results_json,
                "$.human_review.rating",
            ).is_(None)
        )
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
    request: Request,
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

    # P6b §2b-variant D8 (ii): terminate any in-flight variant on the parent
    # BEFORE applying (terminate-then-apply ordering; no-op when none). Mostly
    # defensive — apply requires the parent IDLE, so the deactivation D8 hook
    # has usually already cleared the variant; this catches a variant spawned
    # against an IDLE parent out-of-band. Commits internally (§2a contract).
    engine = getattr(request.app.state, "strategy_engine", None)
    await PaperVariantService(session, engine).terminate_for_parent(
        parent_strategy_id=strategy.id,
        reason="parent_proposal_applied",
        user_id=current_user.id,
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


# ----- P6b §1b-drift: on-demand check + per-strategy status -----


def _drift_metrics_dict(m: Any) -> dict[str, Any]:
    return {
        "trade_count": m.trade_count,
        "win_rate": m.win_rate,
        "avg_return_per_trade": m.avg_return_per_trade,
    }


def _drift_result_to_response(result: Any) -> dict[str, Any]:
    """Serialize the sealed §1a DriftResult union to a JSON-safe dict. Three
    explicit branches — the result types are fixed by §1a-drift."""
    if isinstance(result, DriftFinding):
        return {
            "kind": "drift_detected",
            "strategy_id": result.strategy_id,
            "live_metrics": _drift_metrics_dict(result.live_metrics),
            "baseline_metrics": _drift_metrics_dict(result.baseline_metrics),
            "win_rate_delta_pp": result.win_rate_delta_pp,
            "avg_return_delta_pct": result.avg_return_delta_pct,
            "breached": result.breached,
            "detected_at": result.detected_at.isoformat(),
        }
    if isinstance(result, DriftWithin):
        return {
            "kind": "within_thresholds",
            "strategy_id": result.strategy_id,
            "live_metrics": _drift_metrics_dict(result.live_metrics),
            "baseline_metrics": _drift_metrics_dict(result.baseline_metrics),
            "win_rate_delta_pp": result.win_rate_delta_pp,
            "avg_return_delta_pct": result.avg_return_delta_pct,
        }
    if isinstance(result, DriftSkip):
        return {"kind": "skip", "strategy_id": result.strategy_id, "reason": result.reason}
    raise ValueError(  # pragma: no cover - sealed union
        f"Unknown DriftResult subtype: {type(result).__name__}"
    )


@strategies_router.post("/{strategy_id}/drift-check", response_model=dict)
async def drift_check(
    strategy_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """On-demand drift re-evaluation for one strategy (P6b §1b, Q3(d) "check
    now"). Runs §1a detection; audits a finding (one row per txn, the hash-chain
    contract); read-mostly otherwise."""
    strategy = await session.get(Strategy, strategy_id)
    if strategy is None or strategy.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")

    profile = await TradingProfileService(session).get(current_user.id)
    result = await run_drift_detection_for_strategy(
        session, strategy, profile.agent_envelope or {}
    )
    if isinstance(result, DriftFinding):
        write_drift_audit(session, result, user_id=current_user.id)
        await session.commit()
    return _drift_result_to_response(result)


@strategies_router.get("/{strategy_id}/drift-status", response_model=dict)
async def drift_status(
    strategy_id: int,
    lookback_days: int = Query(default=7, ge=1, le=365),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Most recent STRATEGY_DRIFT_DETECTED for the strategy within the window,
    or no_recent_drift (P6b §1b). Read-only — no detection, no audit write."""
    strategy = await session.get(Strategy, strategy_id)
    if strategy is None or strategy.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")

    cutoff = datetime.now(UTC) - timedelta(days=lookback_days)
    row = (
        await session.execute(
            select(AuditLog)
            .where(AuditLog.user_id == current_user.id)
            .where(AuditLog.action == "STRATEGY_DRIFT_DETECTED")
            .where(AuditLog.target_id == str(strategy_id))  # target_id is a STR column
            .where(AuditLog.ts >= cutoff)
            .order_by(AuditLog.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if row is None:
        return {
            "status": "no_recent_drift",
            "strategy_id": strategy_id,
            "lookback_days": lookback_days,
        }
    return {
        "status": "drift_detected",
        "strategy_id": strategy_id,
        "lookback_days": lookback_days,
        "detected_at": row.ts.isoformat(),
        "payload": json.loads(row.payload_json or "{}"),
    }


# ----- P6b §2a-variant: paper-variant spawn / stop -----


@proposals_router.post("/{proposal_id}/validate", response_model=ProposalResponse)
async def validate_on_paper(
    proposal_id: int,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ProposalResponse:
    """P6b §2a: spawn the paper variant for an ACCEPTED proposal on a LIVE
    strategy — validate the proposed params forward on paper (ADR 0007). The
    proposal moves ACCEPTED → EVALUATING."""
    # P6b §3b: a strategy in 30-day post-promotion lockout can't start a new
    # evaluation cycle (ADR 0007). Look up the parent via the proposal to gate.
    proposal = await session.get(StrategyProposal, proposal_id)
    if proposal is not None and proposal.user_id == current_user.id:
        parent = await session.get(Strategy, proposal.strategy_id)
        if parent is not None and in_lockout(parent, datetime.now(UTC)):
            expires = lockout_expires_at(parent)
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Strategy in {PROMOTION_LOCKOUT_DAYS}-day post-promotion "
                    f"lockout until {expires.isoformat() if expires else ''}"
                ),
            )

    engine = getattr(request.app.state, "strategy_engine", None)
    try:
        await PaperVariantService(session, engine).spawn(
            proposal_id=proposal_id, user_id=current_user.id
        )
    except ValueError as exc:
        msg = str(exc)
        if msg in ("proposal_not_found", "parent_not_found"):
            raise HTTPException(status_code=404, detail=msg) from exc
        code = 409 if msg == "variant_already_in_flight" else 400
        raise HTTPException(status_code=code, detail=msg) from exc
    row = await session.get(StrategyProposal, proposal_id)
    if row is None:  # pragma: no cover - just spawned
        raise HTTPException(status_code=404, detail="Proposal not found")
    return _to_response(row)


@proposals_router.post(
    "/{proposal_id}/stop-validation", response_model=ProposalResponse
)
async def stop_validation(
    proposal_id: int,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ProposalResponse:
    """P6b §2a: stop a running paper-variant evaluation (EVALUATING → REJECTED)."""
    row = await session.get(StrategyProposal, proposal_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if row.state != ProposalState.EVALUATING:
        raise HTTPException(status_code=400, detail="Proposal is not evaluating")
    variant_id = (
        (row.evaluation_results_json or {}).get("paper_variant", {}).get(
            "variant_strategy_id"
        )
    )
    if variant_id is None:
        raise HTTPException(status_code=400, detail="No paper variant on this proposal")
    engine = getattr(request.app.state, "strategy_engine", None)
    await PaperVariantService(session, engine).terminate(
        variant_strategy_id=variant_id, reason="user_stopped", user_id=current_user.id
    )
    await session.refresh(row)
    return _to_response(row)


@proposals_router.post("/{proposal_id}/review", response_model=ProposalResponse)
async def submit_review(
    proposal_id: int,
    body: ReviewRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ProposalResponse:
    """P6 §2b-review: record a thumbs-up/down review for a proposal the weekly
    sampling cron queued. Validates "sampled AND not yet rated", merge-writes
    the human_review sub-key (preserving the §2b-backtest eval sub-tree), and
    writes a PROPOSAL_REVIEW_RECORDED audit row. The sampling sweep is silent;
    this user action is the meaningful, audited event."""
    if body.rating not in ("thumbs_up", "thumbs_down"):
        raise HTTPException(
            status_code=400,
            detail=f"rating must be 'thumbs_up' or 'thumbs_down' (got {body.rating!r})",
        )

    row = await session.get(StrategyProposal, proposal_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Proposal not found")

    eval_state = dict(row.evaluation_results_json or {})
    human_review = eval_state.get("human_review")
    if human_review is None:
        raise HTTPException(
            status_code=400, detail="Proposal has not been sampled for review"
        )
    if human_review.get("rating") is not None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Proposal already reviewed at {human_review.get('reviewed_at')} "
                f"with rating {human_review.get('rating')}"
            ),
        )

    # MERGE-WRITE — reassign the column (SQLAlchemy JSON dirty detection is
    # reassignment-based). NON-NEGOTIABLE: never overwrite evaluation_results_json
    # wholesale; preserve status/baseline_metrics/variant_metrics/verdict.
    now = datetime.now(UTC)
    row.evaluation_results_json = {
        **eval_state,
        "human_review": {
            **human_review,
            "reviewed_at": now.isoformat(),
            "rating": body.rating,
            "reason": body.reason,
        },
    }
    row.updated_at = now

    AuditLogger.write(
        session,
        actor_type=AuditActorType.USER,
        actor_id=str(current_user.id),
        action=AuditAction.PROPOSAL_REVIEW_RECORDED,
        target_type="strategy_proposal",
        target_id=row.id,
        payload={
            "proposal_id": row.id,
            "rating": body.rating,
            "reason": body.reason,
        },
        user_id=current_user.id,
    )
    await session.commit()
    await session.refresh(row)
    return _to_response(row)


# ----- P6b §3b-promote: promote / reject-promotion (ADR 0007) -----


def _bundle_hash(bundle: dict[str, Any]) -> str:
    """SHA-256 of the canonicalized evidence bundle — embedded in the promote
    audit row so a future auditor can verify the bundle the user acted on
    (ADR 0007: 'the full evidence bundle at the moment of approval is preserved')."""
    canonical = json.dumps(bundle, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@proposals_router.post("/{proposal_id}/promote", response_model=dict)
async def promote_proposal(
    proposal_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """P6b §3b (ADR 0007): user-gated promotion. EVIDENCE_READY → PROMOTING,
    starting the standard P5 §7 24h cooldown. The paper variant keeps running
    through the cooldown (the live params don't change until the cron applies
    them at PROMOTED); the variant is terminated then, not now. Promotion is
    ALWAYS user-gated — there is no auto-promote."""
    proposal = await session.get(StrategyProposal, proposal_id)
    if proposal is None or proposal.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.state != ProposalState.EVIDENCE_READY:
        raise HTTPException(
            status_code=400,
            detail=f"Proposal must be EVIDENCE_READY to promote (current: {proposal.state.value})",
        )

    parent = await session.get(Strategy, proposal.strategy_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="Parent strategy not found")
    if parent.status != StrategyStatus.LIVE:
        raise HTTPException(
            status_code=409,
            detail=f"Parent strategy must be LIVE to promote (current: {parent.status.value})",
        )

    now = datetime.now(UTC)
    if in_lockout(parent, now):
        expires = lockout_expires_at(parent)
        raise HTTPException(
            status_code=409,
            detail=(
                f"Strategy in {PROMOTION_LOCKOUT_DAYS}-day post-promotion lockout "
                f"until {expires.isoformat() if expires else ''}"
            ),
        )

    bundle = (proposal.evaluation_results_json or {}).get("evidence_bundle")
    if bundle is None:  # EVIDENCE_READY without a bundle is inconsistent state.
        raise HTTPException(
            status_code=409,
            detail="Proposal lacks an evidence bundle (re-evaluate via the morning brief)",
        )

    cooldown_expires = now + timedelta(hours=ACTIVATION_COOLDOWN_HOURS)
    proposal.state = ProposalState.PROMOTING
    proposal.transitioned_at = now  # the PROMOTING-entry anchor for the cron
    proposal.updated_at = now
    AuditLogger.write(
        session,
        actor_type=AuditActorType.USER,
        actor_id=str(current_user.id),
        action=AuditAction.STRATEGY_PROPOSAL_TRANSITIONED,
        target_type="strategy_proposal",
        target_id=proposal.id,
        payload={
            "proposal_id": proposal.id,
            "from": "EVIDENCE_READY",
            "to": "PROMOTING",
            "trigger": "user_promoted",
            "evidence_bundle_hash": _bundle_hash(bundle),
            "cooldown_expires_at": cooldown_expires.isoformat(),
        },
        user_id=current_user.id,
    )
    await session.commit()
    return {
        "status": "promoting",
        "proposal_id": proposal.id,
        "promoting_at": now.isoformat(),
        "cooldown_expires_at": cooldown_expires.isoformat(),
    }


@proposals_router.post("/{proposal_id}/reject-promotion", response_model=dict)
async def reject_promotion(
    proposal_id: int,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """P6b §3b: user rejection — one endpoint serving 'Reject evidence' (from
    EVIDENCE_READY) and 'Cancel cooldown' (from PROMOTING, frictionless per ADR
    0007). Both → REJECTED (terminal) and terminate the paper variant. Terminate
    FIRST (its own commit) then the transition (one audit row per commit)."""
    proposal = await session.get(StrategyProposal, proposal_id)
    if proposal is None or proposal.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.state not in (ProposalState.EVIDENCE_READY, ProposalState.PROMOTING):
        raise HTTPException(
            status_code=400,
            detail=(
                "Proposal must be EVIDENCE_READY or PROMOTING to reject "
                f"(current: {proposal.state.value})"
            ),
        )

    from_state = proposal.state.value
    # Terminate the in-flight variant first (commits internally; no-op if gone).
    engine = getattr(request.app.state, "strategy_engine", None)
    await PaperVariantService(session, engine).terminate_for_parent(
        parent_strategy_id=proposal.strategy_id,
        reason=(
            "evidence_rejected" if from_state == "EVIDENCE_READY"
            else "promotion_cancelled"
        ),
        user_id=current_user.id,
    )

    now = datetime.now(UTC)
    proposal.state = ProposalState.REJECTED
    proposal.transitioned_at = now
    proposal.updated_at = now
    AuditLogger.write(
        session,
        actor_type=AuditActorType.USER,
        actor_id=str(current_user.id),
        action=AuditAction.STRATEGY_PROPOSAL_TRANSITIONED,
        target_type="strategy_proposal",
        target_id=proposal.id,
        payload={
            "proposal_id": proposal.id,
            "from": from_state,
            "to": "REJECTED",
            "trigger": (
                "user_rejected_evidence" if from_state == "EVIDENCE_READY"
                else "user_cancelled_promotion"
            ),
        },
        user_id=current_user.id,
    )
    await session.commit()
    return {"status": "rejected", "proposal_id": proposal.id, "from_state": from_state}


# ----- P6b §2b-variant: variant-vs-live comparison (read-only) -----


def _variant_side_metrics_dict(m: VariantSideMetrics) -> dict[str, Any]:
    return {
        "trade_count": m.trade_count,
        "win_rate": m.win_rate,
        "avg_return_per_trade": m.avg_return_per_trade,
        "sharpe_ratio": m.sharpe_ratio,
        "max_drawdown": m.max_drawdown,
    }


def _equity_curve_dicts(curve: list[Any]) -> list[dict[str, Any]]:
    """Serialize an equity curve [(ts, Decimal)] to chart-ready points."""
    return [{"ts": ts.isoformat(), "equity": float(eq)} for ts, eq in curve]


def _variant_comparison_dict(
    comp: VariantComparison, *, spawn_proposal_id: int | None
) -> dict[str, Any]:
    return {
        "parent_strategy_id": comp.parent_strategy_id,
        "variant_strategy_id": comp.variant_strategy_id,
        # P6b §2c: the spawn proposal id (for the Stop-validation button) +
        # the equity-curve series (for the strategy-detail chart). Additive —
        # existing clients (the §2b MCP tool) ignore the new keys.
        "spawn_proposal_id": spawn_proposal_id,
        "window_start": comp.window_start.isoformat(),
        "window_end": comp.window_end.isoformat(),
        "live_metrics": _variant_side_metrics_dict(comp.live_metrics),
        "variant_metrics": _variant_side_metrics_dict(comp.variant_metrics),
        "deltas": comp.deltas,
        "live_trade_count": comp.live_trade_count,
        "variant_trade_count": comp.variant_trade_count,
        "live_equity_curve": _equity_curve_dicts(comp.live_equity_curve),
        "variant_equity_curve": _equity_curve_dicts(comp.variant_equity_curve),
    }


async def _active_validation_proposal_for_parent(
    session: AsyncSession, parent_strategy_id: int
) -> StrategyProposal | None:
    """The parent's proposal currently in an active-validation/promotion state
    (EVALUATING | EVIDENCE_READY | PROMOTING). Broadened from §2c's EVALUATING-
    only lookup (P6b §3b correction A2) so the promote UI + MCP additive fields
    resolve the proposal through the whole lifecycle, not just EVALUATING. At
    most one in-flight per parent (the §2a concurrency guard). Source of
    ``spawn_proposal_id`` for the Stop/Promote/Reject buttons."""
    return (
        await session.execute(
            select(StrategyProposal)
            .where(StrategyProposal.strategy_id == parent_strategy_id)
            .where(
                StrategyProposal.state.in_(
                    [
                        ProposalState.EVALUATING,
                        ProposalState.EVIDENCE_READY,
                        ProposalState.PROMOTING,
                    ]
                )
            )
            .order_by(StrategyProposal.id.desc())
        )
    ).scalars().first()


@strategies_router.get("/{strategy_id}/variant-comparison", response_model=dict)
async def variant_comparison(
    strategy_id: int,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Variant-vs-live comparison for the in-flight paper variant of
    ``strategy_id`` (the parent). Read-only — no detection, no audit write.
    Returns ``{"status": "no_active_variant", ...}`` when the strategy has no
    in-flight variant (always carries ``parent_last_promoted_at`` so the UI can
    render the post-promotion lockout state)."""
    parent = await session.get(Strategy, strategy_id)
    if parent is None or parent.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")

    now = datetime.now(UTC)
    parent_last_promoted_at = (
        parent.last_promoted_at.isoformat() if parent.last_promoted_at else None
    )

    variant = await find_in_flight_variant(session, strategy_id)
    if variant is None:
        return {
            "status": "no_active_variant",
            "strategy_id": strategy_id,
            "parent_last_promoted_at": parent_last_promoted_at,
        }

    # bar_cache lives in app.state only when the alpaca block is configured;
    # getattr-guard it (None → equity curves degenerate gracefully — Norton/dev).
    bar_cache = getattr(request.app.state, "bar_cache", None)
    comparison = await compare_variant_to_parent(
        session, variant.id, bar_cache=bar_cache
    )
    if comparison is None:  # pragma: no cover - variant vanished mid-request
        return {
            "status": "no_active_variant",
            "strategy_id": strategy_id,
            "parent_last_promoted_at": parent_last_promoted_at,
        }

    proposal = await _active_validation_proposal_for_parent(session, strategy_id)
    comp_dict = _variant_comparison_dict(
        comparison, spawn_proposal_id=proposal.id if proposal else None
    )
    # P6b §3b additive fields (for the promote UI + MCP tool).
    comp_dict["proposal_state"] = proposal.state.value if proposal else None
    comp_dict["evidence_bundle"] = (
        (proposal.evaluation_results_json or {}).get("evidence_bundle")
        if proposal
        else None
    )
    comp_dict["eligible_for_promotion"] = bool(
        proposal
        and proposal.state == ProposalState.EVIDENCE_READY
        and not in_lockout(parent, now)
    )
    comp_dict["parent_last_promoted_at"] = parent_last_promoted_at
    return {
        "status": "variant_active",
        "strategy_id": strategy_id,
        "variant_strategy_id": variant.id,
        "comparison": comp_dict,
    }
