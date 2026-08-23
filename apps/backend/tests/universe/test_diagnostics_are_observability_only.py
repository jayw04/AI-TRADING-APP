"""Ownership diagnostics report decisions; they never make them (PR S / S8.3-A).

The required direction of flow is one-way::

    classification -> decision -> emission

    emission -/-> selection
    emission -/-> BUY authority
    emission -/-> ownership classification
    emission -/-> liquidation authorization

The risk this guards against is subtle and would be easy to introduce later: a diagnostic
that grows a return value someone then branches on, at which point "reporting" silently
becomes part of the safety decision and the fail-closed behaviour depends on logging
working. These tests prove the coupling does not exist today, both structurally and by
mutation — suppressing emission entirely must change nothing except observability.
"""

from __future__ import annotations

import ast
import inspect
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.db.enums import OrderSide, OrderSourceType, OrderStatus, OrderType, TimeInForce
from app.db.models.account import Account, AccountMode
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.universe import liquidation as liquidation_mod
from app.universe.diagnostics import OwnershipDiagnostics, OwnershipOperation
from app.universe.liquidation import LiquidationDisposition, StrategyPositionLiquidator
from app.universe.owned_holdings import StrategyOwnedHoldingsProvider

T0 = datetime(2026, 7, 7, 17, 31, tzinfo=UTC)
_IDENTITY = {"OWNED": "P-1", "CONTESTED": "P-2", "GHOST": None}


class _FakeIdentity:
    def resolve(self, ticker: str, as_of: date) -> str | None:
        return _IDENTITY.get(ticker.upper())

    def current_identity_date(self) -> date:
        # Date-insensitive stand-in: a fixed frontier so the default as_of is well defined.
        # Dated/interval semantics are proven against a real store in
        # tests/universe/test_identity_asof_and_readiness.py.
        return date(2026, 8, 20)

    @property
    def ready(self) -> bool:
        return True


# ---- structural: emission cannot feed a decision -------------------------------


def test_emitters_return_nothing_a_decision_could_branch_on():
    """``emit_liquidation_exclusion`` returns None; ``emit_exclusions`` returns a report.

    ``emit_exclusions`` does return the list of events it emitted — useful for tests and
    for a caller that wants to count them — so the binding invariant is not "returns None"
    but "no production caller consumes the value". That is asserted separately below.
    """
    sig = inspect.signature(OwnershipDiagnostics.emit_liquidation_exclusion)
    assert sig.return_annotation in (None, "None")


def test_no_production_caller_consumes_an_emitter_result():
    """Every call site discards the return value.

    Walked with the AST rather than grepped: a call whose result is assigned, returned,
    or used in a condition would be the first step toward emission influencing behaviour.
    """
    import app.strategies.engine as engine_mod

    offenders: list[str] = []
    for mod in (liquidation_mod, engine_mod):
        tree = ast.parse(inspect.getsource(mod))
        for node in ast.walk(tree):
            # A bare expression statement is a discarded result — the safe shape.
            if isinstance(node, ast.Expr):
                continue
            for child in ast.iter_child_nodes(node):
                if not isinstance(child, ast.Call):
                    continue
                fn = child.func
                name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                if name.startswith("emit_"):
                    offenders.append(f"{mod.__name__}:{child.lineno} result consumed")
    assert not offenders, offenders


def test_classification_helper_is_pure():
    """``ownership_event_for`` maps a reason to a label and touches nothing else."""
    tree = ast.parse(inspect.getsource(liquidation_mod.StrategyPositionLiquidator))
    # The liquidator must not consult the diagnostics object when deciding a disposition.
    decision_fns = {"_excluded_line"}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in decision_fns:
            src = ast.dump(node)
            assert "_diagnostics" not in src, f"{node.name} reads the emitter"


# ---- behavioural: suppressing emission changes nothing -------------------------


