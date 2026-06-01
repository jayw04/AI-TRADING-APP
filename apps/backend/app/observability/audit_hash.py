"""SHA-256 hash chain for ``audit_log`` rows (P5 §8.1).

The hash is computed over a canonical representation of the row's content
plus the previous row's hash in the same user's chain. Any change to a
row's content, any reordering, any insertion or deletion of a row breaks
the chain downstream — ``scripts/verify_audit_integrity.py`` detects it.

**Per-user chains, not a global chain.** ``prev_hash`` links to the
previous row *for the same ``user_id``*. A global chain would serialize
every audit write (each insert reading the latest row); per-user chains
parallelize and the schema accommodates multi-user without change.

**Canonicalization must be identical at write time and verify time.**
The write path (a ``before_insert`` mapper event in
``app/db/models/audit_log.py``) passes Python values straight off the ORM
object; the verify script reads raw strings back from SQLite. Two values
need careful, reproducible normalization:

  - ``ts`` — accepted as a ``datetime`` (write path) or a string (verify
    path / SQLite). Both are coerced to aware-UTC and emitted via
    ``isoformat()`` so "naive UTC" and "+00:00" forms hash identically.
  - ``payload_json`` — hashed AS the stored JSON string, not re-parsed.
    ``AuditLogger.write`` is the only writer and already serializes with
    ``json.dumps(..., default=str)``; hashing the stored string avoids a
    parse/re-serialize round-trip that could diverge.

The row ``id`` is deliberately **not** part of the hash: ``id`` is a
SQLite autoincrement assigned during INSERT (unknown at ``before_insert``
time without overriding the primary key), and the ``prev_hash`` linkage
already detects reordering and deletion. Content tampering is caught by
the per-row content hash; structural tampering by the chain.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any


def _canon_ts(ts: Any) -> str:
    """Coerce a datetime or SQLite timestamp string to a canonical aware-UTC
    isoformat string. ``None`` → empty string."""
    if ts is None:
        return ""
    if isinstance(ts, str):
        if not ts:
            return ""
        # SQLite DateTime renders "YYYY-MM-DD HH:MM:SS[.ffffff][+00:00]";
        # fromisoformat (3.11+) accepts the space separator and the offset.
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    else:
        parsed = ts
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.isoformat()


def compute_row_hash(
    *,
    user_id: int | None,
    actor_type: str | None,
    actor_id: str | None,
    action: str | None,
    target_type: str | None,
    target_id: str | None,
    payload_json: str | None,
    ts: Any,
    prev_hash: str | None,
) -> str:
    """SHA-256 over the canonical representation of an ``audit_log`` row.

    ``payload_json`` is the stored JSON string (or ``None``). ``ts`` may be
    a ``datetime`` or a string. ``target_id`` is the stored string form."""
    canonical = {
        "user_id": user_id,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "payload_json": payload_json or "",
        "ts": _canon_ts(ts),
        "prev_hash": prev_hash or "",
    }
    serialized = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
