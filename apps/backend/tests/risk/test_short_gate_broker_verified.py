"""The SHORT_NOT_ALLOWED gate — the position it trusts must be the BROKER's, not the ledger's.

WHY THIS FILE EXISTS. On 2026-07-16 account 2 was found holding an AMD -4 SHORT while
`allow_short = 0`. The gate was never bypassed — it was TOLD THE WRONG POSITION. An Alpaca paper
account reset (2026-07-07 15:36) wiped the broker's positions while the local order ledger kept
every pre-reset fill, leaving the local view permanently +7 AMD long of reality. A SELL 7 then
looked like a legal flatten locally (7 -> 0) and opened a real -7 short at the broker.
See docs/incidents/2026-07-16-account2-ghost-positions-short-gate-escape.md.

The first half of this file pins the gate's PRE-EXISTING behaviour (the suite had exactly one
trivial test), so the broker-verification change lands on a regression net rather than on nothing.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.db.enums import OrderSide, OrderSourceType, OrderType, RiskScopeType, TimeInForce
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.position import Position
from app.db.models.risk_limits import RiskLimits
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.risk.engine import RiskEngine
from app.risk.reason_codes import ReasonCode
from app.risk.types import OrderRequest


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Paper"))
        s.add(Symbol(id=1, ticker="AMD", exchange="NASDAQ", asset_class="us_equity",
                     name="AMD", active=True))
        s.add(RiskLimits(
            user_id=1, scope_type=RiskScopeType.GLOBAL, scope_id=None,
            max_position_qty=Decimal("1000"), max_position_notional=Decimal("1000000"),
            max_gross_exposure=Decimal("10000000"), max_daily_loss=Decimal("5000"),
            max_orders_per_minute=100, allow_short=False, created_at=_now(), updated_at=_now(),
        ))
        s.add(AccountState(
            account_id=1, cash=Decimal("100000"), equity=Decimal("100000"),
            last_equity=Decimal("100000"), buying_power=Decimal("200000"),
            portfolio_value=Decimal("100000"), daytrade_count=0, day_change=Decimal(0),
            day_change_pct=Decimal(0), status="ACTIVE", pattern_day_trader=False,
            trading_blocked=False, account_blocked=False, raw_payload={}, updated_at=_now(),
        ))
        await s.commit()
    yield


async def _set_local_position(session_factory, qty: Decimal) -> None:
    """The LEDGER-derived local position — the number the old gate trusted."""
    async with session_factory() as s:
        s.add(Position(user_id=1, account_id=1, symbol_id=1, qty=qty,
                       avg_entry_price=Decimal("500"), side="long",
                       market_value=qty * Decimal("500"), cost_basis=qty * Decimal("500"),
                       unrealized_pl=Decimal(0), unrealized_plpc=Decimal(0), updated_at=_now()))
        await s.commit()


def _req(**over) -> OrderRequest:
    base = dict(user_id=1, account_id=1, symbol_ticker="AMD", side=OrderSide.SELL,
                qty=Decimal("7"), type=OrderType.MARKET, tif=TimeInForce.DAY,
                source_type=OrderSourceType.MANUAL)
    base.update(over)
    return OrderRequest(**base)


class _Adapter:
    """Minimal broker stub. `positions` is what the BROKER really holds."""

    def __init__(self, positions: list[dict] | None = None, fail: bool = False):
        self._positions = positions or []
        self._fail = fail

    def get_account(self):
        if self._fail:
            raise RuntimeError("broker unreachable")
        return {"cash": "100000", "equity": "100000"}

    def get_positions(self):
        if self._fail:
            raise RuntimeError("broker unreachable")
        return self._positions

    def list_orders(self, **_kw):
        if self._fail:
            raise RuntimeError("broker unreachable")
        return []


class _Registry:
    def __init__(self, adapter):
        self._a = adapter

    def get(self, account_id: int):          # keyed by ACCOUNT id, not user id
        return self._a if account_id == 1 else None


def _amd(qty: str, side: str = "long") -> dict:
    return {"symbol": "AMD", "qty": qty, "side": side, "current_price": "500",
            "market_value": str(Decimal(qty) * Decimal("500"))}


# =====================================================================================
# PART 1 — the gate's PRE-EXISTING behaviour, pinned before it is changed.
# These must hold with or without a broker: they are the contract, not the mechanism.
# =====================================================================================
async def test_sell_with_no_position_is_rejected(session_factory, seeded) -> None:
    out = await RiskEngine(session_factory).evaluate(_req(), trading_mode="paper")
    assert ReasonCode.SHORT_NOT_ALLOWED in out.reason_codes


async def test_sell_within_the_long_is_allowed(session_factory, seeded) -> None:
    await _set_local_position(session_factory, Decimal("10"))
    eng = RiskEngine(session_factory, broker_registry=_Registry(_Adapter([_amd("10")])))
    out = await eng.evaluate(_req(qty=Decimal("7")), trading_mode="paper")
    assert out.passed, out.reason_codes


async def test_sell_exceeding_the_long_is_rejected(session_factory, seeded) -> None:
    await _set_local_position(session_factory, Decimal("3"))
    eng = RiskEngine(session_factory, broker_registry=_Registry(_Adapter([_amd("3")])))
    out = await eng.evaluate(_req(qty=Decimal("7")), trading_mode="paper")
    assert ReasonCode.SHORT_NOT_ALLOWED in out.reason_codes


async def test_buy_is_never_touched_by_the_short_gate(session_factory, seeded) -> None:
    out = await RiskEngine(session_factory).evaluate(
        _req(side=OrderSide.BUY, qty=Decimal("7")), trading_mode="paper")
    assert ReasonCode.SHORT_NOT_ALLOWED not in out.reason_codes


async def test_gate_does_not_apply_when_shorting_is_allowed(session_factory, seeded) -> None:
    async with session_factory() as s:
        rl = await s.get(RiskLimits, 1)
        rl.allow_short = True
        await s.commit()
    out = await RiskEngine(session_factory).evaluate(_req(), trading_mode="paper")
    assert ReasonCode.SHORT_NOT_ALLOWED not in out.reason_codes


# =====================================================================================
# PART 2 — the fix. The gate must trust the BROKER.
# =====================================================================================
async def test_ghost_long_must_not_authorise_a_real_short(session_factory, seeded) -> None:
    """THE REGRESSION. Account 2, 2026-07-16, reproduced exactly.

    Local ledger says +7 (ghost from a pre-reset fill the broker never saw); the broker is FLAT.
    The old gate compared against the ghost, passed `SELL 7` as a flatten, and opened a -7 short.
    """
    await _set_local_position(session_factory, Decimal("7"))          # the ghost
    eng = RiskEngine(session_factory, broker_registry=_Registry(_Adapter([])))  # broker: FLAT
    out = await eng.evaluate(_req(qty=Decimal("7")), trading_mode="paper")
    assert ReasonCode.SHORT_NOT_ALLOWED in out.reason_codes, (
        "a ghost long authorised a real short — the account-2 escape")


async def test_broker_position_authorises_a_genuine_reduction(session_factory, seeded) -> None:
    """The converse: the broker holds it, so the reduction is legal even if the ledger lags."""
    await _set_local_position(session_factory, Decimal("0"))          # ledger behind
    eng = RiskEngine(session_factory, broker_registry=_Registry(_Adapter([_amd("100")])))
    out = await eng.evaluate(_req(qty=Decimal("7")), trading_mode="paper")
    assert out.passed, (
        f"the broker holds 100; refusing a 7-share reduction would trap de-risking: "
        f"{out.reason_codes}")


async def test_broker_short_position_cannot_be_sold_further(session_factory, seeded) -> None:
    """Already short at the broker (the live account-2 state): any further SELL deepens it."""
    await _set_local_position(session_factory, Decimal("3"))
    eng = RiskEngine(session_factory,
                     broker_registry=_Registry(_Adapter([_amd("4", side="short")])))
    out = await eng.evaluate(_req(qty=Decimal("1")), trading_mode="paper")
    assert ReasonCode.SHORT_NOT_ALLOWED in out.reason_codes


# =====================================================================================
# PART 3 — the degradation path. A broker outage must NOT trap de-risking.
#
# router.py runs RiskEngine.evaluate() (line ~275) BEFORE RiskDecisionService.decide()
# (line ~435). So a fail-closed rejection here would block a locked account's de-risking SELL
# upstream of the ADR-0042 path built to allow it — reproducing the 2026-07-13 incident. Account
# 3's /v2/positions timed out >15s on 2026-07-15, so this is measured, not hypothetical.
# Owner-approved 2026-07-16: on an unverifiable broker, fall back to the ledger and RECORD the
# degradation. Strictly better than the status quo; introduces no new blocking.
# =====================================================================================
async def test_broker_read_failure_falls_back_to_local_and_does_not_block(
    session_factory, seeded
) -> None:
    await _set_local_position(session_factory, Decimal("10"))
    eng = RiskEngine(session_factory, broker_registry=_Registry(_Adapter(fail=True)))
    out = await eng.evaluate(_req(qty=Decimal("7")), trading_mode="paper")
    assert out.passed, (
        f"a broker outage must not block a ledger-legal reduction — that is the 07-13 "
        f"de-risking trap: {out.reason_codes}")


async def test_broker_read_failure_still_enforces_the_local_bound(
    session_factory, seeded
) -> None:
    """Degraded != disabled. The ledger bound still applies when the broker is unreadable."""
    await _set_local_position(session_factory, Decimal("3"))
    eng = RiskEngine(session_factory, broker_registry=_Registry(_Adapter(fail=True)))
    out = await eng.evaluate(_req(qty=Decimal("7")), trading_mode="paper")
    assert ReasonCode.SHORT_NOT_ALLOWED in out.reason_codes


async def test_no_registry_falls_back_to_local(session_factory, seeded) -> None:
    """Pre-§5 call sites and unit tests construct RiskEngine(session_factory) with no registry.
    Production always wires one (lifespan.py). No registry must not mean 'reject every SELL'."""
    await _set_local_position(session_factory, Decimal("10"))
    out = await RiskEngine(session_factory).evaluate(_req(qty=Decimal("7")), trading_mode="paper")
    assert out.passed, out.reason_codes
