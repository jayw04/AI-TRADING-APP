#!/usr/bin/env python3
"""Trigger momentum portfolio rebalance immediately.

This script connects to the running strategy engine via the backend service
and triggers an immediate rebalance dispatch for all momentum strategies.
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
from app.lifespan import _engine_instance
from app.utils.logging import configure_logging

logger = structlog.get_logger(__name__)


async def trigger_rebalance():
    """Manually invoke the strategy engine's dispatch for momentum strategies."""
    settings = get_settings()
    configure_logging("info")

    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        # Find all momentum strategies
        async with session_factory() as session:
            result = await session.execute(
                select(StrategyRow).where(
                    StrategyRow.name == "momentum-portfolio"
                )
            )
            strategies = result.scalars().all()

        if not strategies:
            print("No momentum strategies found in database")
            return

        print(f"Found {len(strategies)} momentum strategies:")
        for strat in strategies:
            print(f"  - ID {strat.id}: {strat.name} (status={strat.status})")

        # Get the global strategy engine instance (from lifespan)
        # This is a bit hacky but necessary to access the running engine
        from app.strategies.engine import _global_engine

        if _global_engine is None:
            print("\nERROR: Strategy engine not initialized.")
            print("Make sure the backend service is running.")
            return 1

        print(f"\nStrategy engine is running: {type(_global_engine)}")

        # Trigger dispatch for each momentum strategy
        for strat in strategies:
            strategy_id = strat.id
            print(f"\n--- Triggering dispatch for strategy {strategy_id} ---")

            try:
                await _global_engine._dispatch_bar_tick(strategy_id=strategy_id)
                print(f"✓ Dispatch triggered for strategy {strategy_id}")
            except Exception as e:
                print(f"✗ Error dispatching strategy {strategy_id}: {e}")
                logger.exception("dispatch_failed", strategy_id=strategy_id, error=str(e))

        print("\n✓ Rebalance dispatch complete")
        return 0

    finally:
        await engine.dispose()


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(trigger_rebalance())
        sys.exit(exit_code or 0)
    except KeyboardInterrupt:
        print("\nInterrupted")
        sys.exit(1)
    except Exception as e:
        logger.exception("trigger_rebalance_failed")
        print(f"Error: {e}")
        sys.exit(1)
