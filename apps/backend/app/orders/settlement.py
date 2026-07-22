"""Per-order REST settlement barrier — canonically reconcile ONE order to broker truth.

When the Alpaca trade-updates websocket drops a fill/cancel event (dual-armed account, flapping
stream), a local order stays non-terminal though the broker already finished it. Any sequence that
must know order N is fully settled before deciding order N+1 — the ADR-0043 canary churn, or any
controlled-turnover harness — cannot rely on the stream. ``settle_order`` polls the broker REST for
the order's real outcome and re-applies it through the CANONICAL ``TradeUpdateConsumer._handle`` — the
exact path the live stream would have driven (Fill row, order status, ``terminal_at``, position
recompute, reservation release, ``ORDER_FILL_INGESTED`` audit). Read-only against the broker
(``get_order`` only; never submits or cancels).

FAIL CLOSED. ``settle_order`` never returns "settled" on doubt — it raises :class:`SettlementError`
on: broker REST unavailable, broker order missing, non-terminal at timeout, a shrinking filled qty, a
fill with no average price, a raising consumer, a still-non-terminal LOCAL order after ingest, a
local≠broker position, a stale HELD reservation for the order, or a duplicate/ambiguous outcome. A
caller MUST NOT submit the next order until this returns without raising.

``resolve_broker_outcome`` is the single shared drift-computation + ingest step; ``reconcile_stuck_orders``
imports it so there is exactly one implementation of "apply the broker's real outcome locally".
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.enums import TERMINAL_ORDER_STATUSES, OrderStatus
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.risk_reservation import RESERVATION_HELD, RiskReservation
from app.orders.lifecycle import TradeUpdateConsumer

# Broker (Alpaca) statuses that mean the order is DONE at the broker.
BROKER_FILLED = "filled"
BROKER_CANCEL = frozenset({"canceled", "expired", "rejected", "replaced"})
# Everything else (new, accepted, partially_filled, pending_*, done_for_day) = still working.

DEFAULT_TIMEOUT_S = 30.0
DEFAULT_POLL_INTERVAL_S = 1.5


class SettlementError(RuntimeError):
    """A settlement precondition could not be positively established. The caller must treat this as a
    HARD STOP — the ledger state for this order is unresolved, so no further order may be placed."""


@dataclass(frozen=True)
class OrderOutcome:
    order_id: int
    broker_status: str
    action: str          # "fill" | "terminal" | "none"
    delta: Decimal | None
    avg_price: Decimal | None
    broker_terminal: bool


def _dec(v: Any) -> Decimal:
    return Decimal(str(v or 0))


async def _local_filled_qty(session_factory: async_sessionmaker, order_id: int) -> Decimal:
    async with session_factory() as s:
        total = (
            await s.execute(
                select(func.coalesce(func.sum(Fill.qty), 0)).where(Fill.order_id == order_id)
            )
        ).scalar_one()
    return Decimal(str(total or 0))


async def resolve_broker_outcome(
    session_factory: async_sessionmaker,
    consumer: TradeUpdateConsumer,
    *,
    order_id: int,
    broker_order_id: str,
    broker_order: dict[str, Any],
    apply: bool,
) -> OrderOutcome:
    """Compute the drift between one fetched broker order and the local ledger, and — when ``apply`` —
    ingest the missing outcome through the canonical ``TradeUpdateConsumer._handle`` (idempotent via a
    deterministic execution id). Raises :class:`SettlementError` on malformed broker data or a raising
    consumer. This is the ONE place "apply the broker's real outcome locally" is implemented."""
    bstatus = str(broker_order.get("status") or "").lower()

    if bstatus == BROKER_FILLED:
        bqty = _dec(broker_order.get("filled_qty"))
        bavg = _dec(broker_order.get("filled_avg_price"))
        local = await _local_filled_qty(session_factory, order_id)
        delta = bqty - local
        if delta < 0:
            raise SettlementError(
                f"order {order_id}: broker filled_qty {bqty} < local booked {local} "
                f"(shrinking fill — ambiguous broker outcome)"
            )
        if delta > 0:
            if bavg <= 0:
                raise SettlementError(
                    f"order {order_id}: fill delta {delta} but broker reports no average price"
                )
            if apply:
                payload: dict[str, Any] = {
                    "event": "fill",
                    "broker_order_id": broker_order_id,
                    # deterministic → a re-run at the same cumulative fill is a no-op (delta=0).
                    "execution_id": f"settle-{broker_order_id}-{bqty}",
                    "qty": str(delta),
                    "price": str(bavg),
                    "timestamp": str(broker_order.get("filled_at")),
                }
                try:
                    await consumer._handle(payload)
                except Exception as exc:  # noqa: BLE001 — any consumer failure is fail-closed
                    raise SettlementError(
                        f"order {order_id}: canonical consumer raised on fill ingest: "
                        f"{type(exc).__name__}: {exc}"
                    ) from exc
            return OrderOutcome(order_id, bstatus, "fill", delta, bavg, broker_terminal=True)
        return OrderOutcome(order_id, bstatus, "none", Decimal(0), bavg, broker_terminal=True)

    if bstatus in BROKER_CANCEL:
        if apply:
            payload = {"event": bstatus, "broker_order_id": broker_order_id, "raw": {}}
            try:
                await consumer._handle(payload)
            except Exception as exc:  # noqa: BLE001
                raise SettlementError(
                    f"order {order_id}: canonical consumer raised on terminal ingest: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc
        return OrderOutcome(order_id, bstatus, "terminal", None, None, broker_terminal=True)

    # Still genuinely working at the broker (new/accepted/partially_filled/pending_*).
    if bstatus == "partially_filled" and apply:
        # Book the partial increment so the local ledger tracks it, but the order is NOT terminal yet.
        bqty = _dec(broker_order.get("filled_qty"))
        bavg = _dec(broker_order.get("filled_avg_price"))
        local = await _local_filled_qty(session_factory, order_id)
        delta = bqty - local
        if delta < 0:
            raise SettlementError(
                f"order {order_id}: broker partial filled_qty {bqty} < local {local} (shrinking)"
            )
        if delta > 0:
            if bavg <= 0:
                raise SettlementError(
                    f"order {order_id}: partial fill delta {delta} but no average price"
                )
            payload = {
                "event": "partial_fill",
                "broker_order_id": broker_order_id,
                "execution_id": f"settle-{broker_order_id}-{bqty}",
                "qty": str(delta),
                "price": str(bavg),
                "timestamp": str(broker_order.get("filled_at")),
            }
            try:
                await consumer._handle(payload)
            except Exception as exc:  # noqa: BLE001
                raise SettlementError(
                    f"order {order_id}: canonical consumer raised on partial-fill ingest: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc
    return OrderOutcome(order_id, bstatus, "none", None, None, broker_terminal=False)


async def _order(session_factory: async_sessionmaker, order_id: int) -> Order | None:
    async with session_factory() as s:
        return await s.scalar(select(Order).where(Order.id == order_id))


async def _local_position_qty(session_factory: async_sessionmaker, account_id: int, symbol_id: int) -> Decimal:
    async with session_factory() as s:
        row = await s.scalar(
            select(Position.qty).where(
                Position.account_id == account_id, Position.symbol_id == symbol_id
            )
        )
    return Decimal(str(row or 0))


async def _has_stale_held_reservation(session_factory: async_sessionmaker, order_id: int) -> bool:
    async with session_factory() as s:
        row = await s.scalar(
            select(RiskReservation.id).where(
                RiskReservation.order_id == order_id, RiskReservation.state == RESERVATION_HELD
            )
        )
    return row is not None


def _broker_qty_for(broker_positions: list[dict[str, Any]], ticker: str) -> Decimal:
    for p in broker_positions:
        if str(p.get("symbol")) == ticker:
            return Decimal(str(p.get("qty") or 0))
    return Decimal(0)


@dataclass(frozen=True)
class SettlementResult:
    order_id: int
    broker_status: str
    local_status: str
    filled_qty: Decimal
    local_position: Decimal
    broker_position: Decimal
    polls: int


async def settle_order(
    session_factory: async_sessionmaker,
    adapter: Any,
    consumer: TradeUpdateConsumer,
    *,
    order_id: int,
    ticker: str,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
) -> SettlementResult:
    """Block until order ``order_id`` is fully settled against broker truth, or raise
    :class:`SettlementError`. On return: the local order is terminal, its fills match the broker, the
    LOCAL position equals the BROKER position for ``ticker``, and no HELD reservation lingers.

    The caller MUST NOT submit the next order until this returns without raising."""
    order = await _order(session_factory, order_id)
    if order is None:
        raise SettlementError(f"order {order_id}: not found locally")
    account_id, symbol_id = order.account_id, order.symbol_id
    broker_order_id = order.broker_order_id
    if not broker_order_id:
        raise SettlementError(f"order {order_id}: no broker_order_id — never reached the broker")

    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_s
    polls = 0
    while True:
        polls += 1
        try:
            broker_order = await asyncio.to_thread(adapter.get_order, broker_order_id)
        except Exception as exc:  # noqa: BLE001 — unreachable / 404 → fail closed, never guess
            raise SettlementError(
                f"order {order_id}: broker get_order failed "
                f"({type(exc).__name__}: {str(exc)[:80]})"
            ) from exc
        if not broker_order or not broker_order.get("status"):
            raise SettlementError(f"order {order_id}: broker returned no order/status (missing)")

        outcome = await resolve_broker_outcome(
            session_factory, consumer,
            order_id=order_id, broker_order_id=broker_order_id,
            broker_order=broker_order, apply=True,
        )
        if outcome.broker_terminal:
            break
        if loop.time() >= deadline:
            raise SettlementError(
                f"order {order_id}: still non-terminal at broker ({outcome.broker_status}) "
                f"after {timeout_s:.0f}s"
            )
        await asyncio.sleep(poll_interval_s)

    # --- post-terminal verification (all fail-closed) ---
    settled = await _order(session_factory, order_id)
    if settled is None:
        raise SettlementError(f"order {order_id}: vanished during settlement")
    if OrderStatus(settled.status) not in TERMINAL_ORDER_STATUSES:
        raise SettlementError(
            f"order {order_id}: broker terminal but LOCAL order still {settled.status} after ingest"
        )
    local_qty = await _local_position_qty(session_factory, account_id, symbol_id)
    broker_qty = _broker_qty_for(await asyncio.to_thread(adapter.get_positions), ticker)
    if local_qty != broker_qty:
        raise SettlementError(
            f"order {order_id}: local position {local_qty} != broker {broker_qty} for {ticker}"
        )
    if await _has_stale_held_reservation(session_factory, order_id):
        raise SettlementError(
            f"order {order_id}: a HELD reservation still lingers after terminal settlement"
        )
    return SettlementResult(
        order_id=order_id,
        broker_status=outcome.broker_status,
        local_status=str(settled.status),
        filled_qty=await _local_filled_qty(session_factory, order_id),
        local_position=local_qty,
        broker_position=broker_qty,
        polls=polls,
    )
