"""A-share market rules, effective-date aware.

Every rule is a dated row with its source and how it was checked. A date before the configured
history (``RULES_START``) or a board outside scope raises ``RuleNotConfigured``: the adapter never
falls back to a guess, and never to a US assumption.

Scope: SSE and SZSE main boards only. ChiNext (20% limits since 2020-08-24), STAR (20%), the Beijing
exchange (30%) and B-shares have different rules and are refused here.

Checked 2026-10-12 against published sources (the ``source`` field on each row):

* Main-board risk-warning (ST, *ST) price limit moved from 5% to 10% on 2026-07-06 (SSE/SZSE 2026
  trading-rule revision, 上证发〔2026〕41号).
* Stamp duty halved to 0.05% (seller only) from 2023-08-28 (财政部 税务总局公告2023年第39号).
* Transfer fee halved to 0.001% each side from 2022-04-29 (China Securities Depository and Clearing).
* Exchange handling fee cut from 0.00487% to 0.00341% each side from 2023-08-28 (SZSE fee page).
* Regulatory fee 0.002% each side (current broker fee schedules).

Rows marked ``verified="not re-checked"`` are long-standing values whose start date was not re-read
from a primary source in this build; they are disclosed in every run report.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from decimal import ROUND_HALF_UP, Decimal

from app.markets.cn_ashare.symbols import Board, Exchange, Security

#: Earliest date the rules below are configured for (the 2015-08-01 fee unification).
RULES_START = date(2015, 8, 1)
ST_LIMIT_UNIFIED = date(2026, 7, 6)
LOT_SIZE = 100
#: Conservative scope choice, not an exchange rule: no fill in a stock's first N trading days.
NEW_LISTING_EXCLUDED_DAYS = 5


class RuleNotConfigured(ValueError):
    """The requested date, board or instrument is outside what this adapter configures."""


@dataclass(frozen=True)
class RuleRow:
    name: str
    effective_from: date
    value: float
    source: str
    verified: str


def _row_for(rows: tuple[RuleRow, ...], on: date) -> RuleRow:
    if on < RULES_START:
        raise RuleNotConfigured(f"rules are configured from {RULES_START}; {on} is earlier")
    chosen = None
    for r in rows:
        if r.effective_from <= on:
            chosen = r
    if chosen is None:
        raise RuleNotConfigured(f"no {rows[0].name} rule effective on {on}")
    return chosen


# --- price limits (main board) ---------------------------------------------------------------------

_LIMIT_NORMAL = (
    RuleRow(
        "main_board_limit", date(1996, 12, 16), 0.10, "SSE/SZSE trading rules", "not re-checked"
    ),
)
_LIMIT_ST = (
    RuleRow(
        "main_board_st_limit", date(1998, 4, 22), 0.05, "SSE/SZSE trading rules", "not re-checked"
    ),
    RuleRow(
        "main_board_st_limit",
        ST_LIMIT_UNIFIED,
        0.10,
        "上证发〔2026〕41号 SSE trading rules (2026 revision); SZSE revision same date",
        "checked 2026-10-12",
    ),
)


def require_in_scope(sec: Security) -> None:
    if sec.board is not Board.MAIN or sec.exchange not in (Exchange.SSE, Exchange.SZSE):
        raise RuleNotConfigured(f"{sec.symbol} is on {sec.board.value}; only SSE/SZSE main board")


def limit_pct(on: date, *, is_st: bool | None) -> float:
    """The daily price-limit fraction for a main-board stock on ``on``.

    Before 2026-07-06 the ST flag decides the limit, so an unknown flag raises. From that date both
    are 10% and the flag no longer matters."""
    normal = _row_for(_LIMIT_NORMAL, on).value
    st = _row_for(_LIMIT_ST, on).value
    if normal == st:
        return normal
    if is_st is None:
        raise RuleNotConfigured(
            f"ST status unknown on {on}; the limit is 5% or 10% depending on it"
        )
    return st if is_st else normal


def _round_price(x: Decimal) -> Decimal:
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def limit_prices(pre_close: float, on: date, *, is_st: bool | None) -> tuple[float, float]:
    """(limit_down, limit_up), each rounded half-up to 0.01 CNY from the exchange's previous close."""
    pct = Decimal(str(limit_pct(on, is_st=is_st)))
    pc = Decimal(str(pre_close))
    return float(_round_price(pc * (1 - pct))), float(_round_price(pc * (1 + pct)))


# --- sessions --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Session:
    opening_call: tuple[time, time]
    morning: tuple[time, time]
    afternoon: tuple[time, time]
    closing_call: tuple[time, time] | None


