"""Discovery scanner endpoints (P8 §2).

Save a criterion + universe spec, run it against cached-bar indicators, and read
the recorded runs. Deterministic — no LLM (P8 Decision 1). Auth-gated, user-scoped.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.scanner import (
    ScannerDefinitionCreate,
    ScannerDefinitionResponse,
    ScannerMatchItem,
    ScannerRunResponse,
    ScannerRunSummary,
    ScannerSkipItem,
    ScannerVocabulary,
)
from app.audit.logger import AuditAction, AuditActorType, AuditLogger
from app.auth.stub import CurrentUser, get_current_user
from app.db.models.scanner_definition import UNIVERSE_KINDS, UNIVERSE_SYMBOLS, ScannerDefinition
from app.db.models.scanner_run import RUN_OK, ScannerRun
from app.db.session import get_session
from app.indicators.computer import IndicatorComputer
from app.market_data.discovery import get_discovery_feeds
from app.services.scanner import CriteriaError, run_scan, validate_criteria
from app.services.scanner.criteria import FIELD_NAMES, INDICATOR_NAMES

router = APIRouter(prefix="/scanner", tags=["scanner"])


def _validate_body(body: ScannerDefinitionCreate) -> None:
    if body.universe.kind not in UNIVERSE_KINDS:
        raise HTTPException(
            status_code=400, detail=f"unknown universe kind: {body.universe.kind}"
        )
    if body.universe.kind == UNIVERSE_SYMBOLS and not body.universe.symbols:
        raise HTTPException(
            status_code=400, detail="universe kind 'symbols' requires a symbol list"
        )
    try:
        validate_criteria(body.criteria)
    except CriteriaError as exc:
        raise HTTPException(
            status_code=400, detail=f"invalid criterion: {exc}"
        ) from exc


@router.get("/vocabulary", response_model=ScannerVocabulary)
async def get_vocabulary(
    _user: CurrentUser = Depends(get_current_user),
) -> ScannerVocabulary:
    """The supported criterion names — drift-proof (derived from CORE_INDICATORS)."""
    return ScannerVocabulary(
        indicators=sorted(INDICATOR_NAMES), fields=sorted(FIELD_NAMES)
    )


def _def_to_response(d: ScannerDefinition) -> ScannerDefinitionResponse:
    return ScannerDefinitionResponse(
        id=d.id,
        name=d.name,
        criteria=d.criteria,
        universe_kind=d.universe_kind,
        universe_symbols=d.universe_symbols_json,
        timeframe=d.timeframe,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


def _run_to_summary(r: ScannerRun) -> ScannerRunSummary:
    return ScannerRunSummary(
        id=r.id,
        scanner_definition_id=r.scanner_definition_id,
        run_at=r.run_at,
        status=r.status,
        universe_size=r.universe_size,
        evaluated_count=r.evaluated_count,
        matched_count=r.matched_count,
        skipped_count=r.skipped_count,
        error=r.error,
    )


def _run_to_response(r: ScannerRun) -> ScannerRunResponse:
    return ScannerRunResponse(
        **_run_to_summary(r).model_dump(),
        criteria_snapshot=r.criteria_snapshot,
        universe_kind=r.universe_kind,
        timeframe=r.timeframe,
        matched=[ScannerMatchItem(**m) for m in r.matched_json],
        skipped=[ScannerSkipItem(**s) for s in r.skipped_json],
    )


async def _owned_definition(
    session: AsyncSession, definition_id: int, user_id: int
) -> ScannerDefinition:
    d = (
        await session.execute(
            select(ScannerDefinition).where(
                ScannerDefinition.id == definition_id,
                ScannerDefinition.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if d is None:
        raise HTTPException(status_code=404, detail="scanner definition not found")
    return d


@router.post(
    "/definitions",
    response_model=ScannerDefinitionResponse,
    status_code=201,
)
async def create_definition(
    body: ScannerDefinitionCreate,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ScannerDefinitionResponse:
    _validate_body(body)
    now = datetime.now(UTC)
    d = ScannerDefinition(
        user_id=user.id,
        name=body.name,
        criteria=body.criteria,
        universe_kind=body.universe.kind,
        universe_symbols_json=(
            [s.upper() for s in body.universe.symbols]
            if body.universe.symbols
            else None
        ),
        timeframe=body.timeframe,
        created_at=now,
        updated_at=now,
    )
    session.add(d)
    await session.commit()
    await session.refresh(d)
    return _def_to_response(d)


@router.put(
    "/definitions/{definition_id}", response_model=ScannerDefinitionResponse
)
async def update_definition(
    definition_id: int,
    body: ScannerDefinitionCreate,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ScannerDefinitionResponse:
    """Edit a saved definition in place (preserves its run history)."""
    d = await _owned_definition(session, definition_id, user.id)
    _validate_body(body)
    d.name = body.name
    d.criteria = body.criteria
    d.universe_kind = body.universe.kind
    d.universe_symbols_json = (
        [s.upper() for s in body.universe.symbols] if body.universe.symbols else None
    )
    d.timeframe = body.timeframe
    d.updated_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(d)
    return _def_to_response(d)


@router.get("/definitions", response_model=list[ScannerDefinitionResponse])
async def list_definitions(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ScannerDefinitionResponse]:
    rows = (
        await session.execute(
            select(ScannerDefinition)
            .where(ScannerDefinition.user_id == user.id)
            .order_by(ScannerDefinition.created_at.desc())
        )
    ).scalars().all()
    return [_def_to_response(d) for d in rows]


@router.get(
    "/definitions/{definition_id}", response_model=ScannerDefinitionResponse
)
async def get_definition(
    definition_id: int,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ScannerDefinitionResponse:
    return _def_to_response(await _owned_definition(session, definition_id, user.id))


@router.delete("/definitions/{definition_id}", status_code=204)
async def delete_definition(
    definition_id: int,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    d = await _owned_definition(session, definition_id, user.id)
    await session.delete(d)
    await session.commit()


@router.post(
    "/definitions/{definition_id}/run", response_model=ScannerRunResponse
)
async def run_definition(
    definition_id: int,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ScannerRunResponse:
    d = await _owned_definition(session, definition_id, user.id)

    bar_cache = getattr(request.app.state, "bar_cache", None)
    if bar_cache is None:
        raise HTTPException(
            status_code=503, detail="scanner unavailable (bar cache not wired)"
        )

    now = datetime.now(UTC)
    result = await run_scan(
        session,
        criteria=d.criteria,
        universe_kind=d.universe_kind,
        universe_symbols=d.universe_symbols_json,
        timeframe=d.timeframe,
        user_id=user.id,
        bar_cache=bar_cache,
        indicator_computer=IndicatorComputer(),
        discovery_feeds_fn=get_discovery_feeds,
        now=now,
    )

    matched_json = [{"symbol": m.symbol, "values": m.values} for m in result.matched]
    skipped_json = [{"symbol": s.symbol, "reason": s.reason} for s in result.skipped]
    run = ScannerRun(
        scanner_definition_id=d.id,
        user_id=user.id,
        run_at=now,
        status=RUN_OK,
        criteria_snapshot=d.criteria,
        universe_kind=d.universe_kind,
        timeframe=d.timeframe,
        universe_size=result.universe_size,
        evaluated_count=result.evaluated,
        matched_count=len(result.matched),
        skipped_count=len(result.skipped),
        matched_json=matched_json,
        skipped_json=skipped_json,
        error=None,
    )
    session.add(run)

    AuditLogger.write(
        session,
        actor_type=AuditActorType.USER,
        actor_id=str(user.id),
        action=AuditAction.SCANNER_RUN,
        target_type="scanner_definition",
        target_id=d.id,
        user_id=user.id,
        payload={
            "criteria": d.criteria,
            "universe_kind": d.universe_kind,
            "timeframe": d.timeframe,
            "universe_size": result.universe_size,
            "matched_count": len(result.matched),
            "skipped_count": len(result.skipped),
            "matched_symbols": [m.symbol for m in result.matched],
        },
    )
    await session.commit()
    await session.refresh(run)
    return _run_to_response(run)


@router.get(
    "/definitions/{definition_id}/runs",
    response_model=list[ScannerRunSummary],
)
async def list_runs(
    definition_id: int,
    limit: int = Query(20, ge=1, le=100),
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ScannerRunSummary]:
    await _owned_definition(session, definition_id, user.id)
    rows = (
        await session.execute(
            select(ScannerRun)
            .where(ScannerRun.scanner_definition_id == definition_id)
            .order_by(ScannerRun.run_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return [_run_to_summary(r) for r in rows]


@router.get("/runs/{run_id}", response_model=ScannerRunResponse)
async def get_run(
    run_id: int,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ScannerRunResponse:
    r = (
        await session.execute(
            select(ScannerRun).where(
                ScannerRun.id == run_id, ScannerRun.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="scanner run not found")
    return _run_to_response(r)
