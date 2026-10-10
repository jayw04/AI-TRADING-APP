"""Named, fail-closed refusals for RANGE-002 governance.

Every refusal is a distinct exception type so a caller (and a test) can tell
*which* precondition failed. There is no warn-and-continue branch anywhere in
this package.
"""

from __future__ import annotations


class GovernanceError(RuntimeError):
    """Base class for every RANGE-002 governance refusal."""


# --- results guard (WP0.4) ---------------------------------------------------


class SpecNotFrozenError(GovernanceError):
    """The spec view is missing, malformed or has no valid ``spec_sha256``."""


class SpecNotSignedError(GovernanceError):
    """The spec is not signed (``is_signed`` is not exactly ``True``)."""


class SpecIncompleteError(GovernanceError):
    """A development run was requested while ``p3_criteria``, ``exits_candidates``
    or ``exits_selection`` is unset (plan WP4.1)."""


class PartitionNotAuthorizedError(GovernanceError):
    """Unknown partition, or a partition not authorized for the requested phase."""


class ExposureOverlapError(GovernanceError):
    """The requested partition overlaps exposed data (R2 / WP0.6)."""


class SpecViewNotTrustedError(GovernanceError):
    """``authorize`` was handed something other than the adapter's ``GuardSpecView`` built by
    ``spec_adapter.to_guard_view`` -- a duck-typed or hand-built view is never trusted."""


class CollaboratorNotTrustedError(GovernanceError):
    """``authorize`` was handed an injected collaborator that is not exactly the governed type."""


class RegistryNotTrustedError(CollaboratorNotTrustedError):
    """``registry`` is not exactly a ``RunRegistry`` (no duck-typed or subclassed registry)."""


class ExposureLedgerNotTrustedError(CollaboratorNotTrustedError):
    """``exposure_ledger`` is not exactly an ``ExposureLedger`` built by its loaders."""


class HoldoutStoreNotTrustedError(CollaboratorNotTrustedError):
    """``holdout_store`` is not exactly a ``HoldoutTokenStore``."""


class ExposureBindingError(GovernanceError):
    """The spec's ``governance.exposure_signed`` does not record the sha256 of the exposure
    ledger in use (absent, malformed, or a different ledger)."""


class RangeOverlapsPartitionError(PartitionNotAuthorizedError):
    """A PAPER / REPLAY_RNG001 range overlaps the spec's selection, confirmation or holdout."""


class PaperRangeNotAfterR2Error(PartitionNotAuthorizedError):
    """PAPER must start strictly after the end of the R2 window (2026-07-31)."""


class ReplayRangeOutsideR2Error(PartitionNotAuthorizedError):
    """REPLAY_RNG001 is engine validation on the R2 window only; the range must lie within it."""


class PhaseOrderError(GovernanceError):
    """A later phase was requested without registry evidence that its predecessors COMPLETED
    (P3B needs a completed P3A with a selection record; P4 additionally a completed P3B)."""


class PredecessorEvidenceMissingError(PhaseOrderError):
    """The predecessor run's audit-pack / selection-record artefact was not supplied, or cannot
    be read: registry rows alone do not establish that the predecessor phase passed."""


class PredecessorEvidenceMismatchError(PhaseOrderError):
    """The supplied predecessor artefact does not hash to the digest the registry recorded for
    that run (content-bound, Level 1; the artefact is NOT cryptographically authenticated)."""


class PredecessorEvidenceBindingError(PredecessorEvidenceMismatchError):
    """The supplied predecessor artefact is not bound to the predecessor run: its embedded
    ``run_id`` / ``spec_sha256`` header is missing, malformed, or names a different run or spec
    (round 4, N2c). Content-bound, not authenticated."""


class PredecessorHoldoutNotAuthorizedError(PhaseOrderError):
    """A P4 predecessor has no ``holdout_authorized`` row: it was never authorized to open the
    holdout, so it cannot satisfy a successor's phase order."""


class AttemptLimitError(GovernanceError):
    """Base class for P3A / P3B attempt-limit refusals (round 4, N2e)."""


class AttemptLimitNotSetError(AttemptLimitError):
    """``p3.max_p3a_attempts`` / ``p3.max_p3b_attempts`` is unset in the frozen spec: it is a P0
    decision with no default, so the phase is refused until the owner has set it."""


class AttemptLimitExceededError(AttemptLimitError):
    """The pre-registered budget of governed evaluation runs for this (registry genesis = research
    lineage, phase) is used up. An attempt is consumed once governed authorization is issued (the
    ``capability_issued`` row); it is counted across ALL protected windows, ALL spec hashes, code
    versions and worktrees sharing the registry -- a different, disjoint or later-chosen window
    does NOT start a new budget -- and a failed or aborted run after that still counts."""


class AttemptLimitOutOfRangeError(AttemptLimitError):
    """The manifest's pre-registered attempt limit is above ``MAX_ATTEMPT_LIMIT`` (the one cap
    shared with ``RunRegistry.mark_capability_issued``): refused before any state is written."""


