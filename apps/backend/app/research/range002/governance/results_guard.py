"""Results guard -- the single entry point for any computation that yields returns (WP0.4).

``authorize`` is the only way to obtain a :class:`ResultsCapability`. Engine and
statistics entry points demand one (``@requires_capability`` /
``require_capability``), so a direct call, script, notebook or batch job that
skipped the guard fails at runtime with ``InvalidCapabilityError``. Static
import-lint (tests) is the second line of defence, not the first.

Threat model (Level 1): accidental misuse and casual bypass by a developer. Not defended
(Level 2, design-only): code execution in this process, write access to the registry or token
directories or the manifest, a copied or forged registry (including one carrying the PUBLIC
approved genesis id, which stops accidents, not forgery), truncation of the registry tail to a
valid shorter chain, signed approvals, an execution boundary, external anchoring.

"Unforgeable by convention": the constructor demands a module-private token and the capability
is registered, by identity, in a module-private WEAK table (``_BOUND_REGISTRIES``: capability ->
the registry its run lives in; the entry disappears when the capability is garbage collected,
so the table cannot grow without bound). ``object.__new__`` tricks, copies and look-alikes that
reuse a readable ``_nonce`` do not validate, because the lookup is by the capability object
itself. A genuine capability validates for as long as ITS OWN run is OPEN in the registry it was
issued against, and for nothing else.

Checks run in this order and every failure raises a named exception (no
default, no warn-and-continue):

 (N3) an ``independence_authorization`` argument is refused FIRST, always -- with or without any
     holdout conflict -- before any state is read or written (no lineage/independence policy
     exists in code that could validate one)
 (0) the spec is the adapter's ``GuardSpecView`` built by ``to_guard_view`` from a
     ``load_frozen`` view (no duck typing); the registry, exposure ledger and holdout store are
     exactly ``RunRegistry`` / ``ExposureLedger`` / ``HoldoutTokenStore`` (no subclass, no
     duck type); the ledger can only come from its ``from_*`` loaders
 (a) spec frozen (hash recomputed by the loader) and its sign-off fields present and matching
     the hash -- NOT an authenticated signature (Level 2, design pending)
 (N1, round 5 N-A) for EVERY partition, three genesis ids must agree: the registry in use,
     the spec's ``governance.registry_genesis_id`` and the OWNER-APPROVED genesis in the
     committed governance manifest (``spec.manifest``; ``authorize`` itself has no path parameter
     and loads the fixed repo-relative path. The module global ``_MANIFEST_PATH``,
     ``load_manifest(path)`` and ``freeze(manifest_path=)`` are TEST SEAMS, not defences against
     code that can run Python). A null/unset manifest refuses
     (``ManifestNotApprovedError``); a spec/registry that differs from the manifest refuses
     (``ManifestGenesisMismatchError``); a spec that differs from the registry refuses
     (``RegistryGenesisMismatchError``). What this defends (Level 1): a new directory, a
     re-enrolled replacement registry (``RunRegistry.enroll_new`` DOES exist and can create one;
     it simply gets a fresh genesis id) or a re-freeze naming another genesis cannot authorize
     unless the owner changes the committed manifest, which is a reviewed git change. What it
     does NOT defend (Level 2, design-only): a COPY of the approved registry keeps its genesis
     id and is undetectable without external anchoring; anyone able to edit the manifest or the
     registry on disk. The genesis id is an identity marker (UUIDv4), not authentication
 (b) partition is in the closed set and authorized for the phase; P5 (PAPER) is then REFUSED
     outright (``PaperApprovalNotImplementedError``): owner approval before paper is Level 2
     design-only and no approval reference is accepted or recorded
 (f) DEVELOPMENT_* and HOLDOUT refuse while p3_criteria / exits_candidates /
     exits_selection is unset
 (g) phase order, from registry rows AND predecessor artefacts: P3B needs a COMPLETED P3A,
     P4 additionally a COMPLETED P3B (all same spec hash, each with a ``capability_issued``
     row). The caller passes the predecessor artefacts (audit pack, P3A selection record); the
     guard re-reads the files NOW, recomputes their sha256 (must equal the registry digest) and
     checks the run/spec embedded in them (audit-pack header, selection-record fields) equal
     the predecessor's row. A P4 used as a predecessor must also carry a ``holdout_authorized``
     row (that rule is exercised only through ``_check_phase_order``: P5 itself is refused).
     The digests verified are recorded on the capability and in its ``capability_issued`` row.
     "Content-bound, not authenticated": this proves the artefact is the one the registry row
     names and was written for that run, not that the row's author told the truth, that the
     phase PASSED, or that the pack was not rewritten by someone who can also rewrite the
     registry (Level 2: signed run results, design-only)
 (c) partition does not overlap R2's window, the spec's ``exposed`` list or the
     signed exposure ledger, and the ledger is the one the spec's
     ``governance.exposure_signed`` records (REPLAY_RNG001 is exempt: engine
     validation only, flagged never citable). PAPER / REPLAY ranges are bounded
     (PAPER strictly after R2; REPLAY inside R2; neither touches a spec partition)
 (d) an OPEN run_registry row, written first, matches spec/phase/partition
 (N2e, round 5 N-B) P3A / P3B attempt budget. The limits are PRE-REGISTERED in the manifest
     (``p3_attempt_limits``; null => ``AttemptLimitNotSetError``/``ManifestNotApprovedError``)
     and the spec's ``p3.max_p3a_attempts`` / ``max_p3b_attempts`` must equal them
     (``ManifestLimitMismatchError``). An attempt is a governed EVALUATION RUN (one authorized
     run evaluates all frozen exit candidates and baselines together; these are not trade-count
     minimums, the D17 sample-size numbers being a separate undecided matter). It is consumed
     once governed authorization is ISSUED (the ``capability_issued`` row below); a request
     refused before that, and a run that was merely opened, consume nothing; a failed or aborted
     run after it still counts. Attempts are counted per (registry genesis = research lineage,
     phase) across ALL protected windows, spec hashes, code versions and worktrees sharing the
     registry (NF7): a modified, overlapping, disjoint or later-chosen window, a P0 edit, a
     re-freeze or a new run id does not reset the budget. The window stays recorded on the
     ``capability_issued`` run for audit/exposure review only. A new budget would need an
     independently approved registration, an exposure review and a documented justification:
     design-only, NOT implemented; a ``budget_reset_authorization`` argument is refused by name.
     A manifest limit above ``MAX_ATTEMPT_LIMIT`` is refused by name
     (``AttemptLimitOutOfRangeError``) before any state is written. Raising an attempt limit by
     editing the committed manifest is ALLOWED BY DESIGN: it is a process control (reviewed
     change, owner approval); enforcing it against a local edit is Level 2. The manifest is read from the EXECUTING checkout and its sha256
     is recorded on each ``capability_issued`` row but not compared across rows (NF3).
     The check is repeated atomically under the registry's writer lock when the row is written.
     There is no automatic retry, no counter reset and no recovery code (recovery would need a
     documented incident, independent review, owner authorization and a permanent audit record:
     design-only). A run is authorized once (``CapabilityAlreadyIssuedError``)
 (e) HOLDOUT: the *registry* is the authority -- refused if another run whose authorization
     was ISSUED (a ``holdout_authorized`` row exists, whatever its later status) is for the
     same spec hash or for an overlapping holdout window of any spec hash (editing a P0 field
     buys no second opening), or this run was already authorized, whatever token directory is
     used. A legacy HOLDOUT row with no recorded window blocks every window only if it has an
     authorization mark or is COMPLETED (see ``run_registry.holdout_conflict``). Then a valid
     unused token (paired with this registry's genesis id), the durable ``holdout_authorized``
     row, and the two-phase token consume *last*, so a refusal BEFORE the mark never burns the
     token or blocks the window. After the mark (or a crash after it) the window stays
     consumed: no automatic restoration, no reissue, no reset (recovery is design-only, owner
     approval pending)
 (N2a) a durable ``capability_issued`` row is written for every partition BEFORE the capability
     is returned (it records the manifest sha256 that authorized the run);
     ``RunRegistry.close_run(COMPLETED)`` refuses a run without one

A capability is bound to its run: ``require_capability`` consults the registry
and rejects it once the run is no longer OPEN.

The static import-lint (``tests/.../test_import_lint.py``) is a DEVELOPER SAFEGUARD against
accidental omissions, not an adversary-resistant boundary. Known bypasses it does NOT catch:
re-exporting a guarded callable through a private lambda; a dict (or other container) of
undecorated functions; aliased imports of capability-bearing objects from other libraries or
modules; and anything under ``scripts/`` (which is not linted at all). It will not be expanded
further; a real execution boundary is Level 2, design-only.
"""

