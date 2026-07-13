"""The pipeline-health monitor must not cry wolf.

A monitor that reports phantom failures gets ignored, and an ignored monitor is worse than no
monitor — it converts a blind spot into a blind spot you believe you have covered. Every test
here pins a false-alarm mode that the first cut of this script actually had:

  * D3 read a HARDCODED cache path (``/app/data/bar_cache``) that turned out to be a stale
    legacy directory with 5 fixture symbols, while the engine's real cache (``bars_cache``)
    holds 312. It would have reported "5/209 covered — FAIL" on every run, forever.
  * D3 also treated "symbol not in cache" as a fault. The cache is populated LAZILY; absence
    is normal. The fault that actually bites is a symbol that prints NO bars (SATS went dead
    2026-06-23 and sat in all four live universes for three weeks, silently excluded from
    every ranking).
  * R1 would have reported all five live strategies as "NEVER FIRED" on day one, before the
    engine instrumentation had written a single dispatch row.

That last one is the same error I made by hand: reading an empty ``orders`` table for
2026-07-06 and concluding the books never traded. They had — the rows were deleted by the
07-07 baseline reset, and the immutable audit log showed 322 ORDER_SUBMITTED that day.
Absence of evidence is not evidence of absence.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.db.models.ops_health import STATUS_FAIL, STATUS_OK, STATUS_WARN
from scripts.reports.pipeline_health import (
    _bar_cache_root,
    _last_completed_session,
    _sessions_between,
    _worst,
    check_bar_cache,
)

# ---------------------------------------------------------------- cache root


def test_bar_cache_root_comes_from_settings_not_a_hardcoded_path() -> None:
    """The path must track the engine's own setting. Hardcoding it produced a permanent
    false FAIL against a stale legacy directory."""
    from app.config import get_settings

    root = _bar_cache_root()
    assert root.is_absolute()
    assert root.name == get_settings().bars_cache_root.rstrip("/").split("/")[-1]


# ---------------------------------------------------------------- D3


def _mk_cache(tmp_path, symbol: str, month: str, *, empty: bool) -> None:
    d = tmp_path / symbol / "1Day"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{month}.empty" if empty else d / f"{month}.parquet").write_bytes(b"")


def test_uncached_symbol_is_not_a_failure(tmp_path, monkeypatch) -> None:
    """The bar cache is lazy. A symbol absent from disk gets fetched on demand — alarming on
    it would fire on every cold start and on every universe change."""
    monkeypatch.setattr("scripts.reports.pipeline_health._bar_cache_root", lambda: tmp_path)
    _mk_cache(tmp_path, "AAPL", "2026-07", empty=False)

    check, _ = check_bar_cache({"AAPL", "MSFT", "NVDA"}, date(2026, 7, 10))

    assert check.status == STATUS_OK, "an un-warmed cache must not read as a failure"


def test_dead_ticker_in_the_live_universe_is_caught(tmp_path, monkeypatch) -> None:
    """THE REAL FAILURE. SATS stopped printing on 2026-06-23 and stayed in all four live
    universes. The engine sees df.empty, skips it, and the name vanishes from every ranking
    without a single error being raised."""
    monkeypatch.setattr("scripts.reports.pipeline_health._bar_cache_root", lambda: tmp_path)
    for sym in ("AAPL", "MSFT", "NVDA", "AMD"):
        _mk_cache(tmp_path, sym, "2026-07", empty=False)
    _mk_cache(tmp_path, "SATS", "2026-07", empty=True)  # marker, no parquet == no bars

    check, snap = check_bar_cache(
        {"AAPL", "MSFT", "NVDA", "AMD", "SATS"}, date(2026, 7, 10)
    )

    assert check.status in (STATUS_WARN, STATUS_FAIL)
    assert "SATS" in check.detail
    assert check.facts["dead"] == ["SATS"]
    assert snap is not None and snap.symbols_covered == 4


def test_a_symbol_with_both_a_marker_and_real_bars_is_healthy(tmp_path, monkeypatch) -> None:
    """A stale ``.empty`` marker sitting next to a real parquet is NOT a dead ticker — the
    cache clears the marker when bars finally arrive, and the parquet is the truth."""
    monkeypatch.setattr("scripts.reports.pipeline_health._bar_cache_root", lambda: tmp_path)
    d = tmp_path / "AAPL" / "1Day"
    d.mkdir(parents=True)
    (d / "2026-07.parquet").write_bytes(b"")
    (d / "2026-07.empty").write_bytes(b"")

    check, _ = check_bar_cache({"AAPL"}, date(2026, 7, 10))

    assert check.status == STATUS_OK


# ---------------------------------------------------------------- session math


def test_staleness_is_counted_in_SESSIONS_not_calendar_days() -> None:
    """Fri 2026-07-10 -> Mon 2026-07-13 is ONE session, not three days. Counting calendar
    days would raise a warning every single Monday, and every long weekend twice."""
    assert _sessions_between(date(2026, 7, 10), date(2026, 7, 13)) == 1


def test_a_holiday_weekend_does_not_read_as_stale() -> None:
    """Thu 2026-07-02 -> Mon 2026-07-06 spans July 4th (observed Fri 07-03, an NYSE holiday):
    4 calendar days, but only ONE session."""
    assert _sessions_between(date(2026, 7, 2), date(2026, 7, 6)) == 1


@pytest.mark.parametrize(
    ("hour", "expected"),
    [(9, date(2026, 7, 10)), (16, date(2026, 7, 13))],
)
def test_today_only_counts_once_the_market_has_closed(hour: int, expected: date) -> None:
    """Before the close, the newest data anyone could legitimately hold is yesterday's. Calling
    that stale is a false alarm on every single trading morning."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    now = datetime(2026, 7, 13, hour, 0, tzinfo=ZoneInfo("America/New_York"))  # a Monday
    assert _last_completed_session(now) == expected


# ---------------------------------------------------------------- status rollup


def test_worst_status_wins_and_empty_is_ok() -> None:
    assert _worst([STATUS_OK, STATUS_WARN, STATUS_FAIL]) == STATUS_FAIL
    assert _worst([STATUS_OK, STATUS_WARN]) == STATUS_WARN
    assert _worst([]) == STATUS_OK
