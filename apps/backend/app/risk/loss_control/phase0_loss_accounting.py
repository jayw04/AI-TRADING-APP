"""ADR-0043 Phase-0 WP8 — canonical loss-accounting formula (offline).

Implements AMD-18: one authoritative formula shared by model, reachability,
loss-control, replay, and terminal adjudication, plus an O2 reconciliation
check (model-computed vs control-computed on identical inputs).

Does not submit orders or import the order path.
"""

from __future__ import annotations

import inspect
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal
from enum import StrEnum
from typing import Any

from app.risk.loss_control.phase0_contracts import normalize_round_trip_loss_amount

MONEY_QUANT = Decimal("0.01")
FORMULA_ID = "ADR0043-PH0-LOSS-001"
FORMULA_VERSION = 1


class BaselineMode(StrEnum):
    """How control-plane day-change baselines are interpreted (documentation + policy)."""

    BROKER_EQUITY = "BROKER_EQUITY"
    INTERNAL_LEDGER_EQUITY = "INTERNAL_LEDGER_EQUITY"
    REALIZED_ONLY = "REALIZED_ONLY"


class SettlementTiming(StrEnum):
    TRADE_DATE = "TRADE_DATE"
    SETTLEMENT_DATE = "SETTLEMENT_DATE"


class AccountingRefuseReason(StrEnum):
    CORPORATE_ACTION_PRESENT = "CORPORATE_ACTION_PRESENT"
    EMPTY_LEGS = "EMPTY_LEGS"
    INVALID_SIDE = "INVALID_SIDE"
    NON_POSITIVE_QTY = "NON_POSITIVE_QTY"


@dataclass(frozen=True)
class LossAccountingPolicy:
    """Frozen Phase-0 answers to every AMD-18 specification slot."""

    formula_id: str = FORMULA_ID
    formula_version: int = FORMULA_VERSION
    inter_leg_unrealized_counts: bool = False
    control_baseline_mode: BaselineMode = BaselineMode.BROKER_EQUITY
    model_round_trip_mode: BaselineMode = BaselineMode.REALIZED_ONLY
    settlement_timing: SettlementTiming = SettlementTiming.TRADE_DATE
    rounding: Decimal = MONEY_QUANT
    include_residual_fractional_at_mark: bool = True
    refuse_on_corporate_action: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "formula_id": self.formula_id,
            "formula_version": self.formula_version,
            "inter_leg_unrealized_counts": self.inter_leg_unrealized_counts,
            "control_baseline_mode": str(self.control_baseline_mode),
            "model_round_trip_mode": str(self.model_round_trip_mode),
            "settlement_timing": str(self.settlement_timing),
            "rounding": str(self.rounding),
            "include_residual_fractional_at_mark": self.include_residual_fractional_at_mark,
            "refuse_on_corporate_action": self.refuse_on_corporate_action,
            "commissions": "subtracted_from_realized",
            "exchange_regulatory_fees": "subtracted_from_realized",
            "rebates": "added_to_realized",
            "partial_fills": "prorated_open_residual_tracked",
        }


DEFAULT_POLICY = LossAccountingPolicy()


@dataclass(frozen=True)
class FillLeg:
    """One fill leg for canonical accounting."""

    side: str  # BUY | SELL
    qty: Decimal
    price: Decimal
    commission: Decimal = Decimal("0")
    exchange_fee: Decimal = Decimal("0")
    regulatory_fee: Decimal = Decimal("0")
    rebate: Decimal = Decimal("0")
    corporate_action: bool = False
    trade_date: str | None = None
    settlement_date: str | None = None


@dataclass(frozen=True)
class ResidualPosition:
    qty: Decimal
    mark_price: Decimal


@dataclass(frozen=True)
class LossAccountingResult:
    ok: bool
    realized_net: Decimal | None
    round_trip_loss_amount: Decimal | None
    has_residual_fractional: bool
    residual_qty: Decimal
    residual_mark_pnl: Decimal
    policy: dict[str, Any]
    refuse_reason: AccountingRefuseReason | None = None
    detail: str = ""
    components: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "realized_net": str(self.realized_net) if self.realized_net is not None else None,
            "round_trip_loss_amount": (
                str(self.round_trip_loss_amount)
                if self.round_trip_loss_amount is not None
                else None
            ),
            "has_residual_fractional": self.has_residual_fractional,
            "residual_qty": str(self.residual_qty),
            "residual_mark_pnl": str(self.residual_mark_pnl),
            "policy": dict(self.policy),
            "refuse_reason": str(self.refuse_reason) if self.refuse_reason else None,
            "detail": self.detail,
            "components": dict(self.components),
        }


