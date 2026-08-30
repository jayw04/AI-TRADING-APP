"""**B2** — the source identity a governed K computation ran under, MEASURED at runtime.

ATP v1.0.2 §2.3 requires the source identity to be recorded in the verdict artifact. It was not
recorded at all, and retrofitting it after a run would make the claim retrospective — so it is
measured here, by the code itself, during the computation.

⛔ **Nothing here accepts an operator assertion.** There is no ``--source-sha``, no
``--approved-sha``, no ``--assume-clean``, no environment override, and no way to supply blob
hashes. An identity the caller can state is not an identity; it is a claim about one.

⛔ The governed entry point `verify_governed_source_identity` takes **no expected-identity
parameter at all**. Comparison logic lives in the pure `compare_source_identity`, which tests
drive with explicit expected identities but which mints nothing and reads no module state. An
earlier revision let the governed function accept ``authority=``; that reopened, in B2, the very
hole B3 closed in the adjudication path.

⚠ **The approval authority is EXTERNAL to the source it approves.**

An earlier revision held the approved identity in a module constant here. That was unusable: this
file is itself one of ``GOVERNED_SOURCE_PATHS``, so writing the constant changed this file's blob
*and* produced a new commit — meaning the verifier would refuse the very runtime the designation was
meant to authorize. Designating the later authority commit instead does not help, because that commit
would have to contain its own commit SHA and its own final blob hash before it exists. It is a
fixed point, not something another CI run resolves.

The approval therefore lives in a separately custodied immutable record at a fixed, non-injectable
path (`AUTHORITY_RECORD_PATH`), which is deliberately **not** part of ``GOVERNED_SOURCE_PATHS``:

    the source being approved  ≠  the record that grants approval

The record has its own custody rule (committed, clean, schema-pinned, and pinning every governed
path). Absent record ⇒ no designated successor ⇒ every governed run refuses.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

#: The exact files whose bytes constitute the K-computation surface. A change to any of these
#: changes what a governed K value means, so the identity binds them individually rather than
#: trusting a commit SHA alone — a commit can be reproduced from a dirty tree, a blob cannot.
#: Paths are relative to ``apps/backend``.
GOVERNED_SOURCE_PATHS: Final[tuple[str, ...]] = (
    "app/research/mdq_eval/__init__.py",
    "app/research/mdq_eval/authority.py",
    "app/research/mdq_eval/gate.py",
    "app/research/mdq_eval/results.py",
    "app/research/mdq_eval/k1_materiality.py",
    "app/research/mdq_eval/k3_completeness.py",
    "app/research/mdq_eval/source_identity.py",
    "app/research/capture/admissibility.py",
    "app/research/capture/store.py",
    "scripts/mdq_evaluate_k.py",
)


class SourceIdentityRefused(RuntimeError):
    """The runtime source state is not one a governed K value may be computed from."""


@dataclass(frozen=True)
class ApprovedComputationIdentity:
    """The owner-designated successor identity. Constructed only from governed code/config.

    ``review_commit`` is **provenance**, not a runtime equality requirement. It names the commit
    at which the ten-file governed surface was reviewed and approved. The runtime HEAD is allowed
    to be later, provided nothing in that surface changed between the two — which is the whole
    point of holding the approval in an external record.
    """

    review_commit: str
    blobs: Mapping[str, str]


#: The immutable authority record that grants approval. It lives OUTSIDE
#: ``GOVERNED_SOURCE_PATHS`` on purpose — see the module docstring for why the previous
#: in-source constant was unusable. The path is a module constant: not a CLI option, not an
#: environment variable, not a caller argument, and not an operator-supplied path.
AUTHORITY_RECORD_PATH: Final = Path("config") / "mdq_k_computation_authority.json"

#: Schema the authority record must declare. A record that does not is not read.
AUTHORITY_RECORD_SCHEMA: Final = "mdq-k-computation-authority/1"


def load_computation_authority(
    backend_root: Path | None = None,
) -> tuple[ApprovedComputationIdentity | None, list[str]]:
    """Read the external authority record. Returns ``(identity_or_None, problems)``.

    ⛔ Absent record ⇒ **no successor identity is designated** ⇒ every governed run refuses.
    That is the default state and it is deliberate: designation is an owner act, and a missing
    file must never read as permission.

    ⚠ The record is itself governed. It must be committed and clean in the worktree; a dirty
    authority record is refused, because an approval that can be edited between review and run
    is not an approval. That is this artifact's own custody rule, distinct from the governed
    source surface it approves.
    """
    root = backend_root or _backend_root()
    path = root / AUTHORITY_RECORD_PATH
    if not path.exists():
        return None, []

    dirty = _git(["status", "--porcelain", "--", str(AUTHORITY_RECORD_PATH)], root)
    if dirty:
        return None, [
            f"the computation authority record {AUTHORITY_RECORD_PATH.as_posix()} is dirty in the "
            f"worktree; an approval that can be edited between review and run is not an approval"
        ]

    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, [f"computation authority record is unreadable: {exc}"]

    if rec.get("schema") != AUTHORITY_RECORD_SCHEMA:
        return None, [
            f"computation authority record declares schema {rec.get('schema')!r}, expected "
            f"{AUTHORITY_RECORD_SCHEMA!r}; refusing to interpret an unrecognised record"
        ]
    commit = rec.get("approved_review_commit")
    blobs = rec.get("approved_governed_source_blobs")
    if not isinstance(commit, str) or not isinstance(blobs, dict) or not blobs:
        return None, ["computation authority record is missing approved_review_commit or blobs"]

    missing = sorted(set(GOVERNED_SOURCE_PATHS) - set(blobs))
    if missing:
        return None, [
            f"computation authority record does not pin every governed source path; missing "
            f"{missing}. A partial pin would leave an unbound file free to change."
        ]
    return ApprovedComputationIdentity(review_commit=commit, blobs=dict(blobs)), []


@dataclass(frozen=True)
class MeasuredSourceIdentity:
    """What the code observed about itself. Never what a caller said about it."""

    commit: str | None
    dirty_governed_paths: tuple[str, ...]
    blobs: Mapping[str, str]
    problems: tuple[str, ...]

    @property
    def measurable(self) -> bool:
        return self.commit is not None and not self.problems

    def as_dict(self) -> dict[str, object]:
        return {
            "commit": self.commit,
            "dirty_governed_paths": list(self.dirty_governed_paths),
            "blobs": dict(sorted(self.blobs.items())),
            "governed_paths": list(GOVERNED_SOURCE_PATHS),
            "problems": list(self.problems),
            "measurable": self.measurable,
        }


def _backend_root() -> Path:
    """``apps/backend``, derived from this file's own location."""
    return Path(__file__).resolve().parents[3]


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