from __future__ import annotations

import functools
import hashlib
import inspect
import re
import secrets
import weakref
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, final

from app.research.range002.governance.errors import (
    AttemptLimitExceededError,
    AttemptLimitNotSetError,
    AttemptLimitOutOfRangeError,
    BudgetResetNotAcceptedError,
    CapabilityAlreadyIssuedError,
    ExposureBindingError,
    ExposureLedgerNotTrustedError,
    ExposureOverlapError,
    HoldoutAlreadyOpenedError,
    HoldoutStoreNotTrustedError,
    IndependenceAuthorizationNotAcceptedError,
    InvalidCapabilityError,
    PaperApprovalNotImplementedError,
    PaperRangeNotAfterR2Error,
    PartitionNotAuthorizedError,
    PhaseOrderError,
    PredecessorEvidenceBindingError,
    PredecessorEvidenceMismatchError,
    PredecessorEvidenceMissingError,
    PredecessorHoldoutNotAuthorizedError,
    RangeOverlapsPartitionError,
    RegistryGenesisMismatchError,
    RegistryNotTrustedError,
    ReplayRangeOutsideR2Error,
    RunNotRegisteredError,
    SpecIncompleteError,
    SpecNotFrozenError,
    SpecNotSignedError,
    SpecViewNotTrustedError,
)
from app.research.range002.governance.evidence import parse_audit_pack_header
from app.research.range002.governance.exposure_ledger import ExposureLedger
from app.research.range002.governance.holdout_token import HoldoutTokenStore
from app.research.range002.governance.model import (
    DEVELOPMENT_PARTITIONS,
    MAX_ATTEMPT_LIMIT,
    PHASE_PARTITIONS,
    R2_EXCLUDED_WINDOW,
    DateRange,
    Partition,
    Phase,
)
from app.research.range002.governance.run_registry import (
    RunRegistry,
    RunStatus,
    holdout_conflict,
    holdout_conflict_error,
)
from app.research.range002.governance.spec_adapter import GuardSpecView
from app.research.range002.spec.hashing import CanonicalisationError, content_sha256, loads_strict
from app.research.range002.spec.manifest import GovernanceManifest, load_manifest

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ISSUE = object()  # module-private: only authorize() holds it
#: TEST SEAM, module-private and deliberately NOT an ``authorize`` parameter: ``None`` means the
#: committed manifest at its fixed repo-relative path. Tests monkeypatch it to a synthetic file;
#: production code never sets it, and the public API offers no way to name another manifest.
_MANIFEST_PATH: Path | None = None
#: capability -> registry its run lives in. Weak keys (by identity): an entry vanishes with its
#: capability, so the table cannot grow without bound; semantics are otherwise unchanged.
_BOUND_REGISTRIES: weakref.WeakKeyDictionary[ResultsCapability, RunRegistry] = (
    weakref.WeakKeyDictionary()
)


