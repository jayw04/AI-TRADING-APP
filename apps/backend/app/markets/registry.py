"""The markets the application knows, and the only way an API path names one.

A market id in a URL is matched exactly against this registry. Anything else raises
``UnsupportedMarket``; nothing falls back to the US market.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.markets.context import Market


class UnsupportedMarket(ValueError):
    def __init__(self, raw: str) -> None:
        super().__init__(f"unsupported market {raw!r}; supported: {', '.join(api_ids())}")
        self.raw = raw


@dataclass(frozen=True)
class MarketInfo:
    market: Market
    label: str
    currency: str
    currency_label: str
    timezone: str
    research_only: bool
    #: Whether this market's views are served under /api/v1/markets/{id}/. The US subsystem keeps its
    #: existing /api/v1 endpoints.
    scoped_api: bool
    status: str

    @property
    def api_id(self) -> str:
        return self.market.value.lower()

    def as_dict(self) -> dict[str, object]:
        return {
            "market": self.api_id,
            "label": self.label,
            "currency": self.currency,
            "currency_label": self.currency_label,
            "timezone": self.timezone,
            "research_only": self.research_only,
            "scoped_api": self.scoped_api,
            "status": self.status,
        }


MARKETS: dict[str, MarketInfo] = {
    m.api_id: m
    for m in (
        MarketInfo(
            market=Market.US_EQUITY,
            label="US Equities",
            currency="USD",
            currency_label="USD",
            timezone="America/New_York",
            research_only=False,
            scoped_api=False,
            status="PAPER_TRADING",
        ),
        MarketInfo(
            market=Market.CN_ASHARE,
            label="中国 A股",
            currency="CNY",
            currency_label="RMB",
            timezone="Asia/Shanghai",
            research_only=True,
            scoped_api=True,
            status="RESEARCH_ONLY",
        ),
    )
}


def api_ids() -> list[str]:
    return list(MARKETS)


def resolve(raw: str) -> MarketInfo:
    found = MARKETS.get(raw)
    if found is None:
        raise UnsupportedMarket(raw)
    return found
