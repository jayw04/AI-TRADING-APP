"""Provider contract and the normalized row shapes every adapter returns."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Protocol

from app.markets.cn_ashare.units import UnitSpec

DATASETS = ("securities", "trade_calendar", "daily", "adj_factor")

#: Normalized columns per dataset. Prices CNY/share, volume shares, amount CNY, dates ``date``.
COLUMNS: dict[str, tuple[str, ...]] = {
    "securities": ("symbol", "name", "exchange", "board", "list_date", "delist_date", "status"),
    "trade_calendar": ("exchange", "cal_date", "is_open"),
    "daily": (
        "symbol", "trade_date", "open", "high", "low", "close", "pre_close",
        "volume_shares", "amount_cny", "trade_status", "is_st",
    ),
    "adj_factor": ("symbol", "trade_date", "factor", "factor_kind"),
}  # fmt: skip

#: ``factor_kind`` values. A cumulative factor is published for every trading day; a step factor
#: is published only on the dates it changes and applies until the next change.
FACTOR_KINDS = ("hfq_cumulative", "hfq_step")


class ProviderError(RuntimeError):
    """The provider returned an error code or an unusable payload."""


@dataclass
class Fetched:
    dataset: str
    provider: str
    params: dict[str, Any]
    raw_rows: list[dict[str, Any]]  # exactly as received (provider field names and units)
    rows: list[dict[str, Any]]  # normalized to COLUMNS[dataset]
    units: UnitSpec
    fetched_at_utc: str = field(
        default_factory=lambda: datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    )

    def __post_init__(self) -> None:
        if self.dataset not in DATASETS:
            raise ValueError(f"unknown dataset {self.dataset!r}")
        cols = set(COLUMNS[self.dataset])
        for r in self.rows:
            if set(r) != cols:
                raise ProviderError(
                    f"{self.dataset} row has columns {sorted(r)}, expected {sorted(cols)}"
                )


class DailyProvider(Protocol):
    source_id: str
    units: UnitSpec

    def securities(self) -> Fetched: ...

    def trade_calendar(self, start: date, end: date) -> Fetched: ...

    def daily(self, symbol: str, start: date, end: date) -> Fetched: ...

    def adj_factors(self, symbol: str, start: date, end: date) -> Fetched: ...


def parse_float(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, str):
        v = v.strip()
        if not v:
            return None
    f = float(v)
    return None if f != f else f  # NaN -> None


def parse_date(v: Any, fmt: str) -> date | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in ("nan", "none", "nat"):
        return None
    return datetime.strptime(s, fmt).date()
