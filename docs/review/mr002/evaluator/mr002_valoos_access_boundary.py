"""MR-002 validation/OOS evaluator — access boundary + opened-object ledger (operational increment).

The choke point between the evaluator and any partition object. Every read goes through
`AccessBoundary.open_object`; there is no second path. The boundary is fail-closed in every
direction:

  * an absent, unreadable, or malformed authorization state BLOCKS (it is not "no restriction");
  * VALIDATION is blocked unless the durable state records `validation_authorization = true` AND its
    bound identities match what the run expects AND the revision matches;
  * OOS is blocked UNCONDITIONALLY here — a validation grant never unlocks OOS, which requires its
    own separate later authorization and its own boundary;
  * an object outside the registered set is blocked whatever the partition;
  * every attempt — permitted or blocked — is recorded in a hash-chained opened-object ledger, so a
    refusal is evidence rather than a silence.

Reads no partition values itself: it returns the registered object identity and records the access.
"""

from __future__ import annotations

import hashlib
import json

SYNTHETIC = "SYNTHETIC"
DEVELOPMENT = "DEVELOPMENT"
VALIDATION = "VALIDATION"
OOS = "OOS"
PARTITIONS = (SYNTHETIC, DEVELOPMENT, VALIDATION, OOS)

SEALED_PARTITIONS = (VALIDATION, OOS)

VIOLATION = "INTEGRITY_STOP:ACCESS_BOUNDARY_VIOLATION"
STATE_INVALID = "INTEGRITY_STOP:AUTHORIZATION_STATE_INVALID"

_REQUIRED_STATE_FIELDS = ("record_type", "validation_authorization", "_rev", "bound_identities")


class AccessBoundaryViolation(Exception):
    """An access was attempted that the boundary refuses. Never caught to retry."""


class AuthorizationStateInvalid(Exception):
    """The durable authorization state is absent, unreadable, or malformed -> block."""


def load_authorization_state(path: str | None, *, raw: dict | None = None) -> dict:
    """Fail-closed read of the durable ValidationAuthorizationState record.

    Absent file, unreadable bytes, non-object JSON, wrong record_type, or a non-bool authorization
    flag all BLOCK. There is no "assume false and continue" branch: an unparseable state means the
    control structure is not intact, which is a different failure from a recorded `false`.
    """
    if raw is None:
        if not path:
            raise AuthorizationStateInvalid(f"{STATE_INVALID}:state_absent")
        try:
            with open(path, "rb") as fh:
                raw = json.loads(fh.read().decode("utf-8"))
        except FileNotFoundError as exc:
            raise AuthorizationStateInvalid(f"{STATE_INVALID}:state_absent") from exc
        except (ValueError, UnicodeDecodeError, OSError) as exc:
            raise AuthorizationStateInvalid(f"{STATE_INVALID}:state_unreadable") from exc
    if not isinstance(raw, dict):
        raise AuthorizationStateInvalid(f"{STATE_INVALID}:state_not_object")
    for field in _REQUIRED_STATE_FIELDS:
        if field not in raw:
            raise AuthorizationStateInvalid(f"{STATE_INVALID}:missing_field:{field}")
    if raw["record_type"] != "MR002_Phase3BC_ValidationAuthorizationState":
        raise AuthorizationStateInvalid(f"{STATE_INVALID}:wrong_record_type")
    if not isinstance(raw["validation_authorization"], bool):
        raise AuthorizationStateInvalid(f"{STATE_INVALID}:authorization_not_boolean")
    if not isinstance(raw["_rev"], int) or isinstance(raw["_rev"], bool) or raw["_rev"] < 0:
        raise AuthorizationStateInvalid(f"{STATE_INVALID}:rev_not_natural")
    if not isinstance(raw["bound_identities"], dict):
        raise AuthorizationStateInvalid(f"{STATE_INVALID}:bound_identities_not_object")
    return raw