def _git_exit(args: list[str], cwd: Path) -> int | None:
    """Exit status of a git command, or None if git could not be run at all.

    ⚠ Distinct from `_git`, which returns None for ANY non-zero status. `merge-base
    --is-ancestor` signals its answer THROUGH the exit code -- 0 ancestor, 1 not an ancestor,
    anything else an error -- so collapsing those would turn "not an ancestor" into "git broke"
    and lose the fail-closed distinction.
    """
    try:
        out = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=30, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.returncode


def review_commit_is_ancestor(
    review_commit: str, backend_root: Path | None = None
) -> tuple[bool | None, list[str]]:
    """Is the approved reviewed commit an ancestor of the runtime HEAD?

    ★ Required before the governed-path delta check means what it claims. `git diff A HEAD`
    compares two ENDPOINTS; it establishes nothing about lineage. A divergent or unrelated commit
    that happens to carry the same ten governed files would produce an empty delta, and the verdict
    would then assert "the runtime advanced only through non-governed changes" without that ever
    having been established. The blob pins still prove byte equivalence, so this is a provenance
    overclaim rather than an integrity hole -- but a verdict that overclaims is the thing this whole
    tranche exists to prevent.

    Returns ``(True, [])`` / ``(False, reasons)`` / ``(None, reasons)`` for unmeasurable.
    """
    root = backend_root or _backend_root()
    code = _git_exit(["merge-base", "--is-ancestor", review_commit, "HEAD"], root)
    if code == 0:
        return True, []
    if code == 1:
        return False, [
            f"source identity refused: the approved review commit {review_commit} is NOT an "
            f"ancestor of the runtime HEAD; the runtime is on a divergent history, so no claim "
            f"about advancing only through non-governed changes can be made"
        ]
    return None, [
        f"source identity refused: cannot establish whether {review_commit} is an ancestor of the "
        f"runtime HEAD (git unavailable, or the commit is absent from this runtime)"
    ]


