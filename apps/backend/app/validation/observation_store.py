"""Forward-validation observation STORE — the one atomic commit protocol, for every session (R3).

This module holds the fail-closed observation-commit protocol that `first_session` introduced for the
window-opening observation (sequence 1, #476), generalized so sessions 2..N commit through *exactly the
same code path*. There is deliberately ONE implementation: a second transcription of a 150-line
durability/atomicity protocol is a divergence hazard, and a divergence between "how session 1 was
recorded" and "how session 250 was recorded" would itself be an integrity finding.

What the store adds beyond the single-observation opener:

  • **Chain binding.** Every observation's `commit.json` carries `previous_commit_sha256` — the sha256 of
    the previous observation's `commit.json` bytes (null for sequence 1). The committed tree is therefore
    an append-only hash chain in the same spirit as the platform's `audit_log`: rewriting observation 7
    invalidates 8..N, and the break is detectable without any external record.
  • **Contiguity.** The committed sequences must be exactly 1..N. A gap, a duplicate, an out-of-order
    directory, or a non-conforming name fails closed — the derived session count is never a guess.
  • **Monotonic sessions.** Observation N's `session_date` must strictly follow observation N-1's, so a
    session can never be recorded twice and a session can never be back-dated into the record.

Everything else is unchanged from the ruling of 2026-07-23: a single atomic no-overwrite directory
publish rooted by an immutable `commit.json`; a storage-derived (fully validated) session count; a
per-sequence publish mutex; authoritative Account-4 before/after probes across the commit; strict fsync
durability; and complete digest verification of every staged file before publish.

Nothing here touches Account 4, and nothing here imports the order path.
"""

from __future__ import annotations

import contextlib
import ctypes
import errno
import hashlib
import json
import os
import shutil
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from app.validation.forward_window import ForwardRunContext, IntegrityStop, OpenObservation

OBS_DIRNAME = "observations"
STAGING_DIRNAME = ".staging"
LOCKS_DIRNAME = ".commit-locks"
MANIFEST_FILES = ("open.json", "sealed.bin", "provenance.json")
REQUIRED_FILES = (*MANIFEST_FILES, "manifest.json", "commit.json")

FIRST_SEQUENCE = 1


class ObservationCommitError(IntegrityStop):
    """An atomic observation commit did not complete, or a post-stage invariant failed. The session
    count is NOT advanced and no partial/observable record is left. A retry is permitted only after
    correcting an operational/integrity defect WITHOUT changing any frozen research choice."""


@dataclass(frozen=True)
class Account4StateProbe:
    """A tamper-evident snapshot of the Account-4 state that must NOT change across the commit: the
    operational-hold (status/reason/rev), strategy status, and a positions digest. Obtained by an
    authoritative probe callable (live read), never passed in by the caller — and compared before/after."""
    hold_status: str
    hold_reason_code: str
    hold_rev: int
    strategy_status: str
    positions_sha256: str

    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(asdict(self), sort_keys=True).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CommittedObservation:
    """One fully validated committed observation, as read back from storage."""
    sequence: int
    session_date: str
    path: Path
    commit_sha256: str                     # sha256 of commit.json bytes — the next observation's link
    previous_commit_sha256: str | None     # None for sequence 1


# ── the sealed field names (must never leak into the OPEN record) ──────────────────────────────────
_SEALED_FIELD_NAMES: frozenset[str] = frozenset({
    "strategy_return", "benchmark_excess", "excess_return", "sharpe", "cagr", "max_drawdown",
    "cvar", "volatility", "pnl", "turnover_cost", "cumulative_return", "calmar", "dsr",
})


