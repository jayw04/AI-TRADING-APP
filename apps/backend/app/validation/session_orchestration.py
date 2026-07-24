"""Runnable forward session — the orchestration (R5c-2b2).

`run_production_session` is the one function that assembles a complete, runnable session from injected
production dependencies and runs it. It captures exactly one snapshot, wires that snapshot's digest to
the decision provider, the evaluator and the runner, binds the provider evidence into the committed
record, and persists the instrument book only after the observation commits.

Dependencies are INJECTED (the store, accessor, proxy series, price and probe callables) so the
orchestration is testable against a synthetic store; the production caller (R5e) resolves them from the
governed deployment configuration. Nothing here is reachable from readiness — building the instrument
means a session is actually being run.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.validation.account4_probe import Account4Probe
from app.validation.decision_provider import (
    ProductionDecisionProvider,
    capture_instrument_snapshot,
)
from app.validation.forward_session_runner import ForwardSessionRunner, SessionRunResult
from app.validation.forward_window import ForwardRunContext, IntegrityStop
from app.validation.observation_store import Account4StateProbe, committed_observations
from app.validation.production_providers import (
    ProductionBarsProvider,
    ProductionScoresProvider,
)
from app.validation.session_assembly import (
    BarsCallSpec,
    EvidenceBindingDecisionProvider,
    InstrumentBookLifecycle,
    SnapshotOnce,
)
from app.validation.shadow_ledger import ShadowLedger


@dataclass(frozen=True)
class SessionRuntime:
    """The injected production surface a session runs against."""
    store: Any                                    # a read-only FactorDataStore
    accessor: Any                                 # FactorAccessor over the same store
    store_identity: str                           # R5c-1's value-level data-store identity
    universe_fn: Callable[[date, int], list[str]]
    proxy_closes: dict[date, float]
    session_dates: tuple[date, ...]
    strict_price_fn: Callable[[str, date], float]     # raises PriceUnavailable on a missing mark
    account4_probe: Callable[[], Account4Probe]       # the authoritative live read
    context_builder: Callable[[date], ForwardRunContext]
    readiness: Any                                    # R5a/R5b gate: assess + verify_unchanged
    market_symbol: str = "SPY"


def build_strategy_and_adapter(runtime: SessionRuntime, *, strategy_id: int, session: date,
                               starting_capital: float) -> tuple[Any, Any, Any, Any]:
    """Construct the REAL frozen MomentumDaily on a deterministic adapter, wired to the production
    providers. The adapter's book is restored by the caller before the run."""
    from app.strategies.drift_audit_driver import DriftCtxAdapter

    momentum_daily = importlib.import_module("strategies_user.templates.momentum_daily")
    scores = ProductionScoresProvider(
        accessor=runtime.accessor, store_identity=runtime.store_identity,
        universe_fn=runtime.universe_fn, trading_days=lambda d: d in set(runtime.session_dates))
    bars = ProductionBarsProvider(
        proxy_closes=runtime.proxy_closes, name_prices=runtime.strict_price_fn,
        store_identity=runtime.store_identity, market_symbol=runtime.market_symbol,
        session_dates=runtime.session_dates)

    adapter = DriftCtxAdapter(
        symbols=[runtime.market_symbol, *_universe_symbols(runtime, session)],
        strategy_id=strategy_id, scores_provider=scores, bars_provider=bars,
        equity=Decimal(str(starting_capital)), sim_day=session)
    strategy = momentum_daily.MomentumDaily(ctx=adapter, params=_frozen_params())
    return strategy, adapter, scores, bars


def _universe_symbols(runtime: SessionRuntime, session: date) -> list[str]:
    try:
        return list(runtime.universe_fn(session, 200))
    except Exception:                             # pragma: no cover - the run stops on it downstream
        return []


def _frozen_params() -> dict[str, Any]:
    momentum_daily = importlib.import_module("strategies_user.templates.momentum_daily")
    return {**momentum_daily.MomentumDaily.default_params, "order_pacing_seconds": 0.0,
            "regime_mode": "graduated", "use_market_regime_filter": True,
            "initial_seed_investable_gross": 0.60}


