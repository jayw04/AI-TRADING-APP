"""Pre-market scheduled scanning (P8 §4). A 15-minute interval tick.

For each user with `scheduled` scanner definitions: once the user's configured
`discovery_scan_time` (trading_profile.session_preferences_json, default 7:30
ET) has passed today, run all their scheduled scans — **once per day**
(idempotent: skip if a scheduled run already exists for the user today). Mirrors
the morning-brief "skip if done today" and the completion crons' tick-and-check.
Weekends are skipped (no fresh bars). Per-user failures are logged, not fatal.

Only scheduled runs (trigger="scheduled") feed the Opportunities view.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.scanner_definition import ScannerDefinition
from app.db.models.scanner_run import TRIGGER_SCHEDULED, ScannerRun
from app.db.models.trading_profile import TradingProfile
from app.market_data.discovery import get_discovery_feeds
from app.services.scanner.service import run_and_record
from app.utils.time import EASTERN

logger = structlog.get_logger(__name__)

DEFAULT_SCAN_TIME = "07:30"


def _parse_hhmm(value: Any) -> tuple[int, int]:
    """Parse 'HH:MM' → (hour, minute); fall back to the default on bad input."""
    try:
        hh, mm = str(value).split(":", 1)
        h, m = int(hh), int(mm)
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
    except (ValueError, AttributeError):
        pass
    h, m = (int(p) for p in DEFAULT_SCAN_TIME.split(":"))
    return h, m


async def run_scheduled_scans(
    *,
    session_factory: async_sessionmaker[Any],
    bar_cache: Any = None,
    indicator_computer: Any = None,
    now: datetime | None = None,
) -> dict[str, int]:
    now = now or datetime.now(UTC)
    now_et = now.astimezone(EASTERN)
    ran = skipped = failed = 0

    if now_et.weekday() >= 5:  # Sat/Sun — markets closed, bars are stale
        return {"ran": 0, "skipped": 0, "failed": 0}
    if bar_cache is None:
        logger.info("scheduled_scans_skipped_no_bar_cache")
        return {"ran": 0, "skipped": 0, "failed": 0}

    today_start_utc = now_et.replace(
        hour=0, minute=0, second=0, microsecond=0
    ).astimezone(UTC)

    async with session_factory() as session:
        user_ids = (
            await session.execute(
                select(distinct(ScannerDefinition.user_id)).where(
                    ScannerDefinition.scheduled.is_(True)
                )
            )
        ).scalars().all()

    for user_id in user_ids:
        try:
            async with session_factory() as session:
                profile = (
                    await session.execute(
                        select(TradingProfile).where(
                            TradingProfile.user_id == user_id
                        )
                    )
                ).scalar_one_or_none()
                prefs = (profile.session_preferences_json or {}) if profile else {}
                hour, minute = _parse_hhmm(prefs.get("discovery_scan_time"))
                due_at = now_et.replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
                if now_et < due_at:
                    skipped += 1
                    continue

                already = (
                    await session.execute(
                        select(ScannerRun.id).where(
                            ScannerRun.user_id == user_id,
                            ScannerRun.trigger == TRIGGER_SCHEDULED,
                            ScannerRun.run_at >= today_start_utc,
                        )
                    )
                ).first()
                if already is not None:
                    skipped += 1
                    continue

                defs = (
                    await session.execute(
                        select(ScannerDefinition).where(
                            ScannerDefinition.user_id == user_id,
                            ScannerDefinition.scheduled.is_(True),
                        )
                    )
                ).scalars().all()
                for d in defs:
                    await run_and_record(
                        session,
                        definition=d,
                        bar_cache=bar_cache,
                        indicator_computer=indicator_computer,
                        discovery_feeds_fn=get_discovery_feeds,
                        now=now,
                        trigger=TRIGGER_SCHEDULED,
                    )
                    ran += 1
                await session.commit()
        except Exception:
            logger.exception("scheduled_scans_user_failed", user_id=user_id)
            failed += 1

    logger.info("scheduled_scans_pass", ran=ran, skipped=skipped, failed=failed)
    return {"ran": ran, "skipped": skipped, "failed": failed}
