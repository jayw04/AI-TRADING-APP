"""BarCache mechanics: cache hits, gap fetching, LRU eviction, error shapes.

The Alpaca fetch is mocked. We only test the cache layer's behavior, not
Alpaca itself.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from app.market_data.bar_cache import BarCache, _empty_bars_frame


def _mk_bars(start: datetime, n: int) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "t": start + timedelta(minutes=i),
                "o": 100.0 + i * 0.01,
                "h": 100.5 + i * 0.01,
                "l": 99.5 + i * 0.01,
                "c": 100.0 + i * 0.01,
                "v": 1000 + i,
            }
            for i in range(n)
        ]
    )


@pytest.fixture
def tmp_cache(tmp_path):
    adapter = MagicMock()
    cache = BarCache(adapter=adapter, root=str(tmp_path), max_gb=0.001)  # 1 MB cap
    return cache, tmp_path


async def test_first_read_fetches_and_writes_parquet(tmp_cache):
    cache, root = tmp_cache
    start = datetime(2025, 11, 3, 14, 30, tzinfo=UTC)
    end = datetime(2025, 11, 3, 14, 45, tzinfo=UTC)
    fake_bars = _mk_bars(start, 16)

    with patch(
        "app.market_data.bar_cache._alpaca_fetch_bars", return_value=fake_bars
    ):
        df = await cache.get_bars("AAPL", "1Min", start, end)

    assert len(df) == 16
    expected = root / "AAPL" / "1Min" / "2025-11-03.parquet"
    assert expected.exists()


async def test_second_read_serves_from_disk(tmp_cache):
    cache, _root = tmp_cache
    start = datetime(2025, 11, 3, 14, 30, tzinfo=UTC)
    end = datetime(2025, 11, 3, 14, 45, tzinfo=UTC)
    fake_bars = _mk_bars(start, 16)

    fetcher = MagicMock(return_value=fake_bars)
    with patch("app.market_data.bar_cache._alpaca_fetch_bars", fetcher):
        await cache.get_bars("AAPL", "1Min", start, end)
        assert fetcher.call_count == 1
        await cache.get_bars("AAPL", "1Min", start, end)
        # Second call must NOT fetch — that's the whole point of the cache.
        assert fetcher.call_count == 1


async def test_open_bucket_refetched_after_throttle(tmp_cache):
    """The current, still-OPEN bucket must be re-fetched (throttled) so bars
    printed since the last write land — a partial current-month/day file must NOT
    freeze the cache (the weeks-stale-bars bug). Past buckets stay disk-served."""
    cache, _root = tmp_cache
    now = datetime.now(UTC)
    start = now - timedelta(hours=6)  # within the current (open) month bucket
    fetcher = MagicMock(return_value=_mk_bars(now - timedelta(hours=1), 5))

    with patch("app.market_data.bar_cache._alpaca_fetch_bars", fetcher):
        await cache.get_bars("AAPL", "1Day", start, now)
        assert fetcher.call_count == 1  # first fetch of the open month
        await cache.get_bars("AAPL", "1Day", start, now)
        assert fetcher.call_count == 1  # throttled — no immediate re-fetch
        cache._last_open_fetch.clear()  # simulate the throttle window elapsing
        await cache.get_bars("AAPL", "1Day", start, now)
        assert fetcher.call_count == 2  # FIX: open bucket re-fetched (was frozen before)


async def test_empty_day_marker_skips_refetch(tmp_cache):
    """If Alpaca returns no bars for a given day (holiday, inactive symbol),
    a ``.empty`` marker is written. Future requests for the same day must
    not hit Alpaca again."""
    cache, root = tmp_cache
    start = datetime(2025, 11, 3, tzinfo=UTC)
    end = datetime(2025, 11, 3, 23, 59, 59, tzinfo=UTC)

    fetcher = MagicMock(return_value=_empty_bars_frame())
    with patch("app.market_data.bar_cache._alpaca_fetch_bars", fetcher):
        await cache.get_bars("ZZZZ", "1Min", start, end)
        marker = root / "ZZZZ" / "1Min" / "2025-11-03.empty"
        assert marker.exists()
        await cache.get_bars("ZZZZ", "1Min", start, end)
        # Marker present → no second fetch.
        assert fetcher.call_count == 1


async def test_lru_eviction_shrinks_cache_when_over_cap(tmp_cache):
    cache, root = tmp_cache
    # Write three day files; backdate atime/mtime so they're outside the
    # 24-hour protection window and therefore evictable.
    for day in (1, 2, 3):
        d = datetime(2025, 11, day, tzinfo=UTC)
        with patch(
            "app.market_data.bar_cache._alpaca_fetch_bars",
            return_value=_mk_bars(d, 60),
        ):
            await cache.get_bars("AAPL", "1Min", d, d + timedelta(hours=23))

    old = time.time() - 48 * 3600
    for f in root.rglob("*.parquet"):
        # Bias atime so day-1 is oldest, day-3 newest (deterministic LRU order).
        bias = int(f.stat().st_size) + ord(f.stem[-1])
        os.utime(f, (old + bias, old))

    cache._max_bytes = 1  # force eviction
    cache._evict_if_over_cap()

    remaining = list(root.rglob("*.parquet"))
    assert len(remaining) < 3


async def test_unknown_timeframe_raises(tmp_cache):
    cache, _ = tmp_cache
    with pytest.raises(ValueError, match="Unsupported timeframe"):
        await cache.get_bars(
            "AAPL",
            "37Min",
            datetime(2025, 11, 3, tzinfo=UTC),
            datetime(2025, 11, 3, 1, tzinfo=UTC),
        )


async def test_end_before_start_raises(tmp_cache):
    cache, _ = tmp_cache
    with pytest.raises(ValueError, match="end < start"):
        await cache.get_bars(
            "AAPL",
            "1Min",
            datetime(2025, 11, 3, 14, tzinfo=UTC),
            datetime(2025, 11, 3, 13, tzinfo=UTC),
        )


async def test_naive_datetime_is_assumed_utc(tmp_cache):
    """Naive datetimes shouldn't crash; we normalize to UTC silently."""
    cache, _ = tmp_cache
    fake_bars = _mk_bars(datetime(2025, 11, 3, 14, 30, tzinfo=UTC), 5)
    with patch(
        "app.market_data.bar_cache._alpaca_fetch_bars", return_value=fake_bars
    ):
        df = await cache.get_bars(
            "AAPL",
            "1Min",
            datetime(2025, 11, 3, 14, 30),
            datetime(2025, 11, 3, 14, 45),
        )
    assert not df.empty