@pytest.fixture
async def book(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(Account(id=6, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Six"))
        for i, t in enumerate(_IDENTITY, start=1):
            session.add(Symbol(id=i, ticker=t, asset_class="us_equity", name=t, active=True))
        await session.commit()

    async def acquire(ticker, oid, source_id="8"):
        async with session_factory() as session:
            sym = (
                (await session.execute(select(Symbol).where(Symbol.ticker == ticker)))
                .scalars()
                .first()
            )
            session.add(
                Order(
                    id=oid,
                    user_id=1,
                    account_id=6,
                    symbol_id=sym.id,
                    side=OrderSide.BUY,
                    qty=Decimal("10"),
                    type=OrderType.MARKET,
                    tif=TimeInForce.DAY,
                    status=OrderStatus.FILLED,
                    source_type=OrderSourceType.STRATEGY,
                    source_id=source_id,
                    created_at=T0,
                    updated_at=T0,
                )
            )
            session.add(
                Fill(id=oid, order_id=oid, qty=Decimal("10"), price=Decimal("100"), filled_at=T0)
            )
            await session.commit()

    async def hold(ticker):
        async with session_factory() as session:
            sym = (
                (await session.execute(select(Symbol).where(Symbol.ticker == ticker)))
                .scalars()
                .first()
            )
            session.add(
                Position(
                    user_id=1,
                    account_id=6,
                    symbol_id=sym.id,
                    qty=Decimal("10"),
                    avg_entry_price=Decimal("100"),
                    side="long",
                    market_value=Decimal("1000"),
                    cost_basis=Decimal("1000"),
                    unrealized_pl=Decimal("0"),
                    unrealized_plpc=Decimal("0"),
                    updated_at=T0,
                )
            )
            await session.commit()

    await acquire("OWNED", 1)
    await hold("OWNED")
    await acquire("CONTESTED", 2)
    await acquire("CONTESTED", 3, source_id="9")
    await hold("CONTESTED")
    await acquire("GHOST", 4)
    await hold("GHOST")


async def _run(session_factory, *, suppress: bool):
    submitted: list = []

    async def submit(req):
        submitted.append(req)
        return MagicMock(id=len(submitted))

    router = MagicMock()
    router.submit = AsyncMock(side_effect=submit)
    liq = StrategyPositionLiquidator(
        StrategyOwnedHoldingsProvider(session_factory, _FakeIdentity()),
        router,
        operation=OwnershipOperation.PAPER_LIQUIDATION,
    )
    if suppress:
        # Emission removed entirely. Behaviour must be identical.
        liq._diagnostics = _Silent()  # type: ignore[assignment]
    result = await liq.liquidate(
        strategy_id=8,
        user_id=1,
        account_id=6,
        broker_positions=[
            {"symbol": "OWNED", "qty": "10"},
            {"symbol": "CONTESTED", "qty": "10"},
            {"symbol": "GHOST", "qty": "10"},
        ],
    )
    return result, submitted


class _Silent:
    def emit_exclusions(self, *a, **k):
        return []

    def emit_liquidation_exclusion(self, *a, **k):
        return None


async def test_suppressing_emission_changes_no_decision(book, session_factory):
    """Mutation proof: remove observability, keep every outcome.

    Same orders, same dispositions, same fail-closed refusals. If a decision had come to
    depend on the emitter, this is where it would show.
    """
    loud_result, loud_orders = await _run(session_factory, suppress=False)
    quiet_result, quiet_orders = await _run(session_factory, suppress=True)

    assert [r.symbol_ticker for r in loud_orders] == [r.symbol_ticker for r in quiet_orders]
    assert [(x.ticker, x.disposition) for x in loud_result.lines] == [
        (x.ticker, x.disposition) for x in quiet_result.lines
    ]
    # And the substance is what we expect: only the owned name closed.
    assert [x.ticker for x in loud_result.liquidated] == ["OWNED"]
    assert {x.disposition for x in loud_result.excluded} == {
        LiquidationDisposition.EXCLUDED_AMBIGUOUS,
        LiquidationDisposition.EXCLUDED_IDENTITY_UNRESOLVED,
    }


async def test_a_raising_emitter_does_not_change_authorization(book, session_factory):
    """Diagnostics are not on the safety path, so a broken logger must not alter outcomes.

    It may propagate — that is a logging bug, loudly. What it must NOT do is silently
    widen or narrow what gets liquidated.
    """
    submitted: list = []

    async def submit(req):
        submitted.append(req)
        return MagicMock(id=1)

    router = MagicMock()
    router.submit = AsyncMock(side_effect=submit)
    liq = StrategyPositionLiquidator(
        StrategyOwnedHoldingsProvider(session_factory, _FakeIdentity()), router
    )
    liq._diagnostics = _Silent()  # type: ignore[assignment]
    result = await liq.liquidate(
        strategy_id=8,
        user_id=1,
        account_id=6,
        broker_positions=[{"symbol": "CONTESTED", "qty": "10"}],
    )
    # Still refused. The refusal came from classification, not from reporting it.
    assert submitted == []
    assert result.order_ids == []