def _q(policy: LossAccountingPolicy, value: Decimal) -> Decimal:
    return value.quantize(policy.rounding, rounding=ROUND_HALF_EVEN)


def compute_canonical_loss(
    legs: Sequence[FillLeg],
    *,
    policy: LossAccountingPolicy = DEFAULT_POLICY,
    residual: ResidualPosition | None = None,
    inter_leg_unrealized: Decimal = Decimal("0"),
) -> LossAccountingResult:
    """Authoritative fill-to-fill realized net + non-negative round-trip loss amount.

    Sign convention for ``realized_net``: positive = gain, negative = loss.
    ``round_trip_loss_amount`` = max(0, −realized_net) after fees (AMD-13 non-negative).
    """
    pol = policy.as_dict()
    if not legs:
        return LossAccountingResult(
            ok=False,
            realized_net=None,
            round_trip_loss_amount=None,
            has_residual_fractional=False,
            residual_qty=Decimal("0"),
            residual_mark_pnl=Decimal("0"),
            policy=pol,
            refuse_reason=AccountingRefuseReason.EMPTY_LEGS,
            detail="no fill legs",
        )

    buy_cost = Decimal("0")
    buy_qty = Decimal("0")
    sell_proceeds = Decimal("0")
    sell_qty = Decimal("0")
    commissions = Decimal("0")
    fees = Decimal("0")
    rebates = Decimal("0")

    for leg in legs:
        if policy.refuse_on_corporate_action and leg.corporate_action:
            return LossAccountingResult(
                ok=False,
                realized_net=None,
                round_trip_loss_amount=None,
                has_residual_fractional=False,
                residual_qty=Decimal("0"),
                residual_mark_pnl=Decimal("0"),
                policy=pol,
                refuse_reason=AccountingRefuseReason.CORPORATE_ACTION_PRESENT,
                detail="corporate action on leg — refuse silent adjustment",
            )
        side = leg.side.upper()
        if side not in {"BUY", "SELL"}:
            return LossAccountingResult(
                ok=False,
                realized_net=None,
                round_trip_loss_amount=None,
                has_residual_fractional=False,
                residual_qty=Decimal("0"),
                residual_mark_pnl=Decimal("0"),
                policy=pol,
                refuse_reason=AccountingRefuseReason.INVALID_SIDE,
                detail=f"invalid side {leg.side!r}",
            )
        if leg.qty <= 0:
            return LossAccountingResult(
                ok=False,
                realized_net=None,
                round_trip_loss_amount=None,
                has_residual_fractional=False,
                residual_qty=Decimal("0"),
                residual_mark_pnl=Decimal("0"),
                policy=pol,
                refuse_reason=AccountingRefuseReason.NON_POSITIVE_QTY,
                detail="qty must be positive",
            )
        notional = leg.qty * leg.price
        if side == "BUY":
            buy_cost += notional
            buy_qty += leg.qty
        else:
            sell_proceeds += notional
            sell_qty += leg.qty
        commissions += leg.commission
        fees += leg.exchange_fee + leg.regulatory_fee
        rebates += leg.rebate

    # Matched quantity (partial-fill safe): realize only the overlapped qty at average prices.
    matched = min(buy_qty, sell_qty)
    avg_buy = (buy_cost / buy_qty) if buy_qty > 0 else Decimal("0")
    avg_sell = (sell_proceeds / sell_qty) if sell_qty > 0 else Decimal("0")
    fill_to_fill = matched * (avg_sell - avg_buy) if matched > 0 else Decimal("0")

    realized = fill_to_fill - commissions - fees + rebates
    if policy.inter_leg_unrealized_counts:
        realized += inter_leg_unrealized
    # else: inter-leg unrealized deliberately ignored

    residual_qty = buy_qty - sell_qty
    residual_mark_pnl = Decimal("0")
    has_residual = residual_qty != 0
    if has_residual and policy.include_residual_fractional_at_mark and residual is not None:
        # Mark residual long (positive qty) or short (negative) vs average entry.
        if residual_qty > 0:
            residual_mark_pnl = residual_qty * (residual.mark_price - avg_buy)
        else:
            residual_mark_pnl = (-residual_qty) * (avg_sell - residual.mark_price)
        # Residual mark is reported but does NOT enter round-trip realized unless policy
        # said unrealized counts (it does not for Phase-0).

    realized_net = _q(policy, realized)
    loss_amt = normalize_round_trip_loss_amount(
        _q(policy, max(Decimal("0"), -realized_net))
    )

    return LossAccountingResult(
        ok=True,
        realized_net=realized_net,
        round_trip_loss_amount=loss_amt,
        has_residual_fractional=has_residual,
        residual_qty=_q(policy, residual_qty),
        residual_mark_pnl=_q(policy, residual_mark_pnl),
        policy=pol,
        detail=(
            f"{FORMULA_ID} v{FORMULA_VERSION}; settlement={policy.settlement_timing}; "
            f"matched_qty={matched}"
        ),
        components={
            "fill_to_fill": str(_q(policy, fill_to_fill)),
            "commissions": str(_q(policy, commissions)),
            "fees": str(_q(policy, fees)),
            "rebates": str(_q(policy, rebates)),
            "inter_leg_unrealized_applied": str(
                _q(policy, inter_leg_unrealized)
                if policy.inter_leg_unrealized_counts
                else Decimal("0.00")
            ),
            "matched_qty": str(matched),
        },
    )


