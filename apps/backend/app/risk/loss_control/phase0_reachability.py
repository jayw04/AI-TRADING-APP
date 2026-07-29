"""ADR-0043 Phase-0 WP2 — reachability / decision adjudicator (offline).

Produces Controlling Design v1.1 verdicts + reason codes from quote evidence.
Displayed-spread inputs are Tier D: never binding. Does not submit orders.
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
    normalize_round_trip_loss_amount,
)

MAX_QUOTE_AGE_S = D("10")

# Legacy alias for callers/tests that still spell the old name.
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
        }


def price_symbol(symbol: str, quote: dict[str, Any] | None, caps: Caps) -> SymbolReachability:
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
) -> Reachability:
    """Adjudicate reachability.

    ``evidence_tier`` defaults to Tier D (displayed spread). Tier D never yields
    ``binding=True``. A Tier-D projection that would have been REACHABLE is reported as
    ``INDETERMINATE`` + ``INSUFFICIENT_EXECUTION_COST``.
    """
    per_symbol = [price_symbol(s, quotes.get(s), caps) for s in symbols]
    priced = [s for s in per_symbol if s.priced]
    remaining = remaining_to_target(day_change, caps.loss_target)
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
        )

    best = max(s.loss_per_round_trip for s in priced if s.loss_per_round_trip is not None)
    best = normalize_round_trip_loss_amount(best)
    max_reachable = (best * caps.max_round_trips).quantize(D("0.01"))
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
        )

    if remaining <= 0:
        return _finalize(
            projected=VERDICT_REACHABLE,
            fresh_ok=fresh_ok,
            tier_d=tier_d,
            evidence_tier=evidence_tier,
            per_symbol=per_symbol,
            day_change=day_change,
            remaining=remaining,
            best=best,
            needed=0,
            max_reachable=max_reachable,
            note="the account is already at or beyond the loss target",
        )

    needed = int((remaining / best).to_integral_value(rounding=ROUND_CEILING))
    within = needed <= caps.max_round_trips
    projected = VERDICT_REACHABLE if within else VERDICT_UNREACHABLE_WITHIN_CAPS
    note = (
        f"{needed} round trip(s) of {caps.max_round_trips} needed at the best fresh spread"
        if within
        else f"{needed} round trips needed but only {caps.max_round_trips} are permitted; "
        "PRESERVE this verdict — do not widen caps, add symbols, or lower the target"
    )
    return _finalize(
        projected=projected,
        fresh_ok=fresh_ok,
        tier_d=tier_d,
        evidence_tier=evidence_tier,
        per_symbol=per_symbol,
        day_change=day_change,
        remaining=remaining,
        best=best,
        needed=needed,
        max_reachable=max_reachable,
        note=note,
    )


def _finalize(
    *,
    projected: str,
    fresh_ok: bool,
    tier_d: bool,
    evidence_tier: str,
    per_symbol: list[SymbolReachability],
    day_change: D | None,
    remaining: D | None,
    best: D,
    needed: int | None,
    max_reachable: D,
    note: str,
) -> Reachability:
    if tier_d:
        # Tier D: never binding. Would-be REACHABLE becomes INDETERMINATE (refuse to trade).
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
            )
        # Diagnostic non-binding UNREACHABLE projection — preserve "do not widen caps".
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
        )

    reason = None if projected == VERDICT_REACHABLE else REASON_ROUND_TRIP_CAP
    return Reachability(
        verdict=projected,
        binding=fresh_ok,
        reason_code=reason,
        evidence_tier=evidence_tier,
        per_symbol=per_symbol,
        day_change=day_change,
        remaining_to_target=remaining,
        best_loss_per_round_trip=best,
        round_trips_needed=needed,
        max_reachable=max_reachable,
        note=note,
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
