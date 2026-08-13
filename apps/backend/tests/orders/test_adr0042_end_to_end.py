"""ADR 0042 — end-to-end through the REAL OrderRouter, on a locked account.

Everything up to now proved that ``RiskEngine.evaluate()`` returns PASS for a verified
reduction. That is not the claim that matters. The claim that matters is:

    **the reduction actually reaches the broker.**

On 2026-07-13 the momentum book's SNDK and LITE trims were *evaluated* and then *refused*, and
no order was ever sent. So these tests assert on ``adapter.submit_order`` — the real boundary —
not on a decision object.

They run the full path: OrderRouter.submit → RiskEngine.evaluate → steps 9/13 → classifier →
snapshot → reservation → ledger → broker. Nothing is stubbed except the broker itself.
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    RiskScopeType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.risk_decision import RiskDecision as LedgerRow
from app.db.models.risk_limits import RiskLimits
from app.db.models.risk_reservation import RESERVATION_HELD, RiskReservation
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.events.bus import EventBus
from app.orders.router import OrderRouter
from app.risk import OrderRequest, RiskEngine

D = Decimal

# The real account-1 numbers from the incident.
BREACHED_DAY_PNL = D("-6790.61")
DAILY_LOSS_CAP = D("5000")


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def seeded(session_factory):
    """A paper account in DAILY-LOSS BREACH, holding 500 AAPL @ $100."""
    async with session_factory() as s:
        s.add(User(id=1, email="t@local"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper,
                      label="Alpaca Paper", created_at=_now()))
        s.add(RiskLimits(
            id=1, user_id=1, broker_mode=AccountMode.paper,
            scope_type=RiskScopeType.GLOBAL,
            max_daily_loss=DAILY_LOSS_CAP, max_gross_exposure=D("1000000"),
            max_orders_per_minute=100, allow_short=False,
            created_at=_now(), updated_at=_now(),
        ))
        s.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ", asset_class="us_equity",
                     name="Apple", active=True))
        s.add(Position(user_id=1, account_id=1, symbol_id=1, qty=D("500"),
                       avg_entry_price=D("100"), side="long", updated_at=_now()))
        s.add(AccountState(
            account_id=1, cash=D("1000"), equity=D("100000") + BREACHED_DAY_PNL,
            last_equity=D("100000"), buying_power=D("1000"),
            portfolio_value=D("100000"), daytrade_count=0,
            day_change=BREACHED_DAY_PNL, day_change_pct=D("0"),
            status="ACTIVE", updated_at=_now(), raw_payload={},
        ))
        await s.commit()
    return session_factory


def _broker(positions=None):
    """A broker that REMEMBERS what it accepted.

    An accepted order appears in ``list_orders(status="open")`` with a broker-issued stamp
    until it terminalises — which is what every real broker does, and what the causality
    check in ``account_snapshot`` reads. The earlier stub returned a constant ``[]`` here,
    so an account that had just been sent an order still looked flat of open orders; that
    is a state no broker produces.

    ⚠ It also returned ``id="acct"`` as the account id. Under the pre-#529 code that id was
    used as the ``broker_cursor`` fallback, and ``"acct"`` sorts AFTER every ``"2026-…"``
    ISO stamp, so the comparison passed. That is the same accident that made four production
    accounts pass while accounts 1 and 5 were permanently stale — the stub was riding the
    bug, not testing around it.
    """
    a = MagicMock()
    a.is_paper = True
    counter = itertools.count(1)
    live: list[dict] = []

    # A distinct broker id per call: orders.broker_order_id is UNIQUE, and a stub that
    # returns the same id twice fails the second insert for reasons that have nothing to do
    # with risk.
    def _submit(**kw):
        n = next(counter)
        live.append({
            "id": f"broker-{n}",
            "symbol": str(kw.get("symbol", "AAPL")).upper(),
            "side": "sell" if str(kw.get("side", "")).lower().endswith("sell") else "buy",
            "qty": str(kw.get("qty", "0")),
            "filled_qty": "0",
            # broker-issued, on the broker's own roughly-synchronised clock
            "submitted_at": _now().isoformat(),
        })
        return {"id": f"broker-{n}", "status": "accepted"}

    a.submit_order.side_effect = _submit
    a.get_account.return_value = {"cash": "1000", "equity": "93209", "id": "acct"}
    a.get_positions.return_value = positions if positions is not None else [
        {"symbol": "AAPL", "qty": "500", "side": "long", "current_price": "100"}
    ]
    a.list_orders.side_effect = lambda **kw: list(live)
    return a


def _router(session_factory, adapter):
    reg = MagicMock()
    reg.get.return_value = adapter
    engine = RiskEngine(session_factory, broker_registry=reg)
    return OrderRouter(adapter, engine, session_factory, EventBus(), broker_registry=reg)


def _req(side: OrderSide, qty: str, source=OrderSourceType.STRATEGY) -> OrderRequest:
    return OrderRequest(
        user_id=1, account_id=1, symbol_ticker="AAPL", side=side, qty=D(qty),
        type=OrderType.MARKET, tif=TimeInForce.DAY, source_type=source,
    )


# ============================================================ THE CLAIM THAT MATTERS


@pytest.mark.usefixtures("_market_open")
async def test_a_verified_reduction_REACHES_THE_BROKER_on_a_locked_account(seeded):
    """2026-07-13, corrected, end to end.

    The account is in daily-loss breach. The strategy proposes a trim. The order must not merely
    'evaluate to PASS' — it must be SENT, persisted, and acknowledged.
    """
    adapter = _broker()
    router = _router(seeded, adapter)

    order = await router.submit(_req(OrderSide.SELL, "100"))

    # The boundary that actually matters.
    adapter.submit_order.assert_called_once()
    sent = adapter.submit_order.call_args.kwargs
    assert sent["symbol"] == "AAPL"
    assert str(sent["side"]).lower().endswith("sell")
    assert Decimal(str(sent["qty"])) == D("100")

    assert order.status == OrderStatus.SUBMITTED
    assert order.broker_order_id == "broker-1"

    async with seeded() as s:
        rows = list((await s.execute(select(LedgerRow))).scalars().all())
        held = list(
            (
                await s.execute(
                    select(RiskReservation).where(RiskReservation.state == RESERVATION_HELD)
                )
            ).scalars().all()
        )
    assert [r.decision for r in rows] == ["ALLOW"]
    assert rows[0].risk_effect == "RISK_REDUCING"
    assert rows[0].lock_state == "DAILY_LOSS"
    assert rows[0].daily_pnl == D("-6790.6100")
    assert len(held) == 1 and held[0].qty == D("100")


@pytest.mark.usefixtures("_market_open")
async def test_a_buy_NEVER_reaches_the_broker_on_a_locked_account(seeded):
    """Nothing loosens. The BE-shaped entry from the same 10:00 run stays blocked."""
    adapter = _broker()
    router = _router(seeded, adapter)

    order = await router.submit(_req(OrderSide.BUY, "10"))

    adapter.submit_order.assert_not_called()
    assert order.status == OrderStatus.REJECTED

    async with seeded() as s:
        rows = list((await s.execute(select(LedgerRow))).scalars().all())
    assert rows[0].decision == "REJECT"
    assert rows[0].risk_effect == "RISK_INCREASING"


@pytest.mark.usefixtures("_market_open")
async def test_an_oversell_never_reaches_the_broker(seeded):
    """600 against a long of 500 would cross zero into a short."""
    adapter = _broker()
    router = _router(seeded, adapter)

    order = await router.submit(_req(OrderSide.SELL, "600"))

    adapter.submit_order.assert_not_called()
    assert order.status == OrderStatus.REJECTED


@pytest.mark.usefixtures("_market_open")
async def test_a_manual_reduction_reaches_the_broker_too(seeded):
    """§ C — source-neutral, end to end. Trapped risk is equally dangerous regardless of who
    initiated the reduction."""
    adapter = _broker()
    router = _router(seeded, adapter)

    order = await router.submit(_req(OrderSide.SELL, "100", OrderSourceType.MANUAL))

    adapter.submit_order.assert_called_once()
    assert order.status == OrderStatus.SUBMITTED

    async with seeded() as s:
        rows = list((await s.execute(select(LedgerRow))).scalars().all())
    assert rows[0].source_type == "MANUAL"
    assert rows[0].risk_effect == "RISK_REDUCING"


# ============================================================ CAPACITY, END TO END


@pytest.mark.usefixtures("_market_open")
async def test_reductions_cannot_be_stacked_past_the_position(seeded):
    """§ D through the real router. Three 200-share trims against a long of 500: the first two
    fit (400), the third would take it to 600 — past the position, into a short.

    The broker never sees the third. Note this holds even though each order, evaluated against
    the broker's own UNCHANGED position of 500, looks individually legal — the reservations are
    what remember the first two.
    """
    adapter = _broker()
    router = _router(seeded, adapter)

    a = await router.submit(_req(OrderSide.SELL, "200"))
    b = await router.submit(_req(OrderSide.SELL, "200"))
    c = await router.submit(_req(OrderSide.SELL, "200"))

    assert a.status == OrderStatus.SUBMITTED
    assert b.status == OrderStatus.SUBMITTED
    assert c.status == OrderStatus.REJECTED

    assert adapter.submit_order.call_count == 2

    async with seeded() as s:
        held = list(
            (
                await s.execute(
                    select(RiskReservation).where(RiskReservation.state == RESERVATION_HELD)
                )
            ).scalars().all()
        )
    assert sum(r.qty for r in held) == D("400")  # never exceeds the 500 long


# ============================================================ THE UNLOCKED PATH


@pytest.mark.usefixtures("_market_open")
async def test_an_unlocked_account_submits_a_buy_with_no_ledger_row(seeded):
    """The safety property, end to end: with no lock, ADR 0042 is not in the path at all."""
    async with seeded() as s:
        st = (
            await s.execute(select(AccountState).where(AccountState.account_id == 1))
        ).scalars().first()
        # BOTH must move. CircuitBreakerService.check() does NOT trust the day_change column —
        # it RECOMPUTES the daily P&L from (equity - last_equity). Setting day_change alone
        # leaves the two disagreeing, and the breaker re-derives the breach from equity and
        # trips anyway. (Correct of the breaker; a trap for the unwary.)
        st.day_change = D("-100")
        st.equity = st.last_equity - D("100")
        await s.commit()

    adapter = _broker()
    router = _router(seeded, adapter)

    order = await router.submit(_req(OrderSide.BUY, "10"))

    assert order.status == OrderStatus.SUBMITTED
    adapter.submit_order.assert_called_once()

    async with seeded() as s:
        assert list((await s.execute(select(LedgerRow))).scalars().all()) == []


@pytest.mark.usefixtures("_market_open")
async def test_the_order_row_and_the_ledger_row_agree(seeded):
    """The durable lifecycle must actually join up: signal → proposal → RISK DECISION → order.
    A ledger the orders table cannot be reconciled against is decoration."""
    adapter = _broker()
    router = _router(seeded, adapter)

    order = await router.submit(_req(OrderSide.SELL, "100"))

    async with seeded() as s:
        row = (await s.execute(select(LedgerRow))).scalars().first()
        persisted = await s.get(Order, order.id)

    assert row.symbol == "AAPL"
    assert row.qty == persisted.qty
    assert str(row.side).lower().endswith("sell")
    assert row.account_id == persisted.account_id
    assert row.before_state_hash and row.risk_policy_version and row.correlation_id


# ================================================ THE 2026-07-27 REGRESSION (accounts 1 & 5)


@pytest.mark.usefixtures("_market_open")
async def test_a_settled_account_can_still_exit_through_the_router(seeded):
    """THE regression for 2026-07-27. A loss-locked account holding positions with NOTHING
    in flight — the normal state when you begin de-risking — must still be able to exit.

    Before #529 this was impossible for any account whose Alpaca id sorted before an ISO
    timestamp: ``fetch_snapshot`` substituted the account UUID for the missing broker cursor,
    the settled account compared as permanently behind itself, and every risk-reducing sell
    returned FAIL_CLOSED/["SNAPSHOT_STALE"]. Account 1 had four full-position sells refused
    that way and was ultimately exited broker-direct, outside the governed path. Account 5
    (sector-rotation, live) was still in that state when this test was written.

    Asserts on ``submit_order`` — the reduction must REACH THE BROKER, not merely evaluate.
    """
    adapter = _broker()
    adapter.list_orders.side_effect = None
    adapter.list_orders.return_value = []       # settled: broker has nothing open
    # an account id that sorts BEFORE every "2026-…" stamp, i.e. accounts 1 and 5
    adapter.get_account.return_value = {
        "cash": "1000", "equity": "93209", "id": "152d5cd1-cfe4-443e-ae06-b7f1b0704fcf",
    }
    router = _router(seeded, adapter)

    order = await router.submit(_req(OrderSide.SELL, "100"))

    assert order.status == OrderStatus.SUBMITTED
    adapter.submit_order.assert_called_once()

    async with seeded() as s:
        row = (await s.execute(select(LedgerRow))).scalars().first()
    assert row.decision == "ALLOW"
    assert row.risk_effect == "RISK_REDUCING"
    assert "SNAPSHOT_STALE" not in (row.reason_codes or "")


# Each case needs its OWN database: a submitted order leaves a non-terminal row behind, and
# under #529 that row is itself an input to the next causality check. Looping inside one test
# would measure that carry-over instead of the account id.
@pytest.mark.parametrize(
    "acct_id",
    [
        "152d5cd1-cfe4-443e-ae06-b7f1b0704fcf",  # account 5 — sorts BEFORE "2026-…"
        "14365a33-b654-4ebc-a20a-e2f46b58aea0",  # account 1 — sorts BEFORE
        "acct",                                  # the old stub — sorts AFTER
        "ffffffff-ffff-ffff-ffff-ffffffffffff",  # sorts AFTER
    ],
)
@pytest.mark.usefixtures("_market_open")
async def test_the_account_id_is_never_what_makes_the_exit_work(seeded, acct_id):
    """The pre-#529 stub passed only because its fake account id ``"acct"`` sorted after every
    ISO stamp, and four production accounts passed for the same reason while accounts 1 and 5
    were permanently stale. The outcome must not depend on that at all: a settled, loss-locked
    account exits regardless of how its id happens to sort."""
    adapter = _broker()
    adapter.list_orders.side_effect = None
    adapter.list_orders.return_value = []       # settled: broker has nothing open
    adapter.get_account.return_value = {"cash": "1000", "equity": "93209", "id": acct_id}
    router = _router(seeded, adapter)

    order = await router.submit(_req(OrderSide.SELL, "10"))

    assert order.status == OrderStatus.SUBMITTED
    adapter.submit_order.assert_called_once()


@pytest.fixture
async def _msft_too(seeded):
    """Second symbol + position, so cross-symbol scoping can be exercised end to end."""
    async with seeded() as s:
        s.add(Symbol(id=2, ticker="MSFT", exchange="NASDAQ", asset_class="us_equity",
                     name="Microsoft", active=True))
        s.add(Position(user_id=1, account_id=1, symbol_id=2, qty=D("300"),
                       avg_entry_price=D("100"), side="long", updated_at=_now()))
        await s.commit()
    return seeded


def _stuck_local_order(session_factory, symbol_id: int):
    """A local order row left non-terminal that the broker does NOT report — the documented
    'trade-updates stream flap leaves an order stuck SUBMITTED' mode."""
    async def _add():
        async with session_factory() as s:
            s.add(Order(
                user_id=1, account_id=1, symbol_id=symbol_id, side=OrderSide.SELL,
                qty=D("10"), type=OrderType.MARKET, tif=TimeInForce.DAY,
                status=OrderStatus.SUBMITTED, source_type=OrderSourceType.MANUAL,
                broker_order_id="stuck-1", created_at=_now(), updated_at=_now(),
            ))
            await s.commit()
    return _add()


def _settled_broker():
    """Broker holding both positions and reporting NOTHING open — the settled state."""
    adapter = _broker(positions=[
        {"symbol": "AAPL", "qty": "500", "side": "long", "current_price": "100"},
        {"symbol": "MSFT", "qty": "300", "side": "long", "current_price": "100"},
    ])
    adapter.list_orders.side_effect = None
    adapter.list_orders.return_value = []
    return adapter


@pytest.mark.usefixtures("_market_open")
async def test_a_stuck_local_order_does_not_block_a_reduction_in_ANOTHER_symbol(_msft_too):
    """Cross-symbol: AAPL's stuck row must not block the MSFT exit.

    Account-wide in-flight scoping made one unresolved row freeze de-risking across the whole
    account, indefinitely — a permanent trap of the same shape as the account-id cursor bug.
    Account 1's real exit spanned four symbols.
    """
    await _stuck_local_order(_msft_too, symbol_id=1)          # stuck in AAPL
    adapter = _settled_broker()
    router = _router(_msft_too, adapter)

    order = await router.submit(OrderRequest(
        user_id=1, account_id=1, symbol_ticker="MSFT", side=OrderSide.SELL, qty=D("100"),
        type=OrderType.MARKET, tif=TimeInForce.DAY, source_type=OrderSourceType.MANUAL,
    ))

    assert order.status == OrderStatus.SUBMITTED
    adapter.submit_order.assert_called_once()
    assert adapter.submit_order.call_args.kwargs["symbol"] == "MSFT"


@pytest.mark.usefixtures("_market_open")
async def test_a_stuck_local_order_STILL_blocks_a_reduction_in_the_SAME_symbol(_msft_too):
    """Same-symbol: fail-closed is preserved. AAPL's true position is genuinely ambiguous
    while we hold an unresolved AAPL order the broker does not report, so an AAPL reduction
    must not be sized against it."""
    await _stuck_local_order(_msft_too, symbol_id=1)          # stuck in AAPL
    adapter = _settled_broker()
    router = _router(_msft_too, adapter)

    order = await router.submit(_req(OrderSide.SELL, "100"))  # AAPL

    assert order.status == OrderStatus.REJECTED
    adapter.submit_order.assert_not_called()

    async with _msft_too() as s:
        row = (await s.execute(select(LedgerRow))).scalars().first()
    assert row.decision == "FAIL_CLOSED"
    assert "SNAPSHOT_STALE" in (row.reason_codes or "")


@pytest.mark.usefixtures("_market_open")
async def test_a_stuck_local_order_still_blocks_a_BUY_in_another_symbol(_msft_too):
    """The narrowing is scoped to risk-REDUCING eligibility, not to general authorization.
    An unknown in-flight order elsewhere can still move buying power, gross exposure and
    account-level loss state, so anything that could increase exposure keeps the account-wide
    test."""
    await _stuck_local_order(_msft_too, symbol_id=1)          # stuck in AAPL
    adapter = _settled_broker()
    router = _router(_msft_too, adapter)

    order = await router.submit(OrderRequest(
        user_id=1, account_id=1, symbol_ticker="MSFT", side=OrderSide.BUY, qty=D("10"),
        type=OrderType.MARKET, tif=TimeInForce.DAY, source_type=OrderSourceType.MANUAL,
    ))

    assert order.status == OrderStatus.REJECTED
    adapter.submit_order.assert_not_called()


@pytest.mark.usefixtures("_market_open")
async def test_an_oversized_sell_does_not_earn_the_symbol_scoped_exception(_msft_too):
    """The pre-test admits only a reduction that CANNOT cross zero. A sell larger than the
    position could reverse into a short, so it keeps the account-wide test."""
    await _stuck_local_order(_msft_too, symbol_id=1)          # stuck in AAPL
    adapter = _settled_broker()
    router = _router(_msft_too, adapter)

    order = await router.submit(OrderRequest(
        user_id=1, account_id=1, symbol_ticker="MSFT", side=OrderSide.SELL, qty=D("400"),
        type=OrderType.MARKET, tif=TimeInForce.DAY, source_type=OrderSourceType.MANUAL,
    ))

    assert order.status == OrderStatus.REJECTED
    adapter.submit_order.assert_not_called()