def assert_open_record_has_no_sealed_content(open_record: dict, sealed_payload: dict) -> None:
    """Fail closed if any sealed field NAME or VALUE appears in the OPEN record. The open record is
    what a routine operator sees; a leaked return would defeat the sealed no-peeking boundary."""
    flat = json.dumps(open_record, sort_keys=True, default=str)
    leaked_names = [n for n in (_SEALED_FIELD_NAMES | set(sealed_payload)) if n in flat]
    if leaked_names:
        raise ObservationCommitError(f"OPEN record leaks sealed field name(s): {sorted(leaked_names)}")
    for v in sealed_payload.values():
        if isinstance(v, (int, float)) and v not in (0, 0.0, 1) and str(v) in flat:
            raise ObservationCommitError(f"OPEN record leaks a sealed value: {v!r}")


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def semantic_digest(payload: dict) -> str:
    """The digest recorded in provenance for the OPEN record (content, not file bytes)."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def canon(payload: dict) -> bytes:
    """Deterministic file bytes for a JSON payload (stable across processes/platforms)."""
    return (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode("utf-8")


def build_open_record(ctx: ForwardRunContext, *, rebalances: int, orders: int, seeds: int,
                      operational: dict, sealed_sha: str,
                      data_finality: dict | None = None) -> OpenObservation:
    """Assemble the operator-visible OPEN record for a session (no performance — sealed by digest)."""
    return OpenObservation(
        session_date=ctx.session_date.isoformat(), integrity_verdict="PASS",
        rebalances=rebalances, orders_submitted=orders, seeds=seeds,
        scheduled_eval_completed=bool(operational.get("scheduled_eval_completed", True)),
        missed_rebalances=int(operational.get("missed_rebalances", 0)),
        duplicate_orders_or_seeds=int(operational.get("duplicate_orders_or_seeds", 0)),
        cap_breaches=int(operational.get("cap_breaches", 0)),
        broker_local_divergence=int(operational.get("broker_local_divergence", 0)),
        unresolved_reservations=int(operational.get("unresolved_reservations", 0)),
        manual_perf_affecting_interventions=int(
            operational.get("manual_perf_affecting_interventions", 0)),
        operational_exceptions=list(operational.get("operational_exceptions", [])),
        sealed_performance_sha256=sealed_sha,
        data_finality=data_finality,
    )


# ── durability: STRICT on production (Linux), explicit best-effort on unsupported dev platforms ────

class Durability:
    """fsync policy. Production execution must use a policy whose fsync errors FAIL CLOSED."""

    def fsync_file(self, path: Path) -> None:
        raise NotImplementedError

    def fsync_dir(self, path: Path) -> None:
        raise NotImplementedError


class StrictDurability(Durability):
    """Production (Linux): fsync MUST succeed. Any OSError raises ObservationCommitError — a governed
    commit never claims durability it did not achieve."""

    def fsync_file(self, path: Path) -> None:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        except OSError as exc:
            raise ObservationCommitError(
                f"fsync failed for {path.name}: {exc} — durability not guaranteed") from exc
        finally:
            os.close(fd)

    def fsync_dir(self, path: Path) -> None:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        except OSError as exc:
            raise ObservationCommitError(
                f"directory fsync failed for {path}: {exc} — rename durability not guaranteed") from exc
        finally:
            os.close(fd)


class BestEffortDurability(Durability):
    """Unsupported development platforms (e.g. Windows, where a read-only or directory fd cannot be
    fsynced). EXPLICIT opt-in only — never selected on posix. Documented as non-durable; not for
    production use."""

    def fsync_file(self, path: Path) -> None:
        try:
            fd = os.open(path, os.O_RDONLY)
        except OSError:
            return
        try:
            with contextlib.suppress(OSError):
                os.fsync(fd)
        finally:
            os.close(fd)

    def fsync_dir(self, path: Path) -> None:
        try:
            fd = os.open(path, os.O_RDONLY)
        except OSError:
            return
        try:
            with contextlib.suppress(OSError):
                os.fsync(fd)
        finally:
            os.close(fd)


def default_durability() -> Durability:
    """STRICT on posix (the EC2 box); explicit best-effort only on non-posix dev platforms."""
    return StrictDurability() if os.name == "posix" else BestEffortDurability()


# ── no-overwrite publish primitive ────────────────────────────────────────────────────────────────

_RENAME_NOREPLACE = 1 << 0
_AT_FDCWD = -100


def _renameat2_noreplace(src: Path, dst: Path) -> None:
    """Atomic directory publish that REFUSES to replace an existing target (Linux glibc renameat2).
    Raises FileExistsError if dst exists, OSError on any other failure (both fail closed upstream)."""
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    libc.renameat2.restype = ctypes.c_int
    libc.renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                               ctypes.c_char_p, ctypes.c_uint]
    ctypes.set_errno(0)
    res = libc.renameat2(_AT_FDCWD, os.fsencode(src), _AT_FDCWD, os.fsencode(dst), _RENAME_NOREPLACE)
    if res != 0:
        err = ctypes.get_errno()
        if err == errno.EEXIST:
            raise FileExistsError(errno.EEXIST, os.strerror(errno.EEXIST), str(dst))
        raise OSError(err, os.strerror(err), str(dst))


def publish_no_overwrite(staging: Path, final: Path) -> None:
    """Atomically publish `staging` as `final` and FAIL CLOSED if `final` already exists — the refusal
    comes from the publish operation itself, not a preceding existence check (no TOCTOU gap)."""
    try:
        if os.name == "posix":
            _renameat2_noreplace(staging, final)
        else:
            os.rename(staging, final)          # Windows: raises FileExistsError if target exists
    except FileExistsError as exc:
        raise ObservationCommitError(
            f"publish refused: an observation already exists at {final} (no-overwrite)") from exc
    except OSError as exc:
        raise ObservationCommitError(f"atomic publish failed: {exc}") from exc


# ── committed-storage validation: per-observation, then the chain ─────────────────────────────────

def validate_committed_observation(
    path: Path, *, expected_sequence: int = FIRST_SEQUENCE,
    expected_previous_commit_sha256: str | None = None,
) -> CommittedObservation:
    """Raise IntegrityStop unless `path` is a FULLY valid committed observation: required files present;
    commit root digest == sha256(manifest.json); manifest file-set exact; each file's digest matches;
    sequence consistent across the directory name, commit marker and provenance; and the recorded
    `previous_commit_sha256` equals the expected chain link (None for the first observation)."""
    name = path.name
    if not (name.isdigit() and len(name) == 6):
        raise IntegrityStop(f"committed observation dir has a non-conforming name: {name!r}")
    seq_from_name = int(name)
    for f in REQUIRED_FILES:
        if not (path / f).is_file():
            raise IntegrityStop(f"committed observation {name} missing required file {f}")
    try:
        commit_bytes = (path / "commit.json").read_bytes()
        commit = json.loads(commit_bytes)
        manifest_bytes = (path / "manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes)
        provenance = json.loads((path / "provenance.json").read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise IntegrityStop(f"committed observation {name} is unreadable/corrupt: {exc}") from exc

    if not (commit.get("sequence") == seq_from_name == expected_sequence):
        raise IntegrityStop(f"committed observation {name}: sequence inconsistent "
                            f"(name={seq_from_name}, commit={commit.get('sequence')}, "
                            f"expected={expected_sequence})")
    if sha_bytes(manifest_bytes) != commit.get("manifest_sha256"):
        raise IntegrityStop(f"committed observation {name}: commit root digest != manifest.json digest")
    if set(manifest) != set(MANIFEST_FILES):
        raise IntegrityStop(f"committed observation {name}: manifest file-set mismatch {sorted(manifest)}")
    for fn, want in manifest.items():
        try:
            got = sha_bytes((path / fn).read_bytes())
        except OSError as exc:
            raise IntegrityStop(f"committed observation {name}: {fn} unreadable: {exc}") from exc
        if got != want:
            raise IntegrityStop(f"committed observation {name}: {fn} digest mismatch")
    if provenance.get("observation_sequence") != expected_sequence:
        raise IntegrityStop(f"committed observation {name}: provenance sequence "
                            f"{provenance.get('observation_sequence')!r} != {expected_sequence}")

    prev = commit.get("previous_commit_sha256")
    if prev != expected_previous_commit_sha256:
        raise IntegrityStop(
            f"committed observation {name}: chain link {prev!r} != expected "
            f"{expected_previous_commit_sha256!r} — the observation chain is broken")

    session_date = commit.get("session_date")
    if not isinstance(session_date, str) or not session_date:
        raise IntegrityStop(f"committed observation {name}: missing/invalid session_date")

    return CommittedObservation(
        sequence=seq_from_name, session_date=session_date, path=path,
        commit_sha256=sha_bytes(commit_bytes), previous_commit_sha256=prev)


def committed_observations(store_dir: Path) -> list[CommittedObservation]:
    """The authoritative, fully validated committed record, in sequence order. FAILS CLOSED
    (IntegrityStop) on a non-conforming directory name, a gap or duplicate in the sequence, a corrupt or
    tampered observation, a broken chain link, or a session date that does not strictly increase."""
    obs = store_dir / OBS_DIRNAME
    if not obs.is_dir():
        return []
    entries = [p for p in obs.iterdir() if p.is_dir()]
    non_numeric = [p.name for p in entries if not (p.name.isdigit() and len(p.name) == 6)]
    if non_numeric:
        raise IntegrityStop(f"unexpected non-numeric entries under observations/: {sorted(non_numeric)}")
    numeric = sorted(entries, key=lambda p: int(p.name))
    if not numeric:
        return []
    expected_names = [f"{i:06d}" for i in range(FIRST_SEQUENCE, FIRST_SEQUENCE + len(numeric))]
    if [p.name for p in numeric] != expected_names:
        raise IntegrityStop(
            f"observation sequences are not contiguous from {FIRST_SEQUENCE:06d}: "
            f"{[p.name for p in numeric]}")

    validated: list[CommittedObservation] = []
    prev_link: str | None = None
    for i, path in enumerate(numeric, start=FIRST_SEQUENCE):
        rec = validate_committed_observation(
            path, expected_sequence=i, expected_previous_commit_sha256=prev_link)
        if validated and rec.session_date <= validated[-1].session_date:
            raise IntegrityStop(
                f"committed observation {rec.sequence:06d}: session_date {rec.session_date} does not "
                f"strictly follow {validated[-1].session_date} (observation {validated[-1].sequence:06d})")
        validated.append(rec)
        prev_link = rec.commit_sha256
    return validated


def committed_session_count(store_dir: Path) -> int:
    """The authoritative, storage-derived forward-session count. Fails closed on any invalid state."""
    return len(committed_observations(store_dir))


def staging_token(sequence: int, preflight_timestamp: str, deployed_tree_identity: str) -> str:
    """A deterministic, filesystem-safe staging name (no wall-clock / randomness available or wanted)."""
    h = hashlib.sha256(
        f"{sequence}|{preflight_timestamp}|{deployed_tree_identity}".encode()).hexdigest()[:16]
    return f"seq{sequence}-{h}"


def _release_lock(lock_path: Path) -> None:
    with contextlib.suppress(OSError):
        lock_path.unlink()


@dataclass(frozen=True)
class CommitResult:
    """What a completed commit reports back: the provenance actually written, the storage-derived
    session count after publishing, and the chain link this observation consumed."""
    provenance: dict
    session_count: int
    previous_commit_sha256: str | None


def commit_observation(
    *,
    store_dir: Path,
    sequence: int,
    session_date: str,
    open_bytes: bytes,
    sealed_bytes: bytes,
    build_provenance: Callable[[str, str | None], dict],
    account4_probe: Callable[[], Account4StateProbe],
    preflight_timestamp: str,
    deployed_tree_identity: str,
    durability: Durability | None = None,
) -> CommitResult:
    """Commit ONE observation as a single atomic, no-overwrite directory publish.

    The caller has already run the integrity gate and built the OPEN record; this function owns the
    commit protocol and every check that must not be delegated to a caller:

      1. derive the session count from FULLY VALIDATED committed storage; require `sequence - 1`;
      2. derive the chain link (previous observation's commit digest) from that validated storage, and
         require the new `session_date` to strictly follow the previous observation's;
      3. acquire the per-sequence publish MUTEX (O_EXCL); contention fails closed;
      4. authoritative Account-4 BEFORE-probe (live read via the probe callable);
      5. stage the COMPLETE directory (open, sealed, provenance, manifest, commit root);
      6. fsync every staged file — STRICT;
      7. verify EVERY staged file's digest against the manifest + the commit root;
      8. fsync the staging directory — STRICT;
      9. authoritative AFTER-probe; require it equal the before-probe (Account 4 unchanged);
     10. publish atomically WITHOUT overwrite (the refusal comes from the publish op itself);
     11. fsync the parent directory — STRICT (rename durability); a failure does NOT report success;
     12. re-validate committed storage and return the derived count (== sequence).

    `build_provenance(before_probe_digest, previous_commit_sha256)` returns the provenance mapping to
    write; it is called with values the CALLER cannot supply (an authoritative live probe digest and the
    chain link read from validated storage). The publish mutex is released on success and on every
    failure path, and no partial/observable record is ever left behind.
    """
    dur = durability or default_durability()

    if sequence < FIRST_SEQUENCE:
        raise ObservationCommitError(f"invalid observation sequence {sequence}")

    # (1) storage-derived, fully validated count
    existing = committed_observations(store_dir)
    if len(existing) != sequence - 1:
        raise ObservationCommitError(
            f"committed storage holds {len(existing)} observation(s); sequence {sequence} requires "
            f"exactly {sequence - 1}")

    # (2) chain link + strictly increasing session date, both derived from validated storage
    previous_commit_sha256 = existing[-1].commit_sha256 if existing else None
    if existing and session_date <= existing[-1].session_date:
        raise ObservationCommitError(
            f"session {session_date} does not strictly follow the last committed session "
            f"{existing[-1].session_date} — a session may not be recorded twice or back-dated")

    obs_dir = store_dir / OBS_DIRNAME
    final_dir = obs_dir / f"{sequence:06d}"
    staging_dir = (store_dir / STAGING_DIRNAME
                   / staging_token(sequence, preflight_timestamp, deployed_tree_identity))
    locks_dir = store_dir / LOCKS_DIRNAME
    lock_path = locks_dir / f"{sequence:06d}.lock"

    obs_dir.mkdir(parents=True, exist_ok=True)
    locks_dir.mkdir(parents=True, exist_ok=True)

    # (3) per-sequence publish MUTEX — atomic O_EXCL create; contention fails closed.
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ObservationCommitError(
            f"another process holds the observation publish lock (seq {sequence})") from exc
    os.write(lock_fd, f"{deployed_tree_identity}|{preflight_timestamp}".encode())
    os.close(lock_fd)

    try:
        # abandoned-stage recovery: remove any stale staging dir before restaging.
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        staging_dir.mkdir(parents=True)

        # (4) authoritative BEFORE-probe (live read; not caller-supplied)
        before = account4_probe()
        before_digest = before.digest()

        prov = build_provenance(before_digest, previous_commit_sha256)
        prov_bytes = canon(prov)

        # (5) stage the COMPLETE directory: content files, manifest, then the commit ROOT marker
        (staging_dir / "open.json").write_bytes(open_bytes)
        (staging_dir / "sealed.bin").write_bytes(sealed_bytes)
        (staging_dir / "provenance.json").write_bytes(prov_bytes)
        manifest = {
            "open.json": sha_bytes(open_bytes),
            "sealed.bin": sha_bytes(sealed_bytes),
            "provenance.json": sha_bytes(prov_bytes),
        }
        manifest_bytes = canon(manifest)
        (staging_dir / "manifest.json").write_bytes(manifest_bytes)
        commit = {
            "sequence": sequence,
            "session_date": session_date,
            "manifest_sha256": sha_bytes(manifest_bytes),        # acyclic root binding
            "previous_commit_sha256": previous_commit_sha256,     # append-only chain link
        }
        commit_bytes = canon(commit)
        (staging_dir / "commit.json").write_bytes(commit_bytes)

        # (6) fsync every staged file (STRICT)
        for name in REQUIRED_FILES:
            dur.fsync_file(staging_dir / name)

        # (7) verify EVERY staged file's digest against the manifest + the commit root
        reread_manifest_bytes = (staging_dir / "manifest.json").read_bytes()
        reread_manifest = json.loads(reread_manifest_bytes)
        if reread_manifest != manifest:
            raise ObservationCommitError("staged manifest failed re-read verification")
        for name, want in reread_manifest.items():
            got = sha_bytes((staging_dir / name).read_bytes())
            if got != want:
                raise ObservationCommitError(
                    f"staged file {name} failed digest verification ({got} != {want})")
        reread_commit = json.loads((staging_dir / "commit.json").read_bytes())
        if reread_commit.get("manifest_sha256") != sha_bytes(reread_manifest_bytes):
            raise ObservationCommitError("commit root digest does not bind the staged manifest")
        if reread_commit.get("previous_commit_sha256") != previous_commit_sha256:
            raise ObservationCommitError("commit root does not carry the derived chain link")
        staged_open = json.loads((staging_dir / "open.json").read_bytes())
        if semantic_digest(staged_open) != prov.get("open_record_sha256"):
            raise ObservationCommitError("open record failed semantic digest verification")

        # (8) fsync the staging directory (STRICT)
        dur.fsync_dir(staging_dir)

        # (9) authoritative AFTER-probe — must equal the before-probe (Account 4 unchanged)
        after = account4_probe()
        if after.digest() != before_digest:
            raise ObservationCommitError(
                "Account 4 state changed across the commit — the validation must not touch the live book")

        # (10) atomically publish WITHOUT overwrite (refusal comes from the publish op itself)
        publish_no_overwrite(staging_dir, final_dir)

        # (11) fsync the parent directory so the rename is durable (STRICT — no success without it)
        dur.fsync_dir(obs_dir)

        # (12) re-validate committed storage and derive the new count
        new_count = committed_session_count(store_dir)
        if new_count != sequence:
            raise ObservationCommitError(
                f"post-publish committed count is {new_count}, expected {sequence}")
        return CommitResult(provenance=prov, session_count=new_count,
                            previous_commit_sha256=previous_commit_sha256)
    finally:
        # the published `observations/` tree (rooted by commit.json) is the durable record; the mutex is
        # always released, and any leftover staging dir is dropped so a corrected retry can proceed.
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        _release_lock(lock_path)
