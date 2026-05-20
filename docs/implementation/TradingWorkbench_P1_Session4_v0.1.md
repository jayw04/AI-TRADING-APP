# P1 Session 4 — Trading DB Schema

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-20 |
| Phase | **P1**, **§2** (full) + Position-sync extension closing out **§1.4** |
| Predecessor | *TradingWorkbench_P1_Session3_v0.1.md* (tag `p1-session3-complete`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | Define the five trading-domain tables (`orders`, `fills`, `positions`, `risk_limits`, `risk_checks`), the enums they reference, one Alembic migration that creates them, a seed row for the default global risk limits, and an extension to `PositionSyncService` so it now persists into `positions`. |
| Estimated wall time | 2–3 hours |
| Stopping point | `git tag p1-session4-complete` |
| Explicitly deferred to **P1 Session 5** | The Risk Engine (logic that *uses* `risk_limits` / writes `risk_checks`), the Order Router (logic that *creates* `orders`), and the trade-update consumer (translates `alpaca.trade_update` → `fills` + status updates). |

---

## Session Goal

After this session:
- A single Alembic migration creates all five tables, the FKs between them, and the indices listed in P1 Checklist §2.3.
- The migration round-trips cleanly (`downgrade -1` → `upgrade head`).
- A default `risk_limits` row exists for user 1, scope `global`.
- `PositionSyncService` now upserts into the `positions` table on every poll, deletes positions that Alpaca no longer reports, and still publishes the same `positions.snapshot` event.
- Tests cover model creation, FK relationships, and the position-sync upsert/delete logic.

What does NOT happen this session:
- No `RiskEngine` implementation. The table is created; the logic that writes to it lives in Session 5.
- No `OrderRouter`. The `orders` table is created; nothing inserts into it yet.
- No `alpaca.trade_update` consumer. Fills table exists; nothing writes to it yet.
- No new REST endpoints. Those land in Session 6.

This session is **pure schema + one small service extension**. By the end, the data layer is ready for Session 5 to be pure logic.

---

## Prerequisites Check

```bash
cd ~/code/AI-TRADING-APP
git status                              # clean
git pull origin main
git describe --tags --abbrev=0          # expect: p1-session3-complete

# Confirm Session 3 stream wiring is intact
./scripts/dev.sh &
sleep 25
docker compose logs backend | grep -E "trade_updates_stream_started|scheduler_started|asset_sync_completed" | head
docker compose down
```

Expect all three log lines from Sessions 2 + 3.

- [ ] On `main`, clean tree, at `p1-session3-complete` or later.
- [ ] Session 3 stream wiring still boots.

Cut the branch:

```bash
git checkout -b feat/p1-trading-db-schema
```

---

## §4.1 — Enums

All shared enums in one file so models and (later) the Risk Engine, Order Router, and API schemas import from a single source of truth.

Create `apps/backend/app/db/enums.py`:

```python
"""Trading-domain enums.

Every enum is `str, Enum` so it serializes naturally to strings in JSON and
maps cleanly to a VARCHAR column in SQLite (we use `native_enum=False` in the
model declarations).
"""
from __future__ import annotations

from enum import Enum


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class TimeInForce(str, Enum):
    DAY = "day"
    GTC = "gtc"          # good til canceled
    IOC = "ioc"          # immediate or cancel
    FOK = "fok"          # fill or kill


class OrderStatus(str, Enum):
    """Internal order lifecycle.

    Sequence in the happy path:
        PENDING_RISK -> PENDING_SUBMIT -> SUBMITTED
            -> PARTIALLY_FILLED -> FILLED       (terminal)

    Other terminal states: CANCELED, EXPIRED, REJECTED, REPLACED.

    Alpaca's own order statuses (new, pending_new, accepted, ...) are mapped
    to these by the trade-update consumer in Session 5.
    """
    PENDING_RISK = "pending_risk"
    PENDING_SUBMIT = "pending_submit"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REJECTED = "rejected"
    REPLACED = "replaced"


# Terminal states (orders in these states never transition again).
TERMINAL_ORDER_STATUSES = frozenset({
    OrderStatus.FILLED,
    OrderStatus.CANCELED,
    OrderStatus.EXPIRED,
    OrderStatus.REJECTED,
    OrderStatus.REPLACED,
})


class OrderSourceType(str, Enum):
    """Who initiated the order. Audited on every order row."""
    MANUAL = "manual"
    STRATEGY = "strategy"
    AGENT_STRATEGY = "agent_strategy"    # B3 in Implementation Plan §13.3
    AGENT_PROPOSAL = "agent_proposal"    # B2 approved-by-human
    PINE = "pine"                        # webhook from TradingView


class RiskDecision(str, Enum):
    PASS = "pass"
    REJECT = "reject"


class RiskScopeType(str, Enum):
    """Scope at which a RiskLimits row applies.

    For P1 only GLOBAL is used. STRATEGY and AGENT_SESSION become relevant in
    P2 and P3 respectively; their referenced tables don't exist yet, so the
    risk_limits.scope_id column is a bare INTEGER for now (no FK).
    """
    GLOBAL = "global"
    ACCOUNT = "account"
    STRATEGY = "strategy"
    AGENT_SESSION = "agent_session"
```

- [ ] `enums.py` created.
- [ ] All six enums + the `TERMINAL_ORDER_STATUSES` set exported.

---

## §4.2 — `RiskLimits` and `RiskCheck` Models

Foundational because `orders.risk_check_id` points at `risk_checks` (and `risk_checks.order_id` points back — bidirectional, both nullable, which Alembic handles fine).

### 4.2.1 `risk_limits` model

Create `apps/backend/app/db/models/risk_limits.py`:

```python
"""RiskLimits — the configurable envelope used by the Risk Engine.

Each row is scoped (GLOBAL, ACCOUNT, STRATEGY, AGENT_SESSION). The Risk Engine
resolves the most specific applicable row at evaluate-time. For P1 we only
need GLOBAL — Session 5's engine starts there and adds the other scopes later.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    Numeric,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import RiskScopeType


class RiskLimits(Base):
    __tablename__ = "risk_limits"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    scope_type: Mapped[RiskScopeType] = mapped_column(
        SQLEnum(RiskScopeType, native_enum=False, length=32), nullable=False
    )
    # scope_id is INTEGER (not FK) because the referenced tables may not
    # exist yet (strategies in P2, agent_sessions in P3). NULL when scope is GLOBAL.
    scope_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # All caps are nullable so a row can leave a particular cap unset
    # (the engine then falls back to a more general scope's value).
    max_position_qty: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    max_position_notional: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    max_gross_exposure: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    max_daily_loss: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    max_orders_per_minute: Mapped[int | None] = mapped_column(Integer, nullable=True)

    allow_short: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allowed_symbols: Mapped[list | None] = mapped_column(JSON, nullable=True)
    denied_symbols: Mapped[list | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RiskLimits scope={self.scope_type.value} scope_id={self.scope_id}>"
```

### 4.2.2 `risk_checks` model

Create `apps/backend/app/db/models/risk_check.py`:

```python
"""RiskCheck — one row per evaluation, written by the Risk Engine.

Every order placement causes exactly one RiskCheck row to be written BEFORE
the order is dispatched to the broker (pass) or rejected (reject). This is
the audit trail for "why did/didn't this order go through".
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum as SQLEnum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.enums import RiskDecision


class RiskCheck(Base):
    __tablename__ = "risk_checks"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Linkage. For P1, only order_id is populated. strategy_id and
    # agent_session_id are reserved for P2/P3; they are bare INTEGERs now
    # without FK constraints because those tables don't exist yet. A later
    # migration will add the FKs.
    order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    strategy_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_session_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    decision: Mapped[RiskDecision] = mapped_column(
        SQLEnum(RiskDecision, native_enum=False, length=16), nullable=False
    )
    reason_codes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RiskCheck order_id={self.order_id} decision={self.decision.value}>"
```

- [ ] Both models created.

---

## §4.3 — `Order` and `Fill` Models

### 4.3.1 `orders` model

Create `apps/backend/app/db/models/order.py`:

```python
"""Order — the canonical record of an order from intent through terminal state.

Every order, regardless of source (manual / strategy / pine / agent_strategy /
agent_proposal), produces exactly one row here. The OrderRouter (Session 5) is
the only writer.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import OrderSide, OrderSourceType, OrderStatus, OrderType, TimeInForce


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Ownership / scoping
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    symbol_id: Mapped[int] = mapped_column(
        ForeignKey("symbols.id", ondelete="RESTRICT"), nullable=False
    )

    # Broker linkage. broker_order_id is NULL until Alpaca acks (i.e. while
    # status is PENDING_RISK / PENDING_SUBMIT). client_order_id is our own
    # idempotency token that we send to Alpaca.
    broker_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    client_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Intent
    side: Mapped[OrderSide] = mapped_column(
        SQLEnum(OrderSide, native_enum=False, length=8), nullable=False
    )
    qty: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    type: Mapped[OrderType] = mapped_column(
        SQLEnum(OrderType, native_enum=False, length=16), nullable=False
    )
    limit_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    stop_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    tif: Mapped[TimeInForce] = mapped_column(
        SQLEnum(TimeInForce, native_enum=False, length=8),
        nullable=False,
        default=TimeInForce.DAY,
    )
    extended_hours: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Lifecycle
    status: Mapped[OrderStatus] = mapped_column(
        SQLEnum(OrderStatus, native_enum=False, length=24),
        nullable=False,
        default=OrderStatus.PENDING_RISK,
    )
    rejection_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Provenance
    source_type: Mapped[OrderSourceType] = mapped_column(
        SQLEnum(OrderSourceType, native_enum=False, length=24), nullable=False
    )
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parent_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )

    # Risk linkage. Nullable on both sides of the circular reference.
    risk_check_id: Mapped[int | None] = mapped_column(
        ForeignKey("risk_checks.id", ondelete="SET NULL"), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    fills: Mapped[list["Fill"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    risk_check = relationship("RiskCheck", foreign_keys=[risk_check_id])
    parent_order = relationship("Order", remote_side="Order.id", uselist=False)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Order id={self.id} side={self.side.value} qty={self.qty} "
            f"status={self.status.value} src={self.source_type.value}>"
        )
```

### 4.3.2 `fills` model

Create `apps/backend/app/db/models/fill.py`:

```python
"""Fill — one row per (partial) execution received from the broker.

The Session 5 trade-update consumer writes one Fill per Alpaca 'fill' or
'partial_fill' event. Position recomputation aggregates these.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Fill(Base):
    __tablename__ = "fills"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )

    # Alpaca's execution_id — unique per fill, used for idempotency on replay.
    broker_fill_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    qty: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    commission: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal(0)
    )
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    order = relationship("Order", back_populates="fills")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Fill order_id={self.order_id} qty={self.qty} price={self.price}>"
```

- [ ] Both models created.

---

## §4.4 — `Position` Model

Create `apps/backend/app/db/models/position.py`:

```python
"""Position — the open position cache per (account, symbol).

Updated by PositionSyncService on each poll. The Position Recomputer (Session 5)
also writes here on every fill so the UI sees changes immediately rather than
waiting for the next poll.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    symbol_id: Mapped[int] = mapped_column(
        ForeignKey("symbols.id", ondelete="RESTRICT"), nullable=False
    )

    qty: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False, default=Decimal(0))
    avg_entry_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal(0)
    )
    side: Mapped[str | None] = mapped_column(String(8), nullable=True)  # 'long' | 'short'

    # Computed market values; updated from Alpaca's position snapshot.
    market_value: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal(0)
    )
    cost_basis: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal(0)
    )
    unrealized_pl: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal(0)
    )
    unrealized_plpc: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, default=Decimal(0)
    )

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        UniqueConstraint("account_id", "symbol_id", name="uq_positions_account_symbol"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Position account_id={self.account_id} symbol_id={self.symbol_id} qty={self.qty}>"
```

- [ ] `Position` model created.

---

## §4.5 — Register Models and Migrate

### 4.5.1 Register imports

Edit `apps/backend/app/db/models/__init__.py` and append:

```python
from .order import Order              # noqa: F401
from .fill import Fill                # noqa: F401
from .position import Position        # noqa: F401
from .risk_limits import RiskLimits   # noqa: F401
from .risk_check import RiskCheck     # noqa: F401
```

### 4.5.2 Generate the migration

```bash
cd apps/backend
uv run alembic revision --autogenerate -m "P1: orders, fills, positions, risk_limits, risk_checks"
```

### 4.5.3 Review the generated migration carefully

Open the new file in `alembic/versions/`. Verify each of the following — autogenerate gets foreign-key cascades and constraint names wrong about 1 time in 3.

- [ ] **Table creation order respects FKs**. `risk_checks` and `orders` reference each other; Alembic should create both tables first with the cross-FKs added via `op.create_foreign_key(...)` *after* both `create_table` calls. If it tries to create the FK inline in the wrong order, you'll get an error on `upgrade head`. Fix manually if needed: move both FK creation calls to the end of `upgrade()`.
- [ ] **`fills.order_id` cascades on delete** (`ondelete='CASCADE'`).
- [ ] **`orders.parent_order_id` is `SET NULL` on delete** (self-referential).
- [ ] **`positions` has a unique constraint** named `uq_positions_account_symbol` on `(account_id, symbol_id)`.
- [ ] **Required indices present** (P1 Checklist §2.3). If Alembic missed any, add explicit `op.create_index(...)` calls:
  ```python
  op.create_index("ix_orders_user_status_created", "orders", ["user_id", "status", "created_at"])
  op.create_index("ix_orders_symbol_created", "orders", ["symbol_id", "created_at"])
  op.create_index("ix_orders_broker_order_id", "orders", ["broker_order_id"], unique=True)
  op.create_index("ix_fills_order_id", "fills", ["order_id"])
  op.create_index("ix_fills_filled_at", "fills", ["filled_at"])
  ```
  (Drop them in `downgrade()` correspondingly.)
- [ ] **`downgrade()` drops all five tables** in reverse FK order: `fills, positions, orders, risk_checks, risk_limits`.

### 4.5.4 Apply and round-trip

```bash
uv run alembic upgrade head
uv run sqlite3 data/workbench.sqlite ".tables"
# Expect to see: accounts accounts_state alembic_version audit_log fills
#                orders positions risk_checks risk_limits symbols
#                system_config users

uv run sqlite3 data/workbench.sqlite ".schema orders" | head -40
uv run sqlite3 data/workbench.sqlite ".schema fills" | head -20
uv run sqlite3 data/workbench.sqlite ".schema positions" | head -20
uv run sqlite3 data/workbench.sqlite ".schema risk_limits"
uv run sqlite3 data/workbench.sqlite ".schema risk_checks"

uv run alembic downgrade -1
uv run sqlite3 data/workbench.sqlite ".tables"  # 5 trading tables should be gone
uv run alembic upgrade head
cd ../..
```

- [ ] `upgrade head` succeeds.
- [ ] All five tables present in `.tables`.
- [ ] Round-trip `downgrade -1` → `upgrade head` clean.

---

## §4.6 — Seed Default Risk Limits

Extend `scripts/seed_dev_data.py` to insert the default global RiskLimits row.

Find where it inserts the User/Account/Symbol rows and append after, using the same `INSERT OR IGNORE` style for idempotency.

Add at the top of the script:

```python
from decimal import Decimal
from datetime import datetime, timezone

from app.db.models.risk_limits import RiskLimits
from app.db.enums import RiskScopeType
```

Then in the seed body (inside the existing async session block):

```python
# Default global risk limits — written once, never overwritten by reseed.
existing = (await session.execute(
    select(RiskLimits).where(
        RiskLimits.user_id == 1,
        RiskLimits.scope_type == RiskScopeType.GLOBAL,
    )
)).scalars().first()
if existing is None:
    now = datetime.now(timezone.utc)
    session.add(RiskLimits(
        user_id=1,
        scope_type=RiskScopeType.GLOBAL,
        scope_id=None,
        max_position_qty=Decimal("1000"),
        max_position_notional=Decimal("25000"),
        max_gross_exposure=Decimal("100000"),
        max_daily_loss=Decimal("2000"),
        max_orders_per_minute=10,
        allow_short=False,
        allowed_symbols=None,
        denied_symbols=None,
        created_at=now,
        updated_at=now,
    ))
    await session.commit()
    print("Seeded default global risk_limits row")
else:
    print("Default global risk_limits row already exists; skipping")
```

> **Schema-name caveat.** If your P0 seed script uses `INSERT OR IGNORE` raw SQL rather than the ORM, follow the same pattern. The fields and values are the spec; the form is up to you.

Run it:

```bash
cd apps/backend
uv run python -m scripts.seed_dev_data
# or whatever the P0 invocation was
uv run sqlite3 data/workbench.sqlite \
  "SELECT scope_type, max_position_qty, max_daily_loss FROM risk_limits;"
# Expect: global|1000|2000
cd ../..
```

- [ ] Seed script extended.
- [ ] Idempotent — running twice doesn't duplicate.
- [ ] Default row exists with the spec'd values.

---

## §4.7 — Extend `PositionSyncService` to Persist

Session 2 deferred DB persistence for positions. Now that the table exists, wire it in.

### 4.7.1 Update the service

Replace the body of `apps/backend/app/services/position_sync.py` with:

```python
"""Position snapshot poller.

Pulls positions from Alpaca, upserts into the `positions` table, deletes
positions Alpaca no longer reports (closed), publishes a snapshot event.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.brokers.alpaca import AlpacaAdapter
from app.db.models.account import Account
from app.db.models.position import Position
from app.db.models.symbol import Symbol
from app.events.bus import EventBus

logger = structlog.get_logger(__name__)


class PositionSyncService:
    def __init__(
        self,
        adapter: AlpacaAdapter,
        session_factory,
        bus: EventBus,
    ) -> None:
        self._adapter = adapter
        self._session_factory = session_factory
        self._bus = bus

    async def sync_once(self) -> list[dict[str, Any]]:
        """Pull positions, upsert into DB, delete missing, publish snapshot."""
        raw_positions = self._adapter.get_positions()
        normalized = [_normalize_position(p) for p in raw_positions]

        async with self._session_factory() as session:
            # Resolve the account row this snapshot belongs to.
            mode = "paper" if self._adapter.is_paper else "live"
            account = (await session.execute(
                select(Account).where(Account.broker == "alpaca", Account.mode == mode)
            )).scalars().first()
            if account is None:
                logger.warning("position_sync_no_account_row")
                return normalized

            # Resolve symbol_ids in one query.
            tickers = [p["symbol"] for p in normalized if p["symbol"]]
            symbol_rows = (await session.execute(
                select(Symbol).where(Symbol.ticker.in_(tickers))
            )).scalars().all() if tickers else []
            symbol_id_by_ticker = {s.ticker: s.id for s in symbol_rows}

            now = datetime.now(timezone.utc)
            seen_symbol_ids = set()

            for p in normalized:
                ticker = p["symbol"]
                symbol_id = symbol_id_by_ticker.get(ticker)
                if symbol_id is None:
                    # Symbol not in our table yet (asset sync hasn't picked it
                    # up, or it's a delisted name). Skip silently for MVP;
                    # P4 polish can add a "create-on-demand" fallback.
                    logger.warning("position_sync_unknown_symbol", ticker=ticker)
                    continue
                seen_symbol_ids.add(symbol_id)

                stmt = sqlite_insert(Position).values(
                    user_id=account.user_id,
                    account_id=account.id,
                    symbol_id=symbol_id,
                    qty=p["qty"],
                    avg_entry_price=p["avg_entry_price"],
                    side=p["side"],
                    market_value=p["market_value"],
                    cost_basis=p["cost_basis"],
                    unrealized_pl=p["unrealized_pl"],
                    unrealized_plpc=p["unrealized_plpc"],
                    updated_at=now,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["account_id", "symbol_id"],
                    set_={
                        "qty": stmt.excluded.qty,
                        "avg_entry_price": stmt.excluded.avg_entry_price,
                        "side": stmt.excluded.side,
                        "market_value": stmt.excluded.market_value,
                        "cost_basis": stmt.excluded.cost_basis,
                        "unrealized_pl": stmt.excluded.unrealized_pl,
                        "unrealized_plpc": stmt.excluded.unrealized_plpc,
                        "updated_at": stmt.excluded.updated_at,
                    },
                )
                await session.execute(stmt)

            # Delete positions in our DB that Alpaca no longer reports.
            # Position table is the "open positions" cache; closed positions
            # leave history in the orders/fills tables, not here.
            existing_ids = (await session.execute(
                select(Position.symbol_id).where(Position.account_id == account.id)
            )).scalars().all()
            stale = [sid for sid in existing_ids if sid not in seen_symbol_ids]
            if stale:
                await session.execute(
                    delete(Position).where(
                        Position.account_id == account.id,
                        Position.symbol_id.in_(stale),
                    )
                )
                logger.info("position_sync_deleted_stale", count=len(stale))

            await session.commit()

        logger.info("position_sync_completed", count=len(normalized))
        await self._bus.publish(
            "positions.snapshot",
            {"count": len(normalized), "positions": normalized},
        )
        return normalized


def _to_decimal(v: Any) -> Decimal:
    if v is None or v == "":
        return Decimal(0)
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal(0)


def _normalize_position(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": raw.get("symbol"),
        "qty": _to_decimal(raw.get("qty")),
        "avg_entry_price": _to_decimal(raw.get("avg_entry_price")),
        "side": raw.get("side"),
        "market_value": _to_decimal(raw.get("market_value")),
        "cost_basis": _to_decimal(raw.get("cost_basis")),
        "unrealized_pl": _to_decimal(raw.get("unrealized_pl")),
        "unrealized_plpc": _to_decimal(raw.get("unrealized_plpc")),
    }
```

### 4.7.2 Update the lifespan construction

`PositionSyncService` now needs a `session_factory`. Edit `apps/backend/app/lifespan.py`:

```python
# OLD:
# position_sync = PositionSyncService(adapter, bus)

# NEW:
position_sync = PositionSyncService(adapter, session_factory, bus)
```

That's the only change in `lifespan.py`.

- [ ] `position_sync.py` rewritten.
- [ ] `lifespan.py` passes `session_factory` to `PositionSyncService`.

---

## §4.8 — Tests

Create `apps/backend/tests/db/test_trading_models.py`:

```python
"""Smoke tests for the trading-domain models.

These check that the schema is well-formed: rows can be inserted with the
expected types, FK constraints behave, the circular Order<->RiskCheck FK
works, and the Position unique constraint fires.
"""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    RiskDecision,
    RiskScopeType,
    TimeInForce,
)
from app.db.models.account import Account
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.risk_check import RiskCheck
from app.db.models.risk_limits import RiskLimits
from app.db.models.symbol import Symbol
from app.db.models.user import User  # if your P0 named it differently, adjust


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
async def seeded(session_factory):
    """Seed minimal user/account/symbol so the trading rows have FKs to satisfy."""
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))  # adjust to your P0 fields
        session.add(Account(id=1, user_id=1, broker="alpaca", mode="paper", label="Paper"))
        session.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ",
                           asset_class="us_equity", name="Apple Inc.", active=True))
        await session.commit()
    yield


@pytest.mark.asyncio
async def test_insert_order_with_minimum_fields(session_factory, seeded):
    async with session_factory() as session:
        order = Order(
            user_id=1, account_id=1, symbol_id=1,
            side=OrderSide.BUY,
            qty=Decimal("10"),
            type=OrderType.MARKET,
            tif=TimeInForce.DAY,
            status=OrderStatus.PENDING_RISK,
            source_type=OrderSourceType.MANUAL,
            created_at=_now(), updated_at=_now(),
        )
        session.add(order)
        await session.commit()
        assert order.id is not None
        assert order.status == OrderStatus.PENDING_RISK
        assert order.extended_hours is False


@pytest.mark.asyncio
async def test_circular_order_risk_check_link(session_factory, seeded):
    async with session_factory() as session:
        order = Order(
            user_id=1, account_id=1, symbol_id=1,
            side=OrderSide.BUY, qty=Decimal("1"), type=OrderType.MARKET,
            tif=TimeInForce.DAY, status=OrderStatus.PENDING_RISK,
            source_type=OrderSourceType.MANUAL,
            created_at=_now(), updated_at=_now(),
        )
        session.add(order)
        await session.flush()

        rc = RiskCheck(
            order_id=order.id,
            decision=RiskDecision.PASS,
            reason_codes=["OK"],
            evaluated_at=_now(),
        )
        session.add(rc)
        await session.flush()

        order.risk_check_id = rc.id
        await session.commit()

    async with session_factory() as session:
        loaded = (await session.execute(select(Order))).scalars().first()
        assert loaded.risk_check_id is not None
        assert loaded.risk_check.decision == RiskDecision.PASS


@pytest.mark.asyncio
async def test_fill_cascade_on_order_delete(session_factory, seeded):
    async with session_factory() as session:
        order = Order(
            user_id=1, account_id=1, symbol_id=1,
            side=OrderSide.BUY, qty=Decimal("1"), type=OrderType.MARKET,
            tif=TimeInForce.DAY, status=OrderStatus.FILLED,
            source_type=OrderSourceType.MANUAL,
            created_at=_now(), updated_at=_now(),
        )
        session.add(order)
        await session.flush()
        session.add(Fill(
            order_id=order.id, qty=Decimal("1"), price=Decimal("190.00"),
            commission=Decimal("0"), filled_at=_now(),
        ))
        await session.commit()
        order_id = order.id

    async with session_factory() as session:
        order = (await session.execute(select(Order).where(Order.id == order_id))).scalars().first()
        await session.delete(order)
        await session.commit()

    async with session_factory() as session:
        fills = (await session.execute(select(Fill))).scalars().all()
        assert len(fills) == 0  # cascade-deleted


@pytest.mark.asyncio
async def test_position_unique_account_symbol(session_factory, seeded):
    async with session_factory() as session:
        session.add(Position(
            user_id=1, account_id=1, symbol_id=1,
            qty=Decimal("10"), avg_entry_price=Decimal("190.00"),
            side="long",
            market_value=Decimal("1950.00"), cost_basis=Decimal("1900.00"),
            unrealized_pl=Decimal("50.00"), unrealized_plpc=Decimal("0.026"),
            updated_at=_now(),
        ))
        await session.commit()

    with pytest.raises(IntegrityError):
        async with session_factory() as session:
            session.add(Position(
                user_id=1, account_id=1, symbol_id=1,
                qty=Decimal("5"), avg_entry_price=Decimal("190.00"),
                side="long",
                market_value=Decimal("0"), cost_basis=Decimal("0"),
                unrealized_pl=Decimal("0"), unrealized_plpc=Decimal("0"),
                updated_at=_now(),
            ))
            await session.commit()


@pytest.mark.asyncio
async def test_default_risk_limits_seed_shape(session_factory):
    """After seeding (in a real run), the default global row should be present.

    In tests we seed it inline to assert the shape is valid.
    """
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        await session.flush()
        session.add(RiskLimits(
            user_id=1,
            scope_type=RiskScopeType.GLOBAL,
            scope_id=None,
            max_position_qty=Decimal("1000"),
            max_position_notional=Decimal("25000"),
            max_gross_exposure=Decimal("100000"),
            max_daily_loss=Decimal("2000"),
            max_orders_per_minute=10,
            allow_short=False,
            created_at=_now(), updated_at=_now(),
        ))
        await session.commit()
        row = (await session.execute(select(RiskLimits))).scalars().first()
        assert row.scope_type == RiskScopeType.GLOBAL
        assert row.max_daily_loss == Decimal("2000")
        assert row.allow_short is False
```

Then update `apps/backend/tests/services/test_position_sync.py` (from Session 2) to cover the new persistence behavior. Replace the previous file:

```python
"""Position sync tests — verifies upsert + delete-stale behavior."""
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.db.models.account import Account
from app.db.models.position import Position
from app.db.models.symbol import Symbol
from app.events.bus import EventBus
from app.services.position_sync import PositionSyncService


@pytest.fixture
async def seeded_for_positions(session_factory):
    async with session_factory() as session:
        from app.db.models.user import User
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(Account(id=1, user_id=1, broker="alpaca", mode="paper", label="Paper"))
        session.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ", asset_class="us_equity",
                           name="Apple Inc.", active=True))
        session.add(Symbol(id=2, ticker="MSFT", exchange="NASDAQ", asset_class="us_equity",
                           name="Microsoft", active=True))
        await session.commit()
    yield


@pytest.fixture
def mock_adapter_paper():
    a = MagicMock()
    a.is_paper = True
    a.get_positions.return_value = [
        {"symbol": "AAPL", "qty": "10", "avg_entry_price": "190.50", "side": "long",
         "market_value": "1950.00", "cost_basis": "1905.00",
         "unrealized_pl": "45.00", "unrealized_plpc": "0.024"},
    ]
    return a


@pytest.mark.asyncio
async def test_position_sync_upserts_new(session_factory, seeded_for_positions, mock_adapter_paper):
    bus = EventBus()
    svc = PositionSyncService(mock_adapter_paper, session_factory, bus)
    await svc.sync_once()

    async with session_factory() as session:
        rows = (await session.execute(select(Position))).scalars().all()
        assert len(rows) == 1
        assert rows[0].symbol_id == 1
        assert rows[0].qty == Decimal("10")


@pytest.mark.asyncio
async def test_position_sync_deletes_stale(session_factory, seeded_for_positions):
    """If MSFT was in our table but Alpaca no longer reports it, it must be removed."""
    from datetime import datetime, timezone
    async with session_factory() as session:
        session.add(Position(
            user_id=1, account_id=1, symbol_id=2,  # MSFT
            qty=Decimal("5"), avg_entry_price=Decimal("400"),
            side="long",
            market_value=Decimal("2000"), cost_basis=Decimal("2000"),
            unrealized_pl=Decimal("0"), unrealized_plpc=Decimal("0"),
            updated_at=datetime.now(timezone.utc),
        ))
        await session.commit()

    adapter = MagicMock()
    adapter.is_paper = True
    # Alpaca now reports only AAPL — MSFT is gone (closed).
    adapter.get_positions.return_value = [
        {"symbol": "AAPL", "qty": "10", "avg_entry_price": "190.50", "side": "long",
         "market_value": "1950.00", "cost_basis": "1905.00",
         "unrealized_pl": "45.00", "unrealized_plpc": "0.024"},
    ]

    bus = EventBus()
    svc = PositionSyncService(adapter, session_factory, bus)
    await svc.sync_once()

    async with session_factory() as session:
        rows = (await session.execute(select(Position))).scalars().all()
        tickers_in_db = []
        # Resolve back to tickers
        symbol_ids = [r.symbol_id for r in rows]
        symbols = (await session.execute(
            select(Symbol).where(Symbol.id.in_(symbol_ids))
        )).scalars().all()
        tickers_in_db = [s.ticker for s in symbols]
        assert "AAPL" in tickers_in_db
        assert "MSFT" not in tickers_in_db


@pytest.mark.asyncio
async def test_position_sync_skips_unknown_symbol(session_factory, seeded_for_positions):
    adapter = MagicMock()
    adapter.is_paper = True
    adapter.get_positions.return_value = [
        {"symbol": "AAPL", "qty": "10", "avg_entry_price": "190.50", "side": "long",
         "market_value": "1950.00", "cost_basis": "1905.00",
         "unrealized_pl": "45.00", "unrealized_plpc": "0.024"},
        # NVDA not in our seeded symbols — must be skipped, not crash.
        {"symbol": "NVDA", "qty": "1", "avg_entry_price": "1000", "side": "long",
         "market_value": "1000", "cost_basis": "1000",
         "unrealized_pl": "0", "unrealized_plpc": "0"},
    ]

    bus = EventBus()
    svc = PositionSyncService(adapter, session_factory, bus)
    await svc.sync_once()

    async with session_factory() as session:
        rows = (await session.execute(select(Position))).scalars().all()
        assert len(rows) == 1  # only AAPL persisted
```

Run the suite:

```bash
cd apps/backend
uv run pytest -q
cd ../..
```

- [ ] `test_trading_models.py` created.
- [ ] `test_position_sync.py` updated.
- [ ] All tests pass; existing Session 1 / 2 / 3 tests still pass.

---

## §4.9 — Manual Smoke

Boot the full stack and confirm the new table populates from Alpaca paper:

```bash
./scripts/dev.sh &
sleep 30

# If you have no paper positions, the positions table will be empty. Place one
# via curl (paper, 1 share Ford) to populate it, the same way you did in Session 3:
set -a; source .env; set +a
curl -s -X POST https://paper-api.alpaca.markets/v2/orders \
  -H "APCA-API-KEY-ID: $ALPACA_PAPER_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_PAPER_API_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"symbol":"F","qty":1,"side":"buy","type":"market","time_in_force":"day"}' | jq .

# Wait for the next position-sync tick (≤ 10s during market hours)
sleep 15

docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "SELECT symbol_id, qty, avg_entry_price, side, market_value FROM positions;"
```

You should see at least one row matching the order you just placed.

Clean up:

```bash
curl -X DELETE https://paper-api.alpaca.markets/v2/positions \
  -H "APCA-API-KEY-ID: $ALPACA_PAPER_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_PAPER_API_SECRET"
sleep 15  # wait for sync to pick up the deletion
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "SELECT count(*) FROM positions;"
# Expect: 0

docker compose down
```

- [ ] Position appears in `positions` table after a paper order fills.
- [ ] Position disappears from `positions` table after Alpaca-side closure.

---

## §4.10 — Commit and PR

```bash
git add apps/backend/app/db/enums.py
git add apps/backend/app/db/models/
git add apps/backend/alembic/versions/
git add apps/backend/scripts/seed_dev_data.py
git add apps/backend/app/services/position_sync.py
git add apps/backend/app/lifespan.py
git add apps/backend/tests/

git commit -m "feat(db): trading domain schema (orders, fills, positions, risk_limits, risk_checks)

- Six enums in app/db/enums.py (OrderSide, OrderType, TimeInForce, OrderStatus,
  OrderSourceType, RiskDecision, RiskScopeType)
- Five trading-domain models with FK relationships matching Implementation
  Plan v0.2 §6.3 + §6.5
- Single Alembic migration creates all five tables + indices from P1 §2.3
- Default global RiskLimits row seeded for user 1
  (max_daily_loss=2000, max_position_notional=25000, etc.)
- PositionSyncService now upserts into positions table and deletes stale rows
  (replaces the no-DB-persistence stub from Session 2)
- Schema tests cover circular Order<->RiskCheck FK, Fill cascade, Position
  unique constraint, and the position-sync upsert/delete behavior

Deferred to P1 Session 5: Risk Engine (consumes risk_limits, writes
risk_checks), Order Router (writes orders), trade-update consumer (writes
fills + updates order status)."

git push -u origin feat/p1-trading-db-schema

gh pr create \
  --title "feat(db): trading domain schema (orders, fills, positions, risk_limits, risk_checks)" \
  --body "P1 Session 4 deliverable. Pure schema + one small service extension. Brings the data layer ready for Session 5's order pipeline.

**In scope:** five new tables, enums, migration, seed default risk limits, position sync DB persistence.

**Out of scope (Session 5):** Risk Engine, Order Router, trade-update consumer."

gh pr checks
```

Wait for CI green, then merge:

```bash
gh pr merge --merge --delete-branch
git checkout main && git pull
```

- [ ] PR opened, CI green, merged, branch deleted.

---

## Verification Checklist (full session)

- [ ] §4.1 `app/db/enums.py` exports all six enums + `TERMINAL_ORDER_STATUSES`.
- [ ] §4.2 `RiskLimits` and `RiskCheck` models created.
- [ ] §4.3 `Order` and `Fill` models created; `Order.risk_check_id` and `RiskCheck.order_id` both nullable.
- [ ] §4.4 `Position` model created with `UniqueConstraint(account_id, symbol_id)`.
- [ ] §4.5 Migration generated, reviewed (FK ordering, indices, downgrade), applied, round-trips clean.
- [ ] §4.6 Seed script extended; default global `risk_limits` row exists after running.
- [ ] §4.7 `PositionSyncService` upserts + deletes-stale; `lifespan.py` passes `session_factory` to it.
- [ ] §4.8 New + updated tests pass; existing tests still pass.
- [ ] §4.9 Live smoke against Alpaca paper populates the `positions` table; closing the position empties it.
- [ ] §4.10 PR merged on `main` via the protected workflow.

---

## Sign-off

```bash
git tag -a p1-session4-complete -m "P1 Session 4 complete: trading DB schema + position persistence"
git push origin p1-session4-complete
```

Update `todo.md`:
- Mark Session 4 complete.
- Tee up **P1 Session 5 — Risk Engine + Order Router + Trade-Update Consumer + Reconciliation Drift**. (This is the biggest single session in P1 — the heart of the phase. ~4–5 hours.)

---

## Notes & Gotchas

1. **Circular Order ↔ RiskCheck FK.** Both columns are nullable, which lets SQLite accept the schema. The Alembic autogenerate output usually creates one table without the cross-FK, creates the other, then `op.create_foreign_key(...)` for the leftover side. If your generated migration tries to inline both FKs in the same `create_table`, the `upgrade head` will fail on SQLite — split into post-creation `op.create_foreign_key` calls manually.

2. **SQLite FK enforcement.** By default SQLite does NOT enforce foreign keys; you need `PRAGMA foreign_keys=ON` per connection. SQLAlchemy's aiosqlite driver enables this by default in modern versions, but if your CASCADE / SET NULL behavior tests fail unexpectedly, this is the first thing to check: `await connection.execute(text("PRAGMA foreign_keys=ON"))`.

3. **`Decimal` precision.** `Numeric(20, 8)` for qty (fractional shares can have up to 8 decimal places at Alpaca) and `Numeric(20, 4)` for prices (sub-penny granularity exists at some venues). Don't drop the precision — Alpaca returns these as strings precisely because Python floats would lose precision.

4. **`source_type` is required on every Order.** The `OrderSourceType` enum has no default. This is intentional: every order MUST declare its provenance. The Order Router (Session 5) will set this; for tests, set it explicitly.

5. **`broker_order_id` is NOT unique-constrained at the DB level by default**, even though the column has `unique=True`. That's because Alembic autogenerate creates the UNIQUE index separately, and you need to verify it actually appeared in the migration. Cross-check by running `EXPLAIN QUERY PLAN SELECT * FROM orders WHERE broker_order_id = 'x'` after `upgrade head`: if it shows `SCAN orders` instead of `SEARCH USING INDEX`, the unique index is missing.

6. **Position-sync's "delete stale" semantics.** A position vanishing from Alpaca's response means it's closed. We don't keep a tombstone in `positions` — closure is reconstructible from fills (Session 5). If you ever want a "positions closed today" view in the UI, that comes from joining `fills` by date, not from `positions`.

7. **`Position.side` is a free-form string**, not an enum, because Alpaca returns it as `"long"` or `"short"` and we just propagate that. If you want strictness, add a `PositionSide` enum and migrate; but for P1 this is fine.

8. **`scope_id` on `risk_limits` is INTEGER, not FK.** It would point to `strategies.id` or `agent_sessions.id` depending on `scope_type`, neither of which exists yet. A future migration in P2/P3 can add FK constraints. For now, the Risk Engine just resolves the most-specific row by `(scope_type, scope_id)` tuple matching and the lack of FK doesn't bite us.

9. **Default risk limits live in the seed, not in code.** The Risk Engine (Session 5) will resolve from the DB row. If you change the defaults, edit the seed script — don't add a Python fallback dict. Keeps one source of truth and ensures the DB always has a row.

10. **Don't start Session 5 mid-session.** Session 5 is the heart of P1 (Risk Engine + Order Router + trade-update consumer + reconciliation drift) and deserves its own focused block. Resist the urge to "just sketch the Risk Engine while the tables are fresh in my head."

---

*End of P1 Session 4 v0.1.*
