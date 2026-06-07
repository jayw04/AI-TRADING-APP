"""Strategy-authoring endpoints (P7 §2).

POST /strategies/author — generate a Python strategy from a plain-English
description (Sonnet tool-use). Generate-and-return only; the trader reviews the
code + assumptions and saves separately (§4). A fresh module, off the P2 gate.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.auth.stub import CurrentUser, get_current_user
from app.db.enums import StrategyStatus, StrategyType
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.strategy_revision import REVISION_GENERATION, StrategyRevision
from app.db.session import get_session
from app.services.strategy_authoring.backtest import BacktestOutcome, backtest_generated_code
from app.services.strategy_authoring.code_safety import UnsafeCodeError, validate_generated_code
from app.services.strategy_authoring.service import (
    AuthoringError,
    BudgetExceededError,
    GenerationError,
    GenerationResult,
    NoApiKeyError,
    authoring_budget,
    debug_strategy,
    generate_strategy,
    refine_strategy,
)
from app.strategies import StrategyLoader, StrategyLoadError

router = APIRouter(tags=["strategy-authoring"])


def _strategies_root() -> Path:
    return Path("strategies_user")


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


class AuthorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=4000)


class RefineRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prior_code: str = Field(min_length=1, max_length=40000)
    request: str = Field(min_length=1, max_length=4000)


def _author_error_status(exc: Exception) -> int:
    if isinstance(exc, BudgetExceededError):
        return 429
    if isinstance(exc, NoApiKeyError):
        return 400
    return 502  # GenerationError


async def _backtest_with_autofix(
    session: AsyncSession,
    *,
    user_id: int,
    result: GenerationResult,
    bar_cache: Any,
    indicator_computer: Any,
) -> tuple[GenerationResult, BacktestOutcome, bool]:
    """Backtest the result; on a HARD failure (syntax/runtime — not no_trades),
    call DEBUG_SYSTEM once and re-backtest. Returns (result, outcome, auto_fixed)."""
    outcome = await backtest_generated_code(
        code=result.code, bar_cache=bar_cache, indicator_computer=indicator_computer
    )
    if outcome.status not in ("syntax_error", "runtime_error"):
        return result, outcome, False
    try:
        fixed = await debug_strategy(
            session, user_id=user_id, prior_code=result.code, error=outcome.error or ""
        )
    except AuthoringError:
        return result, outcome, False  # debug unavailable (budget/key) → keep original
    fixed_outcome = await backtest_generated_code(
        code=fixed.code, bar_cache=bar_cache, indicator_computer=indicator_computer
    )
    return fixed, fixed_outcome, True


def _author_response(
    result: GenerationResult, outcome: BacktestOutcome, auto_fixed: bool
) -> dict[str, Any]:
    return {
        "code": result.code,
        "assumptions": result.assumptions,
        "explanation": result.explanation,
        "cost_usd": float(result.cost_usd),
        "prompt_version": result.prompt_version,
        "model": result.model,
        "auto_fixed": auto_fixed,
        "backtest": {
            "status": outcome.status,
            "metrics": outcome.metrics,
            "trade_count": outcome.trade_count,
            "error": outcome.error,
        },
    }


@router.get("/strategies/author/budget", response_model=dict)
async def get_author_budget(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """The user's daily authoring budget headroom (P7 §8) — the Author page header
    shows spent/cap so the trader sees how close they are before the 429."""
    b = await authoring_budget(session, user_id=current_user.id)
    return {k: float(v) for k, v in b.items()}


@router.post("/strategies/author", response_model=dict)
async def author_strategy(
    body: AuthorRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Generate a strategy from a description, then backtest it (Direction Decision
    2). On a hard backtest failure, auto-debug once. Generate-and-return; the
    trader saves it via the §4 flow."""
    try:
        result = await generate_strategy(
            session, user_id=current_user.id, description=body.description
        )
    except (BudgetExceededError, NoApiKeyError, GenerationError) as exc:
        raise HTTPException(status_code=_author_error_status(exc), detail=str(exc)) from exc

    result, outcome, auto_fixed = await _backtest_with_autofix(
        session, user_id=current_user.id, result=result,
        bar_cache=getattr(request.app.state, "bar_cache", None),
        indicator_computer=getattr(request.app.state, "indicator_computer", None),
    )
    return _author_response(result, outcome, auto_fixed)


