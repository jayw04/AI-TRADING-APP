"""Append-only, hash-chained JSONL file -- the pattern of the DISC-MDQ ledger.

``app.research.disc_mdq.ledger`` binds its chain to that program's constants
(program id, attestation, record schema), so it cannot be reused verbatim; this
module is a small self-contained generalisation of the same mechanism and does
not import or modify ``disc_mdq``.

What is defended (threat model T1: a developer acting by accident or casually):

* every write goes through one function that opens the file ``O_APPEND`` and holds an OS
  lock across read -> verify -> build -> append. The lock is taken on the *data file
  itself* (one byte far beyond EOF, so readers are never blocked), so a hardlink or symlink
  alias of the same file shares the lock; it is not keyed on a path string;
* a handle whose in-memory view is stale re-reads the file under the lock. If the file
  still extends the history this handle wrote, the handle adopts it and appends (concurrent
  writers serialise instead of failing); if that history was truncated or replaced the
  append is refused. Anything that depends on the chain contents (a run id, a state
  transition check) is computed by a callback that receives the freshly read records
  *inside* the lock; a per-handle ``threading.Lock`` serialises threads sharing a handle;
* each record carries ``seq``, ``prev_hash`` and ``row_hash`` (sha256 over the canonical
  JSON of everything else); the chain is re-verified on every read. The reader fails closed
  on duplicate JSON keys, blank lines, non-canonical line text and a bad hash; the writer
  refuses a file that does not end in a newline rather than concatenating onto it, and
  loops over short ``os.write`` returns.

Invalid input never reaches the file (round 5, N-C): payloads are checked as plain strict JSON
(finite numbers, string keys, bounded depth and size), serialised with ``allow_nan=False``, and
the exact line is round-tripped through the strict READER before a single byte is written, so a
record the reader would refuse cannot brick the registry; a refusal is a named
``RegistryPayloadError`` and leaves the file byte-identical. ``namespace_lock`` serialises
``enroll_new`` callers per directory (round 5, N-D). ``LOCK_BACKEND`` names the OS primitive
(``msvcrt`` on Windows, ``fcntl`` elsewhere); a test canary asserts it per platform.

What is NOT defended (T2: code execution, or write access to the governed directory):
whoever can rewrite the whole file can recompute every hash; truncating the *tail* leaves
a valid shorter chain (a handle detects this only against the count/head it has itself
seen; ``head_hash`` is surfaced so a caller could anchor it externally -- not implemented,
owner decision pending); a process that does not use this module is not bound by the lock.

Directory links (Level 1 limitation, NOT confinement): chain and namespace paths.
File-level symlink/hardlink aliases of the chain file share one lock. Governance
DIRECTORIES that are symlinks or junctions are FOLLOWED: the chain, namespace lock,
genesis enrolment and token files are written wherever the link points, which may be
OUTSIDE the originally specified filesystem path. The same target is the same identity
(one registry identity, one lock, one chain, one attempt budget), so an alias cannot
create an independent registry identity, reset the attempt budget or reopen an
exhausted holdout. NO directory confinement is provided or claimed. An empty redirected
token directory looks fresh to the token store, but the registry remains the authority
and refuses a second holdout opening. An attacker who controls governance filesystem
paths is Level 2. Contrast PR 2, which refuses symlinked specs and manifests.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.research.range002.governance.errors import (
    ChainNotNewlineTerminatedError,
    RegistryIntegrityError,
    RegistryNamespaceBusyError,
    RegistryPayloadError,
)
from app.research.range002.spec.hashing import CanonicalisationError, loads_strict

LOCK_TIMEOUT_S = 30.0
#: Fixed name of the per-directory governance-namespace lock file used by ``enroll_new``.
NAMESPACE_LOCK_NAME = ".range002-namespace.lock"
GENESIS_HASH = "0" * 64
CHAIN_SCHEMA = 1
#: The byte that is locked: far beyond any real EOF so a Windows mandatory lock never covers
#: bytes a reader needs.
_LOCK_OFFSET = 1 << 40
#: Windows opens in text mode (LF becomes CRLF) unless told otherwise; the chain is bytes.
_BIN = getattr(os, "O_BINARY", 0)

PayloadSource = Mapping[str, Any] | Callable[[tuple["ChainRecord", ...]], Mapping[str, Any]]


@dataclass(frozen=True)
class ChainRecord:
    seq: int
    kind: str
    recorded_at: str
    payload: Mapping[str, Any]
    prev_hash: str
    row_hash: str

    def body(self) -> dict[str, Any]:
        return {
            "schema": CHAIN_SCHEMA,
            "seq": self.seq,
            "kind": self.kind,
            "recorded_at": self.recorded_at,
            "prev_hash": self.prev_hash,
            "payload": dict(self.payload),
        }

    def as_dict(self) -> dict[str, Any]:
        return {**self.body(), "row_hash": self.row_hash}


#: Which OS locking primitive this process uses: ``msvcrt`` on Windows, ``fcntl`` elsewhere. A test
#: canary asserts it per platform, so a wrong backend FAILS (it is never silently skipped).
LOCK_BACKEND: str = "msvcrt" if sys.platform == "win32" else "fcntl"


def _lock_module(name: str) -> Any:
    """The OS locking module, imported lazily by name (tests substitute a fake to exercise the
    other platform's branch; no ``pragma: no cover`` is needed anywhere)."""
    return importlib.import_module(name)


def _try_lock(fd: int) -> bool:
    if LOCK_BACKEND == "msvcrt":
        msvcrt = _lock_module("msvcrt")
        os.lseek(fd, _LOCK_OFFSET, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError:
            return False
        return True
    fcntl = _lock_module("fcntl")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return False
    return True


def _unlock(fd: int) -> None:
    if LOCK_BACKEND == "msvcrt":
        msvcrt = _lock_module("msvcrt")
        os.lseek(fd, _LOCK_OFFSET, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        return
    fcntl = _lock_module("fcntl")
    fcntl.flock(fd, fcntl.LOCK_UN)


@contextmanager
def file_lock(chain_path: Path, timeout: float | None = None) -> Iterator[None]:
    """Exclusive OS lock on the chain's data file; fail closed if it cannot be taken in time.

    The lock lives on the data file's own inode, so every name that reaches the same file
    (hardlink, symlink) contends for the same lock. Creates an empty data file if absent.
    """
    timeout = LOCK_TIMEOUT_S if timeout is None else timeout
    fd = os.open(chain_path, os.O_RDWR | os.O_CREAT | _BIN, 0o644)
    try:
        deadline = time.monotonic() + timeout
        while not _try_lock(fd):
            if time.monotonic() >= deadline:
                raise RegistryIntegrityError(
                    f"could not take the writer lock on {chain_path} within {timeout}s"
                )
            time.sleep(0.005)
        try:
            yield
        finally:
            _unlock(fd)
    finally:
        os.close(fd)


@contextmanager
def namespace_lock(directory: Path, timeout: float | None = None) -> Iterator[None]:
    """OS lock on a fixed namespace file in ``directory`` (N-D: one authoritative registry per
    governance namespace). The file is created exclusively when absent; whoever loses that race
    opens the existing file. The lock is released when the context exits; the (empty) file stays.
    Level 1: it serialises cooperating ``enroll_new`` callers; a process that does not use this
    module is not bound by it."""
    timeout = LOCK_TIMEOUT_S if timeout is None else timeout
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / NAMESPACE_LOCK_NAME
    try:
        fd = os.open(target, os.O_RDWR | os.O_CREAT | os.O_EXCL | _BIN, 0o644)
    except FileExistsError:
        fd = os.open(target, os.O_RDWR | _BIN)
    try:
        deadline = time.monotonic() + timeout
        while not _try_lock(fd):
            if time.monotonic() >= deadline:
                raise RegistryNamespaceBusyError(
                    f"could not take the governance-namespace lock in {directory} within "
                    f"{timeout}s (another enrollment is in progress?)"
                )
            time.sleep(0.005)
        try:
            yield
        finally:
            _unlock(fd)
    finally:
        os.close(fd)


def write_all(fd: int, data: bytes) -> None:
    """``os.write`` until every byte is out; a zero-byte return is an error, not a loop."""
    view = memoryview(data)
    while view:
        written = os.write(fd, bytes(view))
        if written <= 0:
            raise RegistryIntegrityError("short write: os.write accepted no bytes")
        view = view[written:]


#: A single chain line larger than this is refused before it is written (bounded input).
MAX_RECORD_BYTES = 1 << 20
_MAX_DEPTH = 32


def _assert_plain_json(value: Any, path: str = "$", depth: int = 0) -> None:
    """Refuse anything that is not plain strict JSON: non-finite floats, non-string keys, odd
    types. ``bool`` is a distinct type from ``int`` here only in that both are plain JSON."""
    if depth > _MAX_DEPTH:
        raise RegistryPayloadError(f"{path}: nesting deeper than {_MAX_DEPTH}")
    if value is None or isinstance(value, bool | str):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise RegistryPayloadError(f"{path}: non-finite number {value!r} cannot be recorded")
        return
    if isinstance(value, Mapping):
        for k, v in value.items():
            if not isinstance(k, str):
                raise RegistryPayloadError(f"{path}: non-string key {k!r}")
            _assert_plain_json(v, f"{path}.{k}", depth + 1)
        return
    if isinstance(value, list | tuple):
        for i, v in enumerate(value):
            _assert_plain_json(v, f"{path}[{i}]", depth + 1)
        return
    raise RegistryPayloadError(f"{path}: unsupported type {type(value).__name__}")


def _canonical(body: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
            "utf-8"
        )
    except (ValueError, TypeError, RecursionError) as exc:
        raise RegistryPayloadError(f"record is not strict canonical JSON: {exc}") from exc


def _row_hash(body: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(body)).hexdigest()


def _line(record_dict: Mapping[str, Any]) -> str:
    try:
        return json.dumps(record_dict, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (ValueError, TypeError, RecursionError) as exc:
        raise RegistryPayloadError(f"record is not strict canonical JSON: {exc}") from exc


TORN_TAIL_NOTE = "fail closed; owner-authorized recovery procedure required (not implemented)"


def read_chain(path: Path) -> tuple[ChainRecord, ...]:
    """Parse and verify every record; any defect raises (fail closed).

    A defect in a file that does not end in a newline may be a torn tail (a crashed append).
    The error says so; there is NO repair path -- recovery needs an owner-authorized procedure
    that is not implemented.
    """
    try:
        return _read_chain(path)
    except RegistryIntegrityError as exc:
        if path.is_file() and not path.read_bytes().endswith(b"\n") and path.stat().st_size > 0:
            raise RegistryIntegrityError(
                f"{exc} (the file does not end in a newline -- a torn tail?): {TORN_TAIL_NOTE}"
            ) from exc
        raise


def _read_chain(path: Path) -> tuple[ChainRecord, ...]:
    """Parse and verify every record; any defect raises (fail closed)."""
    if not path.exists():
        return ()
    try:
        text = path.read_bytes().decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RegistryIntegrityError(f"{path} is not valid UTF-8: {exc}") from exc
    lines = text.split("\n")  # only "\n" separates records; no other character does
    if lines and lines[-1] == "":
        lines.pop()  # the newline after the final record
    records: list[ChainRecord] = []
    prev = GENESIS_HASH
    for lineno, raw in enumerate(lines, start=1):
        if not raw.strip():
            raise RegistryIntegrityError(
                f"{path}:{lineno} is a blank line inside the chain -- the file was edited"
            )
        try:
            data = loads_strict(raw)
        except CanonicalisationError as exc:
            raise RegistryIntegrityError(
                f"{path}:{lineno} is not valid strict JSON (duplicate keys, NaN and bad "
                f"syntax are refused): {exc}"
            ) from exc
        if not isinstance(data, dict):
            raise RegistryIntegrityError(f"{path}:{lineno} is not a record object")
        if raw != _line(data):
            raise RegistryIntegrityError(
                f"{path}:{lineno} is not in canonical form -- the line text was edited"
            )
        if data.get("schema") != CHAIN_SCHEMA:
            raise RegistryIntegrityError(
                f"{path}:{lineno} has schema {data.get('schema')!r}; expected {CHAIN_SCHEMA}"
            )
        expected_seq = len(records) + 1
        if data.get("seq") != expected_seq:
            raise RegistryIntegrityError(
                f"{path}:{lineno} has seq {data.get('seq')!r}, expected {expected_seq} "
                "-- a record was inserted or removed"
            )
        if data.get("prev_hash") != prev:
            raise RegistryIntegrityError(
                f"{path}:{lineno} chains to {data.get('prev_hash')!r}, expected {prev!r}"
            )
        stated = data.get("row_hash")
        body = {k: v for k, v in data.items() if k != "row_hash"}
        if stated != _row_hash(body):
            raise RegistryIntegrityError(
                f"{path}:{lineno} row_hash does not match its contents -- "
                "the record was edited after it was written"
            )
        kind = data.get("kind")
        payload = data.get("payload")
        if not isinstance(kind, str) or not isinstance(payload, dict):
            raise RegistryIntegrityError(f"{path}:{lineno} has a malformed kind/payload")
        records.append(
            ChainRecord(
                seq=expected_seq,
                kind=kind,
                recorded_at=str(data.get("recorded_at")),
                payload=payload,
                prev_hash=prev,
                row_hash=str(stated),
            )
        )
        prev = str(stated)
    return tuple(records)


def _verify_line_round_trips(line: str, record: ChainRecord) -> None:
    if len(line.encode("utf-8")) > MAX_RECORD_BYTES:
        raise RegistryPayloadError(f"record exceeds {MAX_RECORD_BYTES} bytes")
    try:
        parsed = loads_strict(line.rstrip("\n"))
    except CanonicalisationError as exc:
        raise RegistryPayloadError(f"record does not survive the strict reader: {exc}") from exc
    if (
        not isinstance(parsed, dict)
        or _line(parsed) != line.rstrip("\n")
        or parsed.get("row_hash") != _row_hash({k: v for k, v in parsed.items() if k != "row_hash"})
        or parsed.get("row_hash") != record.row_hash
    ):
        raise RegistryPayloadError("record does not round-trip through the strict reader")


class HashChainFile:
    """A handle on one chain file. Appends only; never rewrites."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._mutex = threading.Lock()  # serialises threads that share this handle
        records = read_chain(self._path)  # raises on a broken chain
        self._count = len(records)
        self._head = records[-1].row_hash if records else GENESIS_HASH

    @property
    def path(self) -> Path:
        return self._path

    @property
    def head_hash(self) -> str:
        return self._head

    @property
    def count(self) -> int:
        return self._count

    def _check_not_rolled_back(self, records: tuple[ChainRecord, ...]) -> None:
        count, head = self._count, self._head
        if len(records) < count or (count > 0 and records[count - 1].row_hash != head):
            raise RegistryIntegrityError(
                f"{self._path} no longer contains the history this handle wrote "
                "(truncated or replaced)"
            )

    def records(self) -> tuple[ChainRecord, ...]:
        """Chain-verified records; also checks this handle has not been rolled back."""
        records = read_chain(self._path)
        self._check_not_rolled_back(records)
        return records

    def append(
        self, kind: str, payload: PayloadSource, *, now: datetime | None = None
    ) -> ChainRecord:
        """Append one record.

        ``payload`` is a mapping, or a callable receiving the chain's records as read *under
        the writer lock* and returning the mapping (it may raise to veto the append). Use the
        callable form for anything derived from the chain (ids, state-transition checks).
        """
        with self._mutex, file_lock(self._path):
            return self._append_locked(kind, payload, now)

    def _append_locked(
        self, kind: str, payload: PayloadSource, now: datetime | None
    ) -> ChainRecord:
        # Re-read under the lock: a stale view is adopted if the file still extends the
        # history this handle wrote; a truncated or replaced history is refused.
        records = self.records()
        if records:
            self._count, self._head = len(records), records[-1].row_hash
        else:
            self._count, self._head = 0, GENESIS_HASH
        data = payload(records) if callable(payload) else payload
        _assert_plain_json(data)
        ts = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
        draft = ChainRecord(
            seq=self._count + 1,
            kind=kind,
            recorded_at=ts,
            payload=dict(data),
            prev_hash=self._head,
            row_hash="",
        )
        record = ChainRecord(
            seq=draft.seq,
            kind=draft.kind,
            recorded_at=draft.recorded_at,
            payload=draft.payload,
            prev_hash=draft.prev_hash,
            row_hash=_row_hash(draft.body()),
        )
        # N-C: build the exact line and round-trip it through the strict READER before any byte is
        # written, so a record the reader would refuse can never reach the file (which would
        # otherwise brick the registry).
        line = _line(record.as_dict()) + "\n"
        _verify_line_round_trips(line, record)
        fd = os.open(self._path, os.O_RDWR | os.O_CREAT | os.O_APPEND | _BIN, 0o644)
        try:
            size = os.lseek(fd, 0, os.SEEK_END)
            if size > 0:
                os.lseek(fd, size - 1, os.SEEK_SET)
                if os.read(fd, 1) != b"\n":
                    raise ChainNotNewlineTerminatedError(
                        f"{self._path} does not end in a newline; refusing to append onto a "
                        f"partial last line (the file was edited or a write was torn): "
                        f"{TORN_TAIL_NOTE}"
                    )
            write_all(fd, (_line(record.as_dict()) + "\n").encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        self._head = record.row_hash
        self._count = record.seq
        return record
