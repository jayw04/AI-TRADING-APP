#!/usr/bin/env python3
"""Manual momentum portfolio rebalance trigger.

Usage: python manual_rebalance.py [strategy_id]

If strategy_id is omitted, triggers rebalance on all registered momentum strategies.
"""

import asyncio
import sys
from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import get_settings
from app.db.enums import StrategyStatus
from app.db.models.strategy import Strategy as StrategyRow
from app.strategies.context import Bar
from app.strategies.engine import StrategyEngine
from app.utils.logging import configure_logging

logger = structlog.get_logger(__name__)


async def main():
    settings = get_settings()
    configure_logging(settings.log_level)

    # Parse args
    strategy_ids = []
    if len(sys.argv) > 1:
        try:
            strategy_ids = [int(sys.argv[1])]
        except ValueError:
            print(f"Invalid strategy_id: {sys.argv[1]}")
            sys.exit(1)

    # Connect to database
    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        # Find momentum strategies to rebalance
        if not strategy_ids:
            result = await session.execute(
                select(StrategyRow).where(
                    StrategyRow.name == "momentum-portfolio"
                )
            )
            strats = result.scalars().all()
            strategy_ids = [s.id for s in strats]

        if not strategy_ids:
            print("No momentum strategies found")
            return

        print(f"Found strategies to rebalance: {strategy_ids}")

        # Get details of each strategy
        for sid in strategy_ids:
            strat = await session.get(StrategyRow, sid)
            if strat is None:
                print(f"Strategy {sid} not found")
                continue

            print(f"\n--- Strategy {sid}: {strat.name} ---")
            print(f"Status: {strat.status}")
            print(f"Account: {strat.account_id}")
            print(f"Symbols: {len(strat.symbols_json)} registered")
            print(f"Schedule: {strat.schedule}")

    await engine.dispose()
    print("\nTo actually trigger the rebalance, the strategy engine must be running.")
    print("The engine will dispatch on the next scheduled time or via APScheduler.")


if __name__ == "__main__":
    asyncio.run(main())
