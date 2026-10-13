"""Synthetic tests of A-share execution constraints: next-open fills or a refusal with a reason."""

from __future__ import annotations

from datetime import date

import pytest

from app.markets.cn_ashare import rules
from app.markets.cn_ashare.execution import (
    DailyBar,
    Fill,
    Order,
    Position,
    Refusal,
    apply_fill,
    execute,
)

D0, D1, D2 = date(2024, 5, 6), date(2024, 5, 7), date(2024, 5, 8)
SYM = "600000.SH"


def bar(day: date = D1, *, o: float = 10.1, h: float = 10.3, lo: float = 9.9, c: float = 10.2,
        pre: float = 10.0, vol: float = 1e6, status: int = 1, st: bool | None = False) -> DailyBar:  # fmt: skip
    return DailyBar(SYM, day, o, h, lo, c, pre, vol, vol * c, status, st)


def run(
    order: Order, b: DailyBar | None, *, pos: Position | None = None, age: int | None = None
) -> Fill | Refusal:
    return execute(
        order, b, b.trade_date if b else D1, position=pos, trading_days_since_listing=age
    )


def test_buy_fills_at_next_open_with_dated_fees() -> None:
    res = run(Order(SYM, "buy", 1000, D0), bar())
    assert isinstance(res, Fill)
    assert res.fill_day == D1 and res.price == 10.1 and res.notional_cny == pytest.approx(10_100)
    assert res.fees.stamp_duty == 0.0 and res.fees.commission == 5.0


def test_t_plus_1_shares_bought_today_are_not_sellable_today() -> None:
    pos = Position(SYM, [(D1, 1000)])
    assert pos.sellable_on(D1) == 0 and pos.sellable_on(D2) == 1000
    res = run(Order(SYM, "sell", 1000, D0), bar(D1), pos=pos)
    assert isinstance(res, Refusal) and res.reason == "T_PLUS_1"
    assert isinstance(run(Order(SYM, "sell", 1000, D1), bar(D2), pos=pos), Fill)


@pytest.mark.parametrize("shares", [150, 0, -100])
def test_buys_must_be_whole_lots(shares: int) -> None:
    res = run(Order(SYM, "buy", shares, D0), bar())
    assert isinstance(res, Refusal) and res.reason == "LOT_SIZE"


def test_an_odd_lot_remainder_may_be_sold_whole() -> None:
    pos = Position(SYM, [(D0, 150)])
    assert isinstance(run(Order(SYM, "sell", 150, D0), bar(), pos=pos), Fill)
    res = run(Order(SYM, "sell", 50, D0), bar(), pos=pos)
    assert isinstance(res, Refusal) and res.reason == "LOT_SIZE"


def test_suspended_or_missing_bar_never_fills() -> None:
    for b in (None, bar(status=0), bar(vol=0)):
        res = run(Order(SYM, "buy", 100, D0), b)
        assert isinstance(res, Refusal) and res.reason == "SUSPENDED"


def test_limit_up_open_or_one_price_day_refuses_buy() -> None:
    res = run(Order(SYM, "buy", 100, D0), bar(o=11.0, h=11.0, lo=10.5, c=11.0))
    assert isinstance(res, Refusal) and res.reason == "LIMIT_UP_NO_BUY"
    res = run(Order(SYM, "buy", 100, D0), bar(o=11.0, h=11.0, lo=11.0, c=11.0))
    assert isinstance(res, Refusal) and res.reason == "LIMIT_UP_NO_BUY"


def test_limit_down_refuses_sell() -> None:
    pos = Position(SYM, [(D0, 100)])
    res = run(Order(SYM, "sell", 100, D0), bar(o=9.0, h=9.0, lo=9.0, c=9.0), pos=pos)
    assert isinstance(res, Refusal) and res.reason == "LIMIT_DOWN_NO_SELL"


def test_st_limit_is_5_percent_before_2026_07_06() -> None:
    res = run(Order(SYM, "buy", 100, D0), bar(o=10.5, h=10.5, lo=10.2, c=10.5, st=True))
    assert isinstance(res, Refusal) and res.reason == "LIMIT_UP_NO_BUY"
    res = run(Order(SYM, "buy", 100, D0), bar(st=None))  # unknown ST flag before the unification
    assert isinstance(res, Refusal) and res.reason == "RULE_NOT_CONFIGURED"


def test_new_listing_window_refuses() -> None:
    res = run(Order(SYM, "buy", 100, D0), bar(), age=rules.NEW_LISTING_EXCLUDED_DAYS - 1)
    assert isinstance(res, Refusal) and res.reason == "NEW_LISTING_WINDOW"
    assert isinstance(
        run(Order(SYM, "buy", 100, D0), bar(), age=rules.NEW_LISTING_EXCLUDED_DAYS), Fill
    )


def test_out_of_scope_board_refuses_without_approximation() -> None:
    order = Order("300750.SZ", "buy", 100, D0)
    res = execute(order, bar(), D1, position=None, trading_days_since_listing=None)
    assert isinstance(res, Refusal) and res.reason == "RULE_NOT_CONFIGURED"


def test_apply_fill_removes_oldest_lots_first() -> None:
    positions = {SYM: Position(SYM, [(D0, 200), (D1, 100)])}
    fill = run(Order(SYM, "sell", 200, D1), bar(D2), pos=positions[SYM])
    assert isinstance(fill, Fill)
    apply_fill(positions, fill)
    assert positions[SYM].lots == [(D1, 100)]