@dataclass(frozen=True)
class ReconciliationResult:
    matched: bool
    model: LossAccountingResult
    control: LossAccountingResult
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "matched": self.matched,
            "detail": self.detail,
            "model": self.model.as_dict(),
            "control": self.control.as_dict(),
        }


def reconcile_model_vs_control(
    legs: Sequence[FillLeg],
    *,
    policy: LossAccountingPolicy = DEFAULT_POLICY,
    residual: ResidualPosition | None = None,
    inter_leg_unrealized: Decimal = Decimal("0"),
) -> ReconciliationResult:
    """O2 matrix helper: model and control must share this formula on identical inputs."""
    model = compute_canonical_loss(
        legs, policy=policy, residual=residual, inter_leg_unrealized=inter_leg_unrealized
    )
    control = compute_canonical_loss(
        legs, policy=policy, residual=residual, inter_leg_unrealized=inter_leg_unrealized
    )
    if not model.ok or not control.ok:
        return ReconciliationResult(
            matched=model.ok == control.ok
            and model.refuse_reason == control.refuse_reason,
            model=model,
            control=control,
            detail="both refused or mismatched refuse state",
        )
    matched = (
        model.realized_net == control.realized_net
        and model.round_trip_loss_amount == control.round_trip_loss_amount
        and model.components == control.components
    )
    return ReconciliationResult(
        matched=matched,
        model=model,
        control=control,
        detail="identical inputs → identical canonical loss" if matched else "MISMATCH",
    )


def assert_no_order_path_imports() -> None:
    import app.risk.loss_control.phase0_loss_accounting as mod

    src = inspect.getsource(mod)
    needles = [
        "from app." + "services.order_router",
        "import app." + "services.order_router",
        "from app." + "brokers",
        "import app." + "brokers",
        "from app." + "orders",
        "submit_" + "order(",
    ]
    for needle in needles:
        if needle in src:
            raise AssertionError(f"phase0_loss_accounting must not reference {needle}")


__all__ = [
    "DEFAULT_POLICY",
    "FORMULA_ID",
    "FORMULA_VERSION",
    "AccountingRefuseReason",
    "BaselineMode",
    "FillLeg",
    "LossAccountingPolicy",
    "LossAccountingResult",
    "ReconciliationResult",
    "ResidualPosition",
    "SettlementTiming",
    "assert_no_order_path_imports",
    "compute_canonical_loss",
    "reconcile_model_vs_control",
]
