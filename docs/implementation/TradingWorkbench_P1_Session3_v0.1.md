# P1 Session 3 — Trade Updates WebSocket Lifecycle

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-20 |
| Phase | **P1**, **§1.4 WS subscription only** |
| Predecessor | *TradingWorkbench_P1_Session2_v0.1.md* (tag `p1-session2-complete`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | Bring the `TradeUpdatesStream` skeleton from Session 1 to life. Subscribe to Alpaca's Trade Updates WebSocket, run it as a background task inside the FastAPI event loop, publish raw events to the in-process event bus, monitor connection health. |
| Estimated wall time | 2–3 hours |
| Stopping point | `git tag p1-session3-complete` |
| Explicitly deferred | Translating trade-update events into internal `Order` / `Fill` rows (waits for Session 4's DB schema). Reconciliation drift detection (moves to Session 5 alongside Risk Engine + Order Router). |

---

## Session Goal

After this session:
- `TradeUpdatesStream.start()` / `stop()` are real implementations, no longer `NotImplementedError`.
- The stream runs as a background asyncio task spawned by the FastAPI lifespan.
- Every trade update from Alpaca lands on the in-process event bus as `alpaca.trade_update` with a normalized payload.
- A connection-health signal is exposed (`is_started`, `last_message_at`) and published to the bus as `alpaca.stream_status` on state changes.
- A manual smoke (placing a small paper order **via curl directly against Alpaca**, *not* via our app — see §3.4) produces visible trade-update log lines in the backend.
- Unit tests cover the handler logic and lifecycle wiring with a mocked `TradingStream`.

What does **not** happen this session:
- No translation from `alpaca.trade_update` → internal `Order`/`Fill` records. That's Session 4 once the `orders` / `fills` tables exist.
- No `OrderRouter`. Still no path that submits orders from our app code.
- No reconciliation drift logic. That waits until Session 5 where it can compare across the full local order/position state.

---

## Prerequisites Check

```bash
cd ~/code/AI-TRADING-APP
git status                                # clean
git pull origin main
git describe --tags --abbrev=0            # expect: p1-session2-complete

# Confirm Session 2 scheduler is alive end-to-end
./scripts/dev.sh &
sleep 25
docker compose logs backend | grep -E "scheduler_started|account_sync_completed|asset_sync_completed" | head
docker compose down
```

You should see all three lines from Session 2's lifespan startup. If you don't, fix Session 2 issues first.

- [ ] On `main`, clean tree, at `p1-session2-complete` or later.
- [ ] Session 2 background services boot cleanly.

Cut the feature branch:

```bash
git checkout -b feat/p1-trade-updates-stream
```

---

## §3.1 — Expose Credentials from `AlpacaAdapter`

`TradeUpdatesStream` needs the credentials to open its own WebSocket connection. Rather than re-loading them from env (which works but couples the stream to the env layout), expose a read-only property on the adapter.

Edit `apps/backend/app/brokers/alpaca/adapter.py`. Add this property after `is_connected`:

```python
@property
def credentials(self) -> AlpacaCredentials:
    """Read-only access to the credentials this adapter was constructed with.

    Used by TradeUpdatesStream to open its own WS connection without
    re-resolving env vars (and to avoid drift if env changes mid-run).
    """
    return self._creds
```

Then add an import at the top of the same file if it's not already there:

```python
from .credentials import AlpacaCredentials, load_credentials  # noqa: F401  -- AlpacaCredentials used by typing
```

Update the `__all__` export in `apps/backend/app/brokers/alpaca/__init__.py` if you want to be explicit:

```python
__all__ = [
    "AlpacaAdapter",
    "AlpacaCredentials",
    "load_credentials",
    "AlpacaError",
    "TransientAlpacaError",
    "PermanentAlpacaError",
    "classify",
    "TradeUpdatesStream",      # NEW
]

from .streaming import TradeUpdatesStream  # NEW
```

- [ ] `credentials` property added.
- [ ] `TradeUpdatesStream` exported from package `__init__`.

---

## §3.2 — Implement `TradeUpdatesStream`

Replace the entire body of `apps/backend/app/brokers/alpaca/streaming.py` with the working implementation. The skeleton's `NotImplementedError` placeholders go away.

```python
"""Alpaca Trade Updates streaming.

Subscribes to Alpaca's WebSocket for order/fill events and forwards each one
to the in-process event bus on topic ``alpaca.trade_update`` with a normalized
payload.

Design notes:

* alpaca-py's ``TradingStream`` exposes both a sync ``run()`` (which internally
  calls ``asyncio.run``) and an async ``_run_forever`` coroutine. We use the
  async path so we can run inside the FastAPI event loop without spawning a
  thread.
* alpaca-py handles reconnects internally for transient socket failures. We do
  NOT add a second layer of supervision; we just log connection state.
* No translation from raw events to internal Order/Fill records happens here.
  Session 4 adds an EventBus subscriber that does that translation once the
  DB schema for orders/fills exists.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import structlog

from app.events.bus import EventBus

from .credentials import AlpacaCredentials

logger = structlog.get_logger(__name__)


class TradeUpdatesStream:
    """Long-running subscriber to Alpaca's Trade Updates WebSocket."""

    def __init__(
        self,
        credentials: AlpacaCredentials,
        bus: EventBus,
    ) -> None:
        self._creds = credentials
        self._bus = bus
        self._stream: Any = None        # alpaca.trading.stream.TradingStream
        self._task: asyncio.Task | None = None
        self._started: bool = False
        self._last_message_at: datetime | None = None
        self._stopping: bool = False

    # ---- public surface ----

    @property
    def is_started(self) -> bool:
        return self._started

    @property
    def last_message_at(self) -> datetime | None:
        return self._last_message_at

    async def start(self) -> None:
        """Open the WS connection and start the background loop.

        Idempotent: calling start() twice is a no-op after the first.
        """
        if self._started:
            logger.debug("trade_updates_stream_already_started")
            return

        # Lazy import to keep alpaca-py out of import-time dep graph
        from alpaca.trading.stream import TradingStream

        self._stream = TradingStream(
            api_key=self._creds.api_key,
            secret_key=self._creds.api_secret,
            paper=self._creds.paper,
        )
        # Register our async handler. alpaca-py expects a coroutine function.
        self._stream.subscribe_trade_updates(self._handle_update)

        # Start the underlying run loop as a background task.
        # _run_forever is an alpaca-py internal but it's the right entry point
        # for embedding the stream into an existing asyncio event loop.
        self._task = asyncio.create_task(
            self._run_forever_supervised(),
            name="alpaca-trade-updates",
        )
        self._started = True
        logger.info("trade_updates_stream_started", paper=self._creds.paper)
        await self._publish_status("started")

    async def stop(self) -> None:
        """Stop the background loop and close the WS connection."""
        if not self._started:
            return
        self._stopping = True
        try:
            if self._stream is not None:
                # alpaca-py's TradingStream has both stop() and stop_ws();
                # use whichever is present.
                if hasattr(self._stream, "stop_ws"):
                    await _maybe_await(self._stream.stop_ws())
                elif hasattr(self._stream, "stop"):
                    await _maybe_await(self._stream.stop())
        except Exception:  # noqa: BLE001
            logger.exception("trade_updates_stream_stop_ws_error")
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._task = None
        self._stream = None
        self._started = False
        logger.info("trade_updates_stream_stopped")
        await self._publish_status("stopped")

    # ---- internals ----

    async def _run_forever_supervised(self) -> None:
        """Run alpaca-py's stream loop and translate exits to log lines.

        alpaca-py handles its own per-message reconnects. If the entire loop
        ever returns or raises, we log it; the caller (lifespan) can decide
        whether to restart the whole stream.
        """
        try:
            # _run_forever is the underlying coroutine on TradingStream.
            # If alpaca-py renames this, update the line below.
            await self._stream._run_forever()
        except asyncio.CancelledError:
            logger.info("trade_updates_stream_cancelled")
            raise
        except Exception:  # noqa: BLE001
            logger.exception("trade_updates_stream_loop_crashed")
            await self._publish_status("crashed")
            self._started = False

    async def _handle_update(self, data: Any) -> None:
        """alpaca-py invokes this for every trade update payload."""
        self._last_message_at = datetime.now(timezone.utc)
        payload = _normalize_trade_update(data)
        logger.info(
            "trade_update_received",
            event=payload.get("event"),
            symbol=payload.get("symbol"),
            broker_order_id=payload.get("broker_order_id"),
        )
        await self._bus.publish("alpaca.trade_update", payload)

    async def _publish_status(self, status: str) -> None:
        try:
            await self._bus.publish(
                "alpaca.stream_status",
                {
                    "status": status,
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "paper": self._creds.paper,
                },
            )
        except Exception:  # noqa: BLE001
            logger.exception("trade_updates_stream_publish_status_failed")


# ---- helpers ----


async def _maybe_await(maybe_coro: Any) -> None:
    """alpaca-py's stop methods sometimes return None, sometimes a coroutine."""
    if asyncio.iscoroutine(maybe_coro):
        await maybe_coro


def _normalize_trade_update(data: Any) -> dict[str, Any]:
    """Map alpaca-py's TradeUpdate object (or dict) to a stable shape.

    The fields we publish are the ones Session 4's OrderRouter lifecycle will
    consume to update local Order/Fill rows. Keep this surface narrow on
    purpose; preserve the full original payload under ``raw`` for forensics.
    """
    # alpaca-py >= 0.30 emits objects with .event, .order, .execution_id, etc.
    # Older versions or dict messages: tolerate both.
    if hasattr(data, "model_dump"):
        raw = data.model_dump(mode="json")
    elif isinstance(data, dict):
        raw = data
    else:
        raw = {k: getattr(data, k, None) for k in (
            "event", "order", "execution_id", "qty", "price",
            "position_qty", "timestamp",
        )}

    order = raw.get("order") or {}
    return {
        "event": raw.get("event"),  # "new", "fill", "partial_fill", "canceled", "expired", "rejected", ...
        "broker_order_id": (order.get("id") if isinstance(order, dict) else None),
        "client_order_id": (order.get("client_order_id") if isinstance(order, dict) else None),
        "symbol": (order.get("symbol") if isinstance(order, dict) else None),
        "side": (order.get("side") if isinstance(order, dict) else None),
        "order_status": (order.get("status") if isinstance(order, dict) else None),
        "execution_id": raw.get("execution_id"),
        "qty": raw.get("qty"),
        "price": raw.get("price"),
        "position_qty": raw.get("position_qty"),
        "timestamp": raw.get("timestamp"),
        "raw": raw,
    }
```

- [ ] `streaming.py` replaced; no more `NotImplementedError`.

---

## §3.3 — Wire `TradeUpdatesStream` into the Lifespan

Extend `apps/backend/app/lifespan.py` from Session 2 to also start/stop the stream.

Find the lifespan function and adjust as follows. The full edited version:

```python
"""FastAPI lifespan wiring for background services.

Startup:
  1. Instantiate AlpacaAdapter and connect (fail-fast if creds are wrong).
  2. Instantiate the three sync services.
  3. Instantiate the scheduler, register jobs, start it.
  4. Run the startup sync pass.
  5. Start the TradeUpdatesStream as a background task.   <-- NEW

Shutdown:
  1. Stop the TradeUpdatesStream.                          <-- NEW
  2. Stop the scheduler.
  3. Disconnect the adapter.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI

from app.brokers.alpaca import AlpacaAdapter, TradeUpdatesStream
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
    trade_stream: TradeUpdatesStream | None = None

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

        # NEW: Trade Updates WebSocket
        trade_stream = TradeUpdatesStream(adapter.credentials, bus)
        await trade_stream.start()

        app.state.alpaca_adapter = adapter
        app.state.asset_sync = asset_sync
        app.state.account_sync = account_sync
        app.state.position_sync = position_sync
        app.state.scheduler = scheduler
        app.state.trade_stream = trade_stream      # NEW

        await scheduler.run_startup_sync()

        logger.info("lifespan_startup_complete")
        yield
    finally:
        logger.info("lifespan_shutdown_begin")
        # Stop the stream BEFORE the scheduler so any final trade-update events
        # don't race in after services have torn down their session factory.
        if trade_stream is not None:
            try:
                await trade_stream.stop()
            except Exception:
                logger.exception("trade_stream_stop_failed")
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

Diff vs. the Session 2 version: three additions (the import, the construction + `await start()`, and `app.state.trade_stream`), plus the `await trade_stream.stop()` block in the `finally`.

- [ ] `lifespan.py` updated.
- [ ] `trade_stream` constructed AFTER scheduler.start() and BEFORE startup sync.
- [ ] Shutdown stops stream BEFORE scheduler.

---

## §3.4 — Manual Smoke Against Alpaca Paper

To verify the stream end-to-end we need to *cause* a trade update to fire. Since our app doesn't yet have an `OrderRouter` (lands in Session 5 alongside the Risk Engine), we generate the trade update by hitting Alpaca's REST API directly with `curl`.

> **ADR 0002 note.** This is NOT a violation. ADR 0002 governs how *our application code* may submit orders — exclusively through `OrderRouter`. Running `curl` from a developer terminal during a smoke test is external instrumentation, not application code. There is no codepath in the Workbench that submits orders at this point; the smoke is deliberately bypassing the *absent* path to validate the stream.

### Step 1 — Boot the backend

```bash
./scripts/dev.sh &
sleep 30
docker compose logs backend | grep -E "trade_updates_stream_started|scheduler_started"
```

Expect to see `trade_updates_stream_started paper=True`.

### Step 2 — Place a 1-share paper order via curl

```bash
set -a; source .env; set +a

# Pick a low-priced symbol so the smoke isn't expensive on paper buying power
SYMBOL="F"   # Ford, typically $10-15 on paper

curl -s -X POST https://paper-api.alpaca.markets/v2/orders \
  -H "APCA-API-KEY-ID: $ALPACA_PAPER_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_PAPER_API_SECRET" \
  -H "Content-Type: application/json" \
  -d "{
    \"symbol\": \"$SYMBOL\",
    \"qty\": 1,
    \"side\": \"buy\",
    \"type\": \"market\",
    \"time_in_force\": \"day\"
  }" | jq '{id, status, symbol, qty, type}'
```

### Step 3 — Watch the backend logs

Within a few seconds, the backend logs should show:

```
trade_update_received event=new symbol=F broker_order_id=...
trade_update_received event=fill symbol=F broker_order_id=... (during regular hours)
```

If market is closed, you'll see `event=new` and `event=accepted` and the fill arrives at next market open. For an immediate fill, run this during regular hours (09:30–16:00 ET, Mon–Fri).

```bash
docker compose logs backend --tail=50 | grep trade_update_received
```

### Step 4 — Clean up (optional)

If the order didn't fill yet, cancel it so it doesn't accidentally execute later:

```bash
curl -X DELETE https://paper-api.alpaca.markets/v2/orders \
  -H "APCA-API-KEY-ID: $ALPACA_PAPER_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_PAPER_API_SECRET"
# cancels ALL open orders on the paper account
```

Or close any position that opened:

```bash
curl -X DELETE https://paper-api.alpaca.markets/v2/positions \
  -H "APCA-API-KEY-ID: $ALPACA_PAPER_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_PAPER_API_SECRET"
```

```bash
docker compose down
```

- [ ] `trade_updates_stream_started` appears in the backend logs at boot.
- [ ] curl POST to Alpaca returns a valid order JSON.
- [ ] At least one `trade_update_received` line appears in the backend logs within ~10 seconds.
- [ ] Open positions / orders cleaned up on the Alpaca paper account.

---

## §3.5 — Tests

Create `apps/backend/tests/brokers/alpaca/test_streaming.py`:

```python
"""Tests for TradeUpdatesStream lifecycle and event-bus forwarding."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.brokers.alpaca.credentials import AlpacaCredentials
from app.brokers.alpaca.streaming import (
    TradeUpdatesStream,
    _normalize_trade_update,
)
from app.events.bus import EventBus


@pytest.fixture
def creds():
    return AlpacaCredentials(api_key="PK_TEST", api_secret="SECRET_TEST", paper=True)


# ---- _normalize_trade_update ----


def test_normalize_handles_dict_payload():
    data = {
        "event": "fill",
        "order": {"id": "abc-123", "symbol": "AAPL", "side": "buy", "status": "filled"},
        "execution_id": "exec-1",
        "qty": "1",
        "price": "190.50",
        "position_qty": "1",
        "timestamp": "2026-05-19T10:00:00Z",
    }
    out = _normalize_trade_update(data)
    assert out["event"] == "fill"
    assert out["broker_order_id"] == "abc-123"
    assert out["symbol"] == "AAPL"
    assert out["side"] == "buy"
    assert out["qty"] == "1"
    assert out["price"] == "190.50"
    assert out["raw"] == data


def test_normalize_handles_object_with_model_dump():
    obj = MagicMock()
    obj.model_dump = MagicMock(return_value={
        "event": "new",
        "order": {"id": "x-1", "symbol": "MSFT", "side": "sell", "status": "new"},
    })
    out = _normalize_trade_update(obj)
    assert out["event"] == "new"
    assert out["broker_order_id"] == "x-1"
    assert out["symbol"] == "MSFT"


def test_normalize_handles_missing_order():
    data = {"event": "trade_update_lol", "execution_id": "e", "qty": None}
    out = _normalize_trade_update(data)
    assert out["event"] == "trade_update_lol"
    assert out["broker_order_id"] is None
    assert out["symbol"] is None


# ---- lifecycle ----


@pytest.mark.asyncio
async def test_start_is_idempotent(creds):
    bus = EventBus()
    stream = TradeUpdatesStream(creds, bus)

    with patch("alpaca.trading.stream.TradingStream") as MockTS:
        instance = MagicMock()
        # _run_forever is awaited in a background task — return an awaitable
        # that hangs until cancelled
        async def _hang():
            await asyncio.sleep(3600)
        instance._run_forever = _hang
        MockTS.return_value = instance

        await stream.start()
        assert stream.is_started is True
        await stream.start()   # second call is a no-op
        # subscribe_trade_updates should have been called exactly once
        assert instance.subscribe_trade_updates.call_count == 1

        await stream.stop()
        assert stream.is_started is False


@pytest.mark.asyncio
async def test_handle_update_publishes_to_bus(creds):
    bus = EventBus()
    received = []
    async def on_event(payload):
        received.append(payload)
    bus.subscribe("alpaca.trade_update", on_event)

    stream = TradeUpdatesStream(creds, bus)
    fake_payload = {
        "event": "fill",
        "order": {"id": "ord-99", "symbol": "F", "side": "buy", "status": "filled"},
        "execution_id": "e-1",
        "qty": "1",
        "price": "12.34",
    }
    await stream._handle_update(fake_payload)
    # Let the bus deliver
    await asyncio.sleep(0)
    assert len(received) == 1
    assert received[0]["event"] == "fill"
    assert received[0]["broker_order_id"] == "ord-99"
    assert received[0]["symbol"] == "F"
    assert stream.last_message_at is not None


@pytest.mark.asyncio
async def test_status_event_published_on_start_stop(creds):
    bus = EventBus()
    statuses = []
    async def on_status(payload):
        statuses.append(payload["status"])
    bus.subscribe("alpaca.stream_status", on_status)

    with patch("alpaca.trading.stream.TradingStream") as MockTS:
        instance = MagicMock()
        async def _hang():
            await asyncio.sleep(3600)
        instance._run_forever = _hang
        MockTS.return_value = instance

        stream = TradeUpdatesStream(creds, bus)
        await stream.start()
        await stream.stop()

    await asyncio.sleep(0)
    assert "started" in statuses
    assert "stopped" in statuses


@pytest.mark.asyncio
async def test_stop_without_start_is_noop(creds):
    bus = EventBus()
    stream = TradeUpdatesStream(creds, bus)
    # Should not raise
    await stream.stop()
    assert stream.is_started is False
```

Run all backend tests:

```bash
cd apps/backend
uv run pytest -q
cd ../..
```

- [ ] `test_streaming.py` created.
- [ ] All new tests pass.
- [ ] All Session 1 + Session 2 tests still pass.

---

## §3.6 — Commit and PR

```bash
git add apps/backend/app/brokers/alpaca/adapter.py
git add apps/backend/app/brokers/alpaca/streaming.py
git add apps/backend/app/brokers/alpaca/__init__.py
git add apps/backend/app/lifespan.py
git add apps/backend/tests/brokers/alpaca/test_streaming.py

git commit -m "feat(brokers): trade updates websocket lifecycle

- TradeUpdatesStream.start/stop fully implemented (was NotImplementedError)
- Runs alpaca-py TradingStream._run_forever as a supervised asyncio task
- Forwards trade updates to EventBus on topic 'alpaca.trade_update'
- Publishes lifecycle state on 'alpaca.stream_status' (started/stopped/crashed)
- AlpacaAdapter.credentials property added for stream construction
- FastAPI lifespan starts the stream after the scheduler, stops it first on shutdown
- Tests cover normalization, idempotent start, bus forwarding, status events

Deferred: trade-update -> Order/Fill row translation lands in Session 4
once the orders/fills DB tables exist. Reconciliation drift moves to
Session 5 alongside Risk Engine + Order Router."

git push -u origin feat/p1-trade-updates-stream

gh pr create \
  --title "feat(brokers): trade updates websocket lifecycle" \
  --body "P1 Session 3 deliverable. Brings TradeUpdatesStream from skeleton to working background task.

**In scope:** stream lifecycle, event-bus forwarding, lifespan integration, tests.

**Out of scope (Session 4):** translation of raw trade updates into internal Order/Fill records.

**Out of scope (Session 5):** reconciliation drift detection."

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

- [ ] §3.1 `AlpacaAdapter.credentials` property exposed; `TradeUpdatesStream` re-exported from `brokers/alpaca/__init__.py`.
- [ ] §3.2 `streaming.py` implemented: `start()` idempotent, `stop()` safe, handler publishes to bus, status events emitted.
- [ ] §3.3 `lifespan.py` starts the stream after scheduler, stops it before scheduler on shutdown.
- [ ] §3.4 Manual smoke: curl-placed paper order causes `trade_update_received` log lines.
- [ ] §3.4 Open paper positions / orders cleaned up after smoke.
- [ ] §3.5 All new and existing tests pass.
- [ ] §3.6 PR merged on `main` via the protected workflow.

---

## Sign-off

```bash
git tag -a p1-session3-complete -m "P1 Session 3 complete: trade updates websocket lifecycle"
git push origin p1-session3-complete
```

Update `todo.md`:
- Mark Session 3 complete.
- Tee up **P1 Session 4 — Trading DB Schema** (orders, fills, positions, risk_limits, risk_checks tables + enums + migration + seed risk limits).

---

## Notes & Gotchas

1. **`_run_forever` is an alpaca-py internal.** It's the only practical entry point for embedding their stream in an existing asyncio loop. If alpaca-py renames or removes it in a future minor release, this is the line that will break:
   ```python
   await self._stream._run_forever()
   ```
   When it breaks, the alternative is to spawn a thread that runs `self._stream.run()` and use `asyncio.run_coroutine_threadsafe` to publish into the bus. Slightly worse ergonomics but more stable.

2. **alpaca-py's reconnect behavior.** The library handles transient socket failures internally and you'll see brief "reconnecting" log lines from it. We don't need to react. If the entire run loop ever *returns* (vs. raises), `_run_forever_supervised` catches it and emits `stream_status=crashed` but does NOT auto-restart — restarting from inside the supervisor invites tight crash loops. If you want auto-restart, the right place is in the lifespan, not here. P4 polish.

3. **Stream events arrive in the lifespan's event loop.** Because we `await stream.start()` inside `lifespan()` and use `asyncio.create_task`, the task runs in the FastAPI event loop. The `await self._bus.publish(...)` call therefore runs in the same loop the WS gateway is using — no thread-safety concerns. If you ever move the stream into a separate thread (gotcha #1), this changes and you'll need `loop.call_soon_threadsafe` or `run_coroutine_threadsafe`.

4. **Smoke order should be the smallest possible quantity.** 1 share of a low-priced symbol is intentional. The Alpaca paper account has $100k by default but it's still worth being economical — avoids confusing equity drift across smokes.

5. **Outside market hours, `event=fill` will not arrive.** You'll see `event=new` and possibly `event=accepted`. The fill arrives at next market open. If you need a deterministic fill for testing, use a marketable limit order during regular hours, or use Alpaca's `extended_hours: true` flag with `type: limit`.

6. **The `raw` field in normalized payloads is the full Alpaca object.** It's there for forensics — if Session 4's translator code finds a payload it doesn't recognize, it can dump `raw` to the audit log without losing information. Don't drop the `raw` field to save space; the payloads are small.

7. **`AlpacaCredentials` is frozen.** Constructed once in the adapter; the stream gets the same instance via `adapter.credentials`. Don't try to mutate it; the dataclass is `frozen=True`. If you ever need to rotate credentials at runtime, that's a `disconnect → re-construct adapter → reconnect` cycle, not an in-place mutation.

8. **Don't start Session 4 mid-session.** The `orders` and `fills` tables will be tempting because they're the natural consumers of the trade-update events you can now see flowing. But designing five tables and writing the migration is a focused unit by itself — keep it for Session 4. The events being received and then ignored is fine for a sleep cycle.

9. **`gh pr checks` may show CI passing before the smoke is done.** CI doesn't run the live Alpaca smoke. Do that locally before merging — the unit tests can pass while the live wiring is broken.

10. **If you don't see `trade_update_received` after the curl smoke** — check three things in order: (a) `trade_updates_stream_started` actually appeared at boot, (b) the curl POST returned a valid order JSON (not an auth error), (c) the backend container has the `ALPACA_PAPER_API_*` env vars (`docker compose exec backend env | grep ALPACA`). If all three are good and there's still no event, the stream's `_run_forever` may have crashed silently — check for `trade_updates_stream_loop_crashed` log lines.

---

*End of P1 Session 3 v0.1.*
