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
on: broker REST unavailable (``get_order`` or ``get_positions``), broker order missing, non-terminal
at timeout, a shrinking filled qty, a fill with no average price, a non-positive incremental price, a
cumulative notional that contradicts the local ledger, a raising consumer, a still-non-terminal LOCAL
order after ingest, a local≠broker cumulative quantity OR notional, a local≠broker position, a stale
HELD reservation for the order, or a duplicate/ambiguous outcome. A caller MUST NOT submit the next
order until this returns without raising.

TWO THINGS THAT LOOK LIKE DETAIL AND ARE NOT. (1) Fills are reconciled before the terminal
transition for EVERY terminal status, because a partially filled order that is then canceled carries
a real fill on a cancellation record. (2) The missing increment is priced from cumulative NOTIONAL,
not from the broker's cumulative average — booking a later increment at the running average records
the wrong cost while quantity and position both still reconcile perfectly.

``resolve_broker_outcome`` is the single shared drift-computation + ingest step; ``reconcile_stuck_orders``
imports it so there is exactly one implementation of "apply the broker's real outcome locally".
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
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

# Brokers report a ROUNDED cumulative average price (Alpaca: 4dp), and we store fill prices at 4dp
# too, so cumulative notional reconstructed from (qty x avg) never matches the sum of booked fills
# exactly. The tolerance is the accumulated rounding of both sides — deliberately small: it must
# absorb representation error and nothing else, because everything it absorbs is a real discrepancy
# we have chosen not to see.
def _notional_tolerance(qty: Decimal) -> Decimal:
    return abs(qty) * Decimal("0.0002") + Decimal("0.01")


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


async def _local_booked(
    session_factory: async_sessionmaker, order_id: int
) -> tuple[Decimal, Decimal]:
    """Locally booked (cumulative quantity, cumulative notional) for one order.

    Notional — not just quantity — because quantity alone cannot detect a fill booked at the wrong
    PRICE, and a wrong price silently corrupts cash, cost basis, realized P&L and every downstream
    loss-control figure while position equality still looks perfect."""
    async with session_factory() as s:
        row = (
            await s.execute(
                select(
                    func.coalesce(func.sum(Fill.qty), 0),
                    func.coalesce(func.sum(Fill.qty * Fill.price), 0),
                ).where(Fill.order_id == order_id)
            )
        ).one()
    return Decimal(str(row[0] or 0)), Decimal(str(row[1] or 0))


