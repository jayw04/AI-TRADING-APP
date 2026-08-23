"""StrategyOwnedSecurityResolver — acquisition provenance, identity-keyed, quantity-blind.

The resolver answers only "which permanent securities may strategy <id> claim as
historically acquired on account <id>". These tests pin that boundary from both sides:
the classification rules it must implement, and the questions it must refuse to answer.

Scenario coverage required by LOW-PIT v0.3 §5.4 / PR S S2:

    STRATEGY:8 BUY, position exists            -> OWNED
    STRATEGY:8 BUY, later MANUAL SELL          -> still OWNED (provenance survives disposal)
    STRATEGY:8 BUY + MANUAL BUY                -> AMBIGUOUS  (non_strategy_acquisition)
    STRATEGY:8 BUY + STRATEGY:9 BUY            -> AMBIGUOUS  (competing_strategy_acquisition)
    only MANUAL BUY                            -> UNCLAIMED
    only STRATEGY:8 SELL                       -> absent (not acquisition provenance)
    STRATEGY:8 BUY on a different account      -> absent on this account
    ticker change, same permaticker            -> ONE owned security, two tickers
    unresolved / gapped identity               -> AMBIGUOUS (identity_unresolved), fail closed
"""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.enums import OrderSide, OrderSourceType, OrderStatus, OrderType, TimeInForce
from app.db.models.account import Account, AccountMode
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.universe import strategy_ownership as mod
from app.universe.strategy_ownership import (
    SECURITY_IDENTITY_CONTRACT,
    AmbiguityReason,
    OwnershipStatus,
    StrategyOwnedSecurityResolver,
)

T0 = datetime(2026, 7, 7, 17, 31, tzinfo=UTC)

#: Ticker -> permanent identity. OLDTICK/NEWTICK are one lineage renamed; GAPPED is a
#: ticker the lineage rule refuses (reuse boundary / structural hole), i.e. resolve -> None.
_IDENTITY = {
    "AAA": "P-1001",
    "BBB": "P-1002",
    "CCC": "P-1003",
    "DDD": "P-1004",
    "EEE": "P-1005",
    "OLDTICK": "P-2001",
    "NEWTICK": "P-2001",
}


