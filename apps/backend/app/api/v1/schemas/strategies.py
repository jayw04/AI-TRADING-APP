"""Pydantic schemas for ``/api/v1/strategies``, ``/api/v1/signals``, and
the strategy-scoped backtest endpoints.

All request bodies use ``extra='forbid'`` so a typo'd field returns 422
instead of silently being ignored (same paranoia ADR 0002 enforces at
the architectural level). Response models use ``from_attributes=True`` so
ORM rows serialize cleanly; ``_json`` columns are aliased to their
unsuffixed public names.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.enums import BacktestJobStatus, SignalType, StrategyStatus, StrategyType

# ---------- Strategy ----------


class StrategyCreateRequest(BaseModel):
    """Register a new strategy.

    The server validates ``code_path`` can be loaded by :class:`StrategyLoader`
    before persisting; an invalid path returns 400 with the loader error.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    version: str = Field(default="0.1.0", max_length=32)
    type: StrategyType = StrategyType.PYTHON
    code_path: str | None = Field(default=None, max_length=512)
    params: dict[str, Any] = Field(default_factory=dict)
    symbols: list[str] = Field(default_factory=list)
    schedule: str = Field(default="*/1 * * * *", max_length=64)
    risk_limits_id: int | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("symbols")
    @classmethod
    def _upper_symbols(cls, v: list[str]) -> list[str]:
        return [s.strip().upper() for s in v if s.strip()]


class StrategyUpdateRequest(BaseModel):
    """Update params / symbols / schedule / risk_limits_id / version.

    Only allowed when ``strategies.status == IDLE``. The endpoint returns
    409 otherwise.
    """

    model_config = ConfigDict(extra="forbid")

    params: dict[str, Any] | None = None
    symbols: list[str] | None = None
    schedule: str | None = Field(default=None, max_length=64)
    risk_limits_id: int | None = None
    version: str | None = Field(default=None, max_length=32)

    @field_validator("symbols")
    @classmethod
    def _upper_symbols(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        return [s.strip().upper() for s in v if s.strip()]


class StrategyResponse(BaseModel):
    # validation_alias (not `alias`) so JSON output uses the field name
    # (`params`, `symbols`) while ORM hydration still reads the
    # underlying ``*_json`` columns. FastAPI's default
    # ``response_model_by_alias`` would otherwise dump `params_json` etc.
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    name: str
    version: str
    type: StrategyType
    status: StrategyStatus
    code_path: str | None
    params: dict[str, Any] = Field(validation_alias="params_json")
    symbols: list[str] = Field(validation_alias="symbols_json")
    schedule: str
    risk_limits_id: int | None
    error_text: str | None
    created_at: datetime
    updated_at: datetime


class StrategyListResponse(BaseModel):
    items: list[StrategyResponse]
    count: int


# ---------- Strategy lifecycle action responses ----------


class StrategyActionResponse(BaseModel):
    strategy_id: int
    action: Literal["start", "stop"]
    new_status: StrategyStatus
    run_id: int | None = None  # populated on start; None on stop


# ---------- Strategy runs ----------


class StrategyRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    strategy_id: int
    started_at: datetime
    ended_at: datetime | None
    status: StrategyStatus
    error_text: str | None


class StrategyRunListResponse(BaseModel):
    items: list[StrategyRunResponse]
    count: int


# ---------- Signals ----------


class SignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    strategy_id: int | None
    symbol: str  # joined ticker (denormalized for read speed)
    type: SignalType
    payload: dict[str, Any] = Field(validation_alias="payload_json")
    received_at: datetime
    processed_at: datetime | None


class SignalListResponse(BaseModel):
    items: list[SignalResponse]
    count: int


# ---------- Backtests ----------


class BacktestRequest(BaseModel):
    """Body for ``POST /api/v1/strategies/{id}/backtest``.

    Symbols default to the strategy's registered ``symbols_json``. Params
    override the strategy's registered ``params``. Label is the
    human-friendly identifier surfaced in the UI list view (``"default"``,
    ``"tighter-rsi-25"``, etc).
    """

    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime
    label: str = Field(default="default", max_length=128)
    initial_equity: Decimal = Field(default=Decimal("100000"), gt=0)
    slippage_bps: float = Field(default=5.0, ge=0)
    commission_per_share: float = Field(default=0.0, ge=0)
    timeframe: str = Field(default="1Min", max_length=16)
    params: dict[str, Any] = Field(default_factory=dict)
    symbols: list[str] | None = None

    @field_validator("symbols")
    @classmethod
    def _upper_symbols(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        return [s.strip().upper() for s in v if s.strip()]


class BacktestResultResponse(BaseModel):
    """Full backtest result returned by the synchronous backtest endpoint.

    For listing, use :class:`BacktestResultSummary` (which omits the heavy
    equity_curve + trades fields).
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    strategy_id: int
    label: str
    params: dict[str, Any] = Field(validation_alias="params_json")
    metrics: dict[str, Any] = Field(validation_alias="metrics_json")
    equity_curve: list[dict[str, Any]] = Field(validation_alias="equity_curve_json")
    trades: list[dict[str, Any]] = Field(validation_alias="trades_json")
    range_start: datetime
    range_end: datetime
    created_at: datetime


class BacktestResultSummary(BaseModel):
    """Compact row for the backtest list view. Excludes equity_curve/trades."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    strategy_id: int
    label: str
    metrics: dict[str, Any] = Field(validation_alias="metrics_json")
    range_start: datetime
    range_end: datetime
    created_at: datetime


class BacktestListResponse(BaseModel):
    items: list[BacktestResultSummary]
    count: int


# ---------- Backtest jobs (P4 §2) ----------


class BacktestJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    strategy_id: int
    result_id: int | None
    status: BacktestJobStatus
    label: str
    percent_complete: float
    current_ts: str | None
    submitted_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    error_text: str | None


class BacktestJobListResponse(BaseModel):
    items: list[BacktestJobResponse]
    count: int


class BacktestJobSubmittedResponse(BaseModel):
    """``POST /strategies/{id}/backtest`` returns this with HTTP 202."""

    job_id: int
    strategy_id: int
    status: BacktestJobStatus
    submitted_at: datetime
