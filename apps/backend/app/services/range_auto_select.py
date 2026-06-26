"""Daily auto-selection of the Range Trader's universe (design §"Top 3–5 candidates").

The Candidate Engine produces the day's Top-N range candidates each morning and a single
Range Trader strategy *consumes* that list — its universe changes daily (the only strategy
whose universe does, per the design). Because a running strategy's symbol set is fixed at
start, applying a new universe is a stop → set symbols → start cycle, audit-logged.

Three layers, each testable in isolation:
  - ``load_range_backtest_evidence`` — realized win-rate/Sharpe per symbol (shared with the
    Range Candidates API so both rank evidence-first from the same source).
  - ``select_range_universe`` — rank a universe evidence-first and return today's Top-N.
  - ``refresh_range_universe`` / ``run_daily_range_universe`` — the orchestration: discover
    opted-in range strategies and re-point each to today's Top-N (stop → update → start).

Opt-in is per strategy via an ``auto_select_top_n`` (int > 0) key in the strategy's
``params_json`` (optionally ``auto_select_universe`` to override the candidate pool). A
strategy without the marker is never touched. No order path; fail-soft; never raises into
the scheduler.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit.logger import AuditAction, AuditActorType, AuditLogger
from app.db.enums import ACTIVE_STRATEGY_STATUSES, StrategyStatus
from app.db.models.backtest_result import BacktestResult
from app.db.models.strategy import Strategy as StrategyRow
from app.services.range_insight import (
    DEFAULT_CANDIDATE_UNIVERSE,
    CandidateEvidence,
    select_top_range_symbols,
)
from app.utils.time import EASTERN

logger = structlog.get_logger(__name__)

# Range strategies reference this template; their traded symbols are symbols_json.
_RANGE_CODE_MATCH = "%range_trader%"
# Per-strategy opt-in marker (in params_json) and its optional universe override.
AUTOSELECT_PARAM = "auto_select_top_n"
AUTOSELECT_UNIVERSE_PARAM = "auto_select_universe"
# Audit payload tag so this system rebalance is distinguishable from a user symbol edit.
AUTOSELECT_SOURCE = "daily_preopen_auto_select"


async def load_range_backtest_evidence(
    session: AsyncSession, symbols: Iterable[str]
) -> dict[str, CandidateEvidence]:
    """Realized range-trading performance per symbol, from its most recent range backtest —
    the evidence that drives the candidate ranking ahead of the structural prior.

    A range strategy is one whose ``code_path`` references the range_trader template; its
    symbol is taken as ``symbols_json[0]``. For each wanted symbol we take the latest
    ``BacktestResult`` (by ``created_at``) across that symbol's range strategies and read
    ``win_rate`` / ``sharpe_ratio`` / ``trade_count`` from ``metrics_json``. Symbols with no
    range backtest are simply absent (they fall back to structural ranking).

    (Single-symbol mapping: historical range backtests are per-symbol. A multi-symbol range
    strategy maps only its FIRST symbol here — its blended backtest is not split per name.)"""
    wanted = {s.strip().upper() for s in symbols if s and s.strip()}
    if not wanted:
        return {}
    strat_rows = (
        await session.execute(
            select(StrategyRow.id, StrategyRow.symbols_json).where(
                StrategyRow.code_path.like(_RANGE_CODE_MATCH)
            )
        )
    ).all()
    sid_symbol: dict[int, str] = {}
    for sid, syms in strat_rows:
        if syms:
            sym = str(syms[0]).upper()
            if sym in wanted:
                sid_symbol[sid] = sym
    if not sid_symbol:
        return {}
    # Ascending created_at so the last assignment per symbol is the most recent backtest.
    results = (
        (
            await session.execute(
                select(BacktestResult)
                .where(BacktestResult.strategy_id.in_(list(sid_symbol)))
                .order_by(BacktestResult.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    evidence: dict[str, CandidateEvidence] = {}
    for r in results:
        esym = sid_symbol.get(r.strategy_id)
        m = r.metrics_json or {}
        if esym is None or m.get("win_rate") is None:
            continue
        evidence[esym] = CandidateEvidence(
            win_rate=float(m["win_rate"]),
            sharpe=(float(m["sharpe_ratio"]) if m.get("sharpe_ratio") is not None else None),
            n_trades=(int(m["trade_count"]) if m.get("trade_count") is not None else None),
            as_of=r.created_at,
            label=r.label,
        )
    return evidence


async def select_range_universe(
    session: AsyncSession,
    *,
    bar_cache: Any,
    n: int,
    universe: Iterable[str] | None = None,
    now: datetime | None = None,
) -> list[str]:
    """Today's Top-N range symbols for a universe, ranked evidence-first (realized win rate
    then the structural Range Score). Defaults to the standard liquid-large-cap pool."""
    now = now or datetime.now(UTC)
    uni = list(universe) if universe else list(DEFAULT_CANDIDATE_UNIVERSE)
    evidence = await load_range_backtest_evidence(session, uni)
    return await select_top_range_symbols(
        uni, bar_cache=bar_cache, now=now, n=n, evidence=evidence
    )


async def find_autoselect_range_strategies(
    session: AsyncSession,
) -> list[tuple[int, int, list[str] | None]]:
    """Discover range strategies opted into daily auto-selection. Returns
    ``(strategy_id, n, universe_override)`` for each strategy whose ``params_json`` carries
    ``auto_select_top_n`` > 0. Paper-variant clones (``parent_strategy_id``) are excluded."""
    rows = (
        await session.execute(
            select(StrategyRow).where(
                StrategyRow.code_path.like(_RANGE_CODE_MATCH),
                StrategyRow.parent_strategy_id.is_(None),
            )
        )
    ).scalars().all()
    targets: list[tuple[int, int, list[str] | None]] = []
    for row in rows:
        params = row.params_json or {}
        try:
            n = int(params.get(AUTOSELECT_PARAM, 0) or 0)
        except (TypeError, ValueError):
            n = 0
        if n <= 0:
            continue
        uni = params.get(AUTOSELECT_UNIVERSE_PARAM) or None
        targets.append((row.id, n, list(uni) if uni else None))
    return targets


async def refresh_range_universe(
    session_factory: async_sessionmaker[AsyncSession],
    engine: Any,
    bar_cache: Any,
    *,
    strategy_id: int,
    n: int,
    universe: Iterable[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Re-point one range strategy to today's Top-N: select → (if running) stop → update
    symbols → audit → (if it was running) start. Idempotent: a no-op when the selection
    equals the current universe. Fail-soft — returns a status dict, never raises."""
    now = now or datetime.now(UTC)

    async with session_factory() as session:
        row = await session.get(StrategyRow, strategy_id)
        if row is None:
            return {"strategy_id": strategy_id, "status": "not_found"}
        # LIVE is out of scope (ADR 0028): the stop→start cycle passes through IDLE and
        # register() maps IDLE→PAPER, which would silently downgrade a live book; and
        # rotating a live universe daily warrants its own ADR + stronger controls. Skip it.
        if row.status == StrategyStatus.LIVE:
            logger.warning("range_autoselect_skipped_live", strategy_id=strategy_id)
            return {"strategy_id": strategy_id, "status": "skipped_live"}
        prev_symbols = [str(s).upper() for s in (row.symbols_json or [])]
        user_id = row.user_id
        was_running = row.status in ACTIVE_STRATEGY_STATUSES
        selected = await select_range_universe(
            session, bar_cache=bar_cache, n=n, universe=universe, now=now
        )

    if not selected:
        logger.warning("range_autoselect_no_candidates", strategy_id=strategy_id)
        return {"strategy_id": strategy_id, "status": "no_candidates", "selected": []}
    if selected == prev_symbols:
        return {
            "strategy_id": strategy_id, "status": "unchanged", "selected": selected,
            "was_running": was_running,
        }

    # Stop first so the symbol update passes the IDLE-only guard (engine commits its own tx).
    if was_running:
        await engine.unregister(strategy_id, reason="daily_range_autoselect")

    async with session_factory() as session:
        row = await session.get(StrategyRow, strategy_id)
        if row is None:  # pragma: no cover - raced deletion
            return {"strategy_id": strategy_id, "status": "not_found"}
        row.symbols_json = selected
        row.updated_at = now
        AuditLogger.write(
            session,
            actor_type=AuditActorType.SYSTEM,
            actor_id=None,
            action=AuditAction.STRATEGY_UPDATED,
            target_type="strategy",
            target_id=row.id,
            payload={
                "changed": {"symbols": selected},
                "previous": prev_symbols,
                "source": AUTOSELECT_SOURCE,
                "n": n,
            },
            user_id=user_id,
        )
        await session.commit()

    started = False
    if was_running:
        # Re-register with the new universe. The engine sets status back to PAPER/LIVE.
        await engine.register(strategy_id)
        started = True

    logger.info(
        "range_autoselect_applied",
        strategy_id=strategy_id, selected=selected, previous=prev_symbols, restarted=started,
    )
    return {
        "strategy_id": strategy_id,
        "status": "applied",
        "selected": selected,
        "previous": prev_symbols,
        "restarted": started,
    }


async def run_daily_range_universe(
    session_factory: async_sessionmaker[AsyncSession],
    engine: Any,
    bar_cache: Any,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Scheduled pre-open entry point: for every opted-in range strategy, apply today's
    Top-N. Skips weekends. Per-strategy fail-soft so one failure can't stop the rest;
    never raises into the scheduler."""
    now = now or datetime.now(UTC)
    if now.astimezone(EASTERN).weekday() >= 5:
        logger.info("range_autoselect_skipped_weekend")
        return []
    if engine is None or bar_cache is None:
        logger.warning("range_autoselect_skipped_unwired")
        return []

    async with session_factory() as session:
        targets = await find_autoselect_range_strategies(session)
    if not targets:
        logger.info("range_autoselect_no_targets")
        return []

    results: list[dict[str, Any]] = []
    for sid, n, uni in targets:
        try:
            results.append(
                await refresh_range_universe(
                    session_factory, engine, bar_cache,
                    strategy_id=sid, n=n, universe=uni, now=now,
                )
            )
        except Exception:
            logger.exception("range_autoselect_failed", strategy_id=sid)
            results.append({"strategy_id": sid, "status": "error"})
    return results
