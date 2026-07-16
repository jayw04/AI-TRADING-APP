"""BarCache — parquet-backed OHLCV cache.

Layout::

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
  - **Append-only**: a day/month file is written once, never modified. Days
    are immutable historical records.
  - **LRU eviction**: when total cache size exceeds the cap, oldest-accessed
    files are evicted. Eviction never touches files modified in the last
    24 hours (those are likely "today's" in-progress data).
  - **Threadsafe-enough for one process**: file writes go through a
    per-(symbol, timeframe) asyncio.Lock so two concurrent requesters don't
    write the same day file twice. Cross-process safety is not needed
    (only one backend writes).
"""

from __future__ import annotations

import asyncio
import functools
import os
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import structlog

from app.brokers.alpaca import AlpacaAdapter
from app.brokers.alpaca.credentials import load_credentials

logger = structlog.get_logger(__name__)


# Timeframes we support, and how they're grouped into files:
#   'fine'   → one file per day (intraday)
#   'daily'  → one file per month (daily bars)
TIMEFRAME_GRANULARITY: dict[str, str] = {
    "1Min": "fine",
    "5Min": "fine",
    "15Min": "fine",
    "1Hour": "fine",
    "1Day": "daily",
}

# Alpaca returns at most this many bars per request. A response of *exactly* this
# size means the span was (possibly) truncated at the page boundary and must be
# continued — never assumed complete (ADR 0033, Historical Data Integrity).
_PAGE_LIMIT = 10000
# Safety cap on a single cold fetch (≤ _MAX_PAGES × _PAGE_LIMIT bars). If hit, we
# stop and leave the un-fetched tail *missing* (re-fetchable), never poisoned.
_MAX_PAGES = 500


