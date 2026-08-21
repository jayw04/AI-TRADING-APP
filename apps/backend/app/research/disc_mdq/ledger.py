"""DISC-MDQ-001 discovery ledger — the append-only record of what was examined.

Plan v0.13 section 4.10.7 (owner ruling, 2026-08-20 PM) fixes what "done" means
for this component, because "the ledger was built" and "the ledger is actually
gating the first read" are two different claims and they drift apart quietly:

    CEE may be the first exploratory consumer, but the discovery ledger must be
    OPERATIONAL before CEE opens its first governed partition. A ledger that
    exists but is not gating is not a ledger; it is a file.

The twelve-item acceptance gate, and where each item lives:

1.  append-only — every write goes through ``_append``, which opens the file
    with ``os.O_APPEND``: the kernel refuses to write anywhere but the end,
    whatever the caller intends.
2.  no overwrite and no delete path exists — there is no method that truncates
    or unlinks; ``LEDGER_PUBLIC_API`` pins the public surface and a test
    asserts it, so adding one fails a test rather than passing review.
3.  timestamp — ``recorded_at``, UTC and explicit.
4.  authorized scope — ``payload.scope``: the full allow-set, its fingerprint,
    the governed window, and the artifact identities in force.
5.  corpus / partition identity — ``payload.partitions``: feed, session date and
    manifest sha256. A condition record without one is REFUSED.
6.  code / version identity — ``payload.code`` (:class:`CodeIdentity`).
7.  condition / feature definition — ``payload.condition``; refused if empty.
8.  disposition / result — ``payload.disposition``; refused if empty.
9.  denial information — ``payload.scope.denials``: FULL detail from
    ``AuthorizedScope.denials``, every symbol/date and its reason, never a
    count.
10. the first exploratory read is IMPOSSIBLE unless ledger initialisation
    SUCCEEDS — :class:`MdqFeatureReader` cannot be constructed without a
    :class:`DiscoveryLedger`, and a :class:`DiscoveryLedger` cannot exist except
    as the return value of :meth:`DiscoveryLedger.open`.
11. the holdout artifact AND the universe pin both load and verify BEFORE the
    reader opens a partition — :meth:`DiscoveryLedger.open` demands a
    *verified* :class:`ArtifactAttestation`, and the reader cross-checks the
    scope's own quarantine identity against it.
12. initialisation failure is FAIL-CLOSED — every failure path raises
    :class:`LedgerInitError`. There is no warn-and-continue branch.

Items 1-9 describe a record. Items 10-12 are what make it a control. The Phase-A
reader already proves the pattern — it cannot be constructed without an
``AuthorizedScope`` — and the ledger binds the same way: authorisation answers
*may these bytes be observed?*, the ledger answers *what was examined, on which
governed corpus, under which code and scope, and with what disposition?* Both
are required at the first read, and neither is optional.

Records are hash-chained in the same spirit as the platform's audit log
(P5 section 8): each carries ``prev_hash`` and ``row_hash``, so a record cannot
be edited or removed after the fact without breaking every record after it. The
chain is re-verified on every ``open()``; a break is fatal, not a warning.

Research/Analytics plane (ADR 0051): no order-path import, no broker
capability, no LLM.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import structlog

from app.research.disc_mdq.policy import ArtifactAttestation, AuthorizedScope
from app.research.disc_mdq.spec import (
    ENRICHES_SCREEN_ID,
    ENRICHES_SCREEN_VERSION,
    HOLDOUT_SYMBOLS_SHA256,
    LEDGER_GENESIS_HASH,
    LEDGER_RECORD_SCHEMA,
    LEDGER_VERSION,
    POLICY_VERSION,
    PROGRAM_ID,
    READER_VERSION,
    UNIVERSE_SYMBOLS_SHA256,
)

logger = structlog.get_logger(__name__)


class LedgerError(RuntimeError):
    """Base class for discovery-ledger failures."""


class LedgerInitError(LedgerError):
    """Initialisation failed. Nothing may be explored — item 12, fail-closed."""


class LedgerIntegrityError(LedgerError):
    """The on-disk chain does not verify: a record was edited or removed."""


class LedgerRecordError(LedgerError):
    """A record was offered without one of the fields 4.10.7 requires."""


class LedgerEvent(StrEnum):
    """What a record describes.

    ``CONDITION_EXAMINED`` is the record the acceptance gate is written about —
    one per condition/feature examined. The other two exist because a condition
    is examined *on* something: ``LEDGER_OPENED`` fixes the artifacts, code and
    scope in force, and ``PARTITION_READ`` fixes the corpus identity actually
    opened. Each is written before the bytes it describes reach a caller.
    """

    LEDGER_OPENED = "ledger_opened"
    PARTITION_READ = "partition_read"
    CONDITION_EXAMINED = "condition_examined"


@dataclass(frozen=True)
class CodeIdentity:
    """Which code examined the condition — acceptance item 6.

    ``source_sha`` is the deployed source revision when one is knowable. On the
    box that is ``/opt/workbench/app/.deploy_src_sha``, surfaced to the process
    as ``WORKBENCH_DEPLOY_SRC_SHA``; it is read from the environment rather than
    from a hardcoded path, so a research process that genuinely does not know
    its revision records ``None`` instead of a guess.
    """

    program_id: str = PROGRAM_ID
    policy_version: str = POLICY_VERSION
    reader_version: str = READER_VERSION
    ledger_version: str = LEDGER_VERSION
    enriches_screen_id: str = ENRICHES_SCREEN_ID
    enriches_screen_version: str = ENRICHES_SCREEN_VERSION
    source_sha: str | None = None

    @classmethod
    def current(cls, source_sha: str | None = None) -> CodeIdentity:
        return cls(source_sha=source_sha or os.environ.get("WORKBENCH_DEPLOY_SRC_SHA") or None)

    def as_dict(self) -> dict[str, Any]:
        return {
            "program_id": self.program_id,
            "policy_version": self.policy_version,
            "reader_version": self.reader_version,
            "ledger_version": self.ledger_version,
            "enriches_screen_id": self.enriches_screen_id,
            "enriches_screen_version": self.enriches_screen_version,
            "source_sha": self.source_sha,
        }


@dataclass(frozen=True)
class LedgerRecord:
    """One verified line of the ledger."""

    seq: int
    event: LedgerEvent
    recorded_at: str
    payload: Mapping[str, Any]
    prev_hash: str
    row_hash: str
    schema: int = LEDGER_RECORD_SCHEMA
    program_id: str = PROGRAM_ID
    ledger_version: str = LEDGER_VERSION

    @property
    def entry_ref(self) -> str:
        """The citation a later pre-registration quotes (section 4.10.2)."""
        return f"{self.program_id}#{self.seq}:{self.row_hash[:16]}"

    def body(self) -> dict[str, Any]:
        """The hashed part of the record — everything except ``row_hash``."""
        return {
            "schema": self.schema,
            "seq": self.seq,
            "event": self.event.value,
            "recorded_at": self.recorded_at,
            "program_id": self.program_id,
            "ledger_version": self.ledger_version,
            "prev_hash": self.prev_hash,
            "payload": dict(self.payload),
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self.body(), "row_hash": self.row_hash}


#: The complete public surface of :class:`DiscoveryLedger`. Pinned so that
#: adding a mutation path (``delete``, ``rewrite``, ``compact``, ``prune``, ...)
#: fails a test rather than passing review — acceptance item 2.
LEDGER_PUBLIC_API = frozenset(
    {
        "open",
        "path",
        "attestation",
        "code_identity",
        "head_hash",
        "count",
        "records",
        "verify",
        "record_partition_read",
        "record_condition",
    }
)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime | date):
        return value.isoformat()
    raise TypeError(
        f"ledger payloads must be JSON-serialisable; got {type(value).__name__}. "
        "Serialise it explicitly rather than letting the ledger guess."
    )


def _canonical(body: Mapping[str, Any]) -> bytes:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=_json_default).encode(
        "utf-8"
    )


def _row_hash(body: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(body)).hexdigest()


def scope_payload(scope: AuthorizedScope) -> dict[str, Any]:
    """Acceptance items 4 and 9 — the allow-set AND every denial, in full.

    ``denials`` keeps symbol, date and reason for each denied pair rather than a
    count. A program that silently drops names cannot afterwards show it
    honoured the quarantine, which is the whole reason
    ``AuthorizedScope.denials`` retains full detail.
    """
    return {
        "purpose": scope.purpose.value,
        "policy_version": scope.policy_version,
        "fingerprint": scope.fingerprint(),
        "window": {
            "d0": scope.window.d0.isoformat(),
            "end_exclusive": scope.window.end_exclusive.isoformat(),
            "period_holdout_start": scope.window.holdout_start.isoformat(),
            "period_holdout_end_exclusive": scope.window.holdout_end_exclusive.isoformat(),
        },
        "universe_sha256": scope.universe_sha256,
        "holdout_sha256": scope.holdout_sha256,
        "holdout_symbols_sha256": scope.holdout_symbols_sha256,
        "authorized_pair_count": len(scope.pairs),
        "authorized_pairs": sorted(f"{s}|{d.isoformat()}" for s, d in scope.pairs),
        "denials": {
            "total": len(scope.denials),
            "counts": scope.denials_by_decision(),
            "detail": sorted(
                f"{d.symbol}|{d.session_date.isoformat()}|{d.decision.value}" for d in scope.denials
            ),
        },
    }


def _partition_payload(partition: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalise one corpus identity — acceptance item 5."""
    required = ("feed", "session_date", "manifest_sha256")
    missing = [k for k in required if not partition.get(k)]
    if missing:
        raise LedgerRecordError(
            f"partition identity is missing {missing}; a condition examined on an "
            "unidentified corpus is not a ledger entry. Pass "
            "PartitionProvenance.as_dict()."
        )
    return dict(partition)


