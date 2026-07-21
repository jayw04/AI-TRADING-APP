"""Operational hold — schema, validation, and the activation-blocking exception.

P7 §7-B (ADR 0044 invariants 5-7). A governed strategy may carry an operational
hold in its durable state (``strategy_state['operational_hold']``, the same
boundary the deployment lifecycle uses). This module owns the hold record's schema
and its FAIL-CLOSED validation so an activation-capable path never acts on a
malformed or unreadable hold.

Distinguishing the four cases (owner-specified) is the whole point:
  - row absent                         -> no hold (activation may proceed)
  - present, valid, status ACTIVE      -> BLOCK activation
  - present, valid, status CLEARED     -> allow (a governed clear happened)
  - present but malformed/unsupported  -> BLOCK (Deployment… no: HoldStateInvalid)
An unreadable store / failed query is the caller's concern and must ALSO block —
an unreadable hold is never read as "no hold".

Scope (7-B minimum): place / read-assert / clear / audit / enforcement. No RBAC
UI, no multiple simultaneous holds, no expiration, no history query — future work.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

HOLD_SCHEMA_VERSION = 1
K_OPERATIONAL_HOLD = "operational_hold"  # the strategy_state key


class HoldStatus(StrEnum):
    ACTIVE = "ACTIVE"
    CLEARED = "CLEARED"


class HoldStateInvalid(Exception):
    """The hold row exists but is malformed, an unsupported version, or otherwise
    unreadable. Activation MUST fail closed — never self-repair, never treat as
    'no hold'."""


class StrategyOnHold(Exception):
    """Raised by the activation guard when an ACTIVE operational hold blocks
    activation. Carries enough for a 409 / audit without a second query."""

    def __init__(self, strategy_id: int, reason_code: str, rev: int) -> None:
        self.strategy_id = strategy_id
        self.reason_code = reason_code
        self.rev = rev
        super().__init__(
            f"strategy {strategy_id} is under operational hold "
            f"({reason_code}, rev {rev})"
        )


class HoldConflict(Exception):
    """A place/clear lost the CAS or violated the mutation contract — a stale
    revision, a concurrent write, an attempt to silently replace an active hold's
    reason, or a clear with no active hold to clear."""


class HoldStoreUnavailable(Exception):
    """The strategy_state store could not be read/written. Fail closed — an
    unavailable store is NEVER interpreted as 'no hold'."""


@dataclass
class HoldRecord:
    status: HoldStatus
    reason_code: str
    reason: str
    effective_at: str          # ISO8601 — when the hold became effective
    placed_at: str             # ISO8601 — when this record was written
    placed_by: str
    rev: int
    evidence_refs: list = field(default_factory=list)
    approval_ref: str | None = None
    source: str | None = None  # e.g. RETROSPECTIVE_FORMALIZATION
    cleared_at: str | None = None
    cleared_by: str | None = None
    schema_version: int = HOLD_SCHEMA_VERSION

    @property
    def is_active(self) -> bool:
        return self.status == HoldStatus.ACTIVE

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "_rev": self.rev,
            "status": str(self.status),
            "reason_code": self.reason_code,
            "reason": self.reason,
            "effective_at": self.effective_at,
            "placed_at": self.placed_at,
            "placed_by": self.placed_by,
            "evidence_refs": list(self.evidence_refs),
            "approval_ref": self.approval_ref,
            "source": self.source,
            "cleared_at": self.cleared_at,
            "cleared_by": self.cleared_by,
        }


def load_hold_record(raw: dict | None) -> HoldRecord | None:
    """Parse + FAIL-CLOSED-validate a hold row. Returns None if absent (no hold);
    raises HoldStateInvalid if present-but-bad (caller blocks activation)."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise HoldStateInvalid(f"hold is not an object: {type(raw).__name__}")
    if raw.get("schema_version") != HOLD_SCHEMA_VERSION:
        raise HoldStateInvalid(f"unsupported hold schema_version {raw.get('schema_version')!r}")
    if not isinstance(raw.get("_rev"), int):
        raise HoldStateInvalid("missing/invalid _rev")
    try:
        status = HoldStatus(raw["status"])
    except (KeyError, ValueError) as exc:
        raise HoldStateInvalid(f"bad hold status: {raw.get('status')!r}") from exc
    for req in ("reason_code", "effective_at", "placed_at"):
        if not raw.get(req):
            raise HoldStateInvalid(f"missing required hold field: {req}")
    return HoldRecord(
        status=status,
        reason_code=raw["reason_code"],
        reason=raw.get("reason", ""),
        effective_at=raw["effective_at"],
        placed_at=raw["placed_at"],
        placed_by=raw.get("placed_by", ""),
        rev=raw["_rev"],
        evidence_refs=list(raw.get("evidence_refs", [])),
        approval_ref=raw.get("approval_ref"),
        source=raw.get("source"),
        cleared_at=raw.get("cleared_at"),
        cleared_by=raw.get("cleared_by"),
        schema_version=HOLD_SCHEMA_VERSION,
    )
