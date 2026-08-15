"""Phase-A REST capture primitives (registration §7).

Two capture modes, both REST — Phase A deliberately arms NO websocket, which
makes subordination to the account-7 transition executor trivial (a couple of
requests per minute) and leaves streaming to Phase B where K2 requires it:

  * ``sample_quotes_cycle`` — one multi-symbol latest-quote request per feed
    per cycle, producing time-aligned SIP/IEX quote pairs (K6 stub-quote
    analysis needs paired same-instant observations).
  * ``fetch_session_bars`` — end-of-session 1-minute bars 04:00–16:00 ET per
    feed (premarket + RTH — the registered census scope; postmarket is
    deliberately not collected without a qualification reason, and the 16:00
    cutoff is what makes the 16:30-capture/16:45-freeze schedule sound). Bars
    carry volume, trade_count and vwap, covering the K1/K3 census fields
    without raw-tape storage cost.

Every request names its feed explicitly (§3.1; check_marketdata_feed_pinning.sh).
The client is passed in untyped — construction and identity-latching live in
scripts/mdq_collector.py.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# Proposed Phase-A capture universe — FROZEN at registration sign-off (§8).
# SPY/QQQ/IWM + the 11 SPDR sector ETFs; the acct-7 transition set and the
# ≤50-symbol scanner sample are appended via the --universe-file override so
# the frozen list lives in one reviewed artifact, not in code drift.
PHASE_A_UNIVERSE: tuple[str, ...] = (
    "SPY",
    "QQQ",
    "IWM",
    "XLB",
    "XLC",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLRE",
    "XLU",
    "XLV",
    "XLY",
)

CAPTURE_MODE_SAMPLER = "rest_quote_sampler_v1"
CAPTURE_MODE_EOD_BARS = "rest_eod_bars_v1"


def sample_quotes_cycle(
    client: Any, universe: tuple[str, ...], *, feeds: tuple[str, ...] = ("iex", "sip")
) -> dict[str, list[dict[str, Any]]]:
    """One paired sampling cycle: for each feed, a single multi-symbol
    latest-quote request. Returns feed -> JSONL-ready records sharing one
    ``cycle_ts`` so SIP/IEX pairs align."""
    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockLatestQuoteRequest

    cycle_ts = datetime.now(UTC).isoformat()
    out: dict[str, list[dict[str, Any]]] = {}
    for feed in feeds:
        # Per-feed error isolation: a transient failure on one feed must not
        # lose the other feed's observation for this cycle. The error record
        # keeps the cycle's slot in the partition auditable (frozen §8 retry
        # policy: continue on transient failure; the CLI aborts only on
        # sustained failure).
        try:
            quotes = client.get_stock_latest_quote(
                StockLatestQuoteRequest(symbol_or_symbols=list(universe), feed=DataFeed(feed))
            )
        except Exception as exc:  # noqa: BLE001 - recorded, never silently dropped
            out[feed] = [{"cycle_ts": cycle_ts, "feed_error": f"{type(exc).__name__}: {exc}"}]
            continue
        records: list[dict[str, Any]] = []
        for symbol in universe:
            q = quotes.get(symbol)
            if q is None:
                records.append({"cycle_ts": cycle_ts, "symbol": symbol, "missing": True})
                continue
            records.append(
                {
                    "cycle_ts": cycle_ts,
                    "symbol": symbol,
                    "quote_ts": q.timestamp.isoformat(),
                    "bid": float(q.bid_price),
                    "ask": float(q.ask_price),
                    "bid_size": float(q.bid_size),
                    "ask_size": float(q.ask_size),
                    "bid_exchange": getattr(q, "bid_exchange", None),
                    "ask_exchange": getattr(q, "ask_exchange", None),
                    "conditions": getattr(q, "conditions", None),
                }
            )
        out[feed] = records
    return out


def fetch_session_bars(client: Any, universe: tuple[str, ...], session: date, feed: str) -> Any:
    """Phase-A session 1-minute bars (04:00–16:00 ET: premarket + RTH, no
    postmarket) for one explicit feed. Returns a tidy DataFrame ready for
    ``write_parquet``."""
    import pandas as pd
    from alpaca.data.enums import DataFeed
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    start = datetime.combine(session, time(4, 0), tzinfo=ET)
    end = datetime.combine(session, time(16, 0), tzinfo=ET)
    data = client.get_stock_bars(
        StockBarsRequest(
            symbol_or_symbols=list(universe),
            timeframe=TimeFrame(1, TimeFrameUnit.Minute),
            start=start,
            end=end,
            feed=DataFeed(feed),
        )
    ).data
    rows: list[dict[str, Any]] = []
    for symbol, bars in data.items():
        for b in bars:
            rows.append(
                {
                    "symbol": symbol,
                    "ts": b.timestamp.isoformat(),
                    "open": float(b.open),
                    "high": float(b.high),
                    "low": float(b.low),
                    "close": float(b.close),
                    "volume": float(b.volume),
                    "trade_count": float(b.trade_count) if b.trade_count is not None else None,
                    "vwap": float(b.vwap) if b.vwap is not None else None,
                }
            )
    return pd.DataFrame(rows)
