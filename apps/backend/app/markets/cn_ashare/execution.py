"""Simulated daily-bar execution constraints for A-share research. Not an order path.

An order decided on day D (using data dated <= D) is filled at the **open of the next trading day**,
or refused with a reason. Nothing is filled on a day the stock did not trade, and no price is
invented for an unavailable day.

Refusal reasons:

* ``SUSPENDED``: no bar, a non-trading status, or zero volume.
* ``LIMIT_UP_NO_BUY`` / ``LIMIT_DOWN_NO_SELL``: the open is at or beyond the limit, or the whole day
  traded at one limit price. A daily bar cannot prove a queue position at the limit, so these refuse.
* ``T_PLUS_1``: shares bought on day T are sellable from the next trading day.
* ``LOT_SIZE``: buys in multiples of 100; a sell must be a multiple of 100 or the whole odd remainder.
* ``NEW_LISTING_WINDOW``: the first trading days after listing (a disclosed scope choice).
* ``RULE_NOT_CONFIGURED``: date, board or ST status outside the configured rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.markets.cn_ashare import rules
from app.markets.cn_ashare.symbols import parse


@dataclass(frozen=True)
class DailyBar:
    symbol: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    pre_close: float
    volume_shares: float
    amount_cny: float
    trade_status: int = 1  # 1 = traded normally, 0 = suspended
    is_st: bool | None = None

    @property
    def tradable(self) -> bool:
        return self.trade_status == 1 and self.volume_shares > 0


@dataclass(frozen=True)
class Order:
    symbol: str
    side: str  # "buy" | "sell"
    shares: int
    decision_day: date


@dataclass(frozen=True)
class Fill:
    order: Order
    fill_day: date
    price: float
    notional_cny: float
    fees: rules.FeeBreakdown


@dataclass(frozen=True)
class Refusal:
    order: Order
    attempted_day: date | None
    reason: str
    detail: str = ""


@dataclass
class Position:
    symbol: str
    lots: list[tuple[date, int]] = field(default_factory=list)  # (acquired day, shares)

    @property
    def shares(self) -> int:
        return sum(n for _, n in self.lots)

    def sellable_on(self, day: date) -> int:
        return sum(n for acquired, n in self.lots if acquired < day)


def _lot_ok(order: Order, held: int) -> bool:
    if order.shares <= 0:
        return False
    if order.side == "buy":
        return order.shares % rules.LOT_SIZE == 0
    return order.shares % rules.LOT_SIZE == 0 or order.shares == held


def execute(
    order: Order,
    next_bar: DailyBar | None,
    next_day: date | None,
    *,
    position: Position | None,
    trading_days_since_listing: int | None,
    commission: rules.CommissionAssumption | None = None,
) -> Fill | Refusal:
    """Fill ``order`` at ``next_bar.open`` or refuse it. ``next_day`` is the next trading day on the
    exchange calendar; ``next_bar`` is the stock's bar on that day, or None if it has none."""
    sec = parse(order.symbol)
    try:
        rules.require_in_scope(sec)
    except rules.RuleNotConfigured as exc:
        return Refusal(order, next_day, "RULE_NOT_CONFIGURED", str(exc))
    if next_day is None:
        return Refusal(order, None, "SUSPENDED", "no later trading day in the data")
    held = position.shares if position else 0
    if not _lot_ok(order, held):
        return Refusal(order, next_day, "LOT_SIZE", f"{order.shares} shares, {held} held")
    if next_bar is None or not next_bar.tradable:
        return Refusal(order, next_day, "SUSPENDED", "no traded bar on the execution day")
    if (
        trading_days_since_listing is not None
        and trading_days_since_listing < rules.NEW_LISTING_EXCLUDED_DAYS
    ):
        return Refusal(
            order, next_day, "NEW_LISTING_WINDOW", f"listing day +{trading_days_since_listing}"
        )
    try:
        down, up = rules.limit_prices(next_bar.pre_close, next_day, is_st=next_bar.is_st)
    except rules.RuleNotConfigured as exc:
        return Refusal(order, next_day, "RULE_NOT_CONFIGURED", str(exc))
    one_price = next_bar.high == next_bar.low
    if order.side == "buy":
        if next_bar.open >= up or (one_price and next_bar.high >= up):
            return Refusal(order, next_day, "LIMIT_UP_NO_BUY", f"open {next_bar.open} limit {up}")
    else:
        if position is None or position.sellable_on(next_day) < order.shares:
            return Refusal(order, next_day, "T_PLUS_1", "shares not yet sellable or not held")
        if next_bar.open <= down or (one_price and next_bar.low <= down):
            return Refusal(
                order, next_day, "LIMIT_DOWN_NO_SELL", f"open {next_bar.open} limit {down}"
            )
    notional = next_bar.open * order.shares
    try:
        fee = rules.fees(notional, order.side, next_day, commission)
    except rules.RuleNotConfigured as exc:
        return Refusal(order, next_day, "RULE_NOT_CONFIGURED", str(exc))
    return Fill(order, next_day, next_bar.open, notional, fee)


def apply_fill(positions: dict[str, Position], fill: Fill) -> None:
    sym = fill.order.symbol
    if fill.order.side == "buy":
        positions.setdefault(sym, Position(sym)).lots.append((fill.fill_day, fill.order.shares))
        return
    pos = positions[sym]
    remaining = fill.order.shares
    kept: list[tuple[date, int]] = []
    for acquired, n in sorted(pos.lots):
        take = min(n, remaining)
        remaining -= take
        if n - take:
            kept.append((acquired, n - take))
    pos.lots = kept
    if not pos.lots:
        del positions[sym]
