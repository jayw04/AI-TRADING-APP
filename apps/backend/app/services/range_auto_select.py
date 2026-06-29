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
from datetime import UTC, datetime, time
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.audit.logger import AuditAction, AuditActorType, AuditLogger
from app.db.enums import (
    ACTIVE_STRATEGY_STATUSES,
    TERMINAL_ORDER_STATUSES,
    OrderSourceType,
    StrategyStatus,
)
from app.db.models.account import Account, AccountMode
from app.db.models.backtest_result import BacktestResult
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.services.range_insight import (
    DEFAULT_CANDIDATE_UNIVERSE,
    DEFAULT_HARD_FILTERS,
    CandidateEvidence,
    HardFilters,
    RangeCandidate,
    rank_range_candidates,
    top_range_symbols,
)
from app.utils.time import EASTERN

logger = structlog.get_logger(__name__)

# Range strategies reference this template; their traded symbols are symbols_json.
_RANGE_CODE_MATCH = "%range_trader%"
# Per-strategy opt-in marker (in params_json), its optional universe override, and the
# optional minimum Range-Score quality floor (ADR 0028 review #4; 0 = no floor).
AUTOSELECT_PARAM = "auto_select_top_n"
AUTOSELECT_UNIVERSE_PARAM = "auto_select_universe"
AUTOSELECT_MIN_SCORE_PARAM = "auto_select_min_score"
# Audit payload tag so this system rebalance is distinguishable from a user symbol edit.
AUTOSELECT_SOURCE = "daily_preopen_auto_select"
# Stamped into the selection evidence so a future audit can tie a pick to the ranking it used.
# v2-guarded (ADR 0028 §Open items): evidence grants top-tier priority only when win_rate >= 0.50
# AND sharpe > 0; otherwise the name ranks on its structural Range Score. Bump on rule changes.
RANKING_VERSION = "evidence-first-v2-guarded"
# Regular-trading-hours open (ET). Rotation is a PRE-OPEN act only; once the session has
# begun the day's universe is frozen (ADR 0028 §"frozen daily input" / review #2).
RTH_OPEN_ET = time(9, 30)


async def _preflight_blocker(session: AsyncSession, row: StrategyRow) -> str | None:
    """ADR 0028 / review #6 pre-flight: it is unsafe to stop→start a running sleeve that
    holds a position or has a working order — a stop mid-position could strand a fill and a
    working order could fill against the old universe. Returns a short skip reason, or None
    when clear. Checked only for the PAPER stop→start path."""
    # A working (non-terminal) order placed by this strategy.
    working = (
        await session.execute(
            select(Order.id)
            .where(
                Order.source_type == OrderSourceType.STRATEGY,
                Order.source_id == str(row.id),
                Order.status.notin_(tuple(TERMINAL_ORDER_STATUSES)),
            )
            .limit(1)
        )
    ).first()
    if working is not None:
        return "pending_order"
    # An open position in any symbol the sleeve currently trades, on its paper account.
    syms = [str(s).upper() for s in (row.symbols_json or [])]
    if syms:
        acct_id = (
            await session.execute(
                select(Account.id).where(
                    Account.user_id == row.user_id,
                    Account.broker == "alpaca",
                    Account.mode == AccountMode.paper,
                )
            )
        ).scalars().first()
        if acct_id is not None:
            held = (
                await session.execute(
                    select(Position.id)
                    .join(Symbol, Symbol.id == Position.symbol_id)
                    .where(
                        Position.account_id == acct_id,
                        Position.qty != 0,
                        Symbol.ticker.in_(syms),
                    )
                    .limit(1)
                )
            ).first()
            if held is not None:
                return "open_position"
    return None


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
        # A backtest that produced ZERO trades carries no win-rate signal — treat it as NO
        # evidence (skip it). Otherwise a degenerate 0-trade run reads as win_rate=0.0 and,
        # because it is "evidenced", sorts ABOVE genuinely range-bound non-backtested names
        # (the AAPL anomaly: AAPL's 0-trade backtest displaced real candidates). The symbol
        # then correctly falls back to structural ranking, and an older non-degenerate
        # backtest (if any) wins instead, since results are ordered oldest→newest.
        tc = m.get("trade_count")
        if tc is None or int(tc) <= 0:
            continue
        evidence[esym] = CandidateEvidence(
            win_rate=float(m["win_rate"]),
            sharpe=(float(m["sharpe_ratio"]) if m.get("sharpe_ratio") is not None else None),
            n_trades=int(tc),
            as_of=r.created_at,
            label=r.label,
        )
    return evidence


async def select_range_universe_detailed(
    session: AsyncSession,
    *,
    bar_cache: Any,
    n: int,
    universe: Iterable[str] | None = None,
    now: datetime | None = None,
    min_score: float = 0.0,
    hard_filters: HardFilters | None = None,
) -> tuple[list[str], list[RangeCandidate]]:
    """Today's Top-N range symbols PLUS the full ranked candidate list (for audit evidence).
    Two-step (ADR 0028 review #4): hard filters → qualified universe → evidence-first Range
    Score → Top-N. Only **qualified** names (price/ADV/ATR%) are selectable; range-boundness is
    a *score* factor, not a gate. ``min_score`` is the optional absolute cutoff (0 = research
    default → collect Top-N regardless of absolute score). Defaults to the liquid-large-cap pool."""
    now = now or datetime.now(UTC)
    filters = hard_filters if hard_filters is not None else DEFAULT_HARD_FILTERS
    uni = list(universe) if universe else list(DEFAULT_CANDIDATE_UNIVERSE)
    evidence = await load_range_backtest_evidence(session, uni)
    ranked = await rank_range_candidates(
        uni, bar_cache=bar_cache, now=now, evidence=evidence, hard_filters=filters
    )
    selected = top_range_symbols(
        ranked, n=n, require_suitable=False, require_qualified=True, min_score=min_score
    )
    return selected, ranked


