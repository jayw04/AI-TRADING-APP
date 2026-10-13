"""Provider -> A-share store, with provenance on every ingest.

A bounded sample is fetched dataset by dataset: security metadata (listed, delisted and paused),
the trading calendar, raw daily bars and adjustment factors. Factors are requested from each stock's
listing date so a step factor in force before the sample window is known.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.markets.cn_ashare import context
from app.markets.cn_ashare.providers.base import DailyProvider
from app.markets.cn_ashare.store import CnAshareStore
from app.markets.cn_ashare.symbols import parse
from app.markets.context import PriceBasis

#: Labels a run or dataset carries. A plumbing sample proves the pipeline works; it is not a
#: survivorship-safe universe and supports no performance claim.
PLUMBING_SAMPLE = "PLUMBING_SAMPLE_NOT_SURVIVORSHIP_SAFE"
SYNTHETIC_SAMPLE = "SYNTHETIC_FIXTURE_NOT_MARKET_DATA"


@dataclass
class IngestResult:
    provider: str
    ingest_ids: list[str] = field(default_factory=list)
    missing_symbols: list[str] = field(default_factory=list)


def ingest_sample(
    store: CnAshareStore,
    provider: DailyProvider,
    symbols: list[str],
    start: date,
    end: date,
    *,
    sample_label: str,
) -> IngestResult:
    pid = provider.source_id
    out = IngestResult(provider=pid)
    sec_fetch = provider.securities()
    out.ingest_ids.append(
        store.record(sec_fetch, context(exchange="SSE+SZSE", provider=pid, price_basis=PriceBasis.RAW),
                     sample_label=sample_label)
    )  # fmt: skip
    listed = {r["symbol"]: r["list_date"] for r in sec_fetch.rows}
    cal = provider.trade_calendar(start, end)
    out.ingest_ids.append(
        store.record(
            cal,
            context(exchange="SSE", provider=pid, price_basis=PriceBasis.RAW),
            sample_label=sample_label,
        )
    )
    for raw_symbol in symbols:
        sec = parse(raw_symbol)
        if sec.symbol not in listed:
            out.missing_symbols.append(sec.symbol)
            store.record_issue(
                severity="WARNING",
                kind="SYMBOL_NOT_IN_SECURITY_LIST",
                detail=f"{sec.symbol} requested but absent from {pid} security metadata; not fetched",
                provider=pid,
                dataset="securities",
            )
            continue
        ctx = context(
            exchange=sec.exchange.value, provider=pid, price_basis=PriceBasis.RAW_WITH_FACTORS
        )
        out.ingest_ids.append(
            store.record(provider.daily(sec.symbol, start, end), ctx, sample_label=sample_label)
        )
        factor_start = min(listed[sec.symbol] or start, start)
        out.ingest_ids.append(
            store.record(
                provider.adj_factors(sec.symbol, factor_start, end), ctx, sample_label=sample_label
            )
        )
    return out
