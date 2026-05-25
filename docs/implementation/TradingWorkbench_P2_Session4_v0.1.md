# P2 Session 4 — REST API, WebSocket Topics, Paper Deploy Lifecycle

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-22 |
| Phase | **P2**, **§6** |
| Predecessor | *TradingWorkbench_P2_Session3_v0.1.md* (tag `p2-session3-complete`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | (1) Pydantic schemas for strategies / signals / backtests. (2) Eleven REST endpoints under `/api/v1/strategies` and `/api/v1/signals`. (3) WebSocket topic publishing for `strategies`, `signals`, `backtests`. (4) Wire the Session 3 backtest harness behind a synchronous REST endpoint. (5) Extend `AuditAction` enum with strategy-specific actions (cleaning up Session 2's placeholder). (6) Extend `StrategyContext.log_signal` to publish on the bus after DB commit. (7) Extend `StrategyEngine` to publish `strategy.run_started` / `strategy.run_ended` distinct events. Single PR. |
| Estimated wall time | 4–5 hours |
| Stopping point | `git tag p2-session4-complete` |
| Out of scope | The frontend Strategies pages (Session 5). Async/background backtests with progress streaming (deferred — synchronous is fine for MVP). Multi-user authentication beyond the existing stub (P5+). |

---

## Session Goal

After this session:
- Eleven REST endpoints work end-to-end, each routed through the Pydantic schemas with `extra="forbid"`.
- A trader can register the reference RSI strategy via `POST /api/v1/strategies`, start it via `POST /api/v1/strategies/{id}/start` (transitions to PAPER, engine begins dispatching), stop it via `POST /api/v1/strategies/{id}/stop` (transitions back to IDLE).
- A backtest is runnable via `POST /api/v1/strategies/{id}/backtest`; result is persisted and returned in the response body.
- The audit log writes typed strategy events (no more `AuditAction.ORDER_CREATED` placeholder from Session 2).
- WebSocket subscribers to `strategies` receive `strategy.status_changed`, `strategy.run_started`, `strategy.run_ended`, `strategy.error` events as they happen. Subscribers to `signals` receive `signal.new` events when strategies emit signals. Subscribers to `backtests` receive `backtest.completed` events after each backtest.
- Every endpoint that creates state writes an `audit_log` row.

What does NOT happen this session:
- Frontend pages. Session 5.
- Async backtest with progress events. Synchronous-only per Checklist §6.2.
- A separate `/api/v1/backtests/{id}` top-level resource. Backtests are always accessed as a sub-resource of a strategy (`/api/v1/strategies/{id}/backtests/{backtest_id}`); the path structure stays hierarchical.

---

## Prerequisites Check

```bash
cd ~/code/AI-TRADING-APP
git status                                       # clean
git pull origin main
git describe --tags --abbrev=0                   # expect: p2-session3-complete

./scripts/dev.sh &
sleep 25

# Session 3 backtest harness reachable from REPL
docker compose exec backend uv run python -c "
from app.strategies import Backtester
from strategies_user.examples.rsi_meanreversion import RsiMeanReversion
print('ok:', Backtester.__name__, RsiMeanReversion.name)
"

# Strategy engine boots
docker compose logs backend | grep -E "strategy_engine_started"

docker compose down
```

- [ ] On `main`, clean tree, at `p2-session3-complete` or later.
- [ ] Strategy engine boots; reference strategy module importable.

Cut the branch:

```bash
git checkout -b feat/p2-strategies-rest-and-ws
```

---

## §4.1 — Extend `AuditAction` with Strategy Events

Session 2 used `AuditAction.ORDER_CREATED` as a placeholder for the strategy-registered audit row (P2 Session 2 Gotcha #6). Clean that up now.

Edit `apps/backend/app/audit/logger.py`. Add to the `AuditAction` enum (after the existing order lifecycle entries):

```python
    # Strategy lifecycle
    STRATEGY_REGISTERED = "strategy.registered"
    STRATEGY_UPDATED = "strategy.updated"
    STRATEGY_STARTED = "strategy.started"
    STRATEGY_STOPPED = "strategy.stopped"
    STRATEGY_ERROR = "strategy.error"
    STRATEGY_BACKTESTED = "strategy.backtested"
```

Now find where Session 2's `StrategyEngine.register` writes audit:

```python
await AuditLogger.write(
    session,
    actor_type=AuditActorType.USER,
    actor_id=str(row.user_id),
    action=AuditAction.ORDER_CREATED,   # placeholder; see Note in Gotcha #6
    target_type="strategy",
    ...
)
```

Replace `AuditAction.ORDER_CREATED` with `AuditAction.STRATEGY_STARTED` and update the comment to remove the placeholder note. Similarly, find any other strategy-related audit writes using the placeholder and switch them.

Find `_handle_user_exception` and add an audit write before the bus publish:

```python
async with self._session_factory() as session:
    row = await session.get(StrategyRow, strategy_id)
    if row is not None:
        await self._mark_error(session, row, f"{hook}: {exc}")
        await AuditLogger.write(
            session,
            actor_type=AuditActorType.SYSTEM,
            actor_id="strategy_engine",
            action=AuditAction.STRATEGY_ERROR,
            target_type="strategy",
            target_id=strategy_id,
            payload={"hook": hook, "error": str(exc)[:512]},
            user_id=row.user_id,
        )
        await session.commit()
```

And in `unregister`, before the final bus publish, add a stop audit row inside the existing session block:

```python
# (Inside the existing async with self._session_factory() as session: block,
# after the row.status transition)
if row is not None and row.user_id is not None:
    await AuditLogger.write(
        session,
        actor_type=AuditActorType.USER,
        actor_id=str(row.user_id),
        action=AuditAction.STRATEGY_STOPPED,
        target_type="strategy",
        target_id=strategy_id,
        payload={"reason": reason},
        user_id=row.user_id,
    )
await session.commit()
```

- [ ] Six new `AuditAction` values added.
- [ ] Session 2's placeholder reference updated to `STRATEGY_STARTED`.
- [ ] `_handle_user_exception` writes a `STRATEGY_ERROR` audit row.
- [ ] `unregister` writes a `STRATEGY_STOPPED` audit row.

---

## §4.2 — Pydantic Schemas

Create `apps/backend/app/api/v1/schemas/strategies.py`:

```python
"""Pydantic schemas for /api/v1/strategies, /api/v1/signals, and the
strategy-scoped backtest endpoints.

All request bodies use extra='forbid' so a typo'd field returns 422 rather
than silently being ignored. Response models use from_attributes so ORM rows
serialize cleanly.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.enums import SignalType, StrategyStatus, StrategyType


# ---------- Strategy ----------


class StrategyCreateRequest(BaseModel):
    """Register a new strategy. Server validates code_path can be loaded
    before persisting; an invalid path returns 400 with the loader error.
    """
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    version: str = Field(default="0.1.0", max_length=32)
    type: StrategyType = StrategyType.PYTHON
    code_path: Optional[str] = Field(default=None, max_length=512)
    params: dict[str, Any] = Field(default_factory=dict)
    symbols: list[str] = Field(default_factory=list)
    schedule: str = Field(default="*/1 * * * *", max_length=64)
    risk_limits_id: Optional[int] = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        return v.strip()

    @field_validator("symbols")
    @classmethod
    def _upper_symbols(cls, v: list[str]) -> list[str]:
        return [s.strip().upper() for s in v if s.strip()]


class StrategyUpdateRequest(BaseModel):
    """Update params / symbols / schedule / risk_limits_id.

    Only allowed when strategies.status == IDLE. The endpoint returns 409
    otherwise.
    """
    model_config = ConfigDict(extra="forbid")

    params: Optional[dict[str, Any]] = None
    symbols: Optional[list[str]] = None
    schedule: Optional[str] = Field(default=None, max_length=64)
    risk_limits_id: Optional[int] = None
    version: Optional[str] = Field(default=None, max_length=32)

    @field_validator("symbols")
    @classmethod
    def _upper_symbols(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return None
        return [s.strip().upper() for s in v if s.strip()]


class StrategyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    version: str
    type: StrategyType
    status: StrategyStatus
    code_path: Optional[str]
    params: dict[str, Any] = Field(alias="params_json")
    symbols: list[str] = Field(alias="symbols_json")
    schedule: str
    risk_limits_id: Optional[int]
    error_text: Optional[str]
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
    run_id: Optional[int] = None         # populated on start; None on stop


# ---------- Strategy runs ----------


class StrategyRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_id: int
    started_at: datetime
    ended_at: Optional[datetime]
    status: StrategyStatus
    error_text: Optional[str]


class StrategyRunListResponse(BaseModel):
    items: list[StrategyRunResponse]
    count: int


# ---------- Signals ----------


class SignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_id: Optional[int]
    symbol: str                    # joined ticker (denormalized for read speed)
    type: SignalType
    payload: dict[str, Any] = Field(alias="payload_json")
    received_at: datetime
    processed_at: Optional[datetime]


class SignalListResponse(BaseModel):
    items: list[SignalResponse]
    count: int


# ---------- Backtests ----------


class BacktestRequest(BaseModel):
    """Body for POST /api/v1/strategies/{id}/backtest.

    Symbols default to the strategy's registered symbols_json. Params override
    the strategy's registered params. Label is the human-friendly identifier
    surfaced in the UI list view ("default", "tighter-rsi-25", etc).
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
    symbols: Optional[list[str]] = None

    @field_validator("symbols")
    @classmethod
    def _upper_symbols(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return None
        return [s.strip().upper() for s in v if s.strip()]


class BacktestResultResponse(BaseModel):
    """Full backtest result returned by the synchronous backtest endpoint.

    For listing, use BacktestResultSummary (no equity_curve_json / trades_json
    inline; those are heavy fields).
    """
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_id: int
    label: str
    params: dict[str, Any] = Field(alias="params_json")
    metrics: dict[str, Any] = Field(alias="metrics_json")
    equity_curve: list[dict[str, Any]] = Field(alias="equity_curve_json")
    trades: list[dict[str, Any]] = Field(alias="trades_json")
    range_start: datetime
    range_end: datetime
    created_at: datetime


class BacktestResultSummary(BaseModel):
    """Compact row for the backtest list view. Excludes equity_curve/trades."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_id: int
    label: str
    metrics: dict[str, Any] = Field(alias="metrics_json")
    range_start: datetime
    range_end: datetime
    created_at: datetime


class BacktestListResponse(BaseModel):
    items: list[BacktestResultSummary]
    count: int
```

- [ ] Schema file created.
- [ ] All Pydantic models use `extra="forbid"` on requests and `from_attributes=True` on responses.

---

## §4.3 — Extend `StrategyContext.log_signal` to Publish on Bus

Session 2's `StrategyContext.log_signal` writes a `Signal` row to the DB but doesn't publish to the event bus, so the WS layer can't see it. Fix that.

Edit `apps/backend/app/strategies/context.py`. The constructor currently takes `submit_order_fn`; add a bus parameter:

```python
# In __init__ signature:
def __init__(
    self,
    *,
    strategy_id: int,
    user_id: int,
    account_id: int,
    symbols: list[str],
    session_factory: async_sessionmaker[AsyncSession],
    bar_cache: Any,
    indicator_computer: Any,
    submit_order_fn: OrderRouterCallable,
    bus: Any = None,                              # NEW: optional event bus
) -> None:
    ...
    self._bus = bus
```

> The bus is optional so the existing `BacktestContext` (which doesn't subclass `StrategyContext` but mirrors its surface) doesn't need updating, and unit tests that construct `StrategyContext` directly without a bus still work.

Then extend `log_signal` to publish:

```python
async def log_signal(
    self,
    symbol: str,
    type_: SignalType,
    payload: Optional[dict] = None,
) -> int:
    """Persist a signal row attributed to this strategy and publish on the bus."""
    symbol = symbol.upper()
    if symbol not in {s.upper() for s in self.symbols}:
        logger.warning("strategy_logged_unauthorized_signal",
                       strategy_id=self.strategy_id, symbol=symbol)
    async with self._session_factory() as session:
        sym = (await session.execute(
            select(Symbol).where(Symbol.ticker == symbol)
        )).scalars().first()
        if sym is None:
            logger.warning("strategy_signal_unknown_symbol", symbol=symbol)
            return 0
        sig = Signal(
            user_id=self.user_id,
            strategy_id=self.strategy_id,
            symbol_id=sym.id,
            type=type_,
            payload_json=payload or {},
            received_at=datetime.now(timezone.utc),
        )
        session.add(sig)
        await session.commit()
        await session.refresh(sig)
        signal_id = sig.id

    # Publish AFTER the commit so any subscriber that reads the DB sees the row.
    if self._bus is not None:
        try:
            await self._bus.publish("signal.new", {
                "signal_id": signal_id,
                "strategy_id": self.strategy_id,
                "symbol": symbol,
                "type": type_.value,
                "payload": payload or {},
                "received_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            logger.exception("signal_publish_failed", signal_id=signal_id)
    return signal_id
```

Finally update the engine's context construction in `apps/backend/app/strategies/engine.py` to pass the bus. Find the `ctx = StrategyContext(...)` call in `register()` and add:

```python
ctx = StrategyContext(
    strategy_id=row.id,
    user_id=row.user_id,
    account_id=account.id,
    symbols=symbols,
    session_factory=self._session_factory,
    bar_cache=self._bar_cache,
    indicator_computer=self._indicator_computer,
    submit_order_fn=self._order_router.submit,
    bus=self._bus,                                 # NEW
)
```

- [ ] `StrategyContext.__init__` accepts `bus`.
- [ ] `log_signal` publishes `signal.new` after DB commit.
- [ ] Engine passes its bus into each new context.

---

## §4.4 — Extend `StrategyEngine` with Distinct Run-Lifecycle Events

Session 2 publishes `strategy.status_changed` on both register and unregister. For richer UI affordances, also publish `strategy.run_started` and `strategy.run_ended` as distinct events.

Edit `apps/backend/app/strategies/engine.py`. In `register()`, after the existing `strategy.status_changed` publish:

```python
# Existing:
await self._bus.publish("strategy.status_changed", {
    "strategy_id": strategy_id, "status": StrategyStatus.PAPER.value,
})

# NEW: also publish run_started with run_id and started_at
await self._bus.publish("strategy.run_started", {
    "strategy_id": strategy_id,
    "run_id": run_id,
    "started_at": datetime.now(timezone.utc).isoformat(),
    "symbols": symbols,
})
```

In `unregister()`, before the existing `strategy.status_changed` publish, fetch the run we just closed and add the run_ended publish:

```python
# Inside the existing session block in unregister, after the run.ended_at
# assignment, capture for the bus payload:
closed_run_id = run.id if run else None
closed_run_started = run.started_at if run else None
closed_run_ended = run.ended_at if run else None

# Then after session.commit():
if closed_run_id is not None:
    duration_seconds = None
    if closed_run_started and closed_run_ended:
        duration_seconds = int((closed_run_ended - closed_run_started).total_seconds())
    await self._bus.publish("strategy.run_ended", {
        "strategy_id": strategy_id,
        "run_id": closed_run_id,
        "ended_at": closed_run_ended.isoformat() if closed_run_ended else None,
        "duration_seconds": duration_seconds,
        "reason": reason,
    })

# Existing:
await self._bus.publish("strategy.status_changed", {
    "strategy_id": strategy_id, "status": StrategyStatus.IDLE.value,
    "reason": reason,
})
```

- [ ] `register` publishes `strategy.run_started`.
- [ ] `unregister` publishes `strategy.run_ended`.
- [ ] `strategy.status_changed` still publishes (it's now redundant on register/unregister but useful for UI listening for any state change — keep it).

---

## §4.5 — REST: Strategies Endpoints

The big one. Eleven endpoints in one file.

Create `apps/backend/app/api/v1/strategies.py`:

```python
"""REST endpoints for /api/v1/strategies and the per-strategy sub-resources.

Lifecycle:
  POST   /strategies                       Register a new strategy
  GET    /strategies                       List
  GET    /strategies/{id}                  Detail
  PUT    /strategies/{id}                  Update (only when status=IDLE)
  POST   /strategies/{id}/start            Engine.register; status -> PAPER
  POST   /strategies/{id}/stop             Engine.unregister; status -> IDLE
  POST   /strategies/{id}/backtest         Sync backtest; persists + returns result
  GET    /strategies/{id}/runs             Strategy run history
  GET    /strategies/{id}/signals          Signals emitted by this strategy
  GET    /strategies/{id}/backtests        Past backtest results (summary list)
  GET    /strategies/{id}/backtests/{bid}  One backtest result (full)
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.strategies import (
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
from app.auth.stub import get_current_user
from app.db.enums import ACTIVE_STRATEGY_STATUSES, StrategyStatus, StrategyType
from app.db.models.backtest_result import BacktestResult
from app.db.models.signal import Signal
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.strategy_run import StrategyRun
from app.db.models.symbol import Symbol
from app.db.session import get_session
from app.strategies import (
    Backtester,
    BacktestConfig,
    StrategyLoader,
    StrategyLoadError,
    persist_backtest_result,
)

router = APIRouter(prefix="/strategies", tags=["strategies"])


# ---------- helpers ----------


def _get_engine(request: Request):
    engine = getattr(request.app.state, "strategy_engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="Strategy engine not initialized")
    return engine


def _get_bar_cache(request: Request):
    bc = getattr(request.app.state, "bar_cache", None)
    if bc is None:
        raise HTTPException(status_code=503, detail="Bar cache not initialized")
    return bc


def _get_indicator_computer(request: Request):
    ic = getattr(request.app.state, "indicator_computer", None)
    if ic is None:
        raise HTTPException(status_code=503, detail="Indicator computer not initialized")
    return ic


def _get_strategies_root() -> Path:
    return Path("strategies_user")


def _get_bus(request: Request):
    return getattr(request.app.state, "event_bus", None)


async def _row_to_response(row: StrategyRow) -> StrategyResponse:
    return StrategyResponse.model_validate(row, from_attributes=True)


async def _signal_to_response(session: AsyncSession, signal: Signal) -> SignalResponse:
    sym = await session.get(Symbol, signal.symbol_id)
    return SignalResponse(
        id=signal.id,
        strategy_id=signal.strategy_id,
        symbol=sym.ticker if sym else "?",
        type=signal.type,
        payload_json=signal.payload_json,
        received_at=signal.received_at,
        processed_at=signal.processed_at,
    )


# ---------- POST /strategies ----------


@router.post("", response_model=StrategyResponse)
async def create_strategy(
    body: StrategyCreateRequest,
    request: Request,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    # Reject PINE/AGENT in P2 — Sessions 4 and 5 only handle PYTHON.
    if body.type != StrategyType.PYTHON:
        raise HTTPException(
            status_code=400,
            detail=f"Strategy type {body.type.value} is reserved but not supported until later phases",
        )
    if not body.code_path:
        raise HTTPException(status_code=400, detail="code_path is required for python strategies")

    # Validate the loader can resolve the code_path BEFORE persisting.
    # This catches typos and path traversal at create time, not at start time.
    try:
        loader = StrategyLoader(_get_strategies_root())
        cls = loader.load(body.code_path)
    except StrategyLoadError as exc:
        raise HTTPException(status_code=400, detail=f"Strategy file invalid: {exc}")

    # If symbols list empty, fall back to the strategy class's declared symbols.
    symbols = body.symbols or list(cls.symbols)
    now = datetime.now(timezone.utc)
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

    await AuditLogger.write(
        session,
        actor_type=AuditActorType.USER,
        actor_id=str(current_user.id),
        action=AuditAction.STRATEGY_REGISTERED,
        target_type="strategy",
        target_id=row.id,
        payload={
            "name": body.name, "version": body.version,
            "code_path": body.code_path, "symbols": symbols,
        },
        user_id=current_user.id,
    )
    await session.commit()
    await session.refresh(row)
    return await _row_to_response(row)


# ---------- GET /strategies ----------


@router.get("", response_model=StrategyListResponse)
async def list_strategies(
    status: Optional[StrategyStatus] = Query(default=None),
    type_: Optional[StrategyType] = Query(default=None, alias="type"),
    limit: int = Query(default=100, ge=1, le=500),
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(StrategyRow).where(StrategyRow.user_id == current_user.id)
    if status is not None:
        stmt = stmt.where(StrategyRow.status == status)
    if type_ is not None:
        stmt = stmt.where(StrategyRow.type == type_)
    stmt = stmt.order_by(StrategyRow.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    items = [await _row_to_response(r) for r in rows]
    return StrategyListResponse(items=items, count=len(items))


# ---------- GET /strategies/{id} ----------


@router.get("/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: int,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(StrategyRow, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    return await _row_to_response(row)


# ---------- PUT /strategies/{id} ----------


@router.put("/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: int,
    body: StrategyUpdateRequest,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(StrategyRow, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if row.status != StrategyStatus.IDLE:
        raise HTTPException(
            status_code=409,
            detail=f"Strategy is in status {row.status.value}; stop it before updating.",
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

    row.updated_at = datetime.now(timezone.utc)

    await AuditLogger.write(
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
    return await _row_to_response(row)


# ---------- POST /strategies/{id}/start ----------


@router.post("/{strategy_id}/start", response_model=StrategyActionResponse)
async def start_strategy(
    strategy_id: int,
    request: Request,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(StrategyRow, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if row.status in ACTIVE_STRATEGY_STATUSES:
        # Idempotent — return current state
        return StrategyActionResponse(
            strategy_id=strategy_id, action="start", new_status=row.status, run_id=None
        )
    if row.status == StrategyStatus.ERROR:
        # Allow restart from ERROR; engine.register clears error_text.
        pass

    engine = _get_engine(request)
    try:
        running = await engine.register(strategy_id)
    except StrategyLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Engine register failed: {exc}")

    # Re-fetch row to get the updated status from engine.register
    row = await session.get(StrategyRow, strategy_id)
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
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(StrategyRow, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")

    engine = _get_engine(request)
    await engine.unregister(strategy_id, reason="user_stop")

    row = await session.get(StrategyRow, strategy_id)
    return StrategyActionResponse(
        strategy_id=strategy_id, action="stop",
        new_status=row.status, run_id=None,
    )


# ---------- POST /strategies/{id}/backtest ----------


@router.post("/{strategy_id}/backtest", response_model=BacktestResultResponse)
async def run_backtest(
    strategy_id: int,
    body: BacktestRequest,
    request: Request,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Synchronous backtest. Runs in the request handler; blocks until done.

    A 60-day, 1-minute, single-symbol backtest typically completes in 2–10s
    on a developer machine. For longer ranges you may need to increase the
    HTTP gateway timeout. See Gotcha #2 in the session doc for details.
    """
    row = await session.get(StrategyRow, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if row.type != StrategyType.PYTHON:
        raise HTTPException(status_code=400, detail="Only python strategies are backtestable in P2")

    # Range sanity
    if body.end <= body.start:
        raise HTTPException(status_code=400, detail="end must be after start")
    # Refuse absurdly long ranges; the endpoint is synchronous.
    if (body.end - body.start).days > 365:
        raise HTTPException(
            status_code=400,
            detail="Backtest range exceeds 1 year. Run shorter ranges or use the CLI helper.",
        )

    # Load the strategy class
    try:
        loader = StrategyLoader(_get_strategies_root())
        strategy_class = loader.load(row.code_path or "")
    except StrategyLoadError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Resolve symbols + params
    symbols = body.symbols or list(row.symbols_json) or list(strategy_class.symbols)
    if not symbols:
        raise HTTPException(status_code=400, detail="No symbols to backtest")
    merged_params = {**(row.params_json or {}), **body.params}

    config = BacktestConfig(
        start=body.start,
        end=body.end,
        initial_equity=body.initial_equity,
        slippage_bps=body.slippage_bps,
        commission_per_share=body.commission_per_share,
        timeframe=body.timeframe,
        params=merged_params,
    )

    bar_cache = _get_bar_cache(request)
    indicator_computer = _get_indicator_computer(request)
    harness = Backtester(bar_cache=bar_cache, indicator_computer=indicator_computer)

    try:
        metrics, trades, equity = await harness.run(strategy_class, symbols, config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {exc}")

    # Persist + audit + publish
    result = await persist_backtest_result(
        session,
        strategy_id=strategy_id,
        config=config,
        metrics=metrics,
        trades=trades,
        equity=equity,
        label=body.label,
    )
    async with session.begin_nested():
        await AuditLogger.write(
            session,
            actor_type=AuditActorType.USER,
            actor_id=str(current_user.id),
            action=AuditAction.STRATEGY_BACKTESTED,
            target_type="backtest_result",
            target_id=result.id,
            payload={
                "strategy_id": strategy_id,
                "range_start": body.start.isoformat(),
                "range_end": body.end.isoformat(),
                "trade_count": metrics.trade_count,
                "total_return": metrics.total_return,
            },
            user_id=current_user.id,
        )
    await session.commit()

    bus = _get_bus(request)
    if bus is not None:
        try:
            await bus.publish("backtest.completed", {
                "backtest_id": result.id,
                "strategy_id": strategy_id,
                "label": body.label,
                "metrics": result.metrics_json,
            })
        except Exception:
            pass

    return BacktestResultResponse.model_validate(result, from_attributes=True)


# ---------- GET /strategies/{id}/runs ----------


@router.get("/{strategy_id}/runs", response_model=StrategyRunListResponse)
async def list_runs(
    strategy_id: int,
    limit: int = Query(default=50, ge=1, le=500),
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(StrategyRow, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    rows = (await session.execute(
        select(StrategyRun)
        .where(StrategyRun.strategy_id == strategy_id)
        .order_by(StrategyRun.started_at.desc())
        .limit(limit)
    )).scalars().all()
    return StrategyRunListResponse(
        items=[StrategyRunResponse.model_validate(r, from_attributes=True) for r in rows],
        count=len(rows),
    )


# ---------- GET /strategies/{id}/signals ----------


@router.get("/{strategy_id}/signals", response_model=SignalListResponse)
async def list_strategy_signals(
    strategy_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(StrategyRow, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    signals = (await session.execute(
        select(Signal)
        .where(Signal.strategy_id == strategy_id)
        .order_by(Signal.received_at.desc())
        .limit(limit)
    )).scalars().all()
    items = [await _signal_to_response(session, s) for s in signals]
    return SignalListResponse(items=items, count=len(items))


# ---------- GET /strategies/{id}/backtests ----------


@router.get("/{strategy_id}/backtests", response_model=BacktestListResponse)
async def list_strategy_backtests(
    strategy_id: int,
    limit: int = Query(default=50, ge=1, le=500),
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(StrategyRow, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    results = (await session.execute(
        select(BacktestResult)
        .where(BacktestResult.strategy_id == strategy_id)
        .order_by(BacktestResult.created_at.desc())
        .limit(limit)
    )).scalars().all()
    return BacktestListResponse(
        items=[BacktestResultSummary.model_validate(r, from_attributes=True) for r in results],
        count=len(results),
    )


# ---------- GET /strategies/{id}/backtests/{backtest_id} ----------


@router.get("/{strategy_id}/backtests/{backtest_id}", response_model=BacktestResultResponse)
async def get_strategy_backtest(
    strategy_id: int,
    backtest_id: int,
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(StrategyRow, strategy_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    result = await session.get(BacktestResult, backtest_id)
    if result is None or result.strategy_id != strategy_id:
        raise HTTPException(status_code=404, detail="Backtest result not found")
    return BacktestResultResponse.model_validate(result, from_attributes=True)
```

- [ ] `strategies.py` router created with all eleven endpoints.

---

## §4.6 — REST: Signals Cross-Strategy Endpoint

Smaller file: one endpoint for the cross-strategy signals view.

Create `apps/backend/app/api/v1/signals.py`:

```python
"""REST endpoint for /api/v1/signals — cross-strategy signal view."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.strategies import SignalListResponse, SignalResponse
from app.auth.stub import get_current_user
from app.db.enums import SignalType
from app.db.models.signal import Signal
from app.db.models.symbol import Symbol
from app.db.session import get_session

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("", response_model=SignalListResponse)
async def list_signals(
    strategy_id: Optional[int] = Query(default=None),
    symbol: Optional[str] = Query(default=None),
    type_: Optional[SignalType] = Query(default=None, alias="type"),
    since: Optional[datetime] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    current_user=Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Signal).where(Signal.user_id == current_user.id)
    if strategy_id is not None:
        stmt = stmt.where(Signal.strategy_id == strategy_id)
    if symbol:
        sym = (await session.execute(
            select(Symbol).where(Symbol.ticker == symbol.upper())
        )).scalars().first()
        if sym is None:
            return SignalListResponse(items=[], count=0)
        stmt = stmt.where(Signal.symbol_id == sym.id)
    if type_ is not None:
        stmt = stmt.where(Signal.type == type_)
    if since is not None:
        stmt = stmt.where(Signal.received_at >= since)
    stmt = stmt.order_by(Signal.received_at.desc()).limit(limit)

    signals = (await session.execute(stmt)).scalars().all()
    # Join symbols once for the response
    symbol_ids = list({s.symbol_id for s in signals})
    symbols_by_id: dict[int, str] = {}
    if symbol_ids:
        sym_rows = (await session.execute(
            select(Symbol).where(Symbol.id.in_(symbol_ids))
        )).scalars().all()
        symbols_by_id = {s.id: s.ticker for s in sym_rows}

    items = [
        SignalResponse(
            id=s.id,
            strategy_id=s.strategy_id,
            symbol=symbols_by_id.get(s.symbol_id, "?"),
            type=s.type,
            payload_json=s.payload_json,
            received_at=s.received_at,
            processed_at=s.processed_at,
        )
        for s in signals
    ]
    return SignalListResponse(items=items, count=len(items))
```

- [ ] `signals.py` router created.

---

## §4.7 — Register the New Routers

Edit `apps/backend/app/main.py` to mount the new routers. Find the existing `app.include_router(...)` calls and add:

```python
from app.api.v1 import strategies as strategies_router
from app.api.v1 import signals as signals_router

# Inside create_app(), with the other routers:
app.include_router(strategies_router.router, prefix="/api/v1")
app.include_router(signals_router.router, prefix="/api/v1")
```

- [ ] Both routers mounted.

---

## §4.8 — Extend WS Gateway with New Bus → WS Topic Map

P1 Session 6 added a `bus_to_ws_map` dict in `apps/backend/app/ws/gateway.py`. Extend it for strategy / signal / backtest events.

Edit `apps/backend/app/ws/gateway.py`. Find the `bus_to_ws_map` dictionary and add:

```python
bus_to_ws_map = {
    # ... existing entries from P1 Session 6 ...
    "order.submitted": "orders",
    "order.rejected": "orders",
    "order.transition": "orders",
    "positions.snapshot": "positions",
    "account.snapshot": "system",
    "alpaca.trade_update": "fills",
    "alpaca.stream_status": "system",
    "system.symbols_synced": "system",
    "system.reconciliation_drift": "system",
    "system.heartbeat": "system",

    # NEW for P2 Session 4:
    "strategy.status_changed": "strategies",
    "strategy.run_started": "strategies",
    "strategy.run_ended": "strategies",
    "strategy.error": "strategies",
    "signal.new": "signals",
    "backtest.completed": "backtests",
}

PUBLISHED_TOPICS = {
    "orders", "fills", "positions", "system", "alerts",
    # NEW:
    "strategies", "signals", "backtests",
}
```

Also extend the replay buffer window config in `apps/backend/app/ws/replay.py`. Per Implementation Plan v0.2 §8 and P2 Checklist §6.3:

```python
REPLAY_WINDOWS_SECONDS = {
    # ... existing entries ...
    "orders": 3600,
    "fills": 3600,
    "positions": 600,
    "system": 0,
    "quote": 0,
    # NEW:
    "strategies": 3600,
    "signals": 3600,
    "backtests": 3600,
}
```

- [ ] `bus_to_ws_map` extended.
- [ ] `PUBLISHED_TOPICS` extended.
- [ ] `REPLAY_WINDOWS_SECONDS` extended.

---

## §4.9 — Tests

Three test files. Goal: prove each endpoint returns the right status code, schema validation works, and the full backtest-via-HTTP path produces a persisted result.

### 4.9.1 — Strategies endpoint tests

Create `apps/backend/tests/api/test_strategies_endpoint.py`:

```python
"""Smoke + behavior tests for /api/v1/strategies."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest
from httpx import AsyncClient

from app.db.enums import (
    OrderSide, OrderSourceType, RiskScopeType, StrategyStatus, StrategyType,
)
from app.db.models.account import Account
from app.db.models.risk_limits import RiskLimits
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(Account(id=1, user_id=1, broker="alpaca", mode="paper", label="Paper"))
        session.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ",
                           asset_class="us_equity", name="Apple", active=True))
        session.add(RiskLimits(
            user_id=1, scope_type=RiskScopeType.GLOBAL, scope_id=None,
            max_position_qty=Decimal("100"),
            max_position_notional=Decimal("25000"),
            max_gross_exposure=Decimal("100000"),
            max_daily_loss=Decimal("2000"),
            max_orders_per_minute=10,
            allow_short=False,
            created_at=_now(), updated_at=_now(),
        ))
        await session.commit()


@pytest.fixture
async def client(seeded, session_factory):
    from app.main import create_app
    app = create_app()
    # Mock strategy engine + bar cache + indicator computer on app.state
    app.state.strategy_engine = MagicMock()
    app.state.strategy_engine.register = AsyncMock()
    app.state.strategy_engine.unregister = AsyncMock()
    app.state.bar_cache = MagicMock()
    app.state.bar_cache.get_bars = AsyncMock(return_value=pd.DataFrame(columns=["t","o","h","l","c","v"]))
    app.state.indicator_computer = MagicMock()
    app.state.event_bus = MagicMock()
    app.state.event_bus.publish = AsyncMock()

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_create_rejects_path_traversal(client):
    resp = await client.post("/api/v1/strategies", json={
        "name": "evil",
        "code_path": "../../etc/passwd",
        "type": "python",
        "symbols": ["AAPL"],
    })
    assert resp.status_code == 400
    assert "escapes" in resp.json()["detail"].lower() or "invalid" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_rejects_extra_field(client):
    resp = await client.post("/api/v1/strategies", json={
        "name": "test",
        "code_path": "examples/rsi_meanreversion.py",
        "fnord": "extra-field",
    })
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_rejects_missing_file(client):
    resp = await client.post("/api/v1/strategies", json={
        "name": "missing",
        "code_path": "does/not/exist.py",
        "type": "python",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_succeeds_with_real_reference_strategy(client):
    """Uses the actual reference RSI strategy file as the create target."""
    resp = await client.post("/api/v1/strategies", json={
        "name": "rsi-test-1",
        "code_path": "examples/rsi_meanreversion.py",
        "type": "python",
        "symbols": ["AAPL"],
        "params": {"entry_threshold": 25.0},
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "idle"
    assert body["symbols"] == ["AAPL"]
    assert body["params"]["entry_threshold"] == 25.0


@pytest.mark.asyncio
async def test_create_rejects_pine_type(client):
    resp = await client.post("/api/v1/strategies", json={
        "name": "pine-later",
        "code_path": None,
        "type": "pine",
    })
    assert resp.status_code == 400
    assert "reserved" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_filters_by_status(client, session_factory):
    async with session_factory() as session:
        session.add(StrategyRow(
            user_id=1, name="active", version="0.1.0", type=StrategyType.PYTHON,
            status=StrategyStatus.PAPER, code_path="examples/rsi_meanreversion.py",
            params_json={}, symbols_json=["AAPL"], schedule="*/1 * * * *",
            risk_limits_id=None, created_at=_now(), updated_at=_now(),
        ))
        session.add(StrategyRow(
            user_id=1, name="idle", version="0.1.0", type=StrategyType.PYTHON,
            status=StrategyStatus.IDLE, code_path="examples/rsi_meanreversion.py",
            params_json={}, symbols_json=["AAPL"], schedule="*/1 * * * *",
            risk_limits_id=None, created_at=_now(), updated_at=_now(),
        ))
        await session.commit()

    resp = await client.get("/api/v1/strategies?status=paper")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["items"][0]["name"] == "active"


@pytest.mark.asyncio
async def test_update_rejects_when_active(client, session_factory):
    async with session_factory() as session:
        row = StrategyRow(
            user_id=1, name="busy", version="0.1.0", type=StrategyType.PYTHON,
            status=StrategyStatus.PAPER, code_path="examples/rsi_meanreversion.py",
            params_json={}, symbols_json=["AAPL"], schedule="*/1 * * * *",
            risk_limits_id=None, created_at=_now(), updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        sid = row.id

    resp = await client.put(f"/api/v1/strategies/{sid}", json={"params": {"entry_threshold": 20}})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_start_calls_engine_register(client, session_factory):
    async with session_factory() as session:
        row = StrategyRow(
            user_id=1, name="to-start", version="0.1.0", type=StrategyType.PYTHON,
            status=StrategyStatus.IDLE, code_path="examples/rsi_meanreversion.py",
            params_json={}, symbols_json=["AAPL"], schedule="*/1 * * * *",
            risk_limits_id=None, created_at=_now(), updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        sid = row.id

    # Stub register: returns a running fake with run_id 42, AND flips DB status
    async def fake_register(strategy_id):
        async with session_factory() as s:
            r = await s.get(StrategyRow, strategy_id)
            r.status = StrategyStatus.PAPER
            await s.commit()
        result = MagicMock()
        result.run_id = 42
        return result

    client._transport.app.state.strategy_engine.register = fake_register

    resp = await client.post(f"/api/v1/strategies/{sid}/start")
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "start"
    assert body["new_status"] == "paper"
    assert body["run_id"] == 42


@pytest.mark.asyncio
async def test_stop_calls_engine_unregister(client, session_factory):
    async with session_factory() as session:
        row = StrategyRow(
            user_id=1, name="to-stop", version="0.1.0", type=StrategyType.PYTHON,
            status=StrategyStatus.PAPER, code_path="examples/rsi_meanreversion.py",
            params_json={}, symbols_json=["AAPL"], schedule="*/1 * * * *",
            risk_limits_id=None, created_at=_now(), updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        sid = row.id

    async def fake_unregister(strategy_id, reason=None):
        async with session_factory() as s:
            r = await s.get(StrategyRow, strategy_id)
            r.status = StrategyStatus.IDLE
            await s.commit()

    client._transport.app.state.strategy_engine.unregister = fake_unregister

    resp = await client.post(f"/api/v1/strategies/{sid}/stop")
    assert resp.status_code == 200
    body = resp.json()
    assert body["new_status"] == "idle"
```

### 4.9.2 — Backtest endpoint integration test

Create `apps/backend/tests/api/test_backtest_endpoint.py`:

```python
"""End-to-end backtest via REST: posts to /backtest, gets back persisted result."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.enums import StrategyStatus, StrategyType
from app.db.models.account import Account
from app.db.models.backtest_result import BacktestResult
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.indicators import IndicatorComputer


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "bars"


def _now():
    return datetime.now(timezone.utc)


def _load_fixture_bars() -> pd.DataFrame:
    days = ["2025-11-03", "2025-11-04", "2025-11-05"]
    frames = []
    for d in days:
        path = FIXTURE_DIR / f"AAPL_{d}_1Min.parquet"
        if not path.exists():
            pytest.skip(f"Fixture not present: {path}")
        frames.append(pd.read_parquet(path))
    df = pd.concat(frames).reset_index(drop=True)
    df["t"] = pd.to_datetime(df["t"], utc=True)
    return df.sort_values("t").reset_index(drop=True)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(Account(id=1, user_id=1, broker="alpaca", mode="paper", label="Paper"))
        session.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ",
                           asset_class="us_equity", name="Apple", active=True))
        row = StrategyRow(
            user_id=1, name="rsi-bt", version="0.1.0",
            type=StrategyType.PYTHON, status=StrategyStatus.IDLE,
            code_path="examples/rsi_meanreversion.py",
            params_json={}, symbols_json=["AAPL"], schedule="*/1 * * * *",
            risk_limits_id=None, created_at=_now(), updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


@pytest.mark.asyncio
async def test_post_backtest_runs_and_persists(seeded, session_factory):
    from app.main import create_app
    sid = seeded
    app = create_app()

    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=_load_fixture_bars())
    app.state.bar_cache = bar_cache
    app.state.indicator_computer = IndicatorComputer()
    app.state.event_bus = MagicMock()
    app.state.event_bus.publish = AsyncMock()

    body = {
        "start": "2025-11-03T00:00:00+00:00",
        "end": "2025-11-06T00:00:00+00:00",
        "label": "smoke",
        "initial_equity": "100000",
        "slippage_bps": 5.0,
        "timeframe": "1Min",
    }
    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.post(f"/api/v1/strategies/{sid}/backtest", json=body)

    assert resp.status_code == 200, resp.text
    response_body = resp.json()
    assert response_body["strategy_id"] == sid
    assert response_body["label"] == "smoke"
    assert "trade_count" in response_body["metrics"]
    assert "total_return" in response_body["metrics"]

    # Persisted row exists
    async with session_factory() as session:
        rows = (await session.execute(
            select(BacktestResult).where(BacktestResult.strategy_id == sid)
        )).scalars().all()
        assert len(rows) == 1
        assert rows[0].label == "smoke"

    # backtest.completed published
    app.state.event_bus.publish.assert_called()
    topics = [c.args[0] for c in app.state.event_bus.publish.call_args_list]
    assert "backtest.completed" in topics


@pytest.mark.asyncio
async def test_backtest_rejects_long_range(seeded, session_factory):
    from app.main import create_app
    sid = seeded
    app = create_app()
    app.state.bar_cache = MagicMock()
    app.state.indicator_computer = MagicMock()
    app.state.event_bus = MagicMock()

    body = {
        "start": "2024-01-01T00:00:00+00:00",
        "end": "2026-01-01T00:00:00+00:00",
        "label": "too-long",
    }
    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.post(f"/api/v1/strategies/{sid}/backtest", json=body)
    assert resp.status_code == 400
    assert "exceeds 1 year" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_backtest_rejects_inverted_range(seeded):
    from app.main import create_app
    sid = seeded
    app = create_app()
    app.state.bar_cache = MagicMock()
    app.state.indicator_computer = MagicMock()
    app.state.event_bus = MagicMock()

    body = {
        "start": "2025-11-06T00:00:00+00:00",
        "end": "2025-11-03T00:00:00+00:00",
        "label": "backwards",
    }
    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.post(f"/api/v1/strategies/{sid}/backtest", json=body)
    assert resp.status_code == 400
```

### 4.9.3 — Signals endpoint test

Create `apps/backend/tests/api/test_signals_endpoint.py`:

```python
"""Tests for /api/v1/signals cross-strategy view."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.db.enums import RiskScopeType, SignalType, StrategyStatus, StrategyType
from app.db.models.account import Account
from app.db.models.risk_limits import RiskLimits
from app.db.models.signal import Signal
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
async def seeded_with_signals(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(Account(id=1, user_id=1, broker="alpaca", mode="paper", label="Paper"))
        session.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ",
                           asset_class="us_equity", name="Apple", active=True))
        session.add(Symbol(id=2, ticker="MSFT", exchange="NASDAQ",
                           asset_class="us_equity", name="Microsoft", active=True))
        s1 = StrategyRow(
            user_id=1, name="s1", version="0.1.0", type=StrategyType.PYTHON,
            status=StrategyStatus.IDLE, code_path="examples/rsi_meanreversion.py",
            params_json={}, symbols_json=["AAPL"], schedule="*/1 * * * *",
            risk_limits_id=None, created_at=_now(), updated_at=_now(),
        )
        session.add(s1)
        await session.commit()
        await session.refresh(s1)

        for t, sym_id, ts_offset in [
            (SignalType.ENTRY, 1, -300),
            (SignalType.EXIT, 1, -200),
            (SignalType.ENTRY, 2, -100),
            (SignalType.INFO, 1, -50),
        ]:
            session.add(Signal(
                user_id=1, strategy_id=s1.id, symbol_id=sym_id, type=t,
                payload_json={}, received_at=_now() + timedelta(seconds=ts_offset),
            ))
        await session.commit()


@pytest.fixture
async def client(seeded_with_signals):
    from app.main import create_app
    app = create_app()
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_list_all_signals(client):
    resp = await client.get("/api/v1/signals")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 4


@pytest.mark.asyncio
async def test_list_signals_filtered_by_symbol(client):
    resp = await client.get("/api/v1/signals?symbol=MSFT")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["items"][0]["symbol"] == "MSFT"


@pytest.mark.asyncio
async def test_list_signals_filtered_by_type(client):
    resp = await client.get("/api/v1/signals?type=entry")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert all(item["type"] == "entry" for item in body["items"])


@pytest.mark.asyncio
async def test_list_signals_unknown_symbol_returns_empty(client):
    resp = await client.get("/api/v1/signals?symbol=ZZZZ")
    assert resp.status_code == 200
    assert resp.json()["count"] == 0
```

### 4.9.4 — Run the suite

```bash
cd apps/backend
uv run pytest tests/api/test_strategies_endpoint.py \
              tests/api/test_backtest_endpoint.py \
              tests/api/test_signals_endpoint.py -v
uv run pytest -q
cd ../..
```

- [ ] All three new test files pass.
- [ ] Existing tests still green.

---

## §4.10 — Manual Smoke Against Alpaca Paper

```bash
./scripts/dev.sh &
sleep 30

# 1. Create the reference strategy via REST
curl -s -X POST http://127.0.0.1:8000/api/v1/strategies \
  -H "Content-Type: application/json" \
  -d '{
    "name": "rsi-mean-reversion",
    "code_path": "examples/rsi_meanreversion.py",
    "type": "python",
    "symbols": ["AAPL"],
    "params": {"entry_threshold": 30}
  }' | jq '{id, name, status, symbols}'

STRATEGY_ID=$(curl -s "http://127.0.0.1:8000/api/v1/strategies" | jq '.items[0].id')
echo "Strategy id: $STRATEGY_ID"

# 2. Run a 3-day backtest (uses cached AAPL bars from Session 1 fixture)
curl -s -X POST "http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID}/backtest" \
  -H "Content-Type: application/json" \
  -d '{
    "start": "2025-11-03T00:00:00+00:00",
    "end": "2025-11-06T00:00:00+00:00",
    "label": "smoke",
    "initial_equity": "100000",
    "slippage_bps": 5.0
  }' | jq '{id, label, metrics: {trade_count: .metrics.trade_count, total_return: .metrics.total_return}}'

# 3. List backtests for the strategy
curl -s "http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID}/backtests" \
  | jq '{count, latest: .items[0] | {id, label, range_end}}'

# 4. Start the strategy on paper
curl -s -X POST "http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID}/start" \
  | jq '{action, new_status, run_id}'

# 5. Verify it's running
curl -s "http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID}" | jq '{status}'

# 6. WS smoke: subscribe to strategies + signals topics and observe events
# (run in another terminal during market hours)
echo '{"action":"subscribe","topics":["strategies","signals","backtests"]}' | \
  websocat -n1 ws://127.0.0.1:8000/ws &

# Wait a minute, then check signals
sleep 70
curl -s "http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID}/signals" \
  | jq '{count, recent: [.items[0:3] | .[] | {type, symbol, payload}]}'

# 7. Stop the strategy
curl -s -X POST "http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID}/stop" \
  | jq '{action, new_status}'

# 8. Cleanup
docker compose down
```

Expected:
- Step 1: strategy created with id=1, status=idle.
- Step 2: backtest returns metrics including trade_count (likely 0 or low on a tight 3-day RSI<30 window) and total_return.
- Step 3: list shows one backtest.
- Step 4: start transitions to paper, run_id populated.
- Step 5: detail confirms paper status.
- Step 6: WS receives `strategy.status_changed`, `strategy.run_started`. During market hours, `signal.new` events may appear if RSI crosses thresholds.
- Step 7: stop transitions to idle.

If step 4 fails because the strategies_user/examples/ directory isn't in the container (volume mount), check `docker-compose.yml` — the path `strategies_user/` should be mounted into `/app/strategies_user`. P0 should have set this up; if not, add to the backend service:

```yaml
volumes:
  - ./apps/backend/strategies_user:/app/strategies_user:ro
```

- [ ] All eight steps green.
- [ ] WS subscribers see strategy + signal events.
- [ ] Reference strategy starts and stops cleanly.

---

## §4.11 — Commit and PR

```bash
git add apps/backend/app/audit/logger.py
git add apps/backend/app/strategies/context.py
git add apps/backend/app/strategies/engine.py
git add apps/backend/app/api/v1/schemas/strategies.py
git add apps/backend/app/api/v1/strategies.py
git add apps/backend/app/api/v1/signals.py
git add apps/backend/app/main.py
git add apps/backend/app/ws/gateway.py
git add apps/backend/app/ws/replay.py
git add apps/backend/tests/api/test_strategies_endpoint.py
git add apps/backend/tests/api/test_backtest_endpoint.py
git add apps/backend/tests/api/test_signals_endpoint.py

git commit -m "feat(api): strategies and signals endpoints + ws topics

- Pydantic schemas for strategies, signals, backtests
- 11 REST endpoints under /api/v1/strategies and /api/v1/signals:
  - POST /strategies validates code_path via StrategyLoader before persist
  - PUT /strategies/{id} rejects mutations when status != IDLE
  - POST /strategies/{id}/backtest runs sync (caps range at 1 year)
  - POST /strategies/{id}/start | /stop drives the engine
- AuditAction enum extended: STRATEGY_REGISTERED / _UPDATED / _STARTED /
  _STOPPED / _ERROR / _BACKTESTED. Session 2's ORDER_CREATED placeholder
  replaced with STRATEGY_STARTED.
- StrategyContext.log_signal publishes signal.new on the bus after DB commit
- StrategyEngine publishes strategy.run_started / run_ended as distinct
  events alongside the existing strategy.status_changed
- WS gateway: strategies/signals/backtests topics; 60min replay window each

REST surface is complete; UI lands in Session 5."

git push -u origin feat/p2-strategies-rest-and-ws

gh pr create \
  --title "feat(api): strategies and signals endpoints + ws topics" \
  --body "P2 Session 4 deliverable.

In scope:
- 11 REST endpoints (strategies CRUD + start/stop + backtest + runs + signals + backtests)
- WS topic publishing for strategies/signals/backtests
- AuditAction enum extended; Session 2's placeholder cleaned up
- StrategyContext.log_signal now publishes on the bus
- StrategyEngine publishes run_started/run_ended events

Out of scope (Session 5):
- Frontend Strategies pages"

gh pr checks
gh pr merge --merge --delete-branch
git checkout main && git pull
```

- [ ] PR merged.

---

## Verification Checklist (full session)

- [ ] §4.1 `AuditAction` enum has six new strategy values; Session 2's placeholder cleaned up.
- [ ] §4.2 Pydantic schemas use `extra="forbid"` on requests and `from_attributes=True` on responses.
- [ ] §4.3 `StrategyContext.log_signal` publishes `signal.new` after DB commit.
- [ ] §4.4 `StrategyEngine` publishes `strategy.run_started` and `strategy.run_ended`.
- [ ] §4.5 Eleven REST endpoints under `/api/v1/strategies`.
- [ ] §4.6 `/api/v1/signals` endpoint with filters.
- [ ] §4.7 Both new routers mounted in `main.py`.
- [ ] §4.8 WS gateway translates bus events for strategies/signals/backtests.
- [ ] §4.9 Three test files pass; existing suites still green.
- [ ] §4.10 Live smoke walks all eight steps cleanly.
- [ ] §4.11 PR merged through protected workflow.

---

## Sign-off

```bash
git tag -a p2-session4-complete -m "P2 Session 4 complete: REST + WS topics + paper deploy lifecycle"
git push origin p2-session4-complete
```

Update `todo.md`:
- Mark P2 Session 4 complete.
- Tee up **P2 Session 5 — Frontend Strategies pages** (Checklist §7).

---

## Notes & Gotchas

1. **Audit-action cleanup in Session 2's engine code.** The placeholder `AuditAction.ORDER_CREATED` from P2 Session 2 Gotcha #6 gets replaced in this session. If you skipped that cleanup, the historical `audit_log` rows will still have `action='order.created'` against `target_type='strategy'` — that's confusing but not incorrect. Optionally write a one-shot migration to backfill, but don't worry about it for MVP.

2. **Backtest endpoint is synchronous.** A 60-day, 1-minute, single-symbol RSI backtest on a developer machine takes 2–10 seconds. A 1-year backtest can take 30–120 seconds, which is why the endpoint rejects ranges over a year. If you need longer, run the backtester from a Python REPL or write a CLI helper. Async backtests with WS progress events are deferred per the session scope.

3. **The `code_path` validation at create time is belt-and-suspenders.** `StrategyEngine.register` already calls the loader and fails cleanly. But validating at create time means the database never holds an unloadable strategy row — fewer ways to be confused later. The cost is a tiny duplicated import path.

4. **`StrategyActionResponse` returns the new status from the DB after the engine call.** Don't return what you *expected* the new status to be; return what the DB actually shows. The engine may have transitioned to ERROR mid-register (e.g., the strategy's `on_init` raised), in which case `new_status="error"` is the correct response and the UI can react accordingly.

5. **Start is idempotent.** Calling `/start` on an already-PAPER strategy returns its current state without a side effect. Same for `/stop` on IDLE. This makes UI retries safe.

6. **The `signal.new` payload includes `payload` (free-form dict).** Strategies put whatever they want in there. For the UI, we agree that signals from the reference strategy include a `"reason"` field (`"rsi_oversold"`, `"rsi_exit"`, `"stop_loss"`, `"eod"`) so the table can show a human-friendly column. Other strategies aren't bound by this convention; the UI just shows whatever is there.

7. **The `strategy.status_changed` event is now somewhat redundant** with `strategy.run_started` and `strategy.run_ended`. It still fires because some UI states care about transitions that aren't tied to a run (e.g., `IDLE → ERROR` after a failed register). Keep it.

8. **`process_at` on signals is never set in P2.** The column exists but no code path writes it. P3 (Agent MVP) will set it when an agent processes a signal. For now, leaving it `NULL` is correct.

9. **Pydantic `from_attributes=True` + aliased fields.** Several response models use `alias` to map `params_json` → `params` etc. Pydantic v2 requires `populate_by_name=True` or accessing via the original name during validation. The `model_validate(row, from_attributes=True)` pattern works because SQLAlchemy attribute access returns the column value at the model attribute name.

10. **Don't add a top-level `/api/v1/backtests` route.** Backtests live under their parent strategy. If you find yourself wanting a flat listing for a "recent backtests across all strategies" view, that's a UI aggregation — call `/api/v1/strategies` then loop. The flat endpoint earns its place only when there's a strategy-aware permission model that makes the loop expensive (P5+).

11. **`extra="forbid"` on request bodies is non-negotiable.** A typo'd field in a strategy POST silently being ignored is exactly the class of bug ADR 0002 was designed to prevent at the architectural level. The schema-level expression of the same paranoia.

12. **Don't start Session 5 in this PR.** The frontend is a separate design surface with its own components and routing. Stop at the tag.

---

*End of P2 Session 4 v0.1.*
