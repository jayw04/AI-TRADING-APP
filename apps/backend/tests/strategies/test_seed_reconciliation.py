"""P7 §7-A.2a — exhaustive unit tests for the pure seed reconciliation state machine.

Pure function over normalized observations: no DB, no ctx, no mocks.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.strategies.context import FillEvent
from app.strategies.seed_reconciliation import (
    DeploymentState,
    OpenOrderObs,
    SeedAttempt,
    SeedAttemptStatus,
    reconcile_seed_attempt,
)

T0 = datetime(2026, 8, 3, 19, 50, tzinfo=UTC)
TS = datetime(2026, 8, 3, 19, 51, tzinfo=UTC)
PREFIX = "seed:11:att-1:"


def _attempt(**over):
    base = dict(
        attempt_id="att-1", created_at=T0, intended_symbols=("AAA", "BBB"),
        client_order_id_prefix=PREFIX, submitted_order_ids=(101, 102),
        status=SeedAttemptStatus.ORDERS_OPEN,
    )
    base.update(over)
    return SeedAttempt(**base)


def _fill(fid, oid, sym, qty, *, coid=None, ts=TS, status="filled"):
    return FillEvent(
        fill_id=fid, order_id=oid, symbol=sym, side="buy", qty=Decimal(str(qty)),
        price=Decimal("100"), filled_at=ts,
        client_order_id=coid if coid is not None else f"{PREFIX}{sym}",
        account_id=4, source_id="11", order_status=status,
    )


def test_qualifying_fill_with_exposure_deploys_fully():
    r = reconcile_seed_attempt(_attempt(), [_fill(1, 101, "AAA", 5), _fill(2, 102, "BBB", 3)],
                               [], {"AAA": Decimal(5), "BBB": Decimal(3)})
    assert r.deployment_state == DeploymentState.DEPLOYED
    assert r.seed_attempt_status == SeedAttemptStatus.FILLED
    assert r.first_deployed_at == TS
    assert r.should_clear_attempt is True
    assert r.qualifying_fill_ids == (1, 2)
    assert r.alerts == ()


def test_deployed_while_remaining_orders_stay_partially_filled():
    r = reconcile_seed_attempt(_attempt(), [_fill(1, 101, "AAA", 5)],
                               [OpenOrderObs(102, "BBB")], {"AAA": Decimal(5)})
    assert r.deployment_state == DeploymentState.DEPLOYED
    assert r.seed_attempt_status == SeedAttemptStatus.PARTIALLY_FILLED
    assert r.should_clear_attempt is False  # attempt keeps reconciling after deploy


def test_later_poll_closes_remaining_orders_without_changing_first_deployed_at():
    f = _fill(1, 101, "AAA", 5)
    partial = reconcile_seed_attempt(_attempt(), [f], [OpenOrderObs(102, "BBB")], {"AAA": Decimal(5)})
    # BBB now also filled, no open orders remain
    done = reconcile_seed_attempt(_attempt(), [f, _fill(2, 102, "BBB", 3)], [],
                                  {"AAA": Decimal(5), "BBB": Decimal(3)})
    assert partial.seed_attempt_status == SeedAttemptStatus.PARTIALLY_FILLED
    assert done.seed_attempt_status == SeedAttemptStatus.FILLED
    assert done.first_deployed_at == partial.first_deployed_at == f.filled_at
    assert done.should_clear_attempt is True


def test_fill_without_exposure_is_deployed_with_nonblocking_alert():
    # Fill is the authority; missing exposure is a NON-blocking alert (shared-account
    # netting is possible), and the fill stays unresolved so a later poll re-checks.
    r = reconcile_seed_attempt(_attempt(), [_fill(1, 101, "AAA", 5)], [], {"AAA": Decimal(0)})
    assert r.deployment_state == DeploymentState.DEPLOYED
    assert "fill_without_exposure" in r.alerts
    assert r.seed_attempt_status == SeedAttemptStatus.PARTIALLY_FILLED
    assert r.unresolved_fill_ids == (1,)
    assert r.should_clear_attempt is False


def test_unresolved_fill_is_reconsidered_after_exposure_catches_up():
    f = _fill(1, 101, "AAA", 5)
    p1 = reconcile_seed_attempt(_attempt(), [f], [], {"AAA": Decimal(0)})
    p2 = reconcile_seed_attempt(_attempt(), [f], [], {"AAA": Decimal(5)})
    # committed cursor stays behind the unresolved fill in p1, advances in p2
    assert p1.committed_cursor != (f.filled_at, f.fill_id)
    assert p2.committed_cursor == (f.filled_at, f.fill_id)
    assert p2.seed_attempt_status == SeedAttemptStatus.FILLED
    assert p2.unresolved_fill_ids == ()


def test_position_without_attributed_fill_blocks_reconciliation_required():
    r = reconcile_seed_attempt(_attempt(), [], [], {"AAA": Decimal(5)})
    assert r.deployment_state == DeploymentState.DEPLOYMENT_PENDING
    assert r.seed_attempt_status == SeedAttemptStatus.RECONCILIATION_REQUIRED
    assert r.alerts == ("unattributed_position_during_seed",)


def test_same_symbol_position_from_another_source_cannot_prove_deployment():
    # A position in an intended symbol, but NO qualifying fill -> not DEPLOYED.
    r = reconcile_seed_attempt(_attempt(), [], [], {"AAA": Decimal(9)})
    assert r.deployment_state != DeploymentState.DEPLOYED
    assert r.seed_attempt_status == SeedAttemptStatus.RECONCILIATION_REQUIRED


def test_qualifying_fill_plus_unrelated_position_deploys_with_alert_not_suppression():
    r = reconcile_seed_attempt(_attempt(), [_fill(1, 101, "AAA", 5)], [],
                               {"AAA": Decimal(5), "CCC": Decimal(7)})  # CCC = another source
    assert r.deployment_state == DeploymentState.DEPLOYED
    assert "unattributed_position_during_seed" in r.alerts


def test_no_fills_with_open_orders_stays_pending():
    r = reconcile_seed_attempt(_attempt(), [], [OpenOrderObs(101, "AAA")], {})
    assert r.deployment_state == DeploymentState.DEPLOYMENT_PENDING
    assert r.seed_attempt_status == SeedAttemptStatus.ORDERS_OPEN


def test_terminally_unfilled_signals_archive_and_rollback():
    r = reconcile_seed_attempt(_attempt(), [], [], {})
    assert r.deployment_state == DeploymentState.NEVER_DEPLOYED
    assert r.seed_attempt_status == SeedAttemptStatus.TERMINALLY_UNFILLED
    assert r.should_clear_attempt is True  # caller ARCHIVES then clears (not delete)


def test_fill_on_canceled_order_still_qualifies():
    r = reconcile_seed_attempt(_attempt(), [_fill(1, 101, "AAA", 5, status="canceled")], [],
                               {"AAA": Decimal(5)})
    assert r.deployment_state == DeploymentState.DEPLOYED
    assert r.first_deployed_at == TS


def test_unattributable_fill_and_its_position_flag_unattributed():
    stray = _fill(9, 999, "AAA", 5, coid="seed:11:other:AAA")
    r = reconcile_seed_attempt(_attempt(), [stray], [], {"AAA": Decimal(5)})
    assert r.seed_attempt_status == SeedAttemptStatus.RECONCILIATION_REQUIRED
    assert r.alerts == ("unattributed_position_during_seed",)
    assert r.qualifying_fill_ids == ()


def test_cursor_ties_are_ordered_by_fill_id():
    r = reconcile_seed_attempt(_attempt(), [_fill(7, 101, "AAA", 5), _fill(3, 102, "BBB", 3)],
                               [], {"AAA": Decimal(5), "BBB": Decimal(3)})
    assert r.observed_cursor == (TS, 7)


def test_replayed_fills_are_idempotent_and_stable():
    f = _fill(1, 101, "AAA", 5)
    r1 = reconcile_seed_attempt(_attempt(status=SeedAttemptStatus.FILLED), [f], [], {"AAA": Decimal(5)})
    r2 = reconcile_seed_attempt(_attempt(status=SeedAttemptStatus.FILLED), [f, f], [], {"AAA": Decimal(5)})
    assert r1.first_deployed_at == r2.first_deployed_at == f.filled_at
    assert r1.qualifying_fill_ids == r2.qualifying_fill_ids == (1,)
    assert r1.deployment_state == r2.deployment_state == DeploymentState.DEPLOYED


def test_multiple_qualifying_fills_use_earliest_timestamp_regardless_of_order():
    early = _fill(2, 102, "BBB", 3, ts=datetime(2026, 8, 3, 19, 50, 30, tzinfo=UTC))
    late = _fill(1, 101, "AAA", 5, ts=datetime(2026, 8, 3, 19, 55, tzinfo=UTC))
    r = reconcile_seed_attempt(_attempt(), [late, early], [],
                               {"AAA": Decimal(5), "BBB": Decimal(3)})
    assert r.first_deployed_at == early.filled_at  # earliest, not retrieval order
