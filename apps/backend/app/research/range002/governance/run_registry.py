"""Hash-chained, append-only run registry (WP0.7, R8, plan section 6).

Protocol: ``open_run`` writes the row *before* any compute; ``close_run``
records the final status and audit-pack hash. A crash between the two leaves
the run ``OPEN`` on disk; ``abort_open_runs`` then appends an ``ABORTED`` close
row. Aborted, failed and defect runs all stay in the ledger and all count: the
registry has no delete path, and ``count_runs`` includes every row.

Built on :mod:`hashchain` (the DISC-MDQ ledger pattern, self-contained).
Nothing here chooses a ``P0:`` value: every field below is supplied by the
caller from the frozen spec.

Concurrency: every write computes what depends on the chain (the run id, the "is this run
still OPEN" check, the holdout-window conflict check) inside a callback that runs under the
chain's writer lock on the freshly read records, so two handles or threads cannot allocate
the same run id or both close the same run. ``_fold`` additionally refuses a chain that
somehow holds a duplicate ``run_opened`` run id.

Trust boundary (threat model T1, a developer acting by accident or casually): the registry
API is trusted. ``audit_pack_sha256`` is only *format*-checked (64 lowercase hex); nothing here
opens, hashes or verifies an audit pack, so a caller can record any digest. ``COMPLETED``
records that the caller says the run finished -- not that its result was a PASS. Whoever can
rewrite the chain file wholesale, or call into this module with forged inputs, is outside the
threat model (T2).

NOT defended (Level 2, stated plainly): a copied or forged registry -- including one that carries
the PUBLIC owner-approved genesis id (the id is in git, so it stops accidents, not forgery);
truncating the tail to a valid shorter chain; editing the files, directories or the governance
manifest on disk; and any in-process code execution. Attempt budgets are counted per (registry
genesis = research lineage, phase) across all windows and spec hashes; a new budget would need
an independently approved registration, an exposure review and a documented justification, which
is design-only and not implemented here.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, final

from app.research.range002.governance.errors import (
    AttemptLimitExceededError,
    AttemptLimitNotSetError,
    CapabilityAlreadyIssuedError,
    CapabilityNotIssuedError,
    EnrolledByTooLongError,
    EvidenceReuseError,
    HoldoutAlreadyOpenedError,
    RegistryEnrollmentError,
    RegistryIntegrityError,
    RegistryNotEnrolledError,
    RegistryRecordError,
    RunNotRegisteredError,
)
from app.research.range002.governance.hashchain import (
    MAX_RECORD_BYTES,
    ChainRecord,
    HashChainFile,
    namespace_lock,
)
from app.research.range002.governance.model import (
    MAX_ATTEMPT_LIMIT,
    PHASE_PARTITIONS,
    DateRange,
    Partition,
    Phase,
)
from app.research.range002.spec.genesis import is_canonical_uuid4, new_genesis_id
from app.research.range002.spec.hashing import CanonicalisationError, content_sha256

_HEX = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^range002-run-\d{6,12}$")
MAX_SEED_ABS = 2**63 - 1
MAX_EVIDENCE_ITEMS = 16
MAX_EXIT_CANDIDATES = 64
MAX_SELECTION_RECORD_BYTES = 1 << 19

KIND_GENESIS = "registry_genesis"
KIND_OPENED = "run_opened"
KIND_CLOSED = "run_closed"
KIND_SELECTION = "selection_record"
KIND_HOLDOUT_AUTH = "holdout_authorized"
KIND_CAPABILITY = "capability_issued"

#: Identifies a RANGE-002 registry file; ``enroll_new`` refuses a directory that already holds one.
REGISTRY_MARKER = "range002-run-registry"
#: Longest ``enrolled_by`` (after stripping) ``enroll_new`` accepts.
MAX_ENROLLED_BY_CHARS = 256

#: Public surface -- pinned by a test so a mutation path cannot slip in.
REGISTRY_PUBLIC_API = frozenset(
    {
        "path",
        "head_hash",
        "genesis_id",
        "enrollment",
        "enroll_new",
        "count_records",
        "records",
        "runs",
        "get_run",
        "count_runs",
        "open_run",
        "close_run",
        "abort_open_runs",
        "record_selection",
        "find_open_run",
        "mark_holdout_authorized",
        "mark_capability_issued",
        "attempts_consumed",
    }
)


def _new_genesis_id() -> str:
    """A fresh registry genesis id: ``uuid.uuid4()`` text (CSPRNG-backed), canonical lowercase.

    An identity marker for the research lineage, NOT authentication."""
    return new_genesis_id()


class RunStatus(StrEnum):
    OPEN = "OPEN"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    DEFECT = "DEFECT"
    ABORTED = "ABORTED"


_CLOSE_STATUSES = frozenset(
    {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.DEFECT, RunStatus.ABORTED}
)


@dataclass(frozen=True)
class RunState:
    run_id: str
    phase: Phase
    partition: Partition
    spec_sha256: str
    code_sha: str
    data_manifest_sha256: str
    seeds: Mapping[str, int]
    exit_candidates: tuple[str, ...]
    status: RunStatus
    audit_pack_sha256: str | None
    opened_seq: int
    selection_record_seq: int | None
    holdout_authorized_seq: int | None = None
    #: The holdout window this run was opened for. ``None`` for every non-HOLDOUT run. A HOLDOUT
    #: row with no recorded window can only be a legacy row (``open_run`` now requires the
    #: window); it counts as overlapping *every* window ONLY WHEN it blocks at all, i.e. when it
    #: carries a ``holdout_authorized`` mark or is COMPLETED (see :func:`holdout_conflict`). A
    #: legacy OPEN/FAILED/ABORTED/DEFECT row with no window and no mark blocks nothing.
    holdout_range: DateRange | None = None
    #: canonical-JSON sha256 of the SelectionRecord body (None on a legacy row: unverifiable).
    selection_record_sha256: str | None = None
    #: seq of the first ``capability_issued`` row (written by ``authorize`` before it returns a
    #: capability); ``None`` if the guard never authorized this run.
    capability_issued_seq: int | None = None
    #: The protected development window a P3A / P3B run was opened for (``None`` for every other
    #: phase and for a legacy row written before the window was recorded). RECORDED for audit and
    #: exposure review only: it does NOT partition the attempt budget, which is counted per
    #: (registry genesis, phase) across ALL windows and spec hashes (NF7).
    protected_range: DateRange | None = None


def _require_hex(value: object, name: str, pattern: re.Pattern[str] = _HEX) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise RegistryRecordError(f"{name} must be a lowercase hex digest, got {value!r}")
    return value


def holdout_conflict(runs: Sequence[RunState], run: RunState) -> RunState | None:
    """The first OTHER HOLDOUT run that blocks ``run`` from opening the holdout, or ``None``.

    A HOLDOUT run counts as having opened the window when its authorization was *issued*
    (``holdout_authorized_seq`` set -- the registry row ``authorize`` writes before it touches
    the token). That includes a run that crashed or failed after the mark, whatever its status:
    once authorization is issued, or the access state is uncertain, the window stays consumed --
    there is no automatic restoration, no token reissue and no reset (a recovery workflow is
    design-only, owner approval pending). A HOLDOUT request rejected *before* the mark, and
    closed FAILED or ABORTED, is recorded in the registry but does not block anything.

    Legacy rows (a HOLDOUT ``run_opened`` written before the window was recorded) fail closed,
    stricter than the mark alone: a HOLDOUT row with NO recorded window blocks EVERY window when
    it carries an authorization mark OR its status is COMPLETED (a completed holdout run with an
    unknown window may have opened any of it). A windowless row that is OPEN, FAILED, DEFECT or
    ABORTED and was never marked blocks nothing. ``open_run`` itself no longer writes a HOLDOUT
    row without a window.

    Blocks: such a run of the same spec hash, and such a run of ANY spec hash whose recorded
    window overlaps this run's window -- editing a P0 field changes the spec hash but not the
    data. This is RANGE-002's own registry only; research lineage is not modelled.
    """
    for other in runs:
        if other.run_id == run.run_id or other.partition is not Partition.HOLDOUT:
            continue
        legacy_completed = other.holdout_range is None and other.status is RunStatus.COMPLETED
        if other.holdout_authorized_seq is None and not legacy_completed:
            continue
        if other.spec_sha256 == run.spec_sha256:
            return other
        if other.holdout_range is None or run.holdout_range is None:
            return other
        if other.holdout_range.overlaps(run.holdout_range):
            return other
    return None


def holdout_conflict_error(run: RunState, other: RunState) -> HoldoutAlreadyOpenedError:
    return HoldoutAlreadyOpenedError(
        f"the registry already holds HOLDOUT run {other.run_id!r} ({other.status.value}, spec "
        f"{other.spec_sha256[:12]}) for the same spec or an overlapping holdout window; one "
        f"opening per window (R3), so run {run.run_id!r} is refused whatever token store is used"
    )


_ATTEMPT_PHASES = frozenset({Phase.P3A, Phase.P3B})


def attempts_consumed(runs: Sequence[RunState], run: RunState) -> list[RunState]:
    """The OTHER runs whose governed authorization was ISSUED (``capability_issued`` row) in the
    same phase of this registry, whatever their protected window, spec hash, code version or final
    status (NF7, owner ruling). The registry's genesis is the research lineage, so ONE budget per
    (registry genesis, phase): a modified window, a partly overlapping window, a disjoint window
    chosen later, a spec edit or re-freeze, or another worktree all draw on it. One authorized run
    evaluates all frozen exit candidates and baselines together, so these are counts of governed
    evaluation RUNS, not trade-count minimums (D17 sample-size numbers are a separate, undecided
    matter).

    A run merely opened but never authorized consumes nothing; a failed or aborted run AFTER
    ``capability_issued`` still counts. No reset, no automatic retry, no recovery path, and no
    parameter anywhere that could grant a new budget: a new budget would need an independently
    approved registration, an exposure review and a documented justification, which is
    design-only and NOT implemented.
    """
    return [
        other
        for other in runs
        if other.run_id != run.run_id
        and other.phase is run.phase
        and other.capability_issued_seq is not None
    ]


@final
class RunRegistry:
    """Run registry over one chain file; writes are serialised by the chain's writer lock.

    Enrollment (round 4 N1, round 5 N-A / N-D). A registry file begins with one
    ``registry_genesis`` row carrying a ``uuid.uuid4()`` id (canonical lowercase text; an
    identity marker for the research lineage, NOT authentication), an ``enrollment`` record and
    a marker. That row is created ONLY by :meth:`enroll_new`, which does exist and CAN create a
    replacement registry (a new directory, or a new name once the old file is deleted). What
    makes such a replacement useless for authorizing is not its absence but the results guard:
    the guard requires the registry's genesis id to equal the spec's AND the OWNER-APPROVED
    genesis id in the committed governance manifest, and ``enroll_new`` always draws a fresh id.
    Within one directory ``enroll_new`` takes a namespace-level OS lock and re-checks under it
    that no registry exists. That serialises COOPERATING callers of ``enroll_new`` only; it does
    not stop a process that writes a chain some other way (see NOT defended below).
    Constructing ``RunRegistry(path)`` on a missing or empty file, or on a file whose first row
    is not a genesis row, raises :class:`RegistryNotEnrolledError`: opening never creates one.

    Defended (Level 1, accidental misuse / casual bypass): a stray ``RunRegistry(new_path)``
    silently starting an empty history; a registry deleted and re-created, or enrolled in a new
    directory or worktree (different genesis, refused by the manifest check); two concurrent
    ``enroll_new`` calls in one directory. NOT defended (Level 2, design-only): a COPY of the
    approved registry keeps its genesis id (undetectable without an external anchor such as a
    signed or remotely held head); someone who can write the registry directory can build a
    registry with ANY genesis id -- including the PUBLIC owner-approved one, which is in git, so
    the genesis check stops accidents, not forgery -- by writing the chain themselves, or edit the
    manifest on disk; truncating the tail to a valid shorter chain; in-process code execution;
    the manifest is read from the EXECUTING checkout and its sha256 is recorded on each
    ``capability_issued`` row but not compared across rows (NF3);
    the ``enrolled_by`` text is caller-supplied and unauthenticated; the canonical registry
    location and the designation of the one genuine registry are OWNER decisions, recorded at
    enrollment, not chosen by code; external anchoring of the genesis id / head hash is not
    implemented.

    Directory links (Level 1 limitation, NOT confinement): ``RunRegistry`` and ``enroll_new`` accept paths.
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

    def __init__(self, path: Path) -> None:
        file = Path(path)
        if not file.is_file() or file.stat().st_size == 0:
            raise RegistryNotEnrolledError(
                f"{file} is missing or empty: opening a registry never creates one; only "
                "RunRegistry.enroll_new(path) enrolls a new registry (fail closed)"
            )
        self._chain = HashChainFile(file)  # verifies the existing chain; raises if broken
        _read_genesis(self._chain.records())  # raises RegistryNotEnrolledError if not enrolled

    @classmethod
    def enroll_new(
        cls, path: Path, *, enrolled_by: str, now: datetime | None = None
    ) -> RunRegistry:
        """Create a brand-new registry file with a fresh genesis id. The ONLY creating path.

        Refuses (``RegistryEnrollmentError``) if ``path`` already exists (even empty), if
        ``enrolled_by`` is blank, if it is longer than ``MAX_ENROLLED_BY_CHARS`` after stripping
        (:class:`EnrolledByTooLongError`), or if the directory already contains another file
        that begins with a RANGE-002 ``registry_genesis`` row (no second registry beside the
        first). NAMESPACE AVAILABILITY: any file in the registry directory whose first 1 MB has
        no newline, or that cannot be read, or whose first line is deeply nested JSON, is
        treated as a registry and blocks enrolment. Logs and binaries must NOT live in the
        governance namespace directory.
        ``enrolled_by`` is free text supplied by the caller and is NOT authenticated. The
        caller (the owner) records the returned ``genesis_id`` in the manifest and spec and
        decides where the canonical registry lives; this method never picks a location.

        N-D: the existence re-check, the directory scan and the file creation all run while
        holding a namespace-level OS lock (a fixed ``.range002-namespace.lock`` file in the
        directory, created exclusively), so of several concurrent ``enroll_new`` callers
        -- same path or different file names in one directory -- the tests observe exactly one
        winner per round and a named
        :class:`RegistryEnrollmentError`. Level 1: it serialises cooperating ``enroll_new``
        callers only; it cannot stop a process that writes a chain file by other means.

        Directory links (Level 1 limitation, NOT confinement): ``path``'s parent directory, if a symlink or junction, is followed.
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
        file = Path(path)
        if not isinstance(enrolled_by, str) or not enrolled_by.strip():
            raise RegistryEnrollmentError("enrolled_by must be a non-empty string")
        if len(enrolled_by.strip()) > MAX_ENROLLED_BY_CHARS:
            raise EnrolledByTooLongError(
                f"enrolled_by is longer than {MAX_ENROLLED_BY_CHARS} characters"
            )
        with namespace_lock(file.parent):
            if os.path.lexists(file):
                raise RegistryEnrollmentError(
                    f"{file} already exists; enroll_new never reuses or overwrites a file (a "
                    "replacement registry is never created implicitly)"
                )
            other = _other_registry_in(file.parent)
            if other is not None:
                raise RegistryEnrollmentError(
                    f"{file.parent} already contains a RANGE-002 registry ({other.name}); a "
                    "second or replacement registry is never created implicitly"
                )
            try:
                fd = os.open(
                    file, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
                )
            except FileExistsError as exc:  # unreachable under the lock; kept fail-closed
                raise RegistryEnrollmentError(f"{file} was created concurrently") from exc
            os.close(fd)
            genesis = _new_genesis_id()
            stamp = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
            try:
                HashChainFile(file).append(
                    KIND_GENESIS,
                    {
                        "marker": REGISTRY_MARKER,
                        "genesis_id": genesis,
                        "enrollment": {
                            "enrolled_by": enrolled_by.strip(),
                            "enrolled_at_utc": stamp,
                            "authenticated": False,
                        },
                    },
                    now=now,
                )
            except BaseException:
                file.unlink(missing_ok=True)  # never leave a half-enrolled (empty) registry
                raise
        return cls(file)

    # --- read side ----------------------------------------------------------

    @property
    def path(self) -> Path:
        return self._chain.path

    @property
    def genesis_id(self) -> str:
        """The genesis id, re-read from the chain's first row on every access (so a replaced
        or truncated file cannot keep presenting the id it had at construction)."""
        return str(_read_genesis(self._chain.records())["genesis_id"])

    @property
    def enrollment(self) -> dict[str, Any]:
        """The genesis row's enrollment record (``enrolled_by`` is unauthenticated free text)."""
        return dict(_read_genesis(self._chain.records())["enrollment"])

    @property
    def head_hash(self) -> str:
        return self._chain.head_hash

    def count_records(self) -> int:
        return self._chain.count

    def records(self) -> tuple[ChainRecord, ...]:
        return self._chain.records()

    def runs(self) -> tuple[RunState, ...]:
        return _fold(self._chain.records())

    def get_run(self, run_id: str) -> RunState | None:
        for run in self.runs():
            if run.run_id == run_id:
                return run
        return None

    def count_runs(self, spec_sha256: str | None = None) -> int:
        """Every run counts -- completed, failed, defect and aborted alike."""
        return sum(1 for r in self.runs() if spec_sha256 in (None, r.spec_sha256))

    def attempts_consumed(self, run_id: str) -> int:
        """Governed authorizations already ISSUED by OTHER runs of this run's phase in this
        registry, across all windows and spec hashes (see :func:`attempts_consumed`). Read-only;
        the binding check is made again, atomically, inside :meth:`mark_capability_issued`."""
        runs = self.runs()
        run = next((r for r in runs if r.run_id == run_id), None)
        if run is None:
            raise RunNotRegisteredError(f"no run_registry row for run_id {run_id!r}")
        return len(attempts_consumed(runs, run))

    def find_open_run(
        self, *, run_id: str, spec_sha256: str, phase: Phase, partition: Partition
    ) -> RunState:
        """The OPEN row a guarded computation must have written first (R8)."""
        run = self.get_run(run_id)
        if run is None:
            raise RunNotRegisteredError(f"no run_registry row for run_id {run_id!r}")
        if run.status is not RunStatus.OPEN:
            raise RunNotRegisteredError(f"run {run_id!r} is {run.status.value}, not OPEN")
        if (run.spec_sha256, run.phase, run.partition) != (spec_sha256, phase, partition):
            raise RunNotRegisteredError(
                f"run {run_id!r} was registered for spec/phase/partition "
                f"{run.spec_sha256[:12]}/{run.phase.value}/{run.partition.value}, which does "
                "not match the authorization request"
            )
        return run

    # --- write side (append only) -------------------------------------------

    def open_run(
        self,
        *,
        phase: Phase,
        spec_sha256: str,
        code_sha: str,
        data_manifest_sha256: str,
        partition: Partition,
        seeds: Mapping[str, int],
        exit_candidates: Sequence[str],
        holdout_range: DateRange | None = None,
        protected_range: DateRange | None = None,
        now: datetime | None = None,
    ) -> str:
        """Write the OPEN row before computing; returns the run id.

        A HOLDOUT run must state the holdout window it is for (``holdout_range``, taken from
        the spec): that window is what stops a re-hashed spec re-opening the same data. A P3A /
        P3B run must likewise state the protected development window it evaluates
        (``protected_range``). It is recorded for audit and exposure purposes only: the attempt
        budget is counted per (registry genesis, phase) across ALL windows and spec hashes, so a
        different window, a changed P0 field or a re-freeze cannot reset it. Opening a run
        consumes NO attempt; only ``capability_issued`` does.
        """
        phase, partition = Phase(phase), Partition(partition)
        if partition not in PHASE_PARTITIONS[phase]:
            raise RegistryRecordError(
                f"partition {partition.value} is not valid for phase {phase.value}"
            )
        _require_hex(spec_sha256, "spec_sha256", _HEX64)
        _require_hex(code_sha, "code_sha")
        _require_hex(data_manifest_sha256, "data_manifest_sha256", _HEX64)
        if not isinstance(seeds, Mapping) or not seeds:
            raise RegistryRecordError("seeds must be a non-empty mapping (fixed seeds, plan 6.3)")
        clean_seeds: dict[str, int] = {}
        for key, val in seeds.items():
            if not isinstance(key, str) or isinstance(val, bool) or not isinstance(val, int):
                raise RegistryRecordError("seeds must map str -> int")
            clean_seeds[key] = val
        if any(abs(v) > MAX_SEED_ABS for v in clean_seeds.values()) or len(clean_seeds) > 64:
            raise RegistryRecordError("seeds: too many entries or a value outside 64-bit range")
        if (
            isinstance(exit_candidates, str)
            or len(exit_candidates) > MAX_EXIT_CANDIDATES
            or not all(isinstance(c, str) and c and len(c) <= 64 for c in exit_candidates)
        ):
            raise RegistryRecordError(
                "exit_candidates must be a sequence of at most 64 non-empty ids (<= 64 chars)"
            )
        window: dict[str, str] = {}
        if partition is Partition.HOLDOUT:
            if type(holdout_range) is not DateRange:
                raise RegistryRecordError(
                    "a HOLDOUT run must record the spec's holdout_range (a DateRange)"
                )
            window = {
                "holdout_start": holdout_range.start.isoformat(),
                "holdout_end": holdout_range.end.isoformat(),
            }
        elif holdout_range is not None:
            raise RegistryRecordError("holdout_range belongs to HOLDOUT runs only")
        if phase in _ATTEMPT_PHASES:
            if type(protected_range) is not DateRange:
                raise RegistryRecordError(
                    f"a {phase.value} run must record the spec's protected development window "
                    "(protected_range, a DateRange)"
                )
            window.update(
                protected_start=protected_range.start.isoformat(),
                protected_end=protected_range.end.isoformat(),
            )
        elif protected_range is not None:
            raise RegistryRecordError("protected_range belongs to P3A / P3B runs only")

        allocated: list[str] = []

        def build(records: tuple[ChainRecord, ...]) -> Mapping[str, Any]:
            # Runs under the writer lock on the freshly read chain: the id cannot collide.
            run_id = f"range002-run-{len(records) + 1:06d}"
            allocated.append(run_id)
            return {
                "run_id": run_id,
                "phase": phase.value,
                "partition": partition.value,
                "spec_sha256": spec_sha256,
                "code_sha": code_sha,
                "data_manifest_sha256": data_manifest_sha256,
                "seeds": clean_seeds,
                "exit_candidates": list(exit_candidates),
                "k_exit_candidates": len(exit_candidates),
                **window,
            }

        self._chain.append(KIND_OPENED, build, now=now)
        return allocated[-1]

    def close_run(
        self,
        run_id: str,
        status: RunStatus,
        audit_pack_sha256: str | None,
        *,
        now: datetime | None = None,
    ) -> None:
        """Close an OPEN run. ``audit_pack_sha256`` is format-checked only (see module doc).

        Round 4: ``COMPLETED`` is refused unless a ``capability_issued`` row exists for the run
        (``authorize`` writes it; a run the guard never authorized cannot be recorded as having
        completed), and a digest already recorded by another run is refused as reuse. Neither
        check authenticates anything: a caller can still call :meth:`mark_capability_issued`
        directly (the registry API is trusted at Level 1).
        """
        status = RunStatus(status)
        if status not in _CLOSE_STATUSES:
            raise RegistryRecordError(f"{status.value} is not a closing status")
        if status is RunStatus.COMPLETED or audit_pack_sha256 is not None:
            _require_hex(audit_pack_sha256, "audit_pack_sha256", _HEX64)

        def build(records: tuple[ChainRecord, ...]) -> Mapping[str, Any]:
            states = _fold(records)
            run = next((s for s in states if s.run_id == run_id), None)
            if run is None:
                raise RunNotRegisteredError(f"no run_registry row for run_id {run_id!r}")
            if run.status is not RunStatus.OPEN:
                raise RegistryRecordError(f"run {run_id!r} is already {run.status.value}")
            if status is RunStatus.COMPLETED and run.capability_issued_seq is None:
                raise CapabilityNotIssuedError(
                    f"run {run_id!r} has no capability_issued row: results_guard.authorize "
                    "never authorized it, so it cannot be closed COMPLETED"
                )
            if audit_pack_sha256 is not None and any(
                s.audit_pack_sha256 == audit_pack_sha256 for s in states if s.run_id != run_id
            ):
                raise EvidenceReuseError(
                    f"audit pack digest {audit_pack_sha256[:12]} is already recorded by "
                    f"another run; run {run_id!r} cannot reuse it"
                )
            return {
                "run_id": run_id,
                "status": status.value,
                "audit_pack_sha256": audit_pack_sha256,
            }

        self._chain.append(KIND_CLOSED, build, now=now)

    def abort_open_runs(self, *, now: datetime | None = None) -> tuple[str, ...]:
        """Append ABORTED for every run left OPEN (crash recovery). Call only
        when no computation is in flight; the aborted runs still count."""
        aborted: list[str] = []
        for run in self.runs():
            if run.status is RunStatus.OPEN:
                self.close_run(run.run_id, RunStatus.ABORTED, None, now=now)
                aborted.append(run.run_id)
        return tuple(aborted)

    def record_selection(
        self, run_id: str, record: Mapping[str, Any], *, now: datetime | None = None
    ) -> str:
        """Append the P3a ``SelectionRecord`` (WP4.1 step 3) to an OPEN run.

        Returns the row hash so the audit pack can cite it; the record must be
        appended *before* unsealing. Round 4: the record must embed this run's ``run_id`` and
        ``spec_sha256`` (so it is bound to its originating run), and a record whose digest
        another run already holds is refused as reuse."""
        if not record:
            raise RegistryRecordError("selection record must not be empty")
        body = dict(record)
        try:
            record_sha = content_sha256(body)
        except CanonicalisationError as exc:
            raise RegistryRecordError(f"selection record is not canonical JSON: {exc}") from exc
        if len(json.dumps(body, default=str)) > MAX_SELECTION_RECORD_BYTES:
            raise RegistryRecordError("selection record is too large")

        def build(records: tuple[ChainRecord, ...]) -> Mapping[str, Any]:
            run = _find(records, run_id)
            if run.status is not RunStatus.OPEN:
                raise RegistryRecordError(f"run {run_id!r} is {run.status.value}, not OPEN")
            if run.phase is not Phase.P3A:
                raise RegistryRecordError("a SelectionRecord belongs to a P3A run")
            if run.selection_record_seq is not None:
                raise RegistryRecordError(f"run {run_id!r} already has a selection record")
            if body.get("run_id") != run_id or body.get("spec_sha256") != run.spec_sha256:
                raise RegistryRecordError(
                    "selection record must embed this run's 'run_id' and 'spec_sha256'"
                )
            if any(s.selection_record_sha256 == record_sha for s in _fold(records)):
                raise EvidenceReuseError(
                    f"selection record digest {record_sha[:12]} is already recorded by another run"
                )
            return {"run_id": run_id, "record": body, "record_sha256": record_sha}

        return self._chain.append(KIND_SELECTION, build, now=now).row_hash

    def mark_capability_issued(
        self,
        run_id: str,
        *,
        evidence: Sequence[Mapping[str, str | None]] = (),
        manifest_sha256: str | None = None,
        attempt_limit: int | None = None,
        now: datetime | None = None,
    ) -> str:
        """Append the durable "``authorize`` issued a capability for this run" row.

        Written by ``authorize`` BEFORE it returns the capability, for every partition. It
        carries the run's phase, partition and spec hash (read from the run's own row), the
        digests of the predecessor evidence the guard verified, and the sha256 of the governance
        manifest that authorized it. ``close_run(COMPLETED)`` requires this row. Level 1: the row
        proves ``authorize`` was reached for the run, not that the phase passed.

        Attempt accounting (round 5 N-B), atomic under the writer lock: for a P3A / P3B run
        THIS row is what consumes an attempt. ``attempt_limit`` (the manifest's pre-registered
        limit; ``None`` => :class:`AttemptLimitNotSetError`) is checked against the issued
        authorizations of OTHER runs of the same phase in this registry, across all windows and
        spec hashes (NF7); reaching the limit refuses (:class:`AttemptLimitExceededError`). A run
        is authorized once: a second row for the same run is refused
        (:class:`CapabilityAlreadyIssuedError`). Evidence digests, the manifest digest and the
        limit are validated BEFORE anything is written; an invalid value leaves the file
        byte-identical (N-C).
        """
        digests = _validated_evidence(evidence)
        if manifest_sha256 is not None:
            _require_hex(manifest_sha256, "manifest_sha256", _HEX64)
        if attempt_limit is not None and (
            type(attempt_limit) is not int or not 1 <= attempt_limit <= MAX_ATTEMPT_LIMIT
        ):
            raise RegistryRecordError(f"attempt_limit must be an integer in 1..{MAX_ATTEMPT_LIMIT}")

        def build(records: tuple[ChainRecord, ...]) -> Mapping[str, Any]:
            states = _fold(records)
            run = next((s for s in states if s.run_id == run_id), None)
            if run is None:
                raise RunNotRegisteredError(f"no run_registry row for run_id {run_id!r}")
            if run.status is not RunStatus.OPEN:
                raise RegistryRecordError(f"run {run_id!r} is {run.status.value}, not OPEN")
            if run.capability_issued_seq is not None:
                raise CapabilityAlreadyIssuedError(
                    f"run {run_id!r} was already authorized (capability_issued row "
                    f"{run.capability_issued_seq}); a run is authorized once"
                )
            if run.phase in _ATTEMPT_PHASES:
                if attempt_limit is None:
                    raise AttemptLimitNotSetError(
                        f"{run.phase.value} authorization needs the manifest's pre-registered "
                        "attempt limit; none was supplied (fail closed)"
                    )
                used = len(attempts_consumed(states, run))
                if used >= attempt_limit:
                    raise AttemptLimitExceededError(
                        f"{run.phase.value} attempt budget exhausted for this registry (all windows): "
                        f"{used} governed authorization(s) already issued across all spec "
                        f"hashes, limit {attempt_limit} (a failed or aborted run after "
                        "authorization still counts; there is no reset)"
                    )
            return {
                "run_id": run_id,
                "phase": run.phase.value,
                "partition": run.partition.value,
                "spec_sha256": run.spec_sha256,
                "evidence": digests,
                "manifest_sha256": manifest_sha256,
            }

        return self._chain.append(KIND_CAPABILITY, build, now=now).row_hash

    def mark_holdout_authorized(self, run_id: str, *, now: datetime | None = None) -> str:
        """Append the durable "this run was authorized to open the holdout" row.

        Written by ``authorize`` *before* the token is consumed, so the registry -- not the
        token directory -- is the authority on whether a holdout window has been opened. A
        crash after this row counts as opened (same conservative stance as an INTENT token).
        The window-conflict check is repeated here under the writer lock, so two handles
        cannot both be authorized for overlapping windows.
        """

        def build(records: tuple[ChainRecord, ...]) -> Mapping[str, Any]:
            states = _fold(records)
            run = next((s for s in states if s.run_id == run_id), None)
            if run is None:
                raise RunNotRegisteredError(f"no run_registry row for run_id {run_id!r}")
            if run.status is not RunStatus.OPEN:
                raise RegistryRecordError(f"run {run_id!r} is {run.status.value}, not OPEN")
            if run.partition is not Partition.HOLDOUT:
                raise RegistryRecordError("only a HOLDOUT run can be marked holdout-authorized")
            if run.holdout_authorized_seq is not None:
                raise RegistryRecordError(f"run {run_id!r} was already holdout-authorized")
            other = holdout_conflict(states, run)
            if other is not None:
                raise holdout_conflict_error(run, other)
            return {"run_id": run_id}

        return self._chain.append(KIND_HOLDOUT_AUTH, build, now=now).row_hash


