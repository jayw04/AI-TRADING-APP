"""Deployment-lifecycle blob — schema, (de)serialization, and FAIL-CLOSED validation.

P7 §7-A.2b (momentum-daily cold-start repair). The template persists ONE atomic,
``_rev``-versioned JSON blob under ``strategy_state['deployment']`` holding the
whole lifecycle. This module owns its schema and validation so the template never
acts on a malformed or internally-impossible state:

- missing blob            -> DeploymentStateUninitialized  (template: submit nothing,
                             emit ``deployment_state_uninitialized``; 7-B does the
                             authoritative first init)
- present but malformed / unsupported version / impossible combination
                          -> DeploymentStateInvalid        (template: fail closed,
                             emit ``deployment_state_invalid``; never self-repair)

Impossible combinations (owner-specified) are rejected, not silently fixed:
  * has_ever_deployed == false AND state == DEPLOYED
  * has_ever_deployed == true  AND first_deployed_at is null
  * state == DEPLOYMENT_PENDING AND active_seed_attempt is null
  * state == NEVER_DEPLOYED     AND an active NON-TERMINAL attempt exists
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.strategies.seed_reconciliation import (
    DeploymentState,
    SeedAttempt,
    SeedAttemptStatus,
)

SCHEMA_VERSION = 1

_TERMINAL_ATTEMPT = {SeedAttemptStatus.FILLED, SeedAttemptStatus.TERMINALLY_UNFILLED}


class DeploymentStateUninitialized(Exception):
    """The blob does not exist yet (raw is None)."""


class DeploymentStateInvalid(Exception):
    """The blob exists but is malformed, an unsupported version, or internally
    impossible. The template must fail closed — never self-repair."""


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _parse_dt(v, field_name: str) -> datetime | None:
    if v is None:
        return None
    try:
        return datetime.fromisoformat(v)
    except (TypeError, ValueError) as exc:
        raise DeploymentStateInvalid(f"bad datetime in {field_name}: {v!r}") from exc


def _require_dt(v, field_name: str) -> datetime:
    """Like ``_parse_dt`` but for a required field — a null/missing value is invalid."""
    dt = _parse_dt(v, field_name)
    if dt is None:
        raise DeploymentStateInvalid(f"missing required datetime: {field_name}")
    return dt


def seed_attempt_to_dict(a: SeedAttempt) -> dict:
    return {
        "attempt_id": a.attempt_id,
        "created_at": _iso(a.created_at),
        "intended_symbols": list(a.intended_symbols),
        "client_order_id_prefix": a.client_order_id_prefix,
        "submitted_order_ids": list(a.submitted_order_ids),
        "status": str(a.status),
        "last_reconciled_fill_at": _iso(a.last_reconciled_fill_at),
        "last_reconciled_fill_id": a.last_reconciled_fill_id,
    }


def seed_attempt_from_dict(d: dict) -> SeedAttempt:
    try:
        return SeedAttempt(
            attempt_id=d["attempt_id"],
            created_at=_require_dt(d["created_at"], "attempt.created_at"),
            intended_symbols=tuple(d.get("intended_symbols", ())),
            client_order_id_prefix=d["client_order_id_prefix"],
            submitted_order_ids=tuple(d.get("submitted_order_ids", ())),
            status=SeedAttemptStatus(d["status"]),
            last_reconciled_fill_at=_parse_dt(
                d.get("last_reconciled_fill_at"), "attempt.last_reconciled_fill_at"
            ),
            last_reconciled_fill_id=d.get("last_reconciled_fill_id"),
        )
    except (KeyError, ValueError) as exc:
        raise DeploymentStateInvalid(f"malformed active_seed_attempt: {exc}") from exc


@dataclass
class DeploymentBlob:
    rev: int
    state: DeploymentState
    has_ever_deployed: bool
    first_deployed_at: datetime | None = None
    active_seed_attempt: SeedAttempt | None = None
    # Latest TERMINAL attempt, archived for forensics (not full history — 7-B adds
    # an append-only audit; documented limitation).
    last_seed_attempt: dict | None = None
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "_rev": self.rev,
            "state": str(self.state),
            "has_ever_deployed": self.has_ever_deployed,
            "first_deployed_at": _iso(self.first_deployed_at),
            "active_seed_attempt": (
                seed_attempt_to_dict(self.active_seed_attempt)
                if self.active_seed_attempt is not None
                else None
            ),
            "last_seed_attempt": self.last_seed_attempt,
        }


def initial_blob() -> DeploymentBlob:
    """The authoritative NEVER_DEPLOYED starting blob (rev 0)."""
    return DeploymentBlob(rev=0, state=DeploymentState.NEVER_DEPLOYED, has_ever_deployed=False)


def load_deployment_blob(raw: dict | None) -> DeploymentBlob:
    """Parse + FAIL-CLOSED-validate the persisted blob. Raises
    DeploymentStateUninitialized (raw is None) or DeploymentStateInvalid."""
    if raw is None:
        raise DeploymentStateUninitialized
    if not isinstance(raw, dict):
        raise DeploymentStateInvalid(f"blob is not an object: {type(raw).__name__}")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise DeploymentStateInvalid(f"unsupported schema_version {raw.get('schema_version')!r}")
    if not isinstance(raw.get("_rev"), int):
        raise DeploymentStateInvalid("missing/invalid _rev")
    try:
        state = DeploymentState(raw["state"])
    except (KeyError, ValueError) as exc:
        raise DeploymentStateInvalid(f"bad state: {raw.get('state')!r}") from exc

    has_ever = bool(raw.get("has_ever_deployed"))
    first_dep = _parse_dt(raw.get("first_deployed_at"), "first_deployed_at")
    active_raw = raw.get("active_seed_attempt")
    active = seed_attempt_from_dict(active_raw) if active_raw is not None else None

    # Impossible combinations — reject, never repair.
    if state == DeploymentState.DEPLOYED and not has_ever:
        raise DeploymentStateInvalid("DEPLOYED but has_ever_deployed is false")
    if has_ever and first_dep is None:
        raise DeploymentStateInvalid("has_ever_deployed but first_deployed_at is null")
    if state == DeploymentState.DEPLOYMENT_PENDING and active is None:
        raise DeploymentStateInvalid("DEPLOYMENT_PENDING but no active_seed_attempt")
    if (
        state == DeploymentState.NEVER_DEPLOYED
        and active is not None
        and active.status not in _TERMINAL_ATTEMPT
    ):
        raise DeploymentStateInvalid("NEVER_DEPLOYED but an active non-terminal attempt exists")

    return DeploymentBlob(
        rev=raw["_rev"],
        state=state,
        has_ever_deployed=has_ever,
        first_deployed_at=first_dep,
        active_seed_attempt=active,
        last_seed_attempt=raw.get("last_seed_attempt"),
        schema_version=SCHEMA_VERSION,
    )
