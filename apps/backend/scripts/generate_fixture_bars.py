"""Generate a fixture parquet for tests/fixtures/bars/.

Run once locally with Alpaca creds in `.env`; commit the output to git so CI
runs deterministically without hitting Alpaca.

Usage::

    cd apps/backend
    python scripts/generate_fixture_bars.py AAPL 2025-11-03

Pick a normal full-day session. Avoid holidays, half-days, or days with a
known stock split / dividend / major news event. A boring full trading day
produces a reproducible RSI / MACD path for the golden test.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

from app.market_data.bar_cache import _alpaca_fetch_bars


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: generate_fixture_bars.py SYMBOL YYYY-MM-DD", file=sys.stderr)
        return 2
    symbol = sys.argv[1].upper()
    day = sys.argv[2]
    y, m, d = map(int, day.split("-"))
    start = datetime(y, m, d, 0, 0, tzinfo=UTC)
    end = datetime(y, m, d, 23, 59, 59, tzinfo=UTC)

    df = _alpaca_fetch_bars(symbol, "1Min", start, end)
    if df.empty:
        print(f"No bars returned for {symbol} on {day}", file=sys.stderr)
        return 1

    out_dir = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "bars"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{symbol}_{day}_1Min.parquet"
    df.to_parquet(out, index=False)
    print(f"Wrote {out} with {len(df)} bars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
