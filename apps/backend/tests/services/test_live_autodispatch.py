"""P6b §4.5 (ADR 0015) — live-auto-dispatch master switch + suppression wrap."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock

from sqlalchemy import select

from app.db.enums import OrderSide, OrderSourceType, OrderStatus, OrderType
from app.db.models.audit_log import AuditLog
from app.db.models.system_config import SystemConfig
from app.db.models.user import User
from app.risk import OrderRequest
from app.services.live_autodispatch import (
    LIVE_AUTODISPATCH_KEY,
    is_live_autodispatch_enabled,
    make_live_autodispatch_submit_fn,
    set_live_autodispatch_enabled,
)


def _req() -> OrderRequest:
    return OrderRequest(
        user_id=1, account_id=5, symbol_ticker="AAPL", side=OrderSide.BUY,
        qty=Decimal("10"), type=OrderType.MARKET,
        source_type=OrderSourceType.STRATEGY, source_id="7",
    )


async def _seed_user(session_factory) -> None:
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        await s.commit()


async def test_default_off(session_factory):
    async with session_factory() as s:
        assert await is_live_autodispatch_enabled(s) is False  # absent row → off


async def test_set_enables_and_audits(session_factory):
    await _seed_user(session_factory)
    async with session_factory() as s:
        await set_live_autodispatch_enabled(s, True, actor_user_id=1)
        await s.commit()
    async with session_factory() as s:
        assert await is_live_autodispatch_enabled(s) is True
        row = (await s.execute(
            select(SystemConfig).where(SystemConfig.key == LIVE_AUTODISPATCH_KEY)
        )).scalars().first()
        assert row.value == "1"
        audits = (await s.execute(
            select(AuditLog).where(
                AuditLog.action == "LIVE_AUTODISPATCH_ENABLED_CHANGED"
            )
        )).scalars().all()
    assert len(audits) == 1


async def test_set_disable_round_trips(session_factory):
    await _seed_user(session_factory)
    async with session_factory() as s:
        await set_live_autodispatch_enabled(s, True, actor_user_id=1)
        await s.commit()
    async with session_factory() as s:
        await set_live_autodispatch_enabled(s, False, actor_user_id=1)
        await s.commit()
    async with session_factory() as s:
        assert await is_live_autodispatch_enabled(s) is False


async def test_wrap_suppresses_when_off(session_factory):
    real_submit = AsyncMock(return_value="LIVE_ORDER")
    submit = make_live_autodispatch_submit_fn(
        strategy_id=7, real_submit=real_submit, session_factory=session_factory
    )
    result = await submit(_req())
    real_submit.assert_not_called()  # never reached the broker
    assert result.status == OrderStatus.REJECTED
    assert result.rejection_reason == "LIVE_AUTODISPATCH_DISABLED"


async def test_wrap_passes_through_when_on(session_factory):
    await _seed_user(session_factory)
    async with session_factory() as s:
        await set_live_autodispatch_enabled(s, True, actor_user_id=1)
        await s.commit()
    real_submit = AsyncMock(return_value="LIVE_ORDER")
    submit = make_live_autodispatch_submit_fn(
        strategy_id=7, real_submit=real_submit, session_factory=session_factory
    )
    result = await submit(_req())
    real_submit.assert_awaited_once()
    assert result == "LIVE_ORDER"