class _FakeIdentity:
    """Stand-in for the permaticker resolver the engine wires in (S3/S4)."""

    def resolve(self, ticker: str, as_of: date) -> str | None:
        # Date-insensitive stand-in: these suites exercise the classification rules, not
        # the effective-interval semantics. Dated resolution is proven end-to-end against
        # a real factor store in tests/universe/test_security_identity.py (S5.5).
        return _IDENTITY.get(ticker.upper())


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(User(id=2, email="two@test", display_name="Two"))
        session.add(Account(id=6, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Six"))
        # accounts is UNIQUE(user_id, broker, mode), so the second paper account needs
        # its own user. It exists only to prove ownership is account-scoped.
        session.add(
            Account(id=7, user_id=2, broker="alpaca", mode=AccountMode.paper, label="Seven")
        )
        for i, t in enumerate(
            ["AAA", "BBB", "CCC", "DDD", "EEE", "OLDTICK", "NEWTICK", "GAPPED"], start=1
        ):
            session.add(Symbol(id=i, ticker=t, asset_class="us_equity", name=t, active=True))
        await session.commit()


class _Ledger:
    """Minimal order/fill writer. Sequential ids keep assertions readable."""

    def __init__(self, session_factory):
        self._sf = session_factory
        self._oid = 0
        self._fid = 0

    async def order(
        self,
        ticker: str,
        side: OrderSide,
        *,
        source_type: OrderSourceType = OrderSourceType.STRATEGY,
        source_id: str | None = "8",
        account_id: int = 6,
        filled: bool = True,
        status: OrderStatus = OrderStatus.FILLED,
        minutes: int = 0,
    ) -> int:
        self._oid += 1
        oid = self._oid
        async with self._sf() as session:
            sym = (
                (await session.execute(select(Symbol).where(Symbol.ticker == ticker)))
                .scalars()
                .first()
            )
            assert sym is not None, ticker
            session.add(
                Order(
                    id=oid,
                    user_id=1,
                    account_id=account_id,
                    symbol_id=sym.id,
                    side=side,
                    qty=Decimal("10"),
                    type=OrderType.MARKET,
                    tif=TimeInForce.DAY,
                    status=status,
                    source_type=source_type,
                    source_id=source_id,
                    created_at=T0 + timedelta(minutes=minutes),
                    updated_at=T0 + timedelta(minutes=minutes),
                )
            )
            if filled:
                self._fid += 1
                session.add(
                    Fill(
                        id=self._fid,
                        order_id=oid,
                        qty=Decimal("10"),
                        price=Decimal("100"),
                        filled_at=T0 + timedelta(minutes=minutes),
                    )
                )
            await session.commit()
        return oid


def _resolver(session_factory) -> StrategyOwnedSecurityResolver:
    return StrategyOwnedSecurityResolver(session_factory, _FakeIdentity())


def _by_ticker(resolution, ticker: str):
    for s in resolution.securities:
        if ticker.upper() in s.tickers:
            return s
    return None


# ---- the classification table --------------------------------------------------


async def test_strategy_buy_is_owned(seeded, session_factory):
    """The base case: our filled BUY, nobody else's."""
    await _Ledger(session_factory).order("AAA", OrderSide.BUY)
    res = await _resolver(session_factory).resolve(account_id=6, strategy_id=8)

    aaa = _by_ticker(res, "AAA")
    assert aaa.status is OwnershipStatus.OWNED
    assert aaa.reason is None
    assert aaa.security_id == "P-1001"
    assert aaa.identity_contract == SECURITY_IDENTITY_CONTRACT
    assert aaa.is_claimable
    assert res.owned_tickers == frozenset({"AAA"})


async def test_manual_sell_does_not_erase_ownership(seeded, session_factory):
    """A MANUAL SELL disposes of shares; it does not create a competing claim.

    This is the 2026-07-07 Account-6 shape. It is exactly why quantity cannot be
    reconstructed from the strategy ledger — and exactly not a reason to disown the
    security (v0.3 §5.4.1).
    """
    led = _Ledger(session_factory)
    await led.order("AAA", OrderSide.BUY, minutes=0)
    await led.order(
        "AAA", OrderSide.SELL, source_type=OrderSourceType.MANUAL, source_id=None, minutes=12
    )
    res = await _resolver(session_factory).resolve(account_id=6, strategy_id=8)

    aaa = _by_ticker(res, "AAA")
    assert aaa.status is OwnershipStatus.OWNED
    assert aaa.reason is None
    # The manual SELL is not an acquisition, so it is not even in the source set.
    assert aaa.acquiring_sources == ("strategy:8",)


async def test_manual_buy_makes_it_ambiguous(seeded, session_factory):
    """A non-strategy BUY means the live quantity may contain shares we did not acquire."""
    led = _Ledger(session_factory)
    await led.order("BBB", OrderSide.BUY, minutes=0)
    await led.order(
        "BBB", OrderSide.BUY, source_type=OrderSourceType.MANUAL, source_id=None, minutes=5
    )
    res = await _resolver(session_factory).resolve(account_id=6, strategy_id=8)

    bbb = _by_ticker(res, "BBB")
    assert bbb.status is OwnershipStatus.AMBIGUOUS
    assert bbb.reason is AmbiguityReason.NON_STRATEGY_ACQUISITION
    assert not bbb.is_claimable
    assert "BBB" not in res.owned_tickers
    assert set(bbb.acquiring_sources) == {"strategy:8", "manual:"}


async def test_competing_strategy_makes_it_ambiguous(seeded, session_factory):
    """Two strategies acquired it. Do not choose one."""
    led = _Ledger(session_factory)
    await led.order("CCC", OrderSide.BUY, minutes=0)
    await led.order("CCC", OrderSide.BUY, source_id="9", minutes=5)
    res = await _resolver(session_factory).resolve(account_id=6, strategy_id=8)

    ccc = _by_ticker(res, "CCC")
    assert ccc.status is OwnershipStatus.AMBIGUOUS
    assert ccc.reason is AmbiguityReason.COMPETING_STRATEGY_ACQUISITION
    assert set(ccc.acquiring_sources) == {"strategy:8", "strategy:9"}


async def test_manual_buy_only_is_unclaimed_not_ambiguous(seeded, session_factory):
    """Not ours — a positive statement, not an absence, and not ambiguity.

    Ambiguity is reserved for a claim we actually hold; a security we never acquired is
    simply someone else's.
    """
    await _Ledger(session_factory).order(
        "DDD", OrderSide.BUY, source_type=OrderSourceType.MANUAL, source_id=None
    )
    res = await _resolver(session_factory).resolve(account_id=6, strategy_id=8)

    ddd = _by_ticker(res, "DDD")
    assert ddd.status is OwnershipStatus.UNCLAIMED
    assert ddd.reason is None
    assert ddd.acquisition_order_ids == ()
    assert "DDD" not in res.owned_tickers


async def test_sell_only_is_not_acquisition_provenance(seeded, session_factory):
    """Selling a security never establishes that we acquired it (cf. AXP, net -1)."""
    await _Ledger(session_factory).order("EEE", OrderSide.SELL)
    res = await _resolver(session_factory).resolve(account_id=6, strategy_id=8)

    assert _by_ticker(res, "EEE") is None
    assert res.securities == ()


async def test_unfilled_buy_is_not_acquisition_provenance(seeded, session_factory):
    """A REJECTED buy acquired nothing. Account 6 has exactly such a HON order.

    Under-claiming fails closed (UNCLAIMED / absent); over-claiming would silently
    attribute someone else's shares.
    """
    await _Ledger(session_factory).order(
        "AAA", OrderSide.BUY, filled=False, status=OrderStatus.REJECTED
    )
    res = await _resolver(session_factory).resolve(account_id=6, strategy_id=8)

    assert _by_ticker(res, "AAA") is None


async def test_ownership_is_scoped_to_the_account(seeded, session_factory):
    """Our BUY on account 7 confers nothing on account 6."""
    await _Ledger(session_factory).order("AAA", OrderSide.BUY, account_id=7)
    res6 = await _resolver(session_factory).resolve(account_id=6, strategy_id=8)
    res7 = await _resolver(session_factory).resolve(account_id=7, strategy_id=8)

    assert _by_ticker(res6, "AAA") is None
    assert _by_ticker(res7, "AAA").status is OwnershipStatus.OWNED


async def test_other_strategy_only_is_unclaimed_for_us(seeded, session_factory):
    await _Ledger(session_factory).order("AAA", OrderSide.BUY, source_id="9")
    res = await _resolver(session_factory).resolve(account_id=6, strategy_id=8)

    assert _by_ticker(res, "AAA").status is OwnershipStatus.UNCLAIMED


# ---- identity, not ticker ------------------------------------------------------


async def test_ticker_change_within_one_lineage_is_one_security(seeded, session_factory):
    """A rename inside a lineage must collapse to a single owned security.

    Keying on ticker would report two, and a caller reconciling against one broker
    position would then see a phantom extra holding.
    """
    led = _Ledger(session_factory)
    await led.order("OLDTICK", OrderSide.BUY, minutes=0)
    await led.order("NEWTICK", OrderSide.BUY, minutes=60)
    res = await _resolver(session_factory).resolve(account_id=6, strategy_id=8)

    assert len(res.securities) == 1
    sec = res.securities[0]
    assert sec.status is OwnershipStatus.OWNED
    assert sec.security_id == "P-2001"
    assert sec.tickers == ("NEWTICK", "OLDTICK")
    assert len(sec.acquisition_order_ids) == 2
    assert res.owned_tickers == frozenset({"OLDTICK", "NEWTICK"})


async def test_unresolved_identity_fails_closed(seeded, session_factory):
    """No permanent identity -> AMBIGUOUS, never a ticker-keyed guess.

    Ticker reuse across lineages is precisely what the identity contract prevents, so a
    fallback here would reintroduce the defect it exists to stop.
    """
    await _Ledger(session_factory).order("GAPPED", OrderSide.BUY)
    res = await _resolver(session_factory).resolve(account_id=6, strategy_id=8)

    g = _by_ticker(res, "GAPPED")
    assert g.status is OwnershipStatus.AMBIGUOUS
    assert g.reason is AmbiguityReason.IDENTITY_UNRESOLVED
    assert g.security_id is None
    assert not g.is_claimable
    assert res.owned_tickers == frozenset()


async def test_distinct_unresolved_tickers_do_not_merge(seeded, session_factory):
    """Two unresolvable names are two unknowns, not one."""
    led = _Ledger(session_factory)
    await led.order("GAPPED", OrderSide.BUY, minutes=0)
    # A second unresolvable ticker, registered but absent from the identity map.
    async with session_factory() as session:
        session.add(Symbol(id=99, ticker="GAPPED2", asset_class="us_equity", active=True))
        await session.commit()
    await led.order("GAPPED2", OrderSide.BUY, minutes=5)

    res = await _resolver(session_factory).resolve(account_id=6, strategy_id=8)
    assert len(res.ambiguous) == 2
    assert {t for s in res.ambiguous for t in s.tickers} == {"GAPPED", "GAPPED2"}


# ---- the questions this module must REFUSE to answer ---------------------------


async def test_resolver_reports_no_quantity_anywhere(seeded, session_factory):
    """§4.8 behaviourally: no returned object exposes a quantity.

    Two filled BUYs of 10 each; nothing in the result may say 10, 20, or anything else
    about size. The broker position is the only authority on how much exists.
    """
    led = _Ledger(session_factory)
    await led.order("AAA", OrderSide.BUY, minutes=0)
    await led.order("AAA", OrderSide.BUY, minutes=5)
    res = await _resolver(session_factory).resolve(account_id=6, strategy_id=8)

    sec = _by_ticker(res, "AAA")
    fields = set(vars(sec))
    assert not {f for f in fields if "qty" in f or "quantity" in f or "shares" in f}
    assert not any(isinstance(v, Decimal) for v in vars(sec).values())
    # Order ids are identity, not size: two acquisitions, no aggregation of them.
    assert len(sec.acquisition_order_ids) == 2


def test_module_never_sums_fills_or_order_quantities():
    """§4.8 structurally — the invariant enforced in code, not only in prose.

    A behavioural test proves the current return shape carries no quantity; this proves
    the module has no way to compute one. Documentation alone would let a future edit
    reintroduce netting and still pass every behavioural test that does not happen to
    look at the new field.
    """
    tree = ast.parse(inspect.getsource(mod))
    offenders: list[str] = []
    for node in ast.walk(tree):
        # Any attribute access naming a quantity: Order.qty, Fill.qty, row.qty, ...
        if isinstance(node, ast.Attribute) and node.attr in {"qty", "quantity", "shares"}:
            offenders.append(f"attribute .{node.attr} at line {node.lineno}")
        # Aggregation over anything: sum(...), func.sum(...), math.fsum(...)
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name in {"sum", "fsum"}:
                offenders.append(f"call {name}() at line {node.lineno}")
    assert not offenders, "quantity arithmetic reintroduced in strategy_ownership: " + "; ".join(
        offenders
    )


def test_resolver_exposes_no_holding_or_eligibility_api():
    """S2's boundary: provenance only.

    Current-holding status belongs to S3/S4 (owned ∩ broker positions) and buy
    eligibility to PR B. A method here answering either would let a caller skip the
    broker, which is how quantity authority gets quietly relocated.
    """
    public = {n for n in dir(StrategyOwnedSecurityResolver) if not n.startswith("_")}
    assert public == {"resolve"}
    banned = ("held", "holding", "position", "eligib", "buy", "quantity", "qty")
    assert not [n for n in public for b in banned if b in n.lower()]