def _validated_evidence(
    evidence: Sequence[Mapping[str, str | None]],
) -> list[dict[str, str | None]]:
    """Strictly validate predecessor-evidence digests before they are written (N-C)."""
    if isinstance(evidence, str | bytes | Mapping) or not isinstance(evidence, Sequence):
        raise RegistryRecordError("evidence must be a sequence of digest mappings")
    if len(evidence) > MAX_EVIDENCE_ITEMS:
        raise RegistryRecordError(f"evidence has more than {MAX_EVIDENCE_ITEMS} items")
    out: list[dict[str, str | None]] = []
    for item in evidence:
        if not isinstance(item, Mapping) or set(item) != {
            "run_id",
            "audit_pack_sha256",
            "selection_record_sha256",
        }:
            raise RegistryRecordError(
                "each evidence item must have exactly run_id, audit_pack_sha256 and "
                "selection_record_sha256"
            )
        run_id = item["run_id"]
        audit = item["audit_pack_sha256"]
        selection = item["selection_record_sha256"]
        if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
            raise RegistryRecordError(f"evidence run_id is not a run id: {run_id!r}")
        _require_hex(audit, "evidence.audit_pack_sha256", _HEX64)
        if selection is not None:
            _require_hex(selection, "evidence.selection_record_sha256", _HEX64)
        out.append(
            {"run_id": run_id, "audit_pack_sha256": audit, "selection_record_sha256": selection}
        )
    return out


