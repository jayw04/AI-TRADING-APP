"""The identity every dataset, strategy run and result carries.

A ``MarketContext`` states the market, exchange, currency, timezone, provider and price basis. Code
that combines data refuses to mix contexts from different markets: an A-share series and a US series
are never joined, ranked together or written to the same store.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class Market(StrEnum):
    US_EQUITY = "US_EQUITY"
    CN_ASHARE = "CN_ASHARE"


class PriceBasis(StrEnum):
    """How a price series relates to the prices that actually traded."""

    RAW = "RAW"  # as traded, no adjustment
    RAW_WITH_FACTORS = "RAW_WITH_FACTORS"  # raw prices stored with provider adjustment factors
    HFQ = "HFQ"  # back-adjusted (后复权): earliest price kept, later prices scaled
    QFQ = "QFQ"  # forward-adjusted (前复权) to a stated reference date
    SPLIT_ADJUSTED = "SPLIT_ADJUSTED"  # US vendors that restate history for splits


class MarketMismatchError(ValueError):
    """Two contexts from different markets (or a context from the wrong market) were combined."""


@dataclass(frozen=True)
class MarketContext:
    market: Market
    exchange: str
    currency: str
    timezone: str
    provider: str
    price_basis: PriceBasis

    def __post_init__(self) -> None:
        for name in ("exchange", "currency", "timezone", "provider"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"MarketContext.{name} must be a non-empty string")

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["market"] = self.market.value
        d["price_basis"] = self.price_basis.value
        return d

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> MarketContext:
        return cls(
            market=Market(raw["market"]),
            exchange=str(raw["exchange"]),
            currency=str(raw["currency"]),
            timezone=str(raw["timezone"]),
            provider=str(raw["provider"]),
            price_basis=PriceBasis(raw["price_basis"]),
        )


def require_market(ctx: MarketContext, market: Market) -> MarketContext:
    if ctx.market is not market:
        raise MarketMismatchError(f"expected a {market.value} context, got {ctx.market.value}")
    return ctx


def require_single_market(contexts: list[MarketContext]) -> Market:
    """The one market shared by ``contexts``, or raise. An empty list has no market."""
    markets = {c.market for c in contexts}
    if len(markets) != 1:
        raise MarketMismatchError(
            f"contexts span {sorted(m.value for m in markets) or 'no'} markets"
        )
    return markets.pop()


#: The existing US subsystem, described for labelling only. Nothing in the US code reads this.
US_EQUITY = MarketContext(
    market=Market.US_EQUITY,
    exchange="NYSE/NASDAQ",
    currency="USD",
    timezone="America/New_York",
    provider="alpaca+sharadar",
    price_basis=PriceBasis.SPLIT_ADJUSTED,
)