# ---------- P4 §8: streaming buffer + get_latest_bar ----------


class _StreamedBarLike:
    """Duck-typed stand-in for app.services.bar_stream.StreamedBar."""

    def __init__(self, symbol, ts, open_, high, low, close, volume):
        self.symbol = symbol
        self.ts = ts
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume


async def test_append_streamed_bar_lowercases_to_upper_and_grows_buffer(tmp_cache):
    cache, _ = tmp_cache
    bar = _StreamedBarLike(
        symbol="aapl",
        ts=datetime(2025, 11, 3, 14, 30, tzinfo=UTC),
        open_=190.0, high=190.5, low=189.5, close=190.2, volume=1000,
    )
    await cache.append_streamed_bar("aapl", bar)
    assert "AAPL" in cache._streaming_buffer
    assert len(cache._streaming_buffer["AAPL"]) == 1
    assert cache._streaming_buffer["AAPL"][0]["c"] == 190.2


async def test_append_streamed_bar_truncates_at_cap(tmp_cache):
    """The ring buffer caps at _max_buffer_bars; oldest entries are dropped."""
    cache, _ = tmp_cache
    cache._max_buffer_bars = 5
    base = datetime(2025, 11, 3, 14, 30, tzinfo=UTC)
    for i in range(8):
        await cache.append_streamed_bar(
            "AAPL",
            _StreamedBarLike(
                "AAPL", base + timedelta(minutes=i),
                100 + i, 100.5 + i, 99.5 + i, 100 + i, 1000 + i,
            ),
        )
    buf = cache._streaming_buffer["AAPL"]
    assert len(buf) == 5
    # The first 3 should have been dropped; the most-recent should be i=7.
    assert buf[-1]["c"] == 107.0
    assert buf[0]["c"] == 103.0


async def test_get_latest_bar_returns_buffered(tmp_cache):
    cache, _ = tmp_cache
    bar = _StreamedBarLike(
        "AAPL", datetime(2025, 11, 3, 14, 30, tzinfo=UTC),
        190.0, 190.5, 189.5, 190.7, 1234,
    )
    await cache.append_streamed_bar("AAPL", bar)
    latest = await cache.get_latest_bar("AAPL")
    assert latest is not None
    assert latest["c"] == 190.7
    assert latest["v"] == 1234.0


async def test_get_latest_bar_falls_back_to_parquet(tmp_cache):
    """No buffered bar → get_latest_bar calls get_bars over the last 2 days."""
    cache, _ = tmp_cache
    now = datetime.now(UTC)
    fake_bars = _mk_bars(now - timedelta(minutes=5), 5)
    with patch(
        "app.market_data.bar_cache._alpaca_fetch_bars", return_value=fake_bars
    ):
        latest = await cache.get_latest_bar("AAPL")
    assert latest is not None
    # The most recent bar from _mk_bars has index 4.
    assert latest["c"] == pytest.approx(100.04, abs=0.001)


async def test_get_latest_bar_returns_none_on_exception(tmp_cache, monkeypatch):
    """If get_bars raises, get_latest_bar returns None instead of bubbling."""
    cache, _ = tmp_cache

    async def _boom(*a, **kw):
        raise RuntimeError("parquet io failed")

    monkeypatch.setattr(cache, "get_bars", _boom)
    latest = await cache.get_latest_bar("AAPL")
    assert latest is None
