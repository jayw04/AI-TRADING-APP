#!/usr/bin/env python3
"""Forward-validation session CLI — readiness and the governed run (R5c-2b1, run-session added R5e-2).

The production entry point, with two modes:

    readiness     every data, artifact, deployment, binding and Account-4 check — and nothing else.
                  It does NOT construct the instrument, does NOT take a snapshot, does NOT evaluate,
                  book or commit. Nothing it does can change durable strategy state.

    run-session   (R5e-2) resolve the governed configuration into a runnable session and run it: one
                  evaluation of the real frozen instrument, booked into the shadow ledger, committed to
                  the observation store and anchored across the enforced witness boundary. At most ONE
                  observation per session; a session already recorded is a no-op.

Both modes build everything themselves from the governed deployment configuration. The only
invocation-time inputs are the mode and the session date — no path, identity or registered parameter can
be supplied on the command line, because evidence an operator can point at is not evidence.

`run-session` is the ONLY externally exposed way to record an observation, and it reaches the runner
exclusively through `session_composition.build_session_runtime`, which resolves the witness through
`enforce_production_witness` and nothing else.

    python scripts/run_forward_validation_session.py readiness   [--session-date YYYY-MM-DD]
    python scripts/run_forward_validation_session.py run-session [--session-date YYYY-MM-DD]

Exit codes:
    0  READY / NOT_ELIGIBLE / RECORDED / ALREADY_RECORDED   — nothing for the operator to do
    1  NOT_READY / INTEGRITY_STOP                           — a governed refusal, with its evidence
    2  configuration refusal or an unexpected error
    3  the observation COMMITTED but a post-commit durable write did not — never retry as an ordinary
       failure: the record advanced, and the next run stops for governed recovery
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.validation.account4_probe import Account4Probe, probe_account4  # noqa: E402
from app.validation.data_finality import (  # noqa: E402
    DataFinalityEvidence,
    assess_data_finality,
    verify_store_unchanged,
)
from app.validation.deployment_identity import verify_deployment_identity  # noqa: E402
from app.validation.eval_calendar import is_eligible_session  # noqa: E402
from app.validation.forward_deployment_config import (  # noqa: E402
    ForwardDeploymentConfig,
    load_deployment_config,
)
from app.validation.forward_window import GOVERNING_TZ, IntegrityStop  # noqa: E402
from app.validation.production_bindings import (  # noqa: E402
    build_forward_context,
    declare_action_source,
)
from app.validation.witness_enforcement import enforce_production_witness  # noqa: E402


class _StoreScoresProvider:
    """The registered scoring construction, presenting an explicit identity.

    `forward_identity()` binds what the provider actually reads — the governed store and the frozen
    construction parameters — rather than its class name, so two providers over different stores can
    never share an identity (R5c-2a).
    """

    def __init__(self, store: Any, store_identity: str, universe_n: int, lookback: int, skip: int):
        self._store = store
        self._store_identity = store_identity
        self._universe_n = universe_n
        self._lookback = lookback
        self._skip = skip

    def forward_identity(self) -> str:
        return (f"stage2.compute_day|store={self._store_identity}|n={self._universe_n}"
                f"|lookback={self._lookback}|skip={self._skip}")

    def __call__(self, session: date):                      # pragma: no cover - R5d wiring
        raise NotImplementedError(
            "the data-coupled scores provider is wired in the deployment increment; readiness only "
            "verifies its identity")


class _StoreBarsProvider:
    """The registered regime/bars construction, presenting an explicit identity."""

    def __init__(self, store: Any, store_identity: str, proxy_n: int, ma_sessions: int):
        self._store = store
        self._store_identity = store_identity
        self._proxy_n = proxy_n
        self._ma_sessions = ma_sessions

    def forward_identity(self) -> str:
        return (f"stage4.build_market_proxy|store={self._store_identity}|proxy_n={self._proxy_n}"
                f"|ma={self._ma_sessions}")

    def __call__(self, symbol: str, as_of: date, n: int):   # pragma: no cover - R5d wiring
        raise NotImplementedError(
            "the data-coupled bars provider is wired in the deployment increment; readiness only "
            "verifies its identity")


@dataclass
class _ReadinessReport:
    session_date: str
    verdict: str
    detail: str
    evidence: dict[str, Any]

    def emit(self) -> int:
        print(json.dumps({"mode": "readiness", "session_date": self.session_date,
                          "verdict": self.verdict, "detail": self.detail,
                          "evidence": self.evidence}, indent=2, default=str))
        return 0 if self.verdict == "READY" else 1


def _governing_today() -> date:
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo(GOVERNING_TZ)).date()


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _open_store(config: ForwardDeploymentConfig):
    from app.factor_data.store import FactorDataStore

    return FactorDataStore(db_path=str(config.factor_store_path), read_only=True)


def _adjustment_verifier(store: Any, config: ForwardDeploymentConfig):
    from app.validation.adjustment_verifier import verify_adjustments

    source = declare_action_source(store)

    def verifier(window_start: date, session_date: date, tickers: list[str],
                 store_identity: str):
        # The identity is the one the finality assessment computed, so the adjustment verdict and the
        # surrounding readiness evidence are bound to the same identified store.
        return verify_adjustments(store, window_start=window_start, session_date=session_date,
                                  relevant_tickers=tickers, source=source,
                                  store_identity_sha256=store_identity)

    return verifier


def _probe(config: ForwardDeploymentConfig) -> Account4Probe:
    return probe_account4(config.app_db_path, strategy_id=config.strategy_id,
                          expected_broker=config.expected_broker,
                          expected_broker_mode=config.expected_broker_mode)


def run_readiness(config: ForwardDeploymentConfig, session: date) -> _ReadinessReport:
    """Every check the run performs, and NOTHING that can change durable strategy state.

    The instrument is never constructed, no snapshot is taken, `on_bar` is never called, nothing is
    booked and nothing is committed. Provider identities are verified from constructed provider objects,
    which read no data by themselves.
    """
    iso = session.isoformat()
    evidence: dict[str, Any] = {"config": config.to_open_provenance()}

    deployment = verify_deployment_identity(
        model=config.deployment_model, build_info_path=config.build_info_path,
        deployment_manifest_path=config.deployment_manifest_path,
        runtime_digest_path=config.runtime_digest_path,
        runtime_digest_env=config.runtime_digest_env, expected_commit=config.expected_commit)
    evidence["deployment_identity"] = deployment.to_open_provenance()

    if not is_eligible_session(session):
        return _ReadinessReport(iso, "NOT_ELIGIBLE",
                                "not an XNYS session on/after the frozen forward start", evidence)

    # The anchor trust boundary (R5e). Enforced HERE, in readiness, because a deployment whose signer is
    # unreachable or whose sink cannot prove write-once should learn it before a session is due — not at
    # the first commit. The gate resolves the deployment's own signer and sink, challenges the signer
    # against the deployment-installed verifying key, and refuses the reference implementations. It
    # writes nothing: the challenge signs a probe tip outside the committed numbering.
    witness = enforce_production_witness(config.witness, nonce=_now_iso())
    evidence["witness"] = witness.evidence

    store = _open_store(config)
    try:
        source = declare_action_source(store)
        evidence["action_source"] = {
            "identity": source.identity, "authoritative": source.authoritative,
            "coverage_start": str(source.coverage_start), "coverage_end": str(source.coverage_end)}

        finality = assess_data_finality(
            store, session, adjustment_verifier=_adjustment_verifier(store, config))
        evidence["data_finality"] = finality.to_open_provenance()

        scores = _StoreScoresProvider(store, finality.store_identity_sha256, 200, 252, 21)
        bars = _StoreBarsProvider(store, finality.store_identity_sha256, 500, 200)
        from app.validation.decision_provider import provider_identity

        evidence["provider_identities"] = {
            "scores": provider_identity(scores), "bars": provider_identity(bars)}

        ctx = build_forward_context(session, dgs3mo_path=config.dgs3mo_path,
                                    trial_ledger_path=config.trial_ledger_path,
                                    ledger_account_id=config.ledger_account_id)
        evidence["context_session"] = ctx.session_date.isoformat()

        probe = _probe(config)
        evidence["account4"] = probe.to_open_provenance()

        if not finality.ready:
            return _ReadinessReport(iso, str(finality.verdict), finality.detail, evidence)
        return _ReadinessReport(iso, "READY",
                                "every data, artifact, deployment, binding and Account-4 check passed; "
                                "no session was evaluated", evidence)
    finally:
        store.close()


# The post-commit-durability statuses. The observation COMMITTED; a durable write after it did not. A
# scheduler must never retry these as ordinary failures — the record has advanced, and the next run
# stops for governed recovery rather than repairing anything.
_POST_COMMIT_INCOMPLETE = frozenset({
    "RECORDED_BUT_BOOK_UNPERSISTED",
    "RECORDED_BUT_ANCHOR_UNWRITTEN",
    "RECORDED_BUT_ANCHOR_AND_BOOK_UNPERSISTED",
})


def run_session(config: ForwardDeploymentConfig, session: date) -> tuple[dict[str, Any], int]:
    """Resolve the governed configuration into a runnable session, run it, and report.

    The composition root owns every dependency; this function owns only the reporting and the exit
    code. It deliberately does NOT pre-screen eligibility or readiness — the runner performs both as
    part of the governed sequence, and duplicating them here would create a second place where a
    session can be judged runnable.
    """
    from app.validation.session_composition import build_session_runtime
    from app.validation.session_orchestration import run_production_session

    resolved = build_session_runtime(config, session)
    try:
        result = run_production_session(resolved.runtime, session, **resolved.run_kwargs)
    finally:
        resolved.close()

    status = str(result.status)
    report = {
        "mode": "run-session", "session_date": result.session_date, "status": status,
        "session_count": result.session_count, "sequence": result.sequence,
        "exception_code": result.exception_code, "detail": result.detail,
        "operational_exceptions": list(result.operational_exceptions),
        "invocation": resolved.evidence.get("invocation"),
        "evidence": resolved.evidence,
    }
    if status in _POST_COMMIT_INCOMPLETE:
        return report, 3
    return report, (1 if status == "INTEGRITY_STOP" else 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("mode", choices=["readiness", "run-session"])
    parser.add_argument("--session-date", type=date.fromisoformat, default=None,
                        help=f"session to assess (default: today in {GOVERNING_TZ})")
    args = parser.parse_args(argv)

    session = args.session_date or _governing_today()
    try:
        config = load_deployment_config()
    except IntegrityStop as exc:
        print(json.dumps({"mode": args.mode, "status": "REFUSED", "detail": str(exc)}, indent=2))
        return 2

    try:
        if args.mode == "run-session":
            report, code = run_session(config, session)
            print(json.dumps(report, indent=2, default=str))
            return code
        return run_readiness(config, session).emit()
    except IntegrityStop as exc:
        # Governed refusals carry a code (the witness gate's codes name which property failed); older
        # stops carry only a message. Report whichever is present rather than inventing one.
        stop = {"mode": args.mode, "session_date": session.isoformat(),
                "status": "INTEGRITY_STOP", "detail": str(exc)}
        code = getattr(exc, "code", None)
        if code:
            stop["code"] = str(code)
        print(json.dumps(stop, indent=2))
        return 1
    except Exception as exc:                      # noqa: BLE001 - the entry point reports, never hides
        print(json.dumps({"mode": args.mode, "session_date": session.isoformat(), "status": "ERROR",
                          "detail": f"{type(exc).__name__}: {exc}"}, indent=2))
        return 2


__all__ = ["DataFinalityEvidence", "main", "run_readiness", "run_session",
           "verify_store_unchanged"]

if __name__ == "__main__":
    raise SystemExit(main())
