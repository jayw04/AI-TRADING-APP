"""Owner-approved RANGE-002 governance manifest (Round 5, finding N-A).

The manifest is a small committed, strict-JSON file that records the two facts the spec itself
must not be able to choose for itself:

* ``approved_registry_genesis_id``: the one run-registry genesis (a canonical lowercase UUIDv4:
  an identity marker for the research lineage, NOT authentication) the OWNER approved; and
* ``p3_attempt_limits``: the PRE-REGISTERED P3A / P3B budgets of governed EVALUATION RUNS (one
  authorized run evaluates all frozen exit candidates and baselines together). These are run
  counts, NOT trade-count minimums (the D17 sample-size numbers are a separate, undecided matter).

Both are intended to change only through a reviewed git change (a process control, not enforced by
this code). Every value
ships UNSET (``null``); this module never invents, defaults or approves one. An unset or partly
set manifest means "not approved", and every consumer (``freeze_spec`` here; the results guard in the PR that
adds governance) refuses to proceed on it.

Where it lives: a FIXED repo-relative path (:data:`MANIFEST_RELPATH`). The CLI and the default
loader read only that path. ``load_manifest(path)`` and ``freeze(..., manifest_path=)`` are public
Python APIs that accept a path as a TEST SEAM; they are not a defence against a caller who can
run arbitrary Python (Level 2).

Threat model (Level 1: accidental misuse, casual bypass, crashes, wrong paths). What this defends:
a spec or a registry that carries a genesis id the owner did not approve (a new directory with a
freshly enrolled registry, a re-enrolled replacement, a re-freeze with a different genesis)
cannot freeze or authorize, unless the committed manifest is changed. What it does NOT defend
(Level 2, design only): anyone with filesystem access can edit the manifest on disk, or COPY an
approved registry (a copy keeps its genesis id, and that is undetectable without an external
anchor such as a signed or remotely held head). The manifest hash is recorded so a later audit can
see which manifest authorized a run; it is not an authenticated signature.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app.research.range002.spec.genesis import is_canonical_uuid4
from app.research.range002.spec.hashing import CanonicalisationError, content_sha256, loads_strict
from app.research.range002.spec.limits import MAX_ATTEMPT_LIMIT

#: Repo-relative location of the committed manifest. Not caller-supplied in production.
MANIFEST_RELPATH = "docs/implementation/evidence/range_002/RANGE-002_governance_manifest.json"
MANIFEST_SCHEMA_VERSION = 1
MAX_MANIFEST_BYTES = 64 * 1024
#: ``apps/backend/app/research/range002/spec/manifest.py`` -> repository root.
_REPO_ROOT = Path(__file__).resolve().parents[6]
DEFAULT_MANIFEST_PATH = _REPO_ROOT / MANIFEST_RELPATH

_KEYS = frozenset(
    {
        "schema_version",
        "approved_registry_genesis_id",
        "approved_by",
        "approved_on",
        "p3_attempt_limits",
        "notes",
    }
)
_LIMIT_KEYS = frozenset({"p3a", "p3b"})


class ManifestError(ValueError):
    """Base class for governance-manifest refusals (all fail closed)."""


class ManifestMissingError(ManifestError):
    """The manifest file is absent, unreadable, oversized or a symlink."""


class ManifestInvalidError(ManifestError):
    """The manifest is not strict JSON of the expected shape."""


class ManifestNotApprovedError(ManifestError):
    """The manifest parses but the owner has not approved the needed value (it is null)."""


class ManifestGenesisMismatchError(ManifestError):
    """A genesis id (spec or registry) differs from the owner-approved manifest genesis."""


class ManifestLimitMismatchError(ManifestError):
    """A spec attempt limit differs from the manifest's pre-registered limit."""


@dataclass(frozen=True)
class GovernanceManifest:
    schema_version: int
    approved_registry_genesis_id: str | None
    approved_by: str | None
    approved_on: date | None
    max_p3a_attempts: int | None
    max_p3b_attempts: int | None
    notes: str
    sha256: str  # canonical-JSON sha256 of the parsed payload (key order / whitespace agnostic)

    @property
    def is_genesis_approved(self) -> bool:
        return (
            self.approved_registry_genesis_id is not None
            and self.approved_by is not None
            and self.approved_on is not None
        )

    def require_genesis(self) -> str:
        """The approved genesis id, or :class:`ManifestNotApprovedError` (fail closed on null)."""
        if not self.is_genesis_approved or self.approved_registry_genesis_id is None:
            raise ManifestNotApprovedError(
                "governance manifest has no owner-approved registry genesis id "
                "(approved_registry_genesis_id / approved_by / approved_on are unset)"
            )
        return self.approved_registry_genesis_id

    def require_limits(self) -> tuple[int, int]:
        """The pre-registered (P3A, P3B) limits, or :class:`ManifestNotApprovedError`."""
        if self.max_p3a_attempts is None or self.max_p3b_attempts is None:
            raise ManifestNotApprovedError(
                "governance manifest has no pre-registered p3_attempt_limits (p3a / p3b unset)"
            )
        return self.max_p3a_attempts, self.max_p3b_attempts

    def check_genesis(self, genesis_id: str | None, *, what: str) -> None:
        """Require ``genesis_id`` to equal the approved genesis (null on either side refuses)."""
        approved = self.require_genesis()
        if genesis_id != approved:
            raise ManifestGenesisMismatchError(
                f"{what} genesis id {genesis_id!r} is not the owner-approved manifest genesis "
                f"{approved!r}"
            )

    def check_limits(self, max_p3a: int | None, max_p3b: int | None) -> None:
        """Require the spec's attempt limits to equal the pre-registered ones."""
        p3a, p3b = self.require_limits()
        if max_p3a != p3a or max_p3b != p3b:
            raise ManifestLimitMismatchError(
                f"spec p3 attempt limits (p3a={max_p3a!r}, p3b={max_p3b!r}) differ from the "
                f"pre-registered manifest limits (p3a={p3a}, p3b={p3b})"
            )


