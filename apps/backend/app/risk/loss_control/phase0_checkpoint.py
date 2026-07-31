"""ADR-0043 Phase-0 WP3 — checkpoint integrity (offline).

Implements AMD-07 / CORR-07 as elevated to **BLOCKING** by the owner freeze
(Controlling Design v1.1 §3.5):

* binding tuple includes ``loss_control_state_version``;
* sealed checkpoints carry a content hash (and HMAC-SHA256 when a key is supplied);
* tampered or corrupted contents fail closed at load, even when the filename is valid;
* cross-session reuse of a sealed checkpoint is refused.

Does not submit orders or import the order path.
"""

from __future__ import annotations

import hashlib
import hmac
import inspect
import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

CHECKPOINT_SCHEMA_VERSION = 1

# Fields that must be present for a checkpoint to be accepted as authoritative evidence.
REQUIRED_BINDING_FIELDS: frozenset[str] = frozenset(
    {
        "schema_version",
        "run_id",
        "session_id",
        "account_id",
        "plan_hash",
        "authorization_id",
        "loss_control_state",
        "loss_control_state_version",
        "payload",
    }
)

INTEGRITY_FIELD_CONTENT_HASH = "content_hash"
INTEGRITY_FIELD_HMAC = "hmac_sha256"
_ENVELOPE_EXCLUDE_FROM_HASH = frozenset({INTEGRITY_FIELD_CONTENT_HASH, INTEGRITY_FIELD_HMAC})


class CheckpointRefuseReason(StrEnum):
    CORRUPTED_JSON = "CORRUPTED_JSON"
    BINDING_INCOMPLETE = "BINDING_INCOMPLETE"
    MISSING_STATE_VERSION = "MISSING_STATE_VERSION"
    MISSING_CONTENT_HASH = "MISSING_CONTENT_HASH"
    CONTENT_HASH_MISMATCH = "CONTENT_HASH_MISMATCH"
    HMAC_REQUIRED = "HMAC_REQUIRED"
    HMAC_MISMATCH = "HMAC_MISMATCH"
    TAMPERED_CONTENTS = "TAMPERED_CONTENTS"
    CROSS_SESSION_REUSE = "CROSS_SESSION_REUSE"
    SCHEMA_UNSUPPORTED = "SCHEMA_UNSUPPORTED"


@dataclass(frozen=True)
class CheckpointBinding:
    """Authoritative binding tuple for a Phase-0 checkpoint (AMD-07)."""

    run_id: str
    session_id: str
    account_id: int
    plan_hash: str
    authorization_id: str
    loss_control_state: str
    loss_control_state_version: int
    payload: dict[str, Any] = field(default_factory=dict)
    schema_version: int = CHECKPOINT_SCHEMA_VERSION

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "run_id": str(self.run_id),
            "session_id": str(self.session_id),
            "account_id": int(self.account_id),
            "plan_hash": str(self.plan_hash),
            "authorization_id": str(self.authorization_id),
            "loss_control_state": str(self.loss_control_state),
            "loss_control_state_version": int(self.loss_control_state_version),
            "payload": self.payload,
        }


@dataclass(frozen=True)
class CheckpointLoadResult:
    accepted: bool
    binding: CheckpointBinding | None = None
    reason: CheckpointRefuseReason | None = None
    detail: str = ""
    envelope: dict[str, Any] | None = None


def _canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def compute_content_hash(binding_dict: dict[str, Any]) -> str:
    """SHA-256 over the binding tuple only (integrity fields excluded)."""
    body = {k: v for k, v in binding_dict.items() if k not in _ENVELOPE_EXCLUDE_FROM_HASH}
    missing = REQUIRED_BINDING_FIELDS - body.keys()
    if missing:
        raise ValueError(f"binding incomplete for hash: {sorted(missing)}")
    digest = hashlib.sha256(_canonical_json(body)).hexdigest()
    return f"sha256:{digest}"