class BudgetResetNotAcceptedError(AttemptLimitError):
    """A ``budget_reset_authorization`` argument was supplied. A new attempt budget would need an
    independently approved registration, an exposure review and a documented justification: that
    process is design-only, NOT implemented, so no such argument is ever accepted (fail closed)."""


class PaperApprovalNotImplementedError(GovernanceError):
    """P5 (PAPER) authorization is refused outright. Owner approval before paper is Level 2
    design-only: no signed-approval mechanism exists in code, so no approval reference can be
    validated and none is accepted (round 4, N2f)."""


class RunNotRegisteredError(GovernanceError):
    """No matching OPEN run_registry row was written first (R8, plan section 6)."""


class InvalidCapabilityError(GovernanceError):
    """A compute entry point was reached without a valid results capability."""


# --- run registry (WP0.7) ----------------------------------------------------


class RegistryIntegrityError(GovernanceError):
    """The on-disk hash chain does not verify: a record was edited, removed or
    inserted, or a second writer advanced the chain."""


class ChainNotNewlineTerminatedError(RegistryIntegrityError):
    """The chain file is non-empty but does not end in a newline: appending would concatenate
    onto a partial last line, so the writer refuses (fail closed; owner-authorized recovery
    procedure required, not implemented)."""


class RegistryNotEnrolledError(GovernanceError):
    """The registry file is missing, empty, or does not begin with a ``registry_genesis`` row.
    Opening a registry never creates one: only ``RunRegistry.enroll_new`` does (N1)."""


class RegistryEnrollmentError(GovernanceError):
    """``RunRegistry.enroll_new`` refused: the file exists, or the directory already holds
    another RANGE-002 registry (a replacement registry is never created implicitly)."""


class EnrolledByTooLongError(RegistryEnrollmentError):
    """``enrolled_by`` is longer than ``MAX_ENROLLED_BY_CHARS`` (an over-long first-row field must
    not be able to hide a registry from the enrolment directory scan)."""


class RegistryGenesisMismatchError(GovernanceError):
    """The spec's ``governance.registry_genesis_id`` is missing or differs from the genesis id of
    the registry in use (or of the holdout token's pairing): a missing, replaced or
    reinitialized registry is refused (N1)."""


class RegistryNamespaceBusyError(RegistryEnrollmentError):
    """The governance-namespace lock (enroll_new) could not be taken in time (fail closed)."""


class RegistryRecordError(GovernanceError):
    """A registry record was offered without a required field, or an illegal
    state transition was attempted (e.g. closing a closed run)."""


class RegistryPayloadError(RegistryRecordError):
    """A value offered to the registry cannot be written as strict canonical JSON (a non-finite
    number, a non-string key, an unsupported type, an oversized or non-round-tripping payload).
    Raised BEFORE any byte is written: the registry file is untouched and stays usable (N-C)."""


class CapabilityAlreadyIssuedError(RegistryRecordError):
    """``authorize`` already issued a capability for this run: a run is authorized once."""


class CapabilityNotIssuedError(RegistryRecordError):
    """``close_run(COMPLETED)`` for a run with no ``capability_issued`` row: the guard never
    authorized it, so it cannot be recorded as having completed (N2a)."""


class EvidenceReuseError(RegistryRecordError):
    """An audit-pack or selection-record digest is already recorded by another run: evidence is
    bound to one run and cannot be reused (N2c)."""


# --- exposure ledger (WP0.6) -------------------------------------------------


class ExposureLedgerError(GovernanceError):
    """The exposure ledger file is malformed (schema violation)."""


class ExposureLedgerNotSignedError(GovernanceError):
    """The exposure ledger carries no sign-off (WP0.6 audit unsigned, D01)."""


# --- holdout token (WP4.2) ---------------------------------------------------


class HoldoutTokenError(GovernanceError):
    """Base class for holdout-token refusals."""


class HoldoutTokenInvalidError(HoldoutTokenError):
    """No token, wrong spec hash, or a token that does not match the store."""


class HoldoutAlreadyOpenedError(HoldoutTokenError):
    """The token was consumed, or a consume was begun and never verified.

    An unverified intent is treated exactly like a consumed token: after a
    crash we cannot prove the holdout was *not* opened, so it is not offered
    again (R3). Re-issue requires the defect-record + owner-approval path,
    which is deliberately not implemented here.
    """


class IndependenceAuthorizationNotAcceptedError(HoldoutAlreadyOpenedError):
    """``authorize`` was called with an ``independence_authorization`` reference. No
    lineage/independence policy exists in code, so the reference cannot be validated and is
    never accepted (fail closed): it is refused first and always, with or without any holdout
    conflict, before any state is touched. Only a future owner-approved policy may enable this."""


class VerdictError(GovernanceError):
    """A verdict string outside the closed set, or an invalid transition."""
