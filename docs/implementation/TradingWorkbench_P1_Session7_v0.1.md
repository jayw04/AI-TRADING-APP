# P1 Session 7 — Tests, Smoke Matrix, Runbooks, Exit Gate

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-20 |
| Phase | **P1**, **§10 (Tests + Smoke) + §11 (Documentation) + §12 (Exit Gate)** |
| Predecessor | *TradingWorkbench_P1_Session6_v0.1.md* (tag `p1-session6-complete`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | Close P1. (1) Backfill the test coverage that Sessions 5 + 6 deferred. (2) Add the CI guardrail enforcing ADR 0002 as a static + grep check. (3) Execute the formal six-step manual paper-trading smoke matrix. (4) Write the three runbook docs. (5) Walk the P1 exit gate, tag, and update todo.md. |
| Estimated wall time | 3–4 hours (single PR) |
| Stopping point | `git tag p1-complete` |
| Out of scope | Any new feature work. If you find a behavioral bug during smoke, fix it; if you find a missing feature, write it down for P4 and move on. |

---

## Session Goal

After this session:
- Backend test coverage gate is enforced: ≥ 80% overall, and the risk engine module specifically at ≥ 95% branch coverage (target 100%; one or two unreachable defensive lines acceptable). CI fails if either threshold drops.
- One end-to-end backend integration test exercises the full pipeline: ticket POST → router → risk → mocked-Alpaca submit → simulated trade-update → fill row → position update → audit row → WS event broadcast.
- Frontend has the three highest-value Vitest tests: order ticket happy path, order ticket risk-rejection rendering, live-mode confirmation flow.
- The CI grep tripwire from Session 5 §5.6 is wired into the GitHub Actions workflow as a required check.
- Six manual smoke steps from P1 Checklist §10.4 are executed against Alpaca paper and the results recorded in `docs/runbook/p1-smoke-log.md`.
- Three runbook docs exist: `live-mode.md`, `risk-limits.md`, `symbol-mapping-gaps.md` (the last one stays mostly empty for now; it's the place to log mismatches as they appear).
- `README.md` Quickstart section is updated to actually reflect the working system.
- `todo.md` is updated: P1 marked complete; P2 prereqs section written.
- `git tag p1-complete` is pushed.

What does NOT happen this session:
- No new feature work. If a smoke step fails because a feature is missing rather than broken, document it in P4 deferral notes; don't retrofit.
- No frontend E2E tests with Playwright. Per P1 Checklist §10.3, the Vitest unit tests are sufficient for the P1 exit gate; full Playwright matrices are P4 polish.
- No load testing. WebSocket fan-out stability under load is a P4 concern.

---

## Prerequisites Check

```bash
cd ~/code/AI-TRADING-APP
git status                                # clean
git pull origin main
git describe --tags --abbrev=0            # expect: p1-session6-complete

# Confirm the full stack still works end-to-end
./scripts/dev.sh &
sleep 30
curl -s http://127.0.0.1:8000/healthz | jq .
curl -s http://127.0.0.1:8000/api/v1/account | jq '{mode, status, equity}'

# Open the UI to make sure Session 6 work didn't regress
echo "Open http://localhost:5173/ in a browser — verify Dashboard renders real numbers"

docker compose down
```

- [ ] Clean tree at `p1-session6-complete` or later.
- [ ] Backend boots, API returns real account data, UI renders.

Cut the branch:

```bash
git checkout -b feat/p1-tests-smoke-exit
```

This session is one PR. Smaller than 5 / 6 because most of it is tests + docs + executable smoke steps, not new code.

---

## §7.1 — CI Coverage Gates

Coverage gates do two things: they enforce a floor *now*, and they fail any future PR that drops below the floor. Both Risk Engine specifically (the safety-critical path) and overall backend.

### 7.1.1 — Configure pytest-cov thresholds

Edit `apps/backend/pyproject.toml`. Find the `[tool.pytest.ini_options]` block (or add it) and ensure it has:

```toml
[tool.pytest.ini_options]
addopts = "-ra --strict-markers --cov=app --cov-report=term-missing --cov-report=xml"
asyncio_mode = "auto"
markers = [
    "integration: end-to-end tests that mock the Alpaca adapter but exercise the full pipeline",
]

[tool.coverage.run]
source = ["app"]
branch = true
omit = [
    "app/db/models/*",          # ORM model files — coverage is structural
    "app/__init__.py",
    "*/migrations/*",
    "*/alembic/*",
]

[tool.coverage.report]
fail_under = 80
exclude_lines = [
    "pragma: no cover",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
    "if TYPE_CHECKING:",
]
```

Then run the full suite locally to see the current number:

```bash
cd apps/backend
uv run pytest --cov-report=term
cd ../..
```

If overall coverage is below 80%, the gate would fail. Two responses:

- **If you're close (≥ 75%):** add the small handful of tests in §7.2 below; the integration test plus a few targeted unit tests usually nudges it over.
- **If you're far below (< 70%):** lower `fail_under` to the current floor (e.g. 70) for this PR, file a follow-up tracking issue to ratchet up to 80% in P4. The principle (ratcheting, never regressing) matters more than the absolute number.

### 7.1.2 — Add a Risk Engine–specific coverage check

Create `apps/backend/scripts/check_risk_coverage.py`:

```python
"""Fail CI if branch coverage on app/risk/engine.py drops below the threshold.

Reads coverage.xml (produced by pytest-cov), looks up the entry for
app/risk/engine.py, and exits non-zero if its branch-rate is below 0.95.

Risk Engine is the safety-critical path; every branch is meaningful.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

THRESHOLD = 0.95
TARGET_FILE = "app/risk/engine.py"


def main() -> int:
    coverage_xml = Path("coverage.xml")
    if not coverage_xml.exists():
        print(f"ERROR: {coverage_xml} not found. Run pytest --cov-report=xml first.", file=sys.stderr)
        return 2

    tree = ET.parse(coverage_xml)
    root = tree.getroot()

    for cls in root.iter("class"):
        filename = cls.get("filename", "")
        if filename.endswith(TARGET_FILE) or TARGET_FILE in filename:
            branch_rate = float(cls.get("branch-rate", "0"))
            line_rate = float(cls.get("line-rate", "0"))
            print(f"{filename}: branch-rate={branch_rate:.3f} line-rate={line_rate:.3f}")
            if branch_rate < THRESHOLD:
                print(
                    f"FAIL: branch coverage on {TARGET_FILE} is {branch_rate:.3f}, "
                    f"below required {THRESHOLD}",
                    file=sys.stderr,
                )
                return 1
            return 0

    print(f"ERROR: {TARGET_FILE} not found in coverage.xml", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] Coverage gate configured in `pyproject.toml`.
- [ ] Risk Engine–specific check script created.

---

## §7.2 — Backfill Backend Tests

Sessions 5 and 6 deferred most non-Risk-Engine tests to this session. The goal is to land just enough to clear the 80% gate, not to test every line — that's a non-goal for MVP. Three test files do most of the work.

### 7.2.1 — OrderRouter tests

Create `apps/backend/tests/orders/__init__.py` (empty), then `apps/backend/tests/orders/test_router.py`:

```python
"""OrderRouter unit tests with mocked AlpacaAdapter.

These cover the lifecycle paths that the live smoke can't easily trigger
deterministically (specifically transient errors and broker rejections).
The happy path is exercised by the §7.3 integration test and the §7.4
live smoke; we don't duplicate it here.
"""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.brokers.alpaca import PermanentAlpacaError, TransientAlpacaError
from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    RiskScopeType,
    TimeInForce,
)
from app.db.models.account import Account
from app.db.models.order import Order
from app.db.models.risk_limits import RiskLimits
from app.db.models.symbol import Symbol
from app.db.models.system_config import SystemConfig
from app.db.models.user import User
from app.events.bus import EventBus
from app.orders.router import OrderRouter
from app.risk import OrderRequest


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
        session.add(SystemConfig(user_id=1, key="mode", value="paper", updated_at=_now()))
        await session.commit()


def _req(**kw):
    base = dict(
        user_id=1, account_id=1, symbol_id=1, symbol="AAPL",
        side=OrderSide.BUY, qty=Decimal("1"),
        type=OrderType.MARKET, tif=TimeInForce.DAY,
        source_type=OrderSourceType.MANUAL,
        last_price=Decimal("190"),
    )
    base.update(kw)
    return OrderRequest(**base)


def _mock_adapter(submit_result=None, submit_raises=None):
    a = MagicMock()
    a.is_paper = True
    if submit_raises is not None:
        a.submit_order = MagicMock(side_effect=submit_raises)
    else:
        a.submit_order = MagicMock(return_value=submit_result or {"id": "abc-123"})
    a.cancel_order = MagicMock(return_value=None)
    a.replace_order = MagicMock(return_value={"id": "abc-123"})
    return a


@pytest.mark.asyncio
async def test_router_happy_path_writes_order_audit_and_calls_adapter(session_factory, seeded):
    adapter = _mock_adapter()
    router = OrderRouter(adapter, session_factory, EventBus())
    order = await router.submit(_req())

    assert order.status == OrderStatus.SUBMITTED
    assert order.broker_order_id == "abc-123"
    adapter.submit_order.assert_called_once()

    # Audit log must have at least ORDER_CREATED, ORDER_RISK_PASSED, ORDER_SUBMITTED
    async with session_factory() as session:
        from app.db.models.audit_log import AuditLog
        rows = (await session.execute(select(AuditLog).order_by(AuditLog.id))).scalars().all()
        actions = [r.action for r in rows]
        assert "order.created" in actions
        assert "order.risk_passed" in actions
        assert "order.submitted" in actions


@pytest.mark.asyncio
async def test_router_risk_rejection_never_calls_adapter(session_factory, seeded):
    adapter = _mock_adapter()
    router = OrderRouter(adapter, session_factory, EventBus())
    order = await router.submit(_req(qty=Decimal("99999")))  # blows the qty cap

    assert order.status == OrderStatus.REJECTED
    assert "POSITION_CAP_QTY" in (order.rejection_reason or "")
    adapter.submit_order.assert_not_called()


@pytest.mark.asyncio
async def test_router_permanent_broker_error_marks_order_rejected(session_factory, seeded):
    adapter = _mock_adapter(submit_raises=PermanentAlpacaError("insufficient funds"))
    router = OrderRouter(adapter, session_factory, EventBus())
    order = await router.submit(_req())

    assert order.status == OrderStatus.REJECTED
    assert "broker_error" in (order.rejection_reason or "")
    assert "insufficient funds" in (order.rejection_reason or "")


@pytest.mark.asyncio
async def test_router_transient_error_retries_then_succeeds(session_factory, seeded):
    # Fail twice with transient, succeed on third try.
    adapter = MagicMock()
    adapter.is_paper = True
    call_count = {"n": 0}
    def _fake_submit(**_):
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise TransientAlpacaError("connection reset")
        return {"id": "after-retries"}
    adapter.submit_order = MagicMock(side_effect=_fake_submit)
    router = OrderRouter(adapter, session_factory, EventBus())
    order = await router.submit(_req())

    assert order.status == OrderStatus.SUBMITTED
    assert order.broker_order_id == "after-retries"
    assert call_count["n"] == 3


@pytest.mark.asyncio
async def test_router_transient_error_eventually_gives_up(session_factory, seeded):
    adapter = _mock_adapter(submit_raises=TransientAlpacaError("always failing"))
    router = OrderRouter(adapter, session_factory, EventBus())
    order = await router.submit(_req())

    assert order.status == OrderStatus.REJECTED
    assert "broker_error" in (order.rejection_reason or "")


@pytest.mark.asyncio
async def test_router_cancel_terminal_order_is_noop(session_factory, seeded):
    async with session_factory() as session:
        session.add(Order(
            id=42, user_id=1, account_id=1, symbol_id=1,
            broker_order_id="finished-1",
            side=OrderSide.BUY, qty=Decimal("1"),
            type=OrderType.MARKET, tif=TimeInForce.DAY,
            status=OrderStatus.FILLED,
            source_type=OrderSourceType.MANUAL,
            created_at=_now(), updated_at=_now(), terminal_at=_now(),
        ))
        await session.commit()

    adapter = _mock_adapter()
    router = OrderRouter(adapter, session_factory, EventBus())
    order = await router.cancel(42, actor_user_id=1)
    assert order.status == OrderStatus.FILLED
    adapter.cancel_order.assert_not_called()
```

### 7.2.2 — Trade-update consumer test

Create `apps/backend/tests/orders/test_lifecycle.py`:

```python
"""TradeUpdateConsumer tests — Alpaca event -> Order/Fill/Position transitions."""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.enums import OrderSide, OrderSourceType, OrderStatus, OrderType, TimeInForce
from app.db.models.account import Account
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.events.bus import EventBus
from app.orders.lifecycle import TradeUpdateConsumer


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
async def seeded_with_open_order(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(Account(id=1, user_id=1, broker="alpaca", mode="paper", label="Paper"))
        session.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ",
                           asset_class="us_equity", name="Apple", active=True))
        session.add(Order(
            id=100, user_id=1, account_id=1, symbol_id=1,
            broker_order_id="alp-100",
            side=OrderSide.BUY, qty=Decimal("10"),
            type=OrderType.MARKET, tif=TimeInForce.DAY,
            status=OrderStatus.SUBMITTED,
            source_type=OrderSourceType.MANUAL,
            created_at=_now(), updated_at=_now(),
        ))
        await session.commit()


