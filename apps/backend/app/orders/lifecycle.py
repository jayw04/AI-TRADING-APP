"""Trade-update consumer.

Bridges ``alpaca.trade_update`` events from the in-process event bus into
local writes:

  * ``fill`` / ``partial_fill`` → insert ``Fill`` row, update ``Order`` status
    + ``terminal_at``, recompute the affected position, audit, emit
    ``fill.created`` and ``order.updated``.
  * ``canceled`` / ``expired`` / ``rejected`` / ``replaced`` → transition
    ``Order`` to terminal state, audit, emit ``order.<status>``.

Out-of-band orders (broker_order_id we've never seen) are logged as warnings;
the ``PositionSyncService`` drift counter is the second line of defense.

EventBus bridge: my ``EventBus.subscribe`` returns an async generator, so
``start()`` spawns a task that drives the consumption loop. ``stop()``
cancels the task.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.db.enums import TERMINAL_ORDER_STATUSES, OrderStatus
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.events.bus import EventBus

if TYPE_CHECKING:
    from app.orders.positions import PositionRecomputer

logger = structlog.get_logger(__name__)


# Alpaca-event → internal OrderStatus mapping (terminal transitions only).
_ALPACA_TERMINAL_MAP = {
    "canceled": OrderStatus.CANCELED,
    "expired": OrderStatus.EXPIRED,
    "rejected": OrderStatus.REJECTED,
    "replaced": OrderStatus.REPLACED,
}


class TradeUpdateConsumer:
    def __init__(
        self,
        session_factory: async_sessionmaker,
        bus: EventBus,
        position_recomputer: PositionRecomputer,
    ) -> None:
        self._session_factory = session_factory
        self._bus = bus
        self._position_recomputer = position_recomputer
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(
            self._loop(), name="trade-update-consumer"
        )
        logger.info("trade_update_consumer_started")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self._task
        self._task = None
        logger.info("trade_update_consumer_stopped")

    async def _loop(self) -> None:
        """Drive the bus subscription until cancelled."""
        try:
            async for event in self._bus.subscribe("alpaca.trade_update"):
                try:
                    await self._handle(event)
                except Exception:
                    logger.exception("trade_update_handler_error")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("trade_update_consumer_loop_crashed")

    async def _handle(self, payload: dict[str, Any]) -> None:
        event = payload.get("event")
        broker_order_id = payload.get("broker_order_id")
        if not broker_order_id:
            logger.warning("trade_update_missing_broker_order_id", update_event=event)
            return

        async with self._session_factory() as session:
            order = (
                await session.execute(
                    select(Order).where(Order.broker_order_id == broker_order_id)
                )
            ).scalars().first()

            if order is None:
                logger.warning(
                    "trade_update_unknown_order",
                    broker_order_id=broker_order_id,
                    update_event=event,
                )
                return

            if event in ("fill", "partial_fill"):
                await self._handle_fill(
                    session, order, payload, partial=(event == "partial_fill")
                )
            elif event in _ALPACA_TERMINAL_MAP:
                await self._handle_terminal(session, order, payload, event)
            else:
                # 'new', 'accepted', 'pending_new' etc. — informational only.
                logger.debug(
                    "trade_update_informational",
                    update_event=event,
                    order_id=order.id,
                )

    async def _handle_fill(
        self,
        session: AsyncSession,
        order: Order,
        payload: dict[str, Any],
        *,
        partial: bool,
    ) -> None:
        execution_id = payload.get("execution_id")

        # Idempotency: a re-delivered trade-update must not double-write a Fill.
        if execution_id:
            existing = (
                await session.execute(
                    select(Fill).where(Fill.broker_fill_id == execution_id)
                )
            ).scalars().first()
            if existing is not None:
                logger.debug(
                    "trade_update_fill_duplicate", execution_id=execution_id
                )
                return

        qty = _to_decimal(payload.get("qty"))
        price = _to_decimal(payload.get("price"))
        if qty <= 0 or price <= 0:
            logger.warning(
                "trade_update_fill_invalid_numbers",
                qty=str(qty),
                price=str(price),
            )
            return

        now = datetime.now(UTC)
        session.add(
            Fill(
                order_id=order.id,
                broker_fill_id=execution_id,
                qty=qty,
                price=price,
                commission=Decimal(0),
                filled_at=_parse_ts(payload.get("timestamp")) or now,
            )
        )

        # Recompute fills total via SQL aggregate (existing fills + the one
        # we just added but haven't committed). The simplest correct read is
        # "sum of existing fills" + the new qty.
        prior_total = (
            await session.execute(
                select(func.coalesce(func.sum(Fill.qty), 0)).where(
                    Fill.order_id == order.id
                )
            )
        ).scalar_one()
        all_fills_qty = Decimal(prior_total or 0) + qty

        if partial or all_fills_qty < order.qty:
            order.status = OrderStatus.PARTIALLY_FILLED
        else:
            order.status = OrderStatus.FILLED
            order.terminal_at = now
        order.updated_at = now

        AuditLogger.write(
            session,
            actor_type=AuditActorType.SYSTEM,
            actor_id="trade_stream",
            action=AuditAction.ORDER_FILL_INGESTED,
            target_type="order",
            target_id=order.id,
            payload={
                "execution_id": execution_id,
                "qty": str(qty),
                "price": str(price),
            },
            user_id=order.user_id,
        )
        await session.commit()

        await self._bus.publish(
            "fill.created",
            {
                "order_id": order.id,
                "execution_id": execution_id,
                "qty": str(qty),
                "price": str(price),
            },
        )
        await self._bus.publish(
            "order.updated",
            {"order_id": order.id, "status": order.status.value},
        )

        # Recompute the affected position so the UI sees the change without
        # waiting for the next 10-second position sync.
        await self._position_recomputer.recompute(order.account_id, order.symbol_id)

    async def _handle_terminal(
        self,
        session: AsyncSession,
        order: Order,
        payload: dict[str, Any],
        event: str,
    ) -> None:
        new_status = _ALPACA_TERMINAL_MAP[event]
        if order.status in TERMINAL_ORDER_STATUSES:
            logger.debug(
                "trade_update_terminal_for_already_terminal_order",
                order_id=order.id,
                status=order.status.value,
            )
            return
        now = datetime.now(UTC)
        order.status = new_status
        order.terminal_at = now
        order.updated_at = now
        if new_status == OrderStatus.REJECTED and not order.rejection_reason:
            raw = payload.get("raw") or {}
            order.rejection_reason = (
                raw.get("reject_reason") if isinstance(raw, dict) else None
            ) or event

        AuditLogger.write(
            session,
            actor_type=AuditActorType.SYSTEM,
            actor_id="trade_stream",
            # Constructed at runtime from OrderStatus; enum constructor
            # raises if a new status sneaks in without an AuditAction entry.
            action=AuditAction(f"ORDER_{new_status.value.upper()}"),
            target_type="order",
            target_id=order.id,
            payload={"event": event},
            user_id=order.user_id,
        )
        await session.commit()
        await self._bus.publish(
            f"order.{new_status.value}", {"order_id": order.id}
        )


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
