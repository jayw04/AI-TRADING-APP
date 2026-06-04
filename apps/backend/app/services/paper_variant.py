"""Paper-variant runner (P6b §2a-variant, ADR 0007).

Spawns / terminates a cloned ``strategies`` row that runs a proposal's params
forward on the user's paper account, in parallel with the LIVE parent. §2a is
the foundation only — NO comparison metrics (§2b), NO evidence bundle / gate /
promotion (§3).

Decisions (see the §2a-variant doc): variant = a cloned Strategy row with
``parent_strategy_id`` + ``status=PAPER_VARIANT`` (D1/D2); shared paper account
(D3); ``ACCEPTED → EVALUATING`` on spawn, ``→ REJECTED`` on terminate (D4); one
in-flight variant per parent (D7); two audit actions PAPER_VARIANT_SPAWNED /
PAPER_VARIANT_TERMINATED (D9).

Audit discipline: one row per transaction (the §1a-drift hash-chain contract) —
spawn and terminate each write their two audit rows in SEPARATE commits.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.db.enums import StrategyStatus
from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.services.drift_detection import (
    find_baseline_for_strategy,
    reconstruct_round_trips,
)
from app.services.equity_curve import (
    DEFAULT_CAPITAL_BASE,
    reconstruct_equity_curve,
)
from app.services.proposal_evaluation import _apply_changes
from app.strategies.metrics import (
    avg_return_per_trade,
    max_drawdown,
    sharpe_ratio,
    win_rate,
)

logger = structlog.get_logger(__name__)

# D6 (iv): a variant older than this is force-terminated by the expiry sweep.
VARIANT_MAX_AGE_DAYS = 90


class PaperVariantService:
    def __init__(self, session: AsyncSession, engine: Any = None) -> None:
        self._session = session
        self._engine = engine  # app.state.strategy_engine; None in tests/data-only boots

    async def _in_flight_variant_for(self, parent_strategy_id: int) -> Strategy | None:
        return (
            await self._session.execute(
                select(Strategy)
                .where(Strategy.parent_strategy_id == parent_strategy_id)
                .where(Strategy.status == StrategyStatus.PAPER_VARIANT)
            )
        ).scalars().first()

    async def spawn(self, *, proposal_id: int, user_id: int) -> Strategy:
        """Clone the parent with the proposal's params, run it on paper, and
        move the proposal ACCEPTED → EVALUATING. Raises ValueError on guard
        failures (mapped to 400/409 by the endpoint)."""
        proposal = await self._session.get(StrategyProposal, proposal_id)
        if proposal is None or proposal.user_id != user_id:
            raise ValueError("proposal_not_found")
        if proposal.state != ProposalState.ACCEPTED:
            raise ValueError("proposal_not_accepted")
        parent = await self._session.get(Strategy, proposal.strategy_id)
        if parent is None or parent.user_id != user_id:
            raise ValueError("parent_not_found")
        if parent.status != StrategyStatus.LIVE:  # ADR 0007: live-strategy updates only
            raise ValueError("parent_not_live")
        if await self._in_flight_variant_for(parent.id) is not None:  # D7
            raise ValueError("variant_already_in_flight")

        changes = (proposal.proposal_payload_json or {}).get("changes") or []
        variant_params = _apply_changes(dict(parent.params_json or {}), changes)
        now = datetime.now(UTC)
        variant = Strategy(
            user_id=parent.user_id,
            name=f"{parent.name} (variant p{proposal_id})",
            version=parent.version,
            type=parent.type,
            code_path=parent.code_path,
            symbols_json=list(parent.symbols_json or []),
            params_json=variant_params,
            schedule=parent.schedule,
            status=StrategyStatus.PAPER_VARIANT,
            parent_strategy_id=parent.id,
            created_at=now,
            updated_at=now,
        )
        self._session.add(variant)
        await self._session.flush()  # variant.id

        # Commit 1: variant row + its spawn audit (one audit row this txn).
        AuditLogger.write(
            self._session,
            actor_type=AuditActorType.AGENT,
            actor_id="paper_variant",
            action=AuditAction.PAPER_VARIANT_SPAWNED,
            target_type="strategy",
            target_id=variant.id,
            payload={
                "proposal_id": proposal_id,
                "parent_strategy_id": parent.id,
                "variant_strategy_id": variant.id,
            },
            user_id=user_id,
        )
        await self._session.commit()

        # Commit 2: proposal ACCEPTED → EVALUATING + its transition audit.
        proposal.evaluation_results_json = {
            **(proposal.evaluation_results_json or {}),
            "paper_variant": {
                "variant_strategy_id": variant.id,
                "evaluation_started_at": now.isoformat(),
            },
        }
        proposal.state = ProposalState.EVALUATING
        proposal.transitioned_at = now
        proposal.updated_at = now
        AuditLogger.write(
            self._session,
            actor_type=AuditActorType.USER,
            actor_id=str(user_id),
            action=AuditAction.STRATEGY_PROPOSAL_TRANSITIONED,
            target_type="strategy_proposal",
            target_id=proposal.id,
            payload={"from": "ACCEPTED", "to": "EVALUATING", "variant_strategy_id": variant.id},
            user_id=user_id,
        )
        await self._session.commit()

        # Register AFTER commit (the engine opens its own session to read the row).
        if self._engine is not None:
            await self._engine.register(variant.id)
        return variant

    async def terminate(
        self, *, variant_strategy_id: int, reason: str, user_id: int
    ) -> None:
        """Stop a running variant, terminate its proposal (EVALUATING → REJECTED),
        and audit. Idempotent-ish: a missing/already-stopped variant is a no-op."""
        variant = await self._session.get(Strategy, variant_strategy_id)
        if variant is None or variant.parent_strategy_id is None:
            return

        # Engine unregister (its own session: cancels job, closes run, sets IDLE,
        # writes its own STRATEGY_UNREGISTERED audit — one row per txn).
        if self._engine is not None:
            await self._engine.unregister(variant.id, reason=f"paper_variant_{reason}")
        else:
            variant.status = StrategyStatus.IDLE
            variant.updated_at = datetime.now(UTC)

        # Commit: termination audit (one row this txn).
        AuditLogger.write(
            self._session,
            actor_type=AuditActorType.AGENT,
            actor_id="paper_variant",
            action=AuditAction.PAPER_VARIANT_TERMINATED,
            target_type="strategy",
            target_id=variant.id,
            payload={"reason": reason, "parent_strategy_id": variant.parent_strategy_id},
            user_id=user_id,
        )
        await self._session.commit()

        # Commit: proposal EVALUATING → REJECTED + its transition audit.
        proposal = (
            await self._session.execute(
                select(StrategyProposal)
                .where(StrategyProposal.strategy_id == variant.parent_strategy_id)
                .where(StrategyProposal.state == ProposalState.EVALUATING)
            )
        ).scalars().first()
        if proposal is not None:
            now = datetime.now(UTC)
            proposal.state = ProposalState.REJECTED
            proposal.transitioned_at = now
            proposal.updated_at = now
            AuditLogger.write(
                self._session,
                actor_type=AuditActorType.USER,
                actor_id=str(user_id),
                action=AuditAction.STRATEGY_PROPOSAL_TRANSITIONED,
                target_type="strategy_proposal",
                target_id=proposal.id,
                payload={"from": "EVALUATING", "to": "REJECTED", "reason": reason},
                user_id=user_id,
            )
            await self._session.commit()

    async def terminate_for_parent(
        self, *, parent_strategy_id: int, reason: str, user_id: int
    ) -> None:
        """Terminate the in-flight variant for a parent (D8 — e.g. another
        proposal applied to the parent). No-op if none."""
        v = await self._in_flight_variant_for(parent_strategy_id)
        if v is not None:
            await self.terminate(
                variant_strategy_id=v.id, reason=reason, user_id=user_id
            )


async def run_paper_variant_expiry(*, session_factory, engine=None) -> dict[str, int]:
    """D6 (iv) safety sweep: terminate PAPER_VARIANT clones older than
    VARIANT_MAX_AGE_DAYS. Prevents zombie variants (e.g. a parent that left LIVE
    without an explicit termination)."""
    cutoff = datetime.now(UTC) - timedelta(days=VARIANT_MAX_AGE_DAYS)
    terminated = 0
    async with session_factory() as session:
        variants = (
            await session.execute(
                select(Strategy)
                .where(Strategy.status == StrategyStatus.PAPER_VARIANT)
                .where(Strategy.created_at < cutoff)
            )
        ).scalars().all()
        svc = PaperVariantService(session, engine)
        for v in variants:
            await svc.terminate(
                variant_strategy_id=v.id, reason="expired", user_id=v.user_id
            )
            terminated += 1
    logger.info("paper_variant_expiry_sweep", terminated=terminated)
    return {"terminated": terminated}


def register_paper_variant_expiry_job(scheduler, session_factory, engine) -> None:
    """Register the 6-hourly variant-expiry sweep on the APScheduler instance
    (WorkbenchScheduler.scheduler), inside the alpaca-enabled boot block."""
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler.add_job(
        run_paper_variant_expiry,
        IntervalTrigger(hours=6),
        kwargs={"session_factory": session_factory, "engine": engine},
        id="paper_variant_expiry",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    logger.info("paper_variant_expiry_job_registered")


# ----- P6b §2b-variant: variant-vs-live comparison metrics -----


@dataclass(frozen=True)
class VariantSideMetrics:
    """One side's (variant or live-parent) metrics over the comparison window.

    Built by calling the shared §1a-drift metric FUNCTIONS — ``metrics.py`` has
    no ``compute_metrics``/``BacktestMetrics``. ``sharpe_ratio`` and
    ``max_drawdown`` come from the reconstructed equity curve; ``win_rate`` and
    ``avg_return_per_trade`` from the reconstructed round-trips."""

    trade_count: int
    win_rate: float
    avg_return_per_trade: float
    sharpe_ratio: float
    max_drawdown: float


@dataclass(frozen=True)
class VariantComparison:
    """Apples-to-apples variant-vs-live comparison. Both sides share the same
    capital_base and the same window ``[variant.created_at, now]``."""

    parent_strategy_id: int
    variant_strategy_id: int
    window_start: datetime
    window_end: datetime
    live_metrics: VariantSideMetrics
    variant_metrics: VariantSideMetrics
    deltas: dict[str, float | None]
    live_trade_count: int
    variant_trade_count: int


async def find_in_flight_variant(
    session: AsyncSession, parent_strategy_id: int
) -> Strategy | None:
    """Return the in-flight PAPER_VARIANT clone for a parent strategy, or None.
    Per the §2a concurrency guard there is at most one in-flight variant per
    parent. Module-level (vs the service's private ``_in_flight_variant_for``)
    so the read endpoint can call it without constructing the service."""
    return (
        await session.execute(
            select(Strategy)
            .where(Strategy.parent_strategy_id == parent_strategy_id)
            .where(Strategy.status == StrategyStatus.PAPER_VARIANT)
        )
    ).scalars().first()


def _read_capital_base(baseline_metrics_json: dict[str, Any] | None) -> Decimal:
    """Capital base for Sharpe normalization. ``BacktestResult`` has no
    ``config_json`` — the initial equity lives in ``metrics_json.starting_equity``
    (a float written by the backtester). $100k default when there is no baseline
    or the key is absent."""
    if not baseline_metrics_json:
        return DEFAULT_CAPITAL_BASE
    raw = baseline_metrics_json.get("starting_equity")
    if raw is None:
        return DEFAULT_CAPITAL_BASE
    return Decimal(str(raw))


def _pct_delta(variant: float | None, live: float | None) -> float | None:
    """Relative percentage delta ``(variant - live) / |live| * 100``. None if
    either input is None or the denominator is zero."""
    if variant is None or live is None:
        return None
    if live == 0:
        return None
    return ((variant - live) / abs(live)) * 100


async def compare_variant_to_parent(
    session: AsyncSession,
    variant_strategy_id: int,
    bar_cache: Any = None,
) -> VariantComparison | None:
    """Compute apples-to-apples variant-vs-parent metrics.

    Both sides use the SAME capital_base (load-bearing for Sharpe comparability)
    and the SAME window ``[variant.created_at, now]``. ``bar_cache`` is
    ``app.state.bar_cache`` (None in tests/data-only boots → equity curves
    degenerate to flat/empty, which is safe). Returns None if the id is not an
    in-flight variant or the parent is gone."""
    variant = await session.get(Strategy, variant_strategy_id)
    if variant is None or variant.parent_strategy_id is None:
        return None

    parent_id = variant.parent_strategy_id
    parent = await session.get(Strategy, parent_id)
    if parent is None:
        return None

    # SQLite returns DateTime(tz=True) naive — coerce so window/curve math is
    # tz-consistent (the equity-curve fill walk compares against aware EODs).
    created = variant.created_at
    start = created if created.tzinfo is not None else created.replace(tzinfo=UTC)
    end = datetime.now(UTC)

    # Capital base from the parent's baseline backtest (shared across both sides).
    baseline = await find_baseline_for_strategy(session, parent)
    capital_base = _read_capital_base(baseline.metrics_json if baseline else None)

    parent_curve = await reconstruct_equity_curve(
        session, parent_id, start, end, capital_base, bar_cache=bar_cache,
    )
    variant_curve = await reconstruct_equity_curve(
        session, variant_strategy_id, start, end, capital_base, bar_cache=bar_cache,
    )

    # Round-trips for the trade-based metrics (reuses §1a-drift).
    parent_trips = await reconstruct_round_trips(session, parent_id, start)
    variant_trips = await reconstruct_round_trips(session, variant_strategy_id, start)

    def _side(trips: list[Any], curve: list[tuple[datetime, Decimal]]) -> VariantSideMetrics:
        ec = [(t, float(e)) for t, e in curve]
        return VariantSideMetrics(
            trade_count=len(trips),
            win_rate=win_rate([t.pnl for t in trips]),
            avg_return_per_trade=avg_return_per_trade([t.ret for t in trips]),
            sharpe_ratio=sharpe_ratio(ec),
            max_drawdown=max_drawdown(ec),
        )

    parent_metrics = _side(parent_trips, parent_curve)
    variant_metrics = _side(variant_trips, variant_curve)

    deltas: dict[str, float | None] = {
        "sharpe_delta_pct": _pct_delta(
            variant_metrics.sharpe_ratio, parent_metrics.sharpe_ratio,
        ),
        "max_drawdown_delta_pct": _pct_delta(
            variant_metrics.max_drawdown, parent_metrics.max_drawdown,
        ),
        "win_rate_delta_pp": (variant_metrics.win_rate - parent_metrics.win_rate) * 100,
        "avg_return_delta_pct": _pct_delta(
            variant_metrics.avg_return_per_trade,
            parent_metrics.avg_return_per_trade,
        ),
    }

    return VariantComparison(
        parent_strategy_id=parent_id,
        variant_strategy_id=variant_strategy_id,
        window_start=start,
        window_end=end,
        live_metrics=parent_metrics,
        variant_metrics=variant_metrics,
        deltas=deltas,
        live_trade_count=len(parent_trips),
        variant_trade_count=len(variant_trips),
    )