class DiscoveryLedger:
    """Append-only, hash-chained record of every condition examined.

    Construct it with :meth:`open`. There is no other way — ``__init__`` refuses
    a caller that did not come through it, which is what makes acceptance item
    10 ("the first exploratory read is IMPOSSIBLE unless ledger initialisation
    succeeds") a structural property of the reader's signature rather than a
    rule someone has to remember.
    """

    _OPEN_TOKEN = object()

    def __init__(
        self,
        token: object,
        *,
        path: Path,
        attestation: ArtifactAttestation,
        code_identity: CodeIdentity,
        head_hash: str,
        count: int,
    ) -> None:
        if token is not DiscoveryLedger._OPEN_TOKEN:
            raise LedgerInitError(
                "DiscoveryLedger must be created with DiscoveryLedger.open(); direct "
                "construction would skip artifact verification and chain verification"
            )
        self._path = path
        self._attestation = attestation
        self._code_identity = code_identity
        self._head_hash = head_hash
        self._count = count

    # --- initialisation -----------------------------------------------------

    @classmethod
    def open(
        cls,
        path: Path,
        *,
        attestation: ArtifactAttestation,
        code_identity: CodeIdentity | None = None,
        now: datetime | None = None,
        note: str | None = None,
    ) -> DiscoveryLedger:
        """Initialise the ledger. Every failure raises — item 12.

        Order matters: the artifacts are verified, then the existing chain is
        verified, then the opening record is appended. Only when all three
        succeed does a ledger object exist, and only then can a reader be
        constructed.
        """
        if not isinstance(attestation, ArtifactAttestation) or not attestation.verified:
            raise LedgerInitError(
                "discovery ledger requires a VERIFIED ArtifactAttestation from "
                "policy.verify_governed_artifacts(); the holdout artifact and the "
                "universe pin must both load and verify before any partition is opened"
            )
        # Cheap, and it means a hand-built attestation cannot smuggle the wrong
        # pins past the ledger even if it sets verified=True.
        if attestation.universe_sha256 != UNIVERSE_SYMBOLS_SHA256:
            raise LedgerInitError(
                f"attested universe {attestation.universe_sha256} is not the pinned "
                f"Phase-A universe {UNIVERSE_SYMBOLS_SHA256}"
            )
        if attestation.holdout_symbols_sha256 != HOLDOUT_SYMBOLS_SHA256:
            raise LedgerInitError(
                f"attested quarantine {attestation.holdout_symbols_sha256} is not the "
                f"pinned holdout symbol set {HOLDOUT_SYMBOLS_SHA256}"
            )

        path = Path(path)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise LedgerInitError(f"cannot create ledger directory {path.parent}: {exc}") from exc

        try:
            records = _read_chain(path)
        except LedgerIntegrityError as exc:
            raise LedgerInitError(
                f"existing ledger at {path} does not verify: {exc}. Refusing to explore "
                "against a ledger whose history cannot be trusted."
            ) from exc
        except OSError as exc:
            raise LedgerInitError(f"cannot read ledger at {path}: {exc}") from exc

        identity = code_identity or CodeIdentity.current()
        ledger = cls(
            cls._OPEN_TOKEN,
            path=path,
            attestation=attestation,
            code_identity=identity,
            head_hash=records[-1].row_hash if records else LEDGER_GENESIS_HASH,
            count=len(records),
        )

        payload: dict[str, Any] = {
            "artifacts": attestation.as_dict(),
            "code": identity.as_dict(),
            "existing_records": len(records),
        }
        if note:
            payload["note"] = note
        try:
            record = ledger._append(LedgerEvent.LEDGER_OPENED, payload, now=now)
        except OSError as exc:
            raise LedgerInitError(
                f"cannot append to ledger {path}: {exc}. An unwritable ledger is a "
                "closed gate, not a warning."
            ) from exc

        logger.info(
            "mdq_discovery_ledger_opened",
            path=str(path),
            seq=record.seq,
            entry_ref=record.entry_ref,
            existing_records=len(records),
            universe_sha256=attestation.universe_sha256,
            holdout_symbols_sha256=attestation.holdout_symbols_sha256,
            period_holdout_provenance=attestation.period_holdout_provenance,
        )
        return ledger

    # --- read-side ----------------------------------------------------------

    @property
    def path(self) -> Path:
        return self._path

    @property
    def attestation(self) -> ArtifactAttestation:
        return self._attestation

    @property
    def code_identity(self) -> CodeIdentity:
        return self._code_identity

    @property
    def head_hash(self) -> str:
        return self._head_hash

    @property
    def count(self) -> int:
        return self._count

    def records(self) -> tuple[LedgerRecord, ...]:
        """Every record, chain-verified. Raises if the chain is broken."""
        return _read_chain(self._path)

    def verify(self) -> tuple[LedgerRecord, ...]:
        """Re-verify the chain, and that it still ends where this handle thinks.

        Catches the case that matters operationally: the file replaced wholesale
        with a shorter, internally consistent one.
        """
        records = self.records()
        if len(records) != self._count:
            raise LedgerIntegrityError(
                f"ledger {self._path} holds {len(records)} records, this handle has "
                f"written up to {self._count}"
            )
        if records and records[-1].row_hash != self._head_hash:
            raise LedgerIntegrityError(
                f"ledger head {records[-1].row_hash} does not match this handle's head "
                f"{self._head_hash}"
            )
        return records

    # --- write-side (append only) -------------------------------------------

    def record_partition_read(
        self,
        *,
        feed: str,
        session_date: date,
        scope: AuthorizedScope,
        partition: Mapping[str, Any],
        now: datetime | None = None,
    ) -> LedgerRecord:
        """Record that a governed partition was opened under this scope.

        Written by the reader *before* it parses a single row, so there is no
        ordering in which bytes have been examined and the ledger does not yet
        say so. That is why it carries no row counts: they do not exist yet, and
        an append-only ledger cannot go back and fill them in. What was actually
        computed from the partition belongs on the ``CONDITION_EXAMINED``
        record, which cites this one by ``entry_ref``.
        """
        payload = {
            "feed": feed,
            "session_date": session_date.isoformat(),
            "authorized_symbols": sorted(scope.symbols_for(session_date)),
            "scope": scope_payload(scope),
            "partitions": [_partition_payload(partition)],
            "code": self._code_identity.as_dict(),
        }
        return self._append(LedgerEvent.PARTITION_READ, payload, now=now)

    def record_condition(
        self,
        *,
        condition_id: str,
        family: str,
        definition: Mapping[str, Any],
        scope: AuthorizedScope,
        partitions: Sequence[Mapping[str, Any]],
        disposition: str,
        result: Mapping[str, Any] | None = None,
        note: str | None = None,
        now: datetime | None = None,
    ) -> LedgerRecord:
        """Record one condition/feature examined — the 4.10.7 record.

        Every acceptance item 3-9 field is required. A missing one raises
        :class:`LedgerRecordError`: a half-filled entry would let a later
        pre-registration cite a ledger reference that does not actually say what
        was examined, on which corpus, or how it came out.
        """
        if not condition_id or not condition_id.strip():
            raise LedgerRecordError("condition_id is required")
        if not family or not family.strip():
            raise LedgerRecordError("family is required (which hypothesis family was mined)")
        if not definition:
            raise LedgerRecordError(
                "definition is required — acceptance item 7. Record what was actually "
                "computed, not just its name."
            )
        if not disposition or not str(disposition).strip():
            raise LedgerRecordError(
                "disposition is required — acceptance item 8. 'inconclusive' and "
                "'abandoned' are dispositions; silence is not."
            )
        if not partitions:
            raise LedgerRecordError(
                "at least one partition identity is required — acceptance item 5"
            )

        payload: dict[str, Any] = {
            "condition_id": condition_id,
            "family": family,
            "condition": dict(definition),
            "scope": scope_payload(scope),
            "partitions": [_partition_payload(p) for p in partitions],
            "code": self._code_identity.as_dict(),
            "disposition": str(disposition),
            "result": dict(result) if result else None,
        }
        if note:
            payload["note"] = note

        record = self._append(LedgerEvent.CONDITION_EXAMINED, payload, now=now)
        logger.info(
            "mdq_condition_examined",
            condition_id=condition_id,
            family=family,
            disposition=str(disposition),
            entry_ref=record.entry_ref,
            partitions=len(payload["partitions"]),
            denials=len(scope.denials),
        )
        return record

    # --- the only writer ----------------------------------------------------

    def _append(
        self,
        event: LedgerEvent,
        payload: Mapping[str, Any],
        *,
        now: datetime | None = None,
    ) -> LedgerRecord:
        """The single write path.

        ``os.O_APPEND`` makes it append-only at the kernel rather than by
        convention — acceptance items 1 and 2.
        """
        ts = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
        draft = LedgerRecord(
            seq=self._count + 1,
            event=event,
            recorded_at=ts,
            payload=dict(payload),
            prev_hash=self._head_hash,
            row_hash="",
        )
        record = LedgerRecord(
            seq=draft.seq,
            event=draft.event,
            recorded_at=draft.recorded_at,
            payload=draft.payload,
            prev_hash=draft.prev_hash,
            row_hash=_row_hash(draft.body()),
        )

        line = json.dumps(
            record.as_dict(), sort_keys=True, separators=(",", ":"), default=_json_default
        )
        fd = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, (line + "\n").encode("utf-8"))
        finally:
            os.close(fd)

        self._head_hash = record.row_hash
        self._count = record.seq
        return record


