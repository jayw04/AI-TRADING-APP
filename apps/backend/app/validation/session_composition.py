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
import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from app.validation.account4_probe import Account4Probe, probe_account4
from app.validation.data_finality import (
    ConstructionSpec,
    DataFinalityEvidence,
    DataReadiness,
    NarrowReadinessAttestation,
    assess_data_finality,
    load_narrow_readiness_attestation,
    verify_store_unchanged,
)
from app.validation.deployment_identity import verify_deployment_identity
from app.validation.forward_deployment_config import ForwardDeploymentConfig
from app.validation.forward_window import (
    DGS3MO_SNAPSHOT_SHA256,
    TRIAL_LEDGER_SHA256,
    ForwardRunContext,
    IntegrityStop,
)
from app.validation.governed_corpus import (
    GovernedConstruction,
    construction_identity,
    consumed_rows_identity,
    file_sha256,
    require_observation_identities,
    resolve_governed_construction,
)
from app.validation.governed_quarantine import GovernedQuarantinePolicy
from app.validation.measurement_freeze import load_measurement_freeze
from app.validation.production_bindings import (
    build_forward_context,
    governed_narrow_wiring,
    strict_pit_price_fn,
)
from app.validation.security_lineage import SessionLineageFilter
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
                 construction: ConstructionSpec, *, adjustment_verifier: Any,
                 narrow_readiness: NarrowReadinessAttestation | None = None) -> None:
        self._store = store
        self._config = config
        self._construction = construction
        # ⚠ Both are built at the composition root from the GOVERNED construction and handed in.
        # The verifier carries the manifest-bound source authority and the pinned non-decision M&A
        # disclosure; the attestation carries the governed quarantine. Building either here would put
        # a second derivation inside the gate that is supposed to be checking the first.
        self._verifier = adjustment_verifier
        self._narrow = narrow_readiness
        self._assessed: tuple[date, DataFinalityEvidence] | None = None

    def assess(self, session_date: date) -> DataFinalityEvidence:
        if self._assessed is not None and self._assessed[0] == session_date:
            return self._assessed[1]
        evidence = assess_data_finality(
            self._store, session_date, construction=self._construction,
            adjustment_verifier=self._verifier, narrow_readiness=self._narrow)
        self._assessed = (session_date, evidence)
        return evidence

    def verify_unchanged(self, session_date: date, expected: DataFinalityEvidence) -> None:
        verify_store_unchanged(self._store, session_date, expected,
                               construction=self._construction)


def _open_store(config: ForwardDeploymentConfig) -> Any:
    from app.factor_data.store import FactorDataStore

    try:
        return FactorDataStore(db_path=str(config.factor_store_path), read_only=True)
    except Exception as exc:                      # noqa: BLE001 - an unopenable store is a refusal
        raise CompositionError(
            f"the governed factor store at {config.factor_store_path} could not be opened read-only: "
            f"{type(exc).__name__}: {exc}") from exc


def _expected_delta_sessions(base_cutoff: date, session: date) -> tuple[date, ...]:
    """The governed trading sessions a delta chain must cover: strictly after the base cutoff,
    through the observed session.

    Sourced from the authoritative XNYS calendar, deliberately NOT from the store's own calendar
    (`_session_calendar`). A missing delta means the store lacks that session, so a store-derived
    calendar would not list it and the gap would validate clean against itself. The check only means
    something when the expectation comes from outside the artifact being checked.
    """
    from app.validation.eval_calendar import is_trading_session

    out: list[date] = []
    day = base_cutoff + timedelta(days=1)
    while day <= session:
        if is_trading_session(day):
            out.append(day)
        day += timedelta(days=1)
    return tuple(out)


