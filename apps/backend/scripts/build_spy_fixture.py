"""Generate the committed SPY benchmark fixture (P10 §3B-3).

SPY is the Market benchmark for the portfolio study, but it is NOT a research asset in
the factor-data store (which holds individual equities). Rather than wire a live fetch
into the study, we **generate the fixture once and commit it** — the same pattern as the
AAPL bar fixtures (ADR 0017: truststore beats Norton's SSL inspection).

Run this in an environment with Alpaca paper creds in ``.env`` and working egress to
``data.alpaca.markets`` (truststore handles Norton). It writes
``tests/fixtures/spy_daily.parquet`` (columns: ``date``, ``close``) which
``app/research/engine/benchmark.py`` loads. Alpaca's free/IEX tier provides history from
~2016 — that matches the store's real-data depth, so the SPY benchmark is meaningful over
the same window.

    cd apps/backend && .venv/Scripts/python.exe scripts/build_spy_fixture.py
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

import pandas as pd

_OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "spy_daily.parquet"
_SYMBOL = "SPY"


def main() -> int:
    try:
        import truststore

        truststore.inject_into_ssl()  # ADR 0017 — OS trust store beats Norton MITM
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"warning: truststore unavailable ({exc}); fetch may fail behind Norton")

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[3] / ".env")  # repo-root .env
    key = os.environ.get("ALPACA_PAPER_API_KEY") or os.environ.get("ALPACA_PAPER_1_API_KEY")
    sec = os.environ.get("ALPACA_PAPER_API_SECRET") or os.environ.get("ALPACA_PAPER_1_API_SECRET")
    if not (key and sec):
        raise SystemExit("no Alpaca paper creds in .env (ALPACA_PAPER_API_KEY / _SECRET)")

    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    client = StockHistoricalDataClient(key, sec)
    req = StockBarsRequest(
        symbol_or_symbols=_SYMBOL, timeframe=TimeFrame.Day,
        start=datetime(2007, 1, 1), end=datetime(2026, 6, 12),
    )
    df = client.get_stock_bars(req).df
    if df.empty:
        raise SystemExit("Alpaca returned no SPY bars")

    out = pd.DataFrame({
        "date": df.index.get_level_values("timestamp").date,
        "close": df["close"].to_numpy(),
    }).drop_duplicates("date").sort_values("date").reset_index(drop=True)

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(_OUT, index=False)
    print(f"wrote {len(out)} SPY daily closes [{out['date'].iloc[0]} .. {out['date'].iloc[-1]}] -> {_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