async def select_range_universe(
    session: AsyncSession,
    *,
    bar_cache: Any,
    n: int,
    universe: Iterable[str] | None = None,
    now: datetime | None = None,
    min_score: float = 0.0,
    hard_filters: HardFilters | None = None,
) -> list[str]:
    """Today's Top-N range symbols for a universe (thin wrapper over the detailed form)."""
    selected, _ = await select_range_universe_detailed(
        session, bar_cache=bar_cache, n=n, universe=universe, now=now,
        min_score=min_score, hard_filters=hard_filters,
    )
    return selected


def _selection_evidence(
    ranked: list[RangeCandidate], selected: list[str], *, n: int, min_score: float
) -> dict[str, Any]:
    """Build the auditable selection record (ADR 0028 review #3): the chosen names with their
    scores + evidence, why the others were excluded, and the ranking version — so a future
    audit can reconstruct exactly what the engine saw and picked, not just the symbol diff."""
    chosen = set(selected)

    def _excluded_reason(c: RangeCandidate) -> str:
        if c.status != "ok":
            return "insufficient_data"
        if not c.qualified:  # failed a hard filter (price / ADV / ATR%)
            return c.qualify_reason or "not_qualified"
        if c.score < min_score:
            return "below_min_score"
        return "rank_beyond_n"

    return {
        "ranking_version": RANKING_VERSION,
        "n_requested": n,
        "min_score": min_score,
        "universe_size": len(ranked),
        "qualified_size": sum(1 for c in ranked if c.qualified),
        "selected": [
            {
                "symbol": c.symbol, "rank": c.rank, "score": c.score,
                "win_rate": c.win_rate, "sharpe": c.sharpe, "backtested": c.backtested,
            }
            for c in ranked if c.symbol in chosen
        ],
        "excluded": [
            {"symbol": c.symbol, "reason": _excluded_reason(c)}
            for c in ranked if c.symbol not in chosen
        ][:10],
    }


async def find_autoselect_range_strategies(
    session: AsyncSession,
) -> list[tuple[int, int, list[str] | None, float]]:
    """Discover range strategies opted into daily auto-selection. Returns
    ``(strategy_id, n, universe_override, min_score)`` for each strategy whose ``params_json``
    carries ``auto_select_top_n`` > 0. Paper-variant clones (``parent_strategy_id``) excluded."""
    rows = (
        await session.execute(
            select(StrategyRow).where(
                StrategyRow.code_path.like(_RANGE_CODE_MATCH),
                StrategyRow.parent_strategy_id.is_(None),
            )
        )
    ).scalars().all()
    targets: list[tuple[int, int, list[str] | None, float]] = []
    for row in rows:
        params = row.params_json or {}
        try:
            n = int(params.get(AUTOSELECT_PARAM, 0) or 0)
        except (TypeError, ValueError):
            n = 0
        if n <= 0:
            continue
        uni = params.get(AUTOSELECT_UNIVERSE_PARAM) or None
        try:
            min_score = float(params.get(AUTOSELECT_MIN_SCORE_PARAM, 0.0) or 0.0)
        except (TypeError, ValueError):
            min_score = 0.0
        targets.append((row.id, n, list(uni) if uni else None, min_score))
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
    min_score: float = 0.0,
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
        selected, ranked = await select_range_universe_detailed(
            session, bar_cache=bar_cache, n=n, universe=universe, now=now, min_score=min_score
        )

    if not selected:
        logger.warning("range_autoselect_no_candidates", strategy_id=strategy_id)
        return {"strategy_id": strategy_id, "status": "no_candidates", "selected": []}
    if selected == prev_symbols:
        return {
            "strategy_id": strategy_id, "status": "unchanged", "selected": selected,
            "was_running": was_running,
        }

    # Pre-flight (ADR 0028 / review #6): never stop→start a running sleeve that holds a
    # position or has a working order. (IDLE strategies aren't trading → nothing to strand.)
    if was_running:
        async with session_factory() as session:
            row = await session.get(StrategyRow, strategy_id)
            blocker = await _preflight_blocker(session, row) if row is not None else "not_found"
        if blocker:
            logger.warning(
                "range_autoselect_skipped_preflight", strategy_id=strategy_id, reason=blocker
            )
            return {"strategy_id": strategy_id, "status": f"skipped_{blocker}"}

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
                # ADR 0028 review #3 — full selection evidence (scores, ranking version,
                # excluded names + reasons), not just the symbol diff.
                "selection": _selection_evidence(
                    ranked, selected, n=n, min_score=min_score
                ),
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
    now_et = now.astimezone(EASTERN)
    if now_et.weekday() >= 5:
        logger.info("range_autoselect_skipped_weekend")
        return []
    # Pre-open only: once RTH has begun the day's universe is frozen — no intraday rotation
    # (ADR 0028 §"frozen daily input" / review #2). Guards a mis-scheduled/late run.
    if now_et.time() >= RTH_OPEN_ET:
        logger.warning("range_autoselect_skipped_after_open", at=now_et.isoformat())
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
    for sid, n, uni, min_score in targets:
        try:
            results.append(
                await refresh_range_universe(
                    session_factory, engine, bar_cache,
                    strategy_id=sid, n=n, universe=uni, now=now, min_score=min_score,
                )
            )
        except Exception:
            logger.exception("range_autoselect_failed", strategy_id=sid)
            results.append({"strategy_id": sid, "status": "error"})
    return results
