"""China A-share research subsystem. RESEARCH-ONLY.

Daily data from Tushare (intended primary) and Baostock (cross-check), stored in its own DuckDB file
(``settings.cn_ashare_db_path``) with raw payloads cached under ``settings.cn_ashare_cache_dir``.

This package must never reach the order path: it imports no broker adapter, order router, risk
engine, scheduler or US strategy module, and nothing in the US code imports it except the read-only
API router. ``tests/markets/cn_ashare/test_isolation.py`` enforces both directions.

Initial scope (disclosed in every run): SSE and SZSE **main board** A-shares, CNY, daily bars.
ChiNext, STAR, the Beijing exchange and B-shares are refused by the rules adapter.
"""

from app.markets.context import Market, MarketContext, PriceBasis

MARKET = Market.CN_ASHARE
CURRENCY = "CNY"
TIMEZONE = "Asia/Shanghai"

#: The board scope this build supports. Anything else is refused, never approximated.
SCOPE = "SSE and SZSE main-board A-shares (CNY); daily bars only"


def context(*, exchange: str, provider: str, price_basis: PriceBasis) -> MarketContext:
    return MarketContext(
        market=MARKET,
        exchange=exchange,
        currency=CURRENCY,
        timezone=TIMEZONE,
        provider=provider,
        price_basis=price_basis,
    )
