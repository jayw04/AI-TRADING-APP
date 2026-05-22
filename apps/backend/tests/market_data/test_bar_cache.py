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
