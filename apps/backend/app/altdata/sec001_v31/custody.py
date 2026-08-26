"""Crash-safe exactly-once acquisition: an accession state machine and an atomic store.

Two review findings (both P0) live here, and they are the same failure in two layers.

**The exactly-once window.** The previous orchestrator sent the request, then marked the
accession acquired, then parsed, then wrote evidence. A durable ledger of *counters plus an
acquired set* cannot describe the states in between, so a crash left one of two wrong
answers: before ``mark_acquired`` the accession looked un-fetched and would be requested
again (violating CIK-once against a frozen cap); after it, the accession looked complete
while its evidence might never have been written, and the retry that would rebuild it was
permanently refused. The durable unit is therefore an **accession state machine**, and
intent is recorded *before* the request rather than success after it.

**The publication window.** ``os.open(final, O_CREAT | O_EXCL)`` is exclusive *creation*,
not atomic *publication*: it reserves the final pathname and only then writes into it, so a
failure mid-write leaves a truncated object at the name that is supposed to mean "sealed
evidence". Publication is now: write a complete temporary object, flush, ``fsync``, close,
link it into place under the final name (which fails if that name exists, so concurrent
overwrite is still impossible), sync the directory, then **re-read the published bytes and
verify their digest** before the accession is allowed to reach ``SEALED``.

The invariant both halves exist to guarantee:

    there is no recoverable state in which an accession is treated as acquired and a valid
    terminal artifact is absent.

A non-terminal state on restart is an **interrupted acquisition** — reported for
adjudication, never silently retried and never silently treated as complete.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Final


class AccessionState(StrEnum):
    """The durable lifecycle of one authorized accession."""

    AUTHORIZED = "AUTHORIZED"
    LOCATOR_INTENT = "LOCATOR_INTENT"
    LOCATOR_REQUEST_SENT = "LOCATOR_REQUEST_SENT"
    LOCATOR_RESPONSE_RECEIVED = "LOCATOR_RESPONSE_RECEIVED"
    LOCATOR_RESOLVED = "LOCATOR_RESOLVED"
    LOCATOR_SCHEMA_UNSUPPORTED = "LOCATOR_SCHEMA_UNSUPPORTED"
    LOCATOR_NO_PRIMARY_DOCUMENT = "LOCATOR_NO_PRIMARY_DOCUMENT"
    DOCUMENT_RANGE_INTEGRITY_FAILURE = "DOCUMENT_RANGE_INTEGRITY_FAILURE"
    REQUEST_INTENT = "REQUEST_INTENT"
    REQUEST_SENT = "REQUEST_SENT"
    RESPONSE_RETAINED = "RESPONSE_RETAINED"
    EVIDENCE_UNAVAILABLE = "EVIDENCE_UNAVAILABLE"
    PARSED = "PARSED"
    SEALED = "SEALED"


#: States from which nothing further is owed.
TERMINAL_STATES: Final[frozenset[AccessionState]] = frozenset(
    {AccessionState.SEALED, AccessionState.EVIDENCE_UNAVAILABLE}
)

#: States a *completed* step leaves behind, from which work may legitimately continue.
#: ``LOCATOR_RESOLVED`` is the load-bearing one: an accession screened out of the canary on
#: document size has spent no document request, so it stays available rather than being
#: consumed. Failing a screen is not the same as being used up.
RESUMABLE_STATES: Final[frozenset[AccessionState]] = frozenset(
    {
        AccessionState.AUTHORIZED,
        AccessionState.LOCATOR_RESOLVED,
        # Determinate parse outcomes. The request completed and we know exactly what came
        # back; that is a fact about the representation, not an ambiguous interruption, so
        # it must not strand the accession. Its response digest is retained.
        AccessionState.LOCATOR_SCHEMA_UNSUPPORTED,
        AccessionState.LOCATOR_NO_PRIMARY_DOCUMENT,
        # A received response whose facts were durably captured BEFORE adjudication, and
        # which proves the server broke the range contract. Determinate, not a crash --
        # PROSPECTIVE only: it does not reclassify canary attempt #1, whose response facts
        # were never captured and which therefore remains genuinely interrupted.
        AccessionState.DOCUMENT_RANGE_INTEGRITY_FAILURE,
    }
)

#: Mid-flight states. A crash in any of these means a request may already have been put on
#: the wire -- an index request for the locator pair, a document request for the rest -- so
#: repeating it would spend a frozen budget twice for one accession.
INTERRUPTED_STATES: Final[frozenset[AccessionState]] = frozenset(
    {
        AccessionState.LOCATOR_INTENT,
        # Genuinely in flight: no response outcome was durably recorded.
        AccessionState.LOCATOR_REQUEST_SENT,
        # A response arrived and its status/length/digest are recorded, but the parse
        # outcome is not. Distinguishable from a bare in-flight crash, still adjudicable:
        # the body was not retained, so completing it would need another counted request.
        AccessionState.LOCATOR_RESPONSE_RECEIVED,
        AccessionState.REQUEST_INTENT,
        AccessionState.REQUEST_SENT,
        AccessionState.RESPONSE_RETAINED,
        AccessionState.PARSED,
    }
)

# The three sets must partition the lifecycle: a state that belongs to none of them would
# fall through every guard, which is precisely how the previous revision leaked a duplicate.
assert set(AccessionState) == TERMINAL_STATES | RESUMABLE_STATES | INTERRUPTED_STATES
assert not (TERMINAL_STATES & RESUMABLE_STATES)
assert not (RESUMABLE_STATES & INTERRUPTED_STATES)
assert not (TERMINAL_STATES & INTERRUPTED_STATES)


class InterruptedAcquisition(RuntimeError):
    """An accession was found mid-flight on restart. A human adjudicates it."""


class CustodyViolation(RuntimeError):
    """A published artifact could not be created, or failed verification after publication."""


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _fsync_dir(path: Path) -> None:
    """Durably record a directory entry. A no-op where the platform disallows it."""
    try:
        fd = os.open(path, getattr(os, "O_DIRECTORY", os.O_RDONLY))
    except (OSError, AttributeError):
        return  # Windows cannot open a directory this way; the link itself is still atomic
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Durably replace ``path`` with ``payload``.

    temp -> write -> flush -> fsync -> close -> os.replace -> directory sync. Exported so
    the request ledger uses exactly the primitive the journal does: an accounting record
    written *before* a request goes on the wire is worth nothing if it can be lost by the
    same failure the request survives.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, indent=2, sort_keys=True))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        _fsync_dir(path.parent)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


@dataclass
class AccessionRecord:
    accession: str
    cik: int
    form: str
    state: AccessionState
    history: list[dict[str, Any]] = field(default_factory=list)
    artifact_sha256: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "accession": self.accession,
            "cik": self.cik,
            "form": self.form,
            "state": self.state.value,
            "history": self.history,
            "artifact_sha256": self.artifact_sha256,
            "detail": self.detail,
        }

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> AccessionRecord:
        return cls(
            accession=d["accession"],
            cik=int(d["cik"]),
            form=d["form"],
            state=AccessionState(d["state"]),
            history=list(d.get("history", [])),
            artifact_sha256=d.get("artifact_sha256"),
            detail=dict(d.get("detail", {})),
        )


class AcquisitionJournal:
    """Durable per-accession state. Every transition is flushed before it is relied upon."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, AccessionRecord] = {}
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._records = {
                k: AccessionRecord.from_json(v) for k, v in raw.get("accessions", {}).items()
            }

    # ---- durable write ---------------------------------------------------------------
    def _flush(self) -> None:
        atomic_write_json(
            self.path,
            {
                "accessions": {k: v.to_json() for k, v in self._records.items()},
                "updated_utc": _utc_now(),
            },
        )

    # ---- queries ---------------------------------------------------------------------
    def get(self, accession: str) -> AccessionRecord | None:
        return self._records.get(accession)

    def state_of(self, accession: str) -> AccessionState:
        rec = self._records.get(accession)
        return rec.state if rec else AccessionState.AUTHORIZED

    def interrupted(self) -> list[AccessionRecord]:
        """Accessions found mid-flight. Neither retried nor treated as complete."""
        return [r for r in self._records.values() if r.state in INTERRUPTED_STATES]

    def sealed(self) -> list[AccessionRecord]:
        return [r for r in self._records.values() if r.state is AccessionState.SEALED]

    # ---- transitions -----------------------------------------------------------------
    def transition(
        self,
        key: str,
        cik: int,
        form: str,
        state: AccessionState,
        *,
        accession: str | None = None,
        **detail: Any,
    ) -> AccessionRecord:
        """``key`` addresses the record; ``accession`` is the real SEC accession.

        They differ once attempts are namespaced (``<accession>#attemptN``). Keeping them
        distinct matters: anything that derives an evidence path from the record -- notably
        ``reconcile`` -- must use the real accession, or a perfectly good sealed artifact
        reads as missing and the invariant alarm fires falsely.
        """
        rec = self._records.get(key)
        if rec is None:
            rec = AccessionRecord(accession=accession or key, cik=cik, form=form, state=state)
            self._records[key] = rec
        else:
            rec.state = state
        rec.history.append({"state": state.value, "at": _utc_now(), **detail})
        if detail:
            rec.detail.update(detail)
        self._flush()
        return rec

    def seal(self, key: str, artifact_sha256: str) -> AccessionRecord:
        rec = self._records[key]
        rec.artifact_sha256 = artifact_sha256
        return self.transition(
            key,
            rec.cik,
            rec.form,
            AccessionState.SEALED,
            accession=rec.accession,
            artifact_sha256=artifact_sha256,
        )

    def guard_fresh(self, accession: str) -> None:
        """Refuse to start an accession that is complete, or that was left mid-flight."""
        state = self.state_of(accession)
        if state in TERMINAL_STATES:
            raise CustodyViolation(f"{accession} is already terminal in state {state.value}")
        if state in INTERRUPTED_STATES:
            raise InterruptedAcquisition(
                f"{accession} was left in {state.value}: a request may already have been sent "
                "and its evidence may be incomplete. This is a HOLD for adjudication -- it is "
                "neither silently retried nor silently treated as complete."
            )


