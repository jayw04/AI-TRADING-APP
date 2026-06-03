"""Strategy drift detection (P6b §1a-drift).

Compare a live strategy's recent behavior to its backtest baseline and surface
divergence advisorily. Runs on the morning-brief cadence (Q3) and writes a
``STRATEGY_DRIFT_DETECTED`` audit row per drifted strategy (Q4) — it takes no
action.

Settled decisions (8-question turn):
- v1 metrics: ``win_rate`` + ``avg_return_per_trade`` (Q1 multi-metric composite,
  scoped to the two SIZING-INVARIANT dimensions; live Sharpe/max-dd deferred).
- Baseline = most recent COMPLETED ``BacktestResult`` matching the strategy's
  current ``params_json`` (Q2); skip ``no_baseline`` if none.
- Active strategies only (``Strategy.status`` ∈ ``ACTIVE_STRATEGY_STATUSES``).

Correctness invariant: this module imports the formula functions from
``app.strategies.metrics`` — it never re-implements win_rate / avg-return — and
the baseline is computed by the SAME functions on the backtest's ``trades_json``,
so live-vs-baseline is genuinely apples-to-apples.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.db.enums import ACTIVE_STRATEGY_STATUSES, OrderSide, OrderSourceType
from app.db.models.backtest_result import BacktestResult
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.strategy import Strategy
from app.db.models.symbol import Symbol
from app.strategies.metrics import avg_return_per_trade, win_rate

logger = structlog.get_logger(__name__)

# Threshold defaults (tunable via agent_envelope_json.drift_thresholds). The
# second metric is a sizing-invariant avg RETURN per trade, not dollar avg-pnl.
DEFAULT_WIN_RATE_ABSOLUTE_PCT = 10  # 10 percentage points
DEFAULT_AVG_RETURN_RELATIVE_PCT = 25  # 25% relative change in avg return/trade
DEFAULT_MIN_TRADES = 20
DEFAULT_LOOKBACK_DAYS = 30

# Bound the per-strategy baseline scan (most-recent-first).
_BASELINE_SCAN_LIMIT = 20


# ----- value types -----


@dataclass(frozen=True)
class RoundTrip:
    """A reconstructed live round-trip (entry leg(s) → exit leg). ``pnl`` is net
    of commissions; ``ret`` is the sizing-invariant fractional return."""

    symbol: str
    qty: float
    entry_price: float
    exit_price: float
    side: str  # "long" | "short"
    pnl: float

    @property
    def ret(self) -> float:
        notional = self.entry_price * self.qty
        return self.pnl / notional if notional else 0.0


@dataclass(frozen=True)
class DriftMetrics:
    """v1 comparison surface — win_rate + avg_return_per_trade, the only
    sizing-invariant metrics computed live (Sharpe/max-dd deferred)."""

    trade_count: int
    win_rate: float  # [0, 1]
    avg_return_per_trade: float  # mean per-trade fractional return


# ----- result types -----


@dataclass(frozen=True)
class DriftFinding:
    strategy_id: int
    live_metrics: DriftMetrics
    baseline_metrics: DriftMetrics
    win_rate_delta_pp: float  # live - baseline, in percentage points
    avg_return_delta_pct: float  # (live - baseline) / abs(baseline), as a percentage
    breached: list[str]  # which thresholds crossed
    detected_at: datetime


@dataclass(frozen=True)
class DriftSkip:
    strategy_id: int
    reason: str  # "no_baseline" | "insufficient_trades" | "not_active"


@dataclass(frozen=True)
class DriftWithin:
    strategy_id: int
    live_metrics: DriftMetrics
    baseline_metrics: DriftMetrics
    win_rate_delta_pp: float
    avg_return_delta_pct: float


DriftResult = DriftFinding | DriftSkip | DriftWithin


# ----- helpers -----


def _canonicalize(value: Any) -> Any:
    """Recursively stringify leaf scalars so type drift doesn't break matching.

    NOTE: ``json.dumps(..., default=str)`` does NOT do this — ``default`` only
    fires for non-JSON-serializable objects, so ``1`` and ``"1"`` would diverge.
    The APPLY path's ``change.get("to")`` can store an int where the strategy
    has a stringified Decimal (or vice versa), so we coerce every leaf to ``str``
    before serializing. Lossy (``1`` and ``1.0`` differ as ``"1"``/``"1.0"``);
    escalate to a structural compare if false-negative baseline matches surface.
    """
    if isinstance(value, dict):
        return {k: _canonicalize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_canonicalize(v) for v in value]
    return str(value)


def _canonical_params(params: dict[str, Any] | None) -> str:
    """Normalized form for params_json comparison (leaf-stringified)."""
    if not params:
        return "{}"
    return json.dumps(_canonicalize(params), sort_keys=True)


def _read_thresholds(envelope: dict[str, Any] | None) -> dict[str, Any]:
    """Read ``drift_thresholds`` from ``agent_envelope_json`` with defaults."""
    e = (envelope or {}).get("drift_thresholds") or {}
    return {
        "win_rate_absolute_pct": e.get(
            "win_rate_absolute_pct", DEFAULT_WIN_RATE_ABSOLUTE_PCT
        ),
        "avg_return_per_trade_relative_pct": e.get(
            "avg_return_per_trade_relative_pct", DEFAULT_AVG_RETURN_RELATIVE_PCT
        ),
        "min_trades": e.get("min_trades", DEFAULT_MIN_TRADES),
        "lookback_days": e.get("lookback_days", DEFAULT_LOOKBACK_DAYS),
    }


def _is_active(strategy: Strategy) -> bool:
    """Active set = the existing ``ACTIVE_STRATEGY_STATUSES`` frozenset
    ({PAPER, LIVE}; PENDING_LIVE deliberately excluded — it can't submit)."""
    return strategy.status in ACTIVE_STRATEGY_STATUSES


def _baseline_metrics_from_trades_json(
    trades_json: list[dict[str, Any]],
) -> DriftMetrics:
    """Baseline win_rate + avg-return from the backtest's ``trades_json`` (each
    closed ``BacktestTrade`` has ``pnl`` + ``entry_price`` + ``qty``), NOT
    ``metrics_json`` — which has no avg-return field. Uses the SHARED functions
    so the baseline matches the live computation exactly."""
    closed = [
        t
        for t in (trades_json or [])
        if t.get("pnl") is not None and t.get("entry_price") and t.get("qty")
    ]
    pnls = [float(t["pnl"]) for t in closed]
    returns = [
        float(t["pnl"]) / (float(t["entry_price"]) * float(t["qty"])) for t in closed
    ]
    return DriftMetrics(
        trade_count=len(closed),
        win_rate=win_rate(pnls),
        avg_return_per_trade=avg_return_per_trade(returns),
    )


async def find_baseline_for_strategy(
    session: AsyncSession, strategy: Strategy
) -> BacktestResult | None:
    """Most recent ``BacktestResult`` whose ``params_json`` matches the
    strategy's current params (normalized). A BacktestResult row only exists
    once its job completed, so "exists" implies "completed". Returns None if no
    match (caller skips ``no_baseline``)."""
    target = _canonical_params(strategy.params_json)
    rows = (
        await session.execute(
            select(BacktestResult)
            .where(BacktestResult.strategy_id == strategy.id)
            .order_by(BacktestResult.created_at.desc())
            .limit(_BASELINE_SCAN_LIMIT)
        )
    ).scalars().all()
    for r in rows:
        if _canonical_params(r.params_json) == target:
            return r
    return None


async def reconstruct_round_trips(
    session: AsyncSession, strategy_id: int, cutoff: datetime
) -> list[RoundTrip]:
    """FIFO per-symbol round-trip reconstruction from FILLS.

    ``Order`` has no fill aggregates — fills are the legs (``fills`` table:
    qty/price/commission/filled_at), joined to ``orders`` for side + source and
    to ``symbols`` for the ticker (the pdt_analyzer pattern). Each exit leg
    FIFO-matches the oldest open entry leg(s); matched-qty pnl is net of
    pro-rata commissions."""
    rows = (
        await session.execute(
            select(
                Fill.qty,
                Fill.price,
                Fill.commission,
                Fill.filled_at,
                Order.side,
                Symbol.ticker,
            )
            .join(Order, Fill.order_id == Order.id)
            .join(Symbol, Order.symbol_id == Symbol.id)
            .where(Order.source_type == OrderSourceType.STRATEGY)
            .where(Order.source_id == str(strategy_id))
            .where(Fill.filled_at >= cutoff)
            .order_by(Fill.filled_at.asc())
        )
    ).all()

    open_legs: dict[str, list[dict[str, Any]]] = {}
    trips: list[RoundTrip] = []

    for qty_d, price_d, comm_d, _filled_at, side, ticker in rows:
        qty = float(qty_d)
        price = float(price_d)
        comm_ps = (float(comm_d) / qty) if qty else 0.0  # commission per share
        queue = open_legs.setdefault(ticker, [])
        open_dir = queue[0]["direction"] if queue else None
        is_buy = side == OrderSide.BUY

        if open_dir is None:
            queue.append(
                {
                    "direction": "long" if is_buy else "short",
                    "qty": qty,
                    "price": price,
                    "comm_ps": comm_ps,
                }
            )
            continue

        scale_in = (open_dir == "long" and is_buy) or (
            open_dir == "short" and not is_buy
        )
        if scale_in:
            queue.append(
                {"direction": open_dir, "qty": qty, "price": price, "comm_ps": comm_ps}
            )
            continue

        # Exit leg — FIFO-match against oldest open entry leg(s).
        remaining = qty
        while remaining > 0 and queue:
            entry = queue[0]
            matched = min(entry["qty"], remaining)
            sign = 1.0 if entry["direction"] == "long" else -1.0
            gross = sign * (price - entry["price"]) * matched
            commission = matched * (entry["comm_ps"] + comm_ps)
            trips.append(
                RoundTrip(
                    symbol=ticker,
                    qty=matched,
                    entry_price=entry["price"],
                    exit_price=price,
                    side=entry["direction"],
                    pnl=gross - commission,
                )
            )
            entry["qty"] -= matched
            remaining -= matched
            if entry["qty"] <= 0:
                queue.pop(0)
        if remaining > 0:
            # Over-exit (sold more than the open long holds, or vice versa).
            # v1: log and drop the leftover rather than open a reversed position.
            logger.warning(
                "drift_detection_over_exit_anomaly",
                strategy_id=strategy_id,
                symbol=ticker,
                leftover=remaining,
            )

    return trips


def detect_drift(
    live: DriftMetrics, baseline: DriftMetrics, thresholds: dict[str, Any]
) -> tuple[bool, float, float, list[str]]:
    """Returns ``(is_drifted, win_rate_delta_pp, avg_return_delta_pct, breached)``.

    - ``win_rate``: ABSOLUTE percentage points.
    - ``avg_return_per_trade``: RELATIVE percentage (skipped if baseline == 0).
    """
    win_rate_delta_pp = (live.win_rate - baseline.win_rate) * 100
    breached: list[str] = []
    if abs(win_rate_delta_pp) > thresholds["win_rate_absolute_pct"]:
        breached.append("win_rate")

    avg_return_delta_pct = 0.0
    if baseline.avg_return_per_trade != 0:
        avg_return_delta_pct = (
            (live.avg_return_per_trade - baseline.avg_return_per_trade)
            / abs(baseline.avg_return_per_trade)
        ) * 100
        if abs(avg_return_delta_pct) > thresholds["avg_return_per_trade_relative_pct"]:
            breached.append("avg_return_per_trade")

    return (len(breached) > 0, win_rate_delta_pp, avg_return_delta_pct, breached)


async def run_drift_detection_for_strategy(
    session: AsyncSession, strategy: Strategy, envelope: dict[str, Any] | None
) -> DriftResult:
    """Orchestrator for one strategy. Returns DriftFinding / DriftSkip /
    DriftWithin. Does NOT write audit or commit — the caller does."""
    if not _is_active(strategy):
        return DriftSkip(strategy_id=strategy.id, reason="not_active")

    thresholds = _read_thresholds(envelope)
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=thresholds["lookback_days"])

    baseline = await find_baseline_for_strategy(session, strategy)
    if baseline is None:
        return DriftSkip(strategy_id=strategy.id, reason="no_baseline")

    trips = await reconstruct_round_trips(session, strategy.id, cutoff)
    if len(trips) < thresholds["min_trades"]:
        return DriftSkip(strategy_id=strategy.id, reason="insufficient_trades")

    live_metrics = DriftMetrics(
        trade_count=len(trips),
        win_rate=win_rate([t.pnl for t in trips]),
        avg_return_per_trade=avg_return_per_trade([t.ret for t in trips]),
    )
    baseline_metrics = _baseline_metrics_from_trades_json(baseline.trades_json or [])

    is_drift, wr_delta, ret_delta, breached = detect_drift(
        live_metrics, baseline_metrics, thresholds
    )

    if is_drift:
        return DriftFinding(
            strategy_id=strategy.id,
            live_metrics=live_metrics,
            baseline_metrics=baseline_metrics,
            win_rate_delta_pp=wr_delta,
            avg_return_delta_pct=ret_delta,
            breached=breached,
            detected_at=now,
        )
    return DriftWithin(
        strategy_id=strategy.id,
        live_metrics=live_metrics,
        baseline_metrics=baseline_metrics,
        win_rate_delta_pp=wr_delta,
        avg_return_delta_pct=ret_delta,
    )


