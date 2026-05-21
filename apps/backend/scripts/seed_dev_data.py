"""Idempotent dev-data seeder.

Run after `alembic upgrade head`:

    python scripts/seed_dev_data.py

Inserts (or no-ops if already present):
- One user (id=1, email from WORKBENCH_DEV_USER_EMAIL).
- One Alpaca paper account.
- 10 sample symbols.
- system_config key='mode' = 'paper'.
- Default global RiskLimits row for user 1 (P1 Session 4).
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

# Make the backend importable when run as `python scripts/seed_dev_data.py`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db.enums import RiskScopeType  # noqa: E402
from app.db.models import (  # noqa: E402
    Account,
    AccountMode,
    RiskLimits,  # noqa: E402
    Symbol,
    SystemConfig,
    User,
)
from app.db.session import get_sessionmaker  # noqa: E402

SAMPLE_SYMBOLS = [
    ("AAPL", "Apple Inc."),
    ("MSFT", "Microsoft Corporation"),
    ("NVDA", "NVIDIA Corporation"),
    ("SPY", "SPDR S&P 500 ETF Trust"),
    ("QQQ", "Invesco QQQ Trust"),
    ("TSLA", "Tesla, Inc."),
    ("AMD", "Advanced Micro Devices"),
    ("GOOGL", "Alphabet Inc. Class A"),
    ("AMZN", "Amazon.com, Inc."),
    ("META", "Meta Platforms, Inc."),
]


async def seed() -> None:
    settings = get_settings()
    Session = get_sessionmaker()

    async with Session() as session, session.begin():
        # User
        existing_user = await session.scalar(
            select(User).where(User.email == settings.dev_user_email)
        )
        if existing_user is None:
            user = User(email=settings.dev_user_email, display_name="Jay (dev)")
            session.add(user)
            await session.flush()
            user_id = user.id
            print(f"  + user id={user_id} email={settings.dev_user_email}")
        else:
            user_id = existing_user.id
            print(f"  = user id={user_id} already present")

        # Account
        existing_account = await session.scalar(
            select(Account).where(
                Account.user_id == user_id,
                Account.broker == "alpaca",
                Account.mode == AccountMode.paper,
            )
        )
        if existing_account is None:
            session.add(
                Account(
                    user_id=user_id,
                    broker="alpaca",
                    mode=AccountMode.paper,
                    label="Alpaca Paper",
                )
            )
            print("  + account broker=alpaca mode=paper")
        else:
            print("  = account already present")

        # Symbols
        for ticker, name in SAMPLE_SYMBOLS:
            existing = await session.scalar(select(Symbol).where(Symbol.ticker == ticker))
            if existing is None:
                session.add(
                    Symbol(
                        ticker=ticker,
                        name=name,
                        exchange="NASDAQ" if ticker != "SPY" else "NYSE",
                        asset_class="equity",
                        active=True,
                    )
                )
                print(f"  + symbol {ticker}")

        # SystemConfig: mode=paper
        existing_cfg = await session.scalar(
            select(SystemConfig).where(
                SystemConfig.key == "mode", SystemConfig.user_id.is_(None)
            )
        )
        if existing_cfg is None:
            session.add(SystemConfig(key="mode", value="paper"))
            print("  + system_config mode=paper")
        else:
            print("  = system_config mode already present")

        # Default global risk limits (P1 Session 4) — written once,
        # never overwritten on reseed. The Risk Engine (Session 5) resolves
        # this row at evaluate-time.
        existing_limits = await session.scalar(
            select(RiskLimits).where(
                RiskLimits.user_id == user_id,
                RiskLimits.scope_type == RiskScopeType.GLOBAL,
            )
        )
        if existing_limits is None:
            now = datetime.now(UTC)
            session.add(
                RiskLimits(
                    user_id=user_id,
                    scope_type=RiskScopeType.GLOBAL,
                    scope_id=None,
                    max_position_qty=Decimal("1000"),
                    max_position_notional=Decimal("25000"),
                    max_gross_exposure=Decimal("100000"),
                    max_daily_loss=Decimal("2000"),
                    max_orders_per_minute=10,
                    allow_short=False,
                    allowed_symbols=None,
                    denied_symbols=None,
                    created_at=now,
                    updated_at=now,
                )
            )
            print("  + risk_limits global (default caps)")
        else:
            print("  = risk_limits global already present")

    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(seed())