class BarCache:
    """Disk-backed bar cache. One instance per backend process."""

    def __init__(
        self,
        adapter: AlpacaAdapter | None,
        root: str,
        max_gb: float,
    ) -> None:
        # The adapter is held for symmetry (and so tests can pass MagicMock);
        # bar fetches actually use the historical data client directly because
        # AlpacaAdapter wraps the trading client, not the market-data client.
        self._adapter = adapter
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._max_bytes = int(max_gb * 1024 * 1024 * 1024)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        # In-memory ring buffer of streamed 1-minute bars per symbol, populated
        # by BarStreamService (P4 §8). Not persisted to parquet — the historical
        # pull that subsumes the streamed range is the persistence path.
        self._streaming_buffer: dict[str, list[dict[str, Any]]] = {}
        self._max_buffer_bars: int = 500
        # Last time the still-open bucket (current month/day) was re-fetched, keyed
        # by "symbol:timeframe:bucket". In-memory throttle (resets on restart, which
        # forces one fresh re-fetch on boot — the desired behavior). NOT mtime-based:
        # reads os.utime() the file for LRU, so file mtime ≠ last fetch.
        self._last_open_fetch: dict[str, datetime] = {}
        logger.info("bar_cache_init", root=str(self._root), max_gb=max_gb)

    # The current, still-open bucket is re-fetched at most once per these windows,
    # so newly-printed bars land instead of a partial file freezing the cache.
    _OPEN_REFRESH_FINE = timedelta(minutes=1)  # intraday day-bucket
    _OPEN_REFRESH_COARSE = timedelta(hours=1)  # daily month-bucket

    # ---------- public API ----------

    async def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Return OHLCV bars for ``[start, end]`` as a DataFrame.

        Columns: ``t`` (tz-aware UTC datetime), ``o``, ``h``, ``l``, ``c``,
        ``v``. If the cache covers the range, served from disk. If gaps exist,
        the missing buckets are fetched from Alpaca, written, and merged.
        Reads stamp ``os.utime`` on the file to support LRU eviction.
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
            missing = self._compute_missing_buckets(symbol, timeframe, start, end, granularity)
            if missing:
                await self._fetch_and_write(symbol, timeframe, missing, granularity)

            cached_frames: list[pd.DataFrame] = []
            for bucket_key, _bs, _be in self._enumerate_buckets_with_range(
                start, end, granularity
            ):
                f = self._bucket_file(symbol, timeframe, bucket_key)
                if f.exists():
                    cached_frames.append(pd.read_parquet(f))
                    os.utime(f, None)  # touch for LRU

            if not cached_frames:
                return _empty_bars_frame()

            df = pd.concat(cached_frames).drop_duplicates(subset=["t"]).sort_values("t")
            df = df[(df["t"] >= start) & (df["t"] <= end)].reset_index(drop=True)

        # Opportunistic eviction. Triggers ~10% of the time so we don't pay
        # the directory walk on every read.
        if int(time.time()) % 10 == 0:
            self._evict_if_over_cap()

        return df

    async def append_streamed_bar(self, symbol: str, bar: Any) -> None:
        """Append a streamed 1-minute bar to the in-memory buffer for ``symbol``.

        ``bar`` is duck-typed: must expose ``ts``, ``open``, ``high``, ``low``,
        ``close``, ``volume`` attributes (e.g. ``StreamedBar``). Persistence to
        parquet happens via the next historical pull, not here.
        """
        symbol = symbol.upper()
        buf = self._streaming_buffer.setdefault(symbol, [])
        buf.append(
            {
                "t": bar.ts,
                "o": float(bar.open),
                "h": float(bar.high),
                "l": float(bar.low),
                "c": float(bar.close),
                "v": float(bar.volume),
            }
        )
        if len(buf) > self._max_buffer_bars:
            del buf[: len(buf) - self._max_buffer_bars]

    async def get_latest_bar(self, symbol: str) -> dict[str, Any] | None:
        """Most recent known bar for ``symbol``.

        First checks the in-memory streaming buffer; falls back to the
        parquet cache for the last 2 days at 1Min. Returns a dict shaped
        like ``{t, o, h, l, c, v}`` or ``None``.
        """
        symbol = symbol.upper()
        buf = self._streaming_buffer.get(symbol)
        if buf:
            return dict(buf[-1])
        try:
            now = datetime.now(UTC)
            df = await self.get_bars(symbol, "1Min", now - timedelta(days=2), now)
            if df.empty:
                return None
            row = df.iloc[-1]
            return {
                "t": row["t"],
                "o": float(row["o"]),
                "h": float(row["h"]),
                "l": float(row["l"]),
                "c": float(row["c"]),
                "v": float(row["v"]),
            }
        except Exception:
            return None

    # ---------- internals ----------

    def _bucket_file(self, symbol: str, timeframe: str, bucket_key: str) -> Path:
        return self._root / symbol / timeframe / f"{bucket_key}.parquet"

    def _compute_missing_buckets(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        granularity: str,
    ) -> list[tuple[str, datetime, datetime]]:
        now = datetime.now(UTC)
        refresh = (
            self._OPEN_REFRESH_FINE if granularity == "fine" else self._OPEN_REFRESH_COARSE
        )
        missing = []
        for bucket_key, b_start, b_end in self._enumerate_buckets_with_range(
            start, end, granularity
        ):
            f = self._bucket_file(symbol, timeframe, bucket_key)
            marker = f.with_suffix(".empty")
            # ``b_end >= now`` → this is the current, still-OPEN period (current
            # month for daily, current day for intraday). Its cached file may be
            # missing bars printed since the last fetch — a partial file must NOT
            # freeze the cache (the bug behind weeks-stale bars).
            is_open = b_end >= now
            tf_key = f"{symbol}:{timeframe}:{bucket_key}"
            if not f.exists() and not marker.exists():
                missing.append((bucket_key, b_start, b_end))
                if is_open:
                    self._last_open_fetch[tf_key] = now  # start its refresh clock
                continue
            # Existing file: trust past buckets; re-fetch the open one, throttled
            # to ≤ once per bar period so we don't hammer Alpaca on every read.
            if is_open:
                last = self._last_open_fetch.get(tf_key)
                if last is None or (now - last) >= refresh:
                    missing.append((bucket_key, b_start, b_end))
                    self._last_open_fetch[tf_key] = now
        return missing

    def _enumerate_buckets_with_range(
        self,
        start: datetime,
        end: datetime,
        granularity: str,
    ) -> list[tuple[str, datetime, datetime]]:
        out: list[tuple[str, datetime, datetime]] = []
        if granularity == "fine":
            cur = start.replace(hour=0, minute=0, second=0, microsecond=0)
            while cur <= end:
                key = cur.strftime("%Y-%m-%d")
                bs = cur
                be = cur + timedelta(days=1) - timedelta(microseconds=1)
                out.append((key, bs, be))
                cur += timedelta(days=1)
        else:  # daily → monthly bucket
            cur = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            while cur <= end:
                key = cur.strftime("%Y-%m")
                bs = cur
                if cur.month == 12:
                    next_month = cur.replace(year=cur.year + 1, month=1)
                else:
                    next_month = cur.replace(month=cur.month + 1)
                be = next_month - timedelta(microseconds=1)
                out.append((key, bs, be))
                cur = next_month
        return out

    def _write_empty_marker(self, symbol: str, timeframe: str, bucket_key: str) -> None:
        """Write a zero-byte ``.empty`` marker so a genuinely-empty bucket
        (holiday, inactive symbol) is not re-fetched forever."""
        marker = self._bucket_file(symbol, timeframe, bucket_key).with_suffix(".empty")
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()

    async def _fetch_and_write(
        self,
        symbol: str,
        timeframe: str,
        missing: list[tuple[str, datetime, datetime]],
        granularity: str,
    ) -> pd.DataFrame:
        """Fetch the missing span from Alpaca, split into buckets, and write.

        ADR 0033 (Historical Data Integrity). Alpaca caps a response at
        ``_PAGE_LIMIT`` bars, so a cold multi-year intraday span comes back
        truncated. We therefore **paginate**: a full page (== ``_PAGE_LIMIT``)
        is treated as *possibly truncated* and the fetch continues from just
        after the last returned bar until a short/empty page proves the span is
        exhausted. ``.empty`` markers are written only for genuinely-empty
        buckets **within the range the provider actually covered** — a bucket
        beyond an incomplete fetch is left *missing* (re-fetchable), never
        poisoned.
        """
        if not missing:
            return _empty_bars_frame()

        overall_start = min(m[1] for m in missing)
        overall_end = max(m[2] for m in missing)

        loop = asyncio.get_running_loop()
        frames: list[pd.DataFrame] = []
        cursor = overall_start
        covered_end = overall_end  # optimistic; narrowed only if we stop early
        incomplete = False  # True ⇒ the tail past ``covered_end`` was NOT confirmed
        pages = 0

        while cursor <= overall_end:
            if pages >= _MAX_PAGES:
                logger.warning(
                    "bar_cache_fetch_page_cap",
                    symbol=symbol,
                    timeframe=timeframe,
                    pages=pages,
                    covered_through=cursor.isoformat(),
                )
                covered_end = frames[-1]["t"].max() if frames else overall_start
                incomplete = True
                break
            try:
                page = await loop.run_in_executor(
                    None,
                    functools.partial(
                        _alpaca_fetch_bars, symbol, timeframe, cursor, overall_end
                    ),
                )
            except Exception:
                logger.exception(
                    "bar_cache_fetch_failed",
                    symbol=symbol,
                    timeframe=timeframe,
                    start=cursor.isoformat(),
                    end=overall_end.isoformat(),
                )
                if not frames:
                    return _empty_bars_frame()  # first page failed → nothing to write
                # A continuation failed: keep what we have, but do NOT claim the
                # unfetched tail is empty — leave it missing (ADR 0033 point 1).
                covered_end = frames[-1]["t"].max()
                incomplete = True
                break
            pages += 1
            if page.empty:
                break  # provider has no (more) data in [cursor, overall_end] → exhausted
            frames.append(page)
            last_ts = page["t"].max()
            if len(page) < _PAGE_LIMIT or last_ts >= overall_end:
                break  # short page or reached the end → span fully covered
            nxt = last_ts + timedelta(microseconds=1)
            if nxt <= cursor:  # no forward progress (defensive)
                covered_end = last_ts
                incomplete = True
                break
            cursor = nxt

        df = (
            pd.concat(frames).drop_duplicates(subset=["t"]).sort_values("t").reset_index(drop=True)
            if frames
            else _empty_bars_frame()
        )

        if df.empty:
            # No data anywhere in the span → authoritative "empty" for a bounded
            # past range (holidays, inactive symbol); mark every requested bucket.
            for bucket_key, _, _ in missing:
                self._write_empty_marker(symbol, timeframe, bucket_key)
            return df

        for bucket_key, b_start, b_end in missing:
            bucket_df = df[(df["t"] >= b_start) & (df["t"] <= b_end)].reset_index(drop=True)
            if bucket_df.empty:
                # Mark empty ONLY if the whole bucket lies within the covered range.
                # A bucket beyond an incomplete fetch stays missing → re-fetchable.
                if not incomplete or b_end <= covered_end:
                    self._write_empty_marker(symbol, timeframe, bucket_key)
                continue
            f = self._bucket_file(symbol, timeframe, bucket_key)
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".parquet.tmp")
            bucket_df.to_parquet(tmp, index=False)
            tmp.replace(f)  # atomic overwrite (cross-platform; rename() won't replace on Windows)
            f.with_suffix(".empty").unlink(missing_ok=True)  # clear any stale marker
            logger.info(
                "bar_cache_wrote",
                symbol=symbol,
                timeframe=timeframe,
                bucket=bucket_key,
                granularity=granularity,
                rows=len(bucket_df),
            )

        return df

    def _evict_if_over_cap(self) -> None:
        """LRU eviction. Files modified <24h ago are protected (likely
        contain today's in-progress bars)."""
        total = 0
        all_files: list[tuple[float, int, Path]] = []  # (atime, size, path)
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

        all_files.sort(key=lambda x: x[0])  # oldest atime first
        protected_cutoff = now - 24 * 3600
        evicted_count = 0
        evicted_bytes = 0
        for _atime, size, f in all_files:
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
            logger.info(
                "bar_cache_evicted",
                files=evicted_count,
                bytes_freed=evicted_bytes,
                total_after=total,
            )


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _empty_bars_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["t", "o", "h", "l", "c", "v"])


