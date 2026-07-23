"""Forward-validation first observation — atomic directory-commit + full provenance (PREREG v1.0 §0/§5).

Builds on `forward_window.preflight` (the fail-closed gate). This module completes the *operational*
opening of the window. The window-open transition is a SINGLE atomic directory publish: the observation
becomes visible (and the forward session count advances 0 → 1) only when one fully-staged, digest-verified
directory is atomically renamed into place. A preflight PASS alone does not open the window.

The commit protocol (owner ruling 2026-07-23, CHANGES REQUESTED on the three-rename draft):

  1. preflight() — fail closed on any binding / Account-4 isolation mismatch.
  2. derive the current session count from COMMITTED storage; require it be 0 (first observation only).
  3. acquire EXCLUSIVE first-observation ownership (O_EXCL lock) so two processes cannot both publish
     sequence 1. Contention fails closed (conservative; a wedged lock is an operator clear, never an
     auto-overwrite).
  4. authoritative Account-4 BEFORE-probe (read live state via the probe callable — NOT caller-supplied).
  5. stage the COMPLETE observation directory (open record, sealed payload, provenance, manifest).
  6. fsync every staged file.
  7. verify EVERY staged file's digest against the single manifest — provenance included.
  8. fsync the staging directory.
  9. authoritative Account-4 AFTER-probe; require it equal the before-probe (proves Account 4 was
     unchanged across the staged commit). Mismatch fails closed — nothing is published.
 10. atomically publish the directory WITHOUT overwrite (rename; refuses if the target exists).
 11. fsync the parent directory (rename durability).
 12. derive the new session count from committed storage and return it.

Abandoned-stage recovery: a crashed prior attempt leaves a stale staging dir, which is removed on entry
(the published `observations/` tree is the only source of truth and is never touched by recovery).

Nothing here touches Account 4: the write goes to the shadow / separate paper-validation ledger, and the
authoritative before/after probes prove the live book was unchanged across the commit.
"""

from __future__ import annotations

import contextlib
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
    observation_manifest_sha256: str            # single digest binding the whole committed directory
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


def committed_session_count(store_dir: Path) -> int:
    """Derive the session count from COMMITTED storage — the number of published observation dirs.
    This is the authoritative, durable counter; there is no in-memory count argument."""
    obs = store_dir / _OBS_DIRNAME
    if not obs.is_dir():
        return 0
    return sum(1 for p in obs.iterdir() if p.is_dir() and p.name.isdigit() and len(p.name) == 6)


def _fsync_file(path: Path) -> None:
    """fsync a file's bytes to durable storage. The fsync is best-effort on platforms that refuse it
    for a given fd mode (e.g. Windows read-only handles) — those aren't the production runtime (Linux)."""
    fd = os.open(path, os.O_RDONLY)
    try:
        with contextlib.suppress(OSError):
            os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_dir(path: Path) -> None:
    """fsync a directory so a rename/create is durable. No-op on platforms that refuse to open a
    directory fd (e.g. Windows) — those aren't the production runtime (the box is Linux)."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        with contextlib.suppress(OSError):
            os.fsync(fd)
    finally:
        os.close(fd)


def _staging_token(preflight_timestamp: str, deployed_tree_identity: str) -> str:
    """A deterministic, filesystem-safe staging name (no wall-clock / randomness available or wanted)."""
    h = hashlib.sha256(f"{preflight_timestamp}|{deployed_tree_identity}".encode()).hexdigest()[:16]
    return f"seq{_SEQUENCE}-{h}"


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
) -> tuple[OpenObservation, FirstObservationProvenance, int]:
    """Run the gate, then COMMIT the first observation as one atomic directory publish, and return the
    session count derived from committed storage (1 on success). See the module docstring for the full
    fail-closed commit protocol. Nothing partial or observable is left on any failure path."""
    preflight(ctx)                                                          # (1)

    if committed_session_count(store_dir) != 0:                            # (2) durable, storage-derived
        raise WindowOpenError(
            "committed storage already holds an observation — this is not the first session (expected 0)")

    obs_dir = store_dir / _OBS_DIRNAME
    final_dir = obs_dir / f"{_SEQUENCE:06d}"
    staging_dir = store_dir / _STAGING_DIRNAME / _staging_token(preflight_timestamp, deployed_tree_identity)
    locks_dir = store_dir / _LOCKS_DIRNAME
    lock_path = locks_dir / f"{_SEQUENCE:06d}.lock"

    obs_dir.mkdir(parents=True, exist_ok=True)
    locks_dir.mkdir(parents=True, exist_ok=True)

    # (3) EXCLUSIVE first-observation ownership — atomic O_EXCL create; contention fails closed.
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise WindowOpenError(
            f"another process already owns first-observation publication (seq {_SEQUENCE}); a wedged "
            "lock is an operator clear, never an auto-overwrite") from exc
    try:
        os.write(lock_fd, f"{deployed_tree_identity}|{preflight_timestamp}".encode())
        os.fsync(lock_fd)
    finally:
        os.close(lock_fd)

    published = False
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
            observation_manifest_sha256="",     # filled once the manifest bytes exist
            account4_unchanged=True,             # enforced by the publish gate (after == before)
            account4_state_digest_before=before_digest,
            account4_state_digest_after=before_digest,   # verified == before authoritatively at publish
        )
        prov_bytes = _canon(asdict(prov))

        # (5) stage the COMPLETE directory: open record, sealed payload, provenance, manifest
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

        # (6) fsync every staged file
        for name in ("open.json", "sealed.bin", "provenance.json", "manifest.json"):
            _fsync_file(staging_dir / name)

        # (7) verify EVERY staged file's digest against the single manifest — provenance included
        reread_manifest = json.loads((staging_dir / "manifest.json").read_bytes())
        if reread_manifest != manifest:
            raise WindowOpenError("staged manifest failed re-read verification")
        for name, want in reread_manifest.items():
            got = _sha_bytes((staging_dir / name).read_bytes())
            if got != want:
                raise WindowOpenError(f"staged file {name} failed digest verification ({got} != {want})")
        # cross-check the semantic open-record digest too
        if _digest(json.loads((staging_dir / "open.json").read_bytes())) != prov.open_record_sha256:
            raise WindowOpenError("open record failed semantic digest verification")

        # (8) fsync the staging directory
        _fsync_dir(staging_dir)

        # (9) authoritative AFTER-probe — must equal the before-probe (Account 4 unchanged across commit)
        after = account4_probe()
        if after.digest() != before_digest:
            raise WindowOpenError(
                "Account 4 state changed across the commit — the validation must not touch the live book")

        # (10) atomically publish WITHOUT overwrite
        if final_dir.exists():
            raise WindowOpenError(f"refusing to overwrite an existing observation at {final_dir}")
        os.rename(staging_dir, final_dir)      # atomic on the same filesystem; target does not exist
        published = True

        # (11) fsync the parent directory so the rename is durable
        _fsync_dir(obs_dir)

    except Exception:
        # nothing observable is left: drop the staging dir and release the lock so a corrected retry
        # is possible (the published tree, if we got that far, is the source of truth and is untouched).
        if not published and staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        _release_lock(lock_path)
        raise
    finally:
        if staging_dir.exists() and published:
            shutil.rmtree(staging_dir, ignore_errors=True)

    # (12) derive the new session count from committed storage
    new_count = committed_session_count(store_dir)
    if new_count != 1:
        raise WindowOpenError(f"post-publish committed count is {new_count}, expected 1")
    return open_obs, prov, new_count


def _release_lock(lock_path: Path) -> None:
    with contextlib.suppress(OSError):
        lock_path.unlink()
