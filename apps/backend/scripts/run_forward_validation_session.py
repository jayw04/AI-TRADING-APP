#!/usr/bin/env python3
"""Forward-validation CLI (R5c-2b) — readiness, or one governed session.

The production entry point. It builds the entire runner ITSELF from the governed deployment
configuration; the only invocation-time inputs are the mode, the session date and the authorization
token. No path, identity or registered parameter can be supplied on the command line, because evidence
an operator can point at is not evidence.

    readiness     every data, artifact, deployment, binding and Account-4 check — and nothing else.
                  It does NOT construct the instrument, does NOT take a snapshot, does NOT evaluate,
                  book or commit. Nothing it does can change durable strategy state.

    run-session   requires explicit authorization. Runs every readiness check, then takes exactly ONE
                  instrument snapshot and hands its digest to the provider, the evaluator and the
                  runner alike, evaluates the real instrument, books at the registered turnover cost,
                  and commits one observation — stopping at the first red prerequisite.

Being runnable does not open the forward window: a session still requires the data gate to be READY
(which needs the authoritative ACTIONS ingest), Account 4 safely paused and held, an identified
deployment, and the operator's authorization for that specific session.

    python scripts/run_forward_validation_session.py readiness [--session-date YYYY-MM-DD]
    python scripts/run_forward_validation_session.py run-session --authorize <token> [--session-date …]

Exit codes:
    0  READY / RECORDED / ALREADY_RECORDED / NOT_ELIGIBLE   — nothing for the operator to do
    1  NOT_READY / INTEGRITY_STOP                            — a governed refusal, evidence recorded
    2  configuration refusal or an unexpected error          — the run never reached the record
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

AUTHORIZATION_ENV = "FORWARD_VALIDATION_AUTHORIZATION"


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


def _adjustment_verifier(store: Any, config: ForwardDeploymentConfig, store_identity: str):
    from app.validation.adjustment_verifier import verify_adjustments

    source = declare_action_source(store)

    def verifier(window_start: date, session_date: date, tickers: list[str]):
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

    store = _open_store(config)
    try:
        source = declare_action_source(store)
        evidence["action_source"] = {
            "identity": source.identity, "authoritative": source.authoritative,
            "coverage_start": str(source.coverage_start), "coverage_end": str(source.coverage_end)}

        finality = assess_data_finality(store, session,
                                        adjustment_verifier=_adjustment_verifier(store, config, ""))
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


def run_session(config: ForwardDeploymentConfig, session: date, *, authorization: str) -> int:
    """One governed session. Requires explicit authorization and fails closed on every red prerequisite.

    The data-coupled providers land in the deployment increment (R5d); until they do, this refuses
    rather than evaluating the instrument against a provider that cannot read.
    """
    readiness = run_readiness(config, session)
    if readiness.verdict != "READY":
        readiness.emit()
        return 1
    print(json.dumps({
        "mode": "run-session", "session_date": session.isoformat(), "status": "REFUSED",
        "detail": "readiness passes, but the data-coupled scores/bars providers are not yet wired "
                  "(R5d). A session is never evaluated against providers that cannot read.",
        "authorization_present": bool(authorization),
    }, indent=2))
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("mode", choices=["readiness", "run-session"])
    parser.add_argument("--session-date", type=date.fromisoformat, default=None,
                        help=f"session to assess (default: today in {GOVERNING_TZ})")
    parser.add_argument("--authorize", default="",
                        help="explicit authorization for run-session (or set "
                             f"{AUTHORIZATION_ENV})")
    args = parser.parse_args(argv)

    session = args.session_date or _governing_today()
    try:
        config = load_deployment_config()
    except IntegrityStop as exc:
        print(json.dumps({"mode": args.mode, "status": "REFUSED", "detail": str(exc)}, indent=2))
        return 2

    try:
        if args.mode == "readiness":
            return run_readiness(config, session).emit()

        import os

        authorization = args.authorize or os.environ.get(AUTHORIZATION_ENV, "")
        if not authorization.strip():
            print(json.dumps({
                "mode": "run-session", "status": "REFUSED",
                "detail": "run-session requires explicit authorization; readiness needs none",
            }, indent=2))
            return 2
        return run_session(config, session, authorization=authorization)
    except IntegrityStop as exc:
        print(json.dumps({"mode": args.mode, "session_date": session.isoformat(),
                          "status": "INTEGRITY_STOP", "detail": str(exc)}, indent=2))
        return 1
    except Exception as exc:                      # noqa: BLE001 - the entry point reports, never hides
        print(json.dumps({"mode": args.mode, "session_date": session.isoformat(), "status": "ERROR",
                          "detail": f"{type(exc).__name__}: {exc}"}, indent=2))
        return 2


__all__ = ["DataFinalityEvidence", "main", "run_readiness", "run_session", "verify_store_unchanged"]

if __name__ == "__main__":
    raise SystemExit(main())
