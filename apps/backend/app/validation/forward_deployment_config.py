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

CONFIG_ENV = "FORWARD_VALIDATION_CONFIG"
DEFAULT_CONFIG_PATH = Path("/etc/workbench/forward_validation.json")

_REQUIRED_KEYS = (
    "factor_store_path", "app_db_path", "observation_store_dir", "ledger_path",
    "dgs3mo_path", "trial_ledger_path", "build_info_path", "deployment_manifest_path",
    "deployment_model", "ledger_account_id", "strategy_id", "expected_broker",
    "expected_broker_mode", "shadow_ledger_identity", "instrument_durable_state_id",
    "starting_capital", "turnover_cost_bps", "backstop_days", "weight_drift_pct",
)


class DeploymentConfigError(IntegrityStop):
    """The deployment did not describe itself completely enough to run a governed session."""


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
    runtime_digest_path: Path | None = None
    runtime_digest_env: str | None = None
    expected_commit: str | None = None
    source_path: Path | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    def to_open_provenance(self) -> dict[str, Any]:
        d = {k: (str(v) if isinstance(v, Path) else v) for k, v in asdict(self).items()
             if k not in {"raw"}}
        d["deployment_model"] = str(self.deployment_model)
        return d


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
        runtime_digest_path=(Path(payload["runtime_digest_path"])
                             if payload.get("runtime_digest_path") else None),
        runtime_digest_env=(str(payload["runtime_digest_env"])
                            if payload.get("runtime_digest_env") else None),
        expected_commit=(str(payload["expected_commit"]) if payload.get("expected_commit") else None),
        source_path=resolved,
        raw=payload,
    )
