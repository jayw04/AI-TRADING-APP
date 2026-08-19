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

Evidence is TWO-PHASE. A remote read cannot be journalled as completed before it happens, because
until the governed reader returns you do not know whether verification succeeded. So:

    fsync read_intent (exact bound object identity)  ->  governed read
        -> fsync read_verified  (or read_failed, if that can still be written)

An earlier version journalled only AFTER the read and claimed "a read never proceeds
un-evidenced". That claim was false: if the append failed after a successful read, the sealed byte
had already been read with no durable row. The intent row is what actually bounds the opening --
it proves an attempt on a specific pinned object existed, even if the process dies immediately
after the read.

A journal whose last intent has no matching outcome row is EVIDENCE_INCOMPLETE. Such a run is
never silently treated as complete; see `reconcile`.
"""

from __future__ import annotations

import contextlib
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
        # An append-only journal RESUMES: a restarted process appending to an existing file must
        # continue the chain and the sequence, not fork them. Otherwise a second journal instance
        # restarts at sequence 1, colliding with earlier rows and making intent/outcome matching
        # ambiguous exactly in the process-death case this protocol exists to cover.
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        row = json.loads(line)
                        self.sequence = max(self.sequence, int(row.get("sequence", 0)))
                        self.prev_hash = row.get("row_hash", self.prev_hash)
            except Exception as exc:      # noqa: BLE001 - an unreadable journal is fail-closed
                raise EvidenceJournalFailure(
                    f"cannot resume evidence journal {path}: {type(exc).__name__}: {exc}") from exc
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
    """Wraps the governed reader with the two-phase evidence protocol.

    The inner reader is NEVER touched: it keeps its bound bytes and its own verification. This
    only bounds each read with durable intent/outcome rows.
    """

    def __init__(self, inner: Any, journal: EvidenceJournal):
        self._inner = inner
        self._journal = journal
        self.reader_kind = getattr(inner, "reader_kind", "UNKNOWN")

    @property
    def reads(self):
        return getattr(self._inner, "reads", [])

    def read(self, obj) -> bytes:
        # PHASE 1 -- durable BEFORE the governed read. If this cannot be persisted the read does
        # not happen at all, so no sealed byte is ever touched without a durable intent bounding it.
        intent = self._journal.append("read_intent", {
            "object_id": obj.key,
            "bucket": getattr(obj, "bucket", None),
            "version_id": obj.version_id,
            "partition": getattr(obj, "partition", None),
            "declared_sha256": getattr(obj, "sha256", None),
            "reader_kind": self.reader_kind,
        })

        try:
            payload = self._inner.read(obj)
        except BaseException as exc:                   # noqa: BLE001 - record, then re-raise
            # best-effort: a broken evidence sink must never mask the real read failure
            with contextlib.suppress(EvidenceJournalFailure):
                self._journal.append("read_failed", {
                    "intent_sequence": intent["sequence"],
                    "intent_row_hash": intent["row_hash"],
                    "object_id": obj.key,
                    "error": f"{type(exc).__name__}: {exc}"[:1000],
                })
            raise

        # PHASE 2 -- outcome. If THIS cannot be persisted the run stops: the intent row already
        # records that this exact pinned object was opened, so the boundary is not lost.
        self._journal.append("read_verified", {
            "intent_sequence": intent["sequence"],
            "intent_row_hash": intent["row_hash"],
            "object_id": obj.key,
            "version_id": obj.version_id,
            "partition": getattr(obj, "partition", None),
            "bytes": len(payload),
            "reader_verification": "PASSED",
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


def reconcile(rows: list[dict]) -> dict:
    """Reconcile intent rows against outcome rows and verify the hash chain.

    A run whose journal contains an intent with no matching read_verified/read_failed is
    EVIDENCE_INCOMPLETE -- the process may have died between the governed read and the outcome
    append, so that object may or may not have been opened. It is never reported as complete.
    """
    prev, chain_ok = ZERO, True
    for r in rows:
        if r.get("prev_hash") != prev:
            chain_ok = False
        recomputed = hashlib.sha256(
            json.dumps({k: v for k, v in r.items() if k != "row_hash"},
                       sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if recomputed != r.get("row_hash"):
            chain_ok = False
        prev = r.get("row_hash")

    intents = {r["sequence"]: r for r in rows if r.get("kind") == "read_intent"}
    resolved = {r.get("intent_sequence") for r in rows
                if r.get("kind") in ("read_verified", "read_failed")}
    unresolved = sorted(set(intents) - {s for s in resolved if s is not None})
    verified = [r for r in rows if r.get("kind") == "read_verified"]
    return {
        "chain_verifies": chain_ok,
        "intents": len(intents),
        "verified": len(verified),
        "failed": sum(1 for r in rows if r.get("kind") == "read_failed"),
        "unresolved_intents": unresolved,
        "unresolved_objects": [intents[s]["object_id"] for s in unresolved],
        "evidence_complete": chain_ok and not unresolved,
        "classification": ("EVIDENCE_COMPLETE" if chain_ok and not unresolved
                           else "EVIDENCE_INCOMPLETE"),
        "sealed_verified": sum(1 for r in verified if r.get("partition") == "VALIDATION"),
        "reference_verified": sum(1 for r in verified if r.get("partition") == "REFERENCE"),
    }
