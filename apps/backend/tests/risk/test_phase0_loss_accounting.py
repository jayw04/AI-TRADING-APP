"""WP8 AMD-18 — canonical loss accounting (hermetic; no broker)."""

from __future__ import annotations

from decimal import Decimal as D

from app.risk.loss_control.phase0_loss_accounting import (
    DEFAULT_POLICY,
    FORMULA_ID,
    AccountingRefuseReason,
    FillLeg,
    ResidualPosition,
    SettlementTiming,
    assert_no_order_path_imports,
    compute_canonical_loss,
    reconcile_model_vs_control,
)


def test_policy_freezes_amd18_slots() -> None:
    p = DEFAULT_POLICY.as_dict()
    assert p["formula_id"] == FORMULA_ID
    assert p["inter_leg_unrealized_counts"] is False
    assert p["settlement_timing"] == str(SettlementTiming.TRADE_DATE)
    assert p["model_round_trip_mode"] == "REALIZED_ONLY"


def test_round_trip_loss_with_fees() -> None:
    legs = (
        FillLeg(side="BUY", qty=D("10"), price=D("100.00"), commission=D("1.00")),
        FillLeg(
            side="SELL",
            qty=D("10"),
            price=D("99.00"),
            commission=D("1.00"),
            exchange_fee=D("0.50"),
            rebate=D("0.25"),
        ),
    )
    r = compute_canonical_loss(legs)
    assert r.ok
    # fill-to-fill = 10*(99-100) = -10; -comms -fees +rebate = -10 -1 -1 -0.50 +0.25 = -12.25
    assert r.realized_net == D("-12.25")
    assert r.round_trip_loss_amount == D("12.25")
    assert r.components["fill_to_fill"] == "-10.00"


def test_inter_leg_unrealized_ignored_by_default() -> None:
    legs = (
        FillLeg(side="BUY", qty=D("5"), price=D("10")),
        FillLeg(side="SELL", qty=D("5"), price=D("9")),
    )
    r = compute_canonical_loss(legs, inter_leg_unrealized=D("-100"))
    assert r.ok
    assert r.realized_net == D("-5.00")
    assert r.components["inter_leg_unrealized_applied"] == "0.00"


def test_partial_fill_residual_tracked() -> None:
    legs = (
        FillLeg(side="BUY", qty=D("10"), price=D("50")),
        FillLeg(side="SELL", qty=D("6"), price=D("49")),
    )
    r = compute_canonical_loss(
        legs, residual=ResidualPosition(qty=D("4"), mark_price=D("48"))
    )
    assert r.ok
    assert r.has_residual_fractional is True
    assert r.residual_qty == D("4.00")
    # matched 6 * (49-50) = -6
    assert r.realized_net == D("-6.00")
    assert r.round_trip_loss_amount == D("6.00")
    # mark residual reported but not in realized
    assert r.residual_mark_pnl == D("-8.00")


def test_corporate_action_refused() -> None:
    legs = (
        FillLeg(side="BUY", qty=D("1"), price=D("10"), corporate_action=True),
        FillLeg(side="SELL", qty=D("1"), price=D("9")),
    )
    r = compute_canonical_loss(legs)
    assert not r.ok
    assert r.refuse_reason is AccountingRefuseReason.CORPORATE_ACTION_PRESENT


def test_model_control_reconciliation_matches() -> None:
    legs = (
        FillLeg(side="BUY", qty=D("2"), price=D("20"), commission=D("0.10")),
        FillLeg(side="SELL", qty=D("2"), price=D("19"), commission=D("0.10")),
    )
    rec = reconcile_model_vs_control(legs)
    assert rec.matched is True
    assert rec.model.round_trip_loss_amount == rec.control.round_trip_loss_amount


def test_empty_legs_refused() -> None:
    r = compute_canonical_loss(())
    assert not r.ok
    assert r.refuse_reason is AccountingRefuseReason.EMPTY_LEGS


def test_no_order_path_imports() -> None:
    assert_no_order_path_imports()
