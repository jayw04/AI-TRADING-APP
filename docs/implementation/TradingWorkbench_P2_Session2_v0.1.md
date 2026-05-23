# P2 Session 2 — Strategies Schema + Framework Skeleton

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-21 |
| Phase | **P2**, **§2 (entirely) + §3 (entirely)** |
| Predecessor | *TradingWorkbench_P2_Session1_v0.1.md* (tag `p2-session1-complete`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | (1) New enums + four DB tables (`strategies`, `strategy_runs`, `signals`, `backtest_results`) + Alembic migration. (2) `Strategy` base class + `StrategyContext` (the safe accessors user strategies see). (3) `StrategyEngine` skeleton: register/unregister, scheduled bar dispatch, error containment, event-bus subscriptions. (4) `StrategyLoader` for `strategies_user/` Python files. **No real strategy runs end-to-end yet** — that arrives in Session 3 with the reference RSI strategy. |
| Estimated wall time | 3.5–4.5 hours |
| Stopping point | `git tag p2-session2-complete` |
| Out of scope | The reference RSI strategy itself (Session 3). The backtest harness (Session 3). REST endpoints for strategies (Session 4). The Strategies UI (Session 5). |

---

## Session Goal

After this session:
- Four new tables exist, the migration round-trips clean, and a STRATEGY-scope `risk_limits` row is seeded ready for Session 3's reference strategy to point at.
- `Strategy` base class is defined; subclassing it gives users `on_bar`/`on_signal`/`on_fill` hooks with sensible defaults.
- `StrategyContext` is the **only** surface user code uses to touch positions, market data, or order submission. It dispatches through `OrderRouter.submit` with `source_type=STRATEGY` and the right `source_id`. ADR 0002 holds.
- `StrategyEngine` can `register(strategy_id)` and `unregister(strategy_id)`. Registered strategies receive `on_bar` ticks at their configured cadence and `on_fill` events when their strategy's orders fill. Uncaught exceptions inside user code mark the strategy `error`, log audit, and keep the engine running.
- `StrategyLoader` resolves a Strategy class from a file path under `strategies_user/` and rejects anything outside that directory.
- A no-op test strategy proves the full register → bar-dispatch → unregister loop works end-to-end with mocked bars.

What does NOT happen this session:
- The reference RSI strategy file. That's Session 3.
- Any backtest code. Session 3.
- REST endpoints for `/api/v1/strategies` (Session 4) or `/api/v1/signals` (Session 4).
- Frontend pages (Session 5).
- Pine webhook strategies (P4) and Agent strategies (P6) — their enum values exist but are explicitly not dispatched here.

---

## Prerequisites Check

```bash
cd ~/code/AI-TRADING-APP
git status                                       # clean
git pull origin main
git describe --tags --abbrev=0                   # expect: p2-session1-complete

# Bar cache + indicators from Session 1 must work
./scripts/dev.sh &
sleep 25
curl -fs "http://127.0.0.1:8000/api/v1/indicators/AAPL?names=RSI14&timeframe=1Min" \
  | jq '{symbol, rsi: (.indicators[] | select(.name=="RSI14") | .latest)}'
docker compose down
```

- [ ] On `main`, clean tree, at `p2-session1-complete` or later.
- [ ] Session 1's indicators endpoint returns a sensible RSI value.

Cut the branch:

```bash
git checkout -b feat/p2-strategies-schema-and-framework
```

---

## §2.1 — Enums

Extend `apps/backend/app/db/enums.py` by adding three new enum classes plus a constant. Find the end of the file and append:

```python
class StrategyType(str, Enum):
    """How a strategy is implemented.

    Only PYTHON is dispatched in P2. PINE arrives in P4 (TradingView webhook
    receiver). AGENT arrives in P6 (Claude Code agent loop). The enum values
    are reserved now so we don't migrate the column twice.
    """
    PYTHON = "python"
    PINE = "pine"
    AGENT = "agent"


class StrategyStatus(str, Enum):
    """Lifecycle state of a registered strategy.

    Transitions:
        IDLE -> BACKTEST (during a backtest run) -> IDLE
        IDLE -> PAPER (engine running it against paper) -> IDLE | HALTED | ERROR
        IDLE -> LIVE  (P5; same shape as PAPER but live mode)
    """
    IDLE = "idle"
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"
    HALTED = "halted"
    ERROR = "error"


# States in which a strategy is actively dispatched by the engine.
ACTIVE_STRATEGY_STATUSES = frozenset({StrategyStatus.PAPER, StrategyStatus.LIVE})


class SignalType(str, Enum):
    """Type of a signal row.

    ENTRY/EXIT/FLAT are produced by Python strategies.
    AGENT_ACTION is reserved for B3 (P6).
    PINE_ALERT is reserved for the TradingView webhook (P4).
    INFO is a free-form annotation (e.g. 'considered entry but RSI=29.99').
    """
    ENTRY = "entry"
    EXIT = "exit"
    FLAT = "flat"
    INFO = "info"
    AGENT_ACTION = "agent_action"
    PINE_ALERT = "pine_alert"
```

- [ ] Three new enums added.
- [ ] `ACTIVE_STRATEGY_STATUSES` constant exported.

---

## §2.2 — Models

Four new ORM model files. Each registered in `apps/backend/app/db/models/__init__.py`.

### 2.2.1 — `Strategy`

Create `apps/backend/app/db/models/strategy.py`:

```python
"""Strategy — the registered, configurable definition of a trading strategy.

A row here is one (name, version, type) triple. The same Python file can be
registered multiple times under different param sets — each registration is a
distinct strategies row.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import StrategyStatus, StrategyType


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="0.1.0")

    type: Mapped[StrategyType] = mapped_column(
        SQLEnum(StrategyType, native_enum=False, length=16),
        nullable=False,
        default=StrategyType.PYTHON,
    )
    status: Mapped[StrategyStatus] = mapped_column(
        SQLEnum(StrategyStatus, native_enum=False, length=16),
        nullable=False,
        default=StrategyStatus.IDLE,
    )

    # For PYTHON strategies: relative path under apps/backend/strategies_user/
    # For PINE (P4): NULL; the alert webhook configuration drives it
    # For AGENT (P6): NULL; agent_strategy_configs row drives it
    code_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Per-strategy parameter overrides (merged over the strategy's default_params)
    params_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Symbol universe this strategy may trade. Subset of the strategy's
    # default symbol list, possibly with overrides per registration.
    symbols_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Cadence: cron-ish string (e.g. "*/1 * * * *") OR the literal "event"
    # for purely event-driven strategies that only react to fills/signals.
    schedule: Mapped[str] = mapped_column(String(64), nullable=False, default="*/1 * * * *")

    # Optional FK to a risk_limits row at STRATEGY scope. When NULL, the
    # engine falls back to the user's GLOBAL row.
    risk_limits_id: Mapped[int | None] = mapped_column(
        ForeignKey("risk_limits.id", ondelete="SET NULL"), nullable=True
    )

    # Last error text (when status == ERROR). Cleared on next successful run.
    error_text: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    risk_limits = relationship("RiskLimits", foreign_keys=[risk_limits_id])

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Strategy id={self.id} name={self.name!r} v={self.version} "
            f"type={self.type.value} status={self.status.value}>"
        )
```

### 2.2.2 — `StrategyRun`

Create `apps/backend/app/db/models/strategy_run.py`:

```python
"""StrategyRun — one row per (paper|live|backtest) run of a strategy.

A 'run' is bounded: start when register/start is called, end when unregister/
stop fires or an error transitions the strategy. Useful for the UI to show
'today I ran the strategy from 09:30 to 16:00 and it produced 12 signals'.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import StrategyStatus


class StrategyRun(Base):
    __tablename__ = "strategy_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Final state of this run (PAPER/LIVE/BACKTEST while running, IDLE/HALTED/ERROR when ended).
    status: Mapped[StrategyStatus] = mapped_column(
        SQLEnum(StrategyStatus, native_enum=False, length=16), nullable=False
    )

    error_text: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    strategy = relationship("Strategy")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<StrategyRun strategy_id={self.strategy_id} started_at={self.started_at}>"
```

### 2.2.3 — `Signal`

Create `apps/backend/app/db/models/signal.py`:

```python
"""Signal — a timestamped, symbol-scoped event from a strategy or external source.

For Python strategies in P2, signals are written by StrategyContext.log_signal.
The signal payload is whatever JSON the strategy wants to attach. Signals are
denormalized for fast read (no joins to fetch the symbol ticker).

Distinct from orders: a strategy may emit an entry signal and then submit
an order, or emit an info signal and not order anything. The two are linked
in audit_log, not in the schema.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import SignalType


class Signal(Base):
    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # NULL strategy_id is intentional: PINE_ALERT signals (P4) arrive before
    # being mapped to a strategy, and AGENT_ACTION signals (P6) may also be
    # detached.
    strategy_id: Mapped[int | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True
    )
    symbol_id: Mapped[int] = mapped_column(
        ForeignKey("symbols.id", ondelete="RESTRICT"), nullable=False
    )

    type: Mapped[SignalType] = mapped_column(
        SQLEnum(SignalType, native_enum=False, length=24),
        nullable=False,
    )

    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # When the signal was received/produced. processed_at is set when an
    # order was submitted (or the engine explicitly decided not to act).
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    strategy = relationship("Strategy")

    __table_args__ = (
        Index("ix_signals_strategy_received", "strategy_id", "received_at"),
        Index("ix_signals_symbol_received", "symbol_id", "received_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Signal id={self.id} type={self.type.value} symbol_id={self.symbol_id}>"
```

### 2.2.4 — `BacktestResult`

Create `apps/backend/app/db/models/backtest_result.py`:

```python
"""BacktestResult — one row per backtest run.

Sized for SQLite: metrics_json, equity_curve_json, trades_json may each be
tens to hundreds of KB. SQLite handles this fine. When we migrate to
Postgres (post-MVP), these columns become JSONB.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    strategy_id: Mapped[int] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # An optional human-readable label distinguishing runs ('default-params',
    # 'tighter-rsi', etc.). The actual parameter set is in params_json.
    label: Mapped[str] = mapped_column(String(128), nullable=False, default="default")

    params_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metrics_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    equity_curve_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    trades_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # Backtest date range, in UTC
    range_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    range_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    strategy = relationship("Strategy")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<BacktestResult strategy_id={self.strategy_id} created_at={self.created_at}>"
```

### 2.2.5 — Register imports

Edit `apps/backend/app/db/models/__init__.py` and append:

```python
from .strategy import Strategy                  # noqa: F401
from .strategy_run import StrategyRun           # noqa: F401
from .signal import Signal                      # noqa: F401
from .backtest_result import BacktestResult     # noqa: F401
```

- [ ] All four model files created.
- [ ] All four registered in the models `__init__.py`.

---

## §2.3 — Alembic Migration

```bash
cd apps/backend
uv run alembic revision --autogenerate -m "P2: strategies, strategy_runs, signals, backtest_results"
```

Open the generated file under `alembic/versions/` and review carefully. Verify each:

- [ ] **Table creation order.** Tables with FKs to others should be created after the targets. `strategies` references `users` (P0) and `risk_limits` (P1) — both should already exist. `strategy_runs`, `signals`, `backtest_results` reference `strategies` — should be created after `strategies`.
- [ ] **FK cascades match the model declarations.** `strategy_runs.strategy_id` cascades on delete. `signals.strategy_id` is SET NULL. `backtest_results.strategy_id` cascades on delete. `strategies.risk_limits_id` is SET NULL.
- [ ] **Indices present.** `ix_strategies_user_id` on `strategies.user_id`, `ix_strategy_runs_strategy_id`, `ix_backtest_results_strategy_id`, `ix_signals_strategy_received` and `ix_signals_symbol_received` (the two composite indices declared in `__table_args__`).
- [ ] **`downgrade()` drops in reverse FK order:** `backtest_results`, `signals`, `strategy_runs`, `strategies`.

If autogenerate missed any of the above, add `op.create_index(...)` / `op.create_foreign_key(...)` calls manually. Common miss: composite indices on `signals` declared via `__table_args__` aren't always picked up — add explicitly if so.

Apply:

```bash
uv run alembic upgrade head
uv run sqlite3 data/workbench.sqlite ".tables"
# Expect: ... strategies strategy_runs signals backtest_results ... (plus P0/P1 tables)

uv run sqlite3 data/workbench.sqlite ".schema strategies"
uv run sqlite3 data/workbench.sqlite ".schema strategy_runs"
uv run sqlite3 data/workbench.sqlite ".schema signals"
uv run sqlite3 data/workbench.sqlite ".schema backtest_results"

# Round-trip check
uv run alembic downgrade -1
uv run sqlite3 data/workbench.sqlite ".tables" | tr ' ' '\n' | sort | grep -E "strateg|signal|backtest"
# Expect: empty (the four tables are gone)
uv run alembic upgrade head
cd ../..
```

- [ ] `upgrade head` succeeds.
- [ ] All four tables present.
- [ ] Round-trip `downgrade -1` → `upgrade head` clean.

---

## §2.4 — Seed: STRATEGY-scope Risk Limits

The reference strategy that Session 3 ships will point at a tighter risk envelope than GLOBAL. Seed the row now so it's ready.

Edit `scripts/seed_dev_data.py`. Find the spot where the GLOBAL `risk_limits` row is seeded; add (after, idempotent):

```python
from app.db.enums import RiskScopeType
from app.db.models.risk_limits import RiskLimits
from decimal import Decimal
from datetime import datetime, timezone
from sqlalchemy import select

# Per-strategy risk envelope template. The strategy registered in Session 3
# will set its risk_limits_id to point at this row.
# scope_id is NULL because the strategy row doesn't exist yet at seed time;
# it will be set when the reference strategy is registered.
existing = (await session.execute(
    select(RiskLimits).where(
        RiskLimits.user_id == 1,
        RiskLimits.scope_type == RiskScopeType.STRATEGY,
        RiskLimits.scope_id.is_(None),
    )
)).scalars().first()
if existing is None:
    now = datetime.now(timezone.utc)
    session.add(RiskLimits(
        user_id=1,
        scope_type=RiskScopeType.STRATEGY,
        scope_id=None,
        max_position_qty=Decimal("100"),
        max_position_notional=Decimal("5000"),     # tighter than global $25000
        max_gross_exposure=Decimal("15000"),       # tighter than global $100000
        max_daily_loss=Decimal("500"),             # tighter than global $2000
        max_orders_per_minute=5,                   # tighter than global 10
        allow_short=False,
        allowed_symbols=None,
        denied_symbols=None,
        created_at=now,
        updated_at=now,
    ))
    await session.commit()
    print("Seeded default STRATEGY-scope risk_limits row (scope_id=NULL placeholder)")
else:
    print("STRATEGY-scope risk_limits row already exists; skipping")
```

Run:

```bash
cd apps/backend
uv run python -m scripts.seed_dev_data
uv run sqlite3 data/workbench.sqlite \
  "SELECT scope_type, scope_id, max_position_notional, max_daily_loss FROM risk_limits;"
# Expect: global|NULL|25000|2000  and  strategy|NULL|5000|500
cd ../..
```

- [ ] Seed extended; STRATEGY-scope row exists with tighter caps.
- [ ] Re-running the seed doesn't duplicate.

---

## §2.5 — `Strategy` Base Class

The contract user strategies implement. Lives at `apps/backend/app/strategies/base.py`.

Create `apps/backend/app/strategies/__init__.py`:

```python
"""Strategy framework.

User strategies subclass `Strategy` and are loaded from
`apps/backend/strategies_user/`. They get a `StrategyContext` with safe
accessors for market data, positions, order submission, and signal logging.
"""
from .base import Strategy
from .context import StrategyContext, Bar, FillEvent, SignalEvent
from .engine import StrategyEngine
from .loader import StrategyLoader, StrategyLoadError

__all__ = [
    "Strategy",
    "StrategyContext",
    "Bar",
    "FillEvent",
    "SignalEvent",
    "StrategyEngine",
    "StrategyLoader",
    "StrategyLoadError",
]
```

Create `apps/backend/app/strategies/base.py`:

```python
"""Strategy base class — the contract user strategies implement.

Subclass `Strategy`, set the four class attributes, implement whichever
of `on_bar` / `on_signal` / `on_fill` are needed. The defaults are no-ops,
so a strategy that only reacts to bars only overrides `on_bar`.

Lifecycle:
    cls = MyStrategy
    instance = cls(ctx=StrategyContext(...), params={...})  # __init__
    while engine is running:
        instance.on_bar(bar)          # at the configured cadence
        instance.on_signal(signal)    # when relevant signals arrive
        instance.on_fill(fill)        # when this strategy's orders fill
"""
from __future__ import annotations

from typing import ClassVar

from .context import Bar, FillEvent, SignalEvent, StrategyContext


class Strategy:
    """Base class for user-authored Python strategies."""

    # ---- class-level metadata (every subclass MUST override name/version) ----

    name: ClassVar[str] = "<unset>"
    version: ClassVar[str] = "0.1.0"

    # Default symbol universe; can be overridden by the registered params.
    symbols: ClassVar[list[str]] = []

    # Schedule: cron-ish ("*/1 * * * *") for periodic on_bar dispatch,
    # OR the literal string "event" for purely event-driven strategies.
    schedule: ClassVar[str] = "*/1 * * * *"

    # Default parameter dict. Merged with the registered strategy's
    # params_json (registered values override defaults).
    default_params: ClassVar[dict] = {}

    # ---- instance ----

    def __init__(self, ctx: StrategyContext, params: dict) -> None:
        self.ctx = ctx
        # params already contains defaults merged with registered overrides
        self.params = params

    # ---- hooks (override in subclass; defaults are no-op) ----

    async def on_bar(self, bar: Bar) -> None:
        """Called for each (symbol, timeframe) bar tick at the configured cadence."""
        pass

    async def on_signal(self, signal: SignalEvent) -> None:
        """Called when a signal scoped to this strategy is emitted by another component."""
        pass

    async def on_fill(self, fill: FillEvent) -> None:
        """Called when one of this strategy's orders fills (or partially fills)."""
        pass

    # ---- optional hook ----

    async def on_init(self) -> None:
        """Called once after construction, before the first on_bar.
        Useful for warming up indicators or fetching historical state."""
        pass

    async def on_shutdown(self) -> None:
        """Called once when the engine unregisters the strategy.
        Useful for emitting a final 'flat' signal or summarizing the session."""
        pass
```

- [ ] `strategies/__init__.py` and `strategies/base.py` created.

---

## §2.6 — `StrategyContext`

The narrow surface user code sees. Critically, `submit_order` dispatches to `OrderRouter.submit` — strategies cannot reach the Alpaca adapter directly.

Create `apps/backend/app/strategies/context.py`:

```python
"""StrategyContext — the safe accessors handed to user strategy code.

Design principle: every method on this class either reads state read-only or
dispatches through an existing component (OrderRouter, BarCache,
IndicatorComputer). NOTHING here lets a strategy reach the broker adapter
directly or bypass the risk engine. ADR 0002 holds.

This file does NOT import `OrderRouter` directly; it accepts a callable so
unit tests can inject a stub.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Awaitable, Callable, Optional

import pandas as pd
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.enums import OrderSourceType, SignalType
from app.db.models.position import Position
from app.db.models.signal import Signal
from app.db.models.symbol import Symbol
from app.risk import OrderRequest

logger = structlog.get_logger(__name__)


# ---------- DTOs handed to user code ----------


@dataclass
class Bar:
    """A single OHLCV bar."""
    symbol: str
    timeframe: str
    t: datetime
    o: float
    h: float
    l: float
    c: float
    v: int


@dataclass
class SignalEvent:
    """A signal scoped to a strategy."""
    signal_id: int
    strategy_id: int
    symbol: str
    type: SignalType
    payload: dict
    received_at: datetime


@dataclass
class FillEvent:
    """A fill on one of this strategy's orders."""
    fill_id: int
    order_id: int
    symbol: str
    side: str             # 'buy' | 'sell'
    qty: Decimal
    price: Decimal
    filled_at: datetime


# ---------- StrategyContext ----------


# Signature of the order-router callable injected into the context.
# Returns the persisted Order's id (or None on rejection).
OrderRouterCallable = Callable[[OrderRequest], Awaitable[Any]]


class StrategyContext:
    """The safe surface user strategy code sees.

    Constructed once per `Strategy` instance by the engine. Holds:
      - strategy_id: the registered strategy this context is for
      - user_id, account_id: scopes any DB reads
      - session_factory: opens DB sessions on demand for the strategy
      - bar_cache, indicator_computer: market-data accessors (Session 1)
      - submit_order_fn: bound to OrderRouter.submit with source_type=STRATEGY
        and source_id=strategy_id

    User code typically calls (in roughly this order):
        bars = await ctx.get_recent_bars("AAPL", "1Min", n=200)
        indicators = await ctx.get_indicators("AAPL", names=["RSI14"], timeframe="1Min")
        positions = await ctx.get_positions()
        await ctx.submit_order(...)
        await ctx.log_signal("AAPL", SignalType.ENTRY, payload={...})
    """

    def __init__(
        self,
        *,
        strategy_id: int,
        user_id: int,
        account_id: int,
        symbols: list[str],
        session_factory: async_sessionmaker[AsyncSession],
        bar_cache: Any,                # BarCache (Session 1)
        indicator_computer: Any,       # IndicatorComputer (Session 1)
        submit_order_fn: OrderRouterCallable,
    ) -> None:
        self.strategy_id = strategy_id
        self.user_id = user_id
        self.account_id = account_id
        self.symbols = list(symbols)
        self._session_factory = session_factory
        self._bar_cache = bar_cache
        self._indicator_computer = indicator_computer
        self._submit_order_fn = submit_order_fn

    # ---- market data ----

    async def get_recent_bars(
        self, symbol: str, timeframe: str, n: int = 100,
    ) -> pd.DataFrame:
        """Return the most recent N bars for (symbol, timeframe).

        Symbol must be in this strategy's allowed universe; otherwise we
        return an empty frame and log a warning. (Don't raise — that would
        let a buggy strategy take itself down via a typo.)
        """
        if symbol.upper() not in {s.upper() for s in self.symbols}:
            logger.warning("strategy_requested_unauthorized_symbol",
                           strategy_id=self.strategy_id, symbol=symbol,
                           allowed=self.symbols)
            return pd.DataFrame(columns=["t","o","h","l","c","v"])

        # Lookback window sized for the largest indicator most strategies
        # care about (SMA200). 300 minutes covers a normal trading session.
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        lookback = {"1Min": 6, "5Min": 24, "15Min": 48, "1Hour": 168, "1Day": 730}
        days_back = lookback.get(timeframe, 24)
        start = now - timedelta(hours=days_back)
        df = await self._bar_cache.get_bars(symbol.upper(), timeframe, start, now)
        return df.tail(n).reset_index(drop=True)

    async def get_indicators(
        self,
        symbol: str,
        names: list[str],
        timeframe: str = "1Min",
        n_bars: int = 250,
    ) -> dict[str, Any]:
        """Compute indicators for the last N bars on (symbol, timeframe).

        Returns a dict keyed by indicator name. Multi-output indicators
        (MACD, BB) return a dict of sub-series.
        """
        bars = await self.get_recent_bars(symbol, timeframe, n=n_bars)
        if bars.empty:
            return {n: pd.Series(dtype="float64") for n in names}
        return self._indicator_computer.compute(
            bars, names=names, symbol=symbol.upper(), timeframe=timeframe
        )

    # ---- positions ----

    async def get_positions(self) -> list[Position]:
        """Return open positions for THIS strategy's symbol universe only.

        Doesn't return position rows for unrelated symbols; a strategy
        should not be aware of holdings outside its mandate.
        """
        async with self._session_factory() as session:
            symbol_ids = (await session.execute(
                select(Symbol.id).where(Symbol.ticker.in_([s.upper() for s in self.symbols]))
            )).scalars().all()
            if not symbol_ids:
                return []
            positions = (await session.execute(
                select(Position).where(
                    Position.account_id == self.account_id,
                    Position.symbol_id.in_(symbol_ids),
                )
            )).scalars().all()
            return list(positions)

    async def get_position_for(self, symbol: str) -> Position | None:
        """Convenience: open position in one specific symbol, or None."""
        symbol = symbol.upper()
        if symbol not in {s.upper() for s in self.symbols}:
            return None
        async with self._session_factory() as session:
            sym = (await session.execute(
                select(Symbol).where(Symbol.ticker == symbol)
            )).scalars().first()
            if sym is None:
                return None
            return (await session.execute(
                select(Position).where(
                    Position.account_id == self.account_id,
                    Position.symbol_id == sym.id,
                )
            )).scalars().first()

    # ---- order submission ----

    async def submit_order(self, order_request: OrderRequest) -> Any:
        """Dispatch an order through OrderRouter with strategy source attribution.

        The engine pre-binds:
            order_request.user_id = self.user_id
            order_request.account_id = self.account_id
            order_request.source_type = OrderSourceType.STRATEGY
            order_request.source_id = str(self.strategy_id)
        ...if the caller didn't already set them. The risk engine evaluates
        as usual; rejections are returned to the strategy, not raised, so
        the strategy can log them as info signals if useful.
        """
        # Stamp provenance if the caller forgot.
        if order_request.source_type != OrderSourceType.STRATEGY:
            order_request.source_type = OrderSourceType.STRATEGY
        if not order_request.source_id:
            order_request.source_id = str(self.strategy_id)
        if order_request.user_id == 0:
            order_request.user_id = self.user_id
        if order_request.account_id == 0:
            order_request.account_id = self.account_id
        return await self._submit_order_fn(order_request)

    # ---- signal logging ----

    async def log_signal(
        self,
        symbol: str,
        type_: SignalType,
        payload: Optional[dict] = None,
    ) -> int:
        """Persist a signal row attributed to this strategy.

        Returns the new signal id.
        """
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
            return sig.id
```

- [ ] `context.py` created.
- [ ] `submit_order` calls the injected `submit_order_fn`, not the adapter directly.

---

## §2.7 — `StrategyLoader`

Loads a Python file from `apps/backend/strategies_user/` and returns the Strategy subclass it defines. Refuses paths outside that directory.

Create `apps/backend/app/strategies/loader.py`:

```python
"""StrategyLoader — resolve a Strategy class from a code_path under strategies_user/.

Security: code_paths are *trusted* in P2 because they come from the database,
which is written only via the API by the authenticated user. The loader
nevertheless refuses paths outside strategies_user/ to prevent typos or
future API bugs from importing arbitrary files.
"""
from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path
from typing import Type

import structlog

from .base import Strategy

logger = structlog.get_logger(__name__)


class StrategyLoadError(Exception):
    """Raised when a code_path cannot be loaded or doesn't define a Strategy subclass."""


class StrategyLoader:
    def __init__(self, strategies_root: Path) -> None:
        self._root = strategies_root.resolve()
        if not self._root.exists():
            raise StrategyLoadError(f"strategies_user root does not exist: {self._root}")

    def load(self, code_path: str) -> Type[Strategy]:
        """Resolve `code_path` (relative to strategies_user/) and return the
        Strategy subclass defined in it.

        Raises StrategyLoadError on any failure: path outside root, file
        missing, no Strategy subclass found, multiple subclasses without a
        clear "main" one.
        """
        path = (self._root / code_path).resolve()
        if not str(path).startswith(str(self._root)):
            raise StrategyLoadError(
                f"code_path escapes strategies_user/: {code_path}"
            )
        if not path.exists():
            raise StrategyLoadError(f"file not found: {path}")
        if path.suffix != ".py":
            raise StrategyLoadError(f"not a Python file: {path}")

        # Use a module name derived from the path so reloads work cleanly.
        module_name = f"strategies_user.{path.stem}_{abs(hash(str(path))) % 1_000_000}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise StrategyLoadError(f"could not load spec for {path}")

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            raise StrategyLoadError(f"error executing strategy module {path}: {exc}") from exc

        # Find Strategy subclasses defined in this module (exclude Strategy itself).
        candidates = [
            obj for _, obj in inspect.getmembers(module, inspect.isclass)
            if issubclass(obj, Strategy)
            and obj is not Strategy
            and obj.__module__ == module.__name__
        ]
        if not candidates:
            raise StrategyLoadError(
                f"no Strategy subclass found in {path}. Did you forget to subclass Strategy?"
            )
        if len(candidates) > 1:
            # Convention: if multiple are defined, the module must declare
            # __strategy__ = <the_class>.
            chosen = getattr(module, "__strategy__", None)
            if chosen is None or chosen not in candidates:
                raise StrategyLoadError(
                    f"multiple Strategy subclasses in {path}; declare __strategy__ = YourStrategy"
                )
            return chosen
        return candidates[0]
```

- [ ] `loader.py` created.
- [ ] Path-traversal protection in place.

---

## §2.8 — `StrategyEngine` Skeleton

The lifecycle owner. Holds running strategies, dispatches bars on a cron schedule, subscribes to the event bus for fills/signals, contains errors so user-strategy bugs don't crash the engine.

Create `apps/backend/app/strategies/engine.py`:

```python
"""StrategyEngine — register / unregister / dispatch.

Owns:
  - A dict {strategy_id: RunningStrategy} of currently-active strategies.
  - A handle to the APScheduler instance for cron-scheduled on_bar dispatch.
  - Subscriptions to the event bus for fill.created and signal.new.

On register():
  1. Load the Strategy class via StrategyLoader.
  2. Construct StrategyContext bound to this strategy_id.
  3. Construct the Strategy instance, call on_init.
  4. If schedule != "event", add an APScheduler job for on_bar dispatch.
  5. Open a StrategyRun row (started_at=now, status=PAPER).
  6. Transition strategies.status -> PAPER.

On uncaught exception from user code:
  - Log audit, transition strategies.status -> ERROR, write error_text,
    close the StrategyRun row, unregister.

On unregister():
  - Cancel the APScheduler job.
  - Call on_shutdown (best-effort, swallow exceptions).
  - Close the StrategyRun row.
  - Transition strategies.status -> IDLE (unless ERROR).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.db.enums import (
    ACTIVE_STRATEGY_STATUSES,
    StrategyStatus,
    StrategyType,
    SignalType as SignalTypeEnum,
)
from app.db.models.account import Account
from app.db.models.signal import Signal
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.strategy_run import StrategyRun
from app.db.models.symbol import Symbol
from app.events.bus import EventBus

from .base import Strategy
from .context import Bar, FillEvent, SignalEvent, StrategyContext
from .loader import StrategyLoader, StrategyLoadError

logger = structlog.get_logger(__name__)


@dataclass
class RunningStrategy:
    """A live strategy instance the engine is dispatching to."""
    strategy_id: int
    instance: Strategy
    job_id: str | None        # APScheduler job id (None for event-driven)
    run_id: int               # StrategyRun row id
    symbols: list[str]
    timeframe: str            # for periodic on_bar dispatch


class StrategyEngine:
    """Lifecycle owner. One instance per backend process."""

    def __init__(
        self,
        scheduler: AsyncIOScheduler,
        session_factory: async_sessionmaker[AsyncSession],
        bus: EventBus,
        bar_cache: Any,
        indicator_computer: Any,
        order_router: Any,           # OrderRouter from P1
        strategies_root: Path,
    ) -> None:
        self._scheduler = scheduler
        self._session_factory = session_factory
        self._bus = bus
        self._bar_cache = bar_cache
        self._indicator_computer = indicator_computer
        self._order_router = order_router
        self._loader = StrategyLoader(strategies_root)

        self._running: dict[int, RunningStrategy] = {}

        # Event-bus subscriptions for fill + signal routing
        self._unsub_fill = bus.subscribe("fill.created", self._on_fill_event)
        self._unsub_signal = bus.subscribe("signal.new", self._on_signal_event)
        logger.info("strategy_engine_started")

    async def shutdown(self) -> None:
        """Unregister everything and detach from the bus."""
        for sid in list(self._running.keys()):
            try:
                await self.unregister(sid, reason="engine_shutdown")
            except Exception:
                logger.exception("strategy_unregister_failed_on_shutdown", strategy_id=sid)
        try:
            self._unsub_fill()
            self._unsub_signal()
        except Exception:
            pass
        logger.info("strategy_engine_stopped")

    # ---- registration ----

    async def register(self, strategy_id: int) -> RunningStrategy:
        """Load, instantiate, and start dispatching to a strategy.

        Idempotent: if the strategy is already registered, returns the
        existing RunningStrategy.
        """
        if strategy_id in self._running:
            return self._running[strategy_id]

        # 1. Read the row
        async with self._session_factory() as session:
            row = await session.get(StrategyRow, strategy_id)
            if row is None:
                raise StrategyLoadError(f"strategy_id={strategy_id} not found")
            if row.type != StrategyType.PYTHON:
                raise StrategyLoadError(
                    f"strategy_id={strategy_id} is type {row.type.value}; "
                    "only PYTHON is dispatched in P2"
                )
            # Resolve account_id for this user
            account = (await session.execute(
                select(Account).where(
                    Account.user_id == row.user_id,
                    Account.broker == "alpaca",
                    Account.mode == "paper",
                )
            )).scalars().first()
            if account is None:
                raise StrategyLoadError(f"no paper account for user_id={row.user_id}")

            # 2. Load the class
            try:
                cls = self._loader.load(row.code_path or "")
            except StrategyLoadError:
                await self._mark_error(session, row, "loader_failed")
                raise

            # 3. Build context + instance
            symbols = list(row.symbols_json) or list(cls.symbols)
            merged_params = {**cls.default_params, **(row.params_json or {})}
            ctx = StrategyContext(
                strategy_id=row.id,
                user_id=row.user_id,
                account_id=account.id,
                symbols=symbols,
                session_factory=self._session_factory,
                bar_cache=self._bar_cache,
                indicator_computer=self._indicator_computer,
                submit_order_fn=self._order_router.submit,
            )
            try:
                instance = cls(ctx=ctx, params=merged_params)
            except Exception as exc:
                await self._mark_error(session, row, f"construct_failed: {exc}")
                raise

            # 4. on_init
            try:
                await instance.on_init()
            except Exception as exc:
                await self._mark_error(session, row, f"on_init_failed: {exc}")
                raise

            # 5. Open a StrategyRun row
            run = StrategyRun(
                strategy_id=row.id,
                started_at=datetime.now(timezone.utc),
                status=StrategyStatus.PAPER,
            )
            session.add(run)
            await session.commit()
            await session.refresh(run)

            # 6. Transition strategy status
            row.status = StrategyStatus.PAPER
            row.error_text = None
            row.updated_at = datetime.now(timezone.utc)
            await AuditLogger.write(
                session,
                actor_type=AuditActorType.USER,
                actor_id=str(row.user_id),
                action=AuditAction.ORDER_CREATED,   # placeholder; see Note in Gotcha #6
                target_type="strategy",
                target_id=row.id,
                payload={"event": "registered", "run_id": run.id},
                user_id=row.user_id,
            )
            await session.commit()
            run_id = run.id

        # 7. Add APScheduler job for periodic on_bar dispatch
        job_id: str | None = None
        if row.schedule != "event":
            job_id = f"strategy:{strategy_id}:on_bar"
            try:
                cron = CronTrigger.from_crontab(row.schedule)
            except Exception:
                # Fall back to "every minute" if the cron string is malformed.
                logger.warning("strategy_schedule_invalid_falling_back",
                               strategy_id=strategy_id, schedule=row.schedule)
                cron = CronTrigger.from_crontab("*/1 * * * *")
            self._scheduler.add_job(
                self._dispatch_bar_tick,
                cron,
                kwargs={"strategy_id": strategy_id},
                id=job_id,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )

        running = RunningStrategy(
            strategy_id=strategy_id,
            instance=instance,
            job_id=job_id,
            run_id=run_id,
            symbols=symbols,
            timeframe=merged_params.get("timeframe", "1Min"),
        )
        self._running[strategy_id] = running
        logger.info("strategy_registered",
                    strategy_id=strategy_id, name=cls.name, symbols=symbols,
                    schedule=row.schedule)

        # Publish a status event so the UI can react
        await self._bus.publish("strategy.status_changed", {
            "strategy_id": strategy_id, "status": StrategyStatus.PAPER.value,
        })
        return running

    async def unregister(self, strategy_id: int, *, reason: str = "user_stop") -> None:
        """Cancel the scheduled job, call on_shutdown, close the run, transition to IDLE.

        Idempotent: unregistering an unknown strategy is a no-op.
        """
        running = self._running.pop(strategy_id, None)
        if running is None:
            return

        # Remove scheduled job
        if running.job_id:
            try:
                self._scheduler.remove_job(running.job_id)
            except Exception:
                logger.exception("strategy_remove_job_failed", strategy_id=strategy_id)

        # Best-effort on_shutdown
        try:
            await running.instance.on_shutdown()
        except Exception:
            logger.exception("strategy_on_shutdown_failed", strategy_id=strategy_id)

        # Close the run + transition status
        async with self._session_factory() as session:
            run = await session.get(StrategyRun, running.run_id)
            if run is not None and run.ended_at is None:
                run.ended_at = datetime.now(timezone.utc)
                # If the row is already in ERROR, keep it; else IDLE.
                run.status = StrategyStatus.IDLE
            row = await session.get(StrategyRow, strategy_id)
            if row is not None and row.status in ACTIVE_STRATEGY_STATUSES:
                row.status = StrategyStatus.IDLE
                row.updated_at = datetime.now(timezone.utc)
            await session.commit()

        await self._bus.publish("strategy.status_changed", {
            "strategy_id": strategy_id, "status": StrategyStatus.IDLE.value,
            "reason": reason,
        })
        logger.info("strategy_unregistered", strategy_id=strategy_id, reason=reason)

    # ---- dispatch ----

    async def _dispatch_bar_tick(self, *, strategy_id: int) -> None:
        """APScheduler-invoked: fetch the latest bar for each of this strategy's
        symbols and call on_bar."""
        running = self._running.get(strategy_id)
        if running is None:
            return

        for symbol in running.symbols:
            try:
                df = await running.instance.ctx.get_recent_bars(symbol, running.timeframe, n=1)
                if df.empty:
                    continue
                last = df.iloc[-1]
                bar = Bar(
                    symbol=symbol.upper(),
                    timeframe=running.timeframe,
                    t=last["t"],
                    o=float(last["o"]),
                    h=float(last["h"]),
                    l=float(last["l"]),
                    c=float(last["c"]),
                    v=int(last["v"]),
                )
            except Exception:
                logger.exception("strategy_dispatch_get_bar_failed",
                                 strategy_id=strategy_id, symbol=symbol)
                continue

            try:
                await running.instance.on_bar(bar)
            except Exception as exc:
                await self._handle_user_exception(strategy_id, "on_bar", exc)
                return  # stop dispatching to a broken strategy this tick

    async def _on_fill_event(self, payload: dict) -> None:
        """Bus subscriber: route fill events to the originating strategy.

        Fills published with source_type='strategy' and source_id=<strategy_id>
        are routed to the matching strategy's on_fill. Other fills are ignored.
        """
        source_type = payload.get("source_type") or payload.get("order_source_type")
        source_id = payload.get("source_id") or payload.get("order_source_id")
        if source_type != "strategy" or source_id is None:
            return
        try:
            strategy_id = int(source_id)
        except (TypeError, ValueError):
            return
        running = self._running.get(strategy_id)
        if running is None:
            return

        symbol = payload.get("symbol") or ""
        fill_event = FillEvent(
            fill_id=payload.get("fill_id") or 0,
            order_id=payload.get("order_id") or 0,
            symbol=symbol.upper(),
            side=str(payload.get("side") or ""),
            qty=payload.get("qty") or 0,
            price=payload.get("price") or 0,
            filled_at=payload.get("filled_at") or datetime.now(timezone.utc),
        )
        try:
            await running.instance.on_fill(fill_event)
        except Exception as exc:
            await self._handle_user_exception(strategy_id, "on_fill", exc)

    async def _on_signal_event(self, payload: dict) -> None:
        """Route signal events to the originating strategy."""
        strategy_id = payload.get("strategy_id")
        if strategy_id is None:
            return
        running = self._running.get(int(strategy_id))
        if running is None:
            return

        try:
            signal_id = int(payload.get("signal_id") or 0)
            symbol = payload.get("symbol") or ""
            type_value = payload.get("type")
            sig_type = SignalTypeEnum(type_value) if type_value else SignalTypeEnum.INFO
        except Exception:
            return

        event = SignalEvent(
            signal_id=signal_id,
            strategy_id=running.strategy_id,
            symbol=symbol.upper(),
            type=sig_type,
            payload=payload.get("payload") or {},
            received_at=payload.get("received_at") or datetime.now(timezone.utc),
        )
        try:
            await running.instance.on_signal(event)
        except Exception as exc:
            await self._handle_user_exception(strategy_id, "on_signal", exc)

    # ---- error containment ----

    async def _handle_user_exception(
        self, strategy_id: int, hook: str, exc: BaseException,
    ) -> None:
        """User code raised. Mark strategy ERROR, audit, unregister."""
        logger.error("strategy_user_exception",
                     strategy_id=strategy_id, hook=hook, error=str(exc),
                     exc_info=True)
        async with self._session_factory() as session:
            row = await session.get(StrategyRow, strategy_id)
            if row is not None:
                await self._mark_error(session, row, f"{hook}: {exc}")
                await session.commit()
        # Unregister without invoking on_shutdown (the strategy is unhealthy).
        running = self._running.pop(strategy_id, None)
        if running is not None and running.job_id:
            try:
                self._scheduler.remove_job(running.job_id)
            except Exception:
                pass
        await self._bus.publish("strategy.error", {
            "strategy_id": strategy_id, "hook": hook, "error": str(exc),
        })

    async def _mark_error(
        self, session: AsyncSession, row: StrategyRow, text: str,
    ) -> None:
        row.status = StrategyStatus.ERROR
        row.error_text = text[:2048]
        row.updated_at = datetime.now(timezone.utc)
```

- [ ] `engine.py` created.
- [ ] `_handle_user_exception` is the central error containment point.

---

## §2.9 — Lifespan Wiring

Edit `apps/backend/app/lifespan.py`. After the bar_cache + indicator_computer wiring from Session 1, add:

```python
# Add to imports:
from pathlib import Path
from app.strategies import StrategyEngine

# In lifespan body, after BarCache + IndicatorComputer + scheduler are ready
# AND after OrderRouter is constructed (it's needed by the engine):
strategy_engine = StrategyEngine(
    scheduler=scheduler._scheduler,     # access the underlying APScheduler instance
    session_factory=session_factory,
    bus=bus,
    bar_cache=bar_cache,
    indicator_computer=indicator_computer,
    order_router=order_router,
    strategies_root=Path("strategies_user"),
)
app.state.strategy_engine = strategy_engine

# Re-register strategies that were active before the last shutdown:
async with session_factory() as session:
    from sqlalchemy import select
    from app.db.enums import ACTIVE_STRATEGY_STATUSES
    from app.db.models.strategy import Strategy as StrategyRow
    rows = (await session.execute(
        select(StrategyRow).where(StrategyRow.status.in_(list(ACTIVE_STRATEGY_STATUSES)))
    )).scalars().all()
    for row in rows:
        try:
            await strategy_engine.register(row.id)
        except Exception:
            logger.exception("strategy_resume_failed_on_boot", strategy_id=row.id)

# In the shutdown finally-block, BEFORE the scheduler shutdown:
if strategy_engine is not None:
    try:
        await strategy_engine.shutdown()
    except Exception:
        logger.exception("strategy_engine_shutdown_failed")
```

> **APScheduler access.** Session 2's `WorkbenchScheduler` wraps `AsyncIOScheduler`. The engine needs the wrapped instance to register cron jobs. If your wrapper doesn't expose the underlying scheduler, add a property `def scheduler(self) -> AsyncIOScheduler: return self._scheduler`.

> **`order_router` availability.** The OrderRouter is constructed in P1 Session 5's lifespan changes. It must be in scope when the engine is constructed; if not, hoist the OrderRouter construction earlier in the lifespan body.

- [ ] Engine constructed in lifespan.
- [ ] Resume-on-boot loop iterates strategies in active status.
- [ ] Engine shutdown called before scheduler shutdown.

---

## §2.10 — Strategy-Isolation CI Tripwire

Per P2 Checklist §8.6. The Risk Engine has a grep tripwire to enforce ADR 0002; we add a similar one ensuring strategy modules can't directly import `app.brokers`.

Create `apps/backend/scripts/check_strategy_isolation.sh`:

```bash
#!/usr/bin/env bash
# Strategy isolation tripwire: code under apps/backend/app/strategies/
# must NOT import from app.brokers directly. The only path to the broker
# is through OrderRouter, which the engine injects into StrategyContext.
#
# This catches future PRs that try to shortcut around StrategyContext.
set -euo pipefail

PATTERN='from\s+app\.brokers|import\s+app\.brokers'
SEARCH_DIR="apps/backend/app/strategies"

OFFENDERS=$(grep -rEn "$PATTERN" "$SEARCH_DIR" --include='*.py' || true)

if [[ -n "$OFFENDERS" ]]; then
  echo "STRATEGY ISOLATION VIOLATION — code under app/strategies/ imports app.brokers:" >&2
  echo "$OFFENDERS" >&2
  echo "" >&2
  echo "Strategies reach the broker only via StrategyContext.submit_order, which the" >&2
  echo "engine binds to OrderRouter.submit. Don't bypass." >&2
  exit 1
fi
echo "Strategy isolation OK"
```

Make executable:

```bash
chmod +x apps/backend/scripts/check_strategy_isolation.sh
bash apps/backend/scripts/check_strategy_isolation.sh
# expect: "Strategy isolation OK"
```

Add to `.github/workflows/ci.yml` near the existing ADR 0002 check:

```yaml
      - name: Strategy isolation invariant check
        run: bash apps/backend/scripts/check_strategy_isolation.sh
```

After this PR is green, add the new step as a required check via the GitHub Rulesets UI.

- [ ] Script created, executable, runs clean.
- [ ] Wired into CI workflow.

---

## §2.11 — Tests

Three test files. Goal: prove register → bar-dispatch → fill-routing → error-containment → unregister works end-to-end with a no-op test strategy. No real Alpaca, no real bars.

### 2.11.1 — Trivial test strategy

Create `apps/backend/tests/fixtures/strategies/echo_strategy.py`:

```python
"""Test fixture: a strategy that records every hook invocation for assertions.

NOT for production use. Lives under tests/fixtures so it's never loaded by
the real engine (the loader resolves paths under strategies_user/ only).
"""
from app.strategies import Strategy


class EchoStrategy(Strategy):
    name = "echo"
    version = "0.0.1"
    symbols = ["AAPL"]
    schedule = "*/1 * * * *"
    default_params = {"timeframe": "1Min"}

    def __init__(self, ctx, params):
        super().__init__(ctx, params)
        self.bars_seen: list = []
        self.fills_seen: list = []
        self.signals_seen: list = []
        self.init_called = False
        self.shutdown_called = False

    async def on_init(self):
        self.init_called = True

    async def on_bar(self, bar):
        self.bars_seen.append(bar)

    async def on_fill(self, fill):
        self.fills_seen.append(fill)

    async def on_signal(self, signal):
        self.signals_seen.append(signal)

    async def on_shutdown(self):
        self.shutdown_called = True
```

We need the engine's loader to be able to find this file. The cleanest path is to use a separate StrategyLoader instance pointed at the test fixtures root.

### 2.11.2 — `StrategyContext` tests

Create `apps/backend/tests/strategies/__init__.py` (empty) and `apps/backend/tests/strategies/test_context.py`:

```python
"""StrategyContext tests with mocked OrderRouter."""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
from sqlalchemy import select

from app.db.enums import OrderSide, OrderSourceType, OrderType, SignalType, TimeInForce
from app.db.models.account import Account
from app.db.models.position import Position
from app.db.models.signal import Signal
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.risk import OrderRequest
from app.strategies.context import StrategyContext


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(Account(id=1, user_id=1, broker="alpaca", mode="paper", label="Paper"))
        session.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ",
                           asset_class="us_equity", name="Apple", active=True))
        session.add(Symbol(id=2, ticker="MSFT", exchange="NASDAQ",
                           asset_class="us_equity", name="Microsoft", active=True))
        await session.commit()


def _ctx(session_factory, **overrides) -> StrategyContext:
    submit_calls = []
    async def fake_submit(req):
        submit_calls.append(req)
        return MagicMock(id=42, status=MagicMock(value="submitted"))
    submit_calls_ref = submit_calls

    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=pd.DataFrame())
    indicator_computer = MagicMock()

    ctx = StrategyContext(
        strategy_id=overrides.get("strategy_id", 99),
        user_id=overrides.get("user_id", 1),
        account_id=overrides.get("account_id", 1),
        symbols=overrides.get("symbols", ["AAPL"]),
        session_factory=session_factory,
        bar_cache=bar_cache,
        indicator_computer=indicator_computer,
        submit_order_fn=fake_submit,
    )
    return ctx, submit_calls_ref


@pytest.mark.asyncio
async def test_submit_order_stamps_source_attribution(session_factory, seeded):
    ctx, submit_calls = _ctx(session_factory)
    req = OrderRequest(
        user_id=0, account_id=0, symbol_id=1, symbol="AAPL",
        side=OrderSide.BUY, qty=Decimal("1"),
        type=OrderType.MARKET, tif=TimeInForce.DAY,
        source_type=OrderSourceType.MANUAL,  # caller "forgot" to set STRATEGY
    )
    await ctx.submit_order(req)

    assert len(submit_calls) == 1
    sent = submit_calls[0]
    assert sent.source_type == OrderSourceType.STRATEGY
    assert sent.source_id == "99"
    assert sent.user_id == 1
    assert sent.account_id == 1


@pytest.mark.asyncio
async def test_get_positions_filtered_by_strategy_symbols(session_factory, seeded):
    async with session_factory() as session:
        # AAPL is in the strategy's universe; MSFT is not.
        session.add(Position(
            user_id=1, account_id=1, symbol_id=1,  # AAPL
            qty=Decimal("10"), avg_entry_price=Decimal("190"), side="long",
            market_value=Decimal("1900"), cost_basis=Decimal("1900"),
            unrealized_pl=Decimal("0"), unrealized_plpc=Decimal("0"),
            updated_at=_now(),
        ))
        session.add(Position(
            user_id=1, account_id=1, symbol_id=2,  # MSFT
            qty=Decimal("5"), avg_entry_price=Decimal("400"), side="long",
            market_value=Decimal("2000"), cost_basis=Decimal("2000"),
            unrealized_pl=Decimal("0"), unrealized_plpc=Decimal("0"),
            updated_at=_now(),
        ))
        await session.commit()

    ctx, _ = _ctx(session_factory, symbols=["AAPL"])
    positions = await ctx.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol_id == 1


@pytest.mark.asyncio
async def test_log_signal_persists_row(session_factory, seeded):
    ctx, _ = _ctx(session_factory)
    sig_id = await ctx.log_signal("AAPL", SignalType.ENTRY, payload={"rsi": 28.5})
    assert sig_id > 0

    async with session_factory() as session:
        rows = (await session.execute(select(Signal))).scalars().all()
        assert len(rows) == 1
        assert rows[0].type == SignalType.ENTRY
        assert rows[0].strategy_id == 99
        assert rows[0].payload_json == {"rsi": 28.5}


@pytest.mark.asyncio
async def test_get_recent_bars_returns_empty_for_unauthorized_symbol(session_factory, seeded):
    ctx, _ = _ctx(session_factory, symbols=["AAPL"])
    # Request bars for MSFT, which is not in the strategy's allowed universe
    df = await ctx.get_recent_bars("MSFT", "1Min", n=10)
    assert df.empty
```

### 2.11.3 — `StrategyLoader` tests

Create `apps/backend/tests/strategies/test_loader.py`:

```python
from pathlib import Path

import pytest

from app.strategies.loader import StrategyLoader, StrategyLoadError


@pytest.fixture
def fixtures_root():
    return Path(__file__).resolve().parents[1] / "fixtures" / "strategies"


def test_loader_finds_echo_strategy(fixtures_root):
    loader = StrategyLoader(fixtures_root)
    cls = loader.load("echo_strategy.py")
    assert cls.__name__ == "EchoStrategy"
    assert cls.name == "echo"


def test_loader_rejects_path_outside_root(fixtures_root):
    loader = StrategyLoader(fixtures_root)
    with pytest.raises(StrategyLoadError, match="escapes"):
        loader.load("../../app/main.py")


def test_loader_rejects_missing_file(fixtures_root):
    loader = StrategyLoader(fixtures_root)
    with pytest.raises(StrategyLoadError, match="file not found"):
        loader.load("does_not_exist.py")


def test_loader_rejects_non_python(fixtures_root, tmp_path):
    # Create a junk fixture
    j = fixtures_root / "junk.txt"
    j.write_text("not python")
    try:
        loader = StrategyLoader(fixtures_root)
        with pytest.raises(StrategyLoadError, match="not a Python file"):
            loader.load("junk.txt")
    finally:
        j.unlink()


def test_loader_rejects_no_strategy_subclass(fixtures_root, tmp_path):
    f = fixtures_root / "_no_subclass.py"
    f.write_text("def hello(): return 'world'\n")
    try:
        loader = StrategyLoader(fixtures_root)
        with pytest.raises(StrategyLoadError, match="no Strategy subclass"):
            loader.load("_no_subclass.py")
    finally:
        f.unlink()
```

### 2.11.4 — `StrategyEngine` integration tests

Create `apps/backend/tests/strategies/test_engine.py`:

```python
"""StrategyEngine: register / dispatch / error-contain / unregister.

These tests use a real session, real event bus, real APScheduler, but the
order router is mocked and the bar cache is a stub returning canned bars.
"""
import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.db.enums import (
    OrderSide, OrderSourceType, OrderStatus, OrderType,
    SignalType, StrategyStatus, StrategyType, TimeInForce,
)
from app.db.models.account import Account
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.strategy_run import StrategyRun
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.events.bus import EventBus
from app.strategies import StrategyEngine


FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "strategies"


def _now():
    return datetime.now(timezone.utc)


def _canned_bar_df():
    return pd.DataFrame([{
        "t": _now(), "o": 190.0, "h": 190.5, "l": 189.5, "c": 190.2, "v": 12345,
    }])


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(Account(id=1, user_id=1, broker="alpaca", mode="paper", label="Paper"))
        session.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ",
                           asset_class="us_equity", name="Apple", active=True))
        await session.commit()


@pytest.fixture
async def engine(session_factory, seeded):
    scheduler = AsyncIOScheduler(timezone="America/New_York")
    scheduler.start()

    bus = EventBus()
    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=_canned_bar_df())
    indicator_computer = MagicMock()
    order_router = MagicMock()
    order_router.submit = AsyncMock(return_value=MagicMock(id=99))

    eng = StrategyEngine(
        scheduler=scheduler,
        session_factory=session_factory,
        bus=bus,
        bar_cache=bar_cache,
        indicator_computer=indicator_computer,
        order_router=order_router,
        strategies_root=FIXTURES_ROOT,
    )
    yield eng, bus, order_router
    await eng.shutdown()
    scheduler.shutdown(wait=False)


async def _register_echo_strategy(session_factory) -> int:
    """Insert an echo_strategy row pointing at the fixture file."""
    async with session_factory() as session:
        row = StrategyRow(
            user_id=1,
            name="echo-test",
            version="0.0.1",
            type=StrategyType.PYTHON,
            status=StrategyStatus.IDLE,
            code_path="echo_strategy.py",
            params_json={"timeframe": "1Min"},
            symbols_json=["AAPL"],
            schedule="event",   # event-driven so we don't depend on cron firing
            risk_limits_id=None,
            created_at=_now(), updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


@pytest.mark.asyncio
async def test_register_transitions_to_paper_and_opens_run(engine, session_factory):
    eng, bus, _ = engine
    sid = await _register_echo_strategy(session_factory)
    running = await eng.register(sid)

    assert running.strategy_id == sid
    assert running.instance.init_called is True

    async with session_factory() as session:
        row = await session.get(StrategyRow, sid)
        assert row.status == StrategyStatus.PAPER
        runs = (await session.execute(
            select(StrategyRun).where(StrategyRun.strategy_id == sid)
        )).scalars().all()
        assert len(runs) == 1
        assert runs[0].ended_at is None


@pytest.mark.asyncio
async def test_unregister_calls_on_shutdown_and_closes_run(engine, session_factory):
    eng, _, _ = engine
    sid = await _register_echo_strategy(session_factory)
    running = await eng.register(sid)
    instance = running.instance

    await eng.unregister(sid, reason="test_done")

    assert instance.shutdown_called is True
    async with session_factory() as session:
        row = await session.get(StrategyRow, sid)
        assert row.status == StrategyStatus.IDLE
        runs = (await session.execute(
            select(StrategyRun).where(StrategyRun.strategy_id == sid)
        )).scalars().all()
        assert runs[0].ended_at is not None


@pytest.mark.asyncio
async def test_fill_event_routes_to_correct_strategy(engine, session_factory):
    eng, bus, _ = engine
    sid = await _register_echo_strategy(session_factory)
    running = await eng.register(sid)
    instance = running.instance

    # Simulate a fill on a strategy-attributed order
    await bus.publish("fill.created", {
        "source_type": "strategy",
        "source_id": str(sid),
        "fill_id": 1,
        "order_id": 100,
        "symbol": "AAPL",
        "side": "buy",
        "qty": "1",
        "price": "190.50",
        "filled_at": _now(),
    })
    await asyncio.sleep(0)

    assert len(instance.fills_seen) == 1
    assert instance.fills_seen[0].symbol == "AAPL"


@pytest.mark.asyncio
async def test_fill_for_other_source_ignored(engine, session_factory):
    eng, bus, _ = engine
    sid = await _register_echo_strategy(session_factory)
    running = await eng.register(sid)
    instance = running.instance

    # A manual order fill — must not be routed to the strategy
    await bus.publish("fill.created", {
        "source_type": "manual",
        "order_id": 999,
        "symbol": "AAPL",
        "side": "buy",
        "qty": "1",
        "price": "190.50",
    })
    await asyncio.sleep(0)

    assert len(instance.fills_seen) == 0


@pytest.mark.asyncio
async def test_user_exception_marks_error_and_unregisters(engine, session_factory):
    eng, bus, _ = engine

    # Patch the EchoStrategy.on_fill to raise
    sid = await _register_echo_strategy(session_factory)
    running = await eng.register(sid)
    async def boom(_fill):
        raise RuntimeError("synthetic failure")
    running.instance.on_fill = boom  # type: ignore[method-assign]

    await bus.publish("fill.created", {
        "source_type": "strategy",
        "source_id": str(sid),
        "fill_id": 1, "order_id": 100, "symbol": "AAPL", "side": "buy",
        "qty": "1", "price": "190.50",
    })
    await asyncio.sleep(0)

    async with session_factory() as session:
        row = await session.get(StrategyRow, sid)
        assert row.status == StrategyStatus.ERROR
        assert row.error_text is not None
        assert "synthetic failure" in row.error_text

    # The engine should have unregistered the broken strategy
    assert sid not in eng._running


@pytest.mark.asyncio
async def test_register_pine_strategy_is_rejected_in_p2(engine, session_factory):
    eng, _, _ = engine
    async with session_factory() as session:
        row = StrategyRow(
            user_id=1, name="pine-not-yet", version="0.0.1",
            type=StrategyType.PINE, status=StrategyStatus.IDLE,
            code_path=None, params_json={}, symbols_json=["AAPL"],
            schedule="event", risk_limits_id=None,
            created_at=_now(), updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        pine_sid = row.id

    from app.strategies.loader import StrategyLoadError
    with pytest.raises(StrategyLoadError, match="only PYTHON is dispatched"):
        await eng.register(pine_sid)
```

### 2.11.5 — Run the suite

```bash
cd apps/backend
uv run pytest tests/strategies -v
# expect: all green
uv run pytest -q
# expect: all green, P1 + P2 Session 1 tests still pass
cd ../..
```

- [ ] All three new test files pass.
- [ ] Existing P1 + Session 1 tests still green.

---

## §2.12 — Manual Smoke

P2 Session 2 has no live trading behavior to smoke — there's no real strategy yet, just the framework. But two things are worth verifying live:

1. The database has the new tables and they're queryable.
2. The lifespan boots cleanly with the new engine wired up and the strategy-resume-on-boot loop is a no-op (no IDLE strategies → nothing to resume).

```bash
./scripts/dev.sh &
sleep 30

# 1. Tables exist
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  ".tables" | tr ' ' '\n' | grep -E "^(strategies|strategy_runs|signals|backtest_results)$"

# 2. Default strategy-scope risk_limits row present
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "SELECT scope_type, max_position_notional, max_daily_loss FROM risk_limits;"
# Expect: global|25000|2000 and strategy|5000|500

# 3. Backend logs show the engine started + no strategies resumed
docker compose logs backend --tail=80 | grep -E "strategy_engine_started|alpaca_connected"
# Expect: both lines present, in order

# 4. Strategy isolation tripwire passes
bash apps/backend/scripts/check_strategy_isolation.sh

docker compose down
```

- [ ] Four new tables visible.
- [ ] STRATEGY-scope risk_limits row in DB.
- [ ] Backend logs show `strategy_engine_started`.
- [ ] Isolation tripwire prints "Strategy isolation OK".

---

## §2.13 — Commit and PR

```bash
git add apps/backend/app/db/enums.py
git add apps/backend/app/db/models/strategy.py
git add apps/backend/app/db/models/strategy_run.py
git add apps/backend/app/db/models/signal.py
git add apps/backend/app/db/models/backtest_result.py
git add apps/backend/app/db/models/__init__.py
git add apps/backend/alembic/versions/
git add apps/backend/scripts/seed_dev_data.py
git add apps/backend/app/strategies/
git add apps/backend/app/lifespan.py
git add apps/backend/scripts/check_strategy_isolation.sh
git add .github/workflows/ci.yml
git add apps/backend/tests/fixtures/strategies/
git add apps/backend/tests/strategies/

git commit -m "feat(strategies): schema + framework skeleton

- Enums: StrategyType, StrategyStatus (with ACTIVE_STRATEGY_STATUSES),
  SignalType. PINE/AGENT values reserved (not dispatched in P2).
- Models: strategies, strategy_runs, signals, backtest_results with FKs +
  indices. Single Alembic migration; round-trips clean.
- Seed: STRATEGY-scope risk_limits row with tighter caps (5k notional,
  500 daily loss) for Session 3's reference strategy to point at.
- Strategy base class: on_bar / on_signal / on_fill / on_init /
  on_shutdown hooks with no-op defaults.
- StrategyContext: the safe surface user code sees. submit_order
  dispatches through the injected OrderRouter callable; ADR 0002 holds.
  Positions / bars / signals filtered to the strategy's allowed symbols.
- StrategyLoader: resolves a Strategy subclass from a file path under
  strategies_user/. Refuses path traversal. Requires __strategy__ when
  a module defines multiple subclasses.
- StrategyEngine: register/unregister + APScheduler-driven on_bar
  dispatch + event-bus subscriptions for fill.created and signal.new.
  Uncaught user exceptions mark the strategy ERROR, write audit, and
  unregister — the engine keeps running.
- Resume-on-boot: lifespan re-registers strategies whose persisted
  status is PAPER/LIVE.
- New CI tripwire: app/strategies/ may not import app.brokers.

No reference strategy yet (Session 3). No REST endpoints (Session 4).
No UI (Session 5)."

git push -u origin feat/p2-strategies-schema-and-framework

gh pr create \
  --title "feat(strategies): schema + framework skeleton" \
  --body "P2 Session 2 deliverable. Schema (4 tables) + framework (base, context, loader, engine). No real strategy runs yet — Session 3 ships the reference RSI strategy + backtest harness.

In scope:
- Strategies / strategy_runs / signals / backtest_results tables
- Strategy / StrategyContext / StrategyLoader / StrategyEngine
- Strategy-isolation CI tripwire

Out of scope (next sessions):
- Reference RSI strategy (Session 3)
- Backtest harness (Session 3)
- REST + WS topics for strategies (Session 4)
- Strategies UI (Session 5)"

gh pr checks
gh pr merge --merge --delete-branch
git checkout main && git pull
```

- [ ] PR merged.

---

## Verification Checklist (full session)

- [ ] §2.1 Three new enums exported; ACTIVE_STRATEGY_STATUSES constant available.
- [ ] §2.2 Four ORM models created and registered.
- [ ] §2.3 Migration generated, reviewed, applied, round-trips.
- [ ] §2.4 STRATEGY-scope risk_limits row seeded; idempotent.
- [ ] §2.5 Strategy base class with five hooks.
- [ ] §2.6 StrategyContext narrow surface; submit_order routes through OrderRouter.
- [ ] §2.7 StrategyLoader path-traversal-safe.
- [ ] §2.8 StrategyEngine register/unregister + dispatch + error containment.
- [ ] §2.9 Engine wired into lifespan; resume-on-boot iterates active strategies.
- [ ] §2.10 Strategy-isolation tripwire runs in CI.
- [ ] §2.11 All new tests pass; existing tests still pass.
- [ ] §2.12 Live smoke verifies tables, seed, engine startup, isolation check.
- [ ] §2.13 PR merged through protected workflow.

---

## Sign-off

```bash
git tag -a p2-session2-complete -m "P2 Session 2 complete: strategies schema + framework skeleton"
git push origin p2-session2-complete
```

Update `todo.md`:
- Mark P2 Session 2 complete.
- Tee up **P2 Session 3 — Reference RSI strategy + backtest harness** (Checklist §4 + §5).

---

## Notes & Gotchas

1. **No strategy runs end-to-end yet.** The engine can register a no-op strategy and dispatch ticks; that's it. Session 3 is when the reference RSI strategy proves the full stack actually trades.

2. **APScheduler instance access.** The engine needs the underlying `AsyncIOScheduler`. If the `WorkbenchScheduler` wrapper from P1 Session 2 doesn't expose it directly, add a property — don't construct a second scheduler. Two schedulers contending for the same job IDs would be a sneaky bug.

3. **The strategy's allowed-symbol filter is enforced in two places.** `StrategyContext.get_recent_bars` returns empty for unauthorized symbols, and `log_signal` warns. Neither raises — a typo in the strategy shouldn't be a fatal crash, just a no-op + log. The risk engine catches actual order attempts at the cap layer regardless.

4. **`source_id` on the OrderRequest is the strategy id as a string.** P1's `OrderSourceType.STRATEGY` exists; the `source_id` field is `str | None`. Stamping the strategy id lets the trade-update consumer route fills back to the right strategy via the bus subscription.

5. **Resume-on-boot is best-effort.** If a strategy fails to re-register on boot, it's logged and skipped — the rest of the system keeps starting. The user sees the strategy in `error` status on next API read. The alternative (fail boot if any strategy fails to resume) would make a single broken strategy file a denial-of-service.

6. **The audit `AuditAction.ORDER_CREATED` placeholder.** I used the existing enum for the registration audit row because P2 hasn't extended `AuditAction` with strategy-specific actions yet. Session 4 (REST endpoints) is the right time to add `STRATEGY_REGISTERED`, `STRATEGY_STARTED`, `STRATEGY_STOPPED`, `STRATEGY_ERROR`; until then, the placeholder is harmless because the `payload` carries the event detail.

7. **`max_instances=1, coalesce=True` on the cron job.** If the engine ever stalls (a strategy takes 30 seconds to process a 30-second tick), APScheduler default behavior is to skip overlapping invocations rather than queue them. `coalesce=True` means missed ticks collapse to one — what you'd intuitively want for "every minute, run once on the latest data."

8. **PINE and AGENT enum values are reserved but rejected at register time.** A strategy row with `type=PINE` exists in the DB but `engine.register(id)` raises `StrategyLoadError`. This matches the design: schema is forward-compatible, runtime is feature-gated. The error message names the future phase.

9. **No hot-reload of strategy files.** Changing a `.py` file under `strategies_user/` while a strategy is registered does nothing — the module was loaded once at register time and Python's module cache holds the old version. For MVP, the workflow is: unregister, edit, register. Hot-reload lands in P4 polish.

10. **`__strategy__` convention for multi-class files.** If a file defines multiple `Strategy` subclasses (rare, but plausible for "main + base"), set `__strategy__ = MainClass` at module level. The loader picks it; the test loader test covers the rejection path when it's missing.

11. **Don't start P2 Session 3 in this PR.** The reference strategy is a meaningful piece of design (parameter choices, RSI thresholds, stop-loss mechanics). It deserves its own focused session and PR.

---

*End of P2 Session 2 v0.1.*
