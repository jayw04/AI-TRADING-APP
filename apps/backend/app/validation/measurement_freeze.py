"""The measurement-instrument freeze — expected identity held OUTSIDE the tree it pins.

## Why the pin cannot live in the source it pins

The prereg originally froze the measurement instrument as a constant *inside*
``app/validation/forward_window.py``:

    VALIDATION_MEASUREMENT_COMMIT = "764883b5…"

That is a fixed point with no solution. Changing the constant produces a new commit, so the constant
can never name the commit that contains it; chasing it produces an infinite regress. The binding was
therefore guaranteed to drift, and it did — 28 authorized commits moved the measurement code past the
frozen SHA, and the frozen SHA predates `governed_corpus`, `security_lineage` and `data_finality`
entirely, so the pinned code cannot even load the corpus the program now requires.

Worse, ``build_forward_context`` defaulted the ACTUAL commit to the EXPECTED constant, so unless a
caller overrode it the gate compared the constant to itself and passed unconditionally. A check that
cannot fail is not a check.

## The replacement

The expected identity lives in a governed manifest OUTSIDE the digested tree
(``manifests/forward/measurement_freeze.json``). Editing the manifest does not change the validation
tree, so there is no regress, and the expected and actual values can genuinely disagree.

Two bindings, because neither alone is sufficient:

``measurement_commit``   the last ratified measurement-code commit. Required to be an ANCESTOR of the
                         deployed HEAD — it proves the deployment descends from ratified history. It
                         is deliberately NOT required to equal the HEAD: a later documentation- or
                         manifest-only commit changes the HEAD without changing executable content.

``validation_tree_sha256``  the CONTROLLING identity: an exact digest over the executable measurement
                         content. Ancestry alone would admit any descendant, including one that
                         rewrote the verifier; exact content equality does not.

The included path set is defined POSITIVELY (:data:`MEASURED_PATHS`) rather than as
"everything except the manifest". A carve-out invites the question of what else was carved out; a
positive list can be read and checked. The manifest is not in the set because it lives in a different
tree, not because it was excluded.

## Two questions, two answers

**Content identity** (`TREE_IDENTITY_ALGORITHM`) asks "is this the ratified SOURCE?". It is
newline-canonical, because git stores LF and a Windows checkout materializes CRLF — the same source
must not have two identities, or no single manifest could describe both.

**Transport integrity** (`verify_deployment_bytes`) asks "did checkout or archive processing alter the
committed BYTES?". It compares the deployment against an authoritative per-file byte manifest, so it
catches ANY transformation — re-encoding, BOM insertion, whitespace stripping, a substituted file —
not merely the one we have already seen.

A deployment can be semantically correct and byte-altered at once. That is exactly what happened here:
`git archive` under ``core.autocrlf=true`` rewrote 581 of 592 deployed ``.py`` files, the runtime ran
fine (Python tolerates CRLF), and the bytes were not the committed bytes. One check would have hidden
it; two report it precisely. A Windows working tree may satisfy the identity while failing the byte
check — correct, since only the deployed artifact must satisfy the transport condition.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Schema versions this loader accepts. A superseded manifest is REFUSED, never best-effort parsed.
SUPPORTED_SCHEMA_VERSIONS = frozenset({"1.0"})

#: The ONE canonicalization contract, named and versioned so a manifest states which rules produced
#: its digest. Changing any rule below requires a new version and a new manifest — the algorithm is
#: part of the binding, not an implementation detail.
#:
#:   * include only the positively enumerated measured files (`MEASURED_PATHS`, `*.py`);
#:   * sort paths deterministically (byte order of the POSIX relative path);
#:   * bind BOTH the relative path and the normalized content, so a rename moves the digest;
#:   * normalize CRLF -> LF and NOTHING ELSE;
#:   * do NOT trim whitespace, do NOT normalize Unicode, do NOT strip a BOM — a BOM is content;
#:   * REJECT a lone CR (an old-Mac ending, or a half-converted file) rather than normalizing it;
#:   * REJECT undecodable text rather than replacing bytes with U+FFFD;
#:   * preserve final-newline presence — "ends with a newline" is content;
#:   * preserve file membership — adding or removing a measured file moves the digest.
TREE_IDENTITY_ALGORITHM = "PATH_SORTED_SHA256_CRLF_TO_LF_V1"

#: The executable measurement content, defined POSITIVELY. Every `.py` reachable under these roots is
#: digested; nothing else is. Adding a module to the measurement path set is a governed change that
#: moves the digest, which is the intended behaviour.
MEASURED_PATHS = ("app/validation",)

MANIFEST_RELPATH = "manifests/forward/measurement_freeze.json"


class MeasurementFreezeError(Exception):
    """The freeze manifest is absent, unreadable, of an unsupported schema, or does not describe the
    running deployment. FAILS CLOSED — a session whose measurement identity cannot be established is
    never run."""


def canonicalize(raw: bytes, rel: str) -> bytes:
    """Apply `TREE_IDENTITY_ALGORITHM` to one file's bytes. Refuses rather than repairs.

    ⚠ The refusals are the point. Silently normalizing a lone CR, or decoding with `errors="replace"`,
    would let two DIFFERENT sources produce the SAME identity — which is precisely the property a
    content identity must not have.
    """
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MeasurementFreezeError(
            f"{rel} is not decodable UTF-8 ({exc.reason} at byte {exc.start}); measured content is "
            f"refused, never re-encoded with replacement characters") from exc
    normalized = raw.replace(b"\r\n", b"\n")
    if b"\r" in normalized:
        raise MeasurementFreezeError(
            f"{rel} contains a lone CR after CRLF normalization — an old-Mac or half-converted line "
            f"ending. It is refused rather than normalized, because normalizing it would give two "
            f"different sources the same identity")
    return normalized


def tree_identity(entries: Iterable[tuple[str, bytes]]) -> str:
    """The canonical digest over `(relative_path, raw_bytes)` pairs — the ONE implementation.

    Both sides of the contract call this: the runtime supplies entries read from disk, the generator
    supplies entries read from git blobs. A second implementation, however carefully transcribed, is a
    second thing that can drift.
    """
    lines: list[str] = []
    for rel, raw in sorted(entries, key=lambda e: e[0]):
        lines.append(f"{rel}\0{hashlib.sha256(canonicalize(raw, rel)).hexdigest()}\n")
    if not lines:
        raise MeasurementFreezeError("no measured content to identify")
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def measured_entries(root: Path, paths: tuple[str, ...] = MEASURED_PATHS
                     ) -> list[tuple[str, bytes]]:
    """Every measured file under `root`, as `(posix relative path, raw bytes)`."""
    out: list[tuple[str, bytes]] = []
    for rel in paths:
        base = root / rel
        if not base.is_dir():
            raise MeasurementFreezeError(
                f"measured path {rel!r} is absent under {root} — the runtime does not carry the "
                f"measurement modules")
        for f in sorted(base.rglob("*.py")):
            if "__pycache__" in f.parts:
                continue
            out.append((f.relative_to(root).as_posix(), f.read_bytes()))
    return out


def validation_tree_digest(root: Path, paths: tuple[str, ...] = MEASURED_PATHS) -> str:
    """Digest the executable measurement content under `root`.

    `root` is the runtime root that CONTAINS the measured paths (the extracted archive, or
    ``apps/backend`` in a checkout). The digest covers `path\\0<sha256 of bytes>\\n` per file, sorted
    by path, so it is stable across filesystems and independent of mtimes, ownership and directory
    order.
    """
    return tree_identity(measured_entries(root, paths))


@dataclass(frozen=True)
class MeasurementFreeze:
    """The expected measurement identity, as loaded from the governed manifest."""
    manifest_schema_version: str
    validation_tree_identity_algorithm: str
    measurement_commit: str
    validation_tree_sha256: str
    supersedes_measurement_commit: str
    ratified_increment_inventory_sha256: str
    amendment_sha256: str
    measured_paths: tuple[str, ...]
    #: Digest of the authoritative per-file BYTE manifest — the transport check's reference.
    byte_manifest_sha256: str
    manifest_sha256: str

    def to_open_provenance(self) -> dict[str, Any]:
        return {
            "manifest_schema_version": self.manifest_schema_version,
            "validation_tree_identity_algorithm": self.validation_tree_identity_algorithm,
            "measurement_commit": self.measurement_commit,
            "validation_tree_sha256": self.validation_tree_sha256,
            "supersedes_measurement_commit": self.supersedes_measurement_commit,
            "ratified_increment_inventory_sha256": self.ratified_increment_inventory_sha256,
            "amendment_sha256": self.amendment_sha256,
            "measured_paths": list(self.measured_paths),
            "byte_manifest_sha256": self.byte_manifest_sha256,
            "manifest_sha256": self.manifest_sha256,
        }


def load_measurement_freeze(path: Path) -> MeasurementFreeze:
    """Load and validate the governed freeze manifest. Refuses anything it cannot fully understand."""
    if not path.exists():
        raise MeasurementFreezeError(f"the measurement-freeze manifest is absent at {path}")
    raw = path.read_bytes()
    try:
        d = json.loads(raw)
    except Exception as exc:
        raise MeasurementFreezeError(f"{path} is not readable JSON: {exc}") from exc

    version = str(d.get("manifest_schema_version", ""))
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise MeasurementFreezeError(
            f"measurement-freeze manifest schema {version!r} is not supported "
            f"(this runtime accepts {sorted(SUPPORTED_SCHEMA_VERSIONS)}) — a superseded manifest is "
            f"refused, never reinterpreted")
    algorithm = str(d.get("validation_tree_identity_algorithm", ""))
    if algorithm != TREE_IDENTITY_ALGORITHM:
        raise MeasurementFreezeError(
            f"the manifest names identity algorithm {algorithm!r} but this runtime implements "
            f"{TREE_IDENTITY_ALGORITHM!r}; the algorithm is part of the binding, so a digest produced "
            f"by different rules is not comparable")
    required = ("measurement_commit", "validation_tree_sha256", "supersedes_measurement_commit",
                "ratified_increment_inventory_sha256", "amendment_sha256", "measured_paths",
                "byte_manifest_sha256")
    missing = [k for k in required if not d.get(k)]
    if missing:
        raise MeasurementFreezeError(f"{path} carries no {', '.join(missing)}")

    measured = tuple(str(p) for p in d["measured_paths"])
    if measured != MEASURED_PATHS:
        raise MeasurementFreezeError(
            f"the manifest measures {measured} but this runtime measures {MEASURED_PATHS}; the two "
            f"do not describe the same executable content")
    return MeasurementFreeze(
        manifest_schema_version=version,
        validation_tree_identity_algorithm=algorithm,
        measurement_commit=str(d["measurement_commit"]),
        validation_tree_sha256=str(d["validation_tree_sha256"]),
        supersedes_measurement_commit=str(d["supersedes_measurement_commit"]),
        ratified_increment_inventory_sha256=str(d["ratified_increment_inventory_sha256"]),
        amendment_sha256=str(d["amendment_sha256"]),
        measured_paths=measured,
        byte_manifest_sha256=str(d["byte_manifest_sha256"]),
        manifest_sha256=hashlib.sha256(raw).hexdigest())


def _ancestry_from_git(ancestor: str, descendant: str, repo: Path) -> bool | None:
    """True/False when git can answer, None when there is no repository to ask."""
    if not (repo / ".git").exists():
        return None
    try:
        r = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor",
                            ancestor, descendant], capture_output=True, timeout=30)
    except Exception:
        return None
    return r.returncode == 0


def _ancestry_from_deployment(marker: Path, ancestor: str, descendant: str) -> bool:
    """The deploy-time ancestry attestation, for runtimes with no repository.

    ⚠ Recorded by the build host, which DID have git. It is a secondary check: the controlling
    identity is the tree digest, which is verified from actual content and cannot be asserted by a
    marker. A marker that does not name BOTH commits is refused.
    """
    if not marker.exists():
        return False
    try:
        d = json.loads(marker.read_bytes())
    except Exception:
        return False
    return (str(d.get("measurement_commit", "")) == ancestor
            and str(d.get("deployed_head", "")) == descendant
            and d.get("is_ancestor") is True)


def byte_manifest(entries: Iterable[tuple[str, bytes]]) -> dict[str, str]:
    """RAW per-file digests — the authoritative byte source a deployment is compared against.

    Distinct from the content identity above and deliberately NOT normalized: this answers "did
    checkout or archive processing alter the committed bytes?", which is a transport question. The
    identity answers "is this the ratified source?", which is a semantic one. A deployment can be
    semantically correct and byte-altered at the same time — that is exactly the CRLF defect — so the
    two questions need two answers.
    """
    return {rel: hashlib.sha256(raw).hexdigest() for rel, raw in entries}


def verify_deployment_bytes(root: Path, expected: dict[str, str],
                            paths: tuple[str, ...] = MEASURED_PATHS) -> list[str]:
    """Compare the deployed files byte-for-byte against the authoritative manifest.

    ⚠ A general transport check, NOT a carriage-return scan. Scanning for CR would catch only the one
    transformation we have already seen; comparing against committed bytes catches ANY of them —
    re-encoding, BOM insertion, trailing-whitespace stripping, smudge filters, or a substituted file.
    """
    fails: list[str] = []
    actual = byte_manifest(measured_entries(root, paths))
    for rel in sorted(set(expected) | set(actual)):
        want, got = expected.get(rel), actual.get(rel)
        if want is None:
            fails.append(f"{rel} is present in the deployment but not in the byte manifest")
        elif got is None:
            fails.append(f"{rel} is in the byte manifest but absent from the deployment")
        elif want != got:
            fails.append(f"{rel} bytes differ from the committed source "
                         f"({got[:12]}… != {want[:12]}…) — the build altered the file")
    return fails


def verify_deployment(
    freeze: MeasurementFreeze,
    *,
    actual_commit: str,
    runtime_root: Path,
    repo_root: Path | None = None,
    ancestry_marker: Path | None = None,
    expected_bytes: dict[str, str] | None = None,
) -> list[str]:
    """Every reason the running deployment is NOT the frozen measurement instrument.

    Empty list == the deployment matches. Returned as reasons rather than a boolean so the gate can
    state WHICH binding failed.
    """
    fails: list[str] = []
    actual = (actual_commit or "").strip()
    if not actual:
        fails.append("no actual deployed commit was supplied — the measurement identity of the "
                     "running code is unknown and cannot be assumed")
        return fails

    # ── the CONTROLLING identity: exact executable content ──
    try:
        got = validation_tree_digest(runtime_root, freeze.measured_paths)
    except MeasurementFreezeError as exc:
        fails.append(str(exc))
        got = ""
    if got and got != freeze.validation_tree_sha256:
        fails.append(f"validation-tree digest {got[:16]}… != frozen {freeze.validation_tree_sha256[:16]}… "
                     f"— the running measurement content is not the ratified content")

    # ── transport integrity: are the deployed bytes the COMMITTED bytes? ──
    #
    # A separate question from the content identity, answered against an authoritative per-file byte
    # manifest rather than by scanning for one known transformation. A CR scan would catch only the
    # defect we have already seen; this catches any build that altered a file.
    if expected_bytes is not None:
        fails.extend(verify_deployment_bytes(runtime_root, expected_bytes, freeze.measured_paths))

    # ── ancestry: the deployment must descend from ratified history ──
    if actual.startswith(freeze.measurement_commit) or freeze.measurement_commit.startswith(actual):
        return fails                       # the deployed HEAD IS the ratified commit
    verdict = _ancestry_from_git(freeze.measurement_commit, actual, repo_root or runtime_root)
    if verdict is None and ancestry_marker is not None:
        verdict = _ancestry_from_deployment(ancestry_marker, freeze.measurement_commit, actual)
    if verdict is None:
        fails.append(
            f"ancestry of {freeze.measurement_commit[:12]}… in {actual[:12]}… could not be verified: "
            f"no git repository and no deploy-time ancestry attestation. The check FAILS CLOSED "
            f"rather than assuming a descendant")
    elif verdict is False:
        fails.append(f"the ratified measurement commit {freeze.measurement_commit[:12]}… is NOT an "
                     f"ancestor of the deployed HEAD {actual[:12]}… — the deployment does not "
                     f"descend from ratified history")
    return fails
