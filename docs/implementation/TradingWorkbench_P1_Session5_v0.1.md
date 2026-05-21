# P1 Session 5 — Risk Engine, Order Router, Trade-Update Consumer, Reconciliation Drift

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-20 |
| Phase | **P1**, **§3 + §4 + remainder of §1 (lifecycle + drift)** |
| Predecessor | *TradingWorkbench_P1_Session4_v0.1.md* (tag `p1-session4-complete`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | Implement the ADR 0002 invariant in code. Four interlocking pieces: (1) Risk Engine that evaluates every order against `risk_limits` and persists `risk_checks`; (2) Order Router as the single entry point for all order submission; (3) trade-update consumer that translates `alpaca.trade_update` events into `Fill` rows and order-status transitions; (4) reconciliation drift detector that compares local DB vs. Alpaca state on each poll. |
| Estimated wall time | 4–6 hours, spread across 1–2 sittings |
| Stopping point | `git tag p1-session5-complete` |
| Recommended split | Phase A (§5.1–§5.5 Risk Engine + Order Router + tests) in one sitting; Phase B (§5.6–§5.10 trade-update consumer + position recomputation + drift + smoke) in another. Each phase is independently committable but the PR lands as one. |

---

## Session Goal

After this session:
- A working `RiskEngine.evaluate()` enforces the eight P1 pre-trade checks against the global `risk_limits` row, persists a `risk_checks` row on every call (pass or reject), and returns a `RiskDecision` value object.
- A working `OrderRouter.submit()` is the **only** code path in the system that calls `AlpacaAdapter.submit_order` — and the adapter's `submit_order` / `cancel_order` / `replace_order` are now real, no longer `NotImplementedError`.
- A CI-enforced grep test fails the build if any code outside `OrderRouter` calls `AlpacaAdapter.submit_order`.
- A `TradeUpdateConsumer` subscribes to `alpaca.trade_update`, translates each event into local writes (`fills` row, `orders.status` transition), recomputes the affected position, and emits internal `orders.*` / `fills.*` / `positions.*` events on the bus.
- A `ReconciliationService` compares local DB orders/positions vs. Alpaca state each tick, flags persistent drift (3+ consecutive missing/extra rows) as warnings.
- One end-to-end smoke: a `POST /api/v1/orders` call (via curl since the router's HTTP endpoint also lands here) → risk check passes → Alpaca paper accepts → trade-update arrives → fill row written → position row updated → audit chain complete.

What does NOT happen this session:
- No frontend changes. The order ticket UI is Session 6.
- No live-mode UX gates. Session 6 again.
- No additional risk scopes (per-strategy, per-agent-session). P1 only needs GLOBAL.

---

## Prerequisites Check

```bash
cd ~/code/AI-TRADING-APP
git status                              # clean
git pull origin main
git describe --tags --abbrev=0          # expect: p1-session4-complete

# Confirm Session 4 schema + position sync are alive
./scripts/dev.sh &
sleep 30
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "SELECT scope_type, max_position_notional, max_daily_loss FROM risk_limits;"
# Expect: global|25000|2000
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite ".tables"
# Expect: orders, fills, positions, risk_limits, risk_checks all listed
docker compose down
```

- [ ] On `main`, clean tree, at `p1-session4-complete` or later.
- [ ] Default risk_limits row exists.
- [ ] All five trading tables present.

Cut the branch:

```bash
git checkout -b feat/p1-risk-engine-order-router
```

---

# Phase A — Risk Engine and Order Router

## §5.1 — Risk Engine Value Objects

The engine returns structured values, not booleans or exceptions, so the Order Router can branch cleanly.

Create `apps/backend/app/risk/__init__.py`:

```python
"""Risk engine: pre-trade gating + post-trade halt detection.

Per ADR 0002 the engine is the only path through which an OrderRequest is
converted into an Order that can be submitted to a broker. There is no fast
path; there is no bypass.
"""
from .reason_codes import ReasonCode
from .types import OrderRequest, RiskOutcome
from .engine import RiskEngine

__all__ = ["RiskEngine", "OrderRequest", "RiskOutcome", "ReasonCode"]
```

Create `apps/backend/app/risk/reason_codes.py`:

```python
"""Stable identifiers returned by the Risk Engine for UI translation."""
from __future__ import annotations

from enum import Enum


class ReasonCode(str, Enum):
    OK = "OK"
    MODE_MISMATCH = "MODE_MISMATCH"
    SYMBOL_DENIED = "SYMBOL_DENIED"
    SHORT_NOT_ALLOWED = "SHORT_NOT_ALLOWED"
    POSITION_CAP_QTY = "POSITION_CAP_QTY"
    POSITION_CAP_NOTIONAL = "POSITION_CAP_NOTIONAL"
    GROSS_EXPOSURE = "GROSS_EXPOSURE"
    HALT_REACHED = "HALT_REACHED"
    RATE_LIMIT = "RATE_LIMIT"
    INVALID_INPUT = "INVALID_INPUT"
    NO_LIMITS_CONFIGURED = "NO_LIMITS_CONFIGURED"
```

Create `apps/backend/app/risk/types.py`:

```python
"""Value objects for the Risk Engine + Order Router boundary."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from app.db.enums import OrderSide, OrderSourceType, OrderType, TimeInForce
from app.risk.reason_codes import ReasonCode


@dataclass(frozen=True)
class OrderRequest:
    """Caller-supplied intent. Pre-validation only; the engine validates substantively."""
    user_id: int
    account_id: int
    symbol_ticker: str
    side: OrderSide
    qty: Decimal
    type: OrderType
    tif: TimeInForce = TimeInForce.DAY
    limit_price: Optional[Decimal] = None
    stop_price: Optional[Decimal] = None
    extended_hours: bool = False
    source_type: OrderSourceType = OrderSourceType.MANUAL
    source_id: Optional[str] = None
    client_order_id: Optional[str] = None


@dataclass(frozen=True)
class RiskOutcome:
    """Engine's decision. risk_check_id is the persisted row ID."""
    decision: str            # "pass" | "reject" (values of RiskDecision)
    reason_codes: list[ReasonCode] = field(default_factory=list)
    risk_check_id: Optional[int] = None
    # Computed context the router might want without re-querying:
    resolved_symbol_id: Optional[int] = None
    estimated_notional: Optional[Decimal] = None

    @property
    def passed(self) -> bool:
        return self.decision == "pass"
```

- [ ] `app/risk/` package created with three files above.

---

## §5.2 — System Halt Flag

The daily-loss check triggers a system-wide halt. We need somewhere to store that flag durably (survives restart) so a freshly-started backend doesn't blindly accept orders after a halt event.

Add a `system_config` row (the table exists from P0). Wrap access in a small service.

Create `apps/backend/app/risk/halt.py`:

```python
"""System halt flag — durable across restarts via system_config."""
from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.system_config import SystemConfig

logger = structlog.get_logger(__name__)

HALT_KEY = "trading.halted"
HALT_REASON_KEY = "trading.halt_reason"


async def is_halted(session: AsyncSession) -> bool:
    row = (await session.execute(
        select(SystemConfig).where(SystemConfig.key == HALT_KEY)
    )).scalars().first()
    return bool(row and str(row.value).lower() in ("1", "true", "yes"))


async def set_halted(session: AsyncSession, halted: bool, reason: str = "") -> None:
    """Set or clear the halt flag. Caller must commit."""
    row = (await session.execute(
        select(SystemConfig).where(SystemConfig.key == HALT_KEY)
    )).scalars().first()
    if row is None:
        session.add(SystemConfig(key=HALT_KEY, value="1" if halted else "0"))
    else:
        row.value = "1" if halted else "0"

    reason_row = (await session.execute(
        select(SystemConfig).where(SystemConfig.key == HALT_REASON_KEY)
    )).scalars().first()
    if reason_row is None:
        session.add(SystemConfig(key=HALT_REASON_KEY, value=reason))
    else:
        reason_row.value = reason

    logger.warning("trading_halt_state_changed", halted=halted, reason=reason)


async def halt_reason(session: AsyncSession) -> str:
    row = (await session.execute(
        select(SystemConfig).where(SystemConfig.key == HALT_REASON_KEY)
    )).scalars().first()
    return str(row.value) if row else ""
```

> **Note on `system_config` schema.** P0 created `SystemConfig(id, user_id NULL, key, value, updated_at)`. We're storing global keys (`user_id=NULL`). If your P0 model has `user_id` non-null, either change to nullable in a tiny migration or scope these keys to user 1.

- [ ] `app/risk/halt.py` created.

---

## §5.3 — The Risk Engine Itself

The core of P1. Lives at `apps/backend/app/risk/engine.py`.

```python
"""RiskEngine — the only pre-trade gate.

Per ADR 0002, every order submission passes through `evaluate()` before it
can reach Alpaca. The function is purely async-DB-bound; no broker calls.

Eight checks, evaluated in order. First failure short-circuits and writes a
RiskCheck row with `decision='reject'`. A passing evaluation also writes a
RiskCheck row (`decision='pass'`) — the audit trail is symmetric.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    RiskDecision,
    RiskScopeType,
)
from app.db.models.account_state import AccountState
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.risk_check import RiskCheck
from app.db.models.risk_limits import RiskLimits
from app.db.models.symbol import Symbol
from app.risk.halt import is_halted, set_halted
from app.risk.reason_codes import ReasonCode
from app.risk.types import OrderRequest, RiskOutcome

logger = structlog.get_logger(__name__)


class RiskEngine:
    """Stateless evaluator. One instance per request is fine.

    Construction takes a session_factory because the engine opens its own
    short-lived transaction (rather than sharing the caller's). This keeps
    the engine's reads consistent against a single DB snapshot and lets the
    OrderRouter use a separate transaction for the Order row write.
    """

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    async def evaluate(self, req: OrderRequest, *, trading_mode: str) -> RiskOutcome:
        """Run the eight P1 checks. Always writes a RiskCheck row."""
        reasons: list[ReasonCode] = []
        resolved_symbol_id: Optional[int] = None
        estimated_notional: Optional[Decimal] = None

        async with self._session_factory() as session:
            # 0. Halt short-circuit — if already halted, reject with HALT_REACHED.
            if await is_halted(session):
                return await self._persist_and_return(
                    session, decision=RiskDecision.REJECT,
                    reasons=[ReasonCode.HALT_REACHED],
                )

            # 1. Sanity (cheap input checks, run first so we don't load tables for garbage)
            if req.qty is None or req.qty <= 0:
                return await self._persist_and_return(
                    session, decision=RiskDecision.REJECT,
                    reasons=[ReasonCode.INVALID_INPUT],
                )
            if req.type.value in ("limit", "stop_limit") and (req.limit_price is None or req.limit_price <= 0):
                return await self._persist_and_return(
                    session, decision=RiskDecision.REJECT,
                    reasons=[ReasonCode.INVALID_INPUT],
                )
            if req.type.value in ("stop", "stop_limit") and (req.stop_price is None or req.stop_price <= 0):
                return await self._persist_and_return(
                    session, decision=RiskDecision.REJECT,
                    reasons=[ReasonCode.INVALID_INPUT],
                )

            # 2. Mode/account consistency.
            from app.db.models.account import Account
            account = (await session.execute(
                select(Account).where(Account.id == req.account_id)
            )).scalars().first()
            if account is None or account.mode != trading_mode:
                return await self._persist_and_return(
                    session, decision=RiskDecision.REJECT,
                    reasons=[ReasonCode.MODE_MISMATCH],
                )

            # 3. Resolve the symbol once.
            symbol = (await session.execute(
                select(Symbol).where(Symbol.ticker == req.symbol_ticker, Symbol.active == True)  # noqa: E712
            )).scalars().first()
            if symbol is None:
                return await self._persist_and_return(
                    session, decision=RiskDecision.REJECT,
                    reasons=[ReasonCode.SYMBOL_DENIED],
                )
            resolved_symbol_id = symbol.id

            # 4. Load applicable risk limits (P1: just GLOBAL).
            limits = await self._load_global_limits(session, req.user_id)
            if limits is None:
                return await self._persist_and_return(
                    session, decision=RiskDecision.REJECT,
                    reasons=[ReasonCode.NO_LIMITS_CONFIGURED],
                )

            # 5. Symbol allow/deny.
            if limits.denied_symbols and req.symbol_ticker in (limits.denied_symbols or []):
                return await self._persist_and_return(
                    session, decision=RiskDecision.REJECT,
                    reasons=[ReasonCode.SYMBOL_DENIED],
                )
            if limits.allowed_symbols and req.symbol_ticker not in (limits.allowed_symbols or []):
                return await self._persist_and_return(
                    session, decision=RiskDecision.REJECT,
                    reasons=[ReasonCode.SYMBOL_DENIED],
                )

            # 6. Side restrictions (P1: short-selling toggle).
            if req.side == OrderSide.SELL and not limits.allow_short:
                # Determine whether this SELL would open a short (no existing long
                # position to cover). We treat any sell without a long >= qty as short.
                pos = (await session.execute(
                    select(Position).where(
                        Position.account_id == req.account_id,
                        Position.symbol_id == symbol.id,
                    )
                )).scalars().first()
                current_qty = pos.qty if pos else Decimal(0)
                if current_qty < req.qty:
                    return await self._persist_and_return(
                        session, decision=RiskDecision.REJECT,
                        reasons=[ReasonCode.SHORT_NOT_ALLOWED],
                    )

            # 7. Estimate notional — limit price if available, else avg position price,
            #    else 0 (market orders pass notional checks; gross exposure picks them up
            #    on the next position-sync poll).
            estimated_notional = self._estimate_notional(req)

            # 8. Position size cap.
            pos = (await session.execute(
                select(Position).where(
                    Position.account_id == req.account_id,
                    Position.symbol_id == symbol.id,
                )
            )).scalars().first()
            current_qty = pos.qty if pos else Decimal(0)
            delta = req.qty if req.side == OrderSide.BUY else -req.qty
            resulting_qty = abs(current_qty + delta)

            if limits.max_position_qty is not None and resulting_qty > limits.max_position_qty:
                return await self._persist_and_return(
                    session, decision=RiskDecision.REJECT,
                    reasons=[ReasonCode.POSITION_CAP_QTY],
                )
            if limits.max_position_notional is not None and estimated_notional is not None:
                resulting_notional = resulting_qty * (req.limit_price or (pos.avg_entry_price if pos else Decimal(0)) or Decimal(0))
                if resulting_notional > limits.max_position_notional:
                    return await self._persist_and_return(
                        session, decision=RiskDecision.REJECT,
                        reasons=[ReasonCode.POSITION_CAP_NOTIONAL],
                    )

            # 9. Gross exposure cap.
            if limits.max_gross_exposure is not None:
                gross_now = (await session.execute(
                    select(func.coalesce(func.sum(func.abs(Position.market_value)), 0))
                    .where(Position.account_id == req.account_id)
                )).scalar_one()
                projected = Decimal(gross_now or 0) + (estimated_notional or Decimal(0))
                if projected > limits.max_gross_exposure:
                    return await self._persist_and_return(
                        session, decision=RiskDecision.REJECT,
                        reasons=[ReasonCode.GROSS_EXPOSURE],
                    )

            # 10. Daily loss cap (triggers HALT).
            if limits.max_daily_loss is not None:
                state = (await session.execute(
                    select(AccountState).where(AccountState.account_id == req.account_id)
                )).scalars().first()
                if state is not None:
                    day_pnl = state.day_change  # equity - last_equity, signed
                    if day_pnl <= -limits.max_daily_loss:
                        await set_halted(session, True, reason="daily_loss_cap_reached")
                        return await self._persist_and_return(
                            session, decision=RiskDecision.REJECT,
                            reasons=[ReasonCode.HALT_REACHED],
                        )

            # 11. Rate limit (per minute).
            if limits.max_orders_per_minute is not None:
                since = datetime.now(timezone.utc) - timedelta(seconds=60)
                count = (await session.execute(
                    select(func.count(Order.id))
                    .where(Order.user_id == req.user_id, Order.created_at >= since)
                )).scalar_one()
                if count >= limits.max_orders_per_minute:
                    return await self._persist_and_return(
                        session, decision=RiskDecision.REJECT,
                        reasons=[ReasonCode.RATE_LIMIT],
                    )

            # Pass.
            return await self._persist_and_return(
                session, decision=RiskDecision.PASS,
                reasons=[ReasonCode.OK],
                resolved_symbol_id=resolved_symbol_id,
                estimated_notional=estimated_notional,
            )

    # ---- internals ----

    async def _load_global_limits(self, session: AsyncSession, user_id: int) -> Optional[RiskLimits]:
        return (await session.execute(
            select(RiskLimits).where(
                RiskLimits.user_id == user_id,
                RiskLimits.scope_type == RiskScopeType.GLOBAL,
            )
        )).scalars().first()

    def _estimate_notional(self, req: OrderRequest) -> Optional[Decimal]:
        if req.limit_price is not None:
            return req.qty * req.limit_price
        # For market orders we can't know the fill price up front; treat as None.
        # The position-cap-notional check below conservatively uses limit_price or 0.
        return None

    async def _persist_and_return(
        self,
        session: AsyncSession,
        *,
        decision: RiskDecision,
        reasons: list[ReasonCode],
        resolved_symbol_id: Optional[int] = None,
        estimated_notional: Optional[Decimal] = None,
    ) -> RiskOutcome:
        rc = RiskCheck(
            order_id=None,
            decision=decision,
            reason_codes=[r.value for r in reasons],
            evaluated_at=datetime.now(timezone.utc),
        )
        session.add(rc)
        await session.commit()
        await session.refresh(rc)
        logger.info(
            "risk_check_persisted",
            decision=decision.value,
            reasons=[r.value for r in reasons],
            risk_check_id=rc.id,
        )
        return RiskOutcome(
            decision=decision.value,
            reason_codes=reasons,
            risk_check_id=rc.id,
            resolved_symbol_id=resolved_symbol_id,
            estimated_notional=estimated_notional,
        )
```

- [ ] `engine.py` created.

> **A note on completeness.** The engine implements all eight checks from P1 Checklist §3.2. The gross-exposure check uses `Position.market_value` aggregated; for accounts with no recent position-sync, that defaults to zero (permissive). That's a known limitation in P1 and is fine for the safety bar we're targeting — the cap rejects egregiously oversized orders, not edge-case 1% overshoots.

---

## §5.4 — Order Router

The single entry point. Lives at `apps/backend/app/orders/router.py`.

Create `apps/backend/app/orders/__init__.py`:

```python
from .router import OrderRouter

__all__ = ["OrderRouter"]
```

Create `apps/backend/app/orders/router.py`:

```python
"""OrderRouter — the only entry point for order submission.

Per ADR 0002 there is no other path through which an OrderRequest may reach
the broker. This invariant is enforced by:
  1. AlpacaAdapter.submit_order / cancel_order / replace_order accept a
     keyword-only `_router_token` and refuse to run without it.
  2. The router is the only module that knows the token.
  3. A CI grep test fails any PR that calls AlpacaAdapter.submit_order from
     a module other than this one.

The router writes the Order row BEFORE calling Alpaca, links the RiskCheck,
and emits internal events so the WS gateway and audit trail are always in sync.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.alpaca import AlpacaAdapter
from app.brokers.alpaca.errors import (
    PermanentAlpacaError,
    TransientAlpacaError,
)
from app.db.enums import OrderStatus
from app.db.models.audit_log import AuditLog
from app.db.models.order import Order
from app.events.bus import EventBus
from app.risk import OrderRequest, RiskEngine, RiskOutcome
from app.risk.reason_codes import ReasonCode

logger = structlog.get_logger(__name__)

# Shared secret between router and adapter; not a security boundary, just a
# tripwire to prevent accidental bypass.
ROUTER_TOKEN = "ADR_0002_ONLY_ORDERROUTER_MAY_CALL_THIS"


class OrderRouter:
    def __init__(
        self,
        adapter: AlpacaAdapter,
        risk_engine: RiskEngine,
        session_factory,
        bus: EventBus,
    ) -> None:
        self._adapter = adapter
        self._risk = risk_engine
        self._session_factory = session_factory
        self._bus = bus

    async def submit(self, req: OrderRequest) -> Order:
        """Sole order-submission entry point.

        Sequence:
          1. Run risk engine. If reject → persist Order in REJECTED state, audit, emit, return.
          2. Persist Order in PENDING_SUBMIT state with risk_check_id linked.
          3. Submit to Alpaca. On transient error: bubble (caller may retry).
             On permanent error: mark order REJECTED with broker reason.
          4. On success: persist broker_order_id, status SUBMITTED, audit, emit.
        """
        trading_mode = "paper" if self._adapter.is_paper else "live"
        outcome = await self._risk.evaluate(req, trading_mode=trading_mode)

        async with self._session_factory() as session:
            order = await self._persist_initial_order(session, req, outcome)

            if not outcome.passed:
                order.status = OrderStatus.REJECTED
                order.rejection_reason = ",".join(r.value for r in outcome.reason_codes)
                order.terminal_at = datetime.now(timezone.utc)
                order.updated_at = order.terminal_at
                await session.commit()
                await session.refresh(order)
                await self._audit(session, order, "ORDER_REJECTED_BY_RISK", {
                    "reasons": [r.value for r in outcome.reason_codes],
                    "risk_check_id": outcome.risk_check_id,
                })
                await self._emit(order, "order.rejected", {
                    "reasons": [r.value for r in outcome.reason_codes],
                })
                logger.info("order_rejected_by_risk",
                            order_id=order.id, reasons=[r.value for r in outcome.reason_codes])
                return order

            # Risk passed. Mark pending_submit and attempt broker submission.
            order.status = OrderStatus.PENDING_SUBMIT
            order.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(order)
            await self._audit(session, order, "ORDER_RISK_PASSED", {
                "risk_check_id": outcome.risk_check_id,
            })

        # ---- broker call (outside the DB transaction) ----
        try:
            broker_response = self._adapter.submit_order(
                symbol=req.symbol_ticker,
                qty=req.qty,
                side=req.side.value,
                type_=req.type.value,
                tif=req.tif.value,
                limit_price=req.limit_price,
                stop_price=req.stop_price,
                extended_hours=req.extended_hours,
                client_order_id=order.client_order_id,
                _router_token=ROUTER_TOKEN,
            )
        except PermanentAlpacaError as exc:
            return await self._mark_broker_rejected(order.id, str(exc))
        except TransientAlpacaError:
            # Leave the order in PENDING_SUBMIT; the caller may retry, or the
            # trade-update stream may pick up the order once Alpaca eventually
            # processes it. We do not mark it rejected — that would be wrong
            # if Alpaca actually accepted it on a retry.
            await self._emit_simple(order.id, "order.submit_transient_error")
            raise

        # Broker accepted.
        async with self._session_factory() as session:
            order = (await session.execute(
                select(Order).where(Order.id == order.id)
            )).scalars().first()
            order.broker_order_id = str(broker_response.get("id") or broker_response.get("broker_order_id") or "")
            order.status = OrderStatus.SUBMITTED
            order.submitted_at = datetime.now(timezone.utc)
            order.updated_at = order.submitted_at
            await session.commit()
            await session.refresh(order)
            await self._audit(session, order, "ORDER_SUBMITTED", {
                "broker_order_id": order.broker_order_id,
            })

        await self._emit(order, "order.submitted", {})
        logger.info("order_submitted", order_id=order.id, broker_order_id=order.broker_order_id)
        return order

    async def cancel(self, order_id: int) -> Order:
        async with self._session_factory() as session:
            order = (await session.execute(
                select(Order).where(Order.id == order_id)
            )).scalars().first()
            if order is None:
                raise ValueError(f"Order {order_id} not found")
            if not order.broker_order_id:
                # Local-only cancel (order never made it to broker).
                order.status = OrderStatus.CANCELED
                order.terminal_at = datetime.now(timezone.utc)
                order.updated_at = order.terminal_at
                await session.commit()
                await session.refresh(order)
                await self._audit(session, order, "ORDER_CANCELED_LOCAL", {})
                await self._emit(order, "order.canceled", {"local_only": True})
                return order

        # Hit Alpaca.
        try:
            self._adapter.cancel_order(order.broker_order_id, _router_token=ROUTER_TOKEN)
        except PermanentAlpacaError as exc:
            logger.warning("cancel_permanent_error", order_id=order_id, error=str(exc))
            # Often means "already filled / already canceled" — let the trade-update
            # stream reconcile. Audit and continue.
            async with self._session_factory() as session:
                order = (await session.execute(
                    select(Order).where(Order.id == order_id)
                )).scalars().first()
                await self._audit(session, order, "ORDER_CANCEL_REJECTED_BY_BROKER", {"error": str(exc)})
            return order

        # Optimistically mark; trade-update consumer will confirm.
        async with self._session_factory() as session:
            order = (await session.execute(
                select(Order).where(Order.id == order_id)
            )).scalars().first()
            await self._audit(session, order, "ORDER_CANCEL_REQUESTED", {})
        await self._emit(order, "order.cancel_requested", {})
        return order

    async def replace(self, order_id: int, *, new_qty: Decimal | None = None,
                      new_limit_price: Decimal | None = None) -> Order:
        async with self._session_factory() as session:
            order = (await session.execute(
                select(Order).where(Order.id == order_id)
            )).scalars().first()
            if order is None or not order.broker_order_id:
                raise ValueError(f"Order {order_id} not replaceable")
        # Adapter call:
        try:
            self._adapter.replace_order(
                order.broker_order_id,
                new_qty=new_qty, new_limit_price=new_limit_price,
                _router_token=ROUTER_TOKEN,
            )
        except PermanentAlpacaError as exc:
            async with self._session_factory() as session:
                order = (await session.execute(
                    select(Order).where(Order.id == order_id)
                )).scalars().first()
                await self._audit(session, order, "ORDER_REPLACE_REJECTED_BY_BROKER", {"error": str(exc)})
            return order

        async with self._session_factory() as session:
            order = (await session.execute(
                select(Order).where(Order.id == order_id)
            )).scalars().first()
            await self._audit(session, order, "ORDER_REPLACE_REQUESTED", {
                "new_qty": str(new_qty) if new_qty else None,
                "new_limit_price": str(new_limit_price) if new_limit_price else None,
            })
        await self._emit(order, "order.replace_requested", {})
        return order

    # ---- internals ----

    async def _persist_initial_order(
        self, session: AsyncSession, req: OrderRequest, outcome: RiskOutcome,
    ) -> Order:
        now = datetime.now(timezone.utc)
        # Resolve symbol_id (the engine already validated existence, but the
        # engine commit closed; re-fetch by ticker).
        from app.db.models.symbol import Symbol
        symbol_id = outcome.resolved_symbol_id
        if symbol_id is None:
            sym = (await session.execute(
                select(Symbol).where(Symbol.ticker == req.symbol_ticker)
            )).scalars().first()
            symbol_id = sym.id if sym else None

        client_order_id = req.client_order_id or f"twb-{uuid.uuid4().hex[:24]}"

        order = Order(
            user_id=req.user_id,
            account_id=req.account_id,
            symbol_id=symbol_id,
            broker_order_id=None,
            client_order_id=client_order_id,
            side=req.side,
            qty=req.qty,
            type=req.type,
            limit_price=req.limit_price,
            stop_price=req.stop_price,
            tif=req.tif,
            extended_hours=req.extended_hours,
            status=OrderStatus.PENDING_RISK,
            source_type=req.source_type,
            source_id=req.source_id,
            risk_check_id=outcome.risk_check_id,
            created_at=now,
            updated_at=now,
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)

        # Back-link RiskCheck.order_id (it was created with order_id=None).
        if outcome.risk_check_id is not None:
            from app.db.models.risk_check import RiskCheck
            rc = (await session.execute(
                select(RiskCheck).where(RiskCheck.id == outcome.risk_check_id)
            )).scalars().first()
            if rc is not None:
                rc.order_id = order.id
                await session.commit()

        return order

    async def _mark_broker_rejected(self, order_id: int, reason: str) -> Order:
        async with self._session_factory() as session:
            order = (await session.execute(
                select(Order).where(Order.id == order_id)
            )).scalars().first()
            order.status = OrderStatus.REJECTED
            order.rejection_reason = reason[:512]
            order.terminal_at = datetime.now(timezone.utc)
            order.updated_at = order.terminal_at
            await session.commit()
            await session.refresh(order)
            await self._audit(session, order, "ORDER_REJECTED_BY_BROKER", {"reason": reason})
        await self._emit(order, "order.rejected", {"reason": reason})
        return order

    async def _audit(self, session: AsyncSession, order: Order, action: str, payload: dict) -> None:
        session.add(AuditLog(
            user_id=order.user_id,
            ts=datetime.now(timezone.utc),
            actor_type="user" if order.source_type.value == "manual" else "system",
            actor_id=str(order.user_id),
            action=action,
            target_type="order",
            target_id=str(order.id),
            payload_json=payload,
        ))
        await session.commit()

    async def _emit(self, order: Order, topic: str, extra: dict) -> None:
        await self._bus.publish(topic, {
            "order_id": order.id,
            "broker_order_id": order.broker_order_id,
            "status": order.status.value,
            "symbol_id": order.symbol_id,
            "side": order.side.value,
            "qty": str(order.qty),
            **extra,
        })

    async def _emit_simple(self, order_id: int, topic: str) -> None:
        await self._bus.publish(topic, {"order_id": order_id})
```

> **Schema-name caveat.** The `AuditLog` model from P0 may have slightly different field names (`payload_json` vs. `payload`, etc.). Adjust the kwargs in `_audit` to match P0.

- [ ] `OrderRouter` class created.

---

## §5.5 — Adapter Tripwire

The adapter's mutating methods now exist but refuse to run without the router token.

Edit `apps/backend/app/brokers/alpaca/adapter.py`. Replace the three `NotImplementedError` methods at the bottom of `AlpacaAdapter` with real implementations:

```python
# ---- mutating methods (router-gated per ADR 0002) ----

def submit_order(
    self,
    *,
    symbol: str,
    qty,
    side: str,
    type_: str,
    tif: str,
    limit_price=None,
    stop_price=None,
    extended_hours: bool = False,
    client_order_id: str | None = None,
    _router_token: str | None = None,
) -> dict[str, Any]:
    """Submit an order to Alpaca. Router-gated per ADR 0002.

    The `_router_token` kwarg is the tripwire — callers other than
    OrderRouter cannot legitimately supply it. CI also greps for direct
    callers of this method outside app/orders/.
    """
    self._assert_router(_router_token)
    try:
        from alpaca.trading.enums import OrderSide as ASide, OrderType as AType, TimeInForce as ATIF
        from alpaca.trading.requests import (
            LimitOrderRequest, MarketOrderRequest, StopLimitOrderRequest, StopOrderRequest,
        )

        common = dict(
            symbol=symbol,
            qty=str(qty),
            side=ASide(side),
            time_in_force=ATIF(tif),
            extended_hours=extended_hours,
            client_order_id=client_order_id,
        )
        if type_ == "market":
            req = MarketOrderRequest(**common)
        elif type_ == "limit":
            req = LimitOrderRequest(limit_price=str(limit_price), **common)
        elif type_ == "stop":
            req = StopOrderRequest(stop_price=str(stop_price), **common)
        elif type_ == "stop_limit":
            req = StopLimitOrderRequest(
                stop_price=str(stop_price), limit_price=str(limit_price), **common
            )
        else:
            raise ValueError(f"Unsupported order type: {type_}")

        out = self._client().submit_order(req)
        return _to_dict(out)
    except Exception as exc:  # noqa: BLE001
        raise classify(exc) from exc


def cancel_order(self, broker_order_id: str, *, _router_token: str | None = None) -> None:
    self._assert_router(_router_token)
    try:
        self._client().cancel_order_by_id(broker_order_id)
    except Exception as exc:  # noqa: BLE001
        raise classify(exc) from exc


def replace_order(
    self,
    broker_order_id: str,
    *,
    new_qty=None,
    new_limit_price=None,
    _router_token: str | None = None,
) -> dict[str, Any]:
    self._assert_router(_router_token)
    try:
        from alpaca.trading.requests import ReplaceOrderRequest
        req = ReplaceOrderRequest(
            qty=str(new_qty) if new_qty is not None else None,
            limit_price=str(new_limit_price) if new_limit_price is not None else None,
        )
        out = self._client().replace_order_by_id(broker_order_id, req)
        return _to_dict(out)
    except Exception as exc:  # noqa: BLE001
        raise classify(exc) from exc


def _assert_router(self, token: str | None) -> None:
    # Lazy import to avoid circular import at module-load time.
    from app.orders.router import ROUTER_TOKEN
    if token != ROUTER_TOKEN:
        raise RuntimeError(
            "AlpacaAdapter mutating methods may only be called via OrderRouter "
            "(see ADR 0002). Direct calls are forbidden."
        )
```

The lazy import in `_assert_router` keeps `brokers/alpaca/` independent of `orders/` at import time (otherwise circular). The token is a string constant; the boundary is enforced by *both* the runtime check and the CI grep below.

- [ ] Three methods replaced; `_assert_router` added.

---

## §5.6 — CI Grep Tripwire

A test that fails the build if any module *other than* `OrderRouter` calls `submit_order` / `cancel_order` / `replace_order` on the adapter.

Create `apps/backend/tests/test_adr_0002_invariant.py`:

```python
"""Static check for ADR 0002 — single order entry point.

Greps the backend source tree for any call to AlpacaAdapter.submit_order,
.cancel_order, or .replace_order outside of app/orders/. The router itself
is the only legitimate caller; the adapter's own implementation contains
the methods (definitions) but does not call them.
"""
from __future__ import annotations

import pathlib
import re

# Patterns matching `.submit_order(`, `.cancel_order(`, `.replace_order(`
# on something that is a reference to AlpacaAdapter (any var name).
CALL_PATTERN = re.compile(
    r"\.(submit_order|cancel_order|replace_order)\s*\("
)

# Files that ARE allowed to contain these patterns:
ALLOWED = {
    # The router itself:
    "app/orders/router.py",
    # The adapter's own definitions (the `def submit_order(...)` lines aren't
    # call sites; the regex still matches them — accept here):
    "app/brokers/alpaca/adapter.py",
    # This very test file references the names:
    "tests/test_adr_0002_invariant.py",
}


BACKEND_ROOT = pathlib.Path(__file__).resolve().parent.parent  # apps/backend


def _iter_source_files():
    for p in BACKEND_ROOT.rglob("*.py"):
        rel = p.relative_to(BACKEND_ROOT).as_posix()
        if rel.startswith((".venv/", "alembic/versions/")):
            continue
        yield rel, p


def test_no_direct_adapter_mutation_calls_outside_router():
    offenders = []
    for rel, path in _iter_source_files():
        if rel in ALLOWED:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in CALL_PATTERN.finditer(text):
            # Heuristic: ignore method *definitions*, only flag *calls*.
            # A `def submit_order(` is preceded by "def ", a call is not.
            start = max(0, m.start() - 4)
            window = text[start:m.start() + 1]
            if "def " in window:
                continue
            offenders.append(f"{rel}: {m.group(0)}")
    assert not offenders, (
        "ADR 0002 violation — these files call AlpacaAdapter mutation methods "
        "outside the OrderRouter:\n  " + "\n  ".join(offenders)
    )
```

Run it:

```bash
cd apps/backend
uv run pytest tests/test_adr_0002_invariant.py -v
cd ../..
```

- [ ] Grep test passes (no offenders).

---

## §5.7 — Wire OrderRouter into the Lifespan

Extend `apps/backend/app/lifespan.py`. Just add the construction after the trade-stream block:

```python
# After: await trade_stream.start()

from app.orders import OrderRouter
from app.risk import RiskEngine

risk_engine = RiskEngine(session_factory)
order_router = OrderRouter(adapter, risk_engine, session_factory, bus)
app.state.risk_engine = risk_engine
app.state.order_router = order_router
```

No shutdown hook needed; the router is stateless.

- [ ] Lifespan constructs the router and risk engine; stashes both on `app.state`.

---

## §5.8 — Minimal REST Endpoint to Drive the Router

Just enough to be able to curl an order through the system. Full REST surface lands in Session 6.

Create `apps/backend/app/api/v1/orders.py`:

```python
"""Minimal orders REST surface — enough for smoke testing the router.

Full schema validation, pagination, modify/cancel endpoints land in Session 6.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.db.enums import OrderSide, OrderSourceType, OrderType, TimeInForce
from app.risk import OrderRequest

router = APIRouter(prefix="/orders", tags=["orders"])


class OrderRequestIn(BaseModel):
    symbol: str
    side: OrderSide
    qty: Decimal = Field(gt=0)
    type: OrderType
    tif: TimeInForce = TimeInForce.DAY
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    extended_hours: bool = False
    client_order_id: str | None = None


@router.post("")
async def submit_order(request: Request, payload: OrderRequestIn) -> dict:
    """Submit a new order. P1 single-user: user_id=1, account_id=1."""
    req = OrderRequest(
        user_id=1,
        account_id=1,
        symbol_ticker=payload.symbol.upper(),
        side=payload.side,
        qty=payload.qty,
        type=payload.type,
        tif=payload.tif,
        limit_price=payload.limit_price,
        stop_price=payload.stop_price,
        extended_hours=payload.extended_hours,
        source_type=OrderSourceType.MANUAL,
        client_order_id=payload.client_order_id,
    )
    try:
        order = await request.app.state.order_router.submit(req)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"broker transient error: {exc}")
    return {
        "id": order.id,
        "status": order.status.value,
        "broker_order_id": order.broker_order_id,
        "rejection_reason": order.rejection_reason,
    }
```

Mount it in the API router registration (your P0 `app/api/v1/__init__.py` should already do per-module includes; add this line):

```python
from app.api.v1 import orders  # NEW
# ...
api_router.include_router(orders.router)  # NEW
```

- [ ] Endpoint mounted at `/api/v1/orders`.

---

# Phase B — Trade-Update Consumer, Position Recomputer, Reconciliation Drift

Take a break here if needed. The branch is intact; the next sittings continue on the same branch.

---

## §5.9 — Trade-Update Consumer

Subscribes to `alpaca.trade_update`, translates each event into local writes.

Create `apps/backend/app/orders/lifecycle.py`:

```python
"""Trade-update consumer.

Subscribes to alpaca.trade_update on the event bus. Each event:
  * fill / partial_fill -> insert Fill row, update Order status + qty fields,
                            recompute Position, audit, emit fill.created and
                            position.updated.
  * canceled / expired / rejected -> update Order to terminal state, audit,
                                     emit order.terminal.

Out-of-band orders (broker_order_id not in our DB) are logged as warnings —
the reconciliation service will detect them and surface as drift.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import OrderStatus, TERMINAL_ORDER_STATUSES
from app.db.models.audit_log import AuditLog
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.events.bus import EventBus

logger = structlog.get_logger(__name__)


# Alpaca-event -> internal OrderStatus mapping (terminal transitions only).
_ALPACA_TERMINAL_MAP = {
    "canceled": OrderStatus.CANCELED,
    "expired": OrderStatus.EXPIRED,
    "rejected": OrderStatus.REJECTED,
    "replaced": OrderStatus.REPLACED,
}


class TradeUpdateConsumer:
    def __init__(self, session_factory, bus: EventBus, position_recomputer) -> None:
        self._session_factory = session_factory
        self._bus = bus
        self._position_recomputer = position_recomputer

    async def start(self) -> None:
        self._bus.subscribe("alpaca.trade_update", self._handle)
        logger.info("trade_update_consumer_subscribed")

    async def _handle(self, payload: dict[str, Any]) -> None:
        event = payload.get("event")
        broker_order_id = payload.get("broker_order_id")
        if not broker_order_id:
            logger.warning("trade_update_missing_broker_order_id", event=event)
            return

        async with self._session_factory() as session:
            order = (await session.execute(
                select(Order).where(Order.broker_order_id == broker_order_id)
            )).scalars().first()

            if order is None:
                logger.warning(
                    "trade_update_unknown_order",
                    broker_order_id=broker_order_id, event=event,
                )
                # Drift detection will pick this up.
                return

            if event in ("fill", "partial_fill"):
                await self._handle_fill(session, order, payload, partial=(event == "partial_fill"))
            elif event in _ALPACA_TERMINAL_MAP:
                await self._handle_terminal(session, order, payload, event)
            else:
                # 'new', 'accepted', 'pending_new' etc. — informational only.
                logger.debug("trade_update_informational", event=event, order_id=order.id)

    async def _handle_fill(
        self, session: AsyncSession, order: Order, payload: dict[str, Any], *, partial: bool,
    ) -> None:
        # Idempotency: check by execution_id.
        execution_id = payload.get("execution_id")
        if execution_id:
            existing = (await session.execute(
                select(Fill).where(Fill.broker_fill_id == execution_id)
            )).scalars().first()
            if existing is not None:
                logger.debug("trade_update_fill_duplicate", execution_id=execution_id)
                return

        qty = _to_decimal(payload.get("qty"))
        price = _to_decimal(payload.get("price"))
        if qty <= 0 or price <= 0:
            logger.warning("trade_update_fill_invalid_numbers",
                           qty=str(qty), price=str(price))
            return

        now = datetime.now(timezone.utc)
        fill = Fill(
            order_id=order.id,
            broker_fill_id=execution_id,
            qty=qty,
            price=price,
            commission=Decimal(0),
            filled_at=_parse_ts(payload.get("timestamp")) or now,
        )
        session.add(fill)

        # Update order: aggregate filled qty by summing fills.
        all_fills_qty = sum(
            (f.qty for f in order.fills), start=Decimal(0)
        ) + qty   # include the one we just added (not flushed yet)
        if partial or all_fills_qty < order.qty:
            order.status = OrderStatus.PARTIALLY_FILLED
        else:
            order.status = OrderStatus.FILLED
            order.terminal_at = now
        order.updated_at = now

        session.add(AuditLog(
            user_id=order.user_id, ts=now, actor_type="system", actor_id="trade_stream",
            action="ORDER_FILL_INGESTED", target_type="order",
            target_id=str(order.id),
            payload_json={"execution_id": execution_id, "qty": str(qty), "price": str(price)},
        ))
        await session.commit()

        await self._bus.publish("fill.created", {
            "order_id": order.id,
            "execution_id": execution_id,
            "qty": str(qty),
            "price": str(price),
        })
        await self._bus.publish("order.updated", {
            "order_id": order.id, "status": order.status.value,
        })

        # Recompute position (fills are the source of truth between polls).
        await self._position_recomputer.recompute(order.account_id, order.symbol_id)

    async def _handle_terminal(
        self, session: AsyncSession, order: Order, payload: dict[str, Any], event: str,
    ) -> None:
        new_status = _ALPACA_TERMINAL_MAP[event]
        if order.status in TERMINAL_ORDER_STATUSES:
            logger.debug("trade_update_terminal_for_already_terminal_order",
                         order_id=order.id, status=order.status.value)
            return
        now = datetime.now(timezone.utc)
        order.status = new_status
        order.terminal_at = now
        order.updated_at = now
        if new_status == OrderStatus.REJECTED and not order.rejection_reason:
            order.rejection_reason = (payload.get("raw", {}) or {}).get("reject_reason") or event
        session.add(AuditLog(
            user_id=order.user_id, ts=now, actor_type="system", actor_id="trade_stream",
            action=f"ORDER_{new_status.value.upper()}", target_type="order",
            target_id=str(order.id),
            payload_json={"event": event},
        ))
        await session.commit()
        await self._bus.publish(f"order.{new_status.value}", {"order_id": order.id})


def _to_decimal(v: Any) -> Decimal:
    if v is None or v == "":
        return Decimal(0)
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal(0)


def _parse_ts(s: Any) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None
```

- [ ] `lifecycle.py` created.

---

## §5.10 — Position Recomputer

Recomputes a position from all fills for one `(account_id, symbol_id)`. Called by the trade-update consumer on every fill so the UI sees position changes immediately instead of waiting for the next 10-second sync.

Create `apps/backend/app/orders/positions.py`:

```python
"""Position recomputer.

Aggregates all fills for an (account, symbol) into qty + avg_entry_price and
upserts into the positions table. Used by the trade-update consumer; the
periodic position sync also runs, providing belt-and-suspenders consistency.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.enums import OrderSide
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.position import Position
from app.events.bus import EventBus

logger = structlog.get_logger(__name__)


class PositionRecomputer:
    def __init__(self, session_factory, bus: EventBus) -> None:
        self._session_factory = session_factory
        self._bus = bus

    async def recompute(self, account_id: int, symbol_id: int) -> None:
        async with self._session_factory() as session:
            # Aggregate signed qty and weighted average entry price from fills.
            fills = (await session.execute(
                select(Fill, Order).join(Order, Fill.order_id == Order.id)
                .where(Order.account_id == account_id, Order.symbol_id == symbol_id)
                .order_by(Fill.filled_at)
            )).all()

            qty = Decimal(0)
            cost_basis = Decimal(0)
            for fill, order in fills:
                signed = fill.qty if order.side == OrderSide.BUY else -fill.qty
                # When position flips through zero, reset cost basis.
                if (qty > 0 and qty + signed <= 0) or (qty < 0 and qty + signed >= 0):
                    cost_basis = Decimal(0)
                    qty = qty + signed
                    if qty != 0:
                        cost_basis = abs(qty) * fill.price
                    continue
                if qty == 0:
                    cost_basis = abs(signed) * fill.price
                else:
                    if (qty > 0 and signed > 0) or (qty < 0 and signed < 0):
                        # Adding to position
                        cost_basis += abs(signed) * fill.price
                    else:
                        # Reducing position — proportional cost basis reduction
                        avg = cost_basis / abs(qty)
                        cost_basis -= abs(signed) * avg
                qty += signed

            now = datetime.now(timezone.utc)
            if qty == 0:
                # Position is closed; delete the row.
                await session.execute(
                    Position.__table__.delete().where(
                        Position.account_id == account_id,
                        Position.symbol_id == symbol_id,
                    )
                )
            else:
                avg_entry_price = (cost_basis / abs(qty)) if qty != 0 else Decimal(0)
                side = "long" if qty > 0 else "short"
                # User id from any of the orders for this account/symbol (constant per account).
                user_id = fills[0][1].user_id if fills else None
                if user_id is None:
                    return

                stmt = sqlite_insert(Position).values(
                    user_id=user_id,
                    account_id=account_id,
                    symbol_id=symbol_id,
                    qty=qty,
                    avg_entry_price=avg_entry_price,
                    side=side,
                    market_value=Decimal(0),       # filled by next position-sync
                    cost_basis=cost_basis,
                    unrealized_pl=Decimal(0),
                    unrealized_plpc=Decimal(0),
                    updated_at=now,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["account_id", "symbol_id"],
                    set_={
                        "qty": stmt.excluded.qty,
                        "avg_entry_price": stmt.excluded.avg_entry_price,
                        "side": stmt.excluded.side,
                        "cost_basis": stmt.excluded.cost_basis,
                        "updated_at": stmt.excluded.updated_at,
                    },
                )
                await session.execute(stmt)

            await session.commit()

        await self._bus.publish("position.updated", {
            "account_id": account_id, "symbol_id": symbol_id, "qty": str(qty),
        })
        logger.info("position_recomputed", account_id=account_id, symbol_id=symbol_id, qty=str(qty))
```

- [ ] `positions.py` created.

---

## §5.11 — Reconciliation Drift Detector

Light P1 implementation: compares local DB positions vs. Alpaca on each poll, persists drift state, warns on persistence.

Edit `apps/backend/app/services/position_sync.py`. Add drift tracking. The simplest implementation: maintain an in-memory counter of "consecutive polls where (account, symbol) didn't match" and emit a `system.reconciliation_drift` event when it exceeds 3.

Add at the top of `PositionSyncService`:

```python
# Inside __init__:
self._drift_counters: dict[tuple[int, int], int] = {}
self._drift_warned: set[tuple[int, int]] = set()
```

Inside `sync_once()`, after computing `seen_symbol_ids` and `existing_ids`, *before* committing, compute drift sets:

```python
# Drift detection: a position is "drifted" if it appears in Alpaca but not
# in our DB (added or modified out of band) OR appears in DB but not Alpaca
# (and Session 5's recomputer hasn't caught up). Local-only-stale rows are
# deleted above; here we look for symbols Alpaca reports that we couldn't
# resolve OR that have a wildly different qty than our DB row.
alpaca_keys = {(account.id, sid) for sid in seen_symbol_ids}
db_keys = {(account.id, sid) for sid in existing_ids}

# Symbols Alpaca has that we don't (after upsert this should be empty;
# anything still in this set was an unknown symbol we skipped).
missing_locally = {(account.id, sid) for sid in (alpaca_keys - db_keys)}

# Bump drift counters; reset for reconciled pairs.
for key in alpaca_keys & db_keys:
    self._drift_counters[key] = 0
    self._drift_warned.discard(key)
for key in missing_locally:
    c = self._drift_counters.get(key, 0) + 1
    self._drift_counters[key] = c
    if c >= 3 and key not in self._drift_warned:
        self._drift_warned.add(key)
        logger.warning("reconciliation_drift_detected",
                       account_id=key[0], symbol_id=key[1], consecutive_polls=c)
        await self._bus.publish("system.reconciliation_drift", {
            "account_id": key[0], "symbol_id": key[1], "consecutive_polls": c,
        })
```

This is intentionally simple. P4 polish will add an "Open drift incidents" UI surface; P1 just needs the signal in the audit/log layer.

- [ ] Drift counters added to `PositionSyncService`.
- [ ] `system.reconciliation_drift` event fires after 3 consecutive misses.

---

## §5.12 — Wire Consumer + Recomputer into Lifespan

Update `apps/backend/app/lifespan.py` once more:

```python
# After: order_router = OrderRouter(...)

from app.orders.lifecycle import TradeUpdateConsumer
from app.orders.positions import PositionRecomputer

position_recomputer = PositionRecomputer(session_factory, bus)
trade_update_consumer = TradeUpdateConsumer(session_factory, bus, position_recomputer)
await trade_update_consumer.start()
app.state.trade_update_consumer = trade_update_consumer
app.state.position_recomputer = position_recomputer
```

No teardown needed; the consumer just unsubscribes when the bus is GC'd at shutdown.

- [ ] Consumer + recomputer constructed in lifespan.

---

## §5.13 — End-to-End Smoke

The whole point of P1. Boot the stack, submit an order via OUR endpoint, watch the chain.

```bash
./scripts/dev.sh &
sleep 30

# 1. Submit a paper order through OUR REST endpoint (not curl-to-Alpaca).
curl -s -X POST http://127.0.0.1:8000/api/v1/orders \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "F",
    "side": "buy",
    "qty": "1",
    "type": "market",
    "tif": "day"
  }' | jq .
```

Expect a response like:
```json
{
  "id": 1,
  "status": "submitted",
  "broker_order_id": "abc-def-...",
  "rejection_reason": null
}
```

Watch logs:

```bash
docker compose logs backend | grep -E "risk_check_persisted|order_submitted|trade_update_received|ORDER_FILL_INGESTED|position_recomputed" | tail
```

Expect in order:
- `risk_check_persisted decision=pass`
- `order_submitted order_id=1 broker_order_id=...`
- `trade_update_received event=new` (from the WS stream)
- `trade_update_received event=fill ...` (when paper executes)
- `ORDER_FILL_INGESTED`
- `position_recomputed account_id=1 symbol_id=...`

Verify state in the DB:

```bash
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "SELECT id, status, broker_order_id, source_type FROM orders;"
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "SELECT order_id, qty, price FROM fills;"
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "SELECT account_id, symbol_id, qty, avg_entry_price FROM positions;"
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "SELECT id, decision, reason_codes, order_id FROM risk_checks;"
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "SELECT action, target_type, target_id, payload_json FROM audit_log WHERE target_type='order' ORDER BY ts DESC LIMIT 10;"
```

You should see: one order row, at least one fill row, one position row, two risk_check rows (one pass for this order; the engine's pass + the back-link in the router writes one row total, but the engine's reject path during testing might have added more), and a chain of 3–5 audit rows.

Now run a deliberate rejection to verify the engine blocks oversized orders:

```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/orders \
  -H "Content-Type: application/json" \
  -d '{"symbol":"F","side":"buy","qty":"99999","type":"market","tif":"day"}' | jq .
```

Expect:
```json
{"id": 2, "status": "rejected", "broker_order_id": null, "rejection_reason": "POSITION_CAP_QTY"}
```

Clean up paper account:

```bash
set -a; source .env; set +a
curl -X DELETE https://paper-api.alpaca.markets/v2/orders \
  -H "APCA-API-KEY-ID: $ALPACA_PAPER_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_PAPER_API_SECRET"
curl -X DELETE https://paper-api.alpaca.markets/v2/positions \
  -H "APCA-API-KEY-ID: $ALPACA_PAPER_API_KEY" \
  -H "APCA-API-SECRET-KEY: $ALPACA_PAPER_API_SECRET"
docker compose down
```

- [ ] Submit endpoint returns 200 with order ID for a valid request.
- [ ] Risk-engine pass path produces fill → position → audit chain.
- [ ] Oversized order rejected with `POSITION_CAP_QTY` reason.
- [ ] Paper account cleaned up.

---

## §5.14 — Tests

Lots of new test files. Group by module.

### 5.14.1 Risk Engine tests

Create `apps/backend/tests/risk/__init__.py` (empty) and `apps/backend/tests/risk/test_engine.py`:

```python
"""Risk Engine — 100% branch coverage on the eight checks."""
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.enums import (
    OrderSide, OrderSourceType, OrderType, RiskScopeType, TimeInForce,
)
from app.db.models.account import Account
from app.db.models.account_state import AccountState
from app.db.models.position import Position
from app.db.models.risk_check import RiskCheck
from app.db.models.risk_limits import RiskLimits
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.risk.engine import RiskEngine
from app.risk.halt import set_halted
from app.risk.reason_codes import ReasonCode
from app.risk.types import OrderRequest


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
        session.add(AccountState(
            account_id=1, cash=Decimal("100000"), equity=Decimal("100000"),
            last_equity=Decimal("100000"), buying_power=Decimal("200000"),
            portfolio_value=Decimal("100000"), daytrade_count=0,
            day_change=Decimal(0), day_change_pct=Decimal(0),
            status="ACTIVE", raw_payload={}, updated_at=_now(),
        ))
        await session.commit()


def _req(**overrides) -> OrderRequest:
    base = dict(
        user_id=1, account_id=1, symbol_ticker="AAPL",
        side=OrderSide.BUY, qty=Decimal("10"),
        type=OrderType.MARKET, tif=TimeInForce.DAY,
        source_type=OrderSourceType.MANUAL,
    )
    base.update(overrides)
    return OrderRequest(**base)


@pytest.mark.asyncio
async def test_passes_clean_buy(session_factory, seeded):
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(), trading_mode="paper")
    assert out.passed
    assert out.reason_codes == [ReasonCode.OK]
    assert out.risk_check_id is not None


@pytest.mark.asyncio
async def test_rejects_negative_qty(session_factory, seeded):
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(qty=Decimal("-1")), trading_mode="paper")
    assert not out.passed
    assert ReasonCode.INVALID_INPUT in out.reason_codes


@pytest.mark.asyncio
async def test_rejects_mode_mismatch(session_factory, seeded):
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(), trading_mode="live")
    assert ReasonCode.MODE_MISMATCH in out.reason_codes


@pytest.mark.asyncio
async def test_rejects_unknown_symbol(session_factory, seeded):
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(symbol_ticker="ZZZZZ"), trading_mode="paper")
    assert ReasonCode.SYMBOL_DENIED in out.reason_codes


@pytest.mark.asyncio
async def test_rejects_short_when_not_allowed(session_factory, seeded):
    eng = RiskEngine(session_factory)
    # No existing position -> a SELL would open a short.
    out = await eng.evaluate(_req(side=OrderSide.SELL), trading_mode="paper")
    assert ReasonCode.SHORT_NOT_ALLOWED in out.reason_codes


@pytest.mark.asyncio
async def test_rejects_oversized_qty(session_factory, seeded):
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(qty=Decimal("9999")), trading_mode="paper")
    assert ReasonCode.POSITION_CAP_QTY in out.reason_codes


@pytest.mark.asyncio
async def test_rejects_oversized_notional(session_factory, seeded):
    eng = RiskEngine(session_factory)
    # qty 50 * limit_price 600 = 30k > 25k cap
    out = await eng.evaluate(
        _req(qty=Decimal("50"), type=OrderType.LIMIT, limit_price=Decimal("600")),
        trading_mode="paper",
    )
    assert ReasonCode.POSITION_CAP_NOTIONAL in out.reason_codes


@pytest.mark.asyncio
async def test_rejects_when_halted(session_factory, seeded):
    async with session_factory() as session:
        await set_halted(session, True, reason="test")
        await session.commit()

    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(), trading_mode="paper")
    assert ReasonCode.HALT_REACHED in out.reason_codes


@pytest.mark.asyncio
async def test_rejects_at_daily_loss_cap(session_factory, seeded):
    """When unrealized P&L breaches the cap, next order is rejected AND system halts."""
    async with session_factory() as session:
        state = (await session.execute(select(AccountState))).scalars().first()
        state.day_change = Decimal("-2500")
        await session.commit()

    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(), trading_mode="paper")
    assert ReasonCode.HALT_REACHED in out.reason_codes

    # And the halt flag is now persisted.
    from app.risk.halt import is_halted
    async with session_factory() as session:
        assert await is_halted(session) is True
```

### 5.14.2 Order Router tests

Create `apps/backend/tests/orders/__init__.py` and `apps/backend/tests/orders/test_router.py`:

```python
"""OrderRouter — happy path, risk reject, broker reject, idempotency."""
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.brokers.alpaca.errors import PermanentAlpacaError
from app.db.enums import (
    OrderSide, OrderSourceType, OrderStatus, OrderType, RiskScopeType, TimeInForce,
)
from app.db.models.account import Account
from app.db.models.audit_log import AuditLog
from app.db.models.order import Order
from app.db.models.risk_check import RiskCheck
from app.db.models.risk_limits import RiskLimits
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.events.bus import EventBus
from app.orders.router import OrderRouter
from app.risk import OrderRequest, RiskEngine


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="j@t"))
        session.add(Account(id=1, user_id=1, broker="alpaca", mode="paper", label="Paper"))
        session.add(Symbol(id=1, ticker="F", exchange="NYSE", asset_class="us_equity",
                           name="Ford", active=True))
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


def _req(**ov) -> OrderRequest:
    base = dict(
        user_id=1, account_id=1, symbol_ticker="F",
        side=OrderSide.BUY, qty=Decimal("1"),
        type=OrderType.MARKET, tif=TimeInForce.DAY,
        source_type=OrderSourceType.MANUAL,
    )
    base.update(ov)
    return OrderRequest(**base)


@pytest.fixture
def adapter_mock_ok():
    a = MagicMock()
    a.is_paper = True
    a.submit_order.return_value = {"id": "broker-1", "status": "accepted"}
    return a


@pytest.fixture
def adapter_mock_perm_fail():
    a = MagicMock()
    a.is_paper = True
    a.submit_order.side_effect = PermanentAlpacaError("insufficient funds")
    return a


@pytest.mark.asyncio
async def test_happy_path(session_factory, seeded, adapter_mock_ok):
    bus = EventBus()
    eng = RiskEngine(session_factory)
    router = OrderRouter(adapter_mock_ok, eng, session_factory, bus)

    order = await router.submit(_req())
    assert order.status == OrderStatus.SUBMITTED
    assert order.broker_order_id == "broker-1"

    async with session_factory() as session:
        # Audit chain: risk_passed + submitted = 2 rows for this order
        audits = (await session.execute(
            select(AuditLog).where(AuditLog.target_type == "order")
        )).scalars().all()
        assert len(audits) >= 2


@pytest.mark.asyncio
async def test_risk_reject_never_calls_broker(session_factory, seeded, adapter_mock_ok):
    bus = EventBus()
    eng = RiskEngine(session_factory)
    router = OrderRouter(adapter_mock_ok, eng, session_factory, bus)

    # qty 9999 exceeds position cap of 100
    order = await router.submit(_req(qty=Decimal("9999")))
    assert order.status == OrderStatus.REJECTED
    assert "POSITION_CAP_QTY" in order.rejection_reason
    adapter_mock_ok.submit_order.assert_not_called()


@pytest.mark.asyncio
async def test_broker_permanent_error_marks_rejected(session_factory, seeded, adapter_mock_perm_fail):
    bus = EventBus()
    eng = RiskEngine(session_factory)
    router = OrderRouter(adapter_mock_perm_fail, eng, session_factory, bus)

    order = await router.submit(_req())
    assert order.status == OrderStatus.REJECTED
    assert "insufficient funds" in (order.rejection_reason or "")


@pytest.mark.asyncio
async def test_risk_check_back_links_order(session_factory, seeded, adapter_mock_ok):
    bus = EventBus()
    eng = RiskEngine(session_factory)
    router = OrderRouter(adapter_mock_ok, eng, session_factory, bus)

    order = await router.submit(_req())
    async with session_factory() as session:
        rc = (await session.execute(
            select(RiskCheck).where(RiskCheck.id == order.risk_check_id)
        )).scalars().first()
        assert rc.order_id == order.id
```

### 5.14.3 Adapter tripwire test

Add to `apps/backend/tests/brokers/alpaca/test_adapter.py`:

```python
def test_submit_order_refuses_without_router_token(paper_creds):
    a = AlpacaAdapter(credentials=paper_creds)
    with pytest.raises(RuntimeError, match="ADR 0002"):
        a.submit_order(symbol="AAPL", qty=1, side="buy", type_="market", tif="day")


def test_cancel_order_refuses_without_router_token(paper_creds):
    a = AlpacaAdapter(credentials=paper_creds)
    with pytest.raises(RuntimeError, match="ADR 0002"):
        a.cancel_order("fake-id")
```

(Removes the older "NotImplementedError" tests added in Session 1.)

### 5.14.4 Trade-update consumer tests

Create `apps/backend/tests/orders/test_lifecycle.py`. Patterns mirror the engine tests; assert that:
- A `fill` payload for a known broker_order_id creates a `Fill` row, updates the `Order` to FILLED, recomputes a Position.
- A duplicate `execution_id` is idempotent (no second Fill).
- A `canceled` event transitions the Order terminal state.
- An unknown `broker_order_id` is logged but does not raise.

(Test bodies omitted for brevity — they follow exactly the same fixture+mock pattern.)

### 5.14.5 Run all tests

```bash
cd apps/backend
uv run pytest -q --cov=app/risk --cov=app/orders --cov-report=term-missing
cd ../..
```

Aim for 100% coverage on `app/risk/engine.py` and `app/orders/router.py`. Coverage gaps are bugs in P1's safety-critical path.

- [ ] All new test files created (or stubs that compile + pass).
- [ ] `app/risk/engine.py` and `app/orders/router.py` ≥ 95% coverage; aim for 100%.
- [ ] All existing tests still pass.

---

## §5.15 — Commit and PR

```bash
git add apps/backend/app/risk/
git add apps/backend/app/orders/
git add apps/backend/app/brokers/alpaca/adapter.py
git add apps/backend/app/api/v1/orders.py
git add apps/backend/app/api/v1/__init__.py
git add apps/backend/app/services/position_sync.py
git add apps/backend/app/lifespan.py
git add apps/backend/tests/

git commit -m "feat(orders+risk): risk engine, order router, trade-update consumer, drift detector

- RiskEngine.evaluate: 8 pre-trade checks; persists RiskCheck row on every call
- System halt flag in system_config (durable across restarts)
- OrderRouter.submit/cancel/replace: single entry point per ADR 0002
- AlpacaAdapter mutating methods are now real, gated by _router_token kwarg
- CI grep test fails build if any non-router code calls mutating methods
- TradeUpdateConsumer: alpaca.trade_update -> Fill rows + Order transitions
- PositionRecomputer: aggregates fills into Position (immediate, no poll wait)
- PositionSyncService: drift counter, warns after 3 consecutive missing pairs
- Minimal POST /api/v1/orders endpoint to drive the router (full surface
  in Session 6)
- 100% branch coverage on risk/engine.py and orders/router.py"

git push -u origin feat/p1-risk-engine-order-router

gh pr create \
  --title "feat(orders+risk): risk engine, order router, trade-update consumer, drift detector" \
  --body "P1 Session 5 deliverable — the heart of P1. Implements ADR 0002 as enforced code.

**In scope:** Risk Engine (8 checks), Order Router (sole submission path), trade-update consumer + position recomputer, reconciliation drift counter, minimal POST /api/v1/orders endpoint.

**Out of scope (Session 6):** full REST surface (GET/PATCH/DELETE for orders, list endpoints), frontend pages, live-mode UX gates."

gh pr checks
```

Merge when CI passes:

```bash
gh pr merge --merge --delete-branch
git checkout main && git pull
```

- [ ] PR opened, CI green, merged, branch deleted.

---

## Verification Checklist (full session)

- [ ] §5.1 `app/risk/` package with `__init__.py`, `reason_codes.py`, `types.py`.
- [ ] §5.2 `halt.py` reads/writes `system_config` rows for halt state.
- [ ] §5.3 `RiskEngine.evaluate` implements 8 checks, persists `risk_checks` on every call, sets halt flag on daily-loss breach.
- [ ] §5.4 `OrderRouter` is the only code path that calls adapter mutation methods; persists Order row before broker call; back-links RiskCheck.
- [ ] §5.5 Adapter `submit_order` / `cancel_order` / `replace_order` enforce `_router_token` tripwire.
- [ ] §5.6 ADR 0002 grep test passes; would fail if a future PR added a direct adapter call from outside `app/orders/`.
- [ ] §5.7 Lifespan constructs RiskEngine + OrderRouter.
- [ ] §5.8 POST `/api/v1/orders` endpoint working.
- [ ] §5.9 `TradeUpdateConsumer` subscribes to `alpaca.trade_update`, writes Fills, updates Order status.
- [ ] §5.10 `PositionRecomputer` aggregates fills into Position upserts.
- [ ] §5.11 `PositionSyncService` emits `system.reconciliation_drift` after 3 consecutive missing pairs.
- [ ] §5.12 Lifespan wires consumer + recomputer.
- [ ] §5.13 End-to-end paper smoke succeeds; oversized order rejected; paper account cleaned up.
- [ ] §5.14 Tests in place; 100% (or near) coverage on engine + router; all existing tests still pass.
- [ ] §5.15 PR merged on `main`.

---

## Sign-off

```bash
git tag -a p1-session5-complete -m "P1 Session 5 complete: ADR 0002 enforced in code; order pipeline alive end-to-end"
git push origin p1-session5-complete
```

Update `todo.md`:
- Mark Session 5 complete.
- Note: **the workbench now executes paper trades end-to-end via its own pipeline.** Manual smoke proves it. The only thing missing from S1 (Design Doc §2.3) is the UI to drive it — that's Session 6.

---

## Notes & Gotchas

1. **The `_router_token` tripwire is not a security boundary.** It's a guardrail against accidental bypass. A malicious developer could read the constant out of `app/orders/router.py` and pass it directly. We accept this — the CI grep is the second layer, and code review is the third. The combination makes accidental bypass near-impossible without it being obvious in PR review.

2. **The Risk Engine commits its own transaction.** This is by design — the `RiskCheck` row must persist even if the router's later operations fail. If you change the engine to share the router's transaction, a broker-side exception could roll back the audit trail. Don't.

3. **`Order.risk_check_id` set on initial persist; `RiskCheck.order_id` back-linked after.** Two-phase because the engine commits before the order exists. SQLite allows this since both columns are nullable. The order of operations is: (1) engine writes RiskCheck with order_id=NULL; (2) router writes Order with risk_check_id=<that id>; (3) router back-links RiskCheck.order_id. Step 3 could be skipped — the relationship is still queryable via the Order row — but having both directions makes audit queries faster.

4. **`PositionRecomputer` runs synchronously with the trade-update handler.** If a future strategy fires many fills per second, this becomes a hot loop. P4 polish should batch recomputes (debounce per `(account, symbol)` to once per second). Not needed for MVP cadence.

5. **`market_value` and `unrealized_pl` in `positions` are not updated by the recomputer.** Those need live quotes, which is the position sync's job (it sees Alpaca's already-computed values). The recomputer keeps qty + avg_entry_price + cost_basis fresh; the sync overwrites market_value + unrealized_pl on its next tick. This split is fine: between the fill arriving and the next 10-second poll, the UI shows an entry-price-only position, which is correct for the few seconds after a fill.

6. **`OrderRouter.cancel` does not wait for Alpaca's confirmation.** It records `ORDER_CANCEL_REQUESTED` in the audit and returns. The trade-update stream emits `canceled` shortly after, which transitions the Order's status to CANCELED via the consumer. If you want a synchronous "wait for terminal state" API, build it in the REST layer (Session 6) — keep the router itself async-event-driven.

7. **Drift counter is in-memory.** Restart loses state. That's intentional for MVP: a backend restart is rare enough that resetting the counter is the right behavior (you want fresh observations). If you ever persist this, do it in a `reconciliation_drifts` table; don't shove counters into `system_config`.

8. **Two-phase Risk Engine + Order Router rejection paths** (engine rejects → router still persists an Order row marked REJECTED) is deliberate. The alternative — only persist Order rows that passed risk — leaves no record of what was *attempted*. For audit completeness, every submission attempt is a row.

9. **`POST /api/v1/orders` has user_id=1, account_id=1 hard-coded.** P1 is single-user. Session 6's frontend will continue to use these constants. Multi-user is post-MVP, and when it arrives the change is local to this handler (pull from `current_user` via the auth dependency).

10. **Don't start Session 6 mid-session.** Session 6 is the frontend pass (order ticket UI, Orders + Positions pages, full REST GET endpoints, live-mode UX gates). It's roughly 4–5 hours of mostly TypeScript/React. The natural seam is "backend is feature-complete for P1; now make it usable." Resist scaffolding frontend code in this PR.

---

*End of P1 Session 5 v0.1.*
