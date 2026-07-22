"""ADR 0042 — the shared risk-effect classifier.

An action is classified by its **projected effect on the account's risk state**, never by its
BUY/SELL verb, never by strategy identity, never by human-vs-automated origin.

A sell can open or enlarge a short. A buy can close one. The verb is not a classification.

This module is PURE: it takes an :class:`AccountSnapshot` and a :class:`ProposedAction` and
returns a :class:`RiskEffectDecision`. It performs no I/O, so the same snapshot + proposal +
policy version always yields the same classification (ADR 0042 release gate #8). Fetching a
causally-complete snapshot is ``app/risk/account_snapshot.py``; persisting the decision is the
risk-decision ledger.

Both the daily-loss gate (engine step 9) and the circuit-breaker gate (step 13) call THIS —
they do not implement similar logic separately. Separate near-duplicate logic is exactly how
the gross-exposure gate got the reducing-order exemption (ADR 0038) while the loss gates did
not, which is the defect this ADR exists to close.

v1 SCOPE IS LONG-ONLY (ADR 0042 § scope). Buy-to-cover on a short book is *conceptually*
risk-reducing and the types below express it, but it is REJECTED until short handling is
separately implemented and approved. The rule is about risk effect; the v1 implementation is
long-only; those are different statements and this file keeps them apart.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from app.db.enums import OrderSide

ZERO = Decimal(0)

# Bumped whenever the classification RULES change. The ledger records it, so a past decision can
# be replayed against the policy that actually made it.
RISK_POLICY_VERSION = "0042.1"


class ActionType(StrEnum):
    """ADR 0042 § B — cancellation is not an order and must not travel the order path."""

    ORDER_SUBMIT = "ORDER_SUBMIT"
    ORDER_CANCEL = "ORDER_CANCEL"
    ORDER_REPLACE = "ORDER_REPLACE"


class RiskEffect(StrEnum):
    RISK_REDUCING = "RISK_REDUCING"
    RISK_INCREASING = "RISK_INCREASING"
    RISK_NEUTRAL = "RISK_NEUTRAL"
    INDETERMINATE = "INDETERMINATE"


class Decision(StrEnum):
    ALLOW = "ALLOW"
    REJECT = "REJECT"
    FAIL_CLOSED = "FAIL_CLOSED"


class RiskEffectReason(StrEnum):
    """Why the classifier decided what it decided. Persisted in the ledger."""

    VERIFIED_REDUCTION = "VERIFIED_REDUCTION"
    INCREASES_INSTRUMENT_EXPOSURE = "INCREASES_INSTRUMENT_EXPOSURE"
    CROSSES_ZERO = "CROSSES_ZERO"
    INCREASES_GROSS_EXPOSURE = "INCREASES_GROSS_EXPOSURE"
    INCREASES_LEVERAGE = "INCREASES_LEVERAGE"
    OPENS_NEW_POSITION = "OPENS_NEW_POSITION"
    EXCEEDS_REDUCIBLE_QUANTITY = "EXCEEDS_REDUCIBLE_QUANTITY"
    # Distinct from the static check above: the quantity WAS available when this decision was
    # classified, and a CONCURRENT decision took it first. The durable capacity claim refused
    # (ADR 0042 § D). This is a determinate rejection, never a fail-closed.
    EXCEEDS_REDUCIBLE_CAPACITY = "EXCEEDS_REDUCIBLE_CAPACITY"
    SHORT_NOT_SUPPORTED_V1 = "SHORT_NOT_SUPPORTED_V1"
    NO_POSITION = "NO_POSITION"
    NON_POSITIVE_QUANTITY = "NON_POSITIVE_QUANTITY"
    # cancellation (§ B)
    CANCEL_REMOVES_PROTECTIVE_REDUCTION = "CANCEL_REMOVES_PROTECTIVE_REDUCTION"
    CANCEL_REMOVES_RISK_INCREASING_ORDER = "CANCEL_REMOVES_RISK_INCREASING_ORDER"
    # indeterminate (§ A)
    SNAPSHOT_STALE = "SNAPSHOT_STALE"
    SNAPSHOT_INCOMPLETE = "SNAPSHOT_INCOMPLETE"
    UNRESOLVED_PARTIAL_FILL = "UNRESOLVED_PARTIAL_FILL"
    UNKNOWN_ACTION = "UNKNOWN_ACTION"
    NO_PRICE = "NO_PRICE"


# ---------------------------------------------------------------------------------------
# Snapshot (ADR 0042 § A)
# ---------------------------------------------------------------------------------------
@dataclass(frozen=True)
class SnapshotPosition:
    symbol: str
    qty: Decimal  # SIGNED: >0 long, <0 short
    price: Decimal


@dataclass(frozen=True)
class SnapshotOpenOrder:
    order_id: str
    symbol: str
    side: OrderSide
    remaining_qty: Decimal
    reduces_position: bool  # a SELL against a long / a BUY against a short
    has_unresolved_partial_fill: bool = False


@dataclass(frozen=True)
class AccountSnapshot:
    """A CAUSALLY COMPLETE view of the account, fetched for THIS decision (ADR 0042 § A).

    There is no "N seconds old" allowance. Staleness is not a tunable — the requirement is
    causal completeness: the snapshot must be at or beyond every broker event we have already
    observed locally. A snapshot that is merely *recent* but behind a fill we have already seen
    is not a stale account; it is a DIFFERENT account.
    """

    account_id: int
    positions: dict[str, SnapshotPosition]
    open_orders: list[SnapshotOpenOrder]
    cash: Decimal
    equity: Decimal
    # Broker cursor / sequence / reconciliation stamp — the causality anchor.
    broker_cursor: str | None
    # Highest broker event we have already observed locally. The snapshot must be >= this.
    observed_cursor: str | None = None
    # Set False by the fetcher when the broker read failed or reconciliation was incomplete.
    complete: bool = True
    # Quantities already promised to other in-flight reducing decisions (§ D).
    reserved_reducing_qty: dict[str, Decimal] = field(default_factory=dict)
    # Of `reserved_reducing_qty`, the quantity already FILLED and therefore already
    # reflected in `positions` — held reservations keep their full original quantity until
    # their order goes terminal, so this is what stops a partial fill being charged twice.
    reserved_filled_qty: dict[str, Decimal] = field(default_factory=dict)

    def gross_exposure(self) -> Decimal:
        return sum((abs(p.qty) * p.price for p in self.positions.values()), ZERO)

    def state_hash(self) -> str:
        """Identity of the state this decision was made against. Recorded in the ledger so an
        approval cannot be silently applied to a different account state."""
        payload = {
            "account_id": self.account_id,
            "cursor": self.broker_cursor,
            "positions": sorted(
                (p.symbol, str(p.qty), str(p.price)) for p in self.positions.values()
            ),
            "open_orders": sorted(
                (o.order_id, o.symbol, str(o.side), str(o.remaining_qty))
                for o in self.open_orders
            ),
            "cash": str(self.cash),
            "reserved": sorted((k, str(v)) for k, v in self.reserved_reducing_qty.items()),
            "reserved_filled": sorted(
                (k, str(v)) for k, v in self.reserved_filled_qty.items()
            ),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()

    def is_causally_complete(self) -> tuple[bool, RiskEffectReason | None]:
        if not self.complete:
            return False, RiskEffectReason.SNAPSHOT_INCOMPLETE
        if self.broker_cursor is None:
            return False, RiskEffectReason.SNAPSHOT_INCOMPLETE
        # Must be AT OR BEYOND every broker event already seen locally.
        if self.observed_cursor is not None and self.broker_cursor < self.observed_cursor:
            return False, RiskEffectReason.SNAPSHOT_STALE
        if any(o.has_unresolved_partial_fill for o in self.open_orders):
            return False, RiskEffectReason.UNRESOLVED_PARTIAL_FILL
        return True, None


@dataclass(frozen=True)
class ProposedAction:
    action: ActionType
    symbol: str
    side: OrderSide | None = None      # None for a cancel
    qty: Decimal | None = None         # None for a cancel
    price: Decimal | None = None
    target_order_id: str | None = None  # for ORDER_CANCEL / ORDER_REPLACE


@dataclass(frozen=True)
class RiskEffectDecision:
    risk_effect: RiskEffect
    decision: Decision
    reasons: list[RiskEffectReason]
    policy_version: str
    before_state_hash: str
    projected_after_state_hash: str | None
    position_qty_before: Decimal
    position_qty_after: Decimal | None
    gross_exposure_before: Decimal
    gross_exposure_after: Decimal | None
    available_reducible_qty: Decimal | None = None

    @property
    def is_verified_reduction(self) -> bool:
        return (
            self.risk_effect is RiskEffect.RISK_REDUCING
            and self.decision is Decision.ALLOW
        )


# ---------------------------------------------------------------------------------------
# Reducible capacity (ADR 0042 § D)
# ---------------------------------------------------------------------------------------
def claimable_reducible_quantity(snap: AccountSnapshot, symbol: str) -> Decimal:
    """The long, net of reducing sells in flight that are NOT already covered by a reservation.

    This is the capacity BASIS for the § D accumulator guard, which compares
    ``reserved_qty + qty <= reducible_capacity_qty``. Because the accumulator already carries
    every HELD reservation on the left-hand side, this side must NOT subtract them again.

        current_long − max(0, open_reducing_sell_qty − reserved_reducing_qty)

    Every reduction this system approves creates a reservation AND (once submitted) appears in
    the broker's open orders, so those two quantities overlap. Subtracting both is a double
    count that shrinks capacity below the truth and refuses legitimate de-risking — the very
    failure ADR 0042 exists to prevent. Subtracting the EXCESS of in-flight over reserved keeps
    the guard honest about sells this system did not reserve (a manual order placed straight at
    the broker), while never charging our own reductions twice.
    """
    pos = snap.positions.get(symbol.upper())
    current = pos.qty if pos else ZERO
    if current <= ZERO:
        return ZERO

    in_flight = sum(
        (
            o.remaining_qty
            for o in snap.open_orders
            if o.symbol.upper() == symbol.upper()
            and o.side == OrderSide.SELL
            and o.reduces_position
        ),
        ZERO,
    )
    reserved_total = snap.reserved_reducing_qty.get(symbol.upper(), ZERO)
    # The part of our held reservations the BROKER POSITION HAS ALREADY ABSORBED. A reservation
    # is held at its full original quantity until its order goes terminal, so a partial fill is
    # charged twice: once by the shrunken position, once by the still-full reservation. Adding
    # it back charges it exactly once. It must come from observed fills — an aggregate guess
    # (reserved − in_flight) cannot tell a FILLED reservation from a NOT-YET-SUBMITTED one, and
    # adding back the latter would over-permit.
    reserved_filled = snap.reserved_filled_qty.get(symbol.upper(), ZERO)
    reserved_pending = max(ZERO, reserved_total - reserved_filled)
    # Broker-open reducing quantity that no reservation of ours accounts for — a sell placed
    # straight at the broker. Charged in full; only OUR overlap is forgiven.
    unreserved_in_flight = max(ZERO, in_flight - reserved_pending)
    return max(ZERO, current + reserved_filled - unreserved_in_flight)


def available_reducible_quantity(snap: AccountSnapshot, symbol: str) -> Decimal:
    """How much of this long may STILL be promised to a reduction.

    Two concurrent sells can each look safe against the same long position and TOGETHER cross
    through zero, creating a short — the exact failure the zero-crossing rule exists to
    prevent, reached by a route no single-order check can see. So the capacity is net of
    everything already in flight or already promised.

        current_long
      - filled_but_not_reconciled_reductions   (carried in the snapshot's position qty)
      - reserved_reducing_qty
      - open_reducing_sell_qty NOT covered by a reservation

    The last two terms are deliberately not simply added: a reduction this system approved is
    counted once as a reservation, even after it reaches the broker and also shows up as an
    open order. See ``claimable_reducible_quantity`` — this is that basis minus the
    reservations, which are the caller's own share of the promised total.
    """
    reserved = snap.reserved_reducing_qty.get(symbol.upper(), ZERO)
    return max(ZERO, claimable_reducible_quantity(snap, symbol) - reserved)


# ---------------------------------------------------------------------------------------
# The classifier
# ---------------------------------------------------------------------------------------
# The emit callback that `classify()` threads into its helpers. Naming the type lets the
# helper signatures be CHECKED, instead of silenced with a blanket `no-untyped-def` ignore
# that had quietly gone stale and was failing mypy on this branch before it was touched.
_Emit = Callable[..., RiskEffectDecision]


def classify(snap: AccountSnapshot, action: ProposedAction) -> RiskEffectDecision:
    """Classify ``action`` by its projected effect on ``snap``.

    Every unclear path lands on INDETERMINATE → FAIL_CLOSED. Not "probably fine".
    """
    before_hash = snap.state_hash()
    sym = action.symbol.upper()
    pos = snap.positions.get(sym)
    qty_before = pos.qty if pos else ZERO
    gross_before = snap.gross_exposure()

    def _out(
        effect: RiskEffect,
        decision: Decision,
        reasons: list[RiskEffectReason],
        qty_after: Decimal | None = None,
        gross_after: Decimal | None = None,
        reducible: Decimal | None = None,
        after_hash: str | None = None,
    ) -> RiskEffectDecision:
        return RiskEffectDecision(
            risk_effect=effect,
            decision=decision,
            reasons=reasons,
            policy_version=RISK_POLICY_VERSION,
            before_state_hash=before_hash,
            projected_after_state_hash=after_hash,
            position_qty_before=qty_before,
            position_qty_after=qty_after,
            gross_exposure_before=gross_before,
            gross_exposure_after=gross_after,
            available_reducible_qty=reducible,
        )

    # --- § A: causal completeness. Checked FIRST — no classification is meaningful against a
    # state we cannot trust.
    ok, why = snap.is_causally_complete()
    if not ok:
        return _out(RiskEffect.INDETERMINATE, Decision.FAIL_CLOSED, [why])  # type: ignore[list-item]

    if action.action is ActionType.ORDER_CANCEL:
        return _classify_cancel(snap, action, _out)

    if action.action is not ActionType.ORDER_SUBMIT:
        # ORDER_REPLACE is a cancel+submit whose net effect we do not yet model.
        return _out(
            RiskEffect.INDETERMINATE, Decision.FAIL_CLOSED, [RiskEffectReason.UNKNOWN_ACTION]
        )

    # --- ORDER_SUBMIT ------------------------------------------------------------------
    if action.qty is None or action.qty <= ZERO:
        return _out(
            RiskEffect.INDETERMINATE,
            Decision.FAIL_CLOSED,
            [RiskEffectReason.NON_POSITIVE_QUANTITY],
        )

    # A price is only needed to QUANTIFY an exposure change, never to CLASSIFY one. A MARKET
    # order carries no limit_price, so requiring a price up-front made every market order on an
    # un-held symbol collapse to INDETERMINATE/NO_PRICE — including a buy that is plainly
    # RISK_INCREASING and a naked sell that is plainly NO_POSITION.
    #
    # The outcome was safe (fail-closed), but the RECORDED REASON was wrong, and the reason IS
    # the evidence. A ledger that says "I could not price it" when the truth is "you do not own
    # it" makes the next investigation harder, not easier — the exact failure this ADR exists to
    # end. Caught by the 2026-07-13 canary, which is what a canary is for.
    #
    # So: classify from POSITION and SIDE first. Demand a price only on the path that actually
    # needs one — a permitted reduction, where the held position always carries its own mark.
    price = action.price or (pos.price if pos else None)

    # A BUY can only add long exposure on a long-only book. (Buy-to-cover a short is
    # conceptually reducing — and explicitly out of v1 scope.) No price required to know that.
    if action.side == OrderSide.BUY:
        if qty_before < ZERO:
            return _out(
                RiskEffect.RISK_REDUCING,  # true in principle...
                Decision.REJECT,           # ...but v1 does not support shorts. Blocked.
                [RiskEffectReason.SHORT_NOT_SUPPORTED_V1],
            )
        reasons = [
            RiskEffectReason.OPENS_NEW_POSITION
            if qty_before == ZERO
            else RiskEffectReason.INCREASES_INSTRUMENT_EXPOSURE
        ]
        qty_after = qty_before + action.qty
        return _out(
            RiskEffect.RISK_INCREASING,
            Decision.REJECT,
            reasons,
            qty_after=qty_after,
            gross_after=(gross_before + action.qty * price) if price else None,
        )

    # --- a SELL. The verb tells us nothing; the projected state does. -------------------
    if qty_before <= ZERO:
        # Selling something we do not own OPENS a short. Never reducing.
        return _out(
            RiskEffect.RISK_INCREASING,
            Decision.REJECT,
            [
                RiskEffectReason.NO_POSITION
                if qty_before == ZERO
                else RiskEffectReason.INCREASES_INSTRUMENT_EXPOSURE
            ],
            qty_after=qty_before - action.qty,
            gross_after=(gross_before + action.qty * price) if price else None,
        )

    qty_after = qty_before - action.qty

    # Rule 2: must not cross through zero and establish opposite exposure.
    if qty_after < ZERO:
        return _out(
            RiskEffect.RISK_INCREASING,
            Decision.REJECT,
            [RiskEffectReason.CROSSES_ZERO],
            qty_after=qty_after,
        )

    # § D: must fit within what is still reducible after in-flight + reserved.
    reducible = available_reducible_quantity(snap, sym)
    if action.qty > reducible:
        return _out(
            RiskEffect.INDETERMINATE,
            Decision.FAIL_CLOSED,
            [RiskEffectReason.EXCEEDS_REDUCIBLE_QUANTITY],
            qty_after=qty_after,
            reducible=reducible,
        )

    # HERE a price is genuinely required: permitting a reduction means PROVING gross exposure
    # falls, and that is a quantity. A held position always carries its own mark, so a missing
    # price at this point means the snapshot is not trustworthy — INDETERMINATE, not "probably
    # fine".
    if price is None or price <= ZERO:
        return _out(
            RiskEffect.INDETERMINATE,
            Decision.FAIL_CLOSED,
            [RiskEffectReason.NO_PRICE],
            qty_after=qty_after,
            reducible=reducible,
        )

    # Rules 1 + 3: instrument exposure falls, gross exposure falls.
    gross_after = gross_before - action.qty * price
    if gross_after >= gross_before:
        return _out(
            RiskEffect.RISK_INCREASING,
            Decision.REJECT,
            [RiskEffectReason.INCREASES_GROSS_EXPOSURE],
            qty_after=qty_after,
            gross_after=gross_after,
            reducible=reducible,
        )

    # Projected state, for the after-hash.
    after_positions = dict(snap.positions)
    if qty_after == ZERO:
        after_positions.pop(sym, None)
    else:
        after_positions[sym] = SnapshotPosition(sym, qty_after, price)
    after_hash = AccountSnapshot(
        account_id=snap.account_id,
        positions=after_positions,
        open_orders=snap.open_orders,
        cash=snap.cash + action.qty * price,
        equity=snap.equity,
        broker_cursor=snap.broker_cursor,
        observed_cursor=snap.observed_cursor,
        reserved_reducing_qty=snap.reserved_reducing_qty,
    ).state_hash()

    return _out(
        RiskEffect.RISK_REDUCING,
        Decision.ALLOW,
        [RiskEffectReason.VERIFIED_REDUCTION],
        qty_after=qty_after,
        gross_after=gross_after,
        reducible=reducible,
        after_hash=after_hash,
    )


def _classify_cancel(
    snap: AccountSnapshot, action: ProposedAction, _out: _Emit
) -> RiskEffectDecision:
    """ADR 0042 § B — a cancellation is NOT automatically reducing.

    Cancelling a pending *protective* reduction (a sell-to-close) REMOVES a de-risking action.
    That is precisely the move that traps risk on the book — the thing this whole ADR exists to
    stop — so it is risk-INCREASING and stays blocked while locked.
    """
    target = next(
        (o for o in snap.open_orders if o.order_id == action.target_order_id), None
    )
    if target is None:
        return _out(
            RiskEffect.INDETERMINATE,
            Decision.FAIL_CLOSED,
            [RiskEffectReason.SNAPSHOT_INCOMPLETE],
        )
    if target.has_unresolved_partial_fill:
        return _out(
            RiskEffect.INDETERMINATE,
            Decision.FAIL_CLOSED,
            [RiskEffectReason.UNRESOLVED_PARTIAL_FILL],
        )

    if target.reduces_position:
        # Cancelling a protective reduction raises worst-case exposure back up.
        return _out(
            RiskEffect.RISK_INCREASING,
            Decision.REJECT,
            [RiskEffectReason.CANCEL_REMOVES_PROTECTIVE_REDUCTION],
        )

    # The open order would have ADDED exposure; removing it weakly reduces worst-case exposure.
    return _out(
        RiskEffect.RISK_REDUCING,
        Decision.ALLOW,
        [RiskEffectReason.CANCEL_REMOVES_RISK_INCREASING_ORDER],
    )
