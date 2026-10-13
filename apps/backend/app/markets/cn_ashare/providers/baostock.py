"""Baostock adapter (cross-check provider; free, anonymous login).

Endpoints: ``query_stock_basic`` (type 1 = stock; status 0 = delisted), ``query_trade_dates``,
``query_history_k_data_plus`` with ``adjustflag="3"`` (unadjusted; volume in shares, amount in CNY;
includes suspended days with ``tradestatus=0`` and an ``isST`` flag) and ``query_adjust_factor``
(``backAdjustFactor`` published only on the dates it changes).

Every Baostock value arrives as a string; an empty string means missing.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.markets.cn_ashare import units
from app.markets.cn_ashare.providers.base import Fetched, ProviderError, parse_date, parse_float
from app.markets.cn_ashare.symbols import SymbolError, parse

_FMT = units.BAOSTOCK.date_format
DAILY_FIELDS = "date,code,open,high,low,close,preclose,volume,amount,adjustflag,tradestatus,isST"


def _rows(rs: Any) -> list[dict[str, Any]]:
    if str(getattr(rs, "error_code", "")) != "0":
        raise ProviderError(
            f"baostock error {getattr(rs, 'error_code', '?')}: {getattr(rs, 'error_msg', '')}"
        )
    out = []
    while rs.next():
        out.append(dict(zip(rs.fields, rs.get_row_data(), strict=True)))
    return out


def _d(day: date) -> str:
    return day.strftime(_FMT)


def _flag(v: Any) -> bool | None:
    s = str(v).strip() if v is not None else ""
    return None if s == "" else s == "1"


class BaostockProvider:
    source_id = "baostock"
    units = units.BAOSTOCK

    def __init__(self, client: Any, *, source_id: str | None = None) -> None:
        """``source_id`` overrides the provenance label, e.g. ``cn_synthetic:baostock_shape``."""
        self._bs = client
        if source_id is not None:
            self.source_id = source_id

    @classmethod
    def from_anonymous_login(cls) -> BaostockProvider:
        import baostock  # optional dependency, imported only when Baostock is actually used

        lg = baostock.login()
        if str(lg.error_code) != "0":
            raise ProviderError(f"baostock login failed: {lg.error_msg}")
        return cls(baostock)

    def securities(self) -> Fetched:
        raw = _rows(self._bs.query_stock_basic())
        rows = []
        for r in raw:
            if str(r.get("type")) != "1":  # 1 = stock; indices, funds and bonds are dropped
                continue
            try:
                sec = parse(str(r["code"]))
            except SymbolError:
                continue
            rows.append(
                {
                    "symbol": sec.symbol,
                    "name": str(r.get("code_name") or ""),
                    "exchange": sec.exchange.value,
                    "board": sec.board.value,
                    "list_date": parse_date(r.get("ipoDate"), _FMT),
                    "delist_date": parse_date(r.get("outDate"), _FMT),
                    "status": "L" if str(r.get("status")) == "1" else "D",
                }
            )
        return Fetched("securities", self.source_id, {"type": "1"}, raw, rows, self.units)

    def trade_calendar(self, start: date, end: date) -> Fetched:
        params = {"start_date": _d(start), "end_date": _d(end)}
        raw = _rows(self._bs.query_trade_dates(**params))
        rows = [
            {
                "exchange": "SSE",
                "cal_date": parse_date(r["calendar_date"], _FMT),
                "is_open": str(r["is_trading_day"]) == "1",
            }
            for r in raw
        ]
        return Fetched("trade_calendar", self.source_id, params, raw, rows, self.units)

    def daily(self, symbol: str, start: date, end: date) -> Fetched:
        sec = parse(symbol)
        params = {
            "code": sec.baostock,
            "fields": DAILY_FIELDS,
            "start_date": _d(start),
            "end_date": _d(end),
            "frequency": "d",
            "adjustflag": "3",
        }
        raw = _rows(self._bs.query_history_k_data_plus(**params))
        rows = []
        for r in raw:
            if str(r.get("adjustflag", "3")) != "3":
                raise ProviderError("baostock returned an adjusted series where raw was requested")
            vol = parse_float(r.get("volume"))
            amt = parse_float(r.get("amount"))
            rows.append(
                {
                    "symbol": sec.symbol,
                    "trade_date": parse_date(r["date"], _FMT),
                    "open": parse_float(r.get("open")),
                    "high": parse_float(r.get("high")),
                    "low": parse_float(r.get("low")),
                    "close": parse_float(r.get("close")),
                    "pre_close": parse_float(r.get("preclose")),
                    "volume_shares": None if vol is None else vol * self.units.volume_to_shares,
                    "amount_cny": None if amt is None else amt * self.units.amount_to_cny,
                    "trade_status": 1 if str(r.get("tradestatus")) == "1" else 0,
                    "is_st": _flag(r.get("isST")),
                }
            )
        return Fetched("daily", self.source_id, params, raw, rows, self.units)

    def adj_factors(self, symbol: str, start: date, end: date) -> Fetched:
        sec = parse(symbol)
        params = {"code": sec.baostock, "start_date": _d(start), "end_date": _d(end)}
        raw = _rows(self._bs.query_adjust_factor(**params))
        rows = [
            {
                "symbol": sec.symbol,
                "trade_date": parse_date(r["dividOperateDate"], _FMT),
                "factor": parse_float(r.get("backAdjustFactor")),
                "factor_kind": "hfq_step",
            }
            for r in raw
        ]
        return Fetched("adj_factor", self.source_id, params, raw, rows, self.units)