class TransactionalEvidenceStore:
    """Write a complete object, then publish it atomically, then verify what was published."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def identity(cik: int, accession: str, source_variant: str, observation_id: str) -> str:
        return f"{cik:010d}/{accession}/{source_variant}/{observation_id}"

    @staticmethod
    def accession_identity(cik: int, accession: str, source_variant: str) -> str:
        return f"{cik:010d}/{accession}/{source_variant}"

    def path_for(self, cik: int, accession: str, source_variant: str) -> Path:
        return self.root / f"{cik:010d}-{accession}-{source_variant}.json"

    def publish_accession_set(
        self,
        cik: int,
        accession: str,
        source_variant: str,
        records: list[dict[str, Any]],
        observation_ids: list[str],
        provenance: dict[str, Any],
    ) -> tuple[Path, str]:
        """Publish one accession's whole observation set. Returns (path, verified sha256)."""
        final = self.path_for(cik, accession, source_variant)
        payload = json.dumps(
            {
                "_artifact_identity": self.accession_identity(cik, accession, source_variant),
                "observation_ids": observation_ids,
                "observations": records,
                "provenance": provenance,
                "committed_utc": _utc_now(),
            },
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        expected = hashlib.sha256(payload).hexdigest()

        # 1. a COMPLETE temporary object, durably on disk before it has the final name
        fd, tmp_name = tempfile.mkstemp(dir=str(self.root), suffix=".partial")
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())

            # 2. atomic, NON-overwriting publication: link fails if the name already exists
            try:
                os.link(tmp, final)
            except FileExistsError as exc:
                raise CustodyViolation(
                    f"artifact identity already exists: "
                    f"{self.accession_identity(cik, accession, source_variant)}"
                ) from exc
            _fsync_dir(self.root)
        finally:
            tmp.unlink(missing_ok=True)

        # 3. verify what was actually published, not what we meant to publish
        got = hashlib.sha256(final.read_bytes()).hexdigest()
        if got != expected:
            raise CustodyViolation(
                f"published artifact digest {got} != expected {expected} for {accession}"
            )
        return final, got

    def verify(self, cik: int, accession: str, source_variant: str, expected_sha256: str) -> bool:
        p = self.path_for(cik, accession, source_variant)
        if not p.exists():
            return False
        return hashlib.sha256(p.read_bytes()).hexdigest() == expected_sha256


def reconcile(
    journal: AcquisitionJournal, store: TransactionalEvidenceStore, source_variant: str
) -> dict[str, list[str]]:
    """Restart-time census. Proves the invariant, or names every accession that breaks it."""
    report: dict[str, list[str]] = {
        "sealed_and_verified": [],
        "sealed_but_artifact_missing_or_corrupt": [],
        "interrupted": [],
        "evidence_unavailable": [],
        "locator_resolved_unspent": [],
    }
    for rec in journal._records.values():
        if rec.state is AccessionState.SEALED:
            ok = rec.artifact_sha256 is not None and store.verify(
                rec.cik, rec.accession, source_variant, rec.artifact_sha256
            )
            key = "sealed_and_verified" if ok else "sealed_but_artifact_missing_or_corrupt"
            report[key].append(rec.accession)
        elif rec.state is AccessionState.EVIDENCE_UNAVAILABLE:
            report["evidence_unavailable"].append(rec.accession)
        elif rec.state in INTERRUPTED_STATES:
            report["interrupted"].append(rec.accession)
        elif rec.state is AccessionState.LOCATOR_RESOLVED:
            report["locator_resolved_unspent"].append(rec.accession)
    return report
