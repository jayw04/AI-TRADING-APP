"""Symbols, units, market context and the effective-date-aware rules adapter."""

from __future__ import annotations

from datetime import date, time

import pytest

from app.markets import cn_ashare
from app.markets.cn_ashare import rules
from app.markets.cn_ashare.symbols import (
    Board,
    Exchange,
    SymbolError,
    parse,
    to_baostock,
    to_canonical,
)
from app.markets.context import (
    US_EQUITY,
    Market,
    MarketContext,
    MarketMismatchError,
    PriceBasis,
    require_market,
    require_single_market,
)
from app.markets.source_classification import Presentation, akshare_source, get_source


@pytest.mark.parametrize(
    ("text", "symbol", "board"),
    [
        ("600000.SH", "600000.SH", Board.MAIN),
        ("sh.601318", "601318.SH", Board.MAIN),
        ("000001.sz", "000001.SZ", Board.MAIN),
        ("002594.SZ", "002594.SZ", Board.MAIN),
        ("300750.SZ", "300750.SZ", Board.CHINEXT),
        ("688981.SH", "688981.SH", Board.STAR),
        ("900901.SH", "900901.SH", Board.B_SHARE),
        ("830799.BJ", "830799.BJ", Board.BSE),
    ],
)
def test_symbol_normalization(text: str, symbol: str, board: Board) -> None:
    sec = parse(text)
    assert sec.symbol == symbol and sec.board is board
    assert to_canonical(to_baostock(text)) == symbol


@pytest.mark.parametrize("bad", ["600000", "AAPL", "60000.SH", "sh600000", ""])
def test_bad_symbols_raise(bad: str) -> None:
    with pytest.raises(SymbolError):
        parse(bad)


def test_context_identity_and_market_mixing() -> None:
    ctx = cn_ashare.context(exchange="SSE", provider="baostock", price_basis=PriceBasis.RAW)
    assert (ctx.market, ctx.currency, ctx.timezone) == (Market.CN_ASHARE, "CNY", "Asia/Shanghai")
    assert MarketContext.from_dict(ctx.as_dict()) == ctx
    with pytest.raises(MarketMismatchError):
        require_market(US_EQUITY, Market.CN_ASHARE)
    with pytest.raises(MarketMismatchError):
        require_single_market([ctx, US_EQUITY])
    with pytest.raises(ValueError):
        cn_ashare.context(exchange="", provider="baostock", price_basis=PriceBasis.RAW)


def test_sources_classified_individually() -> None:
    assert get_source("baostock").presentation is Presentation.UNKNOWN
    assert not get_source("tushare_pro").presentable
    assert get_source("cn_synthetic:baostock_shape").presentable
    ak = akshare_source("eastmoney")
    assert ak.source_id == "akshare:eastmoney" and ak.upstream == "eastmoney"
    assert "upstream" in ak.basis  # classified by the upstream, not as one AkShare blanket entry
    assert akshare_source("baostock").access is get_source("baostock").access
    with pytest.raises(ValueError):
        akshare_source(" ")


# --- price limits -----------------------------------------------------------------------------------


def test_st_limit_moves_from_5_to_10_percent_on_2026_07_06() -> None:
    assert rules.limit_pct(date(2026, 7, 3), is_st=True) == 0.05
    assert rules.limit_pct(date(2026, 7, 6), is_st=True) == 0.10
    assert rules.limit_pct(date(2026, 7, 3), is_st=False) == 0.10


def test_unknown_st_flag_refuses_only_while_it_matters() -> None:
    with pytest.raises(rules.RuleNotConfigured):
        rules.limit_pct(date(2024, 5, 6), is_st=None)
    assert rules.limit_pct(date(2026, 8, 3), is_st=None) == 0.10


def test_limit_prices_round_half_up() -> None:
    assert rules.limit_prices(10.0, date(2024, 5, 6), is_st=False) == (9.0, 11.0)
    assert rules.limit_prices(3.35, date(2024, 5, 6), is_st=True) == (3.18, 3.52)  # 3.1825 / 3.5175


def test_dates_before_configured_history_refuse() -> None:
    with pytest.raises(rules.RuleNotConfigured):
        rules.fees(10_000, "buy", date(2015, 7, 31))
    with pytest.raises(rules.RuleNotConfigured):
        rules.limit_pct(date(2010, 1, 4), is_st=False)


def test_out_of_scope_boards_refuse() -> None:
    for sym in ("300750.SZ", "688981.SH", "830799.BJ", "900901.SH"):
        with pytest.raises(rules.RuleNotConfigured):
            rules.require_in_scope(parse(sym))
    rules.require_in_scope(parse("600000.SH"))


# --- sessions and fees -------------------------------------------------------------------------------


def test_sessions_lunch_break_and_sse_closing_call() -> None:
    s = rules.session(Exchange.SSE, date(2018, 8, 17))
    assert s.morning == (time(9, 30), time(11, 30)) and s.afternoon[0] == time(13, 0)
    assert s.closing_call is None
    assert rules.session(Exchange.SSE, date(2018, 8, 20)).closing_call == (
        time(14, 57),
        time(15, 0),
    )
    assert rules.session(Exchange.SZSE, date(2016, 1, 4)).closing_call is not None


def test_fees_follow_effective_dates() -> None:
    before = rules.fees(100_000, "sell", date(2023, 8, 25))
    after = rules.fees(100_000, "sell", date(2023, 8, 28))
    assert before.stamp_duty == pytest.approx(100.0) and after.stamp_duty == pytest.approx(50.0)
    assert before.handling_fee == pytest.approx(4.87) and after.handling_fee == pytest.approx(3.41)
    assert rules.fees(100_000, "sell", date(2022, 4, 28)).transfer_fee == pytest.approx(2.0)
    assert rules.fees(100_000, "sell", date(2022, 4, 29)).transfer_fee == pytest.approx(1.0)
    assert rules.fees(100_000, "buy", date(2024, 1, 2)).stamp_duty == 0.0  # seller only


def test_commission_minimum_is_an_explicit_assumption() -> None:
    small = rules.fees(1_000, "buy", date(2024, 1, 2))
    assert small.commission == 5.0
    custom = rules.fees(
        1_000, "buy", date(2024, 1, 2), rules.CommissionAssumption(rate=0.0001, minimum_cny=0.0)
    )
    assert custom.commission == pytest.approx(0.1)
    with pytest.raises(ValueError):
        rules.fees(1_000, "short", date(2024, 1, 2))


def test_rule_disclosure_lists_every_row_with_a_source() -> None:
    rows = rules.rule_disclosure()
    assert rows and all(r["source"] and r["verified"] for r in rows)
    assert any(r["effective_from"] == "2026-07-06" for r in rows)