def measure_source_identity(backend_root: Path | None = None) -> MeasuredSourceIdentity:
    """Measure the running source state. Reports problems rather than raising.

    ⚠ Blob hashes are of the **raw on-disk bytes**, deliberately un-normalised. The governed
    source contract is LF-only, so for a conforming file the raw bytes ARE the git blob bytes
    and the hash is directly comparable to a git blob.

    ⛔ An earlier revision stripped CR before hashing so a CRLF deployment would still match.
    That was backwards: it made the identity check *more permissive* to tolerate a deployment
    quirk, and would have hidden a genuine source change involving CR bytes inside a string or
    data literal. Unexpected CR is now a source identity FAILURE. If a deployment produces
    CRLF, that deployment is not a governed computation runtime.
    """
    root = backend_root or _backend_root()
    problems: list[str] = []

    commit = _git(["rev-parse", "HEAD"], root)
    if commit is None:
        problems.append(
            "source identity is UNMEASURABLE: git is unavailable, or this tree is not a repository "
            "(a deployed tarball has no .git). A governed K value may not be computed from a "
            "runtime whose code identity cannot be observed."
        )

    dirty: list[str] = []
    status = _git(["status", "--porcelain", "--", *GOVERNED_SOURCE_PATHS], root)
    if status is None and commit is not None:
        problems.append("could not determine worktree cleanliness for the governed paths")
    elif status:
        for line in status.splitlines():
            path = line[3:].strip().strip('"')
            if path:
                dirty.append(path)

    blobs: dict[str, str] = {}
    for rel in GOVERNED_SOURCE_PATHS:
        p = root / rel
        if not p.exists():
            problems.append(f"governed source path missing from the runtime: {rel}")
            continue
        data = p.read_bytes()
        if b"\r" in data:
            problems.append(
                f"governed source file contains CR bytes, but the governed contract is "
                f"LF-only: {rel}. Refusing rather than normalising: stripping CR would "
                f"also mask a genuine change to CR bytes inside a string or data literal."
            )
            continue
        blobs[rel] = hashlib.sha256(data).hexdigest()

    return MeasuredSourceIdentity(
        commit=commit,
        dirty_governed_paths=tuple(sorted(dirty)),
        blobs=blobs,
        problems=tuple(problems),
    )


def compare_source_identity(
    measured: MeasuredSourceIdentity, expected: ApprovedComputationIdentity
) -> list[str]:
    """Pure comparison. Returns refusal reasons; empty means the runtime matches ``expected``.

    ⚠ This is the ONLY place an expected identity may be supplied, and it is deliberately NOT the
    governed path: it mints nothing, reads no module state, and reaches no partition. Tests exercise
    the comparison logic here with explicit expected identities; production reaches the frozen
    authority through `verify_governed_source_identity`, which takes no such argument.
    """
    reasons: list[str] = []
    if measured.problems:
        reasons.append(f"source identity refused: {'; '.join(measured.problems)}")
    if measured.dirty_governed_paths:
        reasons.append(
            "source identity refused: governed paths are dirty in the worktree "
            f"{list(measured.dirty_governed_paths)}; a governed K value may not be computed from "
            "uncommitted code, because the recorded commit would not describe what actually ran"
        )
    # ⛔ Whole-repository HEAD equality is deliberately NOT required. Committing the external
    # authority record necessarily advances HEAD past the reviewed commit, so demanding equality
    # would refuse every runtime the designation was meant to authorize -- the commit-level twin
    # of the source-level cycle this design already removed. The governed identity is the ten-file
    # surface; the runtime commit is recorded as provenance and checked for governed-path
    # equivalence by `governed_paths_changed_since`, which needs git and so is not done here.
    mismatched = sorted(
        rel for rel, want in expected.blobs.items() if measured.blobs.get(rel) != want
    )
    if mismatched:
        reasons.append(
            "source identity refused: MIXED source state — the governed source bytes do not "
            f"match the approved reviewed source tuple: {mismatched}. Byte equivalence over the "
            "governed surface is the identity; a commit-only check would wave this through"
        )
    return reasons