def _read_genesis(records: Sequence[ChainRecord]) -> Mapping[str, Any]:
    """The validated genesis payload of an enrolled registry, or ``RegistryNotEnrolledError``."""
    if not records or records[0].kind != KIND_GENESIS:
        raise RegistryNotEnrolledError(
            "the registry file does not begin with a registry_genesis row: it was never "
            "enrolled by RunRegistry.enroll_new (fail closed)"
        )
    payload = records[0].payload
    enrollment = payload.get("enrollment")
    if (
        payload.get("marker") != REGISTRY_MARKER
        or not is_canonical_uuid4(payload.get("genesis_id"))
        or not isinstance(enrollment, dict)
        or not isinstance(enrollment.get("enrolled_by"), str)
        or not isinstance(enrollment.get("enrolled_at_utc"), str)
    ):
        raise RegistryIntegrityError("the registry_genesis row is malformed")
    return payload


def _other_registry_in(directory: Path) -> Path | None:
    """A file in ``directory`` that is, or must be assumed to be, a RANGE-002 registry.

    Fail closed (NF1): the whole FIRST line is read, up to the chain's ``MAX_RECORD_BYTES`` (no
    record can be longer), so an over-long field cannot hide a registry. A file whose first line
    is longer than that, that cannot be read at all, or whose first line is so deeply nested that
    ``json.loads`` raises ``RecursionError`` is treated as a registry (fail closed, named
    ``RegistryEnrollmentError`` from ``enroll_new``; the directory is a dedicated governance
    namespace: logs and binaries must not live there). A small first line that is not JSON, or not a genesis row,
    is not a registry. Level 1 only: it finds files this module wrote, not a hostile layout."""
    if not directory.is_dir():
        return None
    for entry in sorted(directory.iterdir()):
        try:
            if not entry.is_file():
                continue
            with entry.open("rb") as fh:
                head = fh.read(MAX_RECORD_BYTES + 2)
        except OSError:  # unreadable: cannot be shown not to be a registry
            return entry
        first, newline, _ = head.partition(b"\n")
        if len(first) > MAX_RECORD_BYTES or (not newline and len(head) > MAX_RECORD_BYTES):
            return entry  # no valid record is this long: oversized first line => assume registry
        try:
            doc = json.loads(first.decode("utf-8"))
        except RecursionError:
            # A deeply nested first line (e.g. '[' * 300000) is not JSON we can parse, and
            # "cannot be shown not to be a registry" is treated as a registry: fail closed with
            # the named enrolment refusal rather than crash or skip the file.
            return entry
        except ValueError:  # small and not JSON: not a registry
            continue
        payload = doc.get("payload") if isinstance(doc, dict) else None
        if (
            isinstance(payload, dict)
            and doc.get("kind") == KIND_GENESIS
            and payload.get("marker") == REGISTRY_MARKER
        ):
            return entry
    return None


