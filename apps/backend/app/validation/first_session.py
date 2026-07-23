"""Forward-validation first observation — atomic directory-commit + full provenance (PREREG v1.0 §0/§5).

Builds on `forward_window.preflight` (the fail-closed gate). This module completes the *operational*
opening of the window. The window-open transition is a SINGLE atomic, no-overwrite directory publish:
the observation becomes visible (and the forward session count advances 0 → 1) only when one
fully-staged, digest-verified directory is atomically renamed into place. A preflight PASS alone does
not open the window.

Committed directory layout (`observations/000001/`):
  open.json        — the OPEN operator-visible record (no performance)
  sealed.bin       — the sealed performance payload (segregated; digest-referenced only)
  provenance.json  — the first-observation provenance (owner-required fields)
  manifest.json    — {file → sha256} over open.json, sealed.bin, provenance.json
  commit.json      — the IMMUTABLE ROOT MARKER: {sha256(manifest.json), sequence, session_date}

The root binding is acyclic: commit.json hashes manifest.json; manifest.json hashes the three content
files; nothing the manifest hashes contains the manifest's own digest. commit.json is the anchor and
must never be rewritten for a committed observation.

The commit protocol (owner ruling 2026-07-23, second CHANGES REQUESTED):
  1. preflight() — fail closed on any binding / Account-4 isolation mismatch.
  2. derive the session count from COMMITTED storage with full validation; require it be 0.
  3. acquire the first-observation publish MUTEX (O_EXCL lock); contention fails closed.
  4. authoritative Account-4 BEFORE-probe (live read via a probe callable — NOT caller-supplied).
  5. stage the COMPLETE directory (open, sealed, provenance, manifest, commit).
  6. fsync every staged file — STRICT: an fsync error fails the commit closed (Linux production).
  7. verify EVERY staged file's digest against the manifest (provenance included) + the commit root.
  8. fsync the staging directory — STRICT.
  9. authoritative Account-4 AFTER-probe; require it equal the before-probe (Account 4 unchanged).
 10. atomically publish WITHOUT overwrite via renameat2(RENAME_NOREPLACE) on Linux (os.rename on
     Windows already refuses an existing target); an existing target fails closed from the publish op.
 11. fsync the parent directory — STRICT (rename durability); a failure does NOT report success.
 12. re-validate committed storage and return the derived count (1).
Cleanup always: the publish mutex is a MUTEX — released after a successful publish and on every failure;
the committed `observations/` tree (rooted by commit.json) is the durable ownership record. A crashed
prior attempt's stale staging dir is removed on entry; the committed tree is never touched by recovery.

Nothing here touches Account 4: the write goes to the shadow / separate paper-validation ledger, and the
authoritative before/after probes prove the live book was unchanged across the commit.
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

from app.validation.forward_window import (
    ForwardRunContext,
    IntegrityStop,
    OpenObservation,
    preflight,
    seal_performance,
)

_SEQUENCE = 1                                   # this module opens the FIRST observation only
_OBS_DIRNAME = "observations"
_STAGING_DIRNAME = ".staging"
_LOCKS_DIRNAME = ".commit-locks"
_MANIFEST_FILES = ("open.json", "sealed.bin", "provenance.json")
_REQUIRED_FILES = (*_MANIFEST_FILES, "manifest.json", "commit.json")


class WindowOpenError(IntegrityStop):
    """The atomic first-observation commit did not complete, or a post-stage invariant failed. The
    session count is NOT advanced and no partial/observable record is left. A retry is permitted only
    after correcting an operational/integrity defect WITHOUT changing any frozen research choice."""


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


@dataclass
class FirstObservationProvenance:
    """The provenance fields the first successful observation must record (owner 2026-07-23)."""
    preflight_execution_timestamp: str          # ISO8601 UTC — caller-supplied (Date.now unavailable)
    deployed_tree_identity: str                 # git commit/tree of the running validation code
    shadow_ledger_identity: str                 # the shadow / separate paper-validation ledger id
    observation_sequence: int                   # 1 for the first observation
    open_record_sha256: str
    sealed_payload_sha256: str
    account4_unchanged: bool                     # True iff the authoritative after-probe == before-probe
    account4_state_digest_before: str            # authoritative before-probe
    account4_state_digest_after: str             # authoritative after-probe (verified == before at publish)


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
        raise WindowOpenError(f"OPEN record leaks sealed field name(s): {sorted(leaked_names)}")
    for v in sealed_payload.values():
        if isinstance(v, (int, float)) and v not in (0, 0.0, 1) and str(v) in flat:
            raise WindowOpenError(f"OPEN record leaks a sealed value: {v!r}")


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _canon(payload: dict) -> bytes:
    """Deterministic file bytes for a JSON payload (stable across processes/platforms)."""
    return (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode("utf-8")


# ── durability: STRICT on production (Linux), explicit best-effort on unsupported dev platforms ────

class Durability:
    """fsync policy. Production execution must use a policy whose fsync errors FAIL CLOSED."""

    def fsync_file(self, path: Path) -> None:
        raise NotImplementedError

    def fsync_dir(self, path: Path) -> None:
        raise NotImplementedError


class StrictDurability(Durability):
    """Production (Linux): fsync MUST succeed. Any OSError raises WindowOpenError — a governed commit
    never claims durability it did not achieve."""

    def fsync_file(self, path: Path) -> None:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        except OSError as exc:
            raise WindowOpenError(
                f"fsync failed for {path.name}: {exc} — durability not guaranteed") from exc
        finally:
            os.close(fd)

    def fsync_dir(self, path: Path) -> None:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        except OSError as exc:
            raise WindowOpenError(
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


def _publish_no_overwrite(staging: Path, final: Path) -> None:
    """Atomically publish `staging` as `final` and FAIL CLOSED if `final` already exists — the refusal
    comes from the publish operation itself, not a preceding existence check (no TOCTOU gap)."""
    try:
        if os.name == "posix":
            _renameat2_noreplace(staging, final)
        else:
            os.rename(staging, final)          # Windows: raises FileExistsError if target exists
    except FileExistsError as exc:
        raise WindowOpenError(
            f"publish refused: an observation already exists at {final} (no-overwrite)") from exc
    except OSError as exc:
        raise WindowOpenError(f"atomic publish failed: {exc}") from exc


# ── committed-storage validation + count ──────────────────────────────────────────────────────────

def validate_committed_observation(path: Path, *, expected_sequence: int = _SEQUENCE) -> None:
    """Raise IntegrityStop unless `path` is a FULLY valid committed observation: required files present;
    commit root digest == sha256(manifest.json); manifest file-set exact; each file's digest matches;
    sequence consistent across the directory name, commit marker, and provenance."""
    name = path.name
    if not (name.isdigit() and len(name) == 6):
        raise IntegrityStop(f"committed observation dir has a non-conforming name: {name!r}")
    seq_from_name = int(name)
    for f in _REQUIRED_FILES:
        if not (path / f).is_file():
            raise IntegrityStop(f"committed observation {name} missing required file {f}")
    try:
        commit = json.loads((path / "commit.json").read_bytes())
        manifest_bytes = (path / "manifest.json").read_bytes()
        manifest = json.loads(manifest_bytes)
        provenance = json.loads((path / "provenance.json").read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise IntegrityStop(f"committed observation {name} is unreadable/corrupt: {exc}") from exc

    if not (commit.get("sequence") == seq_from_name == expected_sequence):
        raise IntegrityStop(f"committed observation {name}: sequence inconsistent "
                            f"(name={seq_from_name}, commit={commit.get('sequence')}, "
                            f"expected={expected_sequence})")
    if _sha_bytes(manifest_bytes) != commit.get("manifest_sha256"):
        raise IntegrityStop(f"committed observation {name}: commit root digest != manifest.json digest")
    if set(manifest) != set(_MANIFEST_FILES):
        raise IntegrityStop(f"committed observation {name}: manifest file-set mismatch {sorted(manifest)}")
    for fn, want in manifest.items():
        try:
            got = _sha_bytes((path / fn).read_bytes())
        except OSError as exc:
            raise IntegrityStop(f"committed observation {name}: {fn} unreadable: {exc}") from exc
        if got != want:
            raise IntegrityStop(f"committed observation {name}: {fn} digest mismatch")
    if provenance.get("observation_sequence") != expected_sequence:
        raise IntegrityStop(f"committed observation {name}: provenance sequence "
                            f"{provenance.get('observation_sequence')!r} != {expected_sequence}")


def committed_session_count(store_dir: Path) -> int:
    """The authoritative, storage-derived session count. FAILS CLOSED (IntegrityStop) on any corrupt or
    unexpected observation directory. For this first-session module the only valid states are exactly:
    no committed observation (→ 0) or one fully valid observation at 000001 (→ 1)."""
    obs = store_dir / _OBS_DIRNAME
    if not obs.is_dir():
        return 0
    numeric = sorted(p for p in obs.iterdir()
                     if p.is_dir() and p.name.isdigit() and len(p.name) == 6)
    non_numeric = [p.name for p in obs.iterdir()
                   if p.is_dir() and not (p.name.isdigit() and len(p.name) == 6)]
    if non_numeric:
        raise IntegrityStop(f"unexpected non-numeric entries under observations/: {sorted(non_numeric)}")
    if not numeric:
        return 0
    names = {p.name for p in numeric}
    if names - {f"{_SEQUENCE:06d}"}:
        raise IntegrityStop(f"unexpected/out-of-sequence observation directories: {sorted(names)}")
    validate_committed_observation(obs / f"{_SEQUENCE:06d}")
    return 1


def _staging_token(preflight_timestamp: str, deployed_tree_identity: str) -> str:
    """A deterministic, filesystem-safe staging name (no wall-clock / randomness available or wanted)."""
    h = hashlib.sha256(f"{preflight_timestamp}|{deployed_tree_identity}".encode()).hexdigest()[:16]
    return f"seq{_SEQUENCE}-{h}"


def _release_lock(lock_path: Path) -> None:
    with contextlib.suppress(OSError):
        lock_path.unlink()


def open_first_window_session(
    ctx: ForwardRunContext,
    *,
    preflight_timestamp: str,
    deployed_tree_identity: str,
    shadow_ledger_identity: str,
    account4_probe: Callable[[], Account4StateProbe],
    rebalances: int,
    orders: int,
    seeds: int,
    operational: dict,
    sealed_performance: dict,
    store_dir: Path,
    durability: Durability | None = None,
) -> tuple[OpenObservation, FirstObservationProvenance, int]:
    """Run the gate, then COMMIT the first observation as one atomic, no-overwrite directory publish,
    and return the session count derived from validated committed storage (1 on success). See the module
    docstring for the full fail-closed commit protocol. Nothing partial or observable is left on any
    failure path; the publish mutex is released on success and on every failure."""
    dur = durability or default_durability()

    preflight(ctx)                                                          # (1)

    if committed_session_count(store_dir) != 0:                            # (2) validated, storage-derived
        raise WindowOpenError(
            "committed storage already holds an observation — this is not the first session (expected 0)")

    obs_dir = store_dir / _OBS_DIRNAME
    final_dir = obs_dir / f"{_SEQUENCE:06d}"
    staging_dir = store_dir / _STAGING_DIRNAME / _staging_token(preflight_timestamp, deployed_tree_identity)
    locks_dir = store_dir / _LOCKS_DIRNAME
    lock_path = locks_dir / f"{_SEQUENCE:06d}.lock"

    obs_dir.mkdir(parents=True, exist_ok=True)
    locks_dir.mkdir(parents=True, exist_ok=True)

    # (3) first-observation publish MUTEX — atomic O_EXCL create; contention fails closed.
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise WindowOpenError(
            f"another process holds the first-observation publish lock (seq {_SEQUENCE})") from exc
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

        # build the OPEN record + sealed payload
        sealed_sha, sealed_bytes = seal_performance(sealed_performance)
        open_obs = OpenObservation(
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
        )
        open_dict = asdict(open_obs)
        assert_open_record_has_no_sealed_content(open_dict, sealed_performance)
        open_bytes = _canon(open_dict)

        prov = FirstObservationProvenance(
            preflight_execution_timestamp=preflight_timestamp,
            deployed_tree_identity=deployed_tree_identity,
            shadow_ledger_identity=shadow_ledger_identity,
            observation_sequence=_SEQUENCE,
            open_record_sha256=_digest(open_dict),
            sealed_payload_sha256=sealed_sha,
            account4_unchanged=True,              # enforced by the publish gate (after == before)
            account4_state_digest_before=before_digest,
            account4_state_digest_after=before_digest,   # verified == before authoritatively at publish
        )
        prov_bytes = _canon(asdict(prov))

        # (5) stage the COMPLETE directory: content files, manifest, then the commit ROOT marker
        (staging_dir / "open.json").write_bytes(open_bytes)
        (staging_dir / "sealed.bin").write_bytes(sealed_bytes)
        (staging_dir / "provenance.json").write_bytes(prov_bytes)
        manifest = {
            "open.json": _sha_bytes(open_bytes),
            "sealed.bin": _sha_bytes(sealed_bytes),
            "provenance.json": _sha_bytes(prov_bytes),
        }
        manifest_bytes = _canon(manifest)
        (staging_dir / "manifest.json").write_bytes(manifest_bytes)
        commit = {
            "sequence": _SEQUENCE,
            "session_date": ctx.session_date.isoformat(),
            "manifest_sha256": _sha_bytes(manifest_bytes),   # acyclic root binding
        }
        commit_bytes = _canon(commit)
        (staging_dir / "commit.json").write_bytes(commit_bytes)

        # (6) fsync every staged file (STRICT)
        for name in _REQUIRED_FILES:
            dur.fsync_file(staging_dir / name)

        # (7) verify EVERY staged file's digest against the manifest + the commit root
        reread_manifest_bytes = (staging_dir / "manifest.json").read_bytes()
        reread_manifest = json.loads(reread_manifest_bytes)
        if reread_manifest != manifest:
            raise WindowOpenError("staged manifest failed re-read verification")
        for name, want in reread_manifest.items():
            got = _sha_bytes((staging_dir / name).read_bytes())
            if got != want:
                raise WindowOpenError(f"staged file {name} failed digest verification ({got} != {want})")
        reread_commit = json.loads((staging_dir / "commit.json").read_bytes())
        if reread_commit.get("manifest_sha256") != _sha_bytes(reread_manifest_bytes):
            raise WindowOpenError("commit root digest does not bind the staged manifest")
        if _digest(json.loads((staging_dir / "open.json").read_bytes())) != prov.open_record_sha256:
            raise WindowOpenError("open record failed semantic digest verification")

        # (8) fsync the staging directory (STRICT)
        dur.fsync_dir(staging_dir)

        # (9) authoritative AFTER-probe — must equal the before-probe (Account 4 unchanged across commit)
        after = account4_probe()
        if after.digest() != before_digest:
            raise WindowOpenError(
                "Account 4 state changed across the commit — the validation must not touch the live book")

        # (10) atomically publish WITHOUT overwrite (refusal comes from the publish op itself)
        _publish_no_overwrite(staging_dir, final_dir)

        # (11) fsync the parent directory so the rename is durable (STRICT — no success without it)
        dur.fsync_dir(obs_dir)

        # (12) re-validate committed storage and derive the new count
        new_count = committed_session_count(store_dir)
        if new_count != 1:
            raise WindowOpenError(f"post-publish committed count is {new_count}, expected 1")
        return open_obs, prov, new_count
    finally:
        # the published `observations/` tree (rooted by commit.json) is the durable record; the mutex is
        # always released, and any leftover staging dir is dropped so a corrected retry can proceed.
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        _release_lock(lock_path)