@dataclass(frozen=True)
class PredecessorEvidence:
    """Artefacts of one COMPLETED predecessor run, handed to ``authorize`` for the successor.

    ``audit_pack_path`` is hashed as raw file bytes and must equal the registry row's
    ``audit_pack_sha256``, and its first line must be the canonical header
    (:mod:`governance.evidence`) naming the predecessor's own ``run_id`` and ``spec_sha256``;
    ``selection_record_path`` (P3A only) is parsed as strict JSON, its canonical-JSON sha256 must
    equal the digest recorded by ``record_selection`` and its embedded ``run_id`` /
    ``spec_sha256`` must name the predecessor. The files are re-read at every ``authorize`` call.
    Content-bound, not authenticated: nothing signs these files.
    """

    run_id: str
    audit_pack_path: Path
    selection_record_path: Path | None = None


@final
class ResultsCapability:
    """Opaque proof that ``authorize`` approved this run. Not constructible outside this module."""

    __slots__ = (
        "__weakref__",
        "_nonce",
        "citable",
        "date_range",
        "evidence_digests",
        "exposure_ledger_sha256",
        "partition",
        "phase",
        "run_id",
        "spec_sha256",
    )

    spec_sha256: str
    phase: Phase
    partition: Partition
    run_id: str
    date_range: DateRange
    citable: bool
    exposure_ledger_sha256: str | None
    #: ``((predecessor run_id, audit_pack_sha256, selection_record_sha256 | None), ...)`` -- the
    #: predecessor evidence digests ``authorize`` verified when it issued this capability.
    evidence_digests: tuple[tuple[str, str, str | None], ...]
    _nonce: str

    def __init__(
        self,
        issue_token: object,
        *,
        spec_sha256: str,
        phase: Phase,
        partition: Partition,
        run_id: str,
        date_range: DateRange,
        citable: bool,
        exposure_ledger_sha256: str | None,
        evidence_digests: tuple[tuple[str, str, str | None], ...],
    ) -> None:
        if issue_token is not _ISSUE:
            raise InvalidCapabilityError(
                "ResultsCapability can only be issued by results_guard.authorize()"
            )
        nonce = secrets.token_hex(16)
        for name, value in (
            ("_nonce", nonce),
            ("spec_sha256", spec_sha256),
            ("phase", phase),
            ("partition", partition),
            ("run_id", run_id),
            ("date_range", date_range),
            ("citable", citable),
            ("exposure_ledger_sha256", exposure_ledger_sha256),
            ("evidence_digests", evidence_digests),
        ):
            object.__setattr__(self, name, value)

    def __setattr__(self, name: str, value: object) -> None:
        raise InvalidCapabilityError("ResultsCapability is immutable")

    def __delattr__(self, name: str) -> None:
        raise InvalidCapabilityError("ResultsCapability is immutable")

    def __reduce__(self) -> Any:
        raise InvalidCapabilityError("ResultsCapability cannot be pickled or copied")

    def __copy__(self) -> Any:
        raise InvalidCapabilityError("ResultsCapability cannot be copied")

    def __deepcopy__(self, memo: Any) -> Any:
        raise InvalidCapabilityError("ResultsCapability cannot be copied")

    def __repr__(self) -> str:
        return (
            f"ResultsCapability(run_id={self.run_id!r}, phase={self.phase.value}, "
            f"partition={self.partition.value}, citable={self.citable})"
        )


