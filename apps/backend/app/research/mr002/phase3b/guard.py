"""Validation-scoped access guard for the mounted Phase 3B layer.

The development guard in `spq1/adapters/partition_guard.py` is NOT edited, parameterised or
relaxed. Widening a working control to obtain a capability deletes the control; this module ADDS a
second one instead, bound to the validation window and its registered object set.

Two properties carry the governance weight:

  * OOS is refused unconditionally. A validation authorisation is never an OOS authorisation, and
    there is no code path here that could become one.
  * The opening is consumed by the first PERMITTED read of a validation object, and by nothing
    else. A refused attempt is recorded as evidence, never as an opening - the owner's 2026-08-11
    adjudication of "access event".
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

VALIDATION = "VALIDATION"
OOS = "OOS"
REFERENCE = "REFERENCE"
DEVELOPMENT = "DEVELOPMENT"

SEALED = (VALIDATION, OOS)
VIOLATION = "INTEGRITY_STOP:FORBIDDEN_PARTITION_ACCESS"


class ValidationAccessRefused(Exception):
    """An access the guard refuses. Never caught to retry."""


@dataclass
class ValidationGuard:
    """Registered-object allowlist + one-opening accounting + hash-chained attempt ledger."""

    registered_objects: dict[str, set[str]]
    pre_access_ready: bool = False
    _ledger: list[dict] = field(default_factory=list)
    _chain: str = "0" * 64
    _opening_consumed: bool = False

    def permitted(self, partition: str, object_id: str) -> tuple[bool, str]:
        if partition == OOS:
            return False, "oos_denied_requires_separate_authorization"
        if partition not in (VALIDATION, REFERENCE, DEVELOPMENT):
            return False, "unknown_partition"
        if object_id not in self.registered_objects.get(partition, set()):
            return False, "unregistered_object"
        if partition == VALIDATION and not self.pre_access_ready:
            return False, "pre_access_gate_not_reached"
        return True, "authorized"

    def open_object(self, partition: str, object_id: str, *, version_id: str | None = None) -> dict:
        ok, reason = self.permitted(partition, object_id)
        if partition == VALIDATION and ok and not version_id:
            ok, reason = False, "unpinned_read"
        entry = self._record(partition, object_id, ok, reason, version_id)
        if not ok:
            raise ValidationAccessRefused(f"{VIOLATION}:{partition}:{reason}:{object_id}")
        if partition == VALIDATION:
            self._opening_consumed = True
        return entry

    def _record(
        self, partition: str, object_id: str, permitted: bool, reason: str, version_id: str | None
    ) -> dict:
        entry = {
            "sequence": len(self._ledger) + 1,
            "partition": partition,
            "object_id": object_id,
            "version_id": version_id,
            "permitted": permitted,
            "reason": reason,
            "prev_hash": self._chain,
        }
        entry["row_hash"] = hashlib.sha256(
            json.dumps(entry, sort_keys=True, ensure_ascii=True).encode("ascii")
        ).hexdigest()
        self._chain = entry["row_hash"]
        self._ledger.append(entry)
        return entry

    # -- evidence -------------------------------------------------------------------
    @property
    def opening_consumed(self) -> bool:
        return self._opening_consumed

    def ledger(self) -> list[dict]:
        return list(self._ledger)

    def chain_verifies(self) -> bool:
        prev = "0" * 64
        for e in self._ledger:
            if e["prev_hash"] != prev:
                return False
            body = {k: v for k, v in e.items() if k != "row_hash"}
            if (
                hashlib.sha256(
                    json.dumps(body, sort_keys=True, ensure_ascii=True).encode("ascii")
                ).hexdigest()
                != e["row_hash"]
            ):
                return False
            prev = e["row_hash"]
        return True

    def counts(self) -> dict:
        permitted = [e for e in self._ledger if e["permitted"]]
        return {
            "attempts": len(self._ledger),
            "permitted": len(permitted),
            "blocked": len(self._ledger) - len(permitted),
            "validation_reads": sum(1 for e in permitted if e["partition"] == VALIDATION),
            "oos_reads": sum(1 for e in permitted if e["partition"] == OOS),
            "sealed_reads": sum(1 for e in permitted if e["partition"] in SEALED),
            "unregistered_data_source_reads": sum(
                1
                for e in permitted
                if e["object_id"] not in self.registered_objects.get(e["partition"], set())
            ),
        }
