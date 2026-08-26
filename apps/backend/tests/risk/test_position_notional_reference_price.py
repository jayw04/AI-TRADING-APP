"""B3a — the reference price the ``max_position_notional`` gate sizes against.

The gate is a **pre-trade deny control**. Before this repair it resolved its
reference price as::

    ref_price = req.limit_price or (pos.avg_entry_price if pos else Decimal(0))

which fails open twice, and the second one is not an accident:

1. **Corrupted existing position** — ``avg_entry_price`` is historical cost, and
   a wrong stored value understates the projected notional silently.
2. **New position, by design** — when ``pos`` is ``None`` (every market-order BUY
   *opening* a name) ``ref_price`` is ``0``, the projected notional is ``0``, and
   the check passes trivially **always**.

Mode 2 is the load-bearing one: measured 2026-08-25, five strategy templates
submit ``OrderType.MARKET`` and **no template passes a limit price at all**, so
the fallback is the normal path for every strategy-originated order rather than
an edge case. A deny control that a whole class of orders passes unconditionally
is not a control, which is why the owner ruled REPAIR (v0.5 §4.2) rather than
accept-with-reason.

The repair reuses the price source the engine already trusts elsewhere.
``_estimate_notional`` — computed a few lines earlier in the same call, and used
by the gross-exposure gate — resolves limit price, then the caller-supplied
reference price, then the latest cached close. ADR 0040 established that
mechanism precisely because market orders pricing to zero let a burst of baskets
each pass against the same settled snapshot. The position-notional gate was
simply never moved onto it.

**Fail-closed scope.** When no trusted price resolves, an *exposure-increasing*
order is refused (``POSITION_CAP_UNPRICED``). A *risk-reducing* order is never
refused for want of a price: ADR 0038 and ADR 0042 both exist because a gate that
traps an exit converts a risk control into a risk. A reduction cannot newly
breach a position cap it is moving away from.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderType,
    RiskScopeType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.position import Position
from app.db.models.risk_limits import RiskLimits
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.risk.engine import RiskEngine
from app.risk.reason_codes import ReasonCode
from app.risk.types import OrderRequest

CAP = Decimal("25000")


def _now() -> datetime:
    return datetime.now(UTC)


class _StubBarCache:
    """Minimal bar cache. ``price=None`` models a cold symbol (no bar)."""

    def __init__(self, price: Decimal | None) -> None:
        self._price = price
        self.calls: list[str] = []

    async def get_latest_bar(self, symbol: str):
        self.calls.append(symbol)
        if self._price is None:
            return None
        return {"c": str(self._price)}


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(
            Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Paper")
        )
        session.add(
            Symbol(
                id=1,
                ticker="AAPL",
                exchange="NASDAQ",
                asset_class="us_equity",
                name="Apple",
                active=True,
            )
        )
        session.add(
            RiskLimits(
                user_id=1,
                scope_type=RiskScopeType.GLOBAL,
                scope_id=None,
                # qty cap deliberately high so the NOTIONAL gate is what binds.
                max_position_qty=Decimal("100000"),
                max_position_notional=CAP,
                max_gross_exposure=Decimal("100000000"),
                max_daily_loss=Decimal("2000"),
                max_orders_per_minute=1000,
                allow_short=False,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        session.add(
            AccountState(
                account_id=1,
                cash=Decimal("100000000"),
                equity=Decimal("100000000"),
                last_equity=Decimal("100000000"),
                buying_power=Decimal("200000000"),
                portfolio_value=Decimal("100000000"),
                daytrade_count=0,
                day_change=Decimal(0),
                day_change_pct=Decimal(0),
                status="ACTIVE",
                pattern_day_trader=False,
                trading_blocked=False,
                account_blocked=False,
                raw_payload={},
                updated_at=_now(),
            )
        )
        await session.commit()
    yield


async def _add_position(session_factory, qty: Decimal, avg_entry_price: Decimal) -> None:
    async with session_factory() as session:
        session.add(
            Position(
                user_id=1,
                account_id=1,
                symbol_id=1,
                qty=qty,
                avg_entry_price=avg_entry_price,
                side="long",
                market_value=qty * avg_entry_price,
                cost_basis=qty * avg_entry_price,
                unrealized_pl=Decimal(0),
                unrealized_plpc=Decimal(0),
                updated_at=_now(),
            )
        )
        await session.commit()


def _req(**overrides) -> OrderRequest:
    base = dict(
        user_id=1,
        account_id=1,
        symbol_ticker="AAPL",
        side=OrderSide.BUY,
        qty=Decimal("10"),
        type=OrderType.MARKET,
        tif=TimeInForce.DAY,
        source_type=OrderSourceType.MANUAL,
    )
    base.update(overrides)
    return OrderRequest(**base)


# ── Mode 2: the new-position zero-reference bypass ────────────────────────────


async def test_new_position_market_buy_is_capped_on_current_price(session_factory, seeded) -> None:
    """The headline repair.

    No position exists, so the old path set ``ref_price = 0`` and passed. With a
    trusted current price the order is valued at 100 x 600 = 60,000 against a
    25,000 cap and must be refused.
    """
    eng = RiskEngine(session_factory, bar_cache=_StubBarCache(Decimal("600")))
    out = await eng.evaluate(_req(qty=Decimal("100")), trading_mode="paper")
    assert ReasonCode.POSITION_CAP_NOTIONAL in out.reason_codes


async def test_new_position_market_buy_under_cap_still_passes(session_factory, seeded) -> None:
    """The repair must not reject everything: 10 x 600 = 6,000 is under the cap."""
    eng = RiskEngine(session_factory, bar_cache=_StubBarCache(Decimal("600")))
    out = await eng.evaluate(_req(qty=Decimal("10")), trading_mode="paper")
    assert ReasonCode.POSITION_CAP_NOTIONAL not in out.reason_codes
    assert ReasonCode.POSITION_CAP_UNPRICED not in out.reason_codes


async def test_caller_supplied_reference_price_is_preferred(session_factory, seeded) -> None:
    """A strategy passes the price it sized against; it outranks the cache."""
    eng = RiskEngine(session_factory, bar_cache=_StubBarCache(Decimal("1")))
    out = await eng.evaluate(
        _req(qty=Decimal("100"), reference_price=Decimal("600")),
        trading_mode="paper",
    )
    assert ReasonCode.POSITION_CAP_NOTIONAL in out.reason_codes


# ── Mode 1: the corrupted existing position ───────────────────────────────────


async def test_corrupted_avg_entry_price_no_longer_understates_the_cap(
    session_factory, seeded
) -> None:
    """HON-shaped row: qty 11 held, stored ``avg_entry_price`` 21.05 against a
    true price near 224 (the recomputer's own output for the full fill history
    is 224.39; the stored row read 21.05).

    Old path: 111 x 21.05 = 2,337 -> passes a 25,000 cap.
    Repaired: 111 x 224.00 = 24,864 ... still under. Use a size that makes the
    divergence decisive rather than marginal: 200 more shares.
        old      211 x 21.05  =  4,441  -> passes
        repaired 211 x 224.00 = 47,264  -> refused
    """
    await _add_position(session_factory, Decimal("11"), Decimal("21.053636"))
    eng = RiskEngine(session_factory, bar_cache=_StubBarCache(Decimal("224")))
    out = await eng.evaluate(_req(qty=Decimal("200")), trading_mode="paper")
    assert ReasonCode.POSITION_CAP_NOTIONAL in out.reason_codes


async def test_stale_avg_entry_price_is_not_consulted_at_all(session_factory, seeded) -> None:
    """Symmetry check: a *high* stale cost basis must not reject an order the
    current price says is fine. The old path multiplied by 5,000 and refused;
    the repaired gate values 10 more shares at 50 and passes."""
    await _add_position(session_factory, Decimal("1"), Decimal("5000"))
    eng = RiskEngine(session_factory, bar_cache=_StubBarCache(Decimal("50")))
    out = await eng.evaluate(_req(qty=Decimal("10")), trading_mode="paper")
    assert ReasonCode.POSITION_CAP_NOTIONAL not in out.reason_codes


# ── Fail-closed, and its deliberate limit ─────────────────────────────────────


async def test_unpriceable_increasing_order_fails_closed(session_factory, seeded) -> None:
    """No limit price, no reference price, cold cache -> no trusted reference.

    The owner ruling is explicit: use a trusted bounded estimate **or fail
    closed**. Passing an unpriced increasing order is the bypass itself.
    """
    eng = RiskEngine(session_factory, bar_cache=_StubBarCache(None))
    out = await eng.evaluate(_req(qty=Decimal("100")), trading_mode="paper")
    assert ReasonCode.POSITION_CAP_UNPRICED in out.reason_codes


async def test_unpriceable_with_no_bar_cache_at_all_fails_closed(session_factory, seeded) -> None:
    """``bar_cache=None`` (unwired) must not be a silent bypass either."""
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(qty=Decimal("100")), trading_mode="paper")
    assert ReasonCode.POSITION_CAP_UNPRICED in out.reason_codes


async def test_unpriceable_reducing_sell_is_never_trapped(session_factory, seeded) -> None:
    """⛔ The limit on fail-closed, and it is not negotiable.

    ADR 0038 and ADR 0042 both exist because a gate that refuses an exit turns a
    risk control into a risk. A SELL that reduces a long position cannot newly
    breach a position cap, so an unresolvable price must never refuse it.
    """
    await _add_position(session_factory, Decimal("500"), Decimal("100"))
    eng = RiskEngine(session_factory, bar_cache=_StubBarCache(None))
    out = await eng.evaluate(_req(side=OrderSide.SELL, qty=Decimal("100")), trading_mode="paper")
    assert ReasonCode.POSITION_CAP_UNPRICED not in out.reason_codes
    assert ReasonCode.POSITION_CAP_NOTIONAL not in out.reason_codes


async def test_priced_reducing_sell_is_not_capped_either(session_factory, seeded) -> None:
    """Even priced, a reduction below the current size must not be refused by the
    position cap — the resulting position is smaller than the one already held."""
    await _add_position(session_factory, Decimal("500"), Decimal("100"))
    eng = RiskEngine(session_factory, bar_cache=_StubBarCache(Decimal("600")))
    out = await eng.evaluate(_req(side=OrderSide.SELL, qty=Decimal("100")), trading_mode="paper")
    assert ReasonCode.POSITION_CAP_NOTIONAL not in out.reason_codes


# ── The anti-stranding safety invariant (ADR 0055 §4) ─────────────────────────
#
# `increases_position` is a SAFETY INVARIANT, not an optimisation. The pair below
# is deliberately matched — the SAME oversized position, one order each way — so
# that a future refactor cannot "simplify" the guard away without turning one of
# these red. Deleting the guard makes the first test fail: the position becomes
# unreducible while it is over the cap, which is the 2026-07-13 exit-stranding
# class (ADR 0042) reintroduced by a risk repair.


async def _seed_oversized_position(session_factory) -> None:
    """500 shares that price to 300,000 against a 25,000 cap — far over."""
    await _add_position(session_factory, Decimal("500"), Decimal("100"))


async def test_oversized_position_reducing_sell_is_allowed_through_this_gate(
    session_factory, seeded
) -> None:
    """Half 1 of the pair: an over-cap holding MUST remain reducible.

    500 held, priced at 600 -> the position is 300,000 against a 25,000 cap. A
    SELL of 100 leaves 400 (240,000), still over the cap, so a naive
    resulting-position check would refuse it and strand the position ABOVE the
    limit. The gate must let the reduction through.
    """
    await _seed_oversized_position(session_factory)
    eng = RiskEngine(session_factory, bar_cache=_StubBarCache(Decimal("600")))
    out = await eng.evaluate(_req(side=OrderSide.SELL, qty=Decimal("100")), trading_mode="paper")
    assert ReasonCode.POSITION_CAP_NOTIONAL not in out.reason_codes
    assert ReasonCode.POSITION_CAP_UNPRICED not in out.reason_codes


async def test_oversized_position_increasing_buy_is_still_rejected(
    session_factory, seeded
) -> None:
    """Half 2 of the pair: the exemption must not become a hole.

    Same oversized 500-share holding, same price. A BUY increases the position,
    so the cap is evaluated normally and refuses it. If this test ever passes an
    increasing order, the exemption has been widened past reductions.
    """
    await _seed_oversized_position(session_factory)
    eng = RiskEngine(session_factory, bar_cache=_StubBarCache(Decimal("600")))
    out = await eng.evaluate(_req(side=OrderSide.BUY, qty=Decimal("10")), trading_mode="paper")
    assert ReasonCode.POSITION_CAP_NOTIONAL in out.reason_codes


async def test_sell_that_flips_into_a_larger_short_counts_as_increasing(
    session_factory, seeded
) -> None:
    """The exemption keys on exposure, not on order side.

    Holding 100 long, a SELL of 600 leaves a 500-share SHORT — larger than what
    was held, so it INCREASES exposure and must be evaluated, not exempted.
    (`allow_short` is False in this fixture, so the short gate refuses it first;
    what matters is that it is refused rather than waved through as a "sell".)
    """
    await _add_position(session_factory, Decimal("100"), Decimal("100"))
    eng = RiskEngine(session_factory, bar_cache=_StubBarCache(Decimal("600")))
    out = await eng.evaluate(_req(side=OrderSide.SELL, qty=Decimal("600")), trading_mode="paper")
    assert not out.passed


# ── Behaviour that must NOT change ────────────────────────────────────────────


async def test_limit_price_remains_authoritative(session_factory, seeded) -> None:
    """The pre-existing limit-order path is untouched: an explicit limit price
    still wins over both the cache and any stored cost basis."""
    eng = RiskEngine(session_factory, bar_cache=_StubBarCache(Decimal("1")))
    out = await eng.evaluate(
        _req(qty=Decimal("50"), type=OrderType.LIMIT, limit_price=Decimal("600")),
        trading_mode="paper",
    )
    assert ReasonCode.POSITION_CAP_NOTIONAL in out.reason_codes


async def test_limit_order_under_cap_passes(session_factory, seeded) -> None:
    eng = RiskEngine(session_factory, bar_cache=_StubBarCache(Decimal("9999")))
    out = await eng.evaluate(
        _req(qty=Decimal("10"), type=OrderType.LIMIT, limit_price=Decimal("100")),
        trading_mode="paper",
    )
    assert ReasonCode.POSITION_CAP_NOTIONAL not in out.reason_codes


async def test_qty_cap_still_evaluated_before_notional(session_factory, seeded) -> None:
    """The notional repair must not shadow the qty cap. With a qty cap of 5 and a
    priced order of 10 shares, POSITION_CAP_QTY is what fires."""
    async with session_factory() as session:
        limits = (
            (await session.execute(__import__("sqlalchemy").select(RiskLimits))).scalars().first()
        )
        limits.max_position_qty = Decimal("5")
        await session.commit()

    eng = RiskEngine(session_factory, bar_cache=_StubBarCache(Decimal("10")))
    out = await eng.evaluate(_req(qty=Decimal("10")), trading_mode="paper")
    assert ReasonCode.POSITION_CAP_QTY in out.reason_codes


# ── Numerical edges ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad_price", [Decimal("0"), Decimal("-1")])
async def test_non_positive_cached_price_is_not_trusted(session_factory, seeded, bad_price) -> None:
    """A zero or negative close is not a price. It must fail closed, not be used
    as a reference that silently passes everything."""
    eng = RiskEngine(session_factory, bar_cache=_StubBarCache(bad_price))
    out = await eng.evaluate(_req(qty=Decimal("100")), trading_mode="paper")
    assert ReasonCode.POSITION_CAP_UNPRICED in out.reason_codes


async def test_exactly_at_the_cap_is_allowed(session_factory, seeded) -> None:
    """Boundary: the gate refuses ``>`` the cap, not ``>=``. 250 x 100 = 25,000."""
    eng = RiskEngine(session_factory, bar_cache=_StubBarCache(Decimal("100")))
    out = await eng.evaluate(_req(qty=Decimal("250")), trading_mode="paper")
    assert ReasonCode.POSITION_CAP_NOTIONAL not in out.reason_codes


async def test_one_cent_over_the_cap_is_refused(session_factory, seeded) -> None:
    eng = RiskEngine(session_factory, bar_cache=_StubBarCache(Decimal("100.01")))
    out = await eng.evaluate(_req(qty=Decimal("250")), trading_mode="paper")
    assert ReasonCode.POSITION_CAP_NOTIONAL in out.reason_codes


async def test_bar_cache_exception_fails_closed_for_increasing_orders(
    session_factory, seeded
) -> None:
    """``_latest_close`` swallows exceptions and returns None. That must reach the
    fail-closed branch rather than the old zero-reference pass."""

    class _Exploding:
        async def get_latest_bar(self, symbol: str):
            raise RuntimeError("cache down")

    eng = RiskEngine(session_factory, bar_cache=_Exploding())
    out = await eng.evaluate(_req(qty=Decimal("100")), trading_mode="paper")
    assert ReasonCode.POSITION_CAP_UNPRICED in out.reason_codes
