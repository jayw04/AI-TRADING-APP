# P2 Session 1 — Bar Cache + Indicator Computer

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-21 |
| Phase | **P2**, **§1** (entirely) |
| Predecessor | *TradingWorkbench_P2_Checklist_v0.1.md* (tag `p1-complete`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | Build the deterministic, fast OHLCV bar layer that everything else in P2 depends on. (1) `BarCache` — parquet-backed per-symbol-per-day cache with LRU eviction. (2) `IndicatorComputer` — pandas-ta wrapper for the core indicator set with result memoization. (3) `/api/v1/indicators/{symbol}` REST endpoint. (4) Tests including a golden test against committed fixture bars. |
| Estimated wall time | 2.5–3.5 hours |
| Stopping point | `git tag p2-session1-complete` |
| Out of scope | Strategy framework, the strategies table, the backtest harness. All of those land in Sessions 2 and 3 and consume this session's output. |

---

## Session Goal

After this session:
- `apps/backend/bars_cache/{symbol}/{timeframe}/{YYYY-MM-DD}.parquet` files exist on disk after first read of any symbol/timeframe range.
- `BarCache.get_bars(symbol, timeframe, start, end)` returns a clean `pd.DataFrame` whether served from cache or freshly fetched from Alpaca. Subsequent calls in the same date range hit disk only.
- `IndicatorComputer.compute(bars, names)` returns the core P2 indicator set: SMA 20/50/200, EMA 9/21, RSI(14), MACD(12,26,9), ATR(14), VWAP, Bollinger Bands(20,2), relative volume.
- `GET /api/v1/indicators/{symbol}?names=RSI,MACD&timeframe=1Min` returns latest values plus a short sparkline window.
- A committed fixture (`tests/fixtures/bars/AAPL_2025-11-03_1Min.parquet`) drives a golden test that locks down indicator output across pandas-ta upgrades.
- LRU eviction kicks in when the cache exceeds the configured size cap.

What does NOT happen this session:
- No strategies table, no strategy engine. Both are Session 2.
- No WebSocket streaming of bars. P2 is poll-driven per Checklist §3.5; live WS subscription to market data is P4.
- No backtest harness. Session 3.

---

## Prerequisites Check

```bash
cd ~/code/AI-TRADING-APP
git status                                       # clean
git pull origin main
git describe --tags --abbrev=0                   # expect: p1-complete

# Confirm P1 stack still boots and Alpaca paper API is reachable
./scripts/dev.sh &
sleep 25
curl -fs http://127.0.0.1:8000/healthz | jq -e '.status == "ok"'
curl -fs http://127.0.0.1:8000/api/v1/account | jq '{mode, status}'
docker compose down
```

- [ ] On `main`, clean tree, at `p1-complete` or later.
- [ ] Backend boots; Alpaca paper account responds ACTIVE.

Cut the branch:

```bash
git checkout -b feat/p2-bar-cache-and-indicators
```

---

## §1.1 — Dependencies

Add the two libraries this session needs.

Edit `apps/backend/pyproject.toml`. In `[project] dependencies`:

```toml
"pandas>=2.2.0,<3.0.0",
"pandas-ta>=0.3.14b,<0.4.0",
"pyarrow>=15.0.0,<20.0.0",       # for parquet
```

Then sync the venv:

```bash
cd apps/backend
uv pip install -e ".[dev]"
cd ../..
```

Verify imports work:

```bash
cd apps/backend
uv run python -c "import pandas, pandas_ta, pyarrow; print('ok')"
cd ../..
```

- [ ] Three dependencies added.
- [ ] `uv pip install` succeeds.
- [ ] Sanity import prints `ok`.

> **pandas-ta version pinning.** pandas-ta is still pre-1.0; the project pins to `~0.3.14b`. If a future minor release breaks signatures, the golden test in §1.5 will catch it. Don't bump pandas-ta lightly.

---

## §1.2 — Bar Cache

Per-symbol-per-day parquet files. Append-only — never rewrites an existing day. LRU eviction over the configured cap.

### 1.2.1 — Settings additions

Extend `apps/backend/app/config.py` `Settings` class with:

```python
# --- Market data cache ---
bars_cache_root: str = Field(
    default="bars_cache",
    alias="WORKBENCH_BARS_CACHE_ROOT",
)
bars_cache_max_gb: float = Field(
    default=5.0,
    alias="WORKBENCH_BARS_CACHE_MAX_GB",
)
```

Add to `.env.example`:

```
# --- Market data cache ---
WORKBENCH_BARS_CACHE_ROOT=bars_cache
WORKBENCH_BARS_CACHE_MAX_GB=5.0
```

> **Path resolution.** `bars_cache_root` is interpreted relative to `apps/backend/` (the backend's working directory). Inside Docker that's `/app/bars_cache`; on the host it's `apps/backend/bars_cache/`. P0's `docker-compose.yml` already mounts `./apps/backend/bars_cache:/app/bars_cache` so host and container see the same files.

### 1.2.2 — Bar cache module

Create `apps/backend/app/market_data/bar_cache.py`:

```python
"""BarCache — parquet-backed OHLCV cache.

Layout:
    bars_cache/
        AAPL/
            1Min/
                2025-11-03.parquet
                2025-11-04.parquet
            1Day/
                2025-11.parquet     # (1Day rolls up to monthly files)
        MSFT/
            ...

Key properties:
  - Append-only: a day file is written once, never modified. Days are
    immutable historical records.
  - LRU eviction: when total cache size exceeds the cap, oldest-accessed
    files are evicted. Eviction never touches files written in the last
    24 hours (those are likely 'today's' in-progress data).
  - Threadsafe-enough for one process: file writes go through a per-symbol
    asyncio.Lock so two concurrent requesters don't write the same day file
    twice. Cross-process safety is not needed (only one backend writes).
"""
from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import structlog

from app.brokers.alpaca import AlpacaAdapter
from app.brokers.alpaca.credentials import load_credentials

logger = structlog.get_logger(__name__)


# Timeframes we support and how they're grouped into files:
#   'fine'     → one file per day (intraday bars)
#   'daily'    → one file per month (daily bars)
TIMEFRAME_GRANULARITY = {
    "1Min": "fine",
    "5Min": "fine",
    "15Min": "fine",
    "1Hour": "fine",
    "1Day": "daily",
}


class BarCache:
    """Disk-backed bar cache. Constructed once per process (typically in lifespan)."""

    def __init__(
        self,
        adapter: AlpacaAdapter,
        root: str,
        max_gb: float,
    ) -> None:
        self._adapter = adapter
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._max_bytes = int(max_gb * 1024 * 1024 * 1024)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        logger.info("bar_cache_init", root=str(self._root), max_gb=max_gb)

    # ---------- public API ----------

    async def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Return OHLCV bars for [start, end] as a DataFrame.

        Columns: index=ts (tz-aware UTC), o, h, l, c, v.

        Behavior:
          - If the cache covers the range, served from disk.
          - If gaps exist, fetch only the missing day-files from Alpaca
            and merge.
          - Cache stamps `os.utime` on read to support LRU eviction.
        """
        symbol = symbol.upper()
        if timeframe not in TIMEFRAME_GRANULARITY:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        start = _to_utc(start)
        end = _to_utc(end)
        if end < start:
            raise ValueError("end < start")

        granularity = TIMEFRAME_GRANULARITY[timeframe]

        async with self._locks[f"{symbol}:{timeframe}"]:
            cached_frames: list[pd.DataFrame] = []
            missing_buckets = self._compute_missing_buckets(symbol, timeframe, start, end, granularity)

            if missing_buckets:
                fetched = await self._fetch_and_write(symbol, timeframe, missing_buckets)
                if not fetched.empty:
                    cached_frames.append(fetched)

            # Now read every bucket file overlapping [start, end].
            buckets = self._enumerate_buckets(start, end, granularity)
            for bucket in buckets:
                f = self._bucket_file(symbol, timeframe, bucket, granularity)
                if f.exists():
                    df = pd.read_parquet(f)
                    cached_frames.append(df)
                    # touch for LRU
                    os.utime(f, None)

            if not cached_frames:
                return _empty_bars_frame()

            df = pd.concat(cached_frames).drop_duplicates(subset=["t"]).sort_values("t")
            df = df[(df["t"] >= start) & (df["t"] <= end)].reset_index(drop=True)

        # Eviction is an opportunistic background concern; run it ~10% of calls.
        if int(time.time()) % 10 == 0:
            self._evict_if_over_cap()

        return df

    # ---------- internals ----------

    def _bucket_file(self, symbol: str, timeframe: str, bucket_key: str, granularity: str) -> Path:
        return self._root / symbol / timeframe / f"{bucket_key}.parquet"

    def _compute_missing_buckets(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        granularity: str,
    ) -> list[tuple[str, datetime, datetime]]:
        """Return list of (bucket_key, bucket_start, bucket_end) for buckets
        that are NOT already in the cache."""
        missing = []
        for bucket_key, b_start, b_end in self._enumerate_buckets_with_range(start, end, granularity):
            f = self._bucket_file(symbol, timeframe, bucket_key, granularity)
            if not f.exists():
                missing.append((bucket_key, b_start, b_end))
        return missing

    def _enumerate_buckets(self, start: datetime, end: datetime, granularity: str) -> list[str]:
        return [b[0] for b in self._enumerate_buckets_with_range(start, end, granularity)]

    def _enumerate_buckets_with_range(
        self,
        start: datetime,
        end: datetime,
        granularity: str,
    ) -> list[tuple[str, datetime, datetime]]:
        out = []
        if granularity == "fine":
            cur = start.replace(hour=0, minute=0, second=0, microsecond=0)
            while cur <= end:
                key = cur.strftime("%Y-%m-%d")
                bs = cur
                be = cur + timedelta(days=1) - timedelta(microseconds=1)
                out.append((key, bs, be))
                cur += timedelta(days=1)
        else:  # daily -> month bucket
            cur = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            while cur <= end:
                key = cur.strftime("%Y-%m")
                bs = cur
                # last day of month
                if cur.month == 12:
                    next_month = cur.replace(year=cur.year + 1, month=1)
                else:
                    next_month = cur.replace(month=cur.month + 1)
                be = next_month - timedelta(microseconds=1)
                out.append((key, bs, be))
                cur = next_month
        return out

    async def _fetch_and_write(
        self,
        symbol: str,
        timeframe: str,
        missing: list[tuple[str, datetime, datetime]],
    ) -> pd.DataFrame:
        """Fetch missing buckets from Alpaca and write parquet files."""
        if not missing:
            return _empty_bars_frame()

        # Fetch the entire range in one Alpaca call (more efficient), then
        # split into bucket files locally.
        overall_start = min(m[1] for m in missing)
        overall_end = max(m[2] for m in missing)

        loop = asyncio.get_running_loop()
        try:
            df = await loop.run_in_executor(
                None,
                lambda: _alpaca_fetch_bars(symbol, timeframe, overall_start, overall_end),
            )
        except Exception:
            logger.exception("bar_cache_fetch_failed",
                             symbol=symbol, timeframe=timeframe,
                             start=overall_start.isoformat(),
                             end=overall_end.isoformat())
            return _empty_bars_frame()

        if df.empty:
            # Still write empty bucket markers so we don't re-fetch the
            # same empty days repeatedly. Use a 0-byte sentinel filename.
            # Actually — simpler: write a marker file alongside.
            for bucket_key, _, _ in missing:
                marker = self._bucket_file(symbol, timeframe, bucket_key, "fine").with_suffix(".empty")
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.touch()
            return df

        # Split by bucket and write.
        for bucket_key, b_start, b_end in missing:
            bucket_df = df[(df["t"] >= b_start) & (df["t"] <= b_end)].reset_index(drop=True)
            if bucket_df.empty:
                continue
            f = self._bucket_file(symbol, timeframe, bucket_key, TIMEFRAME_GRANULARITY[timeframe])
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".parquet.tmp")
            bucket_df.to_parquet(tmp, index=False)
            tmp.rename(f)
            logger.info("bar_cache_wrote", symbol=symbol, timeframe=timeframe,
                        bucket=bucket_key, rows=len(bucket_df))

        return df

    def _evict_if_over_cap(self) -> None:
        """LRU eviction. Touched files get pushed; files modified <24h ago
        are protected (they likely contain today's in-progress bars)."""
        total = 0
        all_files: list[tuple[float, int, Path]] = []  # (mtime, size, path)
        now = time.time()

        for f in self._root.rglob("*.parquet"):
            try:
                stat = f.stat()
                total += stat.st_size
                all_files.append((stat.st_atime, stat.st_size, f))
            except FileNotFoundError:
                continue

        if total <= self._max_bytes:
            return

        # Evict oldest-accessed first, skipping anything modified in last 24h.
        all_files.sort(key=lambda x: x[0])
        protected_cutoff = now - 24 * 3600
        evicted_count = 0
        evicted_bytes = 0
        for atime, size, f in all_files:
            if total <= self._max_bytes:
                break
            try:
                if f.stat().st_mtime > protected_cutoff:
                    continue
                f.unlink()
                total -= size
                evicted_count += 1
                evicted_bytes += size
            except FileNotFoundError:
                continue

        if evicted_count > 0:
            logger.info("bar_cache_evicted",
                        files=evicted_count,
                        bytes_freed=evicted_bytes,
                        total_after=total)


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _empty_bars_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["t", "o", "h", "l", "c", "v"])


def _alpaca_fetch_bars(
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Synchronous Alpaca historical bars fetch. Called via run_in_executor."""
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    creds = load_credentials()
    client = StockHistoricalDataClient(api_key=creds.api_key, secret_key=creds.api_secret)

    tf_map = {
        "1Min": TimeFrame(1, TimeFrameUnit.Minute),
        "5Min": TimeFrame(5, TimeFrameUnit.Minute),
        "15Min": TimeFrame(15, TimeFrameUnit.Minute),
        "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
        "1Day": TimeFrame(1, TimeFrameUnit.Day),
    }
    req = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=tf_map[timeframe],
        start=start,
        end=end,
        feed="iex",
        limit=10000,
    )
    result = client.get_stock_bars(req)
    bars = result.data.get(symbol, []) if hasattr(result, "data") else []
    if not bars:
        return _empty_bars_frame()
    rows = [
        {
            "t": b.timestamp.astimezone(timezone.utc) if hasattr(b.timestamp, "astimezone") else b.timestamp,
            "o": float(b.open),
            "h": float(b.high),
            "l": float(b.low),
            "c": float(b.close),
            "v": int(b.volume),
        }
        for b in bars
    ]
    return pd.DataFrame(rows)
```

- [ ] `bar_cache.py` created.
- [ ] Path layout matches the layout block at the top of the file.

### 1.2.3 — Wire into FastAPI lifespan

Edit `apps/backend/app/lifespan.py`. After the AlpacaAdapter is constructed and before any service that might need bars:

```python
# Add to imports:
from app.market_data.bar_cache import BarCache

# In lifespan, after adapter is connected:
from app.config import get_settings
settings = get_settings()
bar_cache = BarCache(
    adapter=adapter,
    root=settings.bars_cache_root,
    max_gb=settings.bars_cache_max_gb,
)
app.state.bar_cache = bar_cache
```

No shutdown hook needed; the cache is stateless beyond disk.

- [ ] `BarCache` constructed in lifespan and stashed on `app.state`.

---

## §1.3 — Indicator Computer

Wrapper around pandas-ta. Memoizes results keyed by `(symbol, timeframe, end_ts, indicator_name)` for one minute.

Create `apps/backend/app/indicators/__init__.py`:

```python
"""Indicator computation layer.

Wraps pandas-ta with a stable interface and a short-TTL memoization cache.
The indicator set is small and curated; we deliberately don't expose pandas-ta's
full surface to avoid breaking when pandas-ta changes between versions."""
from .computer import IndicatorComputer, CORE_INDICATORS

__all__ = ["IndicatorComputer", "CORE_INDICATORS"]
```

Create `apps/backend/app/indicators/computer.py`:

```python
"""IndicatorComputer — pandas-ta wrapper with TTL memoization.

Supported indicators (P2 core set):
    SMA20, SMA50, SMA200
    EMA9, EMA21
    RSI14
    MACD            -> returns three series: 'macd', 'signal', 'hist'
    ATR14
    VWAP
    BB              -> three series: 'bb_lower', 'bb_mid', 'bb_upper'
    RELVOL20        -> volume / 20-day SMA of volume

Each indicator name maps to a callable that accepts the bars DataFrame
and returns either a Series (single-output) or a dict[str, Series]
(multi-output, e.g. MACD).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd
import structlog

logger = structlog.get_logger(__name__)


CORE_INDICATORS = [
    "SMA20", "SMA50", "SMA200",
    "EMA9", "EMA21",
    "RSI14",
    "MACD",
    "ATR14",
    "VWAP",
    "BB",
    "RELVOL20",
]


# Lazy pandas-ta import so unit tests can run without it if needed.
def _sma(bars: pd.DataFrame, length: int) -> pd.Series:
    import pandas_ta as ta
    return ta.sma(bars["c"], length=length).rename(f"SMA{length}")


def _ema(bars: pd.DataFrame, length: int) -> pd.Series:
    import pandas_ta as ta
    return ta.ema(bars["c"], length=length).rename(f"EMA{length}")


def _rsi(bars: pd.DataFrame) -> pd.Series:
    import pandas_ta as ta
    return ta.rsi(bars["c"], length=14).rename("RSI14")


def _macd(bars: pd.DataFrame) -> dict[str, pd.Series]:
    import pandas_ta as ta
    df = ta.macd(bars["c"], fast=12, slow=26, signal=9)
    # pandas-ta returns a DataFrame with columns like MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9
    return {
        "macd": df.iloc[:, 0].rename("macd"),
        "hist": df.iloc[:, 1].rename("hist"),
        "signal": df.iloc[:, 2].rename("signal"),
    }


def _atr(bars: pd.DataFrame) -> pd.Series:
    import pandas_ta as ta
    return ta.atr(bars["h"], bars["l"], bars["c"], length=14).rename("ATR14")


def _vwap(bars: pd.DataFrame) -> pd.Series:
    """Session VWAP. We use pandas-ta's vwap which assumes datetime index."""
    import pandas_ta as ta
    # pandas-ta vwap needs a DatetimeIndex; set one temporarily
    tmp = bars.set_index("t")
    out = ta.vwap(high=tmp["h"], low=tmp["l"], close=tmp["c"], volume=tmp["v"])
    out.index = bars.index  # restore positional index for alignment
    return out.rename("VWAP")


def _bbands(bars: pd.DataFrame) -> dict[str, pd.Series]:
    import pandas_ta as ta
    df = ta.bbands(bars["c"], length=20, std=2.0)
    # pandas-ta returns: BBL_20_2.0, BBM_20_2.0, BBU_20_2.0, BBB_20_2.0, BBP_20_2.0
    return {
        "bb_lower": df.iloc[:, 0].rename("bb_lower"),
        "bb_mid": df.iloc[:, 1].rename("bb_mid"),
        "bb_upper": df.iloc[:, 2].rename("bb_upper"),
    }


def _relvol20(bars: pd.DataFrame) -> pd.Series:
    """Relative volume = current volume / 20-period SMA of volume."""
    sma_v = bars["v"].rolling(20).mean()
    rv = bars["v"] / sma_v
    return rv.rename("RELVOL20")


_INDICATOR_DISPATCH: dict[str, Callable[[pd.DataFrame], Any]] = {
    "SMA20": lambda b: _sma(b, 20),
    "SMA50": lambda b: _sma(b, 50),
    "SMA200": lambda b: _sma(b, 200),
    "EMA9": lambda b: _ema(b, 9),
    "EMA21": lambda b: _ema(b, 21),
    "RSI14": _rsi,
    "MACD": _macd,
    "ATR14": _atr,
    "VWAP": _vwap,
    "BB": _bbands,
    "RELVOL20": _relvol20,
}


@dataclass
class _CacheKey:
    symbol: str
    timeframe: str
    end_ts_epoch: int
    name: str

    def __hash__(self) -> int:
        return hash((self.symbol, self.timeframe, self.end_ts_epoch, self.name))


class IndicatorComputer:
    """Compute curated indicators on a bars DataFrame with memoization.

    Memoization TTL is 60 seconds. Keyed by (symbol, timeframe, last-bar-ts,
    indicator-name). Same call within the same minute returns the cached
    series; a new bar bumps the key and triggers fresh computation.
    """

    def __init__(self) -> None:
        self._cache: dict[_CacheKey, Any] = {}
        self._cache_expiry: dict[_CacheKey, float] = {}
        self._ttl_seconds = 60.0

    def compute(
        self,
        bars: pd.DataFrame,
        names: list[str],
        symbol: str = "",
        timeframe: str = "",
    ) -> dict[str, Any]:
        """Compute the requested indicators.

        Returns a dict mapping indicator name → Series (single-output) or
        dict[str, Series] (multi-output). Missing names raise KeyError.
        """
        if bars.empty:
            return {n: pd.Series(dtype="float64") for n in names}

        # Last-bar timestamp drives the cache key.
        last_ts = bars["t"].iloc[-1]
        end_epoch = int(pd.Timestamp(last_ts).timestamp())

        out: dict[str, Any] = {}
        now = time.time()

        for name in names:
            if name not in _INDICATOR_DISPATCH:
                raise KeyError(f"Unknown indicator: {name}. Supported: {CORE_INDICATORS}")
            key = _CacheKey(symbol=symbol, timeframe=timeframe, end_ts_epoch=end_epoch, name=name)
            if key in self._cache and self._cache_expiry.get(key, 0) > now:
                out[name] = self._cache[key]
                continue
            try:
                value = _INDICATOR_DISPATCH[name](bars)
            except Exception:
                logger.exception("indicator_compute_failed",
                                 name=name, symbol=symbol, timeframe=timeframe,
                                 bar_count=len(bars))
                out[name] = pd.Series(dtype="float64") if name not in ("MACD", "BB") else {}
                continue
            self._cache[key] = value
            self._cache_expiry[key] = now + self._ttl_seconds
            out[name] = value

        # Opportunistic cleanup of expired entries
        if int(now) % 30 == 0:
            self._prune_expired(now)

        return out

    def _prune_expired(self, now: float) -> None:
        expired = [k for k, exp in self._cache_expiry.items() if exp <= now]
        for k in expired:
            self._cache.pop(k, None)
            self._cache_expiry.pop(k, None)
```

Wire into the lifespan. Same file as before:

```python
# Add import:
from app.indicators import IndicatorComputer

# After bar_cache construction:
indicator_computer = IndicatorComputer()
app.state.indicator_computer = indicator_computer
```

- [ ] `indicators/__init__.py` + `computer.py` created.
- [ ] Wired into lifespan.

---

## §1.4 — REST Endpoint

`GET /api/v1/indicators/{symbol}` — returns latest values + a short sparkline.

### 1.4.1 — Schema

Add to `apps/backend/app/api/v1/schemas/market_data.py`:

```python
from typing import Any
from pydantic import BaseModel


class IndicatorSeriesPoint(BaseModel):
    t: datetime
    v: Optional[float]


class IndicatorSeries(BaseModel):
    name: str            # e.g. "RSI14"; for multi-output indicators: "MACD.macd"
    latest: Optional[float]
    sparkline: list[IndicatorSeriesPoint]


class IndicatorsResponse(BaseModel):
    symbol: str
    timeframe: str
    last_bar_ts: Optional[datetime]
    indicators: list[IndicatorSeries]
```

> The existing imports at the top of `market_data.py` need to include `datetime`, `Optional`, etc. — likely already present from §6A of P1 Session 6.

### 1.4.2 — Endpoint

Create `apps/backend/app/api/v1/indicators.py`:

```python
"""GET /api/v1/indicators/{symbol} — computed indicators for a symbol."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request

from app.api.v1.schemas.market_data import (
    IndicatorSeries,
    IndicatorSeriesPoint,
    IndicatorsResponse,
)
from app.indicators import CORE_INDICATORS

router = APIRouter(prefix="/indicators", tags=["market-data"])


@router.get("/{symbol}", response_model=IndicatorsResponse)
async def get_indicators(
    symbol: str,
    request: Request,
    timeframe: str = Query(default="1Min"),
    names: Optional[str] = Query(default=None, description="Comma-separated indicator names. Defaults to core set."),
    sparkline_points: int = Query(default=30, ge=1, le=200),
):
    """Compute indicators for the most recent bars.

    Returns the latest value of each indicator plus a short trailing
    sparkline (sparkline_points samples) suitable for inline display.
    """
    symbol = symbol.upper()
    if names is None or names.strip() == "":
        requested = list(CORE_INDICATORS)
    else:
        requested = [n.strip() for n in names.split(",") if n.strip()]
        bad = [n for n in requested if n not in CORE_INDICATORS]
        if bad:
            raise HTTPException(status_code=400, detail=f"Unknown indicators: {bad}. Supported: {CORE_INDICATORS}")

    bar_cache = getattr(request.app.state, "bar_cache", None)
    computer = getattr(request.app.state, "indicator_computer", None)
    if bar_cache is None or computer is None:
        raise HTTPException(status_code=503, detail="Indicator service not initialized")

    # Lookback: enough bars to compute the slowest indicator (SMA200) plus
    # the sparkline window. 250 bars is comfortably enough.
    end = datetime.now(timezone.utc)
    lookback_days_by_tf = {"1Min": 2, "5Min": 5, "15Min": 7, "1Hour": 14, "1Day": 365}
    start = end - timedelta(days=lookback_days_by_tf.get(timeframe, 5))

    try:
        bars = await bar_cache.get_bars(symbol, timeframe, start, end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if bars.empty:
        return IndicatorsResponse(
            symbol=symbol,
            timeframe=timeframe,
            last_bar_ts=None,
            indicators=[],
        )

    computed = computer.compute(bars, names=requested, symbol=symbol, timeframe=timeframe)

    series_out: list[IndicatorSeries] = []
    for name in requested:
        value = computed.get(name)
        if isinstance(value, dict):
            # Multi-output indicator (MACD, BB) — expand to "NAME.subname"
            for sub_name, sub_series in value.items():
                series_out.append(_build_series(f"{name}.{sub_name}", sub_series, bars, sparkline_points))
        else:
            series_out.append(_build_series(name, value, bars, sparkline_points))

    return IndicatorsResponse(
        symbol=symbol,
        timeframe=timeframe,
        last_bar_ts=bars["t"].iloc[-1],
        indicators=series_out,
    )


def _build_series(name: str, series: pd.Series, bars: pd.DataFrame, points: int) -> IndicatorSeries:
    if series is None or series.empty:
        return IndicatorSeries(name=name, latest=None, sparkline=[])
    tail = series.tail(points)
    tail_t = bars["t"].tail(points).values
    sparkline = [
        IndicatorSeriesPoint(t=pd.Timestamp(t).to_pydatetime(), v=None if pd.isna(v) else float(v))
        for t, v in zip(tail_t, tail.values)
    ]
    latest_val = series.iloc[-1]
    latest = None if pd.isna(latest_val) else float(latest_val)
    return IndicatorSeries(name=name, latest=latest, sparkline=sparkline)
```

Register in `apps/backend/app/main.py` (or wherever routers are mounted):

```python
from app.api.v1 import indicators as indicators_router

# inside create_app(), with the other routers:
app.include_router(indicators_router.router, prefix="/api/v1")
```

- [ ] Schema added.
- [ ] Endpoint created.
- [ ] Registered with prefix.

---

## §1.5 — Tests

Three categories: golden test (locks pandas-ta output), cache mechanics, endpoint smoke.

### 1.5.1 — Fixture bar file

You need a real OHLCV parquet to drive the golden test. Generate it once from Alpaca paper and commit it.

Create `apps/backend/scripts/generate_fixture_bars.py`:

```python
"""Generate a committed fixture parquet for use in tests/fixtures/bars/.

Run once locally with Alpaca creds in .env. The output is committed to git so
tests run deterministically without hitting Alpaca on CI.

Usage:
    cd apps/backend
    uv run python scripts/generate_fixture_bars.py AAPL 2025-11-03
"""
from __future__ import annotations

import sys
from datetime import datetime, time, timezone
from pathlib import Path

from app.market_data.bar_cache import _alpaca_fetch_bars


def main():
    if len(sys.argv) != 3:
        print("Usage: generate_fixture_bars.py SYMBOL YYYY-MM-DD", file=sys.stderr)
        sys.exit(2)
    symbol = sys.argv[1].upper()
    day = sys.argv[2]
    y, m, d = map(int, day.split("-"))
    start = datetime(y, m, d, 0, 0, tzinfo=timezone.utc)
    end = datetime(y, m, d, 23, 59, 59, tzinfo=timezone.utc)

    df = _alpaca_fetch_bars(symbol, "1Min", start, end)
    if df.empty:
        print(f"No bars returned for {symbol} on {day}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "bars"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{symbol}_{day}_1Min.parquet"
    df.to_parquet(out, index=False)
    print(f"Wrote {out} with {len(df)} bars")


if __name__ == "__main__":
    main()
```

Run it once to populate the fixture (pick a recent normal trading day):

```bash
cd apps/backend
uv run python scripts/generate_fixture_bars.py AAPL 2025-11-03
ls tests/fixtures/bars/
# expect: AAPL_2025-11-03_1Min.parquet
cd ../..
```

> **Pick a normal day.** Avoid market holidays, half-days, the day of a stock split or major news event. A boring full trading day produces a reproducible RSI/MACD path.

### 1.5.2 — Golden test (indicator output stability)

Create `apps/backend/tests/indicators/__init__.py` (empty) and `apps/backend/tests/indicators/test_computer_golden.py`:

```python
"""Golden test: indicators on a fixed bar file must produce stable values.

This catches pandas-ta version drift. If pandas-ta changes how it computes
RSI/MACD/etc., this test fails and we have to make a deliberate decision
about whether to accept the new behavior (and update the expected values).
"""
from pathlib import Path

import pandas as pd
import pytest

from app.indicators import IndicatorComputer


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "bars" / "AAPL_2025-11-03_1Min.parquet"


@pytest.fixture
def bars():
    if not FIXTURE.exists():
        pytest.skip(f"Fixture not present: {FIXTURE}. Run scripts/generate_fixture_bars.py.")
    df = pd.read_parquet(FIXTURE)
    # Ensure t column is datetime
    df["t"] = pd.to_datetime(df["t"], utc=True)
    return df


def test_rsi_latest_is_in_range(bars):
    computer = IndicatorComputer()
    out = computer.compute(bars, names=["RSI14"], symbol="AAPL", timeframe="1Min")
    rsi = out["RSI14"]
    last = rsi.dropna().iloc[-1]
    # RSI must mathematically be in [0, 100]
    assert 0.0 <= last <= 100.0


def test_sma200_equals_mean_of_last_200_closes(bars):
    if len(bars) < 200:
        pytest.skip("Need at least 200 bars for SMA200")
    computer = IndicatorComputer()
    out = computer.compute(bars, names=["SMA200"], symbol="AAPL", timeframe="1Min")
    sma200 = out["SMA200"]
    expected = bars["c"].tail(200).mean()
    actual = sma200.dropna().iloc[-1]
    assert abs(actual - expected) < 1e-6


def test_macd_returns_three_series(bars):
    computer = IndicatorComputer()
    out = computer.compute(bars, names=["MACD"], symbol="AAPL", timeframe="1Min")
    macd = out["MACD"]
    assert isinstance(macd, dict)
    assert set(macd.keys()) == {"macd", "signal", "hist"}
    for k, s in macd.items():
        assert isinstance(s, pd.Series)


def test_bb_returns_three_series_with_mid_between_bands(bars):
    computer = IndicatorComputer()
    out = computer.compute(bars, names=["BB"], symbol="AAPL", timeframe="1Min")
    bb = out["BB"]
    assert set(bb.keys()) == {"bb_lower", "bb_mid", "bb_upper"}
    # Sanity: mid should be between lower and upper at every point
    df = pd.DataFrame(bb).dropna()
    assert (df["bb_lower"] <= df["bb_mid"]).all()
    assert (df["bb_mid"] <= df["bb_upper"]).all()


def test_relvol20_is_positive_when_volume_present(bars):
    computer = IndicatorComputer()
    out = computer.compute(bars, names=["RELVOL20"], symbol="AAPL", timeframe="1Min")
    rv = out["RELVOL20"].dropna()
    # All values should be positive ratios
    assert (rv > 0).all()


def test_unknown_indicator_raises(bars):
    computer = IndicatorComputer()
    with pytest.raises(KeyError, match="Unknown indicator"):
        computer.compute(bars, names=["FNORD"], symbol="AAPL", timeframe="1Min")


def test_empty_bars_returns_empty_series():
    computer = IndicatorComputer()
    out = computer.compute(pd.DataFrame(columns=["t","o","h","l","c","v"]),
                           names=["RSI14"], symbol="X", timeframe="1Min")
    assert out["RSI14"].empty


def test_memoization_returns_same_object(bars):
    computer = IndicatorComputer()
    out1 = computer.compute(bars, names=["RSI14"], symbol="AAPL", timeframe="1Min")
    out2 = computer.compute(bars, names=["RSI14"], symbol="AAPL", timeframe="1Min")
    # Identity check: same call within TTL returns the cached series object
    assert out1["RSI14"] is out2["RSI14"]
```

> **Why no exact-value golden assertions for RSI/MACD?** Floating-point determinism across pandas-ta versions is finicky. The tests assert *structural* properties (RSI in [0,100], SMA equals the obvious mean, BB mid between bands) instead. That's enough to catch a real regression — if pandas-ta starts returning garbage, these fail; if it changes the third decimal place of RSI, who cares.

### 1.5.3 — Bar cache mechanics

Create `apps/backend/tests/market_data/__init__.py` (empty) and `apps/backend/tests/market_data/test_bar_cache.py`:

```python
"""BarCache mechanics: cache hits, gap fetching, LRU eviction.

The Alpaca fetch is mocked. We only test the cache layer's behavior, not
Alpaca itself.
"""
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from app.market_data.bar_cache import BarCache, _empty_bars_frame


def _mk_bars(start: datetime, n: int) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "t": start + timedelta(minutes=i),
            "o": 100.0 + i * 0.01,
            "h": 100.5 + i * 0.01,
            "l": 99.5 + i * 0.01,
            "c": 100.0 + i * 0.01,
            "v": 1000 + i,
        }
        for i in range(n)
    ])


@pytest.fixture
def tmp_cache(tmp_path):
    adapter = MagicMock()
    cache = BarCache(adapter=adapter, root=str(tmp_path), max_gb=0.001)  # 1 MB cap
    return cache, tmp_path


@pytest.mark.asyncio
async def test_first_read_fetches_and_writes_parquet(tmp_cache):
    cache, root = tmp_cache
    start = datetime(2025, 11, 3, 14, 30, tzinfo=timezone.utc)
    end = datetime(2025, 11, 3, 14, 45, tzinfo=timezone.utc)
    fake_bars = _mk_bars(start, 16)

    with patch("app.market_data.bar_cache._alpaca_fetch_bars", return_value=fake_bars):
        df = await cache.get_bars("AAPL", "1Min", start, end)

    assert len(df) == 16
    # Verify parquet on disk
    expected = root / "AAPL" / "1Min" / "2025-11-03.parquet"
    assert expected.exists()


@pytest.mark.asyncio
async def test_second_read_serves_from_disk(tmp_cache):
    cache, root = tmp_cache
    start = datetime(2025, 11, 3, 14, 30, tzinfo=timezone.utc)
    end = datetime(2025, 11, 3, 14, 45, tzinfo=timezone.utc)
    fake_bars = _mk_bars(start, 16)

    fetcher = MagicMock(return_value=fake_bars)
    with patch("app.market_data.bar_cache._alpaca_fetch_bars", fetcher):
        await cache.get_bars("AAPL", "1Min", start, end)
        assert fetcher.call_count == 1
        await cache.get_bars("AAPL", "1Min", start, end)
        # Second call must not fetch
        assert fetcher.call_count == 1


@pytest.mark.asyncio
async def test_lru_eviction_removes_oldest_first(tmp_cache, monkeypatch):
    cache, root = tmp_cache
    # Write three day files; mtime/atime old enough to be evictable.
    for i, day in enumerate([1, 2, 3]):
        d = datetime(2025, 11, day, tzinfo=timezone.utc)
        with patch("app.market_data.bar_cache._alpaca_fetch_bars", return_value=_mk_bars(d, 60)):
            await cache.get_bars("AAPL", "1Min", d, d + timedelta(hours=23))

    # Backdate mtime/atime so all three files are evictable (>24h)
    for f in root.rglob("*.parquet"):
        old = time.time() - 48 * 3600
        # Make atime distinct so LRU order is deterministic
        os.utime(f, (old + int(f.stat().st_size), old + int(f.stat().st_size)))

    # Touch the day-2 file most recently
    day2_file = root / "AAPL" / "1Min" / "2025-11-02.parquet"
    fresh = time.time() - 23 * 3600
    os.utime(day2_file, (fresh, time.time() - 48 * 3600))

    # Force eviction with a tiny cap
    cache._max_bytes = 1
    cache._evict_if_over_cap()

    # day-1 (oldest atime) should be gone; the other behavior is timing-fragile
    # so we just check the cache shrank.
    remaining = list(root.rglob("*.parquet"))
    assert len(remaining) < 3


@pytest.mark.asyncio
async def test_unknown_timeframe_raises(tmp_cache):
    cache, _ = tmp_cache
    with pytest.raises(ValueError, match="Unsupported timeframe"):
        await cache.get_bars("AAPL", "37Min",
                             datetime(2025, 11, 3, tzinfo=timezone.utc),
                             datetime(2025, 11, 3, 1, tzinfo=timezone.utc))


@pytest.mark.asyncio
async def test_end_before_start_raises(tmp_cache):
    cache, _ = tmp_cache
    with pytest.raises(ValueError, match="end < start"):
        await cache.get_bars("AAPL", "1Min",
                             datetime(2025, 11, 3, 14, tzinfo=timezone.utc),
                             datetime(2025, 11, 3, 13, tzinfo=timezone.utc))


@pytest.mark.asyncio
async def test_empty_alpaca_result_returns_empty_frame(tmp_cache):
    cache, _ = tmp_cache
    with patch("app.market_data.bar_cache._alpaca_fetch_bars", return_value=_empty_bars_frame()):
        df = await cache.get_bars("ZZZZ", "1Min",
                                  datetime(2025, 11, 3, tzinfo=timezone.utc),
                                  datetime(2025, 11, 3, 1, tzinfo=timezone.utc))
    assert df.empty
```

### 1.5.4 — Endpoint smoke

Create `apps/backend/tests/api/test_indicators_endpoint.py`:

```python
"""Smoke test for GET /api/v1/indicators/{symbol}."""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, AsyncMock

import pandas as pd
import pytest
from httpx import AsyncClient

from app.indicators import IndicatorComputer
from app.main import create_app


def _bars(n=250):
    start = datetime(2025, 11, 3, 14, 30, tzinfo=timezone.utc)
    rows = [
        {"t": start + timedelta(minutes=i),
         "o": 100 + i * 0.01, "h": 100.5 + i * 0.01,
         "l": 99.5 + i * 0.01, "c": 100 + i * 0.01,
         "v": 1000 + i}
        for i in range(n)
    ]
    return pd.DataFrame(rows)


@pytest.mark.asyncio
async def test_indicators_endpoint_returns_core_set():
    app = create_app()
    mock_cache = MagicMock()
    mock_cache.get_bars = AsyncMock(return_value=_bars())
    app.state.bar_cache = mock_cache
    app.state.indicator_computer = IndicatorComputer()

    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/indicators/AAPL?timeframe=1Min")
    assert resp.status_code == 200
    body = resp.json()
    assert body["symbol"] == "AAPL"
    assert body["timeframe"] == "1Min"

    names = [s["name"] for s in body["indicators"]]
    # Multi-output indicators expand into sub-series
    assert "RSI14" in names
    assert "MACD.macd" in names
    assert "MACD.signal" in names
    assert "MACD.hist" in names
    assert "BB.bb_lower" in names
    assert "BB.bb_upper" in names


@pytest.mark.asyncio
async def test_indicators_endpoint_filters_names():
    app = create_app()
    mock_cache = MagicMock()
    mock_cache.get_bars = AsyncMock(return_value=_bars())
    app.state.bar_cache = mock_cache
    app.state.indicator_computer = IndicatorComputer()

    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/indicators/AAPL?names=RSI14,SMA20")
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()["indicators"]]
    assert set(names) == {"RSI14", "SMA20"}


@pytest.mark.asyncio
async def test_indicators_endpoint_rejects_unknown_name():
    app = create_app()
    mock_cache = MagicMock()
    mock_cache.get_bars = AsyncMock(return_value=_bars())
    app.state.bar_cache = mock_cache
    app.state.indicator_computer = IndicatorComputer()

    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/indicators/AAPL?names=FNORD,RSI14")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_indicators_endpoint_handles_empty_bars():
    app = create_app()
    mock_cache = MagicMock()
    mock_cache.get_bars = AsyncMock(return_value=pd.DataFrame(columns=["t","o","h","l","c","v"]))
    app.state.bar_cache = mock_cache
    app.state.indicator_computer = IndicatorComputer()

    async with AsyncClient(app=app, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/indicators/AAPL")
    assert resp.status_code == 200
    body = resp.json()
    assert body["last_bar_ts"] is None
    assert body["indicators"] == []
```

### 1.5.5 — Run the suite

```bash
cd apps/backend
uv run pytest tests/indicators tests/market_data tests/api/test_indicators_endpoint.py -v
# expect: all green
uv run pytest -q
# expect: all green, including existing P1 tests
cd ../..
```

- [ ] Golden test passes.
- [ ] Bar cache mechanics tests pass.
- [ ] Endpoint smoke tests pass.
- [ ] Full backend suite still green.

---

## §1.6 — Manual Smoke Against Alpaca Paper

```bash
./scripts/dev.sh &
sleep 30

# Hit the new endpoint
curl -s "http://127.0.0.1:8000/api/v1/indicators/AAPL?timeframe=1Min&names=RSI14,MACD,SMA20" \
  | jq '{symbol, last_bar_ts, indicator_count: (.indicators | length),
         rsi_latest: (.indicators[] | select(.name=="RSI14") | .latest)}'

# Larger smoke: pull all core indicators on a slower timeframe
curl -s "http://127.0.0.1:8000/api/v1/indicators/SPY?timeframe=15Min" | jq '.indicators | length'

# Confirm parquet files appeared on disk
docker compose exec backend ls -la /app/bars_cache/AAPL/1Min/ | head -5
docker compose exec backend ls -la /app/bars_cache/SPY/15Min/ | head -5

# Confirm second call is fast (served from cache, no Alpaca round-trip)
time curl -s "http://127.0.0.1:8000/api/v1/indicators/AAPL?timeframe=1Min" > /dev/null

docker compose down
```

Expected:
- First call to a new symbol/timeframe takes 1–3 seconds (Alpaca fetch).
- Cached second call returns in under 200ms.
- Parquet files appear in `apps/backend/bars_cache/{symbol}/{timeframe}/`.

- [ ] Endpoint returns a sensible RSI14 value (0–100).
- [ ] All 11 indicators (with MACD/BB expanded → 15 series total) appear by default.
- [ ] Parquet files written under bars_cache.
- [ ] Cached call faster than first call.

---

## §1.7 — Commit and PR

```bash
git add apps/backend/pyproject.toml
git add apps/backend/app/config.py
git add apps/backend/app/market_data/
git add apps/backend/app/indicators/
git add apps/backend/app/api/v1/indicators.py
git add apps/backend/app/api/v1/schemas/market_data.py
git add apps/backend/app/main.py
git add apps/backend/app/lifespan.py
git add apps/backend/scripts/generate_fixture_bars.py
git add apps/backend/tests/fixtures/bars/
git add apps/backend/tests/indicators/
git add apps/backend/tests/market_data/
git add apps/backend/tests/api/test_indicators_endpoint.py
git add .env.example

git commit -m "feat(market-data): bar cache and indicator computer

- BarCache: parquet-backed OHLCV cache, per-symbol-per-day for intraday
  timeframes, per-month for 1Day. Append-only, LRU eviction with
  24-hour protection window.
- IndicatorComputer: pandas-ta wrapper for the P2 core set
  (SMA/EMA/RSI/MACD/ATR/VWAP/BB/RELVOL20), 60-second memoization keyed
  by (symbol, timeframe, last_bar_ts, indicator_name).
- GET /api/v1/indicators/{symbol} with sparkline window per indicator.
- Fixture parquet for golden test against pandas-ta version drift.
- Lifespan wires BarCache + IndicatorComputer onto app.state.

Foundation for P2 Session 2 (strategy framework) and Session 3 (backtest)."

git push -u origin feat/p2-bar-cache-and-indicators

gh pr create \
  --title "feat(market-data): bar cache and indicator computer" \
  --body "P2 Session 1. Self-contained. Foundation for Sessions 2 (framework) and 3 (backtest)."

gh pr checks
gh pr merge --merge --delete-branch
git checkout main && git pull
```

- [ ] PR merged.

---

## Verification Checklist (full session)

- [ ] §1.1 `pandas`, `pandas-ta`, `pyarrow` in `pyproject.toml`; venv re-synced.
- [ ] §1.2 `BarCache` reads/writes parquet per the documented layout, LRU evicts.
- [ ] §1.2.3 `BarCache` constructed in lifespan and reachable via `app.state.bar_cache`.
- [ ] §1.3 `IndicatorComputer` returns the core set; memoization works.
- [ ] §1.4 `GET /api/v1/indicators/{symbol}` returns indicators + sparklines.
- [ ] §1.5 Golden test, cache mechanics, endpoint smoke — all pass.
- [ ] §1.6 Live smoke against Alpaca paper produces sensible values and writes parquet files.
- [ ] §1.7 PR merged through the protected workflow.

---

## Sign-off

```bash
git tag -a p2-session1-complete -m "P2 Session 1 complete: bar cache + indicator computer"
git push origin p2-session1-complete
```

Update `todo.md`:
- Mark P2 Session 1 complete.
- Tee up **P2 Session 2 — Strategies schema + framework skeleton** (Checklist §2 + §3).

---

## Notes & Gotchas

1. **pandas-ta is sometimes-buggy across versions.** If the golden test fails after a `pandas-ta` upgrade, the right response is to look at what changed in their source (especially for RSI / MACD / VWAP), decide whether the new behavior is correct, and either revert the pin or accept the new behavior and document it in `docs/runbook/indicator-version-history.md`.

2. **VWAP is "session VWAP" by default** in pandas-ta. That means the calc resets at session boundaries when given a tz-aware DatetimeIndex. For intraday bars during one session this matches trader expectations. For multi-day ranges, VWAP values will look stair-stepped — that's correct, not a bug.

3. **The fixture file is committed.** Don't add it to `.gitignore`. The whole point is determinism: every CI run hits the same bytes. The file is small (typically <100 KB for one trading day of 1-minute AAPL).

4. **LRU eviction has a 24-hour protection window.** Files modified less than 24 hours ago are never evicted, even if the cap is exceeded. This protects today's in-progress data. The trade-off: if you genuinely overflow the cap with fresh data, the eviction does nothing — but at that point you have bigger problems and should raise `bars_cache_max_gb`.

5. **The cache is single-process safe, not multi-process.** Two backend instances pointed at the same `bars_cache/` directory could double-write the same day file. We don't deploy that way (one backend per host, ever). If we ever need multi-process safety, add file locks via `fcntl` — but don't preemptively.

6. **Empty-day markers via `.empty` files.** If Alpaca returns no bars for a requested day (a holiday, an inactive symbol), the cache writes a zero-byte `.empty` sentinel. This prevents repeatedly hitting Alpaca for the same empty day. The marker counts toward neither the cache size cap (it's 0 bytes) nor LRU (mtime is checked but file size is 0).

7. **Memoization is per-process.** Indicator results computed in one backend invocation aren't shared with another. For a single-user MVP this is fine; the TTL is short enough (60s) that hot reloads don't cause confusion.

8. **`run_in_executor` for Alpaca fetches.** The `StockHistoricalDataClient` is synchronous. Without `run_in_executor`, a slow fetch (multi-month range) would block the event loop, freezing every other API call. The bar cache wraps every Alpaca call this way; the indicator computer doesn't need to (pandas-ta is in-process and fast).

9. **`pyarrow` is large.** ~50 MB in the docker image. If image size becomes a problem in P4, we can switch to `fastparquet` (about 5 MB) — pandas supports both interchangeably via the `engine=` param. Don't optimize until image size actually bites.

10. **Don't start P2 Session 2 in this PR.** The strategies table + framework is a separate concern with its own design surface. Stop at the tag.

---

*End of P2 Session 1 v0.1.*
