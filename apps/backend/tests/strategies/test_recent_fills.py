"""P7 §7-A.1b — DB-backed authorization + cursor tests for ctx.recent_fills().

Proves the query boundary: strategy+account scope (NOT client_order_id) is the
authorization, the two-part cursor neither skips nor duplicates, and the optional
prefix filter is layered on top without ever cross-attributing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from app.db.enums import OrderSide, OrderSourceType, OrderStatus, OrderType, TimeInForce
from app.db.models.account import Account, AccountMode
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.strategies.context import StrategyContext

PREFIX = "seed:99:att-1:"
T1 = datetime(2026, 8, 3, 19, 50, tzinfo=UTC)
T2 = datetime(2026, 8, 3, 19, 51, tzinfo=UTC)
T3 = datetime(2026, 8, 3, 19, 52, tzinfo=UTC)


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(User(id=2, email="two@test", display_name="Two"))
        session.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="A1"))
        session.add(Account(id=2, user_id=2, broker="alpaca", mode=AccountMode.paper, label="A2"))
        session.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ",
                           asset_class="us_equity", name="Apple", active=True))
        await session.commit()


def _ctx(session_factory, *, strategy_id=99, account_id=1) -> StrategyContext:
    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=pd.DataFrame())
    return StrategyContext(
        strategy_id=strategy_id, user_id=1, account_id=account_id, symbols=["AAPL"],
        session_factory=session_factory, bar_cache=bar_cache,
        indicator_computer=MagicMock(), submit_order_fn=AsyncMock(),
    )


async def _add_fill(
    session_factory, *, source_id="99", account_id=1, user_id=1,
    source_type=OrderSourceType.STRATEGY, status=OrderStatus.FILLED,
    client_order_id=f"{PREFIX}AAPL", qty="5", price="100", filled_at=None,
) -> tuple[int, int]:
    filled_at = filled_at or _now()
    async with session_factory() as session:
        o = Order(
            user_id=user_id, account_id=account_id, symbol_id=1,
            client_order_id=client_order_id, side=OrderSide.BUY, qty=Decimal(qty),
            type=OrderType.MARKET, tif=TimeInForce.DAY, status=status,
            source_type=source_type, source_id=source_id,
            created_at=_now(), updated_at=_now(),
        )
        session.add(o)
        await session.flush()
        f = Fill(order_id=o.id, qty=Decimal(qty), price=Decimal(price), filled_at=filled_at)
        session.add(f)
        await session.flush()
        ids = (o.id, f.id)
        await session.commit()
    return ids


async def test_own_strategy_account_matching_prefix_is_returned(session_factory, seeded):
    await _add_fill(session_factory)
    got = await _ctx(session_factory).recent_fills(client_order_id_prefix=PREFIX)
    assert len(got) == 1
    fe = got[0]
    assert fe.account_id == 1 and fe.source_id == "99"
    assert fe.client_order_id == f"{PREFIX}AAPL" and fe.order_status == "filled"
    assert fe.symbol == "AAPL" and fe.qty == Decimal(5)


async def test_another_strategy_is_excluded(session_factory, seeded):
    await _add_fill(session_factory, source_id="42")  # different strategy, same account
    assert await _ctx(session_factory).recent_fills() == []


async def test_another_account_is_excluded(session_factory, seeded):
    await _add_fill(session_factory, account_id=2, user_id=2)
    assert await _ctx(session_factory).recent_fills() == []


async def test_manual_non_strategy_source_is_excluded(session_factory, seeded):
    await _add_fill(session_factory, source_type=OrderSourceType.MANUAL)
    assert await _ctx(session_factory).recent_fills() == []


async def test_malicious_client_order_id_cannot_cross_attribute(session_factory, seeded):
    # Another strategy's fill wearing OUR prefix must NOT be attributed to us:
    # authorization is source_id/account, not the client_order_id.
    await _add_fill(session_factory, source_id="42", client_order_id=f"{PREFIX}AAPL")
    got = await _ctx(session_factory).recent_fills(client_order_id_prefix=PREFIX)
    assert got == []


async def test_partial_fill_then_canceled_is_still_returned(session_factory, seeded):
    await _add_fill(session_factory, status=OrderStatus.CANCELED)
    got = await _ctx(session_factory).recent_fills()
    assert len(got) == 1 and got[0].order_status == "canceled" and got[0].qty == Decimal(5)


async def test_same_timestamp_fills_order_by_fill_id(session_factory, seeded):
    _, a = await _add_fill(session_factory, filled_at=T2)
    _, b = await _add_fill(session_factory, filled_at=T2)
    got = await _ctx(session_factory).recent_fills()
    assert [f.fill_id for f in got] == sorted([a, b])


async def test_two_part_cursor_neither_skips_nor_duplicates(session_factory, seeded):
    _, fa = await _add_fill(session_factory, filled_at=T1)
    _, fb = await _add_fill(session_factory, filled_at=T2)  # tie 1
    _, fc = await _add_fill(session_factory, filled_at=T2)  # tie 2 (fc > fb)
    _, fd = await _add_fill(session_factory, filled_at=T3)
    # cursor at (T2, fb): must return fc (same ts, higher id) and fd, but NOT fb/fa.
    got = await _ctx(session_factory).recent_fills(since=T2, after_fill_id=fb)
    assert [f.fill_id for f in got] == [fc, fd]


async def test_since_alone_is_inclusive_first_poll(session_factory, seeded):
    _, fa = await _add_fill(session_factory, filled_at=T1)
    _, fb = await _add_fill(session_factory, filled_at=T2)
    got = await _ctx(session_factory).recent_fills(since=T1)
    assert [f.fill_id for f in got] == sorted([fa, fb])  # T1 included (>=)


async def test_repeated_reads_are_deterministic(session_factory, seeded):
    await _add_fill(session_factory, filled_at=T1)
    await _add_fill(session_factory, filled_at=T2)
    ctx = _ctx(session_factory)
    r1 = await ctx.recent_fills()
    r2 = await ctx.recent_fills()
    assert [f.fill_id for f in r1] == [f.fill_id for f in r2]


async def test_null_client_order_id_respects_auth_and_fails_prefix_without_error(
    session_factory, seeded
):
    # A fill whose order has a NULL client_order_id: still strategy/account-scoped,
    # returned with no prefix; simply excluded (no exception) when a prefix is set.
    await _add_fill(session_factory, client_order_id=None)
    ctx = _ctx(session_factory)
    assert len(await ctx.recent_fills()) == 1
    assert await ctx.recent_fills(client_order_id_prefix=PREFIX) == []


# ---- open_orders (attempt-level order observations) ----

async def _add_order(
    session_factory, *, status=OrderStatus.SUBMITTED, source_id="99", account_id=1,
    user_id=1, source_type=OrderSourceType.STRATEGY, client_order_id=f"{PREFIX}AAPL",
) -> int:
    async with session_factory() as session:
        o = Order(
            user_id=user_id, account_id=account_id, symbol_id=1,
            client_order_id=client_order_id, side=OrderSide.BUY, qty=Decimal("5"),
            type=OrderType.MARKET, tif=TimeInForce.DAY, status=status,
            source_type=source_type, source_id=source_id,
            created_at=_now(), updated_at=_now(),
        )
        session.add(o)
        await session.flush()
        oid = o.id
        await session.commit()
    return oid


async def test_open_orders_returns_nonterminal_and_excludes_terminal(session_factory, seeded):
    await _add_order(session_factory, status=OrderStatus.SUBMITTED)
    await _add_order(session_factory, status=OrderStatus.FILLED)  # terminal → excluded
    got = await _ctx(session_factory).open_orders()
    assert [o.status for o in got] == ["submitted"]


async def test_open_orders_excludes_other_strategy_and_account(session_factory, seeded):
    await _add_order(session_factory, source_id="42")               # other strategy
    await _add_order(session_factory, account_id=2, user_id=2)      # other account
    assert await _ctx(session_factory).open_orders() == []


async def test_open_orders_prefix_filters_to_this_attempt_only(session_factory, seeded):
    await _add_order(session_factory, client_order_id="seed:99:att-1:AAPL")
    await _add_order(session_factory, client_order_id="seed:99:att-2:AAPL")  # another attempt
    got = await _ctx(session_factory).open_orders(client_order_id_prefix="seed:99:att-1:")
    assert [o.client_order_id for o in got] == ["seed:99:att-1:AAPL"]


# ---- compare_and_set_state (real optimistic CAS) ----

async def test_cas_insert_if_absent_then_second_insert_fails(session_factory, seeded):
    ctx = _ctx(session_factory)
    ok1 = await ctx.compare_and_set_state("deployment", expected_rev=None,
                                          new_value={"_rev": 0, "state": "NEVER_DEPLOYED"})
    ok2 = await ctx.compare_and_set_state("deployment", expected_rev=None,
                                          new_value={"_rev": 0, "state": "CLOBBER"})
    assert (ok1, ok2) == (True, False)
    assert (await ctx.get_state("deployment"))["state"] == "NEVER_DEPLOYED"


async def test_cas_update_succeeds_on_matching_rev(session_factory, seeded):
    ctx = _ctx(session_factory)
    await ctx.compare_and_set_state("deployment", expected_rev=None,
                                    new_value={"_rev": 0, "state": "NEVER_DEPLOYED"})
    ok = await ctx.compare_and_set_state("deployment", expected_rev=0,
                                         new_value={"_rev": 1, "state": "DEPLOYMENT_PENDING"})
    blob = await ctx.get_state("deployment")
    assert ok is True and blob["_rev"] == 1 and blob["state"] == "DEPLOYMENT_PENDING"


async def test_cas_update_fails_on_stale_rev_leaving_row_unchanged(session_factory, seeded):
    ctx = _ctx(session_factory)
    await ctx.compare_and_set_state("deployment", expected_rev=None,
                                    new_value={"_rev": 0, "state": "A"})
    await ctx.compare_and_set_state("deployment", expected_rev=0,
                                    new_value={"_rev": 1, "state": "B"})
    stale = await ctx.compare_and_set_state("deployment", expected_rev=0,
                                            new_value={"_rev": 1, "state": "C"})
    assert stale is False
    assert (await ctx.get_state("deployment"))["state"] == "B"


async def test_cas_two_callers_same_rev_only_one_succeeds(session_factory, seeded):
    # Both read _rev=0; the first CAS bumps to 1, the second (still expecting 0) fails.
    ctx = _ctx(session_factory)
    await ctx.compare_and_set_state("deployment", expected_rev=None,
                                    new_value={"_rev": 0, "state": "NEVER_DEPLOYED"})
    a = await ctx.compare_and_set_state("deployment", expected_rev=0,
                                        new_value={"_rev": 1, "state": "ATTEMPT_A"})
    b = await ctx.compare_and_set_state("deployment", expected_rev=0,
                                        new_value={"_rev": 1, "state": "ATTEMPT_B"})
    assert [a, b] == [True, False]
    assert (await ctx.get_state("deployment"))["state"] == "ATTEMPT_A"
