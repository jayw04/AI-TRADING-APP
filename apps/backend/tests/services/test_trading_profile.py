"""TradingProfileService tests (P5.5 §1).

Uses the in-memory ``session_factory`` fixture (schema via create_all). Audit
rows are asserted by selecting AuditLog and parsing payload_json. The action is
stored as the UPPER enum name 'TRADING_PROFILE_UPDATED'.
"""
import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.db.models.audit_log import AuditLog
from app.db.models.trading_profile import TradingProfile
from app.db.models.user import User
from app.services.trading_profile import TradingProfileService


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="t@local"))
        session.add(User(id=2, email="u@local"))
        await session.commit()
    return session_factory


async def _audit_rows(session_factory) -> list[AuditLog]:
    async with session_factory() as session:
        return list(
            (await session.execute(select(AuditLog).order_by(AuditLog.id))).scalars()
        )


async def test_get_returns_empty_for_new_user(seeded):
    async with seeded() as session:
        data = await TradingProfileService(session).get(1)
    assert data.user_id == 1
    assert data.watchlist == {}
    assert data.bias_criteria == {}
    assert data.bias_thresholds == {}
    assert data.session_preferences == {}
    assert data.risk_preferences == {}
    # Persisted: a second get finds the same row, doesn't create a duplicate.
    async with seeded() as session:
        count = (
            await session.execute(
                select(func.count()).select_from(TradingProfile).where(
                    TradingProfile.user_id == 1
                )
            )
        ).scalar_one()
    assert count == 1


async def test_get_returns_existing_profile(seeded):
    async with seeded() as session:
        await TradingProfileService(session).update(
            1, changes={"watchlist_json": {"core": ["AAPL"]}}, actor_user_id=1
        )
    async with seeded() as session:
        data = await TradingProfileService(session).get(1)
    assert data.watchlist == {"core": ["AAPL"]}


async def test_get_idempotent_no_duplicate(seeded):
    """Repeated first-time gets for the same user never create a duplicate.

    NOTE: a true two-connection concurrency test is not reliable against the
    no-StaticPool in-memory engine (each physical SQLite connection gets its
    own :memory: DB). The IntegrityError → re-select branch in get() is the
    defensive guard for the genuine concurrent case; here we assert the
    deterministic invariant (single row) that the guard preserves.
    """
    for _ in range(3):
        async with seeded() as session:
            data = await TradingProfileService(session).get(1)
            assert data.user_id == 1
    async with seeded() as session:
        count = (
            await session.execute(
                select(func.count()).select_from(TradingProfile).where(
                    TradingProfile.user_id == 1
                )
            )
        ).scalar_one()
    assert count == 1


async def test_update_changes_persist(seeded):
    async with seeded() as session:
        await TradingProfileService(session).update(
            1,
            changes={
                "watchlist_json": {"core": ["AAPL", "MSFT"]},
                "bias_thresholds_json": {"bullish": {"rsi_min": 50}},
            },
            actor_user_id=1,
        )
    async with seeded() as session:
        data = await TradingProfileService(session).get(1)
    assert data.watchlist == {"core": ["AAPL", "MSFT"]}
    assert data.bias_thresholds == {"bullish": {"rsi_min": 50}}


async def test_update_unknown_field_raises(seeded):
    async with seeded() as session:
        with pytest.raises(ValueError, match="Unknown profile field: bogus"):
            await TradingProfileService(session).update(
                1, changes={"bogus": {}}, actor_user_id=1
            )


async def test_update_partial_only_changes_specified_fields(seeded):
    async with seeded() as session:
        await TradingProfileService(session).update(
            1, changes={"watchlist_json": {"core": ["AAPL"]}}, actor_user_id=1
        )
    async with seeded() as session:
        await TradingProfileService(session).update(
            1, changes={"bias_criteria_json": {"bullish": "trend up"}}, actor_user_id=1
        )
    async with seeded() as session:
        data = await TradingProfileService(session).get(1)
    assert data.watchlist == {"core": ["AAPL"]}  # untouched by 2nd update
    assert data.bias_criteria == {"bullish": "trend up"}


async def test_update_audit_logged_with_diff(seeded):
    async with seeded() as session:
        await TradingProfileService(session).update(
            1, changes={"watchlist_json": {"core": ["AAPL"]}}, actor_user_id=1
        )
    rows = await _audit_rows(seeded)
    assert len(rows) == 1
    row = rows[0]
    assert row.action == "TRADING_PROFILE_UPDATED"
    assert row.target_type == "trading_profile"
    assert row.user_id == 1
    assert row.actor_id == "1"
    payload = json.loads(row.payload_json)
    assert payload["changes"]["old"]["watchlist_json"] == {}
    assert payload["changes"]["new"]["watchlist_json"] == {"core": ["AAPL"]}


async def test_update_no_change_does_not_audit(seeded):
    # First set a value.
    async with seeded() as session:
        await TradingProfileService(session).update(
            1, changes={"watchlist_json": {"core": ["AAPL"]}}, actor_user_id=1
        )
    # Re-submit the SAME value → no diff → no second audit row.
    async with seeded() as session:
        await TradingProfileService(session).update(
            1, changes={"watchlist_json": {"core": ["AAPL"]}}, actor_user_id=1
        )
    rows = await _audit_rows(seeded)
    assert len(rows) == 1  # only the first update audited


async def test_update_empty_changes_no_audit(seeded):
    async with seeded() as session:
        await TradingProfileService(session).update(1, changes={}, actor_user_id=1)
    assert await _audit_rows(seeded) == []


async def test_update_single_audit_row_per_change(seeded):
    """Single-commit contract: each effective update writes exactly one audit
    row (one audit row per commit keeps the §8 hash chain well-formed)."""
    for sym in (["AAPL"], ["MSFT"], ["NVDA"]):
        async with seeded() as session:
            await TradingProfileService(session).update(
                1, changes={"watchlist_json": {"core": sym}}, actor_user_id=1
            )
    rows = await _audit_rows(seeded)
    assert len(rows) == 3


async def test_update_other_user_isolated(seeded):
    async with seeded() as session:
        await TradingProfileService(session).update(
            1, changes={"watchlist_json": {"core": ["AAPL"]}}, actor_user_id=1
        )
    async with seeded() as session:
        data2 = await TradingProfileService(session).get(2)
    assert data2.watchlist == {}  # user 2 unaffected