def run_production_session(
    runtime: SessionRuntime,
    session: date,
    *,
    store_dir: Path,
    ledger_path: Path,
    book_path: Path,
    strategy_id: int,
    shadow_ledger_identity: str,
    instrument_durable_state_id: str,
    starting_capital: float,
    turnover_cost_bps: float,
    backstop_days: int,
    weight_drift_pct: float,
    deployment_blob: dict[str, Any],
    run_timestamp: str,
    deployed_tree_identity: str,
    regime_source_identity: str,
) -> SessionRunResult:
    """Assemble and run one governed session. Captures ONE snapshot, wires its digest end to end, binds
    provider evidence into the record, and writes the instrument book after the observation commits."""
    records = committed_observations(store_dir)
    count = len(records)
    last_session = records[-1].session_date if records else None

    strategy, adapter, scores, bars = build_strategy_and_adapter(
        runtime, strategy_id=strategy_id, session=session, starting_capital=starting_capital)

    # restore + reconcile the instrument's own durable book BEFORE it decides. A book that disagrees
    # with committed storage stops the run for governed recovery — surfaced as a fail-closed result, not
    # an uncaught exception, so the operator sees the divergence rather than a crash.
    lifecycle = InstrumentBookLifecycle(book_path=book_path, starting_capital=starting_capital,
                                        deployment_blob=deployment_blob)
    try:
        lifecycle.restore(adapter, committed_count=count, last_committed_session=last_session)
    except IntegrityStop as exc:
        from app.validation.forward_session_runner import SessionRunStatus
        return SessionRunResult(
            status=SessionRunStatus.INTEGRITY_STOP, session_date=session.isoformat(),
            session_count=count, exception_code="INSTRUMENT_BOOK_DIVERGENCE",
            detail=str(exc), operational_exceptions=("INSTRUMENT_BOOK_DIVERGENCE",))

    # ONE snapshot, taken now, before the decision reads mutable state
    snapshot_once = SnapshotOnce(capture_instrument_snapshot)
    snapshot = snapshot_once(
        strategy, adapter, session, captured_at=run_timestamp,
        regime_source_identity=regime_source_identity, store_identity_sha256=runtime.store_identity)

    inner_provider = ProductionDecisionProvider(
        strategy=strategy, adapter=adapter, snapshot=snapshot,
        durable_state_id=instrument_durable_state_id, fill_price_fn=runtime.strict_price_fn)
    # The Option-B wiring makes a deterministic number of provider calls per evaluation: the frozen
    # class scores once during `_evaluate`, and `capture_seam` re-derives the seam scores once more —
    # both for the same session. The regime reads the market proxy exactly once. These counts are the
    # governed cardinality; a departure means the decision's inputs cannot be identified.
    decision_provider = EvidenceBindingDecisionProvider(
        inner=inner_provider, scores_provider=scores, bars_provider=bars,
        bars_call_spec=BarsCallSpec(market_symbol=runtime.market_symbol, ma_sessions=200))

    def ledger_factory() -> ShadowLedger:
        return ShadowLedger.start(starting_capital=starting_capital,
                                  turnover_cost_bps=turnover_cost_bps, backstop_days=backstop_days,
                                  weight_drift_pct=weight_drift_pct)

    runner = ForwardSessionRunner(
        store_dir=store_dir, ledger_path=ledger_path, decision_provider=decision_provider,
        price_fn=runtime.strict_price_fn, account4_probe=_commit_probe(runtime),
        context_builder=runtime.context_builder, ledger_factory=ledger_factory,
        deployed_tree_identity=deployed_tree_identity, shadow_ledger_identity=shadow_ledger_identity,
        expected_snapshot_digest=snapshot.snapshot_digest,
        readiness=runtime.readiness,
        authoritative_account4_probe=runtime.account4_probe,
        on_committed=_book_writer(lifecycle, adapter))

    return runner.run_session(session, run_timestamp=run_timestamp)


def _book_writer(lifecycle: InstrumentBookLifecycle, adapter: Any) -> Callable[[int, str], None]:
    def write(sequence: int, iso: str) -> None:
        lifecycle.persist_after_commit(adapter, sequence=sequence, session_date=iso)

    return write


def _commit_probe(runtime: SessionRuntime) -> Callable[[], Account4StateProbe]:
    """The commit protocol's own before/after probe, derived from the SAME authoritative read the
    runner's pre/post probes use, so the two bindings cannot disagree about the live book."""
    def probe() -> Account4StateProbe:
        return runtime.account4_probe().to_commit_probe()

    return probe