class AccessBoundary:
    """Registered-object allowlist + authorization gate + hash-chained opened-object ledger."""

    def __init__(self, *, authorization_state: dict, registered_objects: dict,
                 expected_identities: dict | None = None, expected_rev: int | None = None):
        for partition in registered_objects:
            if partition not in PARTITIONS:
                raise AccessBoundaryViolation(f"{VIOLATION}:unknown_partition:{partition}")
        self._state = authorization_state
        self._registered = {p: set(objs) for p, objs in registered_objects.items()}
        self._expected = expected_identities or {}
        self._expected_rev = expected_rev
        self._ledger: list = []
        self._chain = "0" * 64

    # -- authorization ---------------------------------------------------------------
    def _validation_permitted(self) -> tuple[bool, str]:
        if self._state["validation_authorization"] is not True:
            return False, "validation_authorization_false"
        if self._expected_rev is not None and self._state["_rev"] != self._expected_rev:
            return False, "authorization_rev_mismatch"
        bound = self._state.get("bound_identities", {})
        for key, want in self._expected.items():
            if bound.get(key) != want:
                return False, f"bound_identity_mismatch:{key}"
        return True, "authorized"

    def partition_permitted(self, partition: str) -> tuple[bool, str]:
        if partition not in PARTITIONS:
            return False, "unknown_partition"
        if partition == OOS:
            # unconditional: a validation grant is not an OOS grant, and this boundary has no
            # code path that could become one
            return False, "oos_denied_requires_separate_authorization"
        if partition == VALIDATION:
            return self._validation_permitted()
        return True, "unsealed_partition"

    # -- the single access path ------------------------------------------------------
    def open_object(self, partition: str, object_id: str) -> dict:
        permitted, reason = self.partition_permitted(partition)
        registered = object_id in self._registered.get(partition, set())
        if permitted and not registered:
            permitted, reason = False, "unregistered_object"
        record = self._record(partition, object_id, permitted, reason)
        if not permitted:
            raise AccessBoundaryViolation(f"{VIOLATION}:{partition}:{reason}:{object_id}")
        return record

    def _record(self, partition: str, object_id: str, permitted: bool, reason: str) -> dict:
        entry = {"sequence": len(self._ledger) + 1, "partition": partition,
                 "object_id": object_id, "permitted": permitted, "reason": reason,
                 "prev_hash": self._chain}
        entry["row_hash"] = hashlib.sha256(
            json.dumps(entry, sort_keys=True, ensure_ascii=True).encode("ascii")).hexdigest()
        self._chain = entry["row_hash"]
        self._ledger.append(entry)
        return entry

    # -- evidence --------------------------------------------------------------------
    def opened_object_ledger(self) -> list:
        return list(self._ledger)

    def chain_verifies(self) -> bool:
        prev = "0" * 64
        for entry in self._ledger:
            if entry["prev_hash"] != prev:
                return False
            body = {k: v for k, v in entry.items() if k != "row_hash"}
            if hashlib.sha256(
                    json.dumps(body, sort_keys=True, ensure_ascii=True).encode("ascii")
            ).hexdigest() != entry["row_hash"]:
                return False
            prev = entry["row_hash"]
        return True

    def counts(self) -> dict:
        permitted = [e for e in self._ledger if e["permitted"]]
        blocked = [e for e in self._ledger if not e["permitted"]]
        return {
            "attempts": len(self._ledger),
            "permitted": len(permitted),
            "blocked": len(blocked),
            "validation_reads": sum(1 for e in permitted if e["partition"] == VALIDATION),
            "oos_reads": sum(1 for e in permitted if e["partition"] == OOS),
            "sealed_reads": sum(1 for e in permitted if e["partition"] in SEALED_PARTITIONS),
            "blocked_by_reason": {r: sum(1 for e in blocked if e["reason"] == r)
                                  for r in sorted({e["reason"] for e in blocked})},
        }

    def boundary_report(self) -> dict:
        counts = self.counts()
        return {
            "record_type": "MR002_Increment4_AccessBoundaryReport",
            "validation_authorization": self._state["validation_authorization"],
            "authorization_rev": self._state["_rev"],
            "registered_object_counts": {p: len(o) for p, o in sorted(self._registered.items())},
            "counts": counts,
            "chain_verifies": self.chain_verifies(),
            "sealed_reads_zero": counts["sealed_reads"] == 0,
            "opened_object_ledger": self.opened_object_ledger(),
        }
