"""ADR 0042 — the decision service: atomic classify → reserve → persist, and the § A race.

The classifier is pure and already tested. What is tested HERE is the part a pure function
cannot express:

* **§ D** — two concurrent reductions must not both consume the same capacity. This is the
  failure the zero-crossing rule cannot see: two sells of 300 against a long of 500 each pass
  in isolation (``500 - 300 >= 0``) and together create a 100-share short. Only a *reservation*
  that is actually taken can stop it, and only if classification and reservation are atomic.

* **§ A** — an approval is a statement about a *specific account state*. If that state moves
  before submission, the approval is void: release, re-fetch, re-classify **once**, never reuse.

* **§ 7** — every decision writes a ledger row. **Including a rejection.** An order that never
  existed because a gate refused it is exactly the event you most need a record of.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.db.enums import OrderSide
from app.db.models.account import Account, AccountMode
from app.db.models.risk_decision import RiskDecision
from app.db.models.risk_reservation import (
    RESERVATION_HELD,
    RESERVATION_RELEASED,
    RiskReservation,
)
from app.db.models.user import User
from app.risk.decision_service import LOCK_DAILY_LOSS, RiskDecisionService
from app.risk.risk_effect import (
    ActionType,
    Decision,
    ProposedAction,
    RiskEffect,
    RiskEffectReason,
)

D = Decimal


def _adapter(qty="500", price="100.00", open_orders=None):
    """A broker holding `qty` of AAPL at `price`."""
    ad = MagicMock()
    ad.get_account.return_value = {"cash": "10000", "equity": "60000", "id": "acct-x"}
    ad.get_positions.return_value = [
        {"symbol": "AAPL", "qty": qty, "side": "long", "current_price": price}
    ]
    ad.list_orders.return_value = open_orders or []
    return ad


@pytest.fixture
async def acct(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="P"))
        await s.commit()
    return 1


def _sell(qty: str) -> ProposedAction:
    return ProposedAction(ActionType.ORDER_SUBMIT, "AAPL", OrderSide.SELL, D(qty))


async def _rows(session_factory, model):
    async with session_factory() as s:
        return list((await s.execute(select(model).order_by(model.id))).scalars().all())


# ------------------------------------------------------------------ § D concurrency


async def test_two_concurrent_reductions_cannot_both_reserve_the_same_capacity(
    session_factory, acct
):
    """THE § D FAILURE, under real interleaving.

    Long 500. Two sells of 300 fired CONCURRENTLY. Each is individually legal. Together they
    would leave the account 100 short. Exactly one may reserve.
    """
    ad = _adapter(qty="500")

    async def submit() -> tuple:
        async with session_factory() as s:
            return await RiskDecisionService(s).decide(
                account_id=acct, adapter=ad, action=_sell("300"),
                lock_state=LOCK_DAILY_LOSS, daily_pnl=D("-6790.61"),
            )

    a, b = await asyncio.gather(submit(), submit())

    allowed = [r for r, _, _ in (a, b) if r.decision is Decision.ALLOW]
    assert len(allowed) == 1, "both reductions were approved — the account would go short"

    refused = [r for r, _, _ in (a, b) if r.decision is not Decision.ALLOW][0]
    assert refused.decision is Decision.FAIL_CLOSED

    # Exactly one reservation is HELD, and it does not exceed the long.
    held = [r for r in await _rows(session_factory, RiskReservation) if r.state == RESERVATION_HELD]
    assert len(held) == 1
    assert sum(r.qty for r in held) <= D("500")

    # BOTH decisions are on the ledger — the refusal is evidence too.
    assert len(await _rows(session_factory, RiskDecision)) == 2


async def test_reservations_are_netted_out_of_reducible_capacity(session_factory, acct):
    ad = _adapter(qty="500")
    async with session_factory() as s:
        first, _, _ = await RiskDecisionService(s).decide(
            account_id=acct, adapter=ad, action=_sell("400"), lock_state=LOCK_DAILY_LOSS
        )
    assert first.decision is Decision.ALLOW

    async with session_factory() as s:
        second, _, _ = await RiskDecisionService(s).decide(
            account_id=acct, adapter=ad, action=_sell("200"), lock_state=LOCK_DAILY_LOSS
        )
    # only 100 remains reducible
    assert second.decision is Decision.FAIL_CLOSED
    assert second.available_reducible_qty == D("100")


async def test_releasing_a_reservation_returns_the_capacity(session_factory, acct):
    ad = _adapter(qty="500")
    async with session_factory() as s:
        svc = RiskDecisionService(s)
        _, _, res_id = await svc.decide(
            account_id=acct, adapter=ad, action=_sell("400"), lock_state=LOCK_DAILY_LOSS
        )
        await svc.release_reservation(res_id, reason="TEST")

    async with session_factory() as s:
        again, _, _ = await RiskDecisionService(s).decide(
            account_id=acct, adapter=ad, action=_sell("400"), lock_state=LOCK_DAILY_LOSS
        )
    assert again.decision is Decision.ALLOW


# ------------------------------------------------------------------ § A snapshot race


async def test_state_change_before_submission_voids_the_approval(session_factory, acct):
    """An approval is a statement about a SPECIFIC state. If the state moves, it is void —
    release, re-fetch, re-classify ONCE. The prior decision is never reused."""
    ad = _adapter(qty="500")
    async with session_factory() as s:
        svc = RiskDecisionService(s)
        first, ledger_id, res_id = await svc.decide(
            account_id=acct, adapter=ad, action=_sell("300"), lock_state=LOCK_DAILY_LOSS
        )
        assert first.decision is Decision.ALLOW

        # ...a fill lands at the broker. The position is now 250, not 500.
        ad.get_positions.return_value = [
            {"symbol": "AAPL", "qty": "250", "side": "long", "current_price": "100.00"}
        ]

        result, new_ledger_id, _ = await svc.confirm_unchanged_or_reclassify(
            account_id=acct, adapter=ad, action=_sell("300"),
            prior=first, prior_ledger_id=ledger_id, reservation_id=res_id,
            lock_state=LOCK_DAILY_LOSS,
        )

    # The stale approval must NOT survive. Re-classified against the TRUE state, selling 300
    # from a 250 long crosses through zero into a short — so it is RISK_INCREASING / REJECT
    # (rule 2), not merely "insufficient capacity". Had the earlier approval been reused, this
    # is exactly the order that would have opened a short position.
    assert new_ledger_id != ledger_id
    assert result.risk_effect is RiskEffect.RISK_INCREASING
    assert result.decision is Decision.REJECT
    assert RiskEffectReason.CROSSES_ZERO in result.reasons

    reservations = await _rows(session_factory, RiskReservation)
    assert reservations[0].state == RESERVATION_RELEASED
    assert reservations[0].release_reason == "VERSION_CONFLICT"

    # The retry REFERENCES the prior decision rather than overwriting it.
    decisions = await _rows(session_factory, RiskDecision)
    assert decisions[-1].supersedes_id == ledger_id
    assert decisions[-1].retry_generation == 1


async def test_unchanged_state_keeps_the_approval(session_factory, acct):
    ad = _adapter(qty="500")
    async with session_factory() as s:
        svc = RiskDecisionService(s)
        first, ledger_id, res_id = await svc.decide(
            account_id=acct, adapter=ad, action=_sell("300"), lock_state=LOCK_DAILY_LOSS
        )
        same, same_id, same_res = await svc.confirm_unchanged_or_reclassify(
            account_id=acct, adapter=ad, action=_sell("300"),
            prior=first, prior_ledger_id=ledger_id, reservation_id=res_id,
            lock_state=LOCK_DAILY_LOSS,
        )
    assert same_id == ledger_id and same_res == res_id
    assert same.decision is Decision.ALLOW


# ------------------------------------------------------------------ § A broker failure


async def test_broker_read_failure_fails_closed_and_is_still_recorded(session_factory, acct):
    """A broker we cannot read is not permission to trade — and the refusal is still evidence."""
    ad = _adapter()
    ad.get_positions.side_effect = RuntimeError("broker unreachable")

    async with session_factory() as s:
        result, ledger_id, res_id = await RiskDecisionService(s).decide(
            account_id=acct, adapter=ad, action=_sell("100"), lock_state=LOCK_DAILY_LOSS
        )

    assert result.risk_effect is RiskEffect.INDETERMINATE
    assert result.decision is Decision.FAIL_CLOSED
    assert res_id is None
    assert len(await _rows(session_factory, RiskDecision)) == 1


# ------------------------------------------------------------------ § 7 ledger + § C source


async def test_a_rejection_writes_a_ledger_row(session_factory, acct):
    """The 2026-07-13 hole: eighteen proposals refused, ZERO rows anywhere durable."""
    ad = _adapter(qty="500")
    async with session_factory() as s:
        result, _, _ = await RiskDecisionService(s).decide(
            account_id=acct, adapter=ad,
            action=ProposedAction(ActionType.ORDER_SUBMIT, "AAPL", OrderSide.BUY, D("10"), D("100")),
            lock_state=LOCK_DAILY_LOSS, daily_pnl=D("-6790.61"),
        )
    assert result.decision is Decision.REJECT

    rows = await _rows(session_factory, RiskDecision)
    assert len(rows) == 1
    assert rows[0].decision == "REJECT"
    assert rows[0].lock_state == LOCK_DAILY_LOSS
    assert rows[0].daily_pnl == D("-6790.6100")
    assert rows[0].before_state_hash
    assert rows[0].risk_policy_version


async def test_manual_and_strategy_reductions_are_classified_identically(session_factory, acct):
    """§ C — source-neutral. Trapped risk is equally dangerous regardless of who initiated the
    reduction, and a human cannot self-assert a risk effect."""
    ad = _adapter(qty="500")

    async with session_factory() as s:
        strat, _, res1 = await RiskDecisionService(s).decide(
            account_id=acct, adapter=ad, action=_sell("100"),
            lock_state=LOCK_DAILY_LOSS, source_type="STRATEGY",
        )
        await RiskDecisionService(s).release_reservation(res1, reason="TEST")

    async with session_factory() as s:
        manual, _, _ = await RiskDecisionService(s).decide(
            account_id=acct, adapter=ad, action=_sell("100"),
            lock_state=LOCK_DAILY_LOSS, source_type="MANUAL",
        )

    assert strat.risk_effect == manual.risk_effect
    assert strat.decision == manual.decision
    assert strat.reasons == manual.reasons

    rows = await _rows(session_factory, RiskDecision)
    assert {r.source_type for r in rows} == {"STRATEGY", "MANUAL"}
