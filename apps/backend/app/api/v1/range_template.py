"""``POST /api/v1/range-template/apply`` — adopt the range-trading template (P8 §7).

Creates an IDLE strategy that references the committed
``templates/range_trader.py`` with params prefilled from the symbol's Range
Insight (§5), tagged ``authoring_method="template"`` (the value P7 §8 reserved).
Saved IDLE into the standard backtest → paper → activation lifecycle (Decision 4).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.range_template import (
    ApplyRangeTemplateRequest,
    ApplyRangeTemplateResponse,
)
from app.audit.logger import AuditAction, AuditActorType, AuditLogger
from app.auth.stub import CurrentUser, get_current_user
from app.db.enums import StrategyStatus, StrategyType
from app.db.models.strategy import Strategy as StrategyRow
from app.db.session import get_session
from app.services.range_insight import STATUS_OK, RangeInsight, compute_range_insight
from app.strategies.loader import StrategyLoader, StrategyLoadError

router = APIRouter(prefix="/range-template", tags=["range-template"])

CODE_PATH = "templates/range_trader.py"
STOP_ATR_MULT = 1.5


def _strategies_root() -> Path:
    return Path("strategies_user")


def _range_trader_params(
    defaults: dict[str, Any], insight: RangeInsight | None
) -> tuple[dict[str, Any], bool]:
    """Prefill the template's level params from Range Insight when it's usable;
    otherwise keep the static defaults (the strategy stays inert until edited)."""
    params = dict(defaults)
    if (
        insight is not None
        and insight.status == STATUS_OK
        and insight.low_band is not None
        and insight.high_band is not None
        and insight.support is not None
        and insight.atr20 is not None
    ):
        params["entry_price"] = round(insight.low_band.high, 2)
        params["exit_price"] = round(insight.high_band.low, 2)
        params["stop_price"] = round(
            max(0.0, insight.support - STOP_ATR_MULT * insight.atr20), 2
        )
        # Per-symbol ATR normalizer for the ATR-scaled support zone (entry_zone_atr_mult).
        # Inert (zone off) until the trader sets a multiplier; prefilling it is harmless.
        if insight.atr20_pct is not None:
            params["atr20_pct"] = round(insight.atr20_pct, 4)
        return params, True
    return params, False


@router.post("/apply", response_model=ApplyRangeTemplateResponse)
async def apply_range_template(
    body: ApplyRangeTemplateRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ApplyRangeTemplateResponse:
    symbol = body.symbol.upper()

    bar_cache = getattr(request.app.state, "bar_cache", None)
    insight: RangeInsight | None = None
    if bar_cache is not None:
        insight = await compute_range_insight(
            symbol, bar_cache=bar_cache, now=datetime.now(UTC)
        )

    try:
        cls = StrategyLoader(_strategies_root()).load(CODE_PATH)
    except StrategyLoadError as exc:
        raise HTTPException(
            status_code=500, detail=f"range template unavailable: {exc}"
        ) from exc

    params, prefilled = _range_trader_params(dict(cls.default_params or {}), insight)
    name = (body.name or f"Range Trader {symbol}").strip()

    now = datetime.now(UTC)
    row = StrategyRow(
        user_id=user.id,
        name=name,
        version=str(cls.version),
        type=StrategyType.PYTHON,
        status=StrategyStatus.IDLE,
        code_path=CODE_PATH,
        params_json=params,
        symbols_json=[symbol],
        schedule=cls.schedule,
        authoring_method="template",
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    await session.flush()

    AuditLogger.write(
        session,
        actor_type=AuditActorType.USER,
        actor_id=str(user.id),
        action=AuditAction.STRATEGY_REGISTERED,
        target_type="strategy",
        target_id=row.id,
        user_id=user.id,
        payload={
            "name": name,
            "authoring_method": "template",
            "code_path": CODE_PATH,
            "symbol": symbol,
            "prefilled_from_range_insight": prefilled,
        },
    )
    await session.commit()
    await session.refresh(row)

    return ApplyRangeTemplateResponse(
        id=row.id,
        name=name,
        status=row.status.value,
        code_path=CODE_PATH,
        authoring_method=row.authoring_method,
        symbol=symbol,
        prefilled_from_range_insight=prefilled,
    )