def _deployment_corpus_block(config: ForwardDeploymentConfig) -> Any:
    """The `corpus` identity block the deploy step recorded. Re-read from the manifest rather than
    passed along, so it is the same file `verify_deployment_identity` just authenticated."""
    try:
        payload = json.loads(Path(config.deployment_manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CompositionError(
            f"the deployment manifest at {config.deployment_manifest_path} became unreadable while "
            f"resolving the governed construction: {exc}") from exc
    return payload.get("corpus") if isinstance(payload, dict) else None


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


def _universe_fn(store: Any, *, session: date, construction: ConstructionSpec):
    """The registered universe construction, filtered to lineage-eligible securities.

    The filter is applied HERE, at the single callable every downstream consumer draws from, so that
    ranking, score computation, target sizing and tie-breaking cannot see a candidate whose lookback
    crosses a permanent-lineage boundary. `universe_asof` itself is deliberately left untouched: it is
    shared with the frozen replica and with historical conformance evidence, and changing it would
    invalidate both.
    """
    from app.factor_data.universe import universe_asof

    window = store.con.execute(
        "SELECT DISTINCT date FROM sep WHERE date <= ? ORDER BY date DESC LIMIT ?",
        [session, construction.required_history_sessions]).fetchall()
    if not window:
        raise CompositionError(
            f"the governed store holds no sessions on or before {session.isoformat()}; the lineage "
            f"lookback cannot be established")
    lineage = SessionLineageFilter(store, session_date=session, lookback_start=window[-1][0])

    def fn(as_of: date, n: int) -> list[str]:
        return lineage.filter(list(universe_asof(store, as_of, n=n)))

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


def _context_builder(config: ForwardDeploymentConfig, *, deployed_commit: str, freeze: Any,
                     runtime_root: Path, ancestry_marker: Path | None):
    """⚠ `deployed_commit` is the EVIDENCE-DERIVED identity from `verify_deployment_identity`, not a
    caller assertion and never a default. The freeze supplies what the deployment is EXPECTED to be;
    these supply what it IS. The gate compares them."""
    def builder(session: date) -> ForwardRunContext:
        return build_forward_context(session, dgs3mo_path=config.dgs3mo_path,
                                     trial_ledger_path=config.trial_ledger_path,
                                     ledger_account_id=config.ledger_account_id,
                                     code_commit=deployed_commit, measurement_freeze=freeze,
                                     runtime_root=runtime_root, ancestry_marker=ancestry_marker)

    return builder


def _resolve_governed_construction(config: ForwardDeploymentConfig,
                                   session: date) -> GovernedConstruction:
    """Validate the governed construction for this session, fail-closed (ADR 0048)."""
    corpus_block = _deployment_corpus_block(config)
    return resolve_governed_construction(
        corpus_manifest_path=config.corpus_manifest_path,
        dgs3mo_manifest_path=config.dgs3mo_manifest_path,
        dgs3mo_path=config.dgs3mo_path,
        trial_ledger_path=config.trial_ledger_path,
        frozen_dgs3mo_sha256=DGS3MO_SNAPSHOT_SHA256,
        frozen_trial_ledger_sha256=TRIAL_LEDGER_SHA256,
        deployment_manifest_corpus_block=corpus_block,
        observation_session=session,
        expected_sessions=_expected_sessions_for(config, session),
        countersignature_path=config.corpus_countersignature_path,
    )


def _expected_sessions_for(config: ForwardDeploymentConfig, session: date) -> tuple[date, ...]:
    """The delta sessions a BASE-PLUS-DELTA construction must carry, or `()` for a reconstruction.

    ⚠ A Layer 2 reconstruction has no delta chain at all, so there is no expected session list to
    build and no base cutoff to read. Returning `()` states that; synthesizing a cutoff from its
    governed coverage in order to produce a list would invent a chain the construction does not have.
    """
    if _declared_construction_kind(config):
        return ()
    return _expected_delta_sessions(_declared_base_cutoff(config), session)


def _declared_construction_kind(config: ForwardDeploymentConfig) -> str:
    """The `kind` the corpus manifest declares, or `""` for the base-plus-delta construction, which
    predates the marker and carries none."""
    try:
        payload = json.loads(Path(config.corpus_manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CompositionError(
            f"the corpus manifest at {config.corpus_manifest_path} is unreadable: {exc}") from exc
    return str(payload.get("kind", "")).strip() if isinstance(payload, dict) else ""


def _declared_base_cutoff(config: ForwardDeploymentConfig) -> date:
    """The base cutoff a BASE-PLUS-DELTA corpus manifest declares — read before validation only to
    size the expected session list. It is not trusted: `resolve_governed_construction` re-reads the
    manifest and refuses unless every identity agrees with the deployment manifest, so a manipulated
    cutoff here produces a session list that the chain then fails to match."""
    try:
        payload = json.loads(Path(config.corpus_manifest_path).read_text(encoding="utf-8"))
        return date.fromisoformat(str(payload["base_coverage_through"]))
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise CompositionError(
            f"the corpus manifest at {config.corpus_manifest_path} declares no readable "
            f"base_coverage_through: {exc}") from exc


def resolve_witness(config: ForwardDeploymentConfig, *,
                    invocation_id: str | None = None) -> tuple[ProductionWitness, str]:
    """Enforce the deployment's witness for THIS invocation. The only production source of a witness.

    The nonce is generated here rather than accepted from a caller: a caller-chosen nonce is a
    caller-chosen challenge, and one reused across runs would let a recorded signature stand in for a
    live one. `invocation_id` exists so a test can pin it, and so the run and its evidence agree on the
    identifier — never so an operator can supply it.

    The platform boundary (ADR 0047 §7) is enforced inside `enforce_production_witness`, not here: it
    belongs to every production witness rather than to this one caller, and siting it in the gate means
    the readiness CLI and the Step 4D preflight inherit it too.
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

    # The EXPECTED measurement identity, from the governed manifest outside the tree it pins.
    #
    # ⚠ Loaded AFTER the witness and BEFORE any data work. The ordering is load-bearing in both
    # directions: a non-production witness must refuse before anything else runs (a REFERENCE-profile
    # deployment must never reach the store), and a deployment that is not the ratified measurement
    # instrument must refuse before minutes of reads rather than after them.
    measurement_freeze = load_measurement_freeze(config.measurement_freeze_path)
    evidence["measurement_freeze"] = measurement_freeze.to_open_provenance()

    # ADR 0048: establish WHICH governed construction this session is authorized to consume, before
    # the store is opened. A chain with a hole, a repeat, a reordering or a drifted frozen artifact
    # must refuse here rather than after the reads — and the refusal must not depend on the very store
    # whose construction is in question.
    governed = _resolve_governed_construction(config, session)
    evidence["governed_construction"] = governed.to_open_provenance()

    construction = ConstructionSpec()
    store = _open_store(config)
    try:
        session_dates = _session_calendar(store, session)

        # Data finality is assessed BEFORE the market proxy is constructed, and the order is
        # load-bearing rather than stylistic. `build_market_proxy` is a frozen artifact that builds
        # its own basket by calling `universe_asof` directly, so it cannot be filtered; the one
        # finding that says its input could fabricate a return — the lineage bridge risk — therefore
        # has to land before it runs. Refusing afterwards would mean the fabricated return had
        # already been computed and averaged into the regime.
        # ADR 0048 / owner ruling 2026-07-31: the governed quarantine and the non-decision M&A
        # disclosure are derived HERE, from the countersigned construction, and the narrow-readiness
        # attestation is loaded UNDER that quarantine. Until now none of this reached the session
        # path: `governed_quarantine` was a countersigned block with no consumer in `app/`, so a
        # deployment could pass Phase C readiness and then be unable to run the very session that
        # readiness had just cleared.
        wiring = governed_narrow_wiring(
            store, governed.normalized, governed.countersignature,
            governed_root=Path(config.corpus_manifest_path).parent)
        evidence["governed_narrow_wiring"] = wiring.to_open_provenance()
        narrow = _narrow_attestation(config, wiring.quarantine)
        if narrow is not None:
            evidence["narrow_readiness_attestation"] = {
                "path": str(config.narrow_readiness_attestation_path),
                "attested_session": narrow[0].session_date.isoformat(),
                "attestation_sha256": narrow[1],
            }

        readiness = _GovernedReadiness(
            store, config, construction,
            adjustment_verifier=wiring.adjustment_verifier,
            narrow_readiness=narrow[0] if narrow else None)
        finality = readiness.assess(session)
        evidence["data_finality"] = finality.to_open_provenance()
        if finality.verdict is DataReadiness.NOT_READY_LINEAGE_BRIDGE_RISK:
            raise CompositionError(finality.detail)

        proxy_closes, regime_source_identity = _build_proxy_closes(
            store, config, session_dates, construction)

        # Both identities, from their own sources, in every observation. Independence is structural:
        # the construction identity is RECOMPUTED from the governed manifest, and the value-level one
        # is taken off the finality evidence that computed it — `data_finality` is not recomputed,
        # retimed, or otherwise touched here.
        construction_id = construction_identity(governed.corpus)
        consumed_id = consumed_rows_identity(finality)
        evidence["identities"] = require_observation_identities(
            {"corpus_manifest_sha256": construction_id.value,
             "store_identity_sha256": consumed_id.value},
            construction=construction_id, consumed=consumed_id)

        runtime = SessionRuntime(
            store=store, accessor=_accessor(store),
            store_identity=finality.store_identity_sha256,
            universe_fn=_universe_fn(store, session=session, construction=construction),
            proxy_closes=proxy_closes,
            session_dates=session_dates, strict_price_fn=strict_pit_price_fn(store),
            account4_probe=_probe_fn(config),
            context_builder=_context_builder(
                config, deployed_commit=deployment.agreed_commit, freeze=measurement_freeze,
                runtime_root=config.runtime_root, ancestry_marker=config.ancestry_marker_path),
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


def _narrow_attestation(config: ForwardDeploymentConfig, quarantine: GovernedQuarantinePolicy,
                        ) -> tuple[NarrowReadinessAttestation, str] | None:
    """Load the deployment's narrow-readiness attestation, bound to the DERIVED quarantine.

    `None` when the deployment declares none — a construction whose corporate actions are all proven
    needs no narrow claim, and inventing one for it would be worse than not having it. When the
    deployment DOES declare one, an unreadable or non-binding artifact is a refusal rather than a
    silent fall back to the broad gate: the difference between "no narrow claim" and "the narrow claim
    could not be checked" is exactly the difference this fails closed on.
    """
    path = config.narrow_readiness_attestation_path
    if path is None:
        return None
    attestation, _record = load_narrow_readiness_attestation(Path(path), quarantine=quarantine)
    return attestation, file_sha256(Path(path))


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