def compute_hmac_sha256(binding_dict: dict[str, Any], key: bytes) -> str:
    body = {k: v for k, v in binding_dict.items() if k not in _ENVELOPE_EXCLUDE_FROM_HASH}
    digest = hmac.new(key, _canonical_json(body), hashlib.sha256).hexdigest()
    return f"hmac-sha256:{digest}"


def seal_checkpoint(
    binding: CheckpointBinding,
    *,
    hmac_key: bytes | None = None,
) -> dict[str, Any]:
    """Produce a sealed envelope ready for durable write."""
    body = binding.to_canonical_dict()
    envelope = dict(body)
    envelope[INTEGRITY_FIELD_CONTENT_HASH] = compute_content_hash(body)
    if hmac_key is not None:
        envelope[INTEGRITY_FIELD_HMAC] = compute_hmac_sha256(body, hmac_key)
    return envelope


def write_sealed_checkpoint(
    path: Path | str,
    binding: CheckpointBinding,
    *,
    hmac_key: bytes | None = None,
) -> dict[str, Any]:
    """Atomically write a sealed checkpoint (tmp + replace)."""
    path = Path(path)
    envelope = seal_checkpoint(binding, hmac_key=hmac_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(envelope, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    return envelope


def verify_checkpoint_envelope(
    raw: dict[str, Any] | str | bytes,
    *,
    hmac_key: bytes | None = None,
    require_hmac: bool = False,
    expected_session_id: str | None = None,
) -> CheckpointLoadResult:
    """Verify and accept a sealed checkpoint envelope. Fail closed on any integrity defect."""
    try:
        if isinstance(raw, (str, bytes)):
            text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            data = json.loads(text)
        else:
            data = dict(raw)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return CheckpointLoadResult(
            False, reason=CheckpointRefuseReason.CORRUPTED_JSON, detail=str(exc)
        )

    if not isinstance(data, dict):
        return CheckpointLoadResult(
            False, reason=CheckpointRefuseReason.CORRUPTED_JSON, detail="envelope is not an object"
        )

    missing = REQUIRED_BINDING_FIELDS - data.keys()
    if missing:
        reason = (
            CheckpointRefuseReason.MISSING_STATE_VERSION
            if "loss_control_state_version" in missing
            else CheckpointRefuseReason.BINDING_INCOMPLETE
        )
        return CheckpointLoadResult(
            False,
            reason=reason,
            detail=f"missing binding fields: {sorted(missing)}",
            envelope=data,
        )

    try:
        schema = int(data["schema_version"])
        state_version = int(data["loss_control_state_version"])
        account_id = int(data["account_id"])
    except (TypeError, ValueError) as exc:
        return CheckpointLoadResult(
            False,
            reason=CheckpointRefuseReason.BINDING_INCOMPLETE,
            detail=f"non-integer binding field: {exc}",
            envelope=data,
        )

    if schema != CHECKPOINT_SCHEMA_VERSION:
        return CheckpointLoadResult(
            False,
            reason=CheckpointRefuseReason.SCHEMA_UNSUPPORTED,
            detail=f"schema_version {schema} != {CHECKPOINT_SCHEMA_VERSION}",
            envelope=data,
        )

    if "loss_control_state_version" not in data or data["loss_control_state_version"] is None:
        return CheckpointLoadResult(
            False,
            reason=CheckpointRefuseReason.MISSING_STATE_VERSION,
            detail="loss_control_state_version absent from binding tuple",
            envelope=data,
        )

    stored_hash = data.get(INTEGRITY_FIELD_CONTENT_HASH)
    if not stored_hash:
        return CheckpointLoadResult(
            False,
            reason=CheckpointRefuseReason.MISSING_CONTENT_HASH,
            detail="sealed checkpoint requires content_hash",
            envelope=data,
        )

    binding_body = {k: data[k] for k in REQUIRED_BINDING_FIELDS}
    try:
        expected_hash = compute_content_hash(binding_body)
    except ValueError as exc:
        return CheckpointLoadResult(
            False, reason=CheckpointRefuseReason.BINDING_INCOMPLETE, detail=str(exc), envelope=data
        )

    if not hmac.compare_digest(str(stored_hash), expected_hash):
        return CheckpointLoadResult(
            False,
            reason=CheckpointRefuseReason.TAMPERED_CONTENTS,
            detail=f"content_hash mismatch ({CheckpointRefuseReason.CONTENT_HASH_MISMATCH})",
            envelope=data,
        )

    stored_mac = data.get(INTEGRITY_FIELD_HMAC)
    if require_hmac or hmac_key is not None:
        if hmac_key is None:
            return CheckpointLoadResult(
                False,
                reason=CheckpointRefuseReason.HMAC_REQUIRED,
                detail="HMAC key required to accept this checkpoint",
                envelope=data,
            )
        if not stored_mac:
            return CheckpointLoadResult(
                False,
                reason=CheckpointRefuseReason.HMAC_REQUIRED,
                detail="envelope missing hmac_sha256",
                envelope=data,
            )
        expected_mac = compute_hmac_sha256(binding_body, hmac_key)
        if not hmac.compare_digest(str(stored_mac), expected_mac):
            return CheckpointLoadResult(
                False,
                reason=CheckpointRefuseReason.HMAC_MISMATCH,
                detail="hmac_sha256 mismatch (tamper or wrong key)",
                envelope=data,
            )

    if expected_session_id is not None and str(data["session_id"]) != str(expected_session_id):
        return CheckpointLoadResult(
            False,
            reason=CheckpointRefuseReason.CROSS_SESSION_REUSE,
            detail=(
                f"checkpoint session_id {data['session_id']!r} does not match "
                f"expected {expected_session_id!r}"
            ),
            envelope=data,
        )

    if not isinstance(data["payload"], dict):
        return CheckpointLoadResult(
            False,
            reason=CheckpointRefuseReason.BINDING_INCOMPLETE,
            detail="payload must be an object",
            envelope=data,
        )

    binding = CheckpointBinding(
        schema_version=schema,
        run_id=str(data["run_id"]),
        session_id=str(data["session_id"]),
        account_id=account_id,
        plan_hash=str(data["plan_hash"]),
        authorization_id=str(data["authorization_id"]),
        loss_control_state=str(data["loss_control_state"]),
        loss_control_state_version=state_version,
        payload=dict(data["payload"]),
    )
    return CheckpointLoadResult(True, binding=binding, envelope=data)


def load_sealed_checkpoint(
    path: Path | str,
    *,
    hmac_key: bytes | None = None,
    require_hmac: bool = False,
    expected_session_id: str | None = None,
) -> CheckpointLoadResult:
    """Load from a path. Valid filename alone is never sufficient — contents must verify."""
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        return CheckpointLoadResult(
            False, reason=CheckpointRefuseReason.CORRUPTED_JSON, detail=f"unreadable: {exc}"
        )
    return verify_checkpoint_envelope(
        raw,
        hmac_key=hmac_key,
        require_hmac=require_hmac,
        expected_session_id=expected_session_id,
    )


def assert_no_order_path_imports() -> None:
    import app.risk.loss_control.phase0_checkpoint as mod

    src = inspect.getsource(mod)
    needles = [
        "from app." + "services.order_router",
        "import app." + "services.order_router",
        "from app." + "brokers",
        "import app." + "brokers",
        "from app." + "orders",
        "submit_" + "order(",
    ]
    for needle in needles:
        if needle in src:
            raise AssertionError(f"phase0_checkpoint must not reference {needle}")


__all__ = [
    "CHECKPOINT_SCHEMA_VERSION",
    "REQUIRED_BINDING_FIELDS",
    "CheckpointBinding",
    "CheckpointLoadResult",
    "CheckpointRefuseReason",
    "assert_no_order_path_imports",
    "compute_content_hash",
    "compute_hmac_sha256",
    "load_sealed_checkpoint",
    "seal_checkpoint",
    "verify_checkpoint_envelope",
    "write_sealed_checkpoint",
]