def _limit(value: Any, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_ATTEMPT_LIMIT:
        raise ManifestInvalidError(
            f"p3_attempt_limits.{name} must be null or an integer in 1..{MAX_ATTEMPT_LIMIT}"
        )
    return value


def _str_or_none(value: Any, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ManifestInvalidError(f"{name} must be null or a non-blank string")
    return value


def parse_manifest(payload: Any) -> GovernanceManifest:
    """Validate a decoded manifest payload (strict shape, consistent approval state)."""
    if not isinstance(payload, dict):
        raise ManifestInvalidError("manifest must be a JSON object")
    keys = set(payload)
    if keys != _KEYS:
        raise ManifestInvalidError(
            f"manifest keys must be exactly {sorted(_KEYS)}; "
            f"missing={sorted(_KEYS - keys)} unknown={sorted(keys - _KEYS)}"
        )
    version = payload["schema_version"]
    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or version != MANIFEST_SCHEMA_VERSION
    ):
        raise ManifestInvalidError(f"schema_version must be {MANIFEST_SCHEMA_VERSION}")
    genesis = payload["approved_registry_genesis_id"]
    if genesis is not None and not is_canonical_uuid4(genesis):
        raise ManifestInvalidError(
            "approved_registry_genesis_id must be null or a canonical lowercase UUIDv4"
        )
    approved_by = _str_or_none(payload["approved_by"], "approved_by")
    approved_on_raw = payload["approved_on"]
    approved_on: date | None = None
    if approved_on_raw is not None:
        if not isinstance(approved_on_raw, str):
            raise ManifestInvalidError("approved_on must be null or an ISO date string")
        try:
            if len(approved_on_raw) != 10:
                raise ValueError("expected YYYY-MM-DD")
            approved_on = date.fromisoformat(approved_on_raw)
        except ValueError as exc:
            raise ManifestInvalidError(f"approved_on is not an ISO date: {exc}") from exc
        if approved_on > date.today():
            raise ManifestInvalidError("approved_on is in the future")
    # Approval is all-or-nothing: a genesis without an approver and date is NOT approved, and an
    # approver/date without a genesis is an inconsistent file. Both are refused outright.
    if len({genesis is None, approved_by is None, approved_on is None}) != 1:
        raise ManifestInvalidError(
            "approved_registry_genesis_id, approved_by and approved_on must be all null "
            "(unset) or all set (approved)"
        )
    limits = payload["p3_attempt_limits"]
    if not isinstance(limits, dict) or set(limits) != _LIMIT_KEYS:
        raise ManifestInvalidError("p3_attempt_limits must be an object with exactly p3a and p3b")
    notes = payload["notes"]
    if not isinstance(notes, str):
        raise ManifestInvalidError("notes must be a string")
    return GovernanceManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        approved_registry_genesis_id=genesis,
        approved_by=approved_by,
        approved_on=approved_on,
        max_p3a_attempts=_limit(limits["p3a"], "p3a"),
        max_p3b_attempts=_limit(limits["p3b"], "p3b"),
        notes=notes,
        sha256=content_sha256(payload),
    )


def load_manifest(path: Path | None = None) -> GovernanceManifest:
    """Load the committed manifest (fixed path) or, for tests only, the file at ``path``.

    Raises :class:`ManifestMissingError` / :class:`ManifestInvalidError`. An UNSET manifest loads
    fine (it is the shipped state); consumers call ``require_*`` / ``check_*`` to refuse on it.
    """
    target = DEFAULT_MANIFEST_PATH if path is None else Path(path)
    try:
        if target.is_symlink() or not target.is_file():
            raise ManifestMissingError(f"governance manifest not found: {target}")
        if target.stat().st_size > MAX_MANIFEST_BYTES:
            raise ManifestMissingError(f"governance manifest exceeds {MAX_MANIFEST_BYTES} bytes")
        raw = target.read_bytes()
    except OSError as exc:
        raise ManifestMissingError(f"governance manifest unreadable: {exc}") from exc
    try:
        payload = loads_strict(raw)
    except CanonicalisationError as exc:
        raise ManifestInvalidError(f"governance manifest is not strict JSON: {exc}") from exc
    return parse_manifest(payload)


# Manifest handling computes no returns; declared for the range002 import-lint.
PURE_FUNCTIONS = ("parse_manifest", "load_manifest")