def session(exchange: Exchange, on: date) -> Session:
    """Trading session for ``exchange`` on ``on`` (Asia/Shanghai). Lunch break 11:30-13:00.

    SSE introduced the 14:57-15:00 closing call auction on 2018-08-20; SZSE has had one since 2006."""
    if on < RULES_START:
        raise RuleNotConfigured(f"sessions are configured from {RULES_START}")
    open_call = (time(9, 15), time(9, 25))
    morning = (time(9, 30), time(11, 30))
    if exchange is Exchange.SSE and on < date(2018, 8, 20):
        return Session(open_call, morning, (time(13, 0), time(15, 0)), None)
    if exchange in (Exchange.SSE, Exchange.SZSE):
        return Session(open_call, morning, (time(13, 0), time(14, 57)), (time(14, 57), time(15, 0)))
    raise RuleNotConfigured(f"no session configured for {exchange.value}")


# --- fees ------------------------------------------------------------------------------------------

_STAMP_SELL = (
    RuleRow(
        "stamp_duty_sell",
        date(2008, 9, 19),
        0.001,
        "seller-only since 2008-09-19",
        "not re-checked",
    ),
    RuleRow(
        "stamp_duty_sell",
        date(2023, 8, 28),
        0.0005,
        "财政部 税务总局公告2023年第39号",
        "checked 2026-10-12",
    ),
)
_TRANSFER = (
    RuleRow(
        "transfer_fee",
        date(2015, 8, 1),
        0.00002,
        "ChinaClear, SH+SZ unified 2015-08-01",
        "not re-checked",
    ),
    RuleRow(
        "transfer_fee",
        date(2022, 4, 29),
        0.00001,
        "ChinaClear notice, halved 2022-04-29",
        "checked 2026-10-12",
    ),
)
_HANDLING = (
    RuleRow("handling_fee", date(2015, 8, 1), 0.0000487, "SSE/SZSE fee schedule", "not re-checked"),
    RuleRow(
        "handling_fee",
        date(2023, 8, 28),
        0.0000341,
        "SZSE fee page; SSE notice 2023-08-18",
        "checked 2026-10-12",
    ),
)
_REGULATORY = (
    RuleRow(
        "regulatory_fee",
        date(2015, 8, 1),
        0.00002,
        "CSRC fee collected by the exchange",
        "checked 2026-10-12 (current rate)",
    ),
)


@dataclass(frozen=True)
class CommissionAssumption:
    """Broker commission is account-specific, so it is an explicit assumption, never a rule.

    Net-commission mode: handling and regulatory fees are charged separately (as modelled here)."""

    rate: float = 0.00025
    minimum_cny: float = 5.0


@dataclass(frozen=True)
class FeeBreakdown:
    commission: float
    stamp_duty: float
    transfer_fee: float
    handling_fee: float
    regulatory_fee: float

    @property
    def total(self) -> float:
        return (
            self.commission
            + self.stamp_duty
            + self.transfer_fee
            + self.handling_fee
            + self.regulatory_fee
        )


def fees(
    notional_cny: float, side: str, on: date, commission: CommissionAssumption | None = None
) -> FeeBreakdown:
    if side not in ("buy", "sell"):
        raise ValueError("side must be 'buy' or 'sell'")
    if notional_cny < 0:
        raise ValueError("notional must be non-negative")
    c = commission or CommissionAssumption()
    comm = max(notional_cny * c.rate, c.minimum_cny) if notional_cny > 0 else 0.0
    stamp = notional_cny * _row_for(_STAMP_SELL, on).value if side == "sell" else 0.0
    return FeeBreakdown(
        commission=comm,
        stamp_duty=stamp,
        transfer_fee=notional_cny * _row_for(_TRANSFER, on).value,
        handling_fee=notional_cny * _row_for(_HANDLING, on).value,
        regulatory_fee=notional_cny * _row_for(_REGULATORY, on).value,
    )


def rule_disclosure() -> list[dict[str, str]]:
    """Every dated rule row, for the run report."""
    rows = _LIMIT_NORMAL + _LIMIT_ST + _STAMP_SELL + _TRANSFER + _HANDLING + _REGULATORY
    return [
        {
            "name": r.name,
            "effective_from": r.effective_from.isoformat(),
            "value": repr(r.value),
            "source": r.source,
            "verified": r.verified,
        }
        for r in rows
    ]


#: Facts this daily-bar adapter does NOT model; the run report repeats them.
NOT_MODELLED = (
    "intraday sequence: a daily bar cannot show whether a limit price was touched before or after a fill",
    "risk-warning (ST) board extras such as per-account daily buy caps",
    "delisting-arrangement period trading",
    "IPO first-days pricing (those days are excluded from fills instead)",
    "odd-lot and block-trade venues; after-hours fixed-price trading",
)
