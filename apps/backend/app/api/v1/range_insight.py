"""``GET /api/v1/range-insight/{symbol}`` — the Range Insight panel feed (P8 §5).

Deterministic statistical summaries of a symbol's recent daily behavior. No LLM,
no forecasting (Direction Decision 2) — the response carries a disclaimer. The
Charts-rail panel (§6) consumes this.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.schemas.range_insight import (
    RangeCandidatesResponse,
    RangeInsightResponse,
)
from app.auth.stub import CurrentUser, get_current_user
from app.db.models.backtest_result import BacktestResult
from app.db.models.strategy import Strategy as StrategyRow
from app.db.session import get_session
from app.services.range_insight import (
    DEFAULT_CANDIDATE_UNIVERSE,
    CandidateEvidence,
    compute_range_insight,
    rank_range_candidates,
)

router = APIRouter(prefix="/range-insight", tags=["range-insight"])

# Range strategies reference this template; their traded symbol is symbols_json[0].
_RANGE_CODE_MATCH = "%range_trader%"


async def _load_range_backtest_evidence(
    session: AsyncSession, symbols: Iterable[str]
) -> dict[str, CandidateEvidence]:
    """Realized range-trading performance per symbol, from its most recent range backtest —
    the evidence that drives the candidate ranking ahead of the structural prior.

    A range strategy is one whose ``code_path`` references the range_trader template; its
    symbol is ``symbols_json[0]``. For each wanted symbol we take the latest
    ``BacktestResult`` (by ``created_at``) across that symbol's range strategies and read
    ``win_rate`` / ``sharpe_ratio`` / ``trade_count`` from ``metrics_json``. Symbols with no
    range backtest are simply absent (they fall back to structural ranking)."""
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


@router.get("/candidates", response_model=RangeCandidatesResponse)
async def get_range_candidates(
    request: Request,
    symbols: str | None = None,
    _user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> RangeCandidatesResponse:
    """Rank a universe so a user can pick the best symbol(s) to range-trade today.
    EVIDENCE-FIRST: symbols with a realized range backtest rank by their win rate (then
    Sharpe); the rest fall back to the structural Range Score (normalized ATR% × how
    range-bound). ``symbols`` is an optional comma-separated override; otherwise the
    default liquid-large-cap universe.

    Declared before ``/{symbol}`` so the literal path wins the route match.
    """
    bar_cache = getattr(request.app.state, "bar_cache", None)
    if bar_cache is None:
        raise HTTPException(
            status_code=503, detail="range insight unavailable (bar cache not wired)"
        )
    universe = (
        [s for s in (symbols.split(",")) if s.strip()]
        if symbols
        else list(DEFAULT_CANDIDATE_UNIVERSE)
    )
    evidence = await _load_range_backtest_evidence(session, universe)
    ranked = await rank_range_candidates(
        universe, bar_cache=bar_cache, now=datetime.now(UTC), evidence=evidence
    )
    return RangeCandidatesResponse(
        as_of=datetime.now(UTC),
        candidates=[asdict(c) for c in ranked],  # type: ignore[misc]
    )


@router.get("/{symbol}", response_model=RangeInsightResponse)
async def get_range_insight(
    symbol: str,
    request: Request,
    _user: CurrentUser = Depends(get_current_user),
) -> RangeInsightResponse:
    bar_cache = getattr(request.app.state, "bar_cache", None)
    if bar_cache is None:
        raise HTTPException(
            status_code=503, detail="range insight unavailable (bar cache not wired)"
        )
    insight = await compute_range_insight(
        symbol, bar_cache=bar_cache, now=datetime.now(UTC)
    )
    return RangeInsightResponse(**asdict(insight))