def governed_paths_changed_since(
    review_commit: str, backend_root: Path | None = None
) -> tuple[list[str] | None, list[str]]:
    """Which governed paths differ between ``review_commit`` and the runtime HEAD.

    Returns ``(changed_paths, problems)``. ``changed_paths == []`` means the ten-file governed
    surface is unchanged since the reviewed commit, so the runtime HEAD may legitimately be later.

    ✅ This is what permits the intended sequence: merge the hardening, approve the reviewed
    ten-file tuple, then commit the authority record. That custody commit advances HEAD **outside**
    the governed surface, which this check allows and a HEAD-equality check would not.
    """
    root = backend_root or _backend_root()
    out = _git(
        ["diff", "--name-only", review_commit, "HEAD", "--", *GOVERNED_SOURCE_PATHS], root
    )
    if out is None:
        return None, [
            f"cannot determine whether the governed surface changed since {review_commit}: git is "
            f"unavailable, or that commit is not present in this runtime"
        ]
    changed = [line.strip() for line in out.splitlines() if line.strip()]
    return changed, []


def verify_governed_source_identity(backend_root: Path | None = None) -> dict[str, object]:
    """The production entry point. Fail closed unless the runtime IS the approved identity.

    ⛔ There is deliberately **no parameter for the expected identity** — it is read only from the
    frozen module constant. An earlier revision accepted ``authority=`` so tests could inject one;
    that reopened in B2 exactly the hole B3 closed in the adjudication path. A governed function
    whose authority the caller supplies is not governed, and "only tests would pass it" is the same
    argument that once made ``**assess_kwargs`` look acceptable.

    ``backend_root`` is a filesystem location, not an authority: it cannot change WHAT is required,
    only WHERE the runtime is read from, and a wrong root fails closed as unmeasurable.
    """
    measured = measure_source_identity(backend_root)
    expected, authority_problems = load_computation_authority(backend_root)

    if authority_problems:
        raise SourceIdentityRefused(" | ".join(authority_problems))

    if expected is None:
        raise SourceIdentityRefused(
            "no successor governed K-computation identity is designated, so no governed K value may "
            "be computed. The prior #696 identity carries the evidentiary-boundary defect this "
            "hardening closes, and this branch holds no authority of its own; designation is a "
            "separate owner act on an exact reviewed head. Measured runtime: "
            f"{measured.commit or 'UNMEASURABLE'}."
        )

    reasons = compare_source_identity(measured, expected)

    is_ancestor, ancestry_problems = review_commit_is_ancestor(
        expected.review_commit, backend_root
    )
    reasons.extend(ancestry_problems)

    changed, delta_problems = governed_paths_changed_since(expected.review_commit, backend_root)
    reasons.extend(delta_problems)
    if changed:
        reasons.append(
            f"source identity refused: the governed surface changed since the approved review "
            f"commit {expected.review_commit}: {sorted(changed)}. The runtime HEAD may advance "
            f"ONLY through changes outside GOVERNED_SOURCE_PATHS."
        )

    if reasons:
        raise SourceIdentityRefused(" | ".join(reasons))

    return {
        # Three distinct facts. The runtime commit is provenance, not an equality requirement.
        "approved_review_commit": expected.review_commit,
        "runtime_commit": measured.commit,
        "governed_source_identity_verified": True,
        "governed_paths_unchanged_since_review": True,
        "review_commit_is_ancestor_of_runtime": is_ancestor,
        "measured": measured.as_dict(),
    }
