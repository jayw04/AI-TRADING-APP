"""Tushare Pro adapter (intended primary daily provider).

Endpoints: ``stock_basic`` (list_status L/D/P, so delisted names are included), ``trade_cal``,
``daily`` (unadjusted OHLC, ``vol`` in lots, ``amount`` in thousand CNY) and ``adj_factor``
(a cumulative back-adjustment factor for every trading day).

``daily`` omits suspended days and carries no ST flag, so normalized rows have ``trade_status=1`` and
``is_st=None``. The token is read from a file, never from an environment variable. Calls go to
``https://api.tushare.pro`` with the HTTP client's default certificate verification. The installed
library's own default is plain HTTP on ``api.waditu.com``.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from app.markets.cn_ashare import units
from app.markets.cn_ashare.providers.base import Fetched, ProviderError, parse_date, parse_float
from app.markets.cn_ashare.symbols import SymbolError, parse

_FMT = units.TUSHARE.date_format
_HTTPS_URL = "https://api.tushare.pro/dataapi"
_BASIC_FIELDS = "ts_code,symbol,name,exchange,market,list_status,list_date,delist_date"


def _records(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        raise ProviderError("tushare returned no frame")
    return [dict(r) for r in frame.to_dict(orient="records")]


def _d(day: date) -> str:
    return day.strftime(_FMT)


class TushareProvider:
    source_id = "tushare_pro"
    units = units.TUSHARE

    def __init__(self, client: Any, *, source_id: str | None = None) -> None:
        """``source_id`` overrides the provenance label, e.g. ``cn_synthetic:tushare_shape`` for a
        fake client, so synthetic rows are never recorded as Tushare data."""
        self._pro = client
        if source_id is not None:
            self.source_id = source_id

    @classmethod
    def from_token_file(cls, path: str | Path) -> TushareProvider:
        p = Path(path).expanduser()
        if not p.is_file():
            raise ProviderError(f"no Tushare token file at {p}")
        token = p.read_text(encoding="utf-8").strip()
        if not token:
            raise ProviderError(f"Tushare token file {p} is empty")
        import tushare  # optional dependency, imported only when Tushare is actually used

        client = tushare.pro_api(token)
        client._DataApi__http_url = _HTTPS_URL  # noqa: SLF001 — library exposes no public host setting
        return cls(client)

    def securities(self) -> Fetched:
        raw: list[dict[str, Any]] = []
        for status in ("L", "D", "P"):
            raw.extend(
                _records(
                    self._pro.stock_basic(exchange="", list_status=status, fields=_BASIC_FIELDS)
                )
            )
        rows = []
        for r in raw:
            try:
                sec = parse(str(r["ts_code"]))
            except SymbolError:
                continue
            rows.append(
                {
                    "symbol": sec.symbol,
                    "name": str(r.get("name") or ""),
                    "exchange": sec.exchange.value,
                    "board": sec.board.value,
                    "list_date": parse_date(r.get("list_date"), _FMT),
                    "delist_date": parse_date(r.get("delist_date"), _FMT),
                    "status": str(r.get("list_status") or ""),
                }
            )
        return Fetched(
            "securities", self.source_id, {"list_status": ["L", "D", "P"]}, raw, rows, self.units
        )

    def trade_calendar(self, start: date, end: date) -> Fetched:
        params = {"exchange": "SSE", "start_date": _d(start), "end_date": _d(end)}
        raw = _records(self._pro.trade_cal(**params))
        rows = [
            {
                "exchange": "SSE",
                "cal_date": parse_date(r["cal_date"], _FMT),
                "is_open": int(r["is_open"]) == 1,
            }
            for r in raw
        ]
        return Fetched("trade_calendar", self.source_id, params, raw, rows, self.units)

    def daily(self, symbol: str, start: date, end: date) -> Fetched:
        sec = parse(symbol)
        params = {"ts_code": sec.symbol, "start_date": _d(start), "end_date": _d(end)}
        raw = _records(self._pro.daily(**params))
        rows = []
        for r in raw:
            vol = parse_float(r.get("vol"))
            amt = parse_float(r.get("amount"))
            rows.append(
                {
                    "symbol": sec.symbol,
                    "trade_date": parse_date(r["trade_date"], _FMT),
                    "open": parse_float(r.get("open")),
                    "high": parse_float(r.get("high")),
                    "low": parse_float(r.get("low")),
                    "close": parse_float(r.get("close")),
                    "pre_close": parse_float(r.get("pre_close")),
                    "volume_shares": None if vol is None else vol * self.units.volume_to_shares,
                    "amount_cny": None if amt is None else amt * self.units.amount_to_cny,
                    "trade_status": 1,
                    "is_st": None,
                }
            )
        return Fetched("daily", self.source_id, params, raw, rows, self.units)

    def adj_factors(self, symbol: str, start: date, end: date) -> Fetched:
        sec = parse(symbol)
        params = {"ts_code": sec.symbol, "start_date": _d(start), "end_date": _d(end)}
        raw = _records(self._pro.adj_factor(**params))
        rows = [
            {
                "symbol": sec.symbol,
                "trade_date": parse_date(r["trade_date"], _FMT),
                "factor": parse_float(r.get("adj_factor")),
                "factor_kind": "hfq_cumulative",
            }
            for r in raw
        ]
        return Fetched("adj_factor", self.source_id, params, raw, rows, self.units)
