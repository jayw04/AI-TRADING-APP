"""Durable execution evidence for a consumed one-time opening.

Owner ruling 2026-08-19. The 2026-08-19 validation run consumed the opening, then died in replay
with `validation_result.json` never written: the launcher serialised its report only on success, so
the in-memory ValidationOpenedObjectLedger was lost. For a consumed one-time opening, evidence must
survive the very failures it exists to document.

The lifecycle is now:

    sealed read -> durable ledger append (fsync) -> ... -> materialization
                -> durable materialization evidence -> replay
                -> terminal record written on every exit path

NOT: keep everything in RAM -> replay -> write one final report if nothing fails.

This module adds NO economic semantics and changes NO solver behaviour. It does not touch the
governed reader or the materializer: it wraps the reader, so `materialize()` and
`S3PinnedReader` keep their bound bytes.

Failure to journal is FAIL-CLOSED: if evidence cannot be made durable, the read does not proceed.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any

ZERO = "0" * 64


class EvidenceJournalFailure(RuntimeError):
    """Evidence could not be made durable. Fail closed rather than read un-evidenced."""


class EvidenceJournal:
    """Append-only, fsync'd, hash-chained JSONL journal.

    Each append is flushed and fsync'd before the caller continues, so a process death immediately
    after a read still leaves that read on disk.
    """

    def __init__(self, path: str):
        self.path = path
        self.prev_hash = ZERO
        self.sequence = 0
        try:
            directory = os.path.dirname(os.path.abspath(path))
            os.makedirs(directory, exist_ok=True)
            # noqa: SIM115 - the journal handle is deliberately long-lived: it must stay
            # open across the whole run so every read can be appended and fsync'd in place.
            self._fh = open(path, "a", encoding="utf-8")  # noqa: SIM115
            # Directory fsync is POSIX-only; Windows cannot open a directory handle this way.
            # It is a durability nicety, never a correctness requirement -- each append is
            # already flushed and fsync'd on the file itself.
            try:
                self._dir_fd = os.open(directory, os.O_RDONLY) if os.name != "nt" else None
            except OSError:
                self._dir_fd = None
        except Exception as exc:      # noqa: BLE001 - ANY inability to journal is fail-closed
            raise EvidenceJournalFailure(
                f"cannot open evidence journal {path}: {type(exc).__name__}: {exc}") from exc

    def append(self, kind: str, payload: dict) -> dict:
        self.sequence += 1
        row = {"sequence": self.sequence, "kind": kind,
               "at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "prev_hash": self.prev_hash, **payload}
        row["row_hash"] = hashlib.sha256(
            json.dumps({k: v for k, v in row.items() if k != "row_hash"},
                       sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        try:
            self._fh.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
            self._fh.flush()
            os.fsync(self._fh.fileno())
        except Exception as exc:      # noqa: BLE001 - ANY inability to journal is fail-closed
            raise EvidenceJournalFailure(
                f"cannot durably append {kind} to {self.path}: "
                f"{type(exc).__name__}: {exc}") from exc
        self.prev_hash = row["row_hash"]
        return row

    def close(self) -> None:
        try:
            self._fh.close()
            if self._dir_fd is not None:
                os.fsync(self._dir_fd)
                os.close(self._dir_fd)
        except OSError:
            pass


class JournalingReader:
    """Wraps the governed reader and durably journals every object as it is opened.

    Delegates reads unchanged. The wrapped reader's own verification still runs; this only records
    that it happened, before control returns to the materializer.
    """

    def __init__(self, inner: Any, journal: EvidenceJournal):
        self._inner = inner
        self._journal = journal
        self.reader_kind = getattr(inner, "reader_kind", "UNKNOWN")

    @property
    def reads(self):
        return getattr(self._inner, "reads", [])

    def read(self, obj) -> bytes:
        payload = self._inner.read(obj)
        self._journal.append("object_opened", {
            "object_id": obj.key,
            "bucket": getattr(obj, "bucket", None),
            "version_id": obj.version_id,
            "partition": getattr(obj, "partition", None),
            "declared_sha256": getattr(obj, "sha256", None),
            "bytes": len(payload),
            "reader_kind": self.reader_kind,
        })
        return payload


def materialization_complete(journal: EvidenceJournal, out_path: str, evidence: dict) -> dict:
    """Persist materialization evidence BEFORE replay begins."""
    size = os.path.getsize(out_path) if os.path.exists(out_path) else None
    digest = None
    if size is not None:
        h = hashlib.sha256()
        with open(out_path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
        digest = h.hexdigest()
    return journal.append("materialization_complete", {
        "materialized_path": out_path,
        "materialized_bytes": size,
        "materialized_sha256": digest,
        "objects_opened": len(evidence.get("objects_opened", [])),
        "logical_content_identity": evidence.get("logical_content_identity"),
    })


def terminal(journal: EvidenceJournal, disposition: str, detail: str = "") -> dict:
    """Written on EVERY exit path, including exceptions."""
    return journal.append("terminal", {"disposition": disposition, "detail": detail[:2000]})
