"""REST endpoints for ``/api/v1/strategies`` and per-strategy sub-resources.

Lifecycle::

    POST   /strategies                        Register a new strategy
    GET    /strategies                        List
    GET    /strategies/{id}                   Detail
    PUT    /strategies/{id}                   Update (only when status=IDLE)
    POST   /strategies/{id}/start             Engine.register; status -> PAPER
    POST   /strategies/{id}/stop              Engine.unregister; status -> IDLE
    POST   /strategies/{id}/backtest          Sync backtest; persists + returns
    GET    /strategies/{id}/runs              Strategy run history
    GET    /strategies/{id}/signals           Signals emitted by this strategy
    GET    /strategies/{id}/backtests         Past backtest results (summary)
    GET    /strategies/{id}/backtests/{bid}   One backtest result (full)
"""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.strategies import (
    BacktestJobListResponse,
    BacktestJobResponse,
    BacktestJobSubmittedResponse,
    BacktestListResponse,
    BacktestRequest,
    BacktestResultResponse,
    BacktestResultSummary,
    SignalListResponse,
    SignalResponse,
    StrategyActionResponse,
    StrategyCreateRequest,
    StrategyListResponse,
    StrategyResponse,
    StrategyRunListResponse,
    StrategyRunResponse,
    StrategyUpdateRequest,
)
from app.audit import AuditAction, AuditActorType, AuditLogger
from app.auth.stub import CurrentUser, get_current_user
from app.db.enums import (
    ACTIVE_STRATEGY_STATUSES,
    PENDING_BACKTEST_JOB_STATUSES,
    BacktestJobStatus,
    StrategyStatus,
    StrategyType,
)
from app.db.models.backtest_job import BacktestJob
from app.db.models.backtest_result import BacktestResult
from app.db.models.signal import Signal
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.strategy_run import StrategyRun
from app.db.models.symbol import Symbol
from app.db.session import get_session
from app.events import get_event_bus
from app.services.strategy_cooldown import StrategyCooldownService
from app.strategies import StrategyLoader, StrategyLoadError

router = APIRouter(prefix="/strategies", tags=["strategies"])


# ---------- helpers ----------


def _get_engine(request: Request):
    engine = getattr(request.app.state, "strategy_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Strategy engine not initialized")
    return engine


def _strategies_root() -> Path:
    return Path("strategies_user")


def _strategy_to_response(row: StrategyRow) -> StrategyResponse:
    return StrategyResponse.model_validate(row, from_attributes=True)


async def _signal_to_response(
    session: AsyncSession, signal: Signal
) -> SignalResponse:
    sym = await session.get(Symbol, signal.symbol_id)
    return SignalResponse(
        id=signal.id,
        strategy_id=signal.strategy_id,
        symbol=sym.ticker if sym else "?",
        payload=signal.payload_json,
        type=signal.type,
        received_at=signal.received_at,
        processed_at=signal.processed_at,
    )


# ---------- POST /strategies ----------