@pytest.mark.asyncio
async def test_fill_event_creates_fill_and_position(session_factory, seeded_with_open_order):
    bus = EventBus()
    consumer = TradeUpdateConsumer(session_factory, bus)
    consumer.start()

    await bus.publish("alpaca.trade_update", {
        "event": "fill",
        "broker_order_id": "alp-100",
        "execution_id": "exec-1",
        "qty": "10",
        "price": "190.50",
        "timestamp": "2026-05-19T10:00:00Z",
    })
    # let the subscriber run
    await asyncio.sleep(0)

    async with session_factory() as session:
        fills = (await session.execute(select(Fill))).scalars().all()
        assert len(fills) == 1
        assert fills[0].qty == Decimal("10")
        assert fills[0].price == Decimal("190.50")

        order = await session.get(Order, 100)
        assert order.status == OrderStatus.FILLED

        positions = (await session.execute(select(Position))).scalars().all()
        assert len(positions) == 1
        assert positions[0].qty == Decimal("10")
        assert positions[0].avg_entry_price == Decimal("190.50")


@pytest.mark.asyncio
async def test_duplicate_fill_idempotent(session_factory, seeded_with_open_order):
    bus = EventBus()
    consumer = TradeUpdateConsumer(session_factory, bus)
    consumer.start()

    payload = {
        "event": "fill",
        "broker_order_id": "alp-100",
        "execution_id": "exec-dup",
        "qty": "5",
        "price": "190.00",
    }
    await bus.publish("alpaca.trade_update", payload)
    await asyncio.sleep(0)
    await bus.publish("alpaca.trade_update", payload)  # same execution_id
    await asyncio.sleep(0)

    async with session_factory() as session:
        fills = (await session.execute(select(Fill))).scalars().all()
        assert len(fills) == 1


