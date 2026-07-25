"""The production composition root for a governed forward-validation session (R5e-2).

`run_production_session` (R5c-2b2) takes its dependencies injected, which is what makes it testable
against a synthetic store — and also what left a hole: until now NOTHING in production built a
`SessionRuntime`. It was constructed only in tests. The deployment had a readiness command and a
complete session assembly with no path between them.

This module is that path, and it is deliberately the ONLY one. Everything the session runs against is
resolved HERE, from the governed deployment configuration:

  * the witness triple, through `enforce_production_witness` and nothing else — with a fresh canonical
    UTC invocation identifier as the challenge nonce, so a signature recorded from one run's challenge
    cannot satisfy another's;
  * the factor store, opened READ-ONLY, and the value-level store identity the readiness gate computes;
  * the registered universe, price, proxy and scoring constructions — the same calls the decision makes,
    never a re-implementation;
  * every path, identity and registered parameter for the run itself.

The caller supplies a session date. Nothing else. An operator who could pass a store path or a ledger
identity on the command line could point the record at hand-made evidence, and the observation would
faithfully attest to it.

## Why the witness cannot be worked around from here

`SessionRuntime` carries one `ProductionWitness`, which refuses to be constructed without the private
token only `enforce_production_witness` holds. So a future variant of this module cannot assemble a
runtime with R5d's reference implementations even by accident: there is no witness to pass unless the
gate issued it. What that does not do is stop an actor already executing arbitrary code in this process
— see `ProductionWitness` for the precise claim.

Nothing here evaluates, books or commits: it resolves, verifies and hands back. Running is
`run_production_session`. Nothing here touches Account 4 beyond the authoritative READ-ONLY probe, and
nothing imports the order path.
"""

from __future__ import annotations

import contextlib
import importlib
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.validation.account4_probe import Account4Probe, probe_account4
from app.validation.data_finality import (
    ConstructionSpec,
    DataFinalityEvidence,
    assess_data_finality,
    verify_store_unchanged,
)
from app.validation.deployment_identity import verify_deployment_identity
from app.validation.forward_deployment_config import ForwardDeploymentConfig
from app.validation.forward_window import ForwardRunContext, IntegrityStop
from app.validation.production_bindings import build_forward_context, strict_pit_price_fn
from app.validation.session_orchestration import SessionRuntime
from app.validation.witness_enforcement import (
    ProductionWitness,
    enforce_production_witness,
    new_invocation_identifier,
)

# How far back the store calendar is drawn, so the market proxy has a full MA window BEFORE the session.
#
# The frozen regime request reads `market_ma_days + 1` closes, and `build_market_proxy` computes its MA
# with `min_periods=MA_DAYS` — so a proxy built over exactly that many sessions has no MA on its first
# one, and the regime would fail open to fully invested. Four calendar years is ~1,000 sessions: the
# 201-session request, its 200-session MA, and generous slack, matching the production-faithful warm-up
# the §8 census used (real SPY history predates any window). This warms an EXISTING construction; it is
# not a new one, and `_build_proxy_closes` still fails closed if the MA is absent on the session.
CALENDAR_SPAN_YEARS = 4


class CompositionError(IntegrityStop):
    """The governed configuration could not be resolved into a runnable session. Fails closed."""


@dataclass(frozen=True)
class ResolvedSession:
    """A runtime resolved from the governed configuration, with the evidence that produced it.

    `store` is handed back so the caller can close it: the store is opened here but its lifetime spans
    the run, and a composition root that closed it would hand back a runtime that cannot read.
    """

    runtime: SessionRuntime
    store: Any
    run_kwargs: dict[str, Any]
    evidence: dict[str, Any]

    def close(self) -> None:
        # Closing must never mask a run result: the session's verdict is what the operator needs, and a
        # failure to release a read-only handle is not a governed condition.
        with contextlib.suppress(Exception):
            self.store.close()


class _GovernedReadiness:
    """The R5a/R5b data-finality gate, bound to ONE store and ONE construction.

    The runner calls `assess` before it reads and `verify_unchanged` after, and the pair must be bound
    to the same store: assessing one store and verifying another would prove nothing at all. Holding
    both against a single instance is what makes that structural rather than a convention.

    `assess` is memoized per session, for correctness before performance. The composition root must
    assess to obtain the value-level store identity the providers are bound to, and the runner assesses
    again as the first step of its governed sequence. Two independent assessments could disagree — the
    store identity written into the providers would then differ from the one the record attests, and
    the observation would claim inputs it did not use. One assessment per session removes that
    possibility, and removes a second full streaming digest of the consumed rows as a side effect.

    This does NOT weaken the store-unchanged property: `verify_unchanged` deliberately re-streams
    after the reads and is never memoized. Caching what was measured before the reads is the point;
    caching what is measured after them would defeat it.
    """

    def __init__(self, store: Any, config: ForwardDeploymentConfig,
                 construction: ConstructionSpec) -> None:
        self._store = store
        self._config = config
        self._construction = construction
        self._assessed: tuple[date, DataFinalityEvidence] | None = None

    def assess(self, session_date: date) -> DataFinalityEvidence:
        if self._assessed is not None and self._assessed[0] == session_date:
            return self._assessed[1]
        evidence = assess_data_finality(
            self._store, session_date, construction=self._construction,
            adjustment_verifier=_adjustment_verifier(self._store))
        self._assessed = (session_date, evidence)
        return evidence

    def verify_unchanged(self, session_date: date, expected: DataFinalityEvidence) -> None:
        verify_store_unchanged(self._store, session_date, expected,
                               construction=self._construction)