async def _missing_increment(
    session_factory: async_sessionmaker,
    *,
    order_id: int,
    broker_order: dict[str, Any],
) -> tuple[Decimal, Decimal | None]:
    """The fill increment the local ledger is missing: ``(delta_qty, incremental_price)``.

    The incremental price is derived from CUMULATIVE NOTIONAL, never from the broker's cumulative
    average. Booking the missing delta at the cumulative average is only correct when nothing was
    booked before, or when every partial filled at the same price:

        10 @ $100 then 10 @ $120  ->  broker cumulative average $110
        booking the second 10 at $110 records $2,100 against a true cost of $2,200

    Quantity and position convergence both still pass on that, which is exactly what makes it
    dangerous. So: missing notional = broker cumulative notional - locally booked notional, and the
    incremental price is that divided by the missing quantity.

    Returns ``(0, None)`` when nothing is missing. Fails closed on every ambiguity."""
    bqty = _dec(broker_order.get("filled_qty"))
    bavg = _dec(broker_order.get("filled_avg_price"))
    local_qty, local_notional = await _local_booked(session_factory, order_id)

    delta = bqty - local_qty
    if delta < 0:
        raise SettlementError(
            f"order {order_id}: broker filled_qty {bqty} < local booked {local_qty} "
            f"(shrinking fill — ambiguous broker outcome)"
        )
    if delta == 0:
        return Decimal(0), None
    if bavg <= 0:
        raise SettlementError(
            f"order {order_id}: fill delta {delta} but broker reports no average price"
        )

    broker_notional = bqty * bavg
    missing_notional = broker_notional - local_notional
    tolerance = _notional_tolerance(bqty)
    if missing_notional < -tolerance:
        raise SettlementError(
            f"order {order_id}: broker cumulative notional {broker_notional} is below locally "
            f"booked {local_notional} (beyond {tolerance} rounding tolerance) — the ledgers "
            f"disagree on price, not just quantity"
        )
    if missing_notional <= 0:
        raise SettlementError(
            f"order {order_id}: fill delta {delta} carries non-positive notional "
            f"{missing_notional}; refusing to book quantity at a zero or negative price"
        )

    price = (missing_notional / delta).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    if price <= 0:
        raise SettlementError(
            f"order {order_id}: computed incremental price {price} is not positive"
        )
    return delta, price


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
    consumer. This is the ONE place "apply the broker's real outcome locally" is implemented.

    ORDER OF OPERATIONS. Fills are reconciled BEFORE any terminal transition, for every terminal
    status — not only ``filled``. A partially filled order that is then canceled/expired/replaced
    carries a non-zero cumulative ``filled_qty`` on a terminal record, and sending the cancellation
    alone would mark the local order terminal with the fill never booked. The barrier could then
    never repair that ledger, which is the one job it exists to do."""
    bstatus = str(broker_order.get("status") or "").lower()
    is_terminal = bstatus == BROKER_FILLED or bstatus in BROKER_CANCEL
    if not (is_terminal or bstatus == "partially_filled"):
        # Still genuinely working at the broker (new / accepted / pending_* / done_for_day).
        return OrderOutcome(order_id, bstatus, "none", None, None, broker_terminal=False)

    # --- 1. reconcile the cumulative fill, whatever the terminal status ---
    delta, price = await _missing_increment(
        session_factory, order_id=order_id, broker_order=broker_order)
    if delta > 0 and apply:
        # A cancelled/expired remainder means the ORDER is done but this increment is not the whole
        # requested quantity, so it is ingested as a partial: the canonical handler must not infer
        # FILLED from it. The subsequent terminal event carries the real end state.
        event = "fill" if bstatus == BROKER_FILLED else "partial_fill"
        bqty = _dec(broker_order.get("filled_qty"))
        payload: dict[str, Any] = {
            "event": event,
            "broker_order_id": broker_order_id,
            # Deterministic in the CUMULATIVE quantity → a re-run at the same cumulative fill finds
            # delta 0 and ingests nothing; a genuine later increment gets its own id.
            "execution_id": f"settle-{broker_order_id}-{bqty}",
            "qty": str(delta),
            "price": str(price),
            "timestamp": str(broker_order.get("filled_at")),
        }
        try:
            await consumer._handle(payload)
        except Exception as exc:  # noqa: BLE001 — any consumer failure is fail-closed
            raise SettlementError(
                f"order {order_id}: canonical consumer raised on "
                f"{'fill' if event == 'fill' else 'partial-fill'} ingest: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    # --- 2. only then, the terminal transition ---
    if bstatus in BROKER_CANCEL:
        if apply:
            terminal_payload: dict[str, Any] = {
                "event": bstatus, "broker_order_id": broker_order_id, "raw": {},
            }
            try:
                await consumer._handle(terminal_payload)
            except Exception as exc:  # noqa: BLE001
                raise SettlementError(
                    f"order {order_id}: canonical consumer raised on terminal ingest: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc
        return OrderOutcome(order_id, bstatus, "terminal", delta or None, price,
                            broker_terminal=True)

    if bstatus == BROKER_FILLED:
        action = "fill" if delta > 0 else "none"
        return OrderOutcome(order_id, bstatus, action, delta, price, broker_terminal=True)

    # partially_filled — booked (when applying), but NOT terminal; the caller keeps polling.
    return OrderOutcome(order_id, bstatus, "none", delta or None, price, broker_terminal=False)


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
    # Cumulative QUANTITY and cumulative NOTIONAL must both match the broker. Position equality
    # alone is not sufficient: a fill booked at the wrong price leaves the position perfect and the
    # cash, cost basis, realized P&L and loss-control evidence wrong.
    booked_qty, booked_notional = await _local_booked(session_factory, order_id)
    broker_filled = _dec(broker_order.get("filled_qty"))
    broker_avg = _dec(broker_order.get("filled_avg_price"))
    if booked_qty != broker_filled:
        raise SettlementError(
            f"order {order_id}: local booked qty {booked_qty} != broker cumulative "
            f"{broker_filled} after ingest"
        )
    broker_notional = broker_filled * broker_avg
    tolerance = _notional_tolerance(broker_filled)
    if abs(booked_notional - broker_notional) > tolerance:
        raise SettlementError(
            f"order {order_id}: local booked notional {booked_notional} != broker "
            f"{broker_notional} (tolerance {tolerance}) — quantities agree but PRICES do not"
        )

    local_qty = await _local_position_qty(session_factory, account_id, symbol_id)
    try:
        broker_positions = await asyncio.to_thread(adapter.get_positions)
    except Exception as exc:  # noqa: BLE001 — same normalized, credential-safe contract as get_order
        raise SettlementError(
            f"order {order_id}: broker get_positions failed "
            f"({type(exc).__name__}: {str(exc)[:80]})"
        ) from exc
    broker_qty = _broker_qty_for(broker_positions, ticker)
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
        filled_qty=booked_qty,
        local_position=local_qty,
        broker_position=broker_qty,
        polls=polls,
    )