@router.post("", response_model=StrategyResponse)
async def create_strategy(
    body: StrategyCreateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StrategyResponse:
    # P2 only handles PYTHON strategies. PINE/AGENT enum entries exist for
    # later phases; reject them here so the engine never sees an unsupported
    # type.
    if body.type != StrategyType.PYTHON:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Strategy type {body.type.value} is reserved but not "
                "supported until later phases"
            ),
        )
    if not body.code_path:
        raise HTTPException(
            status_code=400, detail="code_path is required for python strategies"
        )

    # Validate the loader can resolve code_path BEFORE persisting — keeps the
    # DB from ever holding an unloadable row.
    try:
        loader = StrategyLoader(_strategies_root())
        cls = loader.load(body.code_path)
    except StrategyLoadError as exc:
        raise HTTPException(
            status_code=400, detail=f"Strategy file invalid: {exc}"
        ) from exc

    symbols = body.symbols or list(cls.symbols)
    now = datetime.now(UTC)
    row = StrategyRow(
        user_id=current_user.id,
        name=body.name,
        version=body.version,
        type=body.type,
        status=StrategyStatus.IDLE,
        code_path=body.code_path,
        params_json=body.params,
        symbols_json=symbols,
        schedule=body.schedule,
        risk_limits_id=body.risk_limits_id,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.flush()

    AuditLogger.write(
        session,
        actor_type=AuditActorType.USER,
        actor_id=str(current_user.id),
        action=AuditAction.STRATEGY_REGISTERED,
        target_type="strategy",
        target_id=row.id,
        payload={
            "name": body.name,
            "version": body.version,
            "code_path": body.code_path,
            "symbols": symbols,
        },
        user_id=current_user.id,
    )
    await session.commit()
    await session.refresh(row)
    return _strategy_to_response(row)


# ---------- GET /strategies ----------


@router.get("", response_model=StrategyListResponse)
async def list_strategies(
    status: StrategyStatus | None = Query(default=None),
    type_: StrategyType | None = Query(default=None, alias="type"),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StrategyListResponse:
    stmt = select(StrategyRow).where(StrategyRow.user_id == current_user.id)
    if status is not None:
        stmt = stmt.where(StrategyRow.status == status)
    if type_ is not None:
        stmt = stmt.where(StrategyRow.type == type_)
    stmt = stmt.order_by(StrategyRow.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    items = [_strategy_to_response(r) for r in rows]
    return StrategyListResponse(items=items, count=len(items))


# ---------- GET /strategies/{id} ----------


@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: int,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StrategyResponse:
    row = await session.get(StrategyRow, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")

    # P4 §7: inject the in-memory params_schema for the form-rendering
    # frontend. The list endpoint intentionally omits this to keep its
    # payload small; only the detail endpoint pays the cost.
    schema: dict | None = None
    engine = getattr(request.app.state, "strategy_engine", None)
    if engine is not None:
        get_schema = getattr(engine, "get_params_schema", None)
        if callable(get_schema):
            schema = get_schema(strategy_id)

    resp = _strategy_to_response(row)
    if schema is not None:
        resp = resp.model_copy(update={"params_schema": schema})
    return resp


# ---------- PUT /strategies/{id} ----------


@router.put("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: int,
    body: StrategyUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StrategyResponse:
    row = await session.get(StrategyRow, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if row.status != StrategyStatus.IDLE:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Strategy is in status {row.status.value}; "
                "stop it before updating."
            ),
        )

    changed: dict = {}
    if body.params is not None:
        row.params_json = body.params
        changed["params"] = body.params
    if body.symbols is not None:
        row.symbols_json = body.symbols
        changed["symbols"] = body.symbols
    if body.schedule is not None:
        row.schedule = body.schedule
        changed["schedule"] = body.schedule
    if body.risk_limits_id is not None:
        row.risk_limits_id = body.risk_limits_id
        changed["risk_limits_id"] = body.risk_limits_id
    if body.version is not None:
        row.version = body.version
        changed["version"] = body.version

    row.updated_at = datetime.now(UTC)

    AuditLogger.write(
        session,
        actor_type=AuditActorType.USER,
        actor_id=str(current_user.id),
        action=AuditAction.STRATEGY_UPDATED,
        target_type="strategy",
        target_id=row.id,
        payload={"changed": changed},
        user_id=current_user.id,
    )
    await session.commit()
    await session.refresh(row)
    return _strategy_to_response(row)


# ---------- POST /strategies/{id}/start ----------


@router.post("/{strategy_id}/start", response_model=StrategyActionResponse)
async def start_strategy(
    strategy_id: int,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StrategyActionResponse:
    row = await session.get(StrategyRow, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    # Idempotent: already-active strategy returns current state without
    # touching the engine.
    if row.status in ACTIVE_STRATEGY_STATUSES:
        return StrategyActionResponse(
            strategy_id=strategy_id,
            action="start",
            new_status=row.status,
            run_id=None,
        )

    engine = _get_engine(request)
    try:
        running = await engine.register(strategy_id)
    except StrategyLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Engine register failed: {exc}"
        ) from exc

    # Re-fetch row so the response reflects what's actually in the DB
    # (engine.register may have transitioned to ERROR mid-init).
    await session.refresh(row)
    return StrategyActionResponse(
        strategy_id=strategy_id,
        action="start",
        new_status=row.status,
        run_id=running.run_id,
    )


# ---------- POST /strategies/{id}/stop ----------


@router.post("/{strategy_id}/stop", response_model=StrategyActionResponse)
async def stop_strategy(
    strategy_id: int,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StrategyActionResponse:
    row = await session.get(StrategyRow, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")

    engine = _get_engine(request)
    await engine.unregister(strategy_id, reason="user_stop")

    await session.refresh(row)
    return StrategyActionResponse(
        strategy_id=strategy_id,
        action="stop",
        new_status=row.status,
        run_id=None,
    )


# ---------- POST /strategies/{id}/reload (P4 §4) ----------


@router.post("/{strategy_id}/reload", response_model=StrategyActionResponse)
async def reload_strategy(
    strategy_id: int,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StrategyActionResponse:
    """Reload a strategy: stop → re-import → start (P4 §4).

    For an active strategy: ``engine.unregister`` then ``engine.register``,
    which forces a fresh module import. For an IDLE strategy: no engine
    calls; we just clear the pending flag (the next ``/start`` will pick
    up the new code).

    The pending-reload flag clears as part of this call regardless of
    whether the re-register succeeds. If the new file has a syntax error
    or import bug, the engine transitions the strategy to ERROR with
    ``error_text``; saving the file again produces a new
    ``strategy.pending_reload`` event.
    """
    row = await session.get(StrategyRow, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if row.type != StrategyType.PYTHON:
        raise HTTPException(
            status_code=400,
            detail="Only python strategies are reloadable.",
        )

    engine = _get_engine(request)
    was_active = row.status in ACTIVE_STRATEGY_STATUSES

    if was_active:
        try:
            await engine.unregister(strategy_id, reason="reload")
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"Stop during reload failed: {exc}"
            ) from exc

    # Clear the pending flag before we re-register — if re-register raises
    # (e.g. import error), the user fixing the file will produce a new
    # pending event. Leaving the flag set after a failed reload would
    # confuse the UI.
    row.has_pending_reload = False
    row.pending_reload_at = None
    row.updated_at = datetime.now(UTC)

    AuditLogger.write(
        session,
        actor_type=AuditActorType.USER,
        actor_id=str(current_user.id),
        action=AuditAction.STRATEGY_UPDATED,
        target_type="strategy",
        target_id=strategy_id,
        payload={"action": "reload", "was_active": was_active},
        user_id=current_user.id,
    )
    await session.commit()

    new_run_id: int | None = None
    if was_active:
        try:
            running = await engine.register(strategy_id)
            new_run_id = running.run_id
        except StrategyLoadError as exc:
            raise HTTPException(
                status_code=400, detail=f"Reload failed: {exc}"
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail=f"Reload failed: {exc}"
            ) from exc

    await session.refresh(row)
    return StrategyActionResponse(
        strategy_id=strategy_id,
        action="reload",
        new_status=row.status,
        run_id=new_run_id,
    )


# ---------- POST /strategies/{id}/backtest (async, P4 §2) ----------


@router.post(
    "/{strategy_id}/backtest",
    response_model=BacktestJobSubmittedResponse,
    status_code=202,
)
async def submit_backtest(
    strategy_id: int,
    body: BacktestRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BacktestJobSubmittedResponse:
    """Submit a backtest for asynchronous execution.

    Returns 202 immediately with a ``job_id``. Subscribe to the
    ``backtests`` WS topic and filter on this job_id to follow progress;
    poll ``GET /api/v1/backtest-jobs/{job_id}`` for a fallback.

    Single-flight per strategy: a second submission while a job for the
    same strategy is QUEUED or RUNNING returns 409. The 1-year range cap
    that bounded the old synchronous endpoint is gone — async means no
    HTTP timeout pressure.
    """
    row = await session.get(StrategyRow, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if row.type != StrategyType.PYTHON:
        raise HTTPException(
            status_code=400,
            detail="Only python strategies are backtestable in P2",
        )
    if body.end <= body.start:
        raise HTTPException(status_code=400, detail="end must be after start")

    # Single-flight: refuse if a pending job already exists for this strategy.
    existing = (
        await session.execute(
            select(BacktestJob).where(
                BacktestJob.strategy_id == strategy_id,
                BacktestJob.status.in_(list(PENDING_BACKTEST_JOB_STATUSES)),
            )
        )
    ).scalars().first()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Backtest job {existing.id} for this strategy is still "
                f"{existing.status.value}. Wait or cancel it first."
            ),
        )

    symbols = body.symbols or list(row.symbols_json) or []
    merged_params = {**(row.params_json or {}), **body.params}

    # Persist the full config so the worker can rehydrate after a restart.
    # ``_symbols`` is an underscore-prefixed worker-internal key.
    config_dict = {
        "start": body.start.isoformat(),
        "end": body.end.isoformat(),
        "initial_equity": str(body.initial_equity),
        "slippage_bps": body.slippage_bps,
        "commission_per_share": body.commission_per_share,
        "timeframe": body.timeframe,
        "params": merged_params,
        "_symbols": symbols,
    }

    job = BacktestJob(
        user_id=current_user.id,
        strategy_id=strategy_id,
        status=BacktestJobStatus.QUEUED,
        config_json=config_dict,
        label=body.label,
        percent_complete=0.0,
        submitted_at=datetime.now(UTC),
    )
    session.add(job)
    await session.flush()

    AuditLogger.write(
        session,
        actor_type=AuditActorType.USER,
        actor_id=str(current_user.id),
        action=AuditAction.STRATEGY_BACKTESTED,
        target_type="backtest_job",
        target_id=job.id,
        payload={
            "strategy_id": strategy_id,
            "range_start": body.start.isoformat(),
            "range_end": body.end.isoformat(),
            "label": body.label,
        },
        user_id=current_user.id,
    )
    await session.commit()
    await session.refresh(job)

    bus = get_event_bus()
    with contextlib.suppress(Exception):
        await bus.publish(
            "backtest.queued",
            {
                "job_id": job.id,
                "strategy_id": strategy_id,
                "label": body.label,
            },
        )

    return BacktestJobSubmittedResponse(
        job_id=job.id,
        strategy_id=strategy_id,
        status=job.status,
        submitted_at=job.submitted_at,
    )


# ---------- GET /strategies/{id}/backtest-jobs ----------


@router.get(
    "/{strategy_id}/backtest-jobs", response_model=BacktestJobListResponse
)
async def list_strategy_backtest_jobs(
    strategy_id: int,
    status: BacktestJobStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BacktestJobListResponse:
    row = await session.get(StrategyRow, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    stmt = select(BacktestJob).where(BacktestJob.strategy_id == strategy_id)
    if status is not None:
        stmt = stmt.where(BacktestJob.status == status)
    stmt = stmt.order_by(BacktestJob.submitted_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return BacktestJobListResponse(
        items=[BacktestJobResponse.model_validate(r, from_attributes=True) for r in rows],
        count=len(rows),
    )


# ---------- GET /strategies/{id}/runs ----------


@router.get("/{strategy_id}/runs", response_model=StrategyRunListResponse)
async def list_runs(
    strategy_id: int,
    limit: int = Query(default=50, ge=1, le=500),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StrategyRunListResponse:
    row = await session.get(StrategyRow, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    runs = (
        await session.execute(
            select(StrategyRun)
            .where(StrategyRun.strategy_id == strategy_id)
            .order_by(StrategyRun.started_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return StrategyRunListResponse(
        items=[
            StrategyRunResponse.model_validate(r, from_attributes=True)
            for r in runs
        ],
        count=len(runs),
    )


# ---------- GET /strategies/{id}/signals ----------


@router.get("/{strategy_id}/signals", response_model=SignalListResponse)
async def list_strategy_signals(
    strategy_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SignalListResponse:
    row = await session.get(StrategyRow, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    signals = (
        await session.execute(
            select(Signal)
            .where(Signal.strategy_id == strategy_id)
            .order_by(Signal.received_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    items = [await _signal_to_response(session, s) for s in signals]
    return SignalListResponse(items=items, count=len(items))


# ---------- GET /strategies/{id}/backtests ----------


@router.get("/{strategy_id}/backtests", response_model=BacktestListResponse)
async def list_strategy_backtests(
    strategy_id: int,
    limit: int = Query(default=50, ge=1, le=500),
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BacktestListResponse:
    row = await session.get(StrategyRow, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    results = (
        await session.execute(
            select(BacktestResult)
            .where(BacktestResult.strategy_id == strategy_id)
            .order_by(BacktestResult.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return BacktestListResponse(
        items=[
            BacktestResultSummary.model_validate(r, from_attributes=True)
            for r in results
        ],
        count=len(results),
    )


# ---------- GET /strategies/{id}/backtests/{backtest_id} ----------


@router.get(
    "/{strategy_id}/backtests/{backtest_id}",
    response_model=BacktestResultResponse,
)
async def get_strategy_backtest(
    strategy_id: int,
    backtest_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> BacktestResultResponse:
    row = await session.get(StrategyRow, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    result = await session.get(BacktestResult, backtest_id)
    if result is None or result.strategy_id != strategy_id:
        raise HTTPException(status_code=404, detail="Backtest result not found")
    return BacktestResultResponse.model_validate(result, from_attributes=True)


# ---------- P5 §6: per-strategy cooldown ----------


class CooldownStatusResponse(BaseModel):
    strategy_id: int
    in_cooldown: bool
    cooldown_until: datetime | None
    seconds_remaining: int


@router.get("/{strategy_id}/cooldown", response_model=CooldownStatusResponse)
async def strategy_cooldown_status(
    strategy_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CooldownStatusResponse:
    strategy = await session.get(StrategyRow, strategy_id)
    if strategy is None or strategy.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    status = await StrategyCooldownService(session).status(strategy_id)
    return CooldownStatusResponse(
        strategy_id=status.strategy_id,
        in_cooldown=status.in_cooldown,
        cooldown_until=status.cooldown_until,
        seconds_remaining=status.seconds_remaining,
    )


@router.post("/{strategy_id}/cooldown/clear")
async def clear_strategy_cooldown(
    strategy_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    try:
        await StrategyCooldownService(session).clear_cooldown(
            strategy_id, user_id=current_user.id
        )
    except PermissionError:
        raise HTTPException(status_code=404, detail="Strategy not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "strategy_id": strategy_id}