def _alpaca_fetch_bars(
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
) -> pd.DataFrame:
    """Synchronous Alpaca historical-bars fetch.

    Called via ``run_in_executor`` from the async cache. ``DataFeed.IEX`` is
    the free real-time feed; bumping to SIP requires a paid Alpaca plan.
    """
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    from app.utils.tls_trust import enable_os_trust_store

    # ADR 0017: also enable here (not just app startup) so standalone callers of
    # this function — backtest fetch scripts, fixture generation — verify against
    # the OS trust store too. Idempotent: a no-op once injected.
    enable_os_trust_store()

    creds = load_credentials()
    client = StockHistoricalDataClient(
        api_key=creds.api_key, secret_key=creds.api_secret
    )

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
        feed=DataFeed.IEX,
        limit=_PAGE_LIMIT,
    )
    result = client.get_stock_bars(req)
    bars = result.data.get(symbol, []) if hasattr(result, "data") else []
    if not bars:
        return _empty_bars_frame()
    rows = [
        {
            "t": (
                b.timestamp.astimezone(UTC)
                if hasattr(b.timestamp, "astimezone")
                else b.timestamp
            ),
            "o": float(b.open),
            "h": float(b.high),
            "l": float(b.low),
            "c": float(b.close),
            "v": int(b.volume),
        }
        for b in bars
    ]
    return pd.DataFrame(rows)