def _find(records: Sequence[ChainRecord], run_id: str) -> RunState:
    for state in _fold(records):
        if state.run_id == run_id:
            return state
    raise RunNotRegisteredError(f"no run_registry row for run_id {run_id!r}")


def _opened_window(
    p: Mapping[str, Any], *, start_key: str = "holdout_start", end_key: str = "holdout_end"
) -> DateRange | None:
    if start_key not in p and end_key not in p:
        return None
    try:
        return DateRange(date.fromisoformat(p[start_key]), date.fromisoformat(p[end_key]))
    except (KeyError, TypeError, ValueError) as exc:
        raise RegistryIntegrityError(
            f"run_opened row has a malformed holdout window: {exc}"
        ) from exc


def _fold(records: Sequence[ChainRecord]) -> tuple[RunState, ...]:
    states: dict[str, RunState] = {}
    order: list[str] = []

    def known(rec: ChainRecord) -> str:
        rid = str(rec.payload["run_id"])
        if rid not in states:
            raise RegistryIntegrityError(
                f"record seq {rec.seq} ({rec.kind}) refers to unknown run_id {rid!r}"
            )
        return rid

    for rec in records:
        p = rec.payload
        if rec.kind == KIND_GENESIS:
            if rec.seq != 1:
                raise RegistryIntegrityError(
                    f"record seq {rec.seq} is a second registry_genesis row: a registry has one"
                )
        elif rec.kind == KIND_OPENED:
            rid = str(p["run_id"])
            if rid in states:
                raise RegistryIntegrityError(
                    f"record seq {rec.seq} re-opens duplicate run_id {rid!r}"
                )
            order.append(rid)
            states[rid] = RunState(
                run_id=rid,
                phase=Phase(p["phase"]),
                partition=Partition(p["partition"]),
                spec_sha256=str(p["spec_sha256"]),
                code_sha=str(p["code_sha"]),
                data_manifest_sha256=str(p["data_manifest_sha256"]),
                seeds=dict(p["seeds"]),
                exit_candidates=tuple(p["exit_candidates"]),
                status=RunStatus.OPEN,
                audit_pack_sha256=None,
                opened_seq=rec.seq,
                selection_record_seq=None,
                holdout_range=_opened_window(p),
                protected_range=_opened_window(
                    p, start_key="protected_start", end_key="protected_end"
                ),
            )
        elif rec.kind == KIND_CLOSED:
            rid = known(rec)
            states[rid] = replace(
                states[rid], status=RunStatus(p["status"]), audit_pack_sha256=p["audit_pack_sha256"]
            )
        elif rec.kind == KIND_SELECTION:
            rid = known(rec)
            states[rid] = replace(
                states[rid],
                selection_record_seq=rec.seq,
                selection_record_sha256=p.get("record_sha256"),
            )
        elif rec.kind == KIND_HOLDOUT_AUTH:
            rid = known(rec)
            states[rid] = replace(states[rid], holdout_authorized_seq=rec.seq)
        elif rec.kind == KIND_CAPABILITY:
            rid = known(rec)
            if states[rid].capability_issued_seq is None:
                states[rid] = replace(states[rid], capability_issued_seq=rec.seq)
    return tuple(states[r] for r in order)
