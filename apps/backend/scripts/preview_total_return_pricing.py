#!/usr/bin/env python3
"""Preview total-return vs raw pricing for combined-book's cross-asset ETF sleeve (read-only).

PORT-001 #3. The report-only dry-run of total-return pricing only fires inside the weekly rebalance;
this script reconstructs the same comparison now — fetch each cross-asset ETF's distributions from the
Alpaca corporate-actions API (the live source; Sharadar has zero ETF coverage), build the total-return
index (raw closes + distributions), and print the per-symbol trailing-return divergence — so the owner
can see what enabling ``use_total_return_pricing`` would change WITHOUT waiting for the next RTH rebalance.

Read-only: no order path, no DB writes, no live-book change. Run INSIDE the backend container
(Alpaca creds + truststore + app modules):
    docker compose exec -T backend python scripts/preview_total_return_pricing.py
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from app.factor_data.total_return import total_return_index
from app.market_data.alpaca_distributions import AlpacaDistributionsProvider
from app.research.factor_lab.cross_asset import CROSS_ASSET_UNIVERSE

_LOOKBACK_DAYS = 900  # ~2.5y of calendar history so trailing 12m return + distributions are well covered
_OUT = Path("/app/data/port001_total_return_preview.json")  # data/ is mounted; docs/ is not


def _fetch_daily(symbols: list[str], days: int = _LOOKBACK_DAYS) -> dict[str, pd.Series]:
    """Batch daily-close series per symbol from Alpaca IEX (raw/unadjusted close, as the live sleeve
    uses). Truststore-injected (ADR 0017) so it works behind Norton and is a no-op on the box."""
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    from app.market_data.bar_cache import load_credentials
    from app.utils.tls_trust import enable_os_trust_store

    enable_os_trust_store()
    creds = load_credentials()
    client = StockHistoricalDataClient(api_key=creds.api_key, secret_key=creds.api_secret)
    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    req = StockBarsRequest(symbol_or_symbols=symbols, timeframe=TimeFrame(1, TimeFrameUnit.Day),
                           start=start, end=end, feed=DataFeed.IEX, limit=10000)
    data = client.get_stock_bars(req).data
    out: dict[str, pd.Series] = {}
    for sym in symbols:
        bars = data.get(sym, [])
        if bars:
            out[sym] = pd.Series(
                [float(b.close) for b in bars],
                index=[pd.Timestamp(b.timestamp).tz_localize(None).normalize() for b in bars])
    return out


async def main() -> int:
    symbols = [s.upper() for s in CROSS_ASSET_UNIVERSE]
    end = datetime.now(UTC)
    start = end - timedelta(days=_LOOKBACK_DAYS)

    provider = AlpacaDistributionsProvider()
    summary = await provider.prefetch(symbols, start.date(), end.date())
    px = _fetch_daily(symbols)
    print(f"fetched daily bars for {len(px)}/{len(symbols)} ETFs; "
          f"distributions: {summary.dividends} div / {summary.splits} split / {summary.rejected} rejected "
          f"({'FALLBACK — raw' if summary.fallback else 'ok'}, {summary.elapsed_ms} ms)")

    rows: list[dict] = []
    for sym in symbols:
        s = px.get(sym)
        if s is None or len(s) < 2:
            continue
        div, spl = provider.distributions(sym, s.index[0], s.index[-1])
        tri = total_return_index(s, div, spl)
        raw_ret = float(s.iloc[-1] / s.iloc[0] - 1.0)
        tr_ret = float(tri.iloc[-1] / tri.iloc[0] - 1.0)
        rows.append({
            "symbol": sym, "n_div": int(len(div)), "n_split": int(len(spl)),
            "raw_return": round(raw_ret, 4), "tr_return": round(tr_ret, 4),
            "divergence_bps": round((tr_ret - raw_ret) * 1e4, 1),
        })

    rows.sort(key=lambda r: -r["divergence_bps"])
    print("\n=== total-return vs raw — cross-asset sleeve preview ===")
    print(f"  {'sym':<5} {'divs':>4} {'splits':>6} {'raw_ret':>9} {'tr_ret':>9} {'Δ bps':>8}")
    for r in rows:
        print(f"  {r['symbol']:<5} {r['n_div']:>4} {r['n_split']:>6} "
              f"{r['raw_return']:>9.2%} {r['tr_return']:>9.2%} {r['divergence_bps']:>8.1f}")

    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "note": "OFFLINE PREVIEW of total-return vs raw pricing for the 9 cross-asset ETFs "
                "(Alpaca corporate-actions distributions). Read-only; no live-book change.",
        "provider": summary.provider, "provider_sdk": summary.provider_sdk,
        "window": list(summary.window), "fallback": summary.fallback, "rows": rows,
    }
    try:
        _OUT.write_text(json.dumps(result, indent=2, default=str))
        print(f"\n  wrote {_OUT}")
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
