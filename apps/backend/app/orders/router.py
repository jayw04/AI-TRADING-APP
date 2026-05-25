"""OrderRouter — the only entry point for order submission.

Per ADR 0002 there is no other path through which an OrderRequest may reach
the broker. This invariant is enforced by:

  1. AlpacaAdapter.submit_order / cancel_order / replace_order accept a
     keyword-only ``_router_token`` and refuse to run without it.
  2. The router is the only module that knows the token.
  3. A CI grep test fails any PR that calls AlpacaAdapter.submit_order from
     a module other than this one (see tests/test_adr_0002_invariant.py).

The router writes the Order row BEFORE calling Alpaca, links the RiskCheck,
and emits internal events so the WS gateway and audit trail stay in sync.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.brokers.alpaca import AlpacaAdapter
from app.brokers.alpaca.errors import PermanentAlpacaError, TransientAlpacaError
from app.db.enums import OrderSourceType, OrderStatus
from app.db.models.order import Order
from app.db.models.risk_check import RiskCheck
from app.db.models.symbol import Symbol
from app.events.bus import EventBus
from app.risk import OrderRequest, RiskEngine, RiskOutcome

logger = structlog.get_logger(__name__)

# Shared token between router and adapter — guardrail against accidental bypass,
# not a security boundary. See ADR 0002 and the CI grep test.
ROUTER_TOKEN = "ADR_0002_ONLY_ORDERROUTER_MAY_CALL_THIS"


class OrderRouter:
    def __init__(
        self,
        adapter: AlpacaAdapter,
        risk_engine: RiskEngine,
        session_factory: async_sessionmaker,
        bus: EventBus,
    ) -> None:
        self._adapter = adapter
        self._risk = risk_engine
        self._session_factory = session_factory
        self._bus = bus

    async def submit(self, req: OrderRequest) -> Order:
        """Sole order-submission entry point."""
        trading_mode = "paper" if self._adapter.is_paper else "live"
        outcome = await self._risk.evaluate(req, trading_mode=trading_mode)

        # If the engine rejected without resolving a Symbol row (e.g. unknown
        # ticker), we cannot persist an Order — orders.symbol_id is NOT NULL.
        # The RiskCheck row already records the rejected attempt for audit;
        # return an ephemeral rejected Order so the API caller's response
        # shape stays consistent.
        if not outcome.passed and outcome.resolved_symbol_id is None:
            return _ephemeral_rejected_order(req, outcome)

        async with self._session_factory() as session:
            order = await self._persist_initial_order(session, req, outcome)

            if not outcome.passed:
                order.status = OrderStatus.REJECTED
                order.rejection_reason = ",".join(r.value for r in outcome.reason_codes)
                order.terminal_at = datetime.now(UTC)
                order.updated_at = order.terminal_at
                await session.commit()
                await session.refresh(order)
                await self._audit(
                    session,
                    order,
                    AuditAction.ORDER_REJECTED_BY_RISK,
                    {
                        "reasons": [r.value for r in outcome.reason_codes],
                        "risk_check_id": outcome.risk_check_id,
                    },
                )
                await self._emit(order, "order.rejected", {
                    "reasons": [r.value for r in outcome.reason_codes],
                })
                logger.info(
                    "order_rejected_by_risk",
                    order_id=order.id,
                    reasons=[r.value for r in outcome.reason_codes],
                )
                return order

            # Risk passed. Mark pending_submit and attempt broker submission.
            order.status = OrderStatus.PENDING_SUBMIT
            order.updated_at = datetime.now(UTC)
            await session.commit()
            await session.refresh(order)
            await self._audit(
                session,
                order,
                AuditAction.ORDER_RISK_PASSED,
                {"risk_check_id": outcome.risk_check_id},
            )

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
            # Leave the order in PENDING_SUBMIT; caller may retry. We do NOT
            # mark it rejected — that would be wrong if Alpaca eventually
            # accepted it on a retry.
            await self._emit_simple(order.id, "order.submit_transient_error")
            raise

        # Broker accepted.
        async with self._session_factory() as session:
            order = (
                await session.execute(select(Order).where(Order.id == order.id))
            ).scalars().first()
            order.broker_order_id = str(
                broker_response.get("id")
                or broker_response.get("broker_order_id")
                or ""
            )
            order.status = OrderStatus.SUBMITTED
            order.submitted_at = datetime.now(UTC)
            order.updated_at = order.submitted_at
            await session.commit()
            await session.refresh(order)
            await self._audit(
                session,
                order,
                AuditAction.ORDER_SUBMITTED,
                {"broker_order_id": order.broker_order_id},
            )

        await self._emit(order, "order.submitted", {})
        logger.info(
            "order_submitted",
            order_id=order.id,
            broker_order_id=order.broker_order_id,
        )
        return order

    async def cancel(self, order_id: int, *, actor_user_id: int | None = None) -> Order:  # noqa: ARG002
        async with self._session_factory() as session:
            order = (
                await session.execute(select(Order).where(Order.id == order_id))
            ).scalars().first()
            if order is None:
                raise ValueError(f"Order {order_id} not found")
            if not order.broker_order_id:
                # Local-only cancel (order never made it to broker).
                order.status = OrderStatus.CANCELED
                order.terminal_at = datetime.now(UTC)
                order.updated_at = order.terminal_at
                await session.commit()
                await session.refresh(order)
                await self._audit(session, order, AuditAction.ORDER_CANCELED_LOCAL, {})
                await self._emit(order, "order.canceled", {"local_only": True})
                return order

        try:
            self._adapter.cancel_order(order.broker_order_id, _router_token=ROUTER_TOKEN)
        except PermanentAlpacaError as exc:
            logger.warning("cancel_permanent_error", order_id=order_id, error=str(exc))
            # Usually "already filled / already canceled" — trade-update stream
            # will reconcile. Audit and continue.
            async with self._session_factory() as session:
                order = (
                    await session.execute(select(Order).where(Order.id == order_id))
                ).scalars().first()
                await self._audit(
                    session,
                    order,
                    AuditAction.ORDER_CANCEL_REJECTED_BY_BROKER,
                    {"error": str(exc)},
                )
            return order

        # Optimistic; trade-update consumer will transition to terminal CANCELED.
        async with self._session_factory() as session:
            order = (
                await session.execute(select(Order).where(Order.id == order_id))
            ).scalars().first()
            await self._audit(session, order, AuditAction.ORDER_CANCEL_REQUESTED, {})
        await self._emit(order, "order.cancel_requested", {})
        return order

    async def replace(
        self,
        order_id: int,
        *,
        new_qty: Decimal | None = None,
        new_limit_price: Decimal | None = None,
        actor_user_id: int | None = None,  # noqa: ARG002 - reserved for future audit
    ) -> Order:
        async with self._session_factory() as session:
            order = (
                await session.execute(select(Order).where(Order.id == order_id))
            ).scalars().first()
            if order is None or not order.broker_order_id:
                raise ValueError(f"Order {order_id} not replaceable")

        try:
            self._adapter.replace_order(
                order.broker_order_id,
                new_qty=new_qty,
                new_limit_price=new_limit_price,
                _router_token=ROUTER_TOKEN,
            )
        except PermanentAlpacaError as exc:
            async with self._session_factory() as session:
                order = (
                    await session.execute(select(Order).where(Order.id == order_id))
                ).scalars().first()
                await self._audit(
                    session,
                    order,
                    AuditAction.ORDER_REPLACE_REJECTED_BY_BROKER,
                    {"error": str(exc)},
                )
            return order

        async with self._session_factory() as session:
            order = (
                await session.execute(select(Order).where(Order.id == order_id))
            ).scalars().first()
            await self._audit(
                session,
                order,
                AuditAction.ORDER_REPLACE_REQUESTED,
                {
                    "new_qty": str(new_qty) if new_qty is not None else None,
                    "new_limit_price": str(new_limit_price) if new_limit_price is not None else None,
                },
            )
        await self._emit(order, "order.replace_requested", {})
        return order

    # ---- internals ----

    async def _persist_initial_order(
        self,
        session: AsyncSession,
        req: OrderRequest,
        outcome: RiskOutcome,
    ) -> Order:
        now = datetime.now(UTC)
        symbol_id = outcome.resolved_symbol_id
        if symbol_id is None:
            sym = (
                await session.execute(
                    select(Symbol).where(Symbol.ticker == req.symbol_ticker)
                )
            ).scalars().first()
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

        # Back-link RiskCheck.order_id (engine created it with order_id=None).
        if outcome.risk_check_id is not None:
            rc = (
                await session.execute(
                    select(RiskCheck).where(RiskCheck.id == outcome.risk_check_id)
                )
            ).scalars().first()
            if rc is not None:
                rc.order_id = order.id
                await session.commit()

        return order

    async def _mark_broker_rejected(self, order_id: int, reason: str) -> Order:
        async with self._session_factory() as session:
            order = (
                await session.execute(select(Order).where(Order.id == order_id))
            ).scalars().first()
            order.status = OrderStatus.REJECTED
            order.rejection_reason = reason[:512]
            order.terminal_at = datetime.now(UTC)
            order.updated_at = order.terminal_at
            await session.commit()
            await session.refresh(order)
            await self._audit(
                session,
                order,
                AuditAction.ORDER_REJECTED_BY_BROKER,
                {"reason": reason},
            )
        await self._emit(order, "order.rejected", {"reason": reason})
        return order

    async def _audit(
        self,
        session: AsyncSession,
        order: Order,
        action: AuditAction | str,
        payload: dict[str, Any],
    ) -> None:
        actor_type = (
            AuditActorType.USER
            if order.source_type == OrderSourceType.MANUAL
            else AuditActorType.SYSTEM
        )
        AuditLogger.write(
            session,
            actor_type=actor_type,
            actor_id=str(order.user_id),
            action=action,
            target_type="order",
            target_id=order.id,
            payload=payload,
            user_id=order.user_id,
        )
        await session.commit()

    async def _emit(self, order: Order, topic: str, extra: dict[str, Any]) -> None:
        await self._bus.publish(
            topic,
            {
                "order_id": order.id,
                "broker_order_id": order.broker_order_id,
                "status": order.status.value,
                "symbol_id": order.symbol_id,
                "side": order.side.value,
                "qty": str(order.qty),
                **extra,
            },
        )

    async def _emit_simple(self, order_id: int, topic: str) -> None:
        await self._bus.publish(topic, {"order_id": order_id})


def _ephemeral_rejected_order(req: OrderRequest, outcome: RiskOutcome) -> Order:
    """Build a non-persisted Order in REJECTED state.

    Used when the engine rejected before a Symbol could be resolved
    (orders.symbol_id is NOT NULL, so we can't write the row). The RiskCheck
    row written by the engine remains the authoritative audit record.
    """
    now = datetime.now(UTC)
    return Order(
        user_id=req.user_id,
        account_id=req.account_id,
        symbol_id=0,  # ephemeral — never reaches the DB
        broker_order_id=None,
        client_order_id=req.client_order_id,
        side=req.side,
        qty=req.qty,
        type=req.type,
        limit_price=req.limit_price,
        stop_price=req.stop_price,
        tif=req.tif,
        extended_hours=req.extended_hours,
        status=OrderStatus.REJECTED,
        rejection_reason=",".join(r.value for r in outcome.reason_codes),
        source_type=req.source_type,
        source_id=req.source_id,
        risk_check_id=outcome.risk_check_id,
        created_at=now,
        terminal_at=now,
        updated_at=now,
    )
