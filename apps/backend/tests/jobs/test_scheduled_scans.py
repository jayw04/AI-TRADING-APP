"""P8 §4 — the pre-market scheduled-scan cron (run_scheduled_scans)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd
from sqlalchemy import select

from app.db.models.scanner_definition import ScannerDefinition
from app.db.models.scanner_run import TRIGGER_SCHEDULED, ScannerRun
from app.db.models.trading_profile import TradingProfile
from app.db.models.user import User
from app.jobs.scheduled_scans import run_scheduled_scans

# Wednesday 08:00 ET (a weekday, after the 7:30 default) / Saturday.
WED_0800_ET = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
SAT_ET = datetime(2026, 6, 13, 12, 0, tzinfo=UTC)
WED_0700_ET = datetime(2026, 6, 10, 11, 0, tzinfo=UTC)  # 07:00 ET — before default


def _bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "t": pd.date_range("2026-01-01", periods=5, tz="UTC"),
            "o": [100.0] * 5,
            "h": [101.0] * 5,
            "l": [99.0] * 5,
            "c": [100.0] * 5,
            "v": [1_000_000] * 5,
        }
    )


class _FakeBarCache:
    async def get_bars(self, symbol: str, tf: str, start: Any, end: Any) -> pd.DataFrame:
        return _bars()


async def _seed(session_factory, *, scheduled: bool, scan_time: str | None = None) -> None:
    async with session_factory() as s:
        s.add(User(id=1, email="dev@x", display_name="Dev"))
        now = datetime.now(UTC)
        s.add(
            TradingProfile(
                user_id=1,
                session_preferences_json=(
                    {"discovery_scan_time": scan_time} if scan_time else {}
                ),
                created_at=now,
                updated_at=now,
            )
        )
        s.add(
            ScannerDefinition(
                user_id=1,
                name="above 50",
                criteria="close > 50",
                universe_kind="symbols",
                universe_symbols_json=["AAPL"],
                timeframe="1Day",
                scheduled=scheduled,
                created_at=now,
                updated_at=now,
            )
        )
        await s.commit()


async def _scheduled_runs(session_factory) -> list[ScannerRun]:
    async with session_factory() as s:
        return list(
            (
                await s.execute(
                    select(ScannerRun).where(
                        ScannerRun.trigger == TRIGGER_SCHEDULED
                    )
                )
            ).scalars().all()
        )


async def test_runs_scheduled_def_when_due(session_factory) -> None:
    await _seed(session_factory, scheduled=True)
    out = await run_scheduled_scans(
        session_factory=session_factory,
        bar_cache=_FakeBarCache(),
        indicator_computer=None,
        now=WED_0800_ET,
    )
    assert out["ran"] == 1
    runs = await _scheduled_runs(session_factory)
    assert len(runs) == 1
    assert runs[0].trigger == TRIGGER_SCHEDULED
    assert runs[0].matched_count == 1  # AAPL close 100 > 50


async def test_idempotent_second_pass_same_day(session_factory) -> None:
    await _seed(session_factory, scheduled=True)
    await run_scheduled_scans(
        session_factory=session_factory, bar_cache=_FakeBarCache(), now=WED_0800_ET
    )
    out = await run_scheduled_scans(
        session_factory=session_factory, bar_cache=_FakeBarCache(), now=WED_0800_ET
    )
    assert out["ran"] == 0  # already ran today
    assert len(await _scheduled_runs(session_factory)) == 1


async def test_not_due_before_scan_time(session_factory) -> None:
    await _seed(session_factory, scheduled=True)  # default 7:30; now is 07:00 ET
    out = await run_scheduled_scans(
        session_factory=session_factory, bar_cache=_FakeBarCache(), now=WED_0700_ET
    )
    assert out["ran"] == 0
    assert await _scheduled_runs(session_factory) == []


async def test_unscheduled_def_is_ignored(session_factory) -> None:
    await _seed(session_factory, scheduled=False)
    out = await run_scheduled_scans(
        session_factory=session_factory, bar_cache=_FakeBarCache(), now=WED_0800_ET
    )
    assert out == {"ran": 0, "skipped": 0, "failed": 0}  # no scheduled users at all


async def test_weekend_is_skipped(session_factory) -> None:
    await _seed(session_factory, scheduled=True)
    out = await run_scheduled_scans(
        session_factory=session_factory, bar_cache=_FakeBarCache(), now=SAT_ET
    )
    assert out["ran"] == 0
    assert await _scheduled_runs(session_factory) == []


async def test_custom_scan_time_makes_it_due(session_factory) -> None:
    # configured 06:00 ET → due at 07:00 ET
    await _seed(session_factory, scheduled=True, scan_time="06:00")
    out = await run_scheduled_scans(
        session_factory=session_factory, bar_cache=_FakeBarCache(), now=WED_0700_ET
    )
    assert out["ran"] == 1
