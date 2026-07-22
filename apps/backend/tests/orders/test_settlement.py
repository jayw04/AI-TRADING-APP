"""ADR 0043 — per-order REST settlement barrier.

The barrier exists because the Phase-0 canary failed twice on SETUP: the trade-updates websocket
was dual-armed, so fills never reached the local ledger and the driver placed order N+1 while
order N was still ``SUBMITTED`` locally. ``settle_order`` is the fix — poll the broker REST for
the order's real outcome, re-apply it through the CANONICAL ``TradeUpdateConsumer._handle``, and
positively verify four things before returning: the LOCAL order is terminal, its fills match the
broker, the LOCAL position equals the BROKER position, and no HELD reservation lingers.

Every test here is written from the same premise: **the caller treats "returned without raising"
as permission to place the next order.** So the failure cases matter more than the happy path —
each one asserts the barrier raises rather than silently reporting "settled". These tests use the
REAL ``TradeUpdateConsumer`` and the REAL ``PositionRecomputer`` against a real (in-memory)
schema; only the broker adapter is faked, because faking the ingest path would test nothing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select, update

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.risk_reservation import (
    RESERVATION_CONSUMED,
    RESERVATION_HELD,
    RESERVATION_RELEASED,
    RiskReservation,
)
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.events.bus import EventBus
from app.orders.lifecycle import TradeUpdateConsumer
from app.orders.positions import PositionRecomputer
from app.orders.settlement import (
    SettlementError,
    resolve_broker_outcome,
    settle_order,
)

TICKER = "MSFT"
# A deadline short enough that the give-up cases don't add seconds to the suite. Only safe for
# tests that either settle on the FIRST poll (the deadline is checked only when NOT terminal) or
# are asserting the timeout itself.
FAST = {"timeout_s": 0.2, "poll_interval_s": 0.005}
# For tests that must reach a LATER poll: the deadline must not be able to expire mid-ingest under
# a loaded machine, or the test becomes order-dependent (it did — caught by random ordering).
PATIENT = {"timeout_s": 10.0, "poll_interval_s": 0.005}


def _now() -> datetime:
    return datetime.now(UTC)


# --------------------------------------------------------------------------------------------
# Fakes — the broker adapter ONLY. Everything below the adapter is the real implementation.
# --------------------------------------------------------------------------------------------


class FakeAdapter:
    """A scripted read-only broker.

    ``order_states`` is consumed one entry per ``get_order`` call; the LAST entry sticks, so a
    single-element script means "the broker keeps saying this". An entry that is an ``Exception``
    is raised (REST unavailable / 404). ``positions`` may be a list or a zero-arg callable, so a
    test can make the broker's position depend on what has settled so far.
    """

    def __init__(
        self,
        order_states: list[Any] | None = None,
        positions: Any = None,
    ) -> None:
        self._order_states = list(order_states or [])
        self._positions = positions if positions is not None else []
        self.get_order_calls: list[str] = []
        self.get_positions_calls = 0

    def get_order(self, broker_order_id: str) -> dict[str, Any] | None:
        self.get_order_calls.append(broker_order_id)
        idx = min(len(self.get_order_calls) - 1, len(self._order_states) - 1)
        state = self._order_states[idx]
        if isinstance(state, Exception):
            raise state
        return state

    def get_positions(self) -> list[dict[str, Any]]:
        self.get_positions_calls += 1
        p = self._positions
        return list(p() if callable(p) else p)


def _broker_order(
    status: str,
    *,
    filled_qty: Any = None,
    filled_avg_price: Any = None,
) -> dict[str, Any]:
    return {
        "id": "b-1",
        "status": status,
        "filled_qty": filled_qty,
        "filled_avg_price": filled_avg_price,
        "filled_at": _now().isoformat(),
    }


# --------------------------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------------------------


@pytest.fixture
async def seeded(session_factory):
    """user 1 / account 1 / symbol 1 (MSFT). No orders — each test adds the ones it needs."""
    async with session_factory() as session:
        session.add(User(id=1, email="j@t"))
        session.add(
            Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Paper")
        )
        session.add(
            Symbol(
                id=1,
                ticker=TICKER,
                exchange="NASDAQ",
                asset_class="us_equity",
                name="Microsoft",
                active=True,
            )
        )
        await session.commit()
    return None


@pytest.fixture
def consumer(session_factory, seeded) -> TradeUpdateConsumer:
    """The REAL consumer wired to the REAL position recomputer — settlement is only meaningful
    if the ingest it drives is the same code the live stream drives."""
    bus = EventBus()
    return TradeUpdateConsumer(session_factory, bus, PositionRecomputer(session_factory, bus))


async def _add_order(
    session_factory,
    *,
    order_id: int,
    side: OrderSide = OrderSide.BUY,
    qty: str = "19",
    status: OrderStatus = OrderStatus.SUBMITTED,
    broker_order_id: str | None = "b-1",
) -> None:
    async with session_factory() as session:
        session.add(
            Order(
                id=order_id,
                user_id=1,
                account_id=1,
                symbol_id=1,
                broker_order_id=broker_order_id,
                client_order_id=f"twb-{order_id}",
                side=side,
                qty=Decimal(qty),
                type=OrderType.MARKET,
                tif=TimeInForce.DAY,
                status=status,
                source_type=OrderSourceType.MANUAL,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        await session.commit()


async def _add_fill(session_factory, *, order_id: int, qty: str, price: str, fill_id: str) -> None:
    async with session_factory() as session:
        session.add(
            Fill(
                order_id=order_id,
                broker_fill_id=fill_id,
                qty=Decimal(qty),
                price=Decimal(price),
                commission=Decimal(0),
                filled_at=_now(),
            )
        )
        await session.commit()


async def _add_reservation(session_factory, *, order_id: int, qty: str = "19") -> int:
    async with session_factory() as session:
        res = RiskReservation(
            account_id=1,
            symbol=TICKER,
            qty=Decimal(qty),
            order_id=order_id,
            state=RESERVATION_HELD,
            created_at=_now(),
        )
        session.add(res)
        await session.commit()
        return res.id


async def _order_row(session_factory, order_id: int) -> Order:
    async with session_factory() as session:
        return await session.scalar(select(Order).where(Order.id == order_id))


async def _fills(session_factory, order_id: int) -> list[Fill]:
    async with session_factory() as session:
        return list(
            (await session.execute(select(Fill).where(Fill.order_id == order_id))).scalars().all()
        )


async def _position_qty(session_factory) -> Decimal | None:
    async with session_factory() as session:
        return await session.scalar(
            select(Position.qty).where(Position.account_id == 1, Position.symbol_id == 1)
        )


async def _reservation_state(session_factory, res_id: int) -> str:
    async with session_factory() as session:
        return await session.scalar(select(RiskReservation.state).where(RiskReservation.id == res_id))


# --------------------------------------------------------------------------------------------
# The failure the barrier was built for: a fill the websocket never delivered
# --------------------------------------------------------------------------------------------


async def test_stream_missed_fill_is_recovered_from_rest(session_factory, consumer) -> None:
    """The canary's actual Phase-0 failure: broker filled, local order still SUBMITTED because
    the dual-armed stream dropped the event. The barrier must book the fill and settle."""
    await _add_order(session_factory, order_id=1)
    adapter = FakeAdapter(
        [_broker_order("filled", filled_qty="19", filled_avg_price="500.00")],
        positions=[{"symbol": TICKER, "qty": "19"}],
    )

    result = await settle_order(
        session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST
    )

    assert result.broker_status == "filled"
    assert result.local_status == OrderStatus.FILLED
    assert result.filled_qty == Decimal("19")
    assert result.local_position == result.broker_position == Decimal("19")

    order = await _order_row(session_factory, 1)
    assert order.status == OrderStatus.FILLED
    assert order.terminal_at is not None
    assert len(await _fills(session_factory, 1)) == 1
    assert await _position_qty(session_factory) == Decimal("19")


async def test_partial_then_final_fill_settles_on_a_later_poll(session_factory, consumer) -> None:
    """A partial books its increment but is NOT terminal — the barrier keeps polling until the
    broker reports the final fill, and the two increments sum to the full quantity."""
    await _add_order(session_factory, order_id=1)
    adapter = FakeAdapter(
        [
            _broker_order("partially_filled", filled_qty="10", filled_avg_price="500.00"),
            _broker_order("filled", filled_qty="19", filled_avg_price="500.00"),
        ],
        positions=[{"symbol": TICKER, "qty": "19"}],
    )

    result = await settle_order(
        session_factory, adapter, consumer, order_id=1, ticker=TICKER, **PATIENT
    )

    assert result.polls == 2
    assert result.filled_qty == Decimal("19")
    fills = await _fills(session_factory, 1)
    assert sorted(f.qty for f in fills) == [Decimal("9"), Decimal("10")]
    assert (await _order_row(session_factory, 1)).status == OrderStatus.FILLED


async def test_incremental_fill_is_priced_from_notional_not_the_running_average(
    session_factory, consumer
) -> None:
    """The defect this test exists for: booking a later increment at the broker's CUMULATIVE
    average silently records the wrong cost.

        10 @ $100, then 10 @ $120  ->  broker cumulative average $110
        booking the second 10 at $110 records $2,100 against a true cost of $2,200

    Quantity and position both still reconcile on that, which is what makes it dangerous. The
    second fill must be booked at $120, derived from the missing notional."""
    await _add_order(session_factory, order_id=1, qty="20")
    adapter = FakeAdapter(
        [
            _broker_order("partially_filled", filled_qty="10", filled_avg_price="100.00"),
            _broker_order("filled", filled_qty="20", filled_avg_price="110.00"),
        ],
        positions=[{"symbol": TICKER, "qty": "20"}],
    )

    result = await settle_order(
        session_factory, adapter, consumer, order_id=1, ticker=TICKER, **PATIENT
    )

    fills = sorted(await _fills(session_factory, 1), key=lambda f: f.price)
    assert [f.qty for f in fills] == [Decimal("10"), Decimal("10")]
    assert [f.price for f in fills] == [Decimal("100"), Decimal("120")]
    booked_notional = sum(f.qty * f.price for f in fills)
    assert booked_notional == Decimal("2200"), "true cost, not the running-average figure"
    assert result.filled_qty == Decimal("20")


async def test_settlement_rejects_a_ledger_whose_prices_contradict_the_broker(
    session_factory, consumer
) -> None:
    """Quantities agree, prices do not: position equality would pass, so the barrier compares
    cumulative NOTIONAL as well."""
    await _add_order(session_factory, order_id=1)
    # Locally booked at $400; the broker says the same 19 shares filled at $500.
    await _add_fill(session_factory, order_id=1, qty="19", price="400.00", fill_id="x-1")
    adapter = FakeAdapter(
        [_broker_order("filled", filled_qty="19", filled_avg_price="500.00")],
        positions=[{"symbol": TICKER, "qty": "19"}],
    )
    async with session_factory() as session:
        await session.execute(
            update(Order).where(Order.id == 1).values(
                status=OrderStatus.FILLED, terminal_at=_now())
        )
        await session.commit()

    with pytest.raises(SettlementError, match="PRICES do not"):
        await settle_order(session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST)


async def test_non_positive_incremental_notional_fails_closed(session_factory, consumer) -> None:
    """A delta whose implied cost is zero or negative is never bookable — refuse rather than
    record quantity at a nonsensical price."""
    await _add_order(session_factory, order_id=1, qty="20")
    # 10 already booked at $200 = $2,000; broker says 20 filled at a $100 average = $2,000 total,
    # leaving 10 shares to book for $0.
    await _add_fill(session_factory, order_id=1, qty="10", price="200.00", fill_id="x-1")
    adapter = FakeAdapter([_broker_order("filled", filled_qty="20", filled_avg_price="100.00")])

    with pytest.raises(SettlementError, match="non-positive notional"):
        await settle_order(session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST)


async def test_an_increment_too_small_to_price_fails_closed(session_factory, consumer) -> None:
    """A missing notional so small that the incremental price rounds to zero at storage precision
    (4dp). Booking quantity at 0.0000 would record a free position — refuse instead."""
    await _add_order(session_factory, order_id=1, qty="1")
    adapter = FakeAdapter([_broker_order("filled", filled_qty="1",
                                         filled_avg_price="0.00004")])

    with pytest.raises(SettlementError, match="is not positive"):
        await settle_order(session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST)

    assert await _fills(session_factory, 1) == []


async def test_ingest_that_books_the_wrong_quantity_fails_closed(
    session_factory, consumer, monkeypatch
) -> None:
    """Final backstop: even if the canonical handler books something other than what was asked
    for, the barrier compares the LEDGER against the broker rather than trusting the ingest."""
    await _add_order(session_factory, order_id=1, qty="1")
    real_handle = consumer._handle

    async def _short_book(payload: dict[str, Any]) -> None:
        if payload.get("event") in ("fill", "partial_fill"):
            payload = {**payload, "qty": "1"}          # books 1 where 19 was required
        await real_handle(payload)

    monkeypatch.setattr(consumer, "_handle", _short_book)
    adapter = FakeAdapter(
        [_broker_order("filled", filled_qty="19", filled_avg_price="500.00")],
        positions=[{"symbol": TICKER, "qty": "19"}],
    )

    with pytest.raises(SettlementError, match="!= broker cumulative"):
        await settle_order(session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST)


async def test_broker_notional_below_local_booked_fails_closed(session_factory, consumer) -> None:
    await _add_order(session_factory, order_id=1, qty="20")
    await _add_fill(session_factory, order_id=1, qty="10", price="500.00", fill_id="x-1")
    # 20 @ $100 = $2,000 cumulative, but $5,000 is already booked locally.
    adapter = FakeAdapter([_broker_order("filled", filled_qty="20", filled_avg_price="100.00")])

    with pytest.raises(SettlementError, match="below locally booked"):
        await settle_order(session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST)


# --------------------------------------------------------------------------------------------
# Terminal outcomes that carry a REAL fill — the cancellation-after-partial family
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("broker_status", "expected"),
    [
        ("canceled", OrderStatus.CANCELED),
        ("expired", OrderStatus.EXPIRED),
    ],
)
async def test_partial_fill_then_terminal_books_the_fill_before_the_transition(
    session_factory, consumer, broker_status: str, expected: OrderStatus
) -> None:
    """The defect this family exists for: a broker order that partially fills and is THEN
    cancelled/expired/replaced carries a non-zero cumulative ``filled_qty`` on a terminal record.
    Sending the cancellation alone marks the local order terminal with the fill never booked — and
    a terminal order is exactly what the barrier can no longer repair."""
    await _add_order(session_factory, order_id=1, qty="19")
    adapter = FakeAdapter(
        [_broker_order(broker_status, filled_qty="5", filled_avg_price="500.00")],
        positions=[{"symbol": TICKER, "qty": "5"}],
    )

    result = await settle_order(
        session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST
    )

    fills = await _fills(session_factory, 1)
    assert [f.qty for f in fills] == [Decimal("5")], "the partial fill must be booked"
    assert fills[0].price == Decimal("500")
    assert result.filled_qty == Decimal("5")
    order = await _order_row(session_factory, 1)
    assert order.status == expected                       # and the order still reaches terminal
    assert order.terminal_at is not None
    assert await _position_qty(session_factory) == Decimal("5")


async def test_replaced_currently_fails_closed_on_a_missing_audit_action(
    session_factory, consumer
) -> None:
    """PRE-EXISTING GAP, documented rather than silently fixed.

    ``TradeUpdateConsumer._handle_terminal`` maps a broker ``replaced`` event to
    ``OrderStatus.REPLACED`` and then builds ``AuditAction("ORDER_REPLACED")`` — which does not
    exist, so the canonical handler raises. That is a latent defect in the LIVE consumer (a real
    ``replaced`` event from the stream would hit it too), not something this barrier introduced.

    Adding the enum value means touching the audit surface and the on-call playbook, which is its
    own change with its own review. Until then the barrier does the right thing: it fails CLOSED and
    names the cause, rather than reporting a settlement it could not perform."""
    await _add_order(session_factory, order_id=1, qty="19")
    adapter = FakeAdapter(
        [_broker_order("replaced", filled_qty="5", filled_avg_price="500.00")],
        positions=[{"symbol": TICKER, "qty": "5"}],
    )

    with pytest.raises(SettlementError, match="raised on terminal ingest"):
        await settle_order(session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST)

    # The FILL was still booked before the terminal attempt — that ordering is the whole point.
    assert [f.qty for f in await _fills(session_factory, 1)] == [Decimal("5")]


async def test_partial_then_cancel_across_two_polls_books_only_the_increment(
    session_factory, consumer
) -> None:
    """The realistic sequence: we see the partial while it is still working, then see the
    cancellation. The already-booked 5 must not be double-counted."""
    await _add_order(session_factory, order_id=1, qty="19")
    adapter = FakeAdapter(
        [
            _broker_order("partially_filled", filled_qty="5", filled_avg_price="500.00"),
            _broker_order("canceled", filled_qty="5", filled_avg_price="500.00"),
        ],
        positions=[{"symbol": TICKER, "qty": "5"}],
    )

    result = await settle_order(
        session_factory, adapter, consumer, order_id=1, ticker=TICKER, **PATIENT
    )

    assert result.polls == 2
    assert len(await _fills(session_factory, 1)) == 1
    assert (await _order_row(session_factory, 1)).status == OrderStatus.CANCELED


async def test_re_settling_a_cancelled_partial_is_idempotent(session_factory, consumer) -> None:
    """A second pass must neither re-book the fill nor disturb the terminal state."""
    await _add_order(session_factory, order_id=1, qty="19")
    adapter = FakeAdapter(
        [_broker_order("canceled", filled_qty="5", filled_avg_price="500.00")],
        positions=[{"symbol": TICKER, "qty": "5"}],
    )

    first = await settle_order(
        session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST
    )
    second = await settle_order(
        session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST
    )

    assert len(await _fills(session_factory, 1)) == 1
    assert first.filled_qty == second.filled_qty == Decimal("5")
    assert (await _order_row(session_factory, 1)).status == OrderStatus.CANCELED
    assert await _position_qty(session_factory) == Decimal("5")


async def test_cancelled_partial_at_a_second_price_is_priced_from_notional(
    session_factory, consumer
) -> None:
    """Both defects at once: a cancellation carrying a cumulative fill booked at more than one
    price. The recovered increment must be priced from the missing notional."""
    await _add_order(session_factory, order_id=1, qty="30")
    await _add_fill(session_factory, order_id=1, qty="10", price="100.00", fill_id="x-1")
    adapter = FakeAdapter(
        # 20 cumulative at a $110 average = $2,200; $1,000 booked, so 10 more for $1,200 = $120.
        [_broker_order("canceled", filled_qty="20", filled_avg_price="110.00")],
        positions=[{"symbol": TICKER, "qty": "20"}],
    )

    await settle_order(session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST)

    fills = sorted(await _fills(session_factory, 1), key=lambda f: f.price)
    assert [(f.qty, f.price) for f in fills] == [
        (Decimal("10"), Decimal("100")), (Decimal("10"), Decimal("120"))]
    assert (await _order_row(session_factory, 1)).status == OrderStatus.CANCELED


@pytest.mark.parametrize(
    ("broker_status", "expected"),
    [
        ("canceled", OrderStatus.CANCELED),
        ("expired", OrderStatus.EXPIRED),
        ("rejected", OrderStatus.REJECTED),
    ],
)
async def test_terminal_non_fill_outcomes_settle(
    session_factory, consumer, broker_status: str, expected: OrderStatus
) -> None:
    """Cancel / expire / reject are settled outcomes too — the order is done, nothing filled, and
    the local position is unchanged (flat here). The barrier must NOT hang waiting for a fill."""
    await _add_order(session_factory, order_id=1)
    adapter = FakeAdapter([_broker_order(broker_status)], positions=[])

    result = await settle_order(
        session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST
    )

    assert result.broker_status == broker_status
    assert result.local_status == expected
    assert result.filled_qty == Decimal("0")
    assert (await _order_row(session_factory, 1)).terminal_at is not None
    assert await _fills(session_factory, 1) == []


async def test_re_settling_a_settled_order_is_idempotent(session_factory, consumer) -> None:
    """The driver may settle the same order twice (retry, restart, belt-and-braces). The second
    pass must not double-book the fill or double-count the position."""
    await _add_order(session_factory, order_id=1)
    adapter = FakeAdapter(
        [_broker_order("filled", filled_qty="19", filled_avg_price="500.00")],
        positions=[{"symbol": TICKER, "qty": "19"}],
    )

    first = await settle_order(
        session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST
    )
    second = await settle_order(
        session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST
    )

    assert len(await _fills(session_factory, 1)) == 1
    assert first.filled_qty == second.filled_qty == Decimal("19")
    assert await _position_qty(session_factory) == Decimal("19")


# --------------------------------------------------------------------------------------------
# Fail-closed: every one of these must RAISE rather than report "settled"
# --------------------------------------------------------------------------------------------


async def test_rest_unavailable_fails_closed(session_factory, consumer) -> None:
    """A broker we cannot reach tells us NOTHING about the order. Guessing "probably fine" is
    precisely how the canary placed a second order against an unknown ledger."""
    await _add_order(session_factory, order_id=1)
    adapter = FakeAdapter([ConnectionError("connection reset")])

    with pytest.raises(SettlementError, match="get_order failed"):
        await settle_order(session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST)

    assert await _fills(session_factory, 1) == []
    assert (await _order_row(session_factory, 1)).status == OrderStatus.SUBMITTED


async def test_get_positions_failure_uses_the_same_error_contract(
    session_factory, consumer
) -> None:
    """A broker read that fails during VERIFICATION must surface as a SettlementError like every
    other barrier failure — same normalized, credential-safe contract as get_order, not a raw
    adapter exception escaping through a different shape."""
    await _add_order(session_factory, order_id=1)
    adapter = FakeAdapter([_broker_order("filled", filled_qty="19", filled_avg_price="500.00")])
    adapter.get_positions = lambda: (_ for _ in ()).throw(ConnectionError("reset"))  # type: ignore[method-assign]

    with pytest.raises(SettlementError, match="get_positions failed"):
        await settle_order(session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST)


async def test_broker_returns_no_order_fails_closed(session_factory, consumer) -> None:
    await _add_order(session_factory, order_id=1)
    adapter = FakeAdapter([None])

    with pytest.raises(SettlementError, match="no order/status"):
        await settle_order(session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST)


async def test_still_working_at_timeout_fails_closed(session_factory, consumer) -> None:
    """An order that never reaches terminal is UNRESOLVED, not settled. The barrier must block
    the sequence rather than let the next leg go out against a live working order."""
    await _add_order(session_factory, order_id=1)
    adapter = FakeAdapter([_broker_order("new")])

    with pytest.raises(SettlementError, match="still non-terminal"):
        await settle_order(session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST)

    assert len(adapter.get_order_calls) >= 2, "should have polled repeatedly before giving up"


async def test_shrinking_filled_qty_fails_closed(session_factory, consumer) -> None:
    """Broker reports LESS filled than we have booked — the two ledgers disagree in a direction
    no reconciliation can explain. Ambiguous, so stop."""
    await _add_order(session_factory, order_id=1)
    await _add_fill(session_factory, order_id=1, qty="19", price="500.00", fill_id="x-1")
    adapter = FakeAdapter([_broker_order("filled", filled_qty="10", filled_avg_price="500.00")])

    with pytest.raises(SettlementError, match="shrinking fill"):
        await settle_order(session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST)


async def test_fill_without_average_price_fails_closed(session_factory, consumer) -> None:
    """A fill we cannot price cannot be booked — an unpriced Fill row would corrupt cost basis."""
    await _add_order(session_factory, order_id=1)
    adapter = FakeAdapter([_broker_order("filled", filled_qty="19", filled_avg_price=None)])

    with pytest.raises(SettlementError, match="no average price"):
        await settle_order(session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST)

    assert await _fills(session_factory, 1) == []


async def test_local_position_diverging_from_broker_fails_closed(
    session_factory, consumer
) -> None:
    """The order settled, but the ACCOUNT did not reconcile — exactly the ghost-position shape
    that fools downstream risk checks. Terminal order + wrong position is still a hard stop."""
    await _add_order(session_factory, order_id=1)
    adapter = FakeAdapter(
        [_broker_order("filled", filled_qty="19", filled_avg_price="500.00")],
        positions=[{"symbol": TICKER, "qty": "31"}],  # broker holds more than our fills imply
    )

    with pytest.raises(SettlementError, match=r"local position 19\S* != broker 31"):
        await settle_order(session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST)


async def test_local_order_not_terminal_after_ingest_fails_closed(
    session_factory, consumer
) -> None:
    """Broker says done, ingest changed nothing, local order is still SUBMITTED. Reporting
    "settled" here would hand the caller a lie about its own ledger."""
    await _add_order(session_factory, order_id=1)
    # Terminal at the broker with nothing to book (filled_qty 0) → no ingest → local unchanged.
    adapter = FakeAdapter([_broker_order("filled", filled_qty="0", filled_avg_price="0")])

    with pytest.raises(SettlementError, match="LOCAL order still submitted"):
        await settle_order(session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST)


async def test_consumer_raising_fails_closed(session_factory, consumer, monkeypatch) -> None:
    """If the canonical ingest path raises, the outcome was NOT applied. Swallowing that would
    leave the ledger behind the broker with no signal."""
    await _add_order(session_factory, order_id=1)

    async def _boom(payload: dict[str, Any]) -> None:
        raise RuntimeError("db locked")

    monkeypatch.setattr(consumer, "_handle", _boom)
    adapter = FakeAdapter([_broker_order("filled", filled_qty="19", filled_avg_price="500.00")])

    with pytest.raises(SettlementError, match="canonical consumer raised"):
        await settle_order(session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST)


async def test_consumer_raising_on_terminal_ingest_fails_closed(
    session_factory, consumer, monkeypatch
) -> None:
    """Same rule on the non-fill path: if the cancel/reject transition did not land locally, the
    order is not settled no matter what the broker says."""
    await _add_order(session_factory, order_id=1)

    async def _boom(payload: dict[str, Any]) -> None:
        raise RuntimeError("db locked")

    monkeypatch.setattr(consumer, "_handle", _boom)

    with pytest.raises(SettlementError, match="raised on terminal ingest"):
        await settle_order(
            session_factory, FakeAdapter([_broker_order("canceled")]), consumer,
            order_id=1, ticker=TICKER, **FAST,
        )


async def test_partial_fill_shrinking_qty_fails_closed(session_factory, consumer) -> None:
    """The shrinking-fill contradiction is rejected on the PARTIAL path too — a partial is still
    a cumulative figure, so it can only ever grow."""
    await _add_order(session_factory, order_id=1)
    await _add_fill(session_factory, order_id=1, qty="10", price="500.00", fill_id="x-1")

    with pytest.raises(SettlementError, match="broker filled_qty 5 < local booked 10"):
        await resolve_broker_outcome(
            session_factory, consumer,
            order_id=1, broker_order_id="b-1",
            broker_order=_broker_order("partially_filled", filled_qty="5", filled_avg_price="500"),
            apply=True,
        )


async def test_partial_fill_without_average_price_fails_closed(
    session_factory, consumer
) -> None:
    await _add_order(session_factory, order_id=1)

    with pytest.raises(SettlementError, match="fill delta 10 but broker reports no average price"):
        await resolve_broker_outcome(
            session_factory, consumer,
            order_id=1, broker_order_id="b-1",
            broker_order=_broker_order("partially_filled", filled_qty="10", filled_avg_price=None),
            apply=True,
        )

    assert await _fills(session_factory, 1) == []


async def test_consumer_raising_on_partial_ingest_fails_closed(
    session_factory, consumer, monkeypatch
) -> None:
    await _add_order(session_factory, order_id=1)

    async def _boom(payload: dict[str, Any]) -> None:
        raise RuntimeError("db locked")

    monkeypatch.setattr(consumer, "_handle", _boom)

    with pytest.raises(SettlementError, match="raised on partial-fill ingest"):
        await resolve_broker_outcome(
            session_factory, consumer,
            order_id=1, broker_order_id="b-1",
            broker_order=_broker_order("partially_filled", filled_qty="10", filled_avg_price="500"),
            apply=True,
        )


async def test_order_vanishing_mid_settlement_fails_closed(
    session_factory, consumer, monkeypatch
) -> None:
    """Defensive, but the barrier's whole value is that it never infers. If the order row is gone
    by the time we verify, there is nothing to assert terminality about."""
    await _add_order(session_factory, order_id=1)
    real_handle = consumer._handle

    async def _handle_then_delete(payload: dict[str, Any]) -> None:
        await real_handle(payload)
        async with session_factory() as session:
            await session.delete(await session.get(Order, 1))
            await session.commit()

    monkeypatch.setattr(consumer, "_handle", _handle_then_delete)
    adapter = FakeAdapter([_broker_order("filled", filled_qty="19", filled_avg_price="500.00")])

    with pytest.raises(SettlementError, match="vanished during settlement"):
        await settle_order(session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST)


async def test_order_never_reached_the_broker_fails_closed(session_factory, consumer) -> None:
    await _add_order(session_factory, order_id=1, broker_order_id=None)
    adapter = FakeAdapter([_broker_order("filled", filled_qty="19", filled_avg_price="500")])

    with pytest.raises(SettlementError, match="never reached the broker"):
        await settle_order(session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST)

    assert adapter.get_order_calls == []


async def test_unknown_local_order_fails_closed(session_factory, consumer) -> None:
    with pytest.raises(SettlementError, match="not found locally"):
        await settle_order(session_factory, FakeAdapter(), consumer, order_id=404, ticker=TICKER, **FAST)


# --------------------------------------------------------------------------------------------
# Reservations — released only after terminal, and a leak blocks the sequence
# --------------------------------------------------------------------------------------------


async def test_reservation_is_consumed_by_the_settled_fill(session_factory, consumer) -> None:
    """ADR 0042: a HELD reservation holds reducible capacity until the order is terminal. The
    barrier drives the canonical ingest, so settling is what consumes it."""
    await _add_order(session_factory, order_id=1, side=OrderSide.SELL)
    res_id = await _add_reservation(session_factory, order_id=1)
    assert await _reservation_state(session_factory, res_id) == RESERVATION_HELD

    adapter = FakeAdapter(
        [_broker_order("filled", filled_qty="19", filled_avg_price="500.00")],
        positions=[{"symbol": TICKER, "qty": "-19"}],
    )
    await settle_order(session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST)

    assert await _reservation_state(session_factory, res_id) == RESERVATION_CONSUMED


async def test_reservation_is_released_by_a_canceled_order(session_factory, consumer) -> None:
    """A reduction that never filled must give its capacity back — a HELD reservation left behind
    a canceled order is the exact leak that made acct 3 unable to de-risk."""
    await _add_order(session_factory, order_id=1, side=OrderSide.SELL)
    res_id = await _add_reservation(session_factory, order_id=1)

    adapter = FakeAdapter([_broker_order("canceled")], positions=[])
    await settle_order(session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST)

    assert await _reservation_state(session_factory, res_id) == RESERVATION_RELEASED


async def test_lingering_held_reservation_fails_closed(session_factory, consumer) -> None:
    """Order terminal, position correct, but a HELD reservation survived — capacity is still
    being consumed by a finished order, so the account is NOT in a state to place the next one."""
    await _add_order(session_factory, order_id=1, status=OrderStatus.FILLED)
    await _add_fill(session_factory, order_id=1, qty="19", price="500.00", fill_id="x-1")
    # Reservation added AFTER the fill, so nothing in the ingest path settles it: a pure leak.
    res_id = await _add_reservation(session_factory, order_id=1)
    adapter = FakeAdapter(
        [_broker_order("filled", filled_qty="19", filled_avg_price="500.00")],
        positions=[{"symbol": TICKER, "qty": "19"}],
    )
    # Position already reconciled by hand so the ONLY failing precondition is the reservation.
    async with session_factory() as session:
        session.add(
            Position(
                user_id=1,
                account_id=1,
                symbol_id=1,
                qty=Decimal("19"),
                avg_entry_price=Decimal("500"),
                side="long",
                market_value=Decimal(0),
                cost_basis=Decimal("9500"),
                unrealized_pl=Decimal(0),
                unrealized_plpc=Decimal(0),
                updated_at=_now(),
            )
        )
        await session.commit()

    with pytest.raises(SettlementError, match="HELD reservation still lingers"):
        await settle_order(session_factory, adapter, consumer, order_id=1, ticker=TICKER, **FAST)

    assert await _reservation_state(session_factory, res_id) == RESERVATION_HELD


# --------------------------------------------------------------------------------------------
# The sequencing contract the churn driver depends on
# --------------------------------------------------------------------------------------------


async def test_buy_then_sell_settles_back_to_flat(session_factory, consumer) -> None:
    """A2 (buy) then A3 (sell): each leg settles against the broker's position AT THAT POINT, and
    the round trip ends flat locally and at the broker."""
    broker_qty = {"n": 0}

    def _positions() -> list[dict[str, Any]]:
        return [{"symbol": TICKER, "qty": str(broker_qty["n"])}] if broker_qty["n"] else []

    await _add_order(session_factory, order_id=1, side=OrderSide.BUY)
    broker_qty["n"] = 19
    buy_adapter = FakeAdapter(
        [_broker_order("filled", filled_qty="19", filled_avg_price="500.00")],
        positions=_positions,
    )
    buy = await settle_order(
        session_factory, buy_adapter, consumer, order_id=1, ticker=TICKER, **FAST
    )
    assert buy.local_position == Decimal("19")

    await _add_order(session_factory, order_id=2, side=OrderSide.SELL, broker_order_id="b-2")
    broker_qty["n"] = 0
    sell_adapter = FakeAdapter(
        [_broker_order("filled", filled_qty="19", filled_avg_price="505.00")],
        positions=_positions,
    )
    sell = await settle_order(
        session_factory, sell_adapter, consumer, order_id=2, ticker=TICKER, **FAST
    )

    assert sell.local_position == sell.broker_position == Decimal("0")
    assert await _position_qty(session_factory) is None  # flat rows are deleted, not zeroed
    assert (await _order_row(session_factory, 2)).status == OrderStatus.FILLED


async def test_second_leg_is_not_submitted_until_the_first_settles(
    session_factory, consumer
) -> None:
    """The contract the churn driver is built on: a leg is submitted ONLY after the previous leg's
    barrier returns. When the barrier raises, the sequence stops — no second order goes out.

    This is the regression test for the Phase-0 failure itself. The old driver submitted leg 2 on
    a wall-clock sleep, which is why it traded against a ledger that had not caught up."""
    submitted: list[int] = []

    async def _governed_sequence(adapter: FakeAdapter) -> None:
        for order_id in (1, 2):
            submitted.append(order_id)
            await settle_order(
                session_factory, adapter, consumer, order_id=order_id, ticker=TICKER, **FAST
            )

    await _add_order(session_factory, order_id=1)
    await _add_order(session_factory, order_id=2, broker_order_id="b-2")
    adapter = FakeAdapter([_broker_order("new")])  # leg 1 never reaches terminal

    with pytest.raises(SettlementError):
        await _governed_sequence(adapter)

    assert submitted == [1], "leg 2 must not be submitted while leg 1 is unsettled"
    assert (await _order_row(session_factory, 2)).status == OrderStatus.SUBMITTED


# --------------------------------------------------------------------------------------------
# resolve_broker_outcome — the shared drift step reconcile_stuck_orders also imports
# --------------------------------------------------------------------------------------------


async def test_resolve_without_apply_reports_drift_but_writes_nothing(
    session_factory, consumer
) -> None:
    """``apply=False`` is the dry-run reconcile_stuck_orders uses to REPORT drift. It must compute
    the same delta as the applying path while leaving the ledger untouched."""
    await _add_order(session_factory, order_id=1)

    outcome = await resolve_broker_outcome(
        session_factory,
        consumer,
        order_id=1,
        broker_order_id="b-1",
        broker_order=_broker_order("filled", filled_qty="19", filled_avg_price="500.00"),
        apply=False,
    )

    assert outcome.action == "fill"
    assert outcome.delta == Decimal("19")
    assert outcome.broker_terminal is True
    assert await _fills(session_factory, 1) == []
    assert (await _order_row(session_factory, 1)).status == OrderStatus.SUBMITTED


async def test_resolve_reports_working_order_as_non_terminal(session_factory, consumer) -> None:
    outcome = await resolve_broker_outcome(
        session_factory,
        consumer,
        order_id=1,
        broker_order_id="b-1",
        broker_order=_broker_order("accepted"),
        apply=True,
    )

    assert outcome.action == "none"
    assert outcome.broker_terminal is False