@router.post("/strategies/author/refine", response_model=dict)
async def refine_strategy_endpoint(
    body: RefineRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Revise an existing strategy from a change request (P7b §6), then backtest +
    auto-debug. Stateless — the client sends the prior code each turn."""
    try:
        result = await refine_strategy(
            session, user_id=current_user.id,
            prior_code=body.prior_code, request=body.request,
        )
    except (BudgetExceededError, NoApiKeyError, GenerationError) as exc:
        raise HTTPException(status_code=_author_error_status(exc), detail=str(exc)) from exc

    result, outcome, auto_fixed = await _backtest_with_autofix(
        session, user_id=current_user.id, result=result,
        bar_cache=getattr(request.app.state, "bar_cache", None),
        indicator_computer=getattr(request.app.state, "indicator_computer", None),
    )
    return _author_response(result, outcome, auto_fixed)


class RevisionInput(BaseModel):
    """One turn of the authoring conversation (client-held, sent on save)."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(default=REVISION_GENERATION, max_length=16)
    user_message: str = Field(default="", max_length=8000)
    assumptions: list[str] = Field(default_factory=list)
    explanation: str = Field(default="", max_length=8000)
    code: str = Field(min_length=1, max_length=40000)
    backtest: dict[str, Any] | None = None
    cost_usd: float | None = None


class SaveAuthoredRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=40000)
    name: str = Field(min_length=1, max_length=128)
    # P7 §5: the authoring conversation (generation + any P7b refinements). Persisted
    # read-only as the saved strategy's history. Empty → a single generation turn
    # from the saved code is recorded so every authored strategy has its history.
    history: list[RevisionInput] = Field(default_factory=list, max_length=100)


