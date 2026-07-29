"""ADR-0043 Phase-0 WP2 — reachability / decision adjudicator (offline).

Produces Controlling Design v1.1 verdicts + reason codes from quote evidence.
Displayed-spread inputs are Tier D: never binding.

Binding REACHABLE (Tier A–C) requires a frozen ``ExecutionPlan`` (or exact single
symbol+quantity derived from one). Multi-symbol max-over-symbols evaluation is
diagnostic only (``binding=False``) — CORR-02.

Does not submit orders.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_DOWN
from decimal import Decimal as D
from typing import Any

from app.risk.loss_control.phase0_contracts import (
    REASON_INSUFFICIENT_EXECUTION_COST,
    REASON_ROUND_TRIP_CAP,
    REASON_STALE_EVIDENCE,
    TIER_D_DISPLAYED_SPREAD,
    VERDICT_INDETERMINATE,
    VERDICT_REACHABLE,
    VERDICT_UNREACHABLE_WITHIN_CAPS,
    ExecutionPlan,
    compute_plan_hash,
    normalize_round_trip_loss_amount,
)

MAX_QUOTE_AGE_S = D("10")
VERDICT_UNREACHABLE = VERDICT_UNREACHABLE_WITHIN_CAPS


@dataclass(frozen=True)
class Caps:
    loss_target: D
    max_round_trips: int
    max_setup_notional: D
    max_position_qty: D
    max_quote_age_s: D = MAX_QUOTE_AGE_S


@dataclass(frozen=True)
class SymbolReachability:
    symbol: str
    bid: D | None = None
    ask: D | None = None
    quote_age_s: D | None = None
    fresh: bool = False
    sized_shares: D | None = None
    loss_per_round_trip: D | None = None
    unusable_reason: str | None = None

    @property
    def priced(self) -> bool:
        return self.loss_per_round_trip is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "bid": str(self.bid) if self.bid is not None else None,
            "ask": str(self.ask) if self.ask is not None else None,
            "quote_age_s": str(self.quote_age_s) if self.quote_age_s is not None else None,
            "fresh": self.fresh,
            "sized_shares": str(self.sized_shares) if self.sized_shares is not None else None,
            "loss_per_round_trip": (
                str(self.loss_per_round_trip) if self.loss_per_round_trip is not None else None
            ),
            "unusable_reason": self.unusable_reason,
        }


@dataclass(frozen=True)
class Reachability:
    verdict: str
    binding: bool
    reason_code: str | None
    evidence_tier: str
    per_symbol: list[SymbolReachability]
    day_change: D | None
    remaining_to_target: D | None
    best_loss_per_round_trip: D | None
    round_trips_needed: int | None
    max_reachable: D | None
    note: str
    selected_symbol: str | None = None
    modeled_quantity: D | None = None
    plan_id: str | None = None
    plan_hash: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "binding": self.binding,
            "reason_code": self.reason_code,
            "evidence_tier": self.evidence_tier,
            "per_symbol": [s.as_dict() for s in self.per_symbol],
            "day_change": str(self.day_change) if self.day_change is not None else None,
            "remaining_to_target": (
                str(self.remaining_to_target) if self.remaining_to_target is not None else None
            ),
            "best_loss_per_round_trip": (
                str(self.best_loss_per_round_trip)
                if self.best_loss_per_round_trip is not None
                else None
            ),
            "round_trips_needed": self.round_trips_needed,
            "max_reachable": str(self.max_reachable) if self.max_reachable is not None else None,
            "note": self.note,
            "selected_symbol": self.selected_symbol,
            "modeled_quantity": str(self.modeled_quantity)
            if self.modeled_quantity is not None
            else None,
            "plan_id": self.plan_id,
            "plan_hash": self.plan_hash,
        }


def price_symbol(
    symbol: str,
    quote: dict[str, Any] | None,
    caps: Caps,
    *,
    frozen_quantity: D | None = None,
) -> SymbolReachability:
    if not quote:
        return SymbolReachability(symbol=symbol, unusable_reason="no governed quote")

    bid, ask, age = _dec(quote.get("bid")), _dec(quote.get("ask")), _dec(quote.get("age_s"))
    fresh = age is not None and D(0) <= age <= caps.max_quote_age_s
    base = SymbolReachability(symbol=symbol, bid=bid, ask=ask, quote_age_s=age, fresh=fresh)

    if age is None:
        return _unusable(base, "quote carries no age; freshness cannot be established")
    if not fresh:
        return _unusable(base, f"quote is {age}s old (ceiling {caps.max_quote_age_s}s)")
    if bid is None or ask is None:
        return _unusable(base, "quote is one-sided (no bid or no ask)")
    if bid <= 0 or ask <= 0:
        return _unusable(base, "non-positive bid or ask")
    if bid > ask:
        return _unusable(base, "crossed book")

    shares = min(
        caps.max_position_qty,
        (caps.max_setup_notional / ask).to_integral_value(ROUND_DOWN),
    )
    if frozen_quantity is not None:
        if frozen_quantity <= 0:
            return _unusable(base, "frozen quantity is non-positive")
        # Modeled qty must equal or be conservatively below the plan quantity.
        shares = min(shares, frozen_quantity.to_integral_value(ROUND_DOWN))
    if shares <= 0:
        return _unusable(base, "notional cap admits zero shares at this ask")
    loss = normalize_round_trip_loss_amount(((ask - bid) * shares).quantize(D("0.01")))
    return SymbolReachability(
        symbol=symbol,
        bid=bid,
        ask=ask,
        quote_age_s=age,
        fresh=True,
        sized_shares=shares,
        loss_per_round_trip=loss,
    )


def remaining_to_target(day_change: D | None, loss_target: D) -> D | None:
    if day_change is None:
        return None
    return loss_target + day_change


def assess(
    *,
    day_change: D | None,
    quotes: dict[str, dict[str, Any] | None],
    symbols: list[str],
    caps: Caps,
    evidence_tier: str = TIER_D_DISPLAYED_SPREAD,
    execution_plan: ExecutionPlan | None = None,
) -> Reachability:
    """Adjudicate reachability.

    Tier D never yields ``binding=True``. Tier A–C binding requires ``execution_plan``
    and evaluates only that plan's symbol/quantity — never max-over-symbols.
    """
    plan_id = plan_hash = selected = None
    modeled_qty: D | None = None
    frozen_qty: D | None = None
    eval_symbols = list(symbols)
    eval_caps = caps
    force_diagnostic = False

    if execution_plan is not None:
        plan_id = execution_plan.plan_id
        plan_hash = compute_plan_hash(execution_plan)
        selected = execution_plan.symbol
        frozen_qty = D(execution_plan.quantity)
        eval_symbols = [execution_plan.symbol]
        eval_caps = Caps(
            loss_target=D(execution_plan.loss_target),
            max_round_trips=execution_plan.max_round_trips,
            max_setup_notional=D(execution_plan.max_setup_notional),
            max_position_qty=D(execution_plan.max_position_qty),
            max_quote_age_s=caps.max_quote_age_s,
        )
        # Reject free-list alternatives: only the plan symbol is assessed for binding.
        if symbols and set(symbols) != {execution_plan.symbol}:
            force_diagnostic = False  # still assess plan symbol only
    elif len(symbols) != 1:
        # Multi-symbol without a frozen plan: diagnostic only (CORR-02).
        force_diagnostic = True

    per_symbol = [
        price_symbol(s, quotes.get(s), eval_caps, frozen_quantity=frozen_qty)
        for s in eval_symbols
    ]
    priced = [s for s in per_symbol if s.priced]
    remaining = remaining_to_target(day_change, eval_caps.loss_target)
    tier_d = evidence_tier == TIER_D_DISPLAYED_SPREAD

    if not priced:
        return Reachability(
            verdict=VERDICT_INDETERMINATE,
            binding=False,
            reason_code=REASON_STALE_EVIDENCE,
            evidence_tier=evidence_tier,
            per_symbol=per_symbol,
            day_change=day_change,
            remaining_to_target=remaining,
            best_loss_per_round_trip=None,
            round_trips_needed=None,
            max_reachable=None,
            note="no symbol produced a usable fresh two-sided quote; nothing was measured",
            selected_symbol=selected,
            modeled_quantity=None,
            plan_id=plan_id,
            plan_hash=plan_hash,
        )

    # With a plan, there is exactly one priced symbol; without, diagnostic may max.
    if execution_plan is not None:
        chosen = priced[0]
        best = normalize_round_trip_loss_amount(chosen.loss_per_round_trip or D("0"))
        selected = chosen.symbol
        modeled_qty = chosen.sized_shares
        # Conformance: modeled symbol == plan symbol; qty <= plan qty.
        if chosen.symbol != execution_plan.symbol:
            return Reachability(
                verdict=VERDICT_INDETERMINATE,
                binding=False,
                reason_code=REASON_INSUFFICIENT_EXECUTION_COST,
                evidence_tier=evidence_tier,
                per_symbol=per_symbol,
                day_change=day_change,
                remaining_to_target=remaining,
                best_loss_per_round_trip=best,
                round_trips_needed=None,
                max_reachable=None,
                note="modeled symbol does not match ExecutionPlan.symbol",
                selected_symbol=chosen.symbol,
                modeled_quantity=modeled_qty,
                plan_id=plan_id,
                plan_hash=plan_hash,
            )
        if modeled_qty is not None and modeled_qty > D(execution_plan.quantity):
            return Reachability(
                verdict=VERDICT_INDETERMINATE,
                binding=False,
                reason_code=REASON_INSUFFICIENT_EXECUTION_COST,
                evidence_tier=evidence_tier,
                per_symbol=per_symbol,
                day_change=day_change,
                remaining_to_target=remaining,
                best_loss_per_round_trip=best,
                round_trips_needed=None,
                max_reachable=None,
                note="modeled quantity exceeds frozen plan quantity",
                selected_symbol=selected,
                modeled_quantity=modeled_qty,
                plan_id=plan_id,
                plan_hash=plan_hash,
            )
    else:
        chosen = max(
            priced,
            key=lambda s: s.loss_per_round_trip or D("0"),
        )
        best = normalize_round_trip_loss_amount(chosen.loss_per_round_trip or D("0"))
        selected = chosen.symbol
        modeled_qty = chosen.sized_shares

    max_reachable = (best * eval_caps.max_round_trips).quantize(D("0.01"))
    fresh_ok = all(s.fresh for s in priced)

    if remaining is None:
        return Reachability(
            verdict=VERDICT_INDETERMINATE,
            binding=False,
            reason_code=REASON_INSUFFICIENT_EXECUTION_COST,
            evidence_tier=evidence_tier,
            per_symbol=per_symbol,
            day_change=None,
            remaining_to_target=None,
            best_loss_per_round_trip=best,
            round_trips_needed=None,
            max_reachable=max_reachable,
            note="spreads priced, but the day-change baseline is unknown so the distance to the "
            "target cannot be computed",
            selected_symbol=selected,
            modeled_quantity=modeled_qty,
            plan_id=plan_id,
            plan_hash=plan_hash,
        )

    if remaining <= 0:
        return _finalize(
            projected=VERDICT_REACHABLE,
            fresh_ok=fresh_ok,
            tier_d=tier_d,
            force_diagnostic=force_diagnostic or execution_plan is None,
            evidence_tier=evidence_tier,
            per_symbol=per_symbol,
            day_change=day_change,
            remaining=remaining,
            best=best,
            needed=0,
            max_reachable=max_reachable,
            note="the account is already at or beyond the loss target",
            selected_symbol=selected,
            modeled_quantity=modeled_qty,
            plan_id=plan_id,
            plan_hash=plan_hash,
            execution_plan=execution_plan,
        )

    needed = int((remaining / best).to_integral_value(rounding=ROUND_CEILING))
    within = needed <= eval_caps.max_round_trips
    projected = VERDICT_REACHABLE if within else VERDICT_UNREACHABLE_WITHIN_CAPS
    note = (
        f"{needed} round trip(s) of {eval_caps.max_round_trips} needed at the frozen plan spread"
        if within and execution_plan is not None
        else (
            f"{needed} round trip(s) of {eval_caps.max_round_trips} needed at the best fresh spread"
            if within
            else f"{needed} round trips needed but only {eval_caps.max_round_trips} are permitted; "
            "PRESERVE this verdict — do not widen caps, add symbols, or lower the target"
        )
    )
    return _finalize(
        projected=projected,
        fresh_ok=fresh_ok,
        tier_d=tier_d,
        force_diagnostic=force_diagnostic or (execution_plan is None and not tier_d),
        evidence_tier=evidence_tier,
        per_symbol=per_symbol,
        day_change=day_change,
        remaining=remaining,
        best=best,
        needed=needed,
        max_reachable=max_reachable,
        note=note,
        selected_symbol=selected,
        modeled_quantity=modeled_qty,
        plan_id=plan_id,
        plan_hash=plan_hash,
        execution_plan=execution_plan,
    )


def _finalize(
    *,
    projected: str,
    fresh_ok: bool,
    tier_d: bool,
    force_diagnostic: bool,
    evidence_tier: str,
    per_symbol: list[SymbolReachability],
    day_change: D | None,
    remaining: D | None,
    best: D,
    needed: int | None,
    max_reachable: D,
    note: str,
    selected_symbol: str | None,
    modeled_quantity: D | None,
    plan_id: str | None,
    plan_hash: str | None,
    execution_plan: ExecutionPlan | None,
) -> Reachability:
    # Binding only when: not Tier D, not forced diagnostic, plan frozen with id+hash.
    can_bind = (
        not tier_d
        and not force_diagnostic
        and execution_plan is not None
        and plan_id is not None
        and plan_hash is not None
        and fresh_ok
    )

    if tier_d:
        if projected == VERDICT_REACHABLE:
            return Reachability(
                verdict=VERDICT_INDETERMINATE,
                binding=False,
                reason_code=REASON_INSUFFICIENT_EXECUTION_COST,
                evidence_tier=evidence_tier,
                per_symbol=per_symbol,
                day_change=day_change,
                remaining_to_target=remaining,
                best_loss_per_round_trip=best,
                round_trips_needed=needed,
                max_reachable=max_reachable,
                note=note
                + " [Tier D displayed-spread: non-binding; cannot authorize REACHABLE]",
                selected_symbol=selected_symbol,
                modeled_quantity=modeled_quantity,
                plan_id=plan_id,
                plan_hash=plan_hash,
            )
        return Reachability(
            verdict=VERDICT_UNREACHABLE_WITHIN_CAPS,
            binding=False,
            reason_code=REASON_ROUND_TRIP_CAP,
            evidence_tier=evidence_tier,
            per_symbol=per_symbol,
            day_change=day_change,
            remaining_to_target=remaining,
            best_loss_per_round_trip=best,
            round_trips_needed=needed,
            max_reachable=max_reachable,
            note=note + " [Tier D diagnostic projection; non-binding]",
            selected_symbol=selected_symbol,
            modeled_quantity=modeled_quantity,
            plan_id=plan_id,
            plan_hash=plan_hash,
        )

    if force_diagnostic or not can_bind:
        # Multi-symbol / missing plan: keep projected label for diagnostics but never bind.
        return Reachability(
            verdict=projected if projected != VERDICT_REACHABLE else VERDICT_INDETERMINATE,
            binding=False,
            reason_code=(
                REASON_INSUFFICIENT_EXECUTION_COST
                if projected == VERDICT_REACHABLE
                else REASON_ROUND_TRIP_CAP
            ),
            evidence_tier=evidence_tier,
            per_symbol=per_symbol,
            day_change=day_change,
            remaining_to_target=remaining,
            best_loss_per_round_trip=best,
            round_trips_needed=needed,
            max_reachable=max_reachable,
            note=note
            + " [diagnostic: binding requires frozen ExecutionPlan plan_id/plan_hash]",
            selected_symbol=selected_symbol,
            modeled_quantity=modeled_quantity,
            plan_id=plan_id,
            plan_hash=plan_hash,
        )

    reason = None if projected == VERDICT_REACHABLE else REASON_ROUND_TRIP_CAP
    return Reachability(
        verdict=projected,
        binding=True,
        reason_code=reason,
        evidence_tier=evidence_tier,
        per_symbol=per_symbol,
        day_change=day_change,
        remaining_to_target=remaining,
        best_loss_per_round_trip=best,
        round_trips_needed=needed,
        max_reachable=max_reachable,
        note=note,
        selected_symbol=selected_symbol,
        modeled_quantity=modeled_quantity,
        plan_id=plan_id,
        plan_hash=plan_hash,
    )


def _unusable(base: SymbolReachability, reason: str) -> SymbolReachability:
    return SymbolReachability(
        symbol=base.symbol,
        bid=base.bid,
        ask=base.ask,
        quote_age_s=base.quote_age_s,
        fresh=base.fresh,
        unusable_reason=reason,
    )


def _dec(value: Any) -> D | None:
    if value is None or value == "":
        return None
    try:
        return D(str(value))
    except Exception:
        return None


__all__ = [
    "Caps",
    "MAX_QUOTE_AGE_S",
    "Reachability",
    "SymbolReachability",
    "VERDICT_INDETERMINATE",
    "VERDICT_REACHABLE",
    "VERDICT_UNREACHABLE",
    "VERDICT_UNREACHABLE_WITHIN_CAPS",
    "assess",
    "price_symbol",
    "remaining_to_target",
]
