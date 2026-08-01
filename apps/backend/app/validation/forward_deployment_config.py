"""Governed forward-validation deployment configuration (R5c-2b).

Every path, identity and registered parameter the production runner uses comes from ONE configuration
file that the deployment owns — never from invocation-time arguments. An operator who could pass
`--build-info-path` or `--app-db` on the command line could point the verifiers at hand-made evidence,
and the record would faithfully attest to it.

The configuration is therefore located by the deployment, not by the caller: `FORWARD_VALIDATION_CONFIG`
(set by the deploy unit) or the fixed governed path. The CLI accepts only the mode and the session date.

Nothing here reads market data, touches Account 4, or constructs the instrument; it resolves and
validates a description of the deployment, and fails closed when that description is incomplete.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.validation.deployment_identity import DeploymentModel
from app.validation.forward_window import ACCOUNT_4_ID, IntegrityStop
from app.validation.witness_config import WitnessConfig, load_witness_config

CONFIG_ENV = "FORWARD_VALIDATION_CONFIG"
DEFAULT_CONFIG_PATH = Path("/etc/workbench/forward_validation.json")

_REQUIRED_KEYS = (
    "factor_store_path", "app_db_path", "observation_store_dir", "ledger_path",
    "dgs3mo_path", "trial_ledger_path", "build_info_path", "deployment_manifest_path",
    # ADR 0048: a deployment that cannot name its governed construction — the immutable base and the
    # ordered deltas it assembled — cannot record which data a session was authorized to consume.
    # Required here rather than defaulted, for the same reason the witness block is.
    "corpus_manifest_path", "dgs3mo_manifest_path",
    "deployment_model", "ledger_account_id", "strategy_id", "expected_broker",
    "expected_broker_mode", "shadow_ledger_identity", "instrument_durable_state_id",
    "starting_capital", "turnover_cost_bps", "backstop_days", "weight_drift_pct",
    # R5e: the anchor trust boundary is part of what the deployment IS. A deployment that cannot
    # independently witness its chain tips cannot run a governed session, so the block is required
    # here rather than defaulted to the reference implementations at the call site.
    "witness",
)


class DeploymentConfigError(IntegrityStop):
    """The deployment did not describe itself completely enough to run a governed session."""


#: `apps/backend` — the root that contains the measured paths in a source checkout.
DEFAULT_RUNTIME_ROOT = Path(__file__).resolve().parents[2]
#: The in-repo governed freeze manifest, resolved from this module rather than the working directory.
DEFAULT_MEASUREMENT_FREEZE_PATH = (
    DEFAULT_RUNTIME_ROOT.parents[1] / "manifests" / "forward" / "measurement_freeze.json")


@dataclass(frozen=True)
class ForwardDeploymentConfig:
    """What the deployment says it is. Paths are resolved but NOT opened here."""
    factor_store_path: Path
    app_db_path: Path
    observation_store_dir: Path
    ledger_path: Path
    dgs3mo_path: Path
    trial_ledger_path: Path
    build_info_path: Path
    deployment_manifest_path: Path
    corpus_manifest_path: Path
    dgs3mo_manifest_path: Path
    deployment_model: DeploymentModel
    ledger_account_id: int
    strategy_id: int
    expected_broker: str
    expected_broker_mode: str
    shadow_ledger_identity: str
    instrument_durable_state_id: str
    starting_capital: float
    turnover_cost_bps: float
    backstop_days: int
    weight_drift_pct: float
    witness: WitnessConfig                 # the anchor trust boundary this deployment witnesses across
    #: The governed measurement freeze — the EXPECTED measurement identity, held outside the tree it
    #: pins so it cannot be a fixed point.
    #:
    #: ⚠ Resolved from THIS module's location, not from the working directory. A CWD-relative default
    #: silently resolves to a different file (or none) depending on where the process was started,
    #: which for a governed binding is the difference between checking and not checking.
    measurement_freeze_path: Path = DEFAULT_MEASUREMENT_FREEZE_PATH
    #: The root that CONTAINS the measured paths, whose executable content is digested and compared
    #: against the freeze. On the box this is the extracted runtime; in a checkout, `apps/backend`.
    runtime_root: Path = DEFAULT_RUNTIME_ROOT
    #: Deploy-time ancestry attestation, for runtimes with no git repository to ask.
    ancestry_marker_path: Path | None = None
    #: The external countersignature sidecar for a Layer 2 reconstruction.
    #:
    #: ⚠ Optional in the CONFIG, mandatory at COMPOSITION for a Layer 2 construction. It is not in
    #: `_REQUIRED_KEYS` because a base-plus-delta deployment legitimately has none — its approval
    #: travels with each delta's own countersignature reference. Absence is therefore diagnosed where
    #: the construction kind is actually known, by `resolve_governed_construction`, rather than
    #: refusing every deployment for lacking a file only one kind needs.
    corpus_countersignature_path: Path | None = None
    #: The narrow-readiness attestation the Phase C runner produced for this construction.
    #:
    #: ⚠ Optional in the CONFIG for the same reason the sidecar is: a construction whose corporate
    #: actions are all proven reaches `READY` on the broad claim and needs no narrow attestation. When
    #: a deployment DOES declare one it is mandatory at composition — an unreadable artifact, or one
    #: written under a different governed quarantine, is a refusal and never a silent fall back to the
    #: broad gate.
    narrow_readiness_attestation_path: Path | None = None
    #: The owner-approved expected outcome for ONE first-session commit (Amendment 6), or None for
    #: ordinary unpinned operation. Parsed fail-closed at load: a declared pin with a missing or
    #: malformed digest refuses the whole configuration rather than degrading into an unpinned run.
    #:
    #: ⚠ THE CONFIGURATION FILE IS THE ONLY SOURCE. No environment fallback, no CLI argument, no
    #: default — expectations that can arrive through an ungoverned channel are suggestions.
    first_session_outcome_pin: Any | None = None
    runtime_digest_path: Path | None = None
    runtime_digest_env: str | None = None
    expected_commit: str | None = None
    source_path: Path | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_open_provenance(self) -> dict[str, Any]:
        d = {k: (str(v) if isinstance(v, Path) else v) for k, v in asdict(self).items()
             if k not in {"raw"}}
        d["deployment_model"] = str(self.deployment_model)
        # The witness block presents itself: `asdict` would flatten it into Paths and enums, and the
        # component options are summarised by key rather than copied into operator-visible evidence.
        d["witness"] = self.witness.to_open_provenance()
        return d


def _parse_outcome_pin(payload: Any) -> Any | None:
    """Parse the optional first-session outcome pin, fail-closed (Amendment 6).

    `None` when the configuration declares none — ordinary unpinned operation. A DECLARED pin that
    cannot be parsed refuses the whole configuration: silently dropping it would convert "commit only
    the reviewed outcome" into an ordinary commit, which is the exact degradation the pin forbids.
    """
    if payload is None:
        return None
    from app.validation.forward_session_runner import FirstSessionOutcomePin

    try:
        return FirstSessionOutcomePin.from_payload(payload)
    except IntegrityStop as exc:
        raise DeploymentConfigError(
            f"the declared first_session_outcome_pin is unusable and the configuration is refused "
            f"rather than run unpinned: {exc}") from exc


def config_path() -> Path:
    """Where the DEPLOYMENT says its configuration lives. Not a caller argument."""
    override = os.environ.get(CONFIG_ENV, "").strip()
    return Path(override) if override else DEFAULT_CONFIG_PATH


def load_deployment_config(path: Path | None = None) -> ForwardDeploymentConfig:
    """Load and validate the governed configuration. `path` exists for tests; production resolves it
    from the deployment via `config_path()`."""
    resolved = Path(path) if path is not None else config_path()
    if not resolved.is_file():
        raise DeploymentConfigError(
            f"no governed forward-validation configuration at {resolved}; the deployment must provide "
            f"one (set {CONFIG_ENV} or install {DEFAULT_CONFIG_PATH})")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentConfigError(f"the configuration at {resolved} is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise DeploymentConfigError(f"the configuration at {resolved} is not an object")

    missing = [k for k in _REQUIRED_KEYS if payload.get(k) in (None, "")]
    if missing:
        raise DeploymentConfigError(
            f"the configuration at {resolved} is incomplete; missing {sorted(missing)}")

    try:
        model = DeploymentModel(str(payload["deployment_model"]))
    except ValueError as exc:
        raise DeploymentConfigError(
            f"unknown deployment_model {payload['deployment_model']!r}") from exc

    ledger_account_id = int(payload["ledger_account_id"])
    if ledger_account_id == ACCOUNT_4_ID:
        raise DeploymentConfigError(
            f"the configuration names Account {ACCOUNT_4_ID} as the validation ledger; the forward "
            f"validation never runs on the live book")
    if model is DeploymentModel.CONTAINER and not (
            payload.get("runtime_digest_path") or payload.get("runtime_digest_env")):
        raise DeploymentConfigError(
            "a CONTAINER deployment must configure runtime_digest_path or runtime_digest_env so the "
            "running artifact can be identified")

    return ForwardDeploymentConfig(
        factor_store_path=Path(payload["factor_store_path"]),
        app_db_path=Path(payload["app_db_path"]),
        observation_store_dir=Path(payload["observation_store_dir"]),
        ledger_path=Path(payload["ledger_path"]),
        dgs3mo_path=Path(payload["dgs3mo_path"]),
        trial_ledger_path=Path(payload["trial_ledger_path"]),
        build_info_path=Path(payload["build_info_path"]),
        deployment_manifest_path=Path(payload["deployment_manifest_path"]),
        corpus_manifest_path=Path(payload["corpus_manifest_path"]),
        dgs3mo_manifest_path=Path(payload["dgs3mo_manifest_path"]),
        deployment_model=model,
        ledger_account_id=ledger_account_id,
        strategy_id=int(payload["strategy_id"]),
        expected_broker=str(payload["expected_broker"]),
        expected_broker_mode=str(payload["expected_broker_mode"]),
        shadow_ledger_identity=str(payload["shadow_ledger_identity"]),
        instrument_durable_state_id=str(payload["instrument_durable_state_id"]),
        starting_capital=float(payload["starting_capital"]),
        turnover_cost_bps=float(payload["turnover_cost_bps"]),
        backstop_days=int(payload["backstop_days"]),
        weight_drift_pct=float(payload["weight_drift_pct"]),
        witness=load_witness_config(payload.get("witness")),
        corpus_countersignature_path=(Path(payload["corpus_countersignature_path"])
                                      if payload.get("corpus_countersignature_path") else None),
        narrow_readiness_attestation_path=(
            Path(payload["narrow_readiness_attestation_path"])
            if payload.get("narrow_readiness_attestation_path") else None),
        first_session_outcome_pin=_parse_outcome_pin(payload.get("first_session_outcome_pin")),
        # ⚠ Absent => None, and the ancestry check then FAILS CLOSED wherever ancestry evidence is
        # required. There is deliberately no environment fallback and no default path: a deployment
        # that cannot point at its ancestry attestation must not have one fabricated for it. The field
        # existed on the dataclass but was never read from the payload, so it was silently always None
        # and no deployment could satisfy an ancestry check it did not itself descend from.
        ancestry_marker_path=(Path(payload["ancestry_marker_path"])
                              if payload.get("ancestry_marker_path") else None),
        runtime_digest_path=(Path(payload["runtime_digest_path"])
                             if payload.get("runtime_digest_path") else None),
        runtime_digest_env=(str(payload["runtime_digest_env"])
                            if payload.get("runtime_digest_env") else None),
        expected_commit=(str(payload["expected_commit"]) if payload.get("expected_commit") else None),
        source_path=resolved,
        raw=payload,
    )
