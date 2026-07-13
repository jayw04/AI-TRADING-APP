"""ADR 0042 — the risk-effect classifier. Acceptance suite.

The governing rule: an action is classified by its PROJECTED EFFECT on the account's risk
state, never by its BUY/SELL verb, never by strategy identity, never by human-vs-automated
origin.

The centrepiece is ``test_replay_2026_07_13_*``: the exact SNDK and LITE proposals the momentum
book made at 10:00 ET on 2026-07-13 and had rejected by the daily-loss gate. They must now
classify as verified reductions — while every exposure-increasing path stays blocked.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.db.enums import OrderSide
from app.risk.risk_effect import (
    RISK_POLICY_VERSION,
    AccountSnapshot,
    ActionType,
    Decision,
    ProposedAction,
    RiskEffect,
    RiskEffectReason,
    SnapshotOpenOrder,
    SnapshotPosition,
    available_reducible_quantity,
    classify,
)

D = Decimal


def _snap(positions=None, open_orders=None, *, reserved=None, complete=True,
          cursor="100", observed="100") -> AccountSnapshot:
    return AccountSnapshot(
        account_id=1,
        positions={p.symbol: p for p in (positions or [])},
        open_orders=list(open_orders or []),
        cash=D("1918.52"),
        equity=D("100164.09"),
        broker_cursor=cursor,
        observed_cursor=observed,
        complete=complete,
        reserved_reducing_qty=reserved or {},
    )


# ============================================================ THE INCIDENT REPLAY
# The live book at 10:00 ET on 2026-07-13, and the two trims it was denied.

MOMENTUM_BOOK = [
    SnapshotPosition("LITE", D("27.84"), D("773.86")),
    SnapshotPosition("SNDK", D("11.68"), D("1738.47")),
    SnapshotPosition("WDC", D("120.0"), D("166.64")),
    SnapshotPosition("MU", D("140.0"), D("138.18")),
    SnapshotPosition("BE", D("70.76"), D("240.865")),
]


@pytest.mark.parametrize(
    ("symbol", "qty"),
    [("SNDK", D("0.218780")), ("LITE", D("2.092465"))],
)
def test_replay_2026_07_13_the_denied_trims_are_now_verified_reductions(symbol, qty):
    """BEFORE: DAILY_LOSS reject. AFTER: ALLOW_VERIFIED_REDUCTION.

    These are the two orders the strategy proposed and the daily-loss gate refused while the
    book bled from -$5,504 to -$7,501 at 98% invested.
    """
    snap = _snap(MOMENTUM_BOOK)
    action = ProposedAction(ActionType.ORDER_SUBMIT, symbol, OrderSide.SELL, qty)

    d = classify(snap, action)

    assert d.risk_effect is RiskEffect.RISK_REDUCING
    assert d.decision is Decision.ALLOW
    assert d.is_verified_reduction
    assert d.reasons == [RiskEffectReason.VERIFIED_REDUCTION]
    assert d.gross_exposure_after < d.gross_exposure_before
    assert d.position_qty_after >= 0


def test_replay_2026_07_13_a_buy_is_still_rejected():
    """The BE entry the strategy also proposed. Reductions pass; additions do not."""
    snap = _snap(MOMENTUM_BOOK)
    d = classify(
        snap,
        ProposedAction(ActionType.ORDER_SUBMIT, "BE", OrderSide.BUY, D("12"), D("240.865")),
    )
    assert d.risk_effect is RiskEffect.RISK_INCREASING
    assert d.decision is Decision.REJECT


# ============================================================ NEGATIVE PATHS (must stay blocked)


def test_oversell_that_crosses_zero_is_rejected():
    """Selling 600 from a long of 500 reverses into a short. Rule 2."""
    snap = _snap([SnapshotPosition("AAPL", D("500"), D("100"))])
    d = classify(
        snap, ProposedAction(ActionType.ORDER_SUBMIT, "AAPL", OrderSide.SELL, D("600"))
    )
    assert d.risk_effect is RiskEffect.RISK_INCREASING
    assert d.decision is Decision.REJECT
    assert RiskEffectReason.CROSSES_ZERO in d.reasons


def test_selling_an_unowned_security_opens_a_short_and_is_rejected():
    """THE REASON THE VERB IS NOT A CLASSIFICATION. This is a SELL, and it is risk-INCREASING."""
    snap = _snap([SnapshotPosition("AAPL", D("500"), D("100"))])
    d = classify(
        snap,
        ProposedAction(ActionType.ORDER_SUBMIT, "TSLA", OrderSide.SELL, D("10"), D("400")),
    )
    assert d.risk_effect is RiskEffect.RISK_INCREASING
    assert d.decision is Decision.REJECT
    assert RiskEffectReason.NO_POSITION in d.reasons


def test_buy_to_open_is_rejected():
    snap = _snap([])
    d = classify(
        snap,
        ProposedAction(ActionType.ORDER_SUBMIT, "AAPL", OrderSide.BUY, D("10"), D("100")),
    )
    assert d.decision is Decision.REJECT
    assert RiskEffectReason.OPENS_NEW_POSITION in d.reasons


def test_buy_to_cover_a_short_is_representable_but_blocked_in_v1():
    """Conceptually risk-reducing; explicitly out of v1 scope. The ADR keeps 'the rule' and
    'the v1 implementation' apart, and so does the code: the effect is REDUCING, the decision
    is REJECT."""
    snap = _snap([SnapshotPosition("AAPL", D("-100"), D("100"))])
    d = classify(
        snap,
        ProposedAction(ActionType.ORDER_SUBMIT, "AAPL", OrderSide.BUY, D("50"), D("100")),
    )
    assert d.risk_effect is RiskEffect.RISK_REDUCING
    assert d.decision is Decision.REJECT
    assert RiskEffectReason.SHORT_NOT_SUPPORTED_V1 in d.reasons


# ============================================================ § A — SNAPSHOT COHERENCE


def test_incomplete_snapshot_fails_closed():
    snap = _snap([SnapshotPosition("AAPL", D("500"), D("100"))], complete=False)
    d = classify(snap, ProposedAction(ActionType.ORDER_SUBMIT, "AAPL", OrderSide.SELL, D("10")))
    assert d.risk_effect is RiskEffect.INDETERMINATE
    assert d.decision is Decision.FAIL_CLOSED


def test_snapshot_behind_an_already_observed_broker_event_is_stale():
    """Not 'a bit old' — a DIFFERENT ACCOUNT. Causal completeness, not an age threshold: the
    snapshot must be at or beyond every broker event we have already seen locally."""
    snap = _snap(
        [SnapshotPosition("AAPL", D("500"), D("100"))], cursor="099", observed="100"
    )
    d = classify(snap, ProposedAction(ActionType.ORDER_SUBMIT, "AAPL", OrderSide.SELL, D("10")))
    assert d.risk_effect is RiskEffect.INDETERMINATE
    assert d.decision is Decision.FAIL_CLOSED
    assert RiskEffectReason.SNAPSHOT_STALE in d.reasons


def test_unresolved_partial_fill_is_indeterminate():
    snap = _snap(
        [SnapshotPosition("AAPL", D("500"), D("100"))],
        [SnapshotOpenOrder("o1", "AAPL", OrderSide.SELL, D("10"), True, has_unresolved_partial_fill=True)],
    )
    d = classify(snap, ProposedAction(ActionType.ORDER_SUBMIT, "AAPL", OrderSide.SELL, D("10")))
    assert d.decision is Decision.FAIL_CLOSED
    assert RiskEffectReason.UNRESOLVED_PARTIAL_FILL in d.reasons


# ============================================================ § D — CONCURRENCY / RESERVATIONS


def test_two_concurrent_reductions_cannot_both_be_approved_into_a_short():
    """THE § D FAILURE. Two sells of 300 against a long of 500 each look safe in isolation —
    500-300 = 200 >= 0 — but together they cross through zero into a 100-share SHORT.

    The single-order zero-crossing check CANNOT see this. Only reducible capacity can.
    """
    long_500 = [SnapshotPosition("AAPL", D("500"), D("100"))]

    first = classify(
        _snap(long_500),
        ProposedAction(ActionType.ORDER_SUBMIT, "AAPL", OrderSide.SELL, D("300")),
    )
    assert first.is_verified_reduction  # in isolation, fine

    # ...the first is now reserved. The second must NOT be approved.
    second = classify(
        _snap(long_500, reserved={"AAPL": D("300")}),
        ProposedAction(ActionType.ORDER_SUBMIT, "AAPL", OrderSide.SELL, D("300")),
    )
    assert not second.is_verified_reduction
    assert second.decision is Decision.FAIL_CLOSED
    assert RiskEffectReason.EXCEEDS_REDUCIBLE_QUANTITY in second.reasons


def test_open_reducing_sells_consume_reducible_capacity():
    snap = _snap(
        [SnapshotPosition("AAPL", D("500"), D("100"))],
        [SnapshotOpenOrder("o1", "AAPL", OrderSide.SELL, D("400"), reduces_position=True)],
    )
    assert available_reducible_quantity(snap, "AAPL") == D("100")

    d = classify(snap, ProposedAction(ActionType.ORDER_SUBMIT, "AAPL", OrderSide.SELL, D("150")))
    assert d.decision is Decision.FAIL_CLOSED
    assert RiskEffectReason.EXCEEDS_REDUCIBLE_QUANTITY in d.reasons

    ok = classify(snap, ProposedAction(ActionType.ORDER_SUBMIT, "AAPL", OrderSide.SELL, D("100")))
    assert ok.is_verified_reduction


# ============================================================ § B — CANCELLATION


def test_cancelling_a_pending_buy_to_open_is_reducing():
    snap = _snap(
        [SnapshotPosition("AAPL", D("500"), D("100"))],
        [SnapshotOpenOrder("o1", "AAPL", OrderSide.BUY, D("50"), reduces_position=False)],
    )
    d = classify(snap, ProposedAction(ActionType.ORDER_CANCEL, "AAPL", target_order_id="o1"))
    assert d.risk_effect is RiskEffect.RISK_REDUCING
    assert d.decision is Decision.ALLOW


def test_cancelling_a_pending_sell_to_close_is_RISK_INCREASING():
    """THE TRAP § B EXISTS TO CLOSE. A blanket 'cancels always pass' rule would let an operator
    cancel the very protective reduction that is de-risking the book — which is exactly the
    trapped-risk failure this entire ADR was written to prevent."""
    snap = _snap(
        [SnapshotPosition("AAPL", D("500"), D("100"))],
        [SnapshotOpenOrder("o1", "AAPL", OrderSide.SELL, D("50"), reduces_position=True)],
    )
    d = classify(snap, ProposedAction(ActionType.ORDER_CANCEL, "AAPL", target_order_id="o1"))
    assert d.risk_effect is RiskEffect.RISK_INCREASING
    assert d.decision is Decision.REJECT
    assert RiskEffectReason.CANCEL_REMOVES_PROTECTIVE_REDUCTION in d.reasons


def test_cancelling_an_unknown_order_fails_closed():
    snap = _snap([SnapshotPosition("AAPL", D("500"), D("100"))])
    d = classify(snap, ProposedAction(ActionType.ORDER_CANCEL, "AAPL", target_order_id="ghost"))
    assert d.decision is Decision.FAIL_CLOSED


def test_order_replace_is_indeterminate_in_v1():
    snap = _snap([SnapshotPosition("AAPL", D("500"), D("100"))])
    d = classify(
        snap,
        ProposedAction(ActionType.ORDER_REPLACE, "AAPL", OrderSide.SELL, D("10"), target_order_id="o1"),
    )
    assert d.decision is Decision.FAIL_CLOSED


# ============================================================ DETERMINISM (release gate #8)


def test_same_snapshot_and_proposal_yield_the_same_classification():
    snap = _snap(MOMENTUM_BOOK)
    action = ProposedAction(ActionType.ORDER_SUBMIT, "SNDK", OrderSide.SELL, D("0.218780"))

    a, b = classify(snap, action), classify(snap, action)

    assert a == b
    assert a.policy_version == RISK_POLICY_VERSION
    assert a.before_state_hash == b.before_state_hash
    assert a.projected_after_state_hash == b.projected_after_state_hash


def test_the_state_hash_changes_when_the_account_changes():
    """An approval must not be silently applied to a different account state."""
    one = _snap([SnapshotPosition("AAPL", D("500"), D("100"))]).state_hash()
    two = _snap([SnapshotPosition("AAPL", D("499"), D("100"))]).state_hash()
    assert one != two


def test_zero_and_negative_quantities_fail_closed():
    snap = _snap([SnapshotPosition("AAPL", D("500"), D("100"))])
    for q in (D("0"), D("-5")):
        d = classify(snap, ProposedAction(ActionType.ORDER_SUBMIT, "AAPL", OrderSide.SELL, q))
        assert d.decision is Decision.FAIL_CLOSED
