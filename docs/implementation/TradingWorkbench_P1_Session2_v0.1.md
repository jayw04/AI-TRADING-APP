# P1 Session 2 — Asset Sync, Account/Position Polling, Scheduler & Lifespan

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-20 |
| Phase | **P1**, **§1.3 + §1.4 (read/poll path)** |
| Predecessor | *TradingWorkbench_P1_Session1_v0.1.md* (tag `p1-session1-complete`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | Bring the Alpaca adapter alive: a scheduler runs daily asset sync + on-cadence account/position polling, results land in the DB or fan out through the event bus, all wired into FastAPI startup/shutdown. |
| Estimated wall time | 3–4 hours |
| Stopping point | `git tag p1-session2-complete` |
| Explicitly deferred to **P1 Session 3** | Trade Updates WebSocket lifecycle (`TradeUpdatesStream.start/stop`); reconciliation drift detection across polls |

---

## Session Goal

After this session:
- A new `accounts_state` table caches the live account snapshot (cash, equity, buying power, day P&L).
- An **`AssetSyncService`** runs once at startup and daily at 04:00 ET, upserting Alpaca's US-equity asset universe into the `symbols` table.
- An **`AccountSyncService`** polls `get_account()` and upserts `accounts_state`.
- A **`PositionSyncService`** polls `get_positions()` and publishes `positions.snapshot` events through the event bus. (No DB persistence yet — the `positions` table lands in Session 4 along with orders/fills.)
- An **`AsyncIOScheduler`** orchestrates all three with market-hours-aware cadence.
- FastAPI's `lifespan` cleanly starts and stops the scheduler.
- Backend tests pass with mocked adapter; one end-to-end smoke run against Alpaca paper proves it works.

What does NOT happen this session:
- No `TradeUpdatesStream.start()` implementation — still raises `NotImplementedError`. Wired up in Session 3.
- No drift comparison logic. Drift detection is Session 3.
- No DB persistence for positions. The positions table lands in Session 4.
- No REST endpoints exposed for the new data. Those land in Session 5.

---

## Prerequisites Check

```bash
cd ~/code/AI-TRADING-APP   # or wherever your local clone is
git status                 # must be clean
git pull origin main
git describe --tags --abbrev=0   # expect: p1-session1-complete

# Confirm the Alpaca adapter foundation from Session 1 is working
cd apps/backend
uv run python << 'EOF'
from app.brokers.alpaca import AlpacaAdapter
a = AlpacaAdapter(); a.connect()
print("paper:", a.is_paper, "| status:", a.get_account().get("status"))
EOF
cd ../..
```

Expect: `paper: True | status: ACTIVE`. If not, fix Session 1 issues before proceeding.

- [ ] On `main`, clean working tree, at tag `p1-session1-complete` (or later).
- [ ] Alpaca paper smoke works.

Cut the feature branch:

```bash
git checkout -b feat/p1-asset-account-position-sync
```

---

## §2.1 — `accounts_state` Cache Table

Singleton-per-account cache holding the live account snapshot.

### 2.1.1 The model

Create `apps/backend/app/db/models/account_state.py`:

```python
"""Live cache of the Alpaca account snapshot.

One row per account. Updated by the AccountSyncService on each poll. Distinct
from the static `accounts` table (which holds identity/credentials metadata) —
this table is the *current* live snapshot the UI Dashboard reads.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class AccountState(Base):
    __tablename__ = "accounts_state"

    id: Mapped[int] = mapped_column(primary_key=True)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    # Numeric fields — Decimal(18, 4) is more than enough for retail equities
    cash: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal(0))
    equity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal(0))
    last_equity: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal(0))
    buying_power: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal(0))
    portfolio_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal(0))
    daytrade_count: Mapped[int] = mapped_column(default=0)

    # Computed convenience fields
    day_change: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal(0))
    day_change_pct: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False, default=Decimal(0))

    # Status flags
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN")
    pattern_day_trader: Mapped[bool] = mapped_column(default=False)
    trading_blocked: Mapped[bool] = mapped_column(default=False)
    account_blocked: Mapped[bool] = mapped_column(default=False)

    # Forensic dump of the full Alpaca payload, so we never lose a field
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    account = relationship("Account")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AccountState account_id={self.account_id} equity={self.equity}>"
```

Register the model so Alembic autogenerate sees it. Edit `apps/backend/app/db/models/__init__.py` and append the import:

```python
from .account_state import AccountState  # noqa: F401
```

### 2.1.2 Migration

```bash
cd apps/backend
uv run alembic revision --autogenerate -m "P1: accounts_state cache table"
```

Open the new file under `alembic/versions/` and **review carefully**. Verify:
- `op.create_table('accounts_state', ...)` includes a FK to `accounts.id` with `ondelete='CASCADE'`.
- A unique constraint exists on `account_id`.
- The downgrade `op.drop_table('accounts_state')` is present.

Apply:

```bash
uv run alembic upgrade head
uv run sqlite3 data/workbench.sqlite ".schema accounts_state"
cd ../..
```

Expect a CREATE TABLE statement matching the model. Then test the round-trip:

```bash
cd apps/backend
uv run alembic downgrade -1
uv run alembic upgrade head
cd ../..
```

- [ ] `account_state.py` model created.
- [ ] Registered in `db/models/__init__.py`.
- [ ] Migration generated, reviewed, applied.
- [ ] Round-trips `downgrade -1` → `upgrade head` cleanly.

---

## §2.2 — Market Hours Helper

Used by the scheduler to pick a polling cadence.

Create `apps/backend/app/services/__init__.py`:

```python
"""Background services: scheduled jobs and pollers that bring the broker state
into the application. None of these accept user input; they read from Alpaca
and either persist to the DB or publish to the event bus."""
```

Then `apps/backend/app/services/market_hours.py`:

```python
"""US equity market hours awareness.

Simple time-of-day check against US/Eastern. Does NOT handle exchange holidays
in MVP — Alpaca will reject orders on closed days anyway, and the holiday
calendar can be layered in during P4 polish.
"""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

NYSE_TZ = ZoneInfo("America/New_York")
REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
PREMARKET_OPEN = time(4, 0)
AFTERHOURS_CLOSE = time(20, 0)


def is_weekday(now: datetime | None = None) -> bool:
    now = (now or datetime.now(NYSE_TZ)).astimezone(NYSE_TZ)
    return now.weekday() < 5  # Mon=0 .. Fri=4


def is_regular_session(now: datetime | None = None) -> bool:
    """True during regular trading hours (09:30-16:00 ET, Mon-Fri)."""
    now = (now or datetime.now(NYSE_TZ)).astimezone(NYSE_TZ)
    return is_weekday(now) and REGULAR_OPEN <= now.time() < REGULAR_CLOSE


def is_extended_session(now: datetime | None = None) -> bool:
    """True during extended hours (04:00-09:30 and 16:00-20:00 ET)."""
    now = (now or datetime.now(NYSE_TZ)).astimezone(NYSE_TZ)
    if not is_weekday(now):
        return False
    t = now.time()
    return (PREMARKET_OPEN <= t < REGULAR_OPEN) or (REGULAR_CLOSE <= t < AFTERHOURS_CLOSE)


def session_label(now: datetime | None = None) -> str:
    """Return 'regular' | 'extended' | 'closed'."""
    if is_regular_session(now):
        return "regular"
    if is_extended_session(now):
        return "extended"
    return "closed"
```

- [ ] `services/__init__.py` exists.
- [ ] `market_hours.py` created.

---

## §2.3 — Asset Sync Service

Pulls Alpaca's US-equity asset list, upserts into `symbols`, deactivates removed rows.

Create `apps/backend/app/services/asset_sync.py`:

```python
"""Daily asset/symbol universe sync.

Pulls Alpaca's active US-equity tradable assets and upserts into the local
`symbols` table. Symbols no longer in Alpaca's active list are marked
inactive (active=False) — never deleted, so historical references remain
joinable.
"""
from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.alpaca import AlpacaAdapter
from app.db.models.symbol import Symbol
from app.events.bus import EventBus

logger = structlog.get_logger(__name__)


class AssetSyncService:
    """Syncs the local `symbols` table against Alpaca's asset universe.

    Designed to be called from the scheduler — not from a request handler.
    """

    def __init__(
        self,
        adapter: AlpacaAdapter,
        session_factory,  # async_sessionmaker[AsyncSession]
        bus: EventBus,
    ) -> None:
        self._adapter = adapter
        self._session_factory = session_factory
        self._bus = bus

    async def sync_once(self) -> dict[str, int]:
        """Run one full sync. Returns counts for observability/testing.

        Strategy:
          1. Fetch the active US-equity asset list from Alpaca (sync call wrapped
             in run_in_executor by the caller if needed; alpaca-py is sync).
          2. Compute (added, updated, deactivated) sets vs. local DB.
          3. Upsert active rows, deactivate missing ones in one transaction.
          4. Publish `system.symbols_synced` event.
        """
        logger.info("asset_sync_started")
        alpaca_assets = self._adapter.list_assets(active_only=True)
        alpaca_by_ticker = {a["symbol"]: a for a in alpaca_assets if a.get("symbol")}

        added = 0
        updated = 0
        deactivated = 0

        async with self._session_factory() as session:
            # Pull current local symbols
            existing = (await session.execute(select(Symbol))).scalars().all()
            existing_by_ticker = {s.ticker: s for s in existing}

            # Upsert active assets
            for ticker, asset in alpaca_by_ticker.items():
                payload = _alpaca_asset_to_symbol_payload(asset)
                stmt = sqlite_insert(Symbol).values(**payload)
                stmt = stmt.on_conflict_do_update(
                    index_elements=["ticker"],
                    set_={
                        "exchange": stmt.excluded.exchange,
                        "asset_class": stmt.excluded.asset_class,
                        "name": stmt.excluded.name,
                        "active": True,
                    },
                )
                await session.execute(stmt)
                if ticker in existing_by_ticker:
                    updated += 1
                else:
                    added += 1

            # Deactivate locals that aren't in the Alpaca active list
            tickers_to_deactivate = [
                t for t in existing_by_ticker
                if t not in alpaca_by_ticker and existing_by_ticker[t].active
            ]
            if tickers_to_deactivate:
                await session.execute(
                    update(Symbol)
                    .where(Symbol.ticker.in_(tickers_to_deactivate))
                    .values(active=False)
                )
                deactivated = len(tickers_to_deactivate)

            await session.commit()

        counts = {
            "count_total": len(alpaca_by_ticker),
            "count_added": added,
            "count_updated": updated,
            "count_deactivated": deactivated,
        }
        logger.info("asset_sync_completed", **counts)
        await self._bus.publish("system.symbols_synced", counts)
        return counts


def _alpaca_asset_to_symbol_payload(asset: dict[str, Any]) -> dict[str, Any]:
    """Translate one Alpaca asset record into the columns of `symbols`."""
    return {
        "ticker": asset["symbol"],
        "exchange": asset.get("exchange") or "",
        "asset_class": asset.get("class") or asset.get("asset_class") or "us_equity",
        "name": asset.get("name") or asset["symbol"],
        "active": True,
    }
```

> **Note on the Symbol model.** P0 created `symbols` with columns `(id, ticker, exchange, asset_class, name, active)`. The upsert above matches that exactly. If your P0 schema differs (e.g., the column is `is_active` instead of `active`), adjust the `set_={...}` dict accordingly. Run `uv run sqlite3 apps/backend/data/workbench.sqlite ".schema symbols"` if you're unsure.

- [ ] `asset_sync.py` created.
- [ ] Column names in `_alpaca_asset_to_symbol_payload` match the actual `symbols` schema.

---

## §2.4 — Account Sync Service

Polls `get_account()` and upserts `accounts_state`.

Create `apps/backend/app/services/account_sync.py`:

```python
"""Account snapshot poller.

Pulls the live account snapshot from Alpaca and upserts the `accounts_state`
cache row. Publishes `account.snapshot` events for live UI updates.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.alpaca import AlpacaAdapter
from app.db.models.account import Account
from app.db.models.account_state import AccountState
from app.events.bus import EventBus

logger = structlog.get_logger(__name__)


class AccountSyncService:
    def __init__(
        self,
        adapter: AlpacaAdapter,
        session_factory,  # async_sessionmaker[AsyncSession]
        bus: EventBus,
    ) -> None:
        self._adapter = adapter
        self._session_factory = session_factory
        self._bus = bus

    async def sync_once(self) -> dict[str, Any]:
        """Pull the latest account snapshot, upsert AccountState, publish event."""
        raw = self._adapter.get_account()
        payload = _normalize_account(raw)

        async with self._session_factory() as session:
            # Find the account row this snapshot belongs to. For MVP single-user,
            # the *first* paper Alpaca account is the target. Multi-account
            # support comes when we add Alpaca account IDs to the `accounts`
            # row in Session 4.
            account = await self._resolve_account(session)
            if account is None:
                logger.warning("account_sync_no_account_row")
                return payload

            stmt = sqlite_insert(AccountState).values(
                account_id=account.id,
                **payload,
                updated_at=datetime.now(timezone.utc),
                raw_payload=raw,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["account_id"],
                set_={
                    "cash": stmt.excluded.cash,
                    "equity": stmt.excluded.equity,
                    "last_equity": stmt.excluded.last_equity,
                    "buying_power": stmt.excluded.buying_power,
                    "portfolio_value": stmt.excluded.portfolio_value,
                    "daytrade_count": stmt.excluded.daytrade_count,
                    "day_change": stmt.excluded.day_change,
                    "day_change_pct": stmt.excluded.day_change_pct,
                    "status": stmt.excluded.status,
                    "pattern_day_trader": stmt.excluded.pattern_day_trader,
                    "trading_blocked": stmt.excluded.trading_blocked,
                    "account_blocked": stmt.excluded.account_blocked,
                    "raw_payload": stmt.excluded.raw_payload,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            await session.execute(stmt)
            await session.commit()

        logger.info("account_sync_completed", status=payload["status"], equity=str(payload["equity"]))
        await self._bus.publish("account.snapshot", {"account_id": account.id, **{k: str(v) if isinstance(v, Decimal) else v for k, v in payload.items()}})
        return payload

    async def _resolve_account(self, session: AsyncSession) -> Account | None:
        mode = "paper" if self._adapter.is_paper else "live"
        result = await session.execute(
            select(Account).where(Account.broker == "alpaca", Account.mode == mode)
        )
        return result.scalars().first()


def _to_decimal(v: Any, default: str = "0") -> Decimal:
    if v is None or v == "":
        return Decimal(default)
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal(default)


def _normalize_account(raw: dict[str, Any]) -> dict[str, Any]:
    """Map Alpaca's account fields to AccountState column names."""
    equity = _to_decimal(raw.get("equity"))
    last_equity = _to_decimal(raw.get("last_equity"))
    day_change = equity - last_equity
    day_change_pct = (
        (day_change / last_equity * Decimal(100))
        if last_equity > 0
        else Decimal(0)
    )
    return {
        "cash": _to_decimal(raw.get("cash")),
        "equity": equity,
        "last_equity": last_equity,
        "buying_power": _to_decimal(raw.get("buying_power")),
        "portfolio_value": _to_decimal(raw.get("portfolio_value") or raw.get("equity")),
        "daytrade_count": int(raw.get("daytrade_count") or 0),
        "day_change": day_change,
        "day_change_pct": day_change_pct,
        "status": str(raw.get("status") or "UNKNOWN"),
        "pattern_day_trader": bool(raw.get("pattern_day_trader") or False),
        "trading_blocked": bool(raw.get("trading_blocked") or False),
        "account_blocked": bool(raw.get("account_blocked") or False),
    }
```

- [ ] `account_sync.py` created.
- [ ] `_resolve_account` matches the actual `accounts` schema from P0 (broker + mode columns).

---

## §2.5 — Position Sync Service (in-memory only for now)

Polls `get_positions()` and publishes a snapshot event. No DB persistence yet.

Create `apps/backend/app/services/position_sync.py`:

```python
"""Position snapshot poller.

For Session 2: pulls positions from Alpaca and publishes them as a snapshot
event. No DB persistence — the `positions` table lands in P1 Session 4 along
with orders/fills, and this service will be extended then to upsert into it.
"""
from __future__ import annotations

from typing import Any

import structlog

from app.brokers.alpaca import AlpacaAdapter
from app.events.bus import EventBus

logger = structlog.get_logger(__name__)


class PositionSyncService:
    def __init__(self, adapter: AlpacaAdapter, bus: EventBus) -> None:
        self._adapter = adapter
        self._bus = bus

    async def sync_once(self) -> list[dict[str, Any]]:
        """Pull positions, publish snapshot, return them.

        Session 4 will add the side-effect of upserting into the `positions`
        table; for now this is read-and-publish.
        """
        positions = self._adapter.get_positions()
        normalized = [_normalize_position(p) for p in positions]
        logger.info("position_sync_completed", count=len(normalized))
        await self._bus.publish(
            "positions.snapshot",
            {"count": len(normalized), "positions": normalized},
        )
        return normalized


def _normalize_position(raw: dict[str, Any]) -> dict[str, Any]:
    """Pick the fields the UI/event subscribers care about."""
    return {
        "symbol": raw.get("symbol"),
        "qty": _maybe_number(raw.get("qty")),
        "avg_entry_price": _maybe_number(raw.get("avg_entry_price")),
        "side": raw.get("side"),
        "market_value": _maybe_number(raw.get("market_value")),
        "cost_basis": _maybe_number(raw.get("cost_basis")),
        "unrealized_pl": _maybe_number(raw.get("unrealized_pl")),
        "unrealized_plpc": _maybe_number(raw.get("unrealized_plpc")),
        "current_price": _maybe_number(raw.get("current_price")),
        "lastday_price": _maybe_number(raw.get("lastday_price")),
        "change_today": _maybe_number(raw.get("change_today")),
        "asset_class": raw.get("asset_class"),
    }


def _maybe_number(v: Any) -> str | None:
    """Keep as a string to preserve precision; the consumer can Decimal it.

    Alpaca returns numeric fields as strings in JSON; we propagate that.
    """
    if v is None or v == "":
        return None
    return str(v)
```

- [ ] `position_sync.py` created.

---

## §2.6 — Scheduler

`AsyncIOScheduler` running all three services on appropriate cadences.

Create `apps/backend/app/services/scheduler.py`:

```python
"""APScheduler wiring for the workbench background jobs.

Cadences:
  - Asset sync:    run once at startup, then daily at 04:00 ET (pre-market).
  - Account sync:  every 10s during regular hours; every 60s otherwise.
  - Position sync: every 10s during regular hours; every 60s otherwise.

The "every 10s during regular hours" pattern is implemented by scheduling
a single interval job that checks market_hours and self-throttles. This is
simpler than maintaining two competing jobs.
"""
from __future__ import annotations

import asyncio
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.services.market_hours import is_regular_session
from app.services.asset_sync import AssetSyncService
from app.services.account_sync import AccountSyncService
from app.services.position_sync import PositionSyncService

logger = structlog.get_logger(__name__)

# A poll counter used by the throttle. We poll every 10s; during off-hours
# we only actually do work every 6th tick (= every 60s).
_OFFHOURS_THROTTLE = 6


class WorkbenchScheduler:
    def __init__(
        self,
        asset_sync: AssetSyncService,
        account_sync: AccountSyncService,
        position_sync: PositionSyncService,
    ) -> None:
        self._asset_sync = asset_sync
        self._account_sync = account_sync
        self._position_sync = position_sync
        self._scheduler = AsyncIOScheduler(timezone="America/New_York")
        self._account_ticks = 0
        self._position_ticks = 0

    def start(self) -> None:
        # Asset sync: daily 04:00 ET
        self._scheduler.add_job(
            self._safe(self._asset_sync.sync_once, "asset_sync"),
            CronTrigger(hour=4, minute=0),
            id="asset_sync_daily",
            replace_existing=True,
        )

        # Account sync: every 10s (throttled off-hours)
        self._scheduler.add_job(
            self._safe(self._account_tick, "account_sync"),
            IntervalTrigger(seconds=10),
            id="account_sync_tick",
            replace_existing=True,
        )

        # Position sync: every 10s (throttled off-hours)
        self._scheduler.add_job(
            self._safe(self._position_tick, "position_sync"),
            IntervalTrigger(seconds=10),
            id="position_sync_tick",
            replace_existing=True,
        )

        self._scheduler.start()
        logger.info("scheduler_started")

    async def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("scheduler_stopped")

    async def run_startup_sync(self) -> None:
        """Run the at-startup sync passes once, in order.

        Called from the FastAPI lifespan AFTER the scheduler is started so any
        startup errors are visible immediately.
        """
        try:
            await self._asset_sync.sync_once()
        except Exception:
            logger.exception("startup_asset_sync_failed")
        try:
            await self._account_sync.sync_once()
        except Exception:
            logger.exception("startup_account_sync_failed")
        try:
            await self._position_sync.sync_once()
        except Exception:
            logger.exception("startup_position_sync_failed")

    # ---- ticks ----

    async def _account_tick(self) -> None:
        self._account_ticks = (self._account_ticks + 1) % _OFFHOURS_THROTTLE
        if not is_regular_session() and self._account_ticks != 0:
            return
        await self._account_sync.sync_once()

    async def _position_tick(self) -> None:
        self._position_ticks = (self._position_ticks + 1) % _OFFHOURS_THROTTLE
        if not is_regular_session() and self._position_ticks != 0:
            return
        await self._position_sync.sync_once()

    # ---- helpers ----

    def _safe(self, coro_fn, name: str):
        """Wrap a coroutine fn so a single tick failure doesn't kill the schedule."""
        async def _wrapped():
            try:
                await coro_fn()
            except Exception:  # noqa: BLE001
                logger.exception(f"{name}_tick_failed")
        return _wrapped
```

- [ ] `scheduler.py` created.

---

## §2.7 — FastAPI Lifespan Integration

Wire the scheduler into FastAPI's startup/shutdown lifecycle.

Create `apps/backend/app/lifespan.py`:

```python
"""FastAPI lifespan wiring for background services.

Responsibilities at startup:
  1. Instantiate AlpacaAdapter and connect (fail-fast if creds are wrong).
  2. Instantiate the three sync services.
  3. Instantiate the scheduler, register jobs, start it.
  4. Run the startup sync pass.

At shutdown:
  1. Stop the scheduler.
  2. Disconnect the adapter.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI

from app.brokers.alpaca import AlpacaAdapter
from app.db.session import get_session_factory
from app.events.bus import get_event_bus
from app.services.account_sync import AccountSyncService
from app.services.asset_sync import AssetSyncService
from app.services.position_sync import PositionSyncService
from app.services.scheduler import WorkbenchScheduler

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("lifespan_startup_begin")

    adapter: AlpacaAdapter | None = None
    scheduler: WorkbenchScheduler | None = None

    try:
        adapter = AlpacaAdapter()
        adapter.connect()
        logger.info("alpaca_connected_at_startup", paper=adapter.is_paper)

        session_factory = get_session_factory()
        bus = get_event_bus()

        asset_sync = AssetSyncService(adapter, session_factory, bus)
        account_sync = AccountSyncService(adapter, session_factory, bus)
        position_sync = PositionSyncService(adapter, bus)

        scheduler = WorkbenchScheduler(asset_sync, account_sync, position_sync)
        scheduler.start()

        # Stash on app.state so request handlers (and tests) can reach them.
        app.state.alpaca_adapter = adapter
        app.state.asset_sync = asset_sync
        app.state.account_sync = account_sync
        app.state.position_sync = position_sync
        app.state.scheduler = scheduler

        # Initial sync pass — fire and (don't) forget; failure is logged but
        # does not abort startup, so the API is reachable for diagnostics.
        await scheduler.run_startup_sync()

        logger.info("lifespan_startup_complete")
        yield
    finally:
        logger.info("lifespan_shutdown_begin")
        if scheduler is not None:
            try:
                await scheduler.shutdown()
            except Exception:
                logger.exception("scheduler_shutdown_failed")
        if adapter is not None:
            try:
                adapter.disconnect()
            except Exception:
                logger.exception("adapter_disconnect_failed")
        logger.info("lifespan_shutdown_complete")
```

Now wire it into the app. Edit `apps/backend/app/main.py`. Find your `create_app` factory and pass `lifespan` to the `FastAPI` constructor:

```python
from app.lifespan import lifespan

def create_app() -> FastAPI:
    app = FastAPI(
        title="Trading Workbench",
        version="0.1.0",
        lifespan=lifespan,
    )
    # ... existing middleware, routers, etc.
    return app
```

> **Important.** If your P0 `main.py` used `@app.on_event("startup")` / `@app.on_event("shutdown")` decorators, FastAPI deprecated those. Migrate by moving any body of those handlers into `lifespan` before the `yield` (startup) or after it (shutdown). Otherwise events run twice or never.

> **Also important.** `get_session_factory()` and `get_event_bus()` are accessors I'm assuming exist from P0. If your P0 used different names (e.g., `Session` async_sessionmaker exported directly, or `EventBus` accessed as a module-level singleton), adjust the imports above. The pattern stays the same.

- [ ] `lifespan.py` created.
- [ ] `main.py` passes `lifespan` to `FastAPI(...)`.
- [ ] Any old `@app.on_event` handlers migrated or removed.

### 2.7.1 Smoke test the lifespan

```bash
cd apps/backend
uv run uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8000
```

Watch the logs in the same terminal. You should see, in order:

```
lifespan_startup_begin
alpaca_adapter_init paper=True base_url=https://paper-api.alpaca.markets
alpaca_adapter_connected paper=True
alpaca_connected_at_startup paper=True
scheduler_started
asset_sync_started
asset_sync_completed count_total=5000+ count_added=5000+ count_updated=0 count_deactivated=0
account_sync_completed status=ACTIVE equity=100000.00
position_sync_completed count=0
lifespan_startup_complete
```

In another terminal:
```bash
curl -s http://127.0.0.1:8000/healthz | jq .
```

Should still return `{"status":"ok","db":"ok"}`.

Ctrl-C the uvicorn process; in the logs you should see the shutdown sequence:
```
lifespan_shutdown_begin
scheduler_stopped
alpaca_adapter_disconnected
lifespan_shutdown_complete
```

- [ ] Startup sequence logs in the right order.
- [ ] Asset sync count > 5000.
- [ ] Account sync logs `status=ACTIVE`.
- [ ] Shutdown logs cleanly on Ctrl-C.

If anything's wrong: the most common cause is a mismatch between the `symbols` schema and the upsert column list in `asset_sync.py`. Re-run the smoke after fixing.

---

## §2.8 — Tests

Create `apps/backend/tests/services/__init__.py` (empty), then the test files.

### 2.8.1 `test_market_hours.py`

```python
from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.market_hours import (
    is_extended_session,
    is_regular_session,
    is_weekday,
    session_label,
)

ET = ZoneInfo("America/New_York")


def _et(year, month, day, hour, minute):
    return datetime(year, month, day, hour, minute, tzinfo=ET)


def test_regular_session_at_10am_tuesday():
    t = _et(2026, 5, 19, 10, 0)
    assert is_regular_session(t) is True
    assert is_extended_session(t) is False
    assert session_label(t) == "regular"


def test_extended_premarket_at_5am():
    t = _et(2026, 5, 19, 5, 0)
    assert is_regular_session(t) is False
    assert is_extended_session(t) is True
    assert session_label(t) == "extended"


def test_extended_afterhours_at_6pm():
    t = _et(2026, 5, 19, 18, 0)
    assert is_regular_session(t) is False
    assert is_extended_session(t) is True


def test_closed_at_3am():
    t = _et(2026, 5, 19, 3, 0)
    assert session_label(t) == "closed"


def test_weekend_always_closed():
    sat = _et(2026, 5, 23, 10, 0)
    sun = _et(2026, 5, 24, 10, 0)
    assert is_weekday(sat) is False
    assert is_weekday(sun) is False
    assert session_label(sat) == "closed"
    assert session_label(sun) == "closed"


def test_exact_open_inclusive():
    t = _et(2026, 5, 19, 9, 30)
    assert is_regular_session(t) is True


def test_exact_close_exclusive():
    t = _et(2026, 5, 19, 16, 0)
    assert is_regular_session(t) is False
    assert is_extended_session(t) is True  # 16:00 starts afterhours
```

### 2.8.2 `test_asset_sync.py`

```python
"""Asset sync tests with mocked adapter + an in-memory SQLite session."""
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.db.models.symbol import Symbol
from app.events.bus import EventBus
from app.services.asset_sync import AssetSyncService


@pytest.fixture
def mock_adapter():
    a = MagicMock()
    a.list_assets.return_value = [
        {"symbol": "AAPL", "exchange": "NASDAQ", "asset_class": "us_equity", "name": "Apple Inc."},
        {"symbol": "MSFT", "exchange": "NASDAQ", "asset_class": "us_equity", "name": "Microsoft"},
        {"symbol": "SPY",  "exchange": "ARCA",   "asset_class": "us_equity", "name": "SPDR S&P 500"},
    ]
    return a


@pytest.mark.asyncio
async def test_asset_sync_inserts_new_symbols(session_factory, mock_adapter):
    bus = EventBus()
    received = []
    async def on_event(payload):
        received.append(payload)
    bus.subscribe("system.symbols_synced", on_event)

    svc = AssetSyncService(mock_adapter, session_factory, bus)
    counts = await svc.sync_once()

    assert counts["count_total"] == 3
    assert counts["count_added"] == 3
    assert counts["count_deactivated"] == 0

    async with session_factory() as session:
        rows = (await session.execute(select(Symbol).order_by(Symbol.ticker))).scalars().all()
        tickers = [r.ticker for r in rows]
        assert "AAPL" in tickers and "MSFT" in tickers and "SPY" in tickers
        assert all(r.active for r in rows)


@pytest.mark.asyncio
async def test_asset_sync_deactivates_missing(session_factory, mock_adapter):
    # Seed an existing symbol that's NOT in the mock Alpaca response
    async with session_factory() as session:
        session.add(Symbol(ticker="STALE", exchange="NASDAQ", asset_class="us_equity", name="Stale Co", active=True))
        await session.commit()

    bus = EventBus()
    svc = AssetSyncService(mock_adapter, session_factory, bus)
    counts = await svc.sync_once()

    assert counts["count_deactivated"] == 1

    async with session_factory() as session:
        stale = (await session.execute(select(Symbol).where(Symbol.ticker == "STALE"))).scalars().first()
        assert stale is not None
        assert stale.active is False
```

> **Note on fixtures.** The `session_factory` fixture should be defined in your `tests/conftest.py` (was set up in P0). It should return an async session_factory bound to an in-memory SQLite with the full schema applied. If P0's conftest doesn't provide that exact fixture, adjust naming or add it. The pattern:
> ```python
> @pytest_asyncio.fixture
> async def session_factory():
>     engine = create_async_engine("sqlite+aiosqlite:///:memory:")
>     async with engine.begin() as conn:
>         await conn.run_sync(Base.metadata.create_all)
>     factory = async_sessionmaker(engine, expire_on_commit=False)
>     yield factory
>     await engine.dispose()
> ```

### 2.8.3 `test_account_sync.py`

```python
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.db.models.account import Account
from app.db.models.account_state import AccountState
from app.events.bus import EventBus
from app.services.account_sync import AccountSyncService


@pytest.fixture
def mock_adapter_paper():
    a = MagicMock()
    a.is_paper = True
    a.get_account.return_value = {
        "status": "ACTIVE",
        "cash": "50000.00",
        "equity": "98750.42",
        "last_equity": "100000.00",
        "buying_power": "150000.00",
        "portfolio_value": "98750.42",
        "daytrade_count": 0,
        "pattern_day_trader": False,
        "trading_blocked": False,
        "account_blocked": False,
    }
    return a


@pytest.mark.asyncio
async def test_account_sync_upserts_state(session_factory, mock_adapter_paper):
    # Seed the paper account row
    async with session_factory() as session:
        session.add(Account(id=1, user_id=1, broker="alpaca", mode="paper", label="Paper"))
        await session.commit()

    bus = EventBus()
    svc = AccountSyncService(mock_adapter_paper, session_factory, bus)
    payload = await svc.sync_once()

    assert payload["status"] == "ACTIVE"
    assert payload["equity"] == Decimal("98750.42")
    assert payload["day_change"] == Decimal("-1249.58")

    async with session_factory() as session:
        state = (await session.execute(select(AccountState))).scalars().first()
        assert state is not None
        assert state.account_id == 1
        assert state.status == "ACTIVE"


@pytest.mark.asyncio
async def test_account_sync_idempotent(session_factory, mock_adapter_paper):
    async with session_factory() as session:
        session.add(Account(id=1, user_id=1, broker="alpaca", mode="paper", label="Paper"))
        await session.commit()

    bus = EventBus()
    svc = AccountSyncService(mock_adapter_paper, session_factory, bus)
    await svc.sync_once()
    await svc.sync_once()
    await svc.sync_once()

    async with session_factory() as session:
        rows = (await session.execute(select(AccountState))).scalars().all()
        assert len(rows) == 1  # unique constraint on account_id
```

### 2.8.4 `test_position_sync.py`

```python
from unittest.mock import MagicMock

import pytest

from app.events.bus import EventBus
from app.services.position_sync import PositionSyncService


@pytest.fixture
def mock_adapter():
    a = MagicMock()
    a.get_positions.return_value = [
        {"symbol": "AAPL", "qty": "10", "avg_entry_price": "190.50", "side": "long",
         "market_value": "1950.00", "cost_basis": "1905.00", "unrealized_pl": "45.00",
         "unrealized_plpc": "0.0236", "current_price": "195.00", "lastday_price": "194.00",
         "change_today": "0.005", "asset_class": "us_equity"},
    ]
    return a


@pytest.mark.asyncio
async def test_position_sync_publishes_snapshot(mock_adapter):
    bus = EventBus()
    received = []
    async def on_event(payload):
        received.append(payload)
    bus.subscribe("positions.snapshot", on_event)

    svc = PositionSyncService(mock_adapter, bus)
    result = await svc.sync_once()

    assert len(result) == 1
    assert result[0]["symbol"] == "AAPL"
    assert result[0]["qty"] == "10"

    # Give the event loop a tick to deliver the published event
    import asyncio
    await asyncio.sleep(0)
    assert len(received) == 1
    assert received[0]["count"] == 1
```

Run all tests:

```bash
cd apps/backend
uv run pytest -q
cd ../..
```

- [ ] All four test files created.
- [ ] All tests pass.
- [ ] Existing Session 1 + P0 tests still pass.

---

## §2.9 — Manual Smoke Against Alpaca Paper

Re-run the live smoke now that the lifespan owns the adapter:

```bash
# Terminal 1
./scripts/dev.sh           # or `docker compose up`

# Wait ~30 seconds, then check the backend logs:
docker compose logs backend | tail -50
```

Expected lines (interleaved with normal request/heartbeat noise):
- `alpaca_connected_at_startup paper=True`
- `asset_sync_completed count_total=5000+`
- `account_sync_completed status=ACTIVE equity=...`
- `position_sync_completed count=0` (or non-zero if you have paper positions)
- `scheduler_started`

Wait another 20 seconds during regular market hours (or 70 seconds off-hours) and confirm a *second* `account_sync_completed` and `position_sync_completed` appear, proving the schedule is ticking.

In the SQLite DB:

```bash
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "SELECT count(*) AS n_symbols FROM symbols WHERE active=1;"
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "SELECT status, equity, updated_at FROM accounts_state;"
```

Expected: thousands of active symbols, one row in `accounts_state` with status ACTIVE and a recent timestamp.

- [ ] Live smoke shows both initial and periodic syncs.
- [ ] `symbols` table has thousands of active rows.
- [ ] `accounts_state` has one row, status ACTIVE, recent `updated_at`.

```bash
docker compose down
```

---

## §2.10 — Commit and PR

```bash
git add apps/backend/app/db/models/account_state.py
git add apps/backend/app/db/models/__init__.py
git add apps/backend/alembic/versions/
git add apps/backend/app/services/
git add apps/backend/app/lifespan.py
git add apps/backend/app/main.py
git add apps/backend/tests/services/

git status   # sanity-check

git commit -m "feat(services): asset sync, account/position polling, scheduler, lifespan

- accounts_state cache table with Alembic migration
- AssetSyncService: daily upsert of Alpaca's US-equity universe into symbols
- AccountSyncService: poll get_account() and upsert accounts_state
- PositionSyncService: poll get_positions() and publish snapshot (no DB yet)
- WorkbenchScheduler: AsyncIOScheduler with market-hours throttling
- FastAPI lifespan wires it all into startup/shutdown
- Market hours helper for US/Eastern session detection
- Tests for each service with mocked adapter + in-memory SQLite

Deferred: Trade Updates WS lifecycle and reconciliation drift land in
P1 Session 3. Position DB persistence lands in P1 Session 4."

git push -u origin feat/p1-asset-account-position-sync

gh pr create \
  --title "feat(services): asset sync, account/position polling, scheduler, lifespan" \
  --body "P1 Session 2 deliverable. Brings the Alpaca adapter alive with scheduled background work.

**In scope:** daily asset sync, account snapshot polling, position polling (events only), scheduler, lifespan.

**Out of scope (P1 Session 3):** Trade Updates WS lifecycle, reconciliation drift detection.

**Out of scope (P1 Session 4):** Position DB persistence (waits for the positions table)."

gh pr checks
```

Wait for all 6 CI jobs to pass, then merge:

```bash
gh pr merge --merge --delete-branch
git checkout main && git pull
```

- [ ] PR opened, CI green, merged, branch deleted.
- [ ] `git pull` brings the change down.

---

## Verification Checklist (full session)

- [ ] §2.1 `accounts_state` table created via migration; round-trips downgrade/upgrade.
- [ ] §2.2 `market_hours.py` provides `is_regular_session` / `is_extended_session` / `session_label`.
- [ ] §2.3 `AssetSyncService.sync_once()` upserts rows from a mocked Alpaca asset list; deactivates removed rows.
- [ ] §2.4 `AccountSyncService.sync_once()` upserts a single `accounts_state` row keyed by `account_id`.
- [ ] §2.5 `PositionSyncService.sync_once()` publishes `positions.snapshot` events.
- [ ] §2.6 `WorkbenchScheduler` registers three jobs; throttles to 60s off-hours.
- [ ] §2.7 `lifespan` connects adapter → starts scheduler → runs startup sync → cleanly shuts down.
- [ ] §2.7.1 Local smoke shows the full startup log sequence.
- [ ] §2.8 All new test files pass; existing tests still pass.
- [ ] §2.9 Live smoke against Alpaca paper shows initial + periodic syncs; `symbols` and `accounts_state` populated.
- [ ] §2.10 PR merged on `main` via the protected workflow.

---

## Sign-off

```bash
git tag -a p1-session2-complete -m "P1 Session 2 complete: asset sync, account/position polling, scheduler, lifespan"
git push origin p1-session2-complete
```

Update `todo.md` to reflect Session 2 done; tee up Session 3 (Trade Updates WS lifecycle + reconciliation drift).

---

## Notes & Gotchas

1. **`Symbol` model column names.** If P0's schema used `is_active` instead of `active`, or different exchange/asset_class field types, the upsert in `asset_sync.py` will silently misbehave. Always cross-check against `.schema symbols`.

2. **`sqlite_insert`'s `on_conflict_do_update`** is dialect-specific. When (later) we move to PostgreSQL, switch to `from sqlalchemy.dialects.postgresql import insert as pg_insert` — same API. Don't import the generic `insert` and try to chain `on_conflict_do_update`; it doesn't exist there.

3. **`pattern_day_trader` and `trading_blocked` are booleans in Alpaca's API**, but Alpaca occasionally returns them as strings. The `bool(raw.get(...) or False)` in `_normalize_account` handles strings safely because non-empty strings are truthy in Python. If you ever see `pattern_day_trader=True` for an account that isn't, change to `str(raw.get(...)).lower() in ("true","1","yes")`.

4. **alpaca-py is sync.** All adapter methods block. The services call them from coroutines without `run_in_executor`, which is fine for one-off ticks every 10s but would be a problem under high load. If we ever see scheduler ticks delayed, the fix is to wrap adapter calls in `asyncio.get_running_loop().run_in_executor(None, ...)`. Not needed for MVP cadence.

5. **APScheduler tick overlap.** If a sync_once() ever takes longer than its interval, APScheduler's default behavior is to fire the next instance anyway (max_instances=1 by default actually skips, but check your apscheduler version). For belt-and-suspenders, you can pass `max_instances=1` to `add_job`. We're not bothering for MVP because polls are sub-second under normal conditions.

6. **Off-hours throttling math.** `_OFFHOURS_THROTTLE=6` with a 10s interval means: poll every 60s off-hours. If you want every 30s off-hours instead, set to 3. If you want different cadences for account vs. position, give each its own constant.

7. **Initial startup sync errors don't abort startup.** Each call inside `run_startup_sync` is in its own try/except. Rationale: a transient Alpaca issue at boot shouldn't make the backend unreachable for diagnostics. If you want hard-fail behavior in CI, set `WORKBENCH_STARTUP_STRICT=1` and check it in `lifespan` (not implemented here; add it if pain warrants).

8. **`get_event_bus()` and `get_session_factory()`.** I'm assuming P0 set these up as module-level singleton accessors. If P0 instead uses dependency-injected sessions everywhere (which would be cleaner for tests but more work in lifespan), the cleanest fix is to expose a module-level `get_session_factory()` that returns the same `async_sessionmaker` instance the FastAPI deps use. Don't create a separate engine; that'd give you two connection pools and gnarly debugging later.

9. **Don't start Session 3 mid-session.** TradeUpdatesStream is tempting because the skeleton is already there — but wiring it through the lifespan, debugging its idiosyncratic alpaca-py asyncio behavior, and adding the drift detector is a separate ~2-hour block. Stop after this PR merges.

10. **`accounts_state` updates are append-then-merge, not append-only.** If you ever want a full history of equity over time (for a daily P&L chart), add a separate `accounts_state_history` table later — don't change this one to append-only, the upsert pattern is correct for the live snapshot.

---

*End of P1 Session 2 v0.1.*