def _read_chain(path: Path) -> tuple[LedgerRecord, ...]:
    """Parse and verify every record in a ledger file.

    Fail-closed by design: a torn or edited line breaks the chain and raises,
    rather than being skipped the way the corpus reader tolerates a torn final
    JSONL line. The corpus is data being observed; the ledger is the record that
    the observation happened, and a record with a hole in it proves nothing.
    """
    if not path.exists():
        return ()

    records: list[LedgerRecord] = []
    prev = LEDGER_GENESIS_HASH
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LedgerIntegrityError(f"{path}:{lineno} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise LedgerIntegrityError(f"{path}:{lineno} is not a record object")

        schema = data.get("schema")
        if schema != LEDGER_RECORD_SCHEMA:
            raise LedgerIntegrityError(
                f"{path}:{lineno} has record schema {schema!r}; this build understands "
                f"{LEDGER_RECORD_SCHEMA}. Refusing to interpret a shape it does not know."
            )
        try:
            event = LedgerEvent(data["event"])
        except (KeyError, ValueError) as exc:
            raise LedgerIntegrityError(
                f"{path}:{lineno} has unknown event {data.get('event')!r}"
            ) from exc

        expected_seq = len(records) + 1
        if data.get("seq") != expected_seq:
            raise LedgerIntegrityError(
                f"{path}:{lineno} has seq {data.get('seq')!r}, expected {expected_seq} — a "
                "record was inserted or removed"
            )
        if data.get("prev_hash") != prev:
            raise LedgerIntegrityError(
                f"{path}:{lineno} chains to {data.get('prev_hash')!r}, expected {prev!r}"
            )

        stated = data.get("row_hash")
        body = {k: v for k, v in data.items() if k != "row_hash"}
        recomputed = _row_hash(body)
        if stated != recomputed:
            raise LedgerIntegrityError(
                f"{path}:{lineno} row_hash {stated!r} does not match its contents "
                f"({recomputed}) — the record was edited after it was written"
            )

        records.append(
            LedgerRecord(
                seq=expected_seq,
                event=event,
                recorded_at=str(data.get("recorded_at")),
                payload=data.get("payload") or {},
                prev_hash=prev,
                row_hash=str(stated),
                schema=schema,
                program_id=str(data.get("program_id")),
                ledger_version=str(data.get("ledger_version")),
            )
        )
        prev = str(stated)

    return tuple(records)


def conditions_examined(
    records: Iterable[LedgerRecord], family: str | None = None
) -> tuple[LedgerRecord, ...]:
    """Conditions examined, optionally within one family.

    Section 4.10.2 requires a later pre-registration to cite its ledger entry
    **and the number of conditions examined in that family** — that count is the
    multiple-comparisons denominator, so it has to be derivable from the ledger
    rather than remembered.
    """
    out = [r for r in records if r.event is LedgerEvent.CONDITION_EXAMINED]
    if family is not None:
        out = [r for r in out if r.payload.get("family") == family]
    return tuple(out)