def write_drift_audit(
    session: AsyncSession, finding: DriftFinding, *, user_id: int
) -> None:
    """Write the ``STRATEGY_DRIFT_DETECTED`` audit row. Sync staticmethod;
    ``session.add`` only — the caller commits (one row per transaction, per the
    audit hash-chain contract)."""
    AuditLogger.write(
        session,
        actor_type=AuditActorType.AGENT,
        actor_id="drift_detector",
        action=AuditAction.STRATEGY_DRIFT_DETECTED,
        target_type="strategy",
        target_id=finding.strategy_id,
        payload={
            "strategy_id": finding.strategy_id,
            "breached": finding.breached,
            "win_rate": {
                "live": finding.live_metrics.win_rate,
                "baseline": finding.baseline_metrics.win_rate,
                "delta_pp": finding.win_rate_delta_pp,
            },
            "avg_return_per_trade": {
                "live": finding.live_metrics.avg_return_per_trade,
                "baseline": finding.baseline_metrics.avg_return_per_trade,
                "delta_pct": finding.avg_return_delta_pct,
            },
            "trade_count": finding.live_metrics.trade_count,
            "detected_at": finding.detected_at.isoformat(),
        },
        user_id=user_id,
    )


async def run_drift_detection_for_user(
    session: AsyncSession, user_id: int
) -> dict[str, int]:
    """Detect drift across all of a user's active strategies and audit each
    finding. Called on the morning-brief cadence (Q3).

    Commits ONE audit row per finding (the audit hash chain requires
    one-row-per-transaction; batching siblings in a single commit would leave
    them unchained). Per-strategy failures are isolated and skipped."""
    from app.services.trading_profile import TradingProfileService

    profile = await TradingProfileService(session).get(user_id)
    envelope = profile.agent_envelope or {}

    strategies = (
        await session.execute(select(Strategy).where(Strategy.user_id == user_id))
    ).scalars().all()

    drifted = skipped = within = 0
    for strategy in strategies:
        try:
            result = await run_drift_detection_for_strategy(session, strategy, envelope)
            if isinstance(result, DriftFinding):
                write_drift_audit(session, result, user_id=user_id)
                await session.commit()  # one row per txn (hash-chain contract)
                drifted += 1
            elif isinstance(result, DriftSkip):
                skipped += 1
            else:
                within += 1
        except Exception:
            logger.exception(
                "drift_detection_failed", strategy_id=strategy.id, user_id=user_id
            )
            await session.rollback()

    logger.info(
        "drift_detection_user_pass",
        user_id=user_id,
        drifted=drifted,
        skipped=skipped,
        within=within,
    )
    return {"drifted": drifted, "skipped": skipped, "within": within}