@router.post("/strategies/author/save", response_model=dict)
async def save_authored_strategy(
    body: SaveAuthoredRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Persist an AI-generated strategy: re-validate (safety), write the .py,
    validate via the loader, and register it (status IDLE, authoring_method
    nl_generation). The trader saves what they reviewed; the standard
    backtest → paper → activation lifecycle applies (Decision 4)."""
    # 1. Safety — a separate trust boundary from generation.
    try:
        validate_generated_code(body.code)
    except SyntaxError as exc:
        raise HTTPException(status_code=400, detail=f"code has a syntax error: {exc}") from exc
    except UnsafeCodeError as exc:
        raise HTTPException(status_code=400, detail=f"unsafe code: {exc}") from exc

    slug = _slugify(body.name)
    if not slug:
        raise HTTPException(status_code=400, detail="name must contain alphanumerics")
    root = _strategies_root()
    rel = f"{slug}.py"
    path = root / rel
    if path.exists():
        raise HTTPException(
            status_code=409, detail="a strategy file by that name already exists"
        )

    root.mkdir(parents=True, exist_ok=True)
    path.write_text(body.code, encoding="utf-8")
    try:
        try:
            cls = StrategyLoader(root).load(rel)
        except StrategyLoadError as exc:
            raise HTTPException(status_code=400, detail=f"strategy file invalid: {exc}") from exc

        now = datetime.now(UTC)
        row = StrategyRow(
            user_id=current_user.id,
            name=body.name,
            version=str(cls.version),
            type=StrategyType.PYTHON,
            status=StrategyStatus.IDLE,
            code_path=rel,
            params_json=dict(cls.default_params or {}),
            symbols_json=list(cls.symbols or []),
            schedule=cls.schedule,
            authoring_method="nl_generation",
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        await session.flush()

        # P7 §5: persist the authoring conversation, read-only, linked to the
        # strategy. Empty history → one generation turn from the saved code.
        turns = body.history or [RevisionInput(code=body.code)]
        for seq, turn in enumerate(turns):
            session.add(
                StrategyRevision(
                    strategy_id=row.id,
                    seq=seq,
                    kind=turn.kind,
                    user_message=turn.user_message,
                    assumptions_json=list(turn.assumptions),
                    explanation=turn.explanation,
                    code=turn.code,
                    backtest_json=turn.backtest,
                    cost_usd=Decimal(str(turn.cost_usd)) if turn.cost_usd is not None else None,
                    created_at=now,
                )
            )

        AuditLogger.write(
            session,
            actor_type=AuditActorType.USER,
            actor_id=str(current_user.id),
            action=AuditAction.STRATEGY_REGISTERED,
            target_type="strategy",
            target_id=row.id,
            payload={"name": body.name, "authoring_method": "nl_generation", "code_path": rel},
            user_id=current_user.id,
        )
        await session.commit()
    except Exception:
        # No orphan .py if anything after the write failed.
        path.unlink(missing_ok=True)
        raise

    return {
        "id": row.id,
        "name": row.name,
        "status": row.status.value,
        "code_path": row.code_path,
        "authoring_method": row.authoring_method,
    }


@router.get("/strategies/{strategy_id}/authoring-history", response_model=dict)
async def get_authoring_history(
    strategy_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """The read-only AI-authoring conversation for a strategy (P7 §5). Empty for
    manually-authored strategies. §6's refinement chat renders this."""
    strategy = await session.get(StrategyRow, strategy_id)
    if strategy is None or strategy.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")

    rows = (
        await session.execute(
            select(StrategyRevision)
            .where(StrategyRevision.strategy_id == strategy_id)
            .order_by(StrategyRevision.seq.asc())
        )
    ).scalars().all()
    return {
        "strategy_id": strategy_id,
        "authoring_method": strategy.authoring_method,
        "out_of_sync": await _is_out_of_sync(session, strategy),
        "revisions": [
            {
                "seq": r.seq,
                "kind": r.kind,
                "user_message": r.user_message,
                "assumptions": r.assumptions_json,
                "explanation": r.explanation,
                "code": r.code,
                "backtest": r.backtest_json,
                "cost_usd": float(r.cost_usd) if r.cost_usd is not None else None,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
    }


async def _is_out_of_sync(session: AsyncSession, strategy: StrategyRow) -> bool:
    """True if the on-disk code has diverged from the last authoring revision
    (P7 §7, Decision 5). Conservative: any ambiguity → False (never cry wolf)."""
    if strategy.authoring_method == "manual" or not strategy.code_path:
        return False
    last = (
        await session.execute(
            select(StrategyRevision)
            .where(StrategyRevision.strategy_id == strategy.id)
            .order_by(StrategyRevision.seq.desc())
            .limit(1)
        )
    ).scalars().first()
    if last is None:
        return False
    path = _strategies_root() / strategy.code_path
    if not path.exists():
        return False
    try:
        on_disk = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return on_disk.strip() != (last.code or "").strip()


@router.get("/strategies/{strategy_id}/authoring-status", response_model=dict)
async def get_authoring_status(
    strategy_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Lightweight authoring status for the strategy detail page (P7 §7):
    authoring method, revision count, and whether the on-disk code was manually
    edited since it was AI-authored."""
    strategy = await session.get(StrategyRow, strategy_id)
    if strategy is None or strategy.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    count = (
        await session.execute(
            select(func.count())
            .select_from(StrategyRevision)
            .where(StrategyRevision.strategy_id == strategy_id)
        )
    ).scalar_one()
    return {
        "strategy_id": strategy_id,
        "authoring_method": strategy.authoring_method,
        "revision_count": int(count),
        "out_of_sync": await _is_out_of_sync(session, strategy),
    }
