"""Synthetic A-share data and fake provider clients. Not market data.

``build_truth`` generates one deterministic ground truth with the cases the rules must handle: a
suspension, a one-price limit-up day, a cash-dividend ex-rights day, a delisting, a new listing, an
ST name under the 5% limit, and an out-of-scope ChiNext name. ``FakeTusharePro`` and
``FakeBaostock`` render that truth in each provider's own shape and units, including the real
differences between them (Baostock lists suspended days, Tushare does not; Tushare rounds volume to
lots and amount to thousand CNY; the two publish back-adjustment factors on different scales).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import pandas as pd

from app.markets.cn_ashare import rules
from app.markets.cn_ashare.symbols import parse

SUSPENDED = "600001.SH"
EX_RIGHTS = "000001.SZ"
LIMIT_UP = "000002.SZ"
DELISTED = "600002.SH"
NEW_LISTING = "603001.SH"
ST_NAME = "002001.SZ"
OUT_OF_SCOPE = "300001.SZ"
SPECIAL = (SUSPENDED, EX_RIGHTS, LIMIT_UP, DELISTED, NEW_LISTING, ST_NAME)
DIVIDEND_CNY = 0.5


@dataclass
class TruthBar:
    open: float
    high: float
    low: float
    close: float
    pre_close: float
    volume: int  # shares
    amount: float  # CNY
    suspended: bool = False


@dataclass
class Truth:
    calendar: list[date]
    all_days: list[date]
    names: dict[str, str]
    list_date: dict[str, date]
    delist_date: dict[str, date | None]
    st: dict[str, bool]
    bars: dict[str, dict[date, TruthBar]] = field(default_factory=dict)
    back_factor: dict[str, dict[date, float]] = field(
        default_factory=dict
    )  # every traded/suspended day
    events: dict[str, list[date]] = field(default_factory=dict)
    special_days: dict[str, date] = field(default_factory=dict)


def _r2(x: float) -> float:
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def build_truth(
    start: date = date(2024, 1, 2),
    end: date = date(2024, 12, 31),
    *,
    n_symbols: int = 20,
    seed: int = 7,
) -> Truth:
    holidays = {date(2024, 2, d) for d in range(12, 17)} | {date(2024, 10, d) for d in range(1, 8)}
    all_days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    cal = [d for d in all_days if d.weekday() < 5 and d not in holidays]
    n_regular = max(0, n_symbols - len(SPECIAL) - 1)
    regular = [f"6000{10 + i:02d}.SH" for i in range(n_regular)]
    symbols = [*SPECIAL, *regular, OUT_OF_SCOPE]
    t = Truth(
        calendar=cal,
        all_days=all_days,
        names={s: f"SYN{i:02d}" + (" ST" if s == ST_NAME else "") for i, s in enumerate(symbols)},
        list_date={s: date(2010, 1, 4) for s in symbols},
        delist_date={s: None for s in symbols},
        st={s: s == ST_NAME for s in symbols},
    )
    q = len(cal) // 4
    t.special_days = {
        "suspend_from": cal[q],
        "ex_rights": cal[q + 10],
        "limit_up": cal[2 * q],
        "delist_last": cal[2 * q + 5],
        "list": cal[q + 3],
    }
    t.list_date[NEW_LISTING] = t.special_days["list"]
    t.delist_date[DELISTED] = t.special_days["delist_last"] + timedelta(days=1)
    suspended = set(cal[q : q + 5])
    for idx, sym in enumerate(symbols):
        rng = random.Random(seed * 1000 + idx)
        prev = 10.0 + idx
        factor = 1.0
        bars: dict[date, TruthBar] = {}
        factors: dict[date, float] = {}
        for day in cal:
            if day < t.list_date[sym]:
                continue
            if t.delist_date[sym] is not None and day >= t.delist_date[sym]:  # type: ignore[operator]
                break
            pre = prev
            if sym == EX_RIGHTS and day == t.special_days["ex_rights"]:
                pre = _r2(prev - DIVIDEND_CNY)  # exchange ex-rights reference price
                factor *= prev / pre
                t.events.setdefault(sym, []).append(day)
            if sym == NEW_LISTING and day == t.list_date[sym]:
                pre = 8.0  # issue price
            factors[day] = factor
            if sym == SUSPENDED and day in suspended:
                bars[day] = TruthBar(pre, pre, pre, pre, pre, 0, 0.0, suspended=True)
                continue
            limit = 0.049 if t.st[sym] else 0.09
            down, up = rules.limit_prices(pre, day, is_st=t.st[sym])
            if sym == LIMIT_UP and day == t.special_days["limit_up"]:
                o = h = lo = c = up
            else:
                c = _r2(pre * (1 + rng.uniform(-limit * 0.6, limit * 0.6)))
                o = _r2(pre * (1 + rng.uniform(-0.01, 0.01)))
                h = _r2(min(max(o, c) * (1 + rng.uniform(0, 0.01)), up))
                lo = _r2(max(min(o, c) * (1 - rng.uniform(0, 0.01)), down))
            vol = rng.randrange(100_000, 1_000_000) * 1 + rng.randrange(0, 100)  # includes odd lots
            amt = round(vol * (h + lo) / 2, 2)
            bars[day] = TruthBar(o, h, lo, c, pre, vol, amt)
            prev = c
        t.bars[sym] = bars
        t.back_factor[sym] = factors
    return t


# --- fake Tushare Pro client ------------------------------------------------------------------------


class FakeTusharePro:
    """Mimics ``tushare.pro_api(token)`` for the four endpoints the adapter calls."""

    def __init__(self, truth: Truth, *, factor_scale: float = 3.25) -> None:
        self.t = truth
        self.scale = factor_scale
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _in(self, d: date, start: str, end: str) -> bool:
        return start <= d.strftime("%Y%m%d") <= end

    def stock_basic(
        self, exchange: str = "", list_status: str = "L", fields: str = ""
    ) -> pd.DataFrame:
        self.calls.append(("stock_basic", {"list_status": list_status}))
        rows = []
        for sym, name in self.t.names.items():
            gone = self.t.delist_date[sym]
            status = "D" if gone else "L"
            if status != list_status:
                continue
            sec = parse(sym)
            rows.append(
                {
                    "ts_code": sym,
                    "symbol": sec.code,
                    "name": name,
                    "exchange": sec.exchange.value,
                    "market": sec.board.value,
                    "list_status": status,
                    "list_date": self.t.list_date[sym].strftime("%Y%m%d"),
                    "delist_date": gone.strftime("%Y%m%d") if gone else None,
                }
            )
        return pd.DataFrame(rows)

    def trade_cal(self, exchange: str, start_date: str, end_date: str) -> pd.DataFrame:
        self.calls.append(("trade_cal", {"start_date": start_date, "end_date": end_date}))
        open_days = set(self.t.calendar)
        rows = [
            {
                "exchange": exchange,
                "cal_date": d.strftime("%Y%m%d"),
                "is_open": 1 if d in open_days else 0,
            }
            for d in self.t.all_days
            if self._in(d, start_date, end_date)
        ]
        return pd.DataFrame(rows)

    def daily(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        self.calls.append(("daily", {"ts_code": ts_code}))
        rows = []
        for d, b in self.t.bars.get(ts_code, {}).items():
            if b.suspended or not self._in(d, start_date, end_date):
                continue  # Tushare's daily endpoint omits suspended days
            rows.append(
                {
                    "ts_code": ts_code,
                    "trade_date": d.strftime("%Y%m%d"),
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "pre_close": b.pre_close,
                    "vol": float(round(b.volume / 100)),  # lots
                    "amount": round(b.amount / 1000, 3),  # thousand CNY
                }
            )
        rows.sort(key=lambda r: str(r["trade_date"]), reverse=True)  # Tushare returns newest first
        return pd.DataFrame(rows)

    def adj_factor(self, ts_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        self.calls.append(("adj_factor", {"ts_code": ts_code}))
        rows = [
            {
                "ts_code": ts_code,
                "trade_date": d.strftime("%Y%m%d"),
                "adj_factor": round(f * self.scale, 6),
            }
            for d, f in self.t.back_factor.get(ts_code, {}).items()
            if self._in(d, start_date, end_date)
        ]
        return pd.DataFrame(rows)


# --- fake Baostock module -----------------------------------------------------------------------------


class _ResultSet:
    def __init__(self, fields: list[str], rows: list[list[str]], error_code: str = "0") -> None:
        self.fields = fields
        self._rows = rows
        self._i = -1
        self.error_code = error_code
        self.error_msg = "" if error_code == "0" else "synthetic error"

    def next(self) -> bool:
        self._i += 1
        return self._i < len(self._rows)

    def get_row_data(self) -> list[str]:
        return self._rows[self._i]


def _s(x: float) -> str:
    return f"{x:.4f}"


class FakeBaostock:
    """Mimics the ``baostock`` module for the four queries the adapter calls."""

    def __init__(self, truth: Truth, *, inject_price_mismatch: bool = False) -> None:
        self.t = truth
        self.inject = inject_price_mismatch
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def login(self) -> _ResultSet:
        return _ResultSet([], [])

    def query_stock_basic(self) -> _ResultSet:
        self.calls.append(("query_stock_basic", {}))
        fields = ["code", "code_name", "ipoDate", "outDate", "type", "status"]
        rows = []
        for sym, name in self.t.names.items():
            gone = self.t.delist_date[sym]
            rows.append(
                [
                    parse(sym).baostock,
                    name,
                    self.t.list_date[sym].isoformat(),
                    gone.isoformat() if gone else "",
                    "1",
                    "0" if gone else "1",
                ]
            )
        rows.append(["sh.000001", "SYN INDEX", "1991-07-15", "", "2", "1"])  # an index, dropped
        return _ResultSet(fields, rows)

    def query_trade_dates(self, start_date: str, end_date: str) -> _ResultSet:
        self.calls.append(("query_trade_dates", {"start_date": start_date, "end_date": end_date}))
        open_days = set(self.t.calendar)
        rows = [
            [d.isoformat(), "1" if d in open_days else "0"]
            for d in self.t.all_days
            if start_date <= d.isoformat() <= end_date
        ]
        return _ResultSet(["calendar_date", "is_trading_day"], rows)

    def query_history_k_data_plus(
        self,
        code: str,
        fields: str,
        start_date: str,
        end_date: str,
        frequency: str,
        adjustflag: str,
    ) -> _ResultSet:
        self.calls.append(("query_history_k_data_plus", {"code": code, "adjustflag": adjustflag}))
        sym = parse(code).symbol
        names = fields.split(",")
        rows = []
        bars = self.t.bars.get(sym, {})
        mismatch_day = sorted(bars)[len(bars) // 2] if bars else None
        for d, b in bars.items():
            if not start_date <= d.isoformat() <= end_date:
                continue
            close = b.close + (
                0.05 if self.inject and d == mismatch_day and not b.suspended else 0.0
            )
            rec = {
                "date": d.isoformat(),
                "code": code,
                "open": _s(b.open),
                "high": _s(b.high),
                "low": _s(b.low),
                "close": _s(close),
                "preclose": _s(b.pre_close),
                "volume": str(b.volume),
                "amount": f"{b.amount:.4f}",
                "adjustflag": adjustflag,
                "tradestatus": "0" if b.suspended else "1",
                "isST": "1" if self.t.st[sym] else "0",
            }
            rows.append([rec[n] for n in names])
        return _ResultSet(names, rows)

    def query_adjust_factor(self, code: str, start_date: str, end_date: str) -> _ResultSet:
        self.calls.append(("query_adjust_factor", {"code": code}))
        sym = parse(code).symbol
        fields = [
            "code",
            "dividOperateDate",
            "foreAdjustFactor",
            "backAdjustFactor",
            "adjustFactor",
        ]
        factors = self.t.back_factor.get(sym, {})
        rows = []
        last = None
        for d in sorted(factors):
            f = factors[d]
            if f != last and start_date <= d.isoformat() <= end_date:
                rows.append([code, d.isoformat(), "", f"{f:.6f}", f"{f:.6f}"])
            last = f
        return _ResultSet(fields, rows)
