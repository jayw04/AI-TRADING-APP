"""ADR 0043 Phase-0 reachability — can the frozen churn cross the loss target at today's spreads?

The question this answers is narrow: at the CURRENT bid/ask, and under the frozen caps (per-order
notional, max position qty, max round trips), can the driver realise the remaining distance to the
loss target? The answer gates whether a Phase-0 session is worth opening at all.

The answer may be **`BREACH_UNREACHABLE`**, and that is a legitimate, preserved outcome — never a
prompt to widen a cap, add a symbol, or lower the target. Those are the mutations ADR 0043 exists
to make impossible, and a reachability tool that quietly enables them is worse than no tool.

Three rules this module exists to enforce, each from a defect found in the staged predecessor:

* **A verdict is BINDING only if it rests on evidence.** The staged version computed
  `all(fresh for entries that priced)`, which is vacuously true when NOTHING priced — so an
  all-unusable-quote read reported `binding: true` with zero observations behind it.
* **Distance is signed.** It floored a positive day-change to zero, so an account up $500 was
  reported as $3,000 from a −$3,000 target instead of $3,500. That biases the verdict optimistic
  in exactly the direction that starts a session that cannot finish.
* **An unknown day-change is not a zero one.** With no usable baseline the distance is UNKNOWN, and
  the verdict is `INDETERMINATE` — not a number computed from a guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN
from decimal import Decimal as D
from typing import Any

#: Quotes older than this cannot size an order. Ten seconds is the frozen ceiling; a stale spread is
#: a different market's spread.
MAX_QUOTE_AGE_S = D("10")

VERDICT_REACHABLE = "REACHABLE"
VERDICT_UNREACHABLE = "BREACH_UNREACHABLE"
VERDICT_INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True)
class SymbolReachability:
    """One instrument's contribution, and — when it cannot contribute — why not."""

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


@dataclass(frozen=True)
class Caps:
    """The frozen driver caps. Inputs, never tuned to reach a verdict."""

    loss_target: D
    max_round_trips: int
    max_setup_notional: D
    max_position_qty: D
    max_quote_age_s: D = MAX_QUOTE_AGE_S


def price_symbol(symbol: str, quote: dict[str, Any] | None, caps: Caps) -> SymbolReachability:
    """What one symbol can contribute per round trip, or the reason it can contribute nothing.

    A round trip is BUY then SELL, so the deterministic cost is the spread times the shares that fit
    inside the per-order notional cap. Anything that makes the spread untrustworthy — no quote, a
    missing side, a crossed book, a stale timestamp — makes the symbol unusable rather than
    optimistically priced.
    """
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

    shares = min(caps.max_position_qty, (caps.max_setup_notional / ask).to_integral_value(ROUND_DOWN))
    if shares <= 0:
        return _unusable(base, "notional cap admits zero shares at this ask")
    return SymbolReachability(
        symbol=symbol,
        bid=bid,
        ask=ask,
        quote_age_s=age,
        fresh=True,
        sized_shares=shares,
        loss_per_round_trip=((ask - bid) * shares).quantize(D("0.01")),
    )


def remaining_to_target(day_change: D | None, loss_target: D) -> D | None:
    """How much further the account must fall to reach `-loss_target`.

    Signed, deliberately: an account UP $500 is $3,500 from a −$3,000 target, not $3,000. The
    predecessor floored the positive case to zero and understated the work by exactly the gain.
    ``None`` in, ``None`` out — an unknown day-change yields an unknown distance.
    """
    if day_change is None:
        return None
    return loss_target + day_change


def assess(
    *,
    day_change: D | None,
    quotes: dict[str, dict[str, Any] | None],
    symbols: list[str],
    caps: Caps,
) -> Reachability:
    """The verdict, and whether it is BINDING.

    BINDING requires actual evidence: at least one symbol priced from a fresh two-sided quote, and
    every symbol that priced doing so from a fresh quote. A read where nothing priced is
    ``INDETERMINATE`` and never binding — the specific failure the predecessor's vacuous ``all()``
    produced, which would have let an all-stale after-hours read masquerade as a session-grade
    verdict.
    """
    per_symbol = [price_symbol(s, quotes.get(s), caps) for s in symbols]
    priced = [s for s in per_symbol if s.priced]
    remaining = remaining_to_target(day_change, caps.loss_target)

    if not priced:
        return Reachability(
            verdict=VERDICT_INDETERMINATE,
            binding=False,
            per_symbol=per_symbol,
            day_change=day_change,
            remaining_to_target=remaining,
            best_loss_per_round_trip=None,
            round_trips_needed=None,
            max_reachable=None,
            note="no symbol produced a usable fresh two-sided quote; nothing was measured",
        )

    best = max(s.loss_per_round_trip for s in priced if s.loss_per_round_trip is not None)
    max_reachable = (best * caps.max_round_trips).quantize(D("0.01"))

    if remaining is None:
        return Reachability(
            verdict=VERDICT_INDETERMINATE,
            binding=False,
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
        return Reachability(
            verdict=VERDICT_REACHABLE,
            binding=all(s.fresh for s in priced),
            per_symbol=per_symbol,
            day_change=day_change,
            remaining_to_target=remaining,
            best_loss_per_round_trip=best,
            round_trips_needed=0,
            max_reachable=max_reachable,
            note="the account is already at or beyond the loss target",
        )

    needed = int((remaining / best).to_integral_value(rounding="ROUND_CEILING"))
    within = needed <= caps.max_round_trips
    return Reachability(
        verdict=VERDICT_REACHABLE if within else VERDICT_UNREACHABLE,
        binding=all(s.fresh for s in priced),
        per_symbol=per_symbol,
        day_change=day_change,
        remaining_to_target=remaining,
        best_loss_per_round_trip=best,
        round_trips_needed=needed,
        max_reachable=max_reachable,
        note=(
            f"{needed} round trip(s) of {caps.max_round_trips} needed at the best fresh spread"
            if within
            else f"{needed} round trips needed but only {caps.max_round_trips} are permitted; "
            "PRESERVE this verdict — do not widen caps, add symbols, or lower the target"
        ),
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
    "assess",
    "price_symbol",
    "remaining_to_target",
]