def _adjustment_verifier(store: Any):
    from app.validation.adjustment_verifier import verify_adjustments
    from app.validation.production_bindings import declare_action_source

    source = declare_action_source(store)

    def verifier(window_start: date, session_date: date, tickers: list[str], store_identity: str):
        return verify_adjustments(store, window_start=window_start, session_date=session_date,
                                  relevant_tickers=tickers, source=source,
                                  store_identity_sha256=store_identity)

    return verifier


def _open_store(config: ForwardDeploymentConfig) -> Any:
    from app.factor_data.store import FactorDataStore

    try:
        return FactorDataStore(db_path=str(config.factor_store_path), read_only=True)
    except Exception as exc:                      # noqa: BLE001 - an unopenable store is a refusal
        raise CompositionError(
            f"the governed factor store at {config.factor_store_path} could not be opened read-only: "
            f"{type(exc).__name__}: {exc}") from exc


def _session_calendar(store: Any, session: date) -> tuple[date, ...]:
    """The governed store's own trading calendar, ending at the session.

    Derived from the store rather than from a calendar package: these are the dates the decision's data
    actually exists for, and the exit-confirmation lookback is defined over exactly them.
    """
    start = date(session.year - CALENDAR_SPAN_YEARS, 1, 1)
    try:
        days = [d for d in store.trading_days(start, session) if d <= session]
    except Exception as exc:                      # noqa: BLE001
        raise CompositionError(
            f"the governed store could not produce its trading calendar: "
            f"{type(exc).__name__}: {exc}") from exc
    if not days or days[-1] != session:
        raise CompositionError(
            f"{session.isoformat()} is not a session in the governed store's calendar; the store has no "
            f"data for the session being run")
    return tuple(days)


def _build_proxy_closes(store: Any, config: ForwardDeploymentConfig, session_dates: tuple[date, ...],
                        construction: ConstructionSpec) -> tuple[dict[date, float], str]:
    """The registered market-proxy construction (`stage4.build_market_proxy`), warmed so the frozen
    regime request has a full MA on the session.

    Returns the closes keyed by session date and the identity of the construction that produced them.
    """
    import pandas as pd

    # Resolved by name, as `session_orchestration` resolves the frozen strategy module. `scripts/` is
    # outside the type-checked surface (the gate is `mypy app`) and holds the countersigned §8 census
    # replica — a frozen validated artifact that must not be edited to satisfy a checker. Importing it
    # by name keeps `app/` fully checked without suppressing anything, and re-implementing the proxy
    # inside `app/` is not an option: it would be a NEW construction, which the governing
    # preregistration forbids.
    build_market_proxy = importlib.import_module(
        "scripts.backtest_momentum_stage4").build_market_proxy

    try:
        proxy = build_market_proxy(store, list(session_dates), str(config.factor_store_path))
    except Exception as exc:                      # noqa: BLE001
        raise CompositionError(
            f"the registered market-proxy construction failed: {type(exc).__name__}: {exc}") from exc

    closes = {d: float(v) for d, v in proxy["idx"].items() if pd.notna(v)}
    session = session_dates[-1]
    required = construction.regime_ma_sessions + 1
    available = [d for d in sorted(closes) if d <= session]
    if len(available) < required:
        raise CompositionError(
            f"the market proxy has {len(available)} close(s) on or before {session.isoformat()}, fewer "
            f"than the {required} the frozen regime request reads; the regime cannot be formed and a "
            f"session that cannot form its regime must not be recorded")
    if pd.isna(proxy["ma"].get(session)):
        raise CompositionError(
            f"the market proxy has no {construction.regime_ma_sessions}-session moving average on "
            f"{session.isoformat()}; the regime would fail open to fully invested, which is a decision "
            f"the record must never attribute to the strategy")

    identity = (f"stage4.build_market_proxy|store={config.factor_store_path}"
                f"|sessions={len(session_dates)}|ma={construction.regime_ma_sessions}")
    return closes, identity