@pytest.mark.asyncio
async def test_unknown_broker_order_id_is_logged_not_crashed(session_factory):
    """Out-of-band orders (placed via the Alpaca dashboard) shouldn't crash."""
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        await session.commit()

    bus = EventBus()
    consumer = TradeUpdateConsumer(session_factory, bus)
    consumer.start()
    await bus.publish("alpaca.trade_update", {
        "event": "fill",
        "broker_order_id": "ghost-order",
        "execution_id": "exec-ghost",
        "qty": "1",
        "price": "100",
    })
    await asyncio.sleep(0)
    # Just confirming no exception was raised.


@pytest.mark.asyncio
async def test_cancel_event_transitions_to_canceled(session_factory, seeded_with_open_order):
    bus = EventBus()
    consumer = TradeUpdateConsumer(session_factory, bus)
    consumer.start()

    await bus.publish("alpaca.trade_update", {
        "event": "canceled",
        "broker_order_id": "alp-100",
    })
    await asyncio.sleep(0)

    async with session_factory() as session:
        order = await session.get(Order, 100)
        assert order.status == OrderStatus.CANCELED
        assert order.terminal_at is not None
```

### 7.2.3 — REST API endpoint smoke tests

Create `apps/backend/tests/api/__init__.py` (empty), then `apps/backend/tests/api/test_orders_endpoint.py`:

```python
"""Smoke tests for /api/v1/orders REST endpoints.

These use httpx.AsyncClient against the FastAPI app with the order router
swapped for a controllable mock. Focus: schema validation + status codes,
not router internals (those are tested in tests/orders/test_router.py).
"""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    RiskScopeType,
    TimeInForce,
)
from app.db.models.account import Account
from app.db.models.account_state import AccountState
from app.db.models.order import Order
from app.db.models.risk_limits import RiskLimits
from app.db.models.symbol import Symbol
from app.db.models.system_config import SystemConfig
from app.db.models.user import User


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
async def seeded_for_api(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(Account(id=1, user_id=1, broker="alpaca", mode="paper", label="Paper"))
        session.add(AccountState(
            account_id=1, cash=Decimal("50000"), equity=Decimal("100000"),
            last_equity=Decimal("100000"), buying_power=Decimal("100000"),
            portfolio_value=Decimal("100000"),
            day_change=Decimal("0"), day_change_pct=Decimal("0"),
            status="ACTIVE", raw_payload={}, updated_at=_now(),
        ))
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
        session.add(SystemConfig(user_id=1, key="mode", value="paper", updated_at=_now()))
        await session.commit()


@pytest.fixture
async def client_with_mock_router(session_factory, seeded_for_api):
    """Yield an httpx.AsyncClient against a FastAPI app with a mock OrderRouter
    stashed on app.state. We avoid bringing up the real lifespan so the test
    doesn't need Alpaca creds."""
    from app.main import create_app
    app = create_app()

    mock_router = MagicMock()
    submitted_order_id = {"n": 0}

    async def _mock_submit(req):
        submitted_order_id["n"] += 1
        async with session_factory() as session:
            order = Order(
                user_id=req.user_id, account_id=req.account_id, symbol_id=req.symbol_id,
                broker_order_id=f"mock-{submitted_order_id['n']}",
                side=req.side, qty=req.qty, type=req.type, tif=req.tif,
                status=OrderStatus.SUBMITTED,
                source_type=req.source_type,
                created_at=_now(), updated_at=_now(), submitted_at=_now(),
            )
            session.add(order)
            await session.commit()
            return order

    mock_router.submit = _mock_submit
    app.state.order_router = mock_router

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_post_orders_happy(client_with_mock_router):
    resp = await client_with_mock_router.post(
        "/api/v1/orders",
        json={"symbol": "AAPL", "side": "buy", "qty": "1", "type": "market", "tif": "day"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "submitted"
    assert data["symbol"] == "AAPL"
    assert data["broker_order_id"].startswith("mock-")


@pytest.mark.asyncio
async def test_post_orders_unknown_symbol(client_with_mock_router):
    resp = await client_with_mock_router.post(
        "/api/v1/orders",
        json={"symbol": "ZZNOTASYMBOL", "side": "buy", "qty": "1", "type": "market"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_post_orders_rejects_extra_field(client_with_mock_router):
    """Pydantic's extra='forbid' must reject unknown fields."""
    resp = await client_with_mock_router.post(
        "/api/v1/orders",
        json={"symbol": "AAPL", "side": "buy", "qty": "1", "type": "market",
              "fnord": "bypass-the-risk-engine"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_post_orders_negative_qty_rejected(client_with_mock_router):
    resp = await client_with_mock_router.post(
        "/api/v1/orders",
        json={"symbol": "AAPL", "side": "buy", "qty": "-1", "type": "market"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_orders_filters_status(client_with_mock_router, session_factory):
    # Seed two orders: one open, one filled
    async with session_factory() as session:
        session.add(Order(
            user_id=1, account_id=1, symbol_id=1,
            broker_order_id="open-1",
            side=OrderSide.BUY, qty=Decimal("1"),
            type=OrderType.MARKET, tif=TimeInForce.DAY,
            status=OrderStatus.SUBMITTED,
            source_type=OrderSourceType.MANUAL,
            created_at=_now(), updated_at=_now(),
        ))
        session.add(Order(
            user_id=1, account_id=1, symbol_id=1,
            broker_order_id="filled-1",
            side=OrderSide.BUY, qty=Decimal("1"),
            type=OrderType.MARKET, tif=TimeInForce.DAY,
            status=OrderStatus.FILLED,
            source_type=OrderSourceType.MANUAL,
            created_at=_now(), updated_at=_now(), terminal_at=_now(),
        ))
        await session.commit()

    resp_open = await client_with_mock_router.get("/api/v1/orders?status=open")
    assert resp_open.status_code == 200
    assert resp_open.json()["count"] == 1

    resp_hist = await client_with_mock_router.get("/api/v1/orders?status=history")
    assert resp_hist.status_code == 200
    assert resp_hist.json()["count"] == 1
```

### 7.2.4 — Run and check

```bash
cd apps/backend
uv run pytest -q
uv run pytest --cov-report=xml
uv run python scripts/check_risk_coverage.py
cd ../..
```

- [ ] All tests pass.
- [ ] Overall coverage ≥ 80% (or whatever ratchet floor you set).
- [ ] Risk engine branch coverage ≥ 95%.

---

## §7.3 — Backend End-to-End Integration Test

One focused test exercising the full pipeline. Mocked Alpaca, real event bus, real DB, real OrderRouter, real RiskEngine, real TradeUpdateConsumer.

Create `apps/backend/tests/integration/test_end_to_end_pipeline.py`:

```python
"""End-to-end pipeline test.

ticket payload -> POST /api/v1/orders -> OrderRouter.submit
    -> RiskEngine.evaluate (passes)
    -> mocked AlpacaAdapter.submit_order (returns broker id)
    -> Order row written, status=SUBMITTED
    -> simulate Alpaca trade update via event bus
    -> TradeUpdateConsumer writes Fill, updates Order to FILLED
    -> Position is upserted with correct qty + avg price
    -> AuditLog has the full chain
"""
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    RiskScopeType,
)
from app.db.models.account import Account
from app.db.models.account_state import AccountState
from app.db.models.audit_log import AuditLog
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.risk_limits import RiskLimits
from app.db.models.symbol import Symbol
from app.db.models.system_config import SystemConfig
from app.db.models.user import User
from app.events.bus import EventBus
from app.orders.lifecycle import TradeUpdateConsumer
from app.orders.router import OrderRouter


def _now():
    return datetime.now(timezone.utc)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_pipeline_paper_buy(session_factory):
    # ---- seed ----
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(Account(id=1, user_id=1, broker="alpaca", mode="paper", label="Paper"))
        session.add(AccountState(
            account_id=1, cash=Decimal("50000"), equity=Decimal("100000"),
            last_equity=Decimal("100000"), buying_power=Decimal("100000"),
            portfolio_value=Decimal("100000"),
            day_change=Decimal("0"), day_change_pct=Decimal("0"),
            status="ACTIVE", raw_payload={}, updated_at=_now(),
        ))
        session.add(Symbol(id=1, ticker="F", exchange="NYSE",
                           asset_class="us_equity", name="Ford", active=True))
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
        session.add(SystemConfig(user_id=1, key="mode", value="paper", updated_at=_now()))
        await session.commit()

    # ---- wire ----
    bus = EventBus()

    mock_adapter = MagicMock()
    mock_adapter.is_paper = True
    mock_adapter.submit_order = MagicMock(return_value={"id": "alp-e2e-1"})

    router = OrderRouter(mock_adapter, session_factory, bus)
    consumer = TradeUpdateConsumer(session_factory, bus)
    consumer.start()

    # Build the FastAPI app and wire the mock router onto app.state
    from app.main import create_app
    app = create_app()
    app.state.order_router = router
    app.state.alpaca_adapter = mock_adapter

    # ---- submit through REST ----
    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/orders",
            json={"symbol": "F", "side": "buy", "qty": "10", "type": "market", "tif": "day"},
        )
    assert resp.status_code == 200
    submitted = resp.json()
    assert submitted["status"] == "submitted"
    assert submitted["broker_order_id"] == "alp-e2e-1"
    order_id = submitted["id"]

    # Adapter was called exactly once with reasonable params
    mock_adapter.submit_order.assert_called_once()
    kwargs = mock_adapter.submit_order.call_args.kwargs
    assert kwargs["symbol"] == "F"
    assert kwargs["side"] == "buy"
    assert kwargs["qty"] == "10"

    # ---- simulate Alpaca trade-update fill ----
    await bus.publish("alpaca.trade_update", {
        "event": "fill",
        "broker_order_id": "alp-e2e-1",
        "execution_id": "exec-e2e-1",
        "qty": "10",
        "price": "12.34",
        "timestamp": "2026-05-19T15:30:00Z",
    })
    await asyncio.sleep(0)

    # ---- assertions ----
    async with session_factory() as session:
        # Order is FILLED
        order = await session.get(Order, order_id)
        assert order.status == OrderStatus.FILLED
        assert order.broker_order_id == "alp-e2e-1"
        assert order.terminal_at is not None

        # Fill row exists with the right qty/price
        fills = (await session.execute(select(Fill).where(Fill.order_id == order_id))).scalars().all()
        assert len(fills) == 1
        assert fills[0].qty == Decimal("10")
        assert fills[0].price == Decimal("12.34")

        # Position upserted
        positions = (await session.execute(select(Position))).scalars().all()
        assert len(positions) == 1
        assert positions[0].symbol_id == 1
        assert positions[0].qty == Decimal("10")
        assert positions[0].avg_entry_price == Decimal("12.34")
        assert positions[0].side == "long"

        # Audit chain is complete
        actions = [
            r.action for r in (await session.execute(select(AuditLog).order_by(AuditLog.id))).scalars().all()
        ]
        assert "order.created" in actions
        assert "order.risk_passed" in actions
        assert "order.submitted" in actions
        assert "order.fill" in actions
```

Run it:

```bash
cd apps/backend
uv run pytest tests/integration/test_end_to_end_pipeline.py -v
cd ../..
```

- [ ] End-to-end test passes.

---

## §7.4 — ADR 0002 CI Tripwire

Session 5 §5.6 wrote the grep script `scripts/check_adr0002.sh` (or similar). This section wires it into CI as a required check.

### 7.4.1 — Verify the script exists and works

```bash
ls apps/backend/scripts/check_adr0002.sh 2>/dev/null || ls scripts/check_adr0002.sh
bash apps/backend/scripts/check_adr0002.sh    # or wherever it lives
# Expected: exit 0 with "ADR 0002 OK" or similar
```

If Session 5 named it differently, just verify there *is* a grep-based check enforcing the invariant. If it's missing, here's the script — drop into `apps/backend/scripts/check_adr0002.sh`:

```bash
#!/usr/bin/env bash
# ADR 0002 tripwire: only OrderRouter (and the adapter file itself) may
# call AlpacaAdapter's mutating methods. Run from repo root.
set -euo pipefail

PATTERNS='\b(submit_order|cancel_order|replace_order)\s*\('
SEARCH_DIR="apps/backend/app"
ALLOWED='apps/backend/app/orders/router.py|apps/backend/app/brokers/alpaca/adapter.py'

OFFENDERS=$(grep -rEn "$PATTERNS" "$SEARCH_DIR" --include='*.py' \
  | grep -Ev "$ALLOWED" \
  || true)

if [[ -n "$OFFENDERS" ]]; then
  echo "ADR 0002 VIOLATION — direct callers of AlpacaAdapter mutating methods outside OrderRouter:" >&2
  echo "$OFFENDERS" >&2
  exit 1
fi
echo "ADR 0002 OK"
```

Make executable:

```bash
chmod +x apps/backend/scripts/check_adr0002.sh
```

### 7.4.2 — Add the check to GitHub Actions

Edit `.github/workflows/ci.yml`. Find the backend Python job and add a step after the test step:

```yaml
      - name: ADR 0002 invariant check
        run: bash apps/backend/scripts/check_adr0002.sh
```

Also add a step for the Risk Engine coverage check:

```yaml
      - name: Risk engine branch-coverage gate
        run: |
          cd apps/backend
          uv run pytest --cov-report=xml
          uv run python scripts/check_risk_coverage.py
```

After this CI run is green on a PR, go to repository settings → Branch protection rules → `protect-main` → required checks → add these two new step names (they'll appear as available checks after the first PR run that includes them).

### 7.4.3 — Test the tripwire

Validate the check actually fails when violated. Temporarily edit `apps/backend/app/api/v1/account.py` and add a line like:

```python
# DELIBERATE TEST — REMOVE BEFORE COMMIT
# adapter.submit_order(symbol="X")
```

Run the script:

```bash
bash apps/backend/scripts/check_adr0002.sh
# Expected: exit 1 with the violating file listed
```

If it doesn't catch the violation, the regex or the ALLOWED pattern is wrong. Fix. Then **remove the test line and verify it's clean again** before continuing:

```bash
# Make sure you actually removed the test line
git diff apps/backend/app/api/v1/account.py
# Should show no changes
bash apps/backend/scripts/check_adr0002.sh
# Expected: exit 0 "ADR 0002 OK"
```

- [ ] Tripwire script exists and exits 0 on clean code.
- [ ] Tripwire exits 1 when a deliberate violation is added.
- [ ] Test violation removed.
- [ ] CI workflow runs the tripwire as a required step.

---

## §7.5 — Frontend Vitest Tests

Per P1 Checklist §10.3, three high-value tests. Order ticket happy path, risk-rejection rendering, live-mode flow.

Create `apps/frontend/src/components/ticket/__tests__/OrderTicket.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { OrderTicket } from "../OrderTicket";
import { ordersApi } from "@/api/orders";
import { quotesApi } from "@/api/quotes";
import { accountApi } from "@/api/account";

vi.mock("@/api/orders");
vi.mock("@/api/quotes");
vi.mock("@/api/account");

const mockedOrdersApi = vi.mocked(ordersApi);
const mockedQuotesApi = vi.mocked(quotesApi);
const mockedAccountApi = vi.mocked(accountApi);

describe("OrderTicket", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedQuotesApi.get.mockResolvedValue({
      symbol: "AAPL",
      bid: "190.50",
      ask: "190.52",
      last: "190.51",
      bid_size: 100,
      ask_size: 100,
      ts: new Date().toISOString(),
    });
    mockedAccountApi.get.mockResolvedValue({
      account_id: 1, mode: "paper", status: "ACTIVE",
      cash: "100000", equity: "100000", last_equity: "100000",
      buying_power: "100000", portfolio_value: "100000",
      day_change: "0", day_change_pct: "0",
      daytrade_count: 0, pattern_day_trader: false,
      trading_blocked: false, account_blocked: false,
      updated_at: new Date().toISOString(),
    });
  });

  it("submits a clean order and shows the success banner", async () => {
    mockedOrdersApi.create.mockResolvedValue({
      id: 42, broker_order_id: "alp-42", client_order_id: "twb-42",
      symbol: "AAPL", side: "buy", qty: "1", type: "market",
      limit_price: null, stop_price: null, tif: "day", extended_hours: false,
      status: "submitted", rejection_reason: null,
      source_type: "manual", source_id: null,
      created_at: new Date().toISOString(),
      submitted_at: new Date().toISOString(),
      terminal_at: null, updated_at: new Date().toISOString(),
      fills: [], risk_check: null,
    });

    render(<OrderTicket defaultSymbol="AAPL" />);

    fireEvent.click(screen.getByText(/Submit BUY/i));

    await waitFor(() => {
      expect(mockedOrdersApi.create).toHaveBeenCalledTimes(1);
      expect(mockedOrdersApi.create).toHaveBeenCalledWith(
        expect.objectContaining({ symbol: "AAPL", side: "buy", qty: "1", type: "market" }),
      );
    });

    expect(await screen.findByText(/Order #42 submitted/i)).toBeInTheDocument();
  });

  it("shows the risk-rejection banner with plain English when risk_check.decision = reject", async () => {
    mockedOrdersApi.create.mockResolvedValue({
      id: 43, broker_order_id: null, client_order_id: "twb-43",
      symbol: "AAPL", side: "buy", qty: "99999", type: "market",
      limit_price: null, stop_price: null, tif: "day", extended_hours: false,
      status: "rejected",
      rejection_reason: "POSITION_CAP_QTY,POSITION_CAP_NOTIONAL",
      source_type: "manual", source_id: null,
      created_at: new Date().toISOString(),
      submitted_at: null, terminal_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      fills: [],
      risk_check: {
        id: 99,
        decision: "reject",
        reason_codes: ["POSITION_CAP_QTY", "POSITION_CAP_NOTIONAL"],
        evaluated_at: new Date().toISOString(),
      },
    });

    render(<OrderTicket defaultSymbol="AAPL" />);
    // Replace the qty before submitting
    fireEvent.change(screen.getByDisplayValue("1"), { target: { value: "99999" } });
    fireEvent.click(screen.getByText(/Submit BUY/i));

    const banner = await screen.findByText(/rejected by risk engine/i);
    expect(banner).toBeInTheDocument();
    expect(banner.textContent).toMatch(/position quantity cap/i);
    expect(banner.textContent).toMatch(/position notional/i);
  });

  it("in live mode, pops the confirmation modal instead of submitting immediately", async () => {
    mockedAccountApi.get.mockResolvedValue({
      ...(await mockedAccountApi.get.mock.results[0]?.value ?? {}),
      mode: "live",
    } as any);
    // Re-mock since the previous call won't have happened yet:
    mockedAccountApi.get.mockResolvedValue({
      account_id: 1, mode: "live", status: "ACTIVE",
      cash: "100000", equity: "100000", last_equity: "100000",
      buying_power: "100000", portfolio_value: "100000",
      day_change: "0", day_change_pct: "0",
      daytrade_count: 0, pattern_day_trader: false,
      trading_blocked: false, account_blocked: false,
      updated_at: new Date().toISOString(),
    });

    render(<OrderTicket defaultSymbol="AAPL" />);
    // wait for accountApi to resolve and mode to be set to live
    await waitFor(() => expect(mockedAccountApi.get).toHaveBeenCalled());

    fireEvent.click(screen.getByText(/Submit BUY/i));

    // Modal should appear
    expect(await screen.findByText(/Confirm Live Order/i)).toBeInTheDocument();
    // orders.create must NOT have been called
    expect(mockedOrdersApi.create).not.toHaveBeenCalled();
  });
});
```

Run:

```bash
cd apps/frontend
pnpm test
cd ../..
```

- [ ] All three Vitest tests pass.

---

## §7.6 — Runbook Docs

### 7.6.1 — `docs/runbook/live-mode.md`

Create `docs/runbook/live-mode.md`:

```markdown
# Live-Mode Runbook

> ⚠️ **Live mode places real orders against real money.** Treat every step as
> production-grade. Defaults intentionally favor paper.

## Default state

`WORKBENCH_TRADING_MODE=paper` is set in `.env.example` and inherited by every
development checkout. The amber `PAPER TRADING` banner is the always-on visual.

## Enabling live mode

Live mode requires **three independent flags** to be true simultaneously:

1. `WORKBENCH_TRADING_MODE=live` in `.env`.
2. `WORKBENCH_LIVE_ACK=I_UNDERSTAND` in `.env`.
3. `ALPACA_LIVE_API_KEY` and `ALPACA_LIVE_API_SECRET` populated in `.env`.

If any one of the three is missing or wrong, the backend boots in **live-blocked**
mode: `/api/v1/account` returns the live account, but `POST /api/v1/orders`
returns 503 and the banner shows "live mode not acknowledged."

### Step-by-step

1. Generate a live API key + secret in Alpaca's live dashboard.
   *(This is a separate dashboard from paper — verify the URL says `app.alpaca.markets/brokerage`, not `paper-app.alpaca.markets`.)*
2. Stop the backend: `docker compose down`.
3. Edit `.env`:
   ```
   WORKBENCH_TRADING_MODE=live
   WORKBENCH_LIVE_ACK=I_UNDERSTAND
   ALPACA_LIVE_API_KEY=YOUR_LIVE_KEY
   ALPACA_LIVE_API_SECRET=YOUR_LIVE_SECRET
   ```
4. Start: `./scripts/dev.sh`.
5. Verify the banner is now **RED** and reads "LIVE TRADING".
6. Verify the account number on the Dashboard matches your live account.
7. Place a 1-share test order on the cheapest symbol you trust to absorb the
   round-trip cost. Confirm it appears in your Alpaca live dashboard.
8. **Close the test position immediately** before you forget it's there.

## Disabling live mode

1. Stop the backend.
2. Set `WORKBENCH_TRADING_MODE=paper` in `.env` (or simply unset it; default is paper).
3. Optionally clear `WORKBENCH_LIVE_ACK`.
4. Start. Verify the banner is amber.

## Emergency: I accidentally went live and placed an unintended order

1. Cancel the order via the Orders page **Cancel** button. If already filled:
2. Close the position via the Positions page **Close** button.
3. If both fail (broker outage, UI broken): go to Alpaca's live web dashboard
   and close the position there directly.
4. Stop the backend (`docker compose down`).
5. Set `WORKBENCH_TRADING_MODE=paper` before restarting.
6. Audit `audit_log` for everything that happened in live mode:
   ```bash
   docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
     "SELECT ts, action, target_id, payload_json FROM audit_log
      WHERE ts >= datetime('now','-2 hours') ORDER BY id;"
   ```

## Per-order safeguards in live mode

These are enforced by the UI on top of all the backend Risk Engine checks:

- The mode banner is red and pulses gently.
- Every Submit click in live mode opens a confirmation modal requiring
  three independent confirmations: two checkboxes plus typing the symbol.
- The "remember my acknowledgement" affordance does not exist by design.

## Backend Risk Engine in live mode

The Risk Engine is **identical** in paper and live mode. Tune the default
`risk_limits` row for tighter caps before going live; see
[`risk-limits.md`](./risk-limits.md).

## Going back to paper after live use

Always switch back to paper at the end of a session unless you intend to leave
working live orders open overnight. Forgetting causes the "I thought I was in
paper" class of accident.
```

### 7.6.2 — `docs/runbook/risk-limits.md`

Create `docs/runbook/risk-limits.md`:

```markdown
# Risk Limits Runbook

The Risk Engine evaluates every order against the most specific applicable
`risk_limits` row. In P1, only the **GLOBAL** scope is used.

## Default seeded values

These are inserted by `scripts/seed_dev_data.py` on a fresh DB:

| Field | Value | Meaning |
|---|---|---|
| `max_position_qty` | 1000 | No single position may exceed 1000 shares |
| `max_position_notional` | 25000 | Notional cap of $25,000 per position |
| `max_gross_exposure` | 100000 | Total absolute exposure across all positions |
| `max_daily_loss` | 2000 | Daily loss limit before HALT |
| `max_orders_per_minute` | 10 | Rate limit |
| `allow_short` | false | No short selling |
| `allowed_symbols` | NULL | All symbols allowed |
| `denied_symbols` | NULL | None denied |

## Viewing current values

```bash
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "SELECT * FROM risk_limits WHERE scope_type = 'global';"
```

## Changing values (P1: SQL only; P4 adds a Settings UI)

```bash
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "UPDATE risk_limits
   SET max_position_notional = 10000, updated_at = datetime('now')
   WHERE scope_type = 'global';"
```

The change takes effect on the *next* order; no restart needed.

## Reason codes — what each rejection means

Codes are returned in `risk_check.reason_codes` and displayed to the user via
the `describeReason` map in the frontend:

| Code | Meaning |
|---|---|
| `OK` | Risk checks passed. |
| `MODE_MISMATCH` | Order's account doesn't match the current trading mode. |
| `SYMBOL_DENIED` | Symbol is on the denylist or not on the allowlist. |
| `SHORT_NOT_ALLOWED` | This would create or extend a short position. |
| `EXTENDED_HOURS_NOT_ALLOWED` | Extended hours requested for a non-limit order. |
| `POSITION_CAP_QTY` | Resulting position size > `max_position_qty`. |
| `POSITION_CAP_NOTIONAL` | Resulting notional > `max_position_notional`. |
| `GROSS_EXPOSURE` | Total exposure would exceed `max_gross_exposure`. |
| `HALT_REACHED` | Trading is halted (daily loss limit hit). |
| `RATE_LIMIT` | > `max_orders_per_minute` in the last 60 seconds. |
| `INVALID_INPUT` | Bad qty, price, or TIF. |
| `NO_QUOTE` | Notional check needs a price; none was available. |

## Halt and unhalt

When `HALT_REACHED` fires, the system halt flag is set in `system_config`:

```bash
# Check
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "SELECT value FROM system_config WHERE key='halted';"
# returns 'true' if halted

# Unhalt manually (P5 adds a UI button)
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "UPDATE system_config SET value='false', updated_at=datetime('now') WHERE key='halted';"
```

Restart not required — the engine reads on every evaluate.

## Tightening for live trading

Before flipping `WORKBENCH_TRADING_MODE=live`, consider:

- Lower `max_position_notional` to a number you'd be comfortable losing entirely.
- Lower `max_daily_loss` to a fraction of your real risk budget.
- Add specific tickers to `allowed_symbols` if you only intend to trade a small set:
  ```sql
  UPDATE risk_limits SET allowed_symbols = '["AAPL","MSFT","SPY"]' WHERE scope_type='global';
  ```
```

### 7.6.3 — `docs/runbook/symbol-mapping-gaps.md`

Create `docs/runbook/symbol-mapping-gaps.md`:

```markdown
# Symbol Mapping Gaps

The Charts page's TradingView widget needs a per-symbol mapping like
`AAPL → NASDAQ:AAPL`. The map lives in
`apps/frontend/src/components/chart/TVChart.tsx` (`SYMBOL_MAP`).

Symbols not in the map fall back to TradingView's auto-resolve, which works
for most large-cap US equities but occasionally hits the wrong listing.

## Known gaps

*Add an entry here every time you find a symbol that doesn't resolve correctly
in the chart. Format: ticker, intended exchange, observed problem, fix.*

| Ticker | Intended | Observed problem | Fix |
|---|---|---|---|
| (none recorded yet — add as encountered) | | | |

## Adding a new mapping

1. Add an entry to `SYMBOL_MAP`:
   ```typescript
   "BRK.B": "NYSE:BRK.B",
   ```
2. Test in the Charts page.
3. Add a row above with the date and what prompted the entry.

## P4 plan

Once the map grows past ~50 entries it should move to a JSON file under
`docs/data/tv-symbol-map.json` and be fetched on Charts page load. Don't
do this in P1.
```

- [ ] All three runbook docs created.

---

## §7.7 — Manual Smoke Matrix (P1 Checklist §10.4)

Six steps against Alpaca paper. Record results inline in a new log file. **Do these during regular market hours** (Mon–Fri, 09:30–16:00 ET) for deterministic fills; off-hours, the limit and cancel steps still work but the market-order steps stall.

### 7.7.1 — Prepare the smoke log

Create `docs/runbook/p1-smoke-log.md`:

```markdown
# P1 Paper-Trading Smoke Log

| Field | Value |
|---|---|
| Date | YYYY-MM-DD |
| Time started | HH:MM ET |
| Trader | Jay |
| Branch / tag | feat/p1-tests-smoke-exit at HEAD |
| Alpaca paper buying power before | $______ |

## Steps

### 1. Market BUY 1 share AAPL → fills near market

- [ ] Submitted at HH:MM:SS ET
- [ ] Status went `submitted → filled` within ___ seconds
- [ ] Order ID: ___
- [ ] Fill price: $___
- [ ] Position appeared in Positions page: yes / no
- [ ] Audit log has the chain: `order.created → order.risk_passed → order.submitted → order.fill`: yes / no
- Notes:

### 2. Limit BUY 1 share AAPL at a low limit (won't fill) → cancel

- [ ] Submitted at HH:MM:SS ET with limit price $___ (well below market)
- [ ] Order appears in Orders "Working" tab: yes / no
- [ ] Clicked Cancel
- [ ] Order moved to "History" with status `canceled`: yes / no
- [ ] Audit log has `order.canceled`: yes / no
- Notes:

### 3. Submit BUY 10000 AAPL (oversize) → expect risk rejection

- [ ] Submitted via ticket
- [ ] Amber banner appeared in UI: yes / no
- [ ] Banner text mentions "position quantity" or "notional": yes / no
- [ ] No order reached Alpaca (checked Alpaca dashboard): yes / no
- [ ] `risk_checks` row exists with `decision=reject` and the right reason code: yes / no
- Notes:

### 4. Force a daily-loss halt

```bash
# Set artificially low daily loss limit
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "UPDATE risk_limits SET max_daily_loss = 1 WHERE scope_type='global';"
# Wait for position-sync poll to pick up any small unrealized loss, OR
# manually trigger halt by inserting a system_config halted=true row:
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "INSERT OR REPLACE INTO system_config(user_id, key, value, updated_at)
   VALUES(1, 'halted', 'true', datetime('now'));"
```

- [ ] Tried to submit a 1-share market BUY: rejected with `HALT_REACHED`: yes / no
- [ ] UI banner shows the rejection: yes / no
- Unhalt:
  ```bash
  docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
    "UPDATE system_config SET value='false' WHERE key='halted';
     UPDATE risk_limits SET max_daily_loss = 2000 WHERE scope_type='global';"
  ```
- [ ] After unhalt, new order goes through: yes / no
- Notes:

### 5. Modify a working order's limit price

- [ ] Submit a LIMIT BUY 1 AAPL at $___ (well below market)
- [ ] Order appears working
- [ ] Click Modify, change limit price to $___
- [ ] Verify in Alpaca dashboard that the limit changed: yes / no
- [ ] Audit log has `order.replaced`: yes / no
- [ ] Cancel the order afterward
- Notes:

### 6. Close a position via the Positions page

- [ ] Submit a MARKET BUY 1 AAPL (fills)
- [ ] Position appears
- [ ] Click "Close" on the Positions page
- [ ] Confirmation modal appears (in paper, just a window.confirm)
- [ ] New SELL order is created via `POST /api/v1/positions/AAPL/close`
- [ ] Position goes to zero after fill: yes / no
- [ ] Audit log has both fills + risk checks for both orders: yes / no
- Notes:

## Summary

- [ ] All 6 steps passed
- Buying power after: $___ (should be approximately equal to before, minus any partial fills that didn't close cleanly)
- Open orders / positions after: ___ / ___ (should both be zero unless something didn't clean up)
- Anomalies: (free text)
```

### 7.7.2 — Execute the smoke

Boot the system:

```bash
./scripts/dev.sh
# in another terminal, run the smoke steps and fill in the log as you go
```

Execute each step. For step 4, double-check you actually unhalted before moving on — leaving the system halted will block all subsequent paper trading until you fix it.

After all six steps:

```bash
# Confirm cleanup
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "SELECT count(*) AS open_orders FROM orders
   WHERE status NOT IN ('filled','canceled','rejected','expired','replaced');"
# Expect: 0

docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "SELECT count(*) FROM positions;"
# Expect: 0

# If non-zero, clean up via Alpaca:
set -a; source .env; set +a
curl -X DELETE https://paper-api.alpaca.markets/v2/orders \
  -H "APCA-API-KEY-ID: $ALPACA_PAPER_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_PAPER_API_SECRET"
curl -X DELETE https://paper-api.alpaca.markets/v2/positions \
  -H "APCA-API-KEY-ID: $ALPACA_PAPER_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_PAPER_API_SECRET"
```

Commit the smoke log with the results filled in. **Do not** edit it after the fact — if any step failed, fix the bug, run that step again on a fresh log entry (append, don't overwrite), and document which step's failure prompted the fix.

```bash
docker compose down
```

- [ ] All six smoke steps green.
- [ ] Smoke log committed with real timestamps and IDs.
- [ ] Open orders count = 0; positions count = 0.

---

## §7.8 — README Quickstart Refresh

Replace the Quickstart section of `README.md` with something that actually reflects the working system:

```markdown
## Quickstart

### Prerequisites

- Docker Desktop (or `docker` + `docker compose`)
- Alpaca paper account: get free API keys from
  [app.alpaca.markets/paper/dashboard/overview](https://app.alpaca.markets/paper/dashboard/overview)

### First-time setup

```bash
# 1. Clone
git clone git@github.com:jayw04/AI-TRADING-APP.git
cd AI-TRADING-APP

# 2. Configure
cp .env.example .env
# Edit .env: set ALPACA_PAPER_API_KEY and ALPACA_PAPER_API_SECRET
# Leave WORKBENCH_TRADING_MODE=paper unless you know what you're doing
# (see docs/runbook/live-mode.md).

# 3. Boot
./scripts/dev.sh

# 4. Open the UI
open http://localhost:5173    # or visit in any browser
```

### What you'll see

- An amber **PAPER TRADING** banner at the top of every page.
- A Dashboard with your real Alpaca paper account: cash, equity, buying power,
  day P&L, open orders/positions count.
- An **Opportunities** page with the order ticket: enter a symbol, pick side,
  qty, type, submit. Orders flow through the Risk Engine and the Order Router
  to Alpaca paper.
- An **Orders** page with Working / History tabs, inline Cancel and Modify.
- A **Positions** page with live P&L per symbol and a one-click market Close.
- A **Charts** page with the embedded TradingView Advanced Charts widget.

### What's running

Three services brought up by `docker compose`:

| Service | Port | Purpose |
|---|---|---|
| `backend` | 8000 | FastAPI: REST + WebSocket + scheduler + order router + risk engine |
| `mcp-server` | 8765 | MCP server for Claude Code (one read-only tool today; expands in P3) |
| `frontend` | 5173 | Vite dev server |

### Common operations

```bash
# Watch backend logs
docker compose logs -f backend

# Inspect the DB
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite

# Restart after .env changes
docker compose down && ./scripts/dev.sh

# Reset to a clean state (DROPS ALL ORDERS, POSITIONS, AUDIT HISTORY)
docker compose down
rm apps/backend/data/workbench.sqlite
./scripts/dev.sh
# the lifespan will re-create + seed on next boot
```

### Going further

- [`docs/runbook/live-mode.md`](docs/runbook/live-mode.md) — how to enable
  live trading (and how to back out safely).
- [`docs/runbook/risk-limits.md`](docs/runbook/risk-limits.md) — what the
  default caps mean and how to change them.
- [`docs/implementation/`](docs/implementation/) — phase plans, session
  docs, implementation plan v0.2.
```

- [ ] README Quickstart updated.

---

## §7.9 — Update `todo.md`

Replace the P1 section of `todo.md` with a completion summary, and add a P2 prereqs section. Suggested shape (adjust to actual commit hashes):

```markdown
## ✅ P1 — Manual Trading MVP (complete)

Tag: `p1-complete` at HEAD of `main`. P1 closes Design Doc §2.3 success
criteria **S1**, **S2**, **S5** (partial), **S6** (partial).

| Session | Status | Notes |
|---|---|---|
| 1. P0 follow-ups + Alpaca adapter foundation | ✅ | Credentials, error taxonomy, read-only adapter |
| 2. Asset / account / position polling | ✅ | Scheduler, lifespan, accounts_state |
| 3. Trade Updates WS lifecycle | ✅ | Stream → event bus |
| 4. Trading DB schema | ✅ | orders, fills, positions, risk_limits, risk_checks |
| 5. Risk Engine + Order Router + trade-update consumer + reconciliation | ✅ | ADR 0002 in code |
| 6. REST + WS topics + frontend trading UI | ✅ | Ticket, Orders, Positions, Charts, Dashboard |
| 7. Tests + smoke + runbooks + exit gate | ✅ | This session |

### Deferred items (intentionally) to P4 polish

- Opportunities page (movers / vol-surge / curated lists / indicator panel)
- Hotkeys
- Full kill-switch UI (the endpoint exists; UI is missing)
- TradingView Charting Library license (free widget is fine for now)
- Per-symbol mapping JSON file (the inline map is fine until ~50 entries)
- Playwright E2E tests
- Auto-repair for reconciliation drift (detection-only for now)

## 🚧 P2 — Strategy MVP (next phase)

Goal: one reference systematic strategy runs end-to-end on paper with a
backtest harness.

### P2 prereqs

- [ ] Re-read Design Doc §11 (Strategy framework).
- [ ] Decide on backtest data caching format (parquet by symbol-day per IP v0.2 §19; confirm).
- [ ] Draft the P2 checklist analogous to the P1 checklist (sessions + acceptance criteria).
- [ ] Confirm: the reference strategy is a simple RSI mean-reversion on a single symbol (low complexity, high explanatory value), not anything market-beating.
```

- [ ] `todo.md` updated.

---

## §7.10 — Exit Gate Walk-through

Every box in this section must be ticked before tagging. From the project root:

```bash
# 1. Fresh checkout / clean state
git status                                     # clean
git pull origin main                           # PR merged
git fetch --tags

# 2. CI is green on main
gh run list --branch main --limit 1
# Verify the latest run shows all checks success

# 3. Branch protection enforced + required checks include the new ones
gh api repos/jayw04/AI-TRADING-APP/rules/branches/main \
  | jq '.[] | select(.type == "required_status_checks")'

# 4. ADR 0002 invariant
bash apps/backend/scripts/check_adr0002.sh
# Expected: ADR 0002 OK

# 5. Coverage gates
cd apps/backend
uv run pytest --cov-report=xml
uv run python scripts/check_risk_coverage.py
cd ../..

# 6. End-to-end docker-compose boots cleanly
./scripts/dev.sh
sleep 30
curl -fs http://127.0.0.1:8000/healthz | jq -e '.status == "ok"'
curl -fs http://127.0.0.1:8000/api/v1/account | jq -e '.status == "ACTIVE"'
echo "open http://localhost:5173 and verify Dashboard renders"

# 7. Smoke log is committed and complete
ls docs/runbook/p1-smoke-log.md
grep -c "All 6 steps passed" docs/runbook/p1-smoke-log.md
# Expect: 1

docker compose down
```

Final checklist mirroring Design Doc §2.3 plus P1 Checklist §12:

- [ ] **S1**: Trader can place, modify, cancel paper orders from UI (covered by §7.7 steps 1, 2, 5).
- [ ] **S2**: TradingView chart visible for seed symbols (UI verification in §7.4).
- [ ] **S5 partial**: Risk controls block out-of-policy orders with clear UI feedback (§7.7 step 3).
- [ ] **S6 partial**: Trading actions persisted + exportable via the audit log table (§7.7 steps 1–6 each record audit chains).
- [ ] Risk engine branch coverage ≥ 95% (script-enforced).
- [ ] No code path submits an order without `OrderRouter` (grep-enforced).
- [ ] All 6 manual smoke steps pass.
- [ ] CI green on `main`.
- [ ] `docker compose up` from a clean checkout works end-to-end.

If every box ticks:

```bash
git tag -a p1-complete -m "P1 Manual Trading MVP complete: paper trading via UI, risk-gated, audited"
git push origin p1-complete
```

- [ ] `p1-complete` tag pushed.

---

## §7.11 — Commit and PR

```bash
git add apps/backend/pyproject.toml
git add apps/backend/scripts/
git add apps/backend/tests/
git add apps/frontend/src/components/ticket/__tests__/
git add .github/workflows/ci.yml
git add docs/runbook/
git add README.md
git add todo.md

git commit -m "test(p1): coverage gates, integration test, smoke log, runbooks, exit gate

- Backend coverage gate at 80%; risk engine specifically at 95% branch
- OrderRouter unit tests (transient retry, permanent reject, cancel terminal)
- Trade-update consumer tests (idempotent fills, unknown order_id, terminals)
- REST endpoint tests (schema strictness, status filters, ownership)
- Integration test: ticket -> router -> risk -> mocked alpaca -> fill -> position
- ADR 0002 grep tripwire wired into CI
- Frontend Vitest tests for ticket happy path, risk rejection, live-mode flow
- Runbooks: live-mode.md, risk-limits.md, symbol-mapping-gaps.md
- P1 smoke log with all 6 steps recorded
- README Quickstart updated to match the working system
- todo.md: P1 marked complete; P2 prereqs section added"

git push -u origin feat/p1-tests-smoke-exit
gh pr create \
  --title "test(p1): exit gate — coverage, integration test, smoke, runbooks" \
  --body "Closes P1. After this lands, tag p1-complete."

gh pr checks
gh pr merge --merge --delete-branch
git checkout main && git pull
```

Then (only after merge):

```bash
git tag -a p1-complete -m "P1 Manual Trading MVP complete"
git push origin p1-complete
```

- [ ] PR merged.
- [ ] Tag pushed.

---

## Final Verification

After the tag is pushed:

```bash
git describe --tags --abbrev=0     # expect: p1-complete
gh release create p1-complete --notes "P1 Manual Trading MVP complete." || true
# (Release is optional; the tag alone is enough.)

# A clean-machine smoke (simulate a new developer joining):
cd /tmp && git clone git@github.com:jayw04/AI-TRADING-APP.git twb-clean
cd twb-clean
cp .env.example .env
# manually populate ALPACA_PAPER_API_KEY/SECRET
./scripts/dev.sh
sleep 30
curl -fs http://127.0.0.1:8000/healthz
docker compose down
cd .. && rm -rf twb-clean
```

- [ ] Clean-machine boot works without surprises.

---

## Sign-off

```bash
git tag -a p1-session7-complete -m "P1 Session 7 complete (= P1 complete)"
git push origin p1-session7-complete
```

> `p1-session7-complete` is functionally identical to `p1-complete` but lets the
> session-tag pattern continue. Either tag works as the reference point.

Update `todo.md` one more time if needed; commit; push directly to a docs PR.

**P1 is done. Move to P2 (Strategy MVP).**

---

## Notes & Gotchas

1. **80% coverage isn't a sacred number.** If your suite is at 78% after this session and getting to 80 means writing meaningless tests just to cover lines, lower the floor to 78 and ratchet it up in P4. Coverage that doesn't catch real bugs is just busywork.

2. **The integration test mocks AlpacaAdapter, not the event bus.** The real bus + real DB + real consumer is what we want exercised; mocking the bus would defeat the purpose. If the integration test ever flakes due to event-loop timing, add a tiny `await asyncio.sleep(0)` before assertions, not a longer sleep — the latter masks real ordering bugs.

3. **The ADR 0002 tripwire is grep-based, not AST-based.** A determined developer could bypass it (`adapter_var = self._adapter; adapter_var.submit_order(...)`). An AST-based check is sturdier but more work; grep is good enough for accidental violations and that's the realistic failure mode. P4 polish can upgrade.

4. **Vitest mocks need vi.resetAllMocks in beforeEach.** Without it, a previous test's `mockResolvedValueOnce` can leak into the next. The test file above does this; don't remove.

5. **Manual smoke must be done in regular hours for steps 1 and 6.** After-hours, the market BUY won't fill until next open and step 6 (close a position) needs a position that actually exists. If you can only smoke after-hours, swap to limit orders at marketable prices and use Alpaca's extended-hours flag.

6. **If smoke step 4 leaves the system halted, you can't trade until you unhalt.** This has bitten me. The cleanup SQL in step 4 is mandatory, not optional.

7. **The smoke log is append-only by convention.** If a step fails on the first try, write what failed, fix the bug, then add a second attempt at the bottom. This keeps the historical record honest.

8. **Don't be tempted to retroactively add P4 deferrals into P1.** Hotkeys, the Opportunities page, the full kill-switch UI — these are all real features I'd like to use, but the cleanest move is to ship P1 as scoped and start P2 with a clean conscience.

9. **`gh pr checks` reports the status of *all* configured checks, including ones not required.** Required checks are the gating set. The `gh api .../rules/branches/main` call in §7.10 confirms which checks are required.

10. **After tagging, the next branch should target P2.** Resist the urge to start P2 work in this session — it's a clean break point and the next session deserves its own setup.

---

*End of P1 Session 7 v0.1.*