def require_capability(capability: object) -> ResultsCapability:
    """Raise unless ``capability`` was issued by :func:`authorize` in this process AND its run
    is still OPEN in the registry it was issued against (same spec hash, phase, partition)."""
    registry = _BOUND_REGISTRIES.get(capability) if type(capability) is ResultsCapability else None
    if type(capability) is not ResultsCapability or registry is None:
        raise InvalidCapabilityError(
            "this entry point requires a ResultsCapability from results_guard.authorize(); "
            "none (or a forged one) was supplied"
        )
    run = registry.get_run(capability.run_id)
    if (
        run is None
        or run.status is not RunStatus.OPEN
        or (run.spec_sha256, run.phase, run.partition)
        != (capability.spec_sha256, capability.phase, capability.partition)
    ):
        raise InvalidCapabilityError(
            f"capability for run {capability.run_id!r} is no longer valid: the run is not OPEN "
            "in the registry (closed, failed, aborted or mismatched)"
        )
    return capability


def requires_capability[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    """Mark a compute entry point. The function must take a ``capability`` parameter."""
    params = inspect.signature(func).parameters
    if "capability" not in params:
        raise TypeError(f"{func.__qualname__} must declare a 'capability' parameter")
    sig = inspect.signature(func)

    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            bound = sig.bind_partial(*args, **kwargs)
        except TypeError as exc:
            raise InvalidCapabilityError(f"{func.__qualname__}: bad call: {exc}") from exc
        require_capability(bound.arguments.get("capability"))
        return func(*args, **kwargs)

    wrapper.__requires_capability__ = True  # type: ignore[attr-defined]
    return wrapper


def _spec_checks(spec: object) -> tuple[GuardSpecView, str]:
    if type(spec) is not GuardSpecView:
        raise SpecViewNotTrustedError(
            "authorize() accepts only the GuardSpecView built by spec_adapter.to_guard_view(); "
            f"got {type(spec).__name__}"
        )
    sha = spec.spec_sha256
    if not isinstance(sha, str) or not _HEX64.fullmatch(sha):
        raise SpecNotFrozenError("spec has no valid 64-hex spec_sha256: it is not frozen")
    if spec.is_signed is not True:
        raise SpecNotSignedError("spec is not signed; results_guard refuses an unsigned spec")
    return spec, sha


def _partition_range(spec: GuardSpecView, partition: Partition) -> DateRange | None:
    ranges = spec.partitions
    return {
        Partition.DEVELOPMENT_SELECTION: lambda: ranges.selection,
        Partition.DEVELOPMENT_CONFIRMATION: lambda: ranges.confirmation,
        Partition.HOLDOUT: lambda: ranges.holdout,
    }.get(partition, lambda: None)()


def _check_free_range(spec: GuardSpecView, partition: Partition, rng: DateRange) -> None:
    """PAPER / REPLAY_RNG001 have no spec range: bound the requested one explicitly."""
    for name, part in (
        ("selection", spec.partitions.selection),
        ("confirmation", spec.partitions.confirmation),
        ("holdout", spec.partitions.holdout),
    ):
        if rng.overlaps(part):
            raise RangeOverlapsPartitionError(
                f"{partition.value} range {rng.as_dict()} overlaps the spec's {name} "
                f"partition {part.as_dict()}"
            )
    if partition is Partition.PAPER and rng.start <= R2_EXCLUDED_WINDOW.end:
        raise PaperRangeNotAfterR2Error(
            f"PAPER must start strictly after the R2 end {R2_EXCLUDED_WINDOW.end.isoformat()}; "
            f"got start {rng.start.isoformat()}"
        )
    if partition is Partition.REPLAY_RNG001 and not R2_EXCLUDED_WINDOW.contains(rng):
        raise ReplayRangeOutsideR2Error(
            f"REPLAY_RNG001 range {rng.as_dict()} must lie within the R2 window "
            f"{R2_EXCLUDED_WINDOW.as_dict()}"
        )


def _check_exposure_binding(spec: GuardSpecView, ledger: ExposureLedger) -> None:
    record = spec.exposure_signed
    recorded = record.get("exposure_ledger_sha256") if isinstance(record, Mapping) else None
    if not isinstance(recorded, str) or not _HEX64.fullmatch(recorded):
        raise ExposureBindingError(
            "spec.governance.exposure_signed does not record a 64-hex 'exposure_ledger_sha256'"
        )
    if recorded != ledger.sha256:
        raise ExposureBindingError(
            f"the spec binds exposure ledger {recorded[:12]} but the ledger in use is "
            f"{ledger.sha256[:12]}"
        )


#: phase -> (predecessor phase, needs a selection record, needs a holdout_authorized row) triples
#: it requires, in order. The P5 entry is dead through ``authorize`` (P5 is refused outright)
#: and is kept, and tested directly, so the rule is in place if owner approval is ever built.
_REQUIRED_PREDECESSORS: dict[Phase, tuple[tuple[Phase, bool, bool], ...]] = {
    Phase.P3B: ((Phase.P3A, True, False),),
    Phase.P4: ((Phase.P3A, True, False), (Phase.P3B, False, False)),
    Phase.P5: ((Phase.P4, False, True),),
}


def _read_evidence(path: object, what: str) -> bytes:
    try:
        return Path(str(path)).read_bytes()
    except OSError as exc:
        raise PredecessorEvidenceMissingError(f"cannot read {what} {path}: {exc}") from exc


def _check_phase_order(
    registry: RunRegistry,
    spec_sha: str,
    phase: Phase,
    evidence: Sequence[PredecessorEvidence],
) -> tuple[tuple[str, str, str | None], ...]:
    """Phase order is enforced from registry rows AND the predecessor artefacts' content.

    Returns the evidence digests it verified, ``(predecessor run_id, audit_pack_sha256,
    selection_record_sha256 | None)`` per predecessor, for the capability to record.

    Level 1 (content-bound, NOT authenticated): the artefact is re-read now, must hash to the
    digest the predecessor's registry row recorded AND must embed that predecessor's run id and
    spec hash. That does not prove the row's author was honest, that the phase passed, or that
    a writer of both pack and registry did not forge a matching pair; signed run results are
    Level 2, design-only.
    """
    required = _REQUIRED_PREDECESSORS.get(phase)
    if required is None:
        return ()
    if any(type(e) is not PredecessorEvidence for e in evidence):
        raise PredecessorEvidenceMissingError("predecessor_evidence must be PredecessorEvidence")
    by_run = {e.run_id: e for e in evidence}
    runs = [r for r in registry.runs() if r.spec_sha256 == spec_sha]
    verified: list[tuple[str, str, str | None]] = []
    for pred, needs_selection, needs_holdout_auth in required:
        done = [
            r
            for r in runs
            if r.phase is pred
            and r.status is RunStatus.COMPLETED
            and r.capability_issued_seq is not None
            and (not needs_selection or r.selection_record_seq is not None)
        ]
        if not done:
            extra = " with a recorded selection record" if needs_selection else ""
            raise PhaseOrderError(
                f"{phase.value} requires a COMPLETED {pred.value} run{extra} "
                f"for spec {spec_sha[:12]} in the registry"
            )
        if needs_holdout_auth:
            done = [r for r in done if r.holdout_authorized_seq is not None]
            if not done:
                raise PredecessorHoldoutNotAuthorizedError(
                    f"{phase.value} requires a {pred.value} run that was authorized to open the "
                    f"holdout (a holdout_authorized row) for spec {spec_sha[:12]}"
                )
        run = next((r for r in done if r.run_id in by_run), None)
        if run is None:
            raise PredecessorEvidenceMissingError(
                f"{phase.value} requires the audit pack of a COMPLETED {pred.value} run of spec "
                f"{spec_sha[:12]} (candidates {[r.run_id for r in done]}); none was supplied"
            )
        item = by_run[run.run_id]
        recorded = run.audit_pack_sha256
        pack = _read_evidence(item.audit_pack_path, "audit pack")
        pack_sha = hashlib.sha256(pack).hexdigest()
        if recorded is None or pack_sha != recorded:
            raise PredecessorEvidenceMismatchError(
                f"audit pack for {pred.value} run {run.run_id!r} does not hash to the digest "
                "recorded in the registry"
            )
        if parse_audit_pack_header(pack) != (run.run_id, run.spec_sha256):
            raise PredecessorEvidenceBindingError(
                f"audit pack for {pred.value} run {run.run_id!r} embeds a different run id or "
                "spec hash: evidence is bound to the run it was written for"
            )
        selection_sha: str | None = None
        if needs_selection:
            if item.selection_record_path is None:
                raise PredecessorEvidenceMissingError(
                    f"the selection record of {pred.value} run {run.run_id!r} was not supplied"
                )
            raw = _read_evidence(item.selection_record_path, "selection record")
            try:
                parsed = loads_strict(raw)
                selection_sha = content_sha256(parsed)
            except CanonicalisationError as exc:
                raise PredecessorEvidenceMissingError(
                    f"cannot parse selection record {item.selection_record_path}: {exc}"
                ) from exc
            if run.selection_record_sha256 is None or selection_sha != run.selection_record_sha256:
                raise PredecessorEvidenceMismatchError(
                    f"selection record for {pred.value} run {run.run_id!r} does not hash "
                    "(canonical JSON) to the digest recorded in the registry"
                )
            if (
                not isinstance(parsed, dict)
                or parsed.get("run_id") != run.run_id
                or parsed.get("spec_sha256") != run.spec_sha256
            ):
                raise PredecessorEvidenceBindingError(
                    f"selection record for {pred.value} run {run.run_id!r} embeds a different "
                    "run id or spec hash"
                )
        verified.append((run.run_id, pack_sha, selection_sha))
    return tuple(verified)


def _check_attempt_limit(
    registry: RunRegistry,
    spec: GuardSpecView,
    manifest: GovernanceManifest,
    phase: Phase,
    run_id: str,
) -> int | None:
    """P3A / P3B attempt budget (round 5 N-B); returns the pre-registered limit to enforce.

    Non-binding pre-check (it refuses early, before any state changes); the binding check is made
    again, atomically, inside ``RunRegistry.mark_capability_issued`` under the writer lock.
    """
    if phase not in (Phase.P3A, Phase.P3B):
        return None
    name = "max_p3a_attempts" if phase is Phase.P3A else "max_p3b_attempts"
    spec_limit = getattr(spec, name)
    if type(spec_limit) is not int or spec_limit < 1:
        raise AttemptLimitNotSetError(
            f"p3.{name} is unset in the frozen spec (a P0 decision with no default): "
            f"{phase.value} is refused until the owner sets it"
        )
    manifest.check_limits(spec.max_p3a_attempts, spec.max_p3b_attempts)  # also refuses null
    limit = manifest.max_p3a_attempts if phase is Phase.P3A else manifest.max_p3b_attempts
    if limit is None:  # pragma: no cover - check_limits already refused
        raise AttemptLimitNotSetError("the manifest's attempt limit is unset")
    if limit > MAX_ATTEMPT_LIMIT:
        raise AttemptLimitOutOfRangeError(
            f"the manifest's {phase.value} attempt limit {limit} is above the maximum "
            f"{MAX_ATTEMPT_LIMIT} the registry accepts (fail closed, before any write)"
        )
    used = registry.attempts_consumed(run_id)
    if used >= limit:
        raise AttemptLimitExceededError(
            f"{phase.value} attempt budget exhausted for this registry (all windows): {used} governed "
            f"authorization(s) already issued across all spec hashes, limit {limit} "
            "(failed and aborted runs after authorization count; there is no reset)"
        )
    return limit


def _check_holdout_unopened(
    registry: RunRegistry,
    spec: GuardSpecView,
    run_id: str,
) -> None:
    """The registry, not the token directory, decides whether the holdout was ever opened."""
    runs = registry.runs()
    run = next(r for r in runs if r.run_id == run_id)  # find_open_run ran first
    if run.holdout_range != spec.partitions.holdout:
        raise RunNotRegisteredError(
            f"run {run_id!r} was registered for a different holdout range "
            f"({run.holdout_range and run.holdout_range.as_dict()}) than the spec's "
            f"{spec.partitions.holdout.as_dict()}"
        )
    if run.holdout_authorized_seq is not None:
        raise HoldoutAlreadyOpenedError(
            f"run {run_id!r} was already authorized to open the holdout"
        )
    other = holdout_conflict(runs, run)
    if other is not None:
        raise holdout_conflict_error(run, other)


def authorize(
    *,
    spec: GuardSpecView,
    phase: Phase,
    partition: Partition,
    run_id: str,
    registry: RunRegistry,
    exposure_ledger: ExposureLedger,
    holdout_store: HoldoutTokenStore | None = None,
    holdout_token: object | None = None,
    requested_range: DateRange | None = None,
    predecessor_evidence: Sequence[PredecessorEvidence] = (),
    independence_authorization: str | None = None,
    budget_reset_authorization: str | None = None,
) -> ResultsCapability:
    """Check every precondition and return a capability, or raise a named refusal.

    ``predecessor_evidence`` carries the predecessor runs' artefacts for P3B / P4 (see
    :class:`PredecessorEvidence`). ``independence_authorization`` is accepted only so a request
    carrying one is refused by name, FIRST and always: there is no policy in code that could
    validate it. ``budget_reset_authorization`` is likewise accepted only to be refused by name,
    FIRST: a new attempt budget is design-only and not implemented. P5 is refused outright
    (``PaperApprovalNotImplementedError``).
    """
    # (NF7) no mechanism grants a new attempt budget; refused before anything is read
    if budget_reset_authorization is not None:
        raise BudgetResetNotAcceptedError(
            "a budget_reset_authorization was supplied, but a new attempt budget needs an "
            "independently approved registration, an exposure review and a documented "
            "justification; none of that is implemented, so it is never accepted (fail closed)"
        )
    # (N3) refused before any state is touched, conflict or not
    if independence_authorization is not None:
        raise IndependenceAuthorizationNotAcceptedError(
            "an independence_authorization reference was supplied, but no lineage/independence "
            "policy exists in code to validate it; it is never accepted (fail closed)"
        )
    # (0) + (a) trusted view, frozen and signed
    spec, spec_sha = _spec_checks(spec)
    if type(registry) is not RunRegistry:
        raise RegistryNotTrustedError(f"registry must be exactly RunRegistry, got {type(registry)}")
    if type(exposure_ledger) is not ExposureLedger:
        raise ExposureLedgerNotTrustedError(
            f"exposure_ledger must be exactly ExposureLedger, got {type(exposure_ledger)}"
        )
    if holdout_store is not None and type(holdout_store) is not HoldoutTokenStore:
        raise HoldoutStoreNotTrustedError(
            f"holdout_store must be exactly HoldoutTokenStore, got {type(holdout_store)}"
        )

    # (N1 / N-A) registry genesis == spec genesis == OWNER-APPROVED manifest genesis
    manifest = load_manifest(_MANIFEST_PATH)  # ManifestMissing/Invalid/NotApproved: fail closed
    manifest.require_genesis()
    registry_genesis = registry.genesis_id
    if spec.registry_genesis_id is None or spec.registry_genesis_id != registry_genesis:
        raise RegistryGenesisMismatchError(
            "the spec's governance.registry_genesis_id is unset or does not match the genesis "
            "id of the registry in use (missing, replaced or reinitialized registry)"
        )
    manifest.check_genesis(spec.registry_genesis_id, what="spec")
    manifest.check_genesis(registry_genesis, what="registry")

    # (b) closed partition set, authorized for this phase
    try:
        phase, partition = Phase(phase), Partition(partition)
    except ValueError as exc:
        raise PartitionNotAuthorizedError(f"unknown phase/partition: {exc}") from exc
    if partition not in PHASE_PARTITIONS[phase]:
        raise PartitionNotAuthorizedError(
            f"partition {partition.value} is not authorized for phase {phase.value}"
        )
    if phase is Phase.P5:
        raise PaperApprovalNotImplementedError(
            "P5 (PAPER) is refused: owner approval before paper is Level 2 design-only, no "
            "signed-approval mechanism exists in code, and no approval reference is accepted"
        )
    if requested_range is not None and type(requested_range) is not DateRange:
        raise PartitionNotAuthorizedError("requested_range must be a DateRange")

    # (f) development and holdout runs need D17 / D19 set
    if partition in DEVELOPMENT_PARTITIONS or partition is Partition.HOLDOUT:
        unset = [
            name
            for name in ("p3_criteria", "exits_candidates", "exits_selection")
            if getattr(spec, name, None) is None
        ]
        if unset:
            raise SpecIncompleteError(
                f"{partition.value} run refused while {unset} is unset (D17/D19 not frozen)"
            )

    # (g) phase order, from registry rows and the predecessor artefacts' content
    evidence_digests = _check_phase_order(registry, spec_sha, phase, tuple(predecessor_evidence))

    # Resolve the date range this run would read.
    spec_range = _partition_range(spec, partition)
    if spec_range is not None:
        if requested_range is not None and not spec_range.contains(requested_range):
            raise PartitionNotAuthorizedError(
                "requested date range lies outside the spec's range for "
                f"{partition.value}: {requested_range.as_dict()} vs {spec_range.as_dict()}"
            )
        date_range = requested_range or spec_range
    else:
        if requested_range is None:
            raise PartitionNotAuthorizedError(
                f"{partition.value} has no spec date range; an explicit requested_range is required"
            )
        _check_free_range(spec, partition, requested_range)
        date_range = requested_range

    # (c) exposure
    citable = partition is not Partition.REPLAY_RNG001
    ledger_sha: str | None = None
    if citable:
        if date_range.overlaps(R2_EXCLUDED_WINDOW):
            raise ExposureOverlapError(
                f"{date_range.as_dict()} overlaps the R2-excluded window "
                f"{R2_EXCLUDED_WINDOW.as_dict()}; never usable in a decisive run"
            )
        for exposed in spec.exposed:
            if date_range.overlaps(exposed):
                raise ExposureOverlapError(
                    f"{date_range.as_dict()} overlaps the spec's exposed range {exposed.as_dict()}"
                )
        exposure_ledger.require_signed()
        _check_exposure_binding(spec, exposure_ledger)
        hits = exposure_ledger.overlaps(date_range)
        if hits:
            raise ExposureOverlapError(
                f"{partition.value} overlaps exposure-ledger entries {[h.id for h in hits]}"
            )
        ledger_sha = exposure_ledger.sha256

    # (d) registry row written first
    registry.find_open_run(run_id=run_id, spec_sha256=spec_sha, phase=phase, partition=partition)

    # (N2e) P3A / P3B attempt budget (pre-check; the binding one is atomic in the registry)
    this_run = registry.get_run(run_id)
    if (
        partition is not Partition.HOLDOUT  # a holdout run reports its own, more specific refusal
        and this_run is not None
        and this_run.capability_issued_seq is not None
    ):
        raise CapabilityAlreadyIssuedError(
            f"run {run_id!r} was already authorized; a run is authorized once"
        )
    if phase in (Phase.P3A, Phase.P3B) and (
        this_run is None or this_run.protected_range != spec_range
    ):
        raise RunNotRegisteredError(
            f"run {run_id!r} was registered for a different protected window "
            f"({this_run and this_run.protected_range and this_run.protected_range.as_dict()}) "
            f"than the spec's {spec_range and spec_range.as_dict()}"
        )
    attempt_limit = _check_attempt_limit(registry, spec, manifest, phase, run_id)

    # (e) holdout: the registry is the authority; the token is a second lock
    if partition is Partition.HOLDOUT:
        _check_holdout_unopened(registry, spec, run_id)
        if holdout_store is None:
            raise PartitionNotAuthorizedError("HOLDOUT requires a HoldoutTokenStore")
        token = holdout_store.validate_unused(holdout_token, spec_sha, registry.genesis_id)
        registry.mark_holdout_authorized(run_id)  # durable BEFORE the token is consumed
        holdout_store.consume(token, run_id)

    # (N2a) durable "capability issued" row BEFORE the capability exists
    registry.mark_capability_issued(
        run_id,
        evidence=[
            {"run_id": rid, "audit_pack_sha256": audit, "selection_record_sha256": sel}
            for rid, audit, sel in evidence_digests
        ],
        manifest_sha256=manifest.sha256,
        attempt_limit=attempt_limit,
    )
    capability = ResultsCapability(
        _ISSUE,
        spec_sha256=spec_sha,
        phase=phase,
        partition=partition,
        run_id=run_id,
        date_range=date_range,
        citable=citable,
        exposure_ledger_sha256=ledger_sha,
        evidence_digests=evidence_digests,
    )
    _BOUND_REGISTRIES[capability] = registry
    return capability


__all__ = [
    "PredecessorEvidence",
    "ResultsCapability",
    "authorize",
    "require_capability",
    "requires_capability",
]
