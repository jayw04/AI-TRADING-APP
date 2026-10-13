"""A-share symbol normalization.

Canonical form is ``<6 digits>.<SH|SZ|BJ>`` (the Tushare ``ts_code`` form). Baostock writes
``sh.600000``. Board is decided by exchange and code prefix; a code whose board is not in scope is
still parsed, so a refusal can name the board.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class Exchange(StrEnum):
    SSE = "SSE"  # Shanghai, suffix SH
    SZSE = "SZSE"  # Shenzhen, suffix SZ
    BSE = "BSE"  # Beijing, suffix BJ


class Board(StrEnum):
    MAIN = "MAIN"
    CHINEXT = "CHINEXT"  # SZSE 300/301
    STAR = "STAR"  # SSE 688/689
    BSE = "BSE"
    B_SHARE = "B_SHARE"  # SSE 900, SZSE 200
    OTHER = "OTHER"


_SUFFIX = {"SH": Exchange.SSE, "SZ": Exchange.SZSE, "BJ": Exchange.BSE}
_EXCHANGE_SUFFIX = {v: k for k, v in _SUFFIX.items()}
_CANON = re.compile(r"^(\d{6})\.(SH|SZ|BJ)$")
_BAOSTOCK = re.compile(r"^(sh|sz|bj)\.(\d{6})$")


class SymbolError(ValueError):
    pass


@dataclass(frozen=True)
class Security:
    code: str
    exchange: Exchange

    @property
    def symbol(self) -> str:
        return f"{self.code}.{_EXCHANGE_SUFFIX[self.exchange]}"

    @property
    def baostock(self) -> str:
        return f"{_EXCHANGE_SUFFIX[self.exchange].lower()}.{self.code}"

    @property
    def board(self) -> Board:
        return board_of(self.code, self.exchange)


def board_of(code: str, exchange: Exchange) -> Board:
    if exchange is Exchange.BSE:
        return Board.BSE
    if exchange is Exchange.SSE:
        if code.startswith(("600", "601", "603", "605")):
            return Board.MAIN
        if code.startswith(("688", "689")):
            return Board.STAR
        if code.startswith("900"):
            return Board.B_SHARE
        return Board.OTHER
    if code.startswith(("000", "001", "002", "003")):
        return Board.MAIN  # 002 (former SME board) merged into the main board on 2021-04-06
    if code.startswith(("300", "301")):
        return Board.CHINEXT
    if code.startswith("200"):
        return Board.B_SHARE
    return Board.OTHER


def parse(text: str) -> Security:
    """Parse a canonical (``600000.SH``) or Baostock (``sh.600000``) symbol."""
    s = text.strip()
    m = _CANON.match(s.upper())
    if m:
        return Security(code=m.group(1), exchange=_SUFFIX[m.group(2)])
    m = _BAOSTOCK.match(s.lower())
    if m:
        return Security(code=m.group(2), exchange=_SUFFIX[m.group(1).upper()])
    raise SymbolError(f"not an A-share symbol: {text!r}")


def to_canonical(text: str) -> str:
    return parse(text).symbol


def to_baostock(text: str) -> str:
    return parse(text).baostock