def _universe_fn(store: Any):
    from app.factor_data.universe import universe_asof

    def fn(as_of: date, n: int) -> list[str]:
        return list(universe_asof(store, as_of, n=n))

    return fn


def _accessor(store: Any) -> Any:
    from app.factor_data.accessor import FactorAccessor

    return FactorAccessor(store)


def _probe_fn(config: ForwardDeploymentConfig):
    def probe() -> Account4Probe:
        return probe_account4(config.app_db_path, strategy_id=config.strategy_id,
                              expected_broker=config.expected_broker,
                              expected_broker_mode=config.expected_broker_mode)

    return probe


def _context_builder(config: ForwardDeploymentConfig):
    def builder(session: date) -> ForwardRunContext:
        return build_forward_context(session, dgs3mo_path=config.dgs3mo_path,
                                     trial_ledger_path=config.trial_ledger_path,
                                     ledger_account_id=config.ledger_account_id)

    return builder


def resolve_witness(config: ForwardDeploymentConfig, *,
                    invocation_id: str | None = None) -> tuple[ProductionWitness, str]:
    """Enforce the deployment's witness for THIS invocation. The only production source of a witness.

    The nonce is generated here rather than accepted from a caller: a caller-chosen nonce is a
    caller-chosen challenge, and one reused across runs would let a recorded signature stand in for a
    live one. `invocation_id` exists so a test can pin it, and so the run and its evidence agree on the
    identifier — never so an operator can supply it.
    """
    nonce = invocation_id or new_invocation_identifier()
    return enforce_production_witness(config.witness, nonce=nonce), nonce


def build_session_runtime(config: ForwardDeploymentConfig, session: date, *,
                          invocation_id: str | None = None) -> ResolvedSession:
    """Resolve the governed configuration into a runnable `SessionRuntime`.

    Order is deliberate. Deployment identity and the witness are established BEFORE the store is opened
    and before any data work: a deployment that cannot identify itself, or whose signer is unreachable
    or whose sink cannot prove write-once, should refuse cheaply rather than after minutes of reads.
    """
    evidence: dict[str, Any] = {"config": config.to_open_provenance()}

    deployment = verify_deployment_identity(
        model=config.deployment_model, build_info_path=config.build_info_path,
        deployment_manifest_path=config.deployment_manifest_path,
        runtime_digest_path=config.runtime_digest_path,
        runtime_digest_env=config.runtime_digest_env, expected_commit=config.expected_commit)
    evidence["deployment_identity"] = deployment.to_open_provenance()

    witness, invocation = resolve_witness(config, invocation_id=invocation_id)
    evidence["invocation"] = invocation
    evidence["witness"] = witness.evidence

    construction = ConstructionSpec()
    store = _open_store(config)
    try:
        session_dates = _session_calendar(store, session)
        proxy_closes, regime_source_identity = _build_proxy_closes(
            store, config, session_dates, construction)

        readiness = _GovernedReadiness(store, config, construction)
        finality = readiness.assess(session)
        evidence["data_finality"] = finality.to_open_provenance()

        runtime = SessionRuntime(
            store=store, accessor=_accessor(store),
            store_identity=finality.store_identity_sha256,
            universe_fn=_universe_fn(store), proxy_closes=proxy_closes,
            session_dates=session_dates, strict_price_fn=strict_pit_price_fn(store),
            account4_probe=_probe_fn(config), context_builder=_context_builder(config),
            readiness=readiness, witness=witness)
    except Exception:
        store.close()
        raise

    run_kwargs = {
        "store_dir": config.observation_store_dir,
        "ledger_path": config.ledger_path,
        "book_path": config.observation_store_dir / "instrument_book.json",
        "strategy_id": config.strategy_id,
        "shadow_ledger_identity": config.shadow_ledger_identity,
        "instrument_durable_state_id": config.instrument_durable_state_id,
        "starting_capital": config.starting_capital,
        "turnover_cost_bps": config.turnover_cost_bps,
        "backstop_days": config.backstop_days,
        "weight_drift_pct": config.weight_drift_pct,
        "deployment_blob": _deployment_blob(),
        "run_timestamp": invocation,
        "deployed_tree_identity": deployment.agreed_commit,
        "regime_source_identity": regime_source_identity,
    }
    return ResolvedSession(runtime=runtime, store=store, run_kwargs=run_kwargs, evidence=evidence)


def _deployment_blob() -> dict[str, Any]:
    """The instrument's own NEVER_DEPLOYED lifecycle blob — the real production initial state."""
    from app.strategies.deployment_state import initial_blob

    return initial_blob().to_dict()


__all__ = [
    "CALENDAR_SPAN_YEARS",
    "CompositionError",
    "ResolvedSession",
    "build_session_runtime",
    "resolve_witness",
]
