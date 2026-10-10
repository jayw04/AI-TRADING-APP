"""Level 1 acceptance tests A-5 (symlinked token / registry directory), L-2 (a killed lock holder)
and L-3 (fork inheritance) from the RANGE-002 Level 1 Acceptance Test Plan.

Everything here uses the REAL locks (``msvcrt`` on Windows, ``fcntl.flock`` elsewhere), REAL
subprocesses and a REAL ``os.fork``; nothing mocks locking. Every file lives under ``tmp_path``;
the authoritative registry is never touched.

Behaviour these tests pin (determined from the code, not assumed):

* A-5: the code does NOT refuse a symlinked / junctioned token or registry DIRECTORY. It follows
  the link, and the link and the real directory are ONE identity (same files, same inode, same
  lock). A symlink planted over a FILE name is never written through (``O_EXCL`` / ``lexists``).
  A token directory redirected to a fresh directory is defeated by the registry, which is the
  authority on whether the holdout was opened (round 4).
* L-2: the OS releases the lock when the holder is killed; nothing stale is left behind.
* L-3: ``flock`` locks belong to the open FILE DESCRIPTION, which ``fork`` shares. The module API
  opens a NEW description per call, so a forked child is excluded while the parent holds the lock
  (no double writer). The same sharing means a lock whose holder was SIGKILLed stays held while a
  forked descendant is alive (fail closed, documented). A ``ResultsCapability`` is process-local
  memory; ``fork`` copies it, and the copy validates exactly as long as its run is OPEN in the
  registry FILE.
"""

from __future__ import annotations

import contextlib
import json
import multiprocessing
import multiprocessing.reduction
import os
import pickle
import random
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from app.research.range002.governance import hashchain
from app.research.range002.governance.errors import (
    HoldoutAlreadyOpenedError,
    HoldoutTokenError,
    InvalidCapabilityError,
    RegistryEnrollmentError,
    RegistryIntegrityError,
    RegistryNamespaceBusyError,
)
from app.research.range002.governance.exposure_ledger import ExposureLedger
from app.research.range002.governance.hashchain import (
    HashChainFile,
    file_lock,
    namespace_lock,
    read_chain,
)
from app.research.range002.governance.holdout_token import HoldoutTokenStore, TokenState
from app.research.range002.governance.model import Partition, Phase
from app.research.range002.governance.results_guard import (
    ResultsCapability,
    authorize,
    require_capability,
)
from app.research.range002.governance.run_registry import RunRegistry
from app.research.range002.governance.spec_adapter import GuardSpecView
from tests.research.range002.spec._fixtures import make_symlink

from .conftest import (
    SPEC_SHA,
    SYNTH_GENESIS_ID,
    complete_prereqs,
    complete_run,
    evidence_for,
    new_registry,
    open_run,
)

BACKEND_DIR = Path(__file__).resolve().parents[4]
_SIGKILL = getattr(signal, "SIGKILL", signal.SIGTERM)  # SIGKILL on POSIX; unused on Windows
IS_WINDOWS = sys.platform == "win32"
ACQUIRE_BUDGET_S = 5.0  # "promptly": the OS frees the lock at once; the budget only bounds a hang

needs_fork = pytest.mark.skipif(
    IS_WINDOWS or sys.platform == "darwin",
    reason="SKIPPED (not passed): fork inheritance is POSIX/Linux only (L-3)",
)


def _env() -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(BACKEND_DIR)}


def _spawn(script: str, *args: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-c", script, *args],
        cwd=BACKEND_DIR,
        env=_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _hard_kill(proc: subprocess.Popen[str]) -> None:
    """SIGKILL on POSIX; ``TerminateProcess`` (``Popen.kill``) on Windows. Neither runs any
    cleanup in the victim, so the lock can only be freed by the OS."""
    if IS_WINDOWS:
        proc.kill()
    else:
        os.kill(proc.pid, _SIGKILL)
    proc.wait(timeout=15)


def _expect_ready(proc: subprocess.Popen[str]) -> None:
    assert proc.stdout is not None
    line = proc.stdout.readline().strip()
    if line != "READY":
        _hard_kill(proc)
        assert proc.stderr is not None
        pytest.fail(f"child did not become READY (got {line!r}): {proc.stderr.read()}")


def _chain_with(path: Path, n: int) -> HashChainFile:
    chain = HashChainFile(path)
    for i in range(n):
        chain.append("k", {"i": i})
    return chain


# ---------------------------------------------------------------------------------------------
# A-5: symlinked token directory and symlinked ledger/registry directory
# ---------------------------------------------------------------------------------------------


def make_dir_alias(link: Path, target: Path) -> None:
    """A directory symlink; on Windows without the symlink privilege, an NTFS junction instead.
    Skips only off Linux when neither can be made; on Linux a failure FAILS (``make_symlink``)."""
    if IS_WINDOWS:
        try:
            link.symlink_to(target, target_is_directory=True)
            return
        except OSError:
            pass
        done = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, check=False
        )
        if done.returncode != 0:
            pytest.skip("SKIPPED (not passed): neither a symlink nor a junction can be created")
        return
    make_symlink(link, target)


def test_a5_symlinked_token_directory_is_one_identity(tmp_path: Path) -> None:
    real = tmp_path / "tokens_real"
    real.mkdir()
    link = tmp_path / "tokens_link"
    make_dir_alias(link, real)
    via_link = HoldoutTokenStore(link)
    via_real = HoldoutTokenStore(real)

    token = via_link.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID)
    assert (real / f"{SPEC_SHA}.token.json").is_file()  # written into the REAL directory
    assert via_real.state(SPEC_SHA) is TokenState.ISSUED
    with pytest.raises(HoldoutTokenError):  # one token per spec hash, whichever name is used
        via_real.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID)
    via_real.validate_unused(token, SPEC_SHA, SYNTH_GENESIS_ID)

    via_link.consume(token, "run-a5")
    assert via_real.state(SPEC_SHA) is TokenState.CONSUMED
    with pytest.raises(HoldoutAlreadyOpenedError):
        via_real.validate_unused(token, SPEC_SHA, SYNTH_GENESIS_ID)
    with pytest.raises(HoldoutAlreadyOpenedError):
        via_link.begin_consume(token, "run-a5-again")


def test_a5_symlinked_registry_directory_is_one_identity_one_lock_one_chain(
    tmp_path: Path,
) -> None:
    real_dir = tmp_path / "gov_real"
    real_dir.mkdir()
    registry = new_registry(real_dir / "runs.jsonl")
    link_dir = tmp_path / "gov_link"
    make_dir_alias(link_dir, real_dir)

    via_link = RunRegistry(link_dir / "runs.jsonl")
    assert via_link.genesis_id == registry.genesis_id

    # one inode -> one writer lock under either name; one namespace lock under either name
    with (
        file_lock(real_dir / "runs.jsonl"),
        pytest.raises(RegistryIntegrityError, match="writer lock"),
        file_lock(link_dir / "runs.jsonl", timeout=0.2),
    ):
        pytest.fail("the symlinked directory must not give a second writer lock")
    with (
        namespace_lock(real_dir),
        pytest.raises(RegistryNamespaceBusyError),
        namespace_lock(link_dir, timeout=0.2),
    ):
        pytest.fail("the symlinked directory must not give a second namespace lock")

    # a second registry cannot be enrolled beside the first by going through the alias
    with pytest.raises(RegistryEnrollmentError):
        RunRegistry.enroll_new(link_dir / "second.jsonl", enrolled_by="synthetic-test-owner")
    assert not (real_dir / "second.jsonl").exists()

    # interleaved appends through both names: a single valid chain, no fork
    base = registry.count_records()
    for i in range(6):
        handle = registry if i % 2 == 0 else via_link
        handle.open_run(
            phase=Phase.P2,
            spec_sha256="1" * 64,
            code_sha="b" * 40,
            data_manifest_sha256="c" * 64,
            partition=Partition.REPLAY_RNG001,
            seeds={"i": i},
            exit_candidates=["E1"],
        )
    records = read_chain(real_dir / "runs.jsonl")
    assert len(records) == base + 6
    assert [r.seq for r in records] == list(range(1, base + 7))
    assert read_chain(link_dir / "runs.jsonl") == records


def test_a5_symlink_planted_over_a_file_name_is_never_written_through(tmp_path: Path) -> None:
    # (1) a dangling symlink where a token file would be created
    tokens = tmp_path / "tokens"
    tokens.mkdir()
    victim = tmp_path / "victim_token.json"
    make_symlink(tokens / f"{SPEC_SHA}.token.json", victim)
    store = HoldoutTokenStore(tokens)
    with pytest.raises(HoldoutTokenError):
        store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID)
    assert not victim.exists(), "a token was written THROUGH a symlink"

    # (2) a dangling symlink where the registry file would be enrolled
    gov = tmp_path / "gov"
    gov.mkdir()
    registry_victim = tmp_path / "victim_registry.jsonl"
    make_symlink(gov / "runs.jsonl", registry_victim)
    with pytest.raises(RegistryEnrollmentError):
        RunRegistry.enroll_new(gov / "runs.jsonl", enrolled_by="synthetic-test-owner")
    assert not registry_victim.exists(), "a registry was enrolled THROUGH a symlink"

    # (3) a symlink to an EXISTING file is not overwritten either
    existing = tmp_path / "existing.json"
    existing.write_text("untouched", encoding="utf-8")
    other = tmp_path / "tokens2"
    other.mkdir()
    make_symlink(other / f"{SPEC_SHA}.token.json", existing)
    with pytest.raises(HoldoutTokenError):
        HoldoutTokenStore(other).issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID)
    assert existing.read_text(encoding="utf-8") == "untouched"


def test_a5_token_directory_redirected_through_a_link_cannot_reopen_the_holdout(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger, tmp_path: Path
) -> None:
    """The token store is not the authority (it follows links): redirecting it to an empty
    directory yields a fresh store, and the REGISTRY still refuses a second holdout opening."""
    real = tmp_path / "tokens_real"
    store = HoldoutTokenStore(real)
    complete_prereqs(registry, Phase.P4)
    first = open_run(registry, Phase.P4, Partition.HOLDOUT)
    authorize(
        spec=spec,
        phase=Phase.P4,
        partition=Partition.HOLDOUT,
        run_id=first,
        registry=registry,
        exposure_ledger=ledger,
        holdout_store=store,
        holdout_token=store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID),
        predecessor_evidence=evidence_for(registry),
    )
    assert store.state(SPEC_SHA) is TokenState.CONSUMED

    empty = tmp_path / "tokens_empty"
    empty.mkdir()
    redirect = tmp_path / "tokens_redirect"
    make_dir_alias(redirect, empty)
    fresh = HoldoutTokenStore(redirect)
    assert fresh.state(SPEC_SHA) is TokenState.NOT_ISSUED  # the store alone is fooled ...
    second = open_run(registry, Phase.P4, Partition.HOLDOUT)
    with pytest.raises(HoldoutAlreadyOpenedError):  # ... the registry is not
        authorize(
            spec=spec,
            phase=Phase.P4,
            partition=Partition.HOLDOUT,
            run_id=second,
            registry=registry,
            exposure_ledger=ledger,
            holdout_store=fresh,
            holdout_token=fresh.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID),
            predecessor_evidence=evidence_for(registry),
        )


# ---------------------------------------------------------------------------------------------
# L-2: the lock is released when the holder is killed
# ---------------------------------------------------------------------------------------------

_HOLDER = """
import sys, time
from pathlib import Path
from app.research.range002.governance import hashchain

kind, target = sys.argv[1], Path(sys.argv[2])
cm = hashchain.file_lock(target) if kind == "chain" else hashchain.namespace_lock(target)
with cm:
    print("READY", flush=True)
    time.sleep(120)
"""


def test_l2_killed_chain_lock_holder_frees_the_lock_and_leaves_the_chain_intact(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chain.jsonl"
    _chain_with(path, 3)
    before = path.read_bytes()
    proc = _spawn(_HOLDER, "chain", str(path))
    try:
        _expect_ready(proc)
        with (
            pytest.raises(RegistryIntegrityError, match="writer lock"),
            file_lock(path, timeout=0.3),
        ):
            pytest.fail("the live holder must exclude us")
    finally:
        _hard_kill(proc)
    started = time.monotonic()
    with file_lock(path, timeout=ACQUIRE_BUDGET_S):
        pass
    assert time.monotonic() - started < ACQUIRE_BUDGET_S
    assert path.read_bytes() == before  # no torn tail, nothing appended or lost
    assert len(read_chain(path)) == 3
    reopened = HashChainFile(path)
    reopened.append("k", {"after": "kill"})
    assert len(read_chain(path)) == 4


def test_l2_killed_namespace_lock_holder_frees_the_lock_and_enrollment_still_works(
    tmp_path: Path,
) -> None:
    gov = tmp_path / "gov"
    proc = _spawn(_HOLDER, "namespace", str(gov))
    try:
        _expect_ready(proc)
        with pytest.raises(RegistryNamespaceBusyError), namespace_lock(gov, timeout=0.3):
            pytest.fail("the live holder must exclude us")
    finally:
        _hard_kill(proc)
    assert (gov / hashchain.NAMESPACE_LOCK_NAME).is_file()  # the (empty) lock file stays ...
    started = time.monotonic()
    with namespace_lock(gov, timeout=ACQUIRE_BUDGET_S):  # ... and is not a stale lock
        pass
    assert time.monotonic() - started < ACQUIRE_BUDGET_S
    registry = RunRegistry.enroll_new(gov / "runs.jsonl", enrolled_by="synthetic-test-owner")
    assert len(read_chain(registry.path)) == 1


_APPENDER = """
import sys
from pathlib import Path
from app.research.range002.governance.hashchain import HashChainFile

chain = HashChainFile(Path(sys.argv[1]))
print("READY", flush=True)
for i in range(5000):
    chain.append("k", {"i": i, "pad": "x" * 200})
    print(i, flush=True)
"""


def test_l2_sigkill_during_an_append_loop_never_leaves_a_torn_or_forked_chain(
    tmp_path: Path,
) -> None:
    seed = 20261009
    rng = random.Random(seed)  # the seed is part of any failure message: rounds are replayable
    path = tmp_path / "chain.jsonl"
    _chain_with(path, 1)
    floor = 1
    for round_no in range(20):
        delay = rng.uniform(0.0, 0.12)
        proc = _spawn(_APPENDER, str(path))
        try:
            _expect_ready(proc)
            time.sleep(delay)
        finally:
            _hard_kill(proc)
        assert proc.stdout is not None
        acked = [ln for ln in proc.stdout.read().split() if ln.isdigit()]
        context = f"seed={seed} round={round_no} delay={delay:.4f}"
        raw = path.read_bytes()
        assert raw.endswith(b"\n"), f"torn tail ({context})"
        records = read_chain(path)  # raises on a fork, a bad hash, a bad seq, a torn line
        assert [r.seq for r in records] == list(range(1, len(records) + 1)), context
        # every append the child ACKNOWLEDGED (printed after fsync) must be in the chain
        assert len(records) >= floor + len(acked), f"lost an acknowledged append ({context})"
        floor = len(records)
        with file_lock(path, timeout=ACQUIRE_BUDGET_S):  # never stale
            pass
    HashChainFile(path).append("k", {"final": True})
    assert len(read_chain(path)) == floor + 1
    assert floor > 20, "the loop appended almost nothing: the test did not exercise the lock"


# ---------------------------------------------------------------------------------------------
# L-3: fork inheritance (POSIX only)
# ---------------------------------------------------------------------------------------------


def _fork(body: Callable[[], Any]) -> tuple[int, int]:
    """Fork a child that runs ``body`` and writes its JSON-able result to a pipe, then
    ``os._exit``s (never returns into pytest). Returns ``(pid, read_fd)``."""
    assert hasattr(os, "fork"), "os.fork is missing on this platform: L-3 cannot run (FAIL)"
    read_fd, write_fd = os.pipe()
    pid = os.fork()  # type: ignore[attr-defined,unused-ignore]
    if pid == 0:
        code = 0
        try:
            os.close(read_fd)
            payload: Any = body()
        except BaseException as exc:  # report, never propagate into the parent's pytest
            payload = {"child_exception": type(exc).__name__, "message": str(exc)}
            code = 1
        try:
            os.write(write_fd, json.dumps(payload).encode("utf-8"))
        finally:
            os._exit(code)
    os.close(write_fd)
    return pid, read_fd


def _reap(pid: int, read_fd: int) -> Any:
    chunks = []
    while True:
        data = os.read(read_fd, 65536)
        if not data:
            break
        chunks.append(data)
    os.close(read_fd)
    os.waitpid(pid, 0)
    return json.loads(b"".join(chunks).decode("utf-8")) if chunks else None


def _quick_open(registry: RunRegistry, tag: int) -> str:
    return registry.open_run(
        phase=Phase.P2,
        spec_sha256="1" * 64,
        code_sha="b" * 40,
        data_manifest_sha256="c" * 64,
        partition=Partition.REPLAY_RNG001,
        seeds={"tag": tag},
        exit_candidates=["E1"],
    )


@needs_fork
def test_l3_forked_child_cannot_append_while_the_parent_holds_the_lock(
    tmp_path: Path, registry: RunRegistry
) -> None:
    path = registry.path
    base = read_chain(path)

    def child() -> Any:
        hashchain.LOCK_TIMEOUT_S = 0.5  # bound the wait; this is a module constant, not a mock
        results: dict[str, Any] = {}
        for name, attempt in (
            ("raw", lambda: HashChainFile(path).append("k", {"who": "child"})),
            ("registry", lambda: _quick_open(registry, 99)),  # the INHERITED handle
        ):
            try:
                attempt()
                results[name] = "APPENDED"
            except RegistryIntegrityError as exc:
                results[name] = "refused: " + str(exc)
        return results

    with file_lock(path):
        pid, fd = _fork(child)
        result = _reap(pid, fd)
        # the parent still holds the lock: the file must be byte-identical to before the fork
        assert read_chain(path) == base
    assert result is not None and "child_exception" not in result, result
    # flock excludes by open file DESCRIPTION: the module opens a fresh one per call, so the
    # child is excluded even though it inherited the parent's locked descriptor.
    assert result["raw"].startswith("refused") and "writer lock" in result["raw"], result
    assert result["registry"].startswith("refused") and "writer lock" in result["registry"], result
    # and once the parent has released it, the child's kind of append works
    _quick_open(registry, 1)
    assert len(read_chain(path)) == len(base) + 1


@needs_fork
def test_l3_lock_released_by_the_parent_is_not_kept_by_a_live_forked_child(
    tmp_path: Path, registry: RunRegistry
) -> None:
    path = registry.path
    go_read, go_write = os.pipe()

    def child() -> Any:
        os.close(go_write)
        os.read(go_read, 1)  # wait (bounded by the parent) until the parent says go
        _quick_open(registry, 7)
        return {"appended": True}

    with file_lock(path):
        pid, fd = _fork(child)
    os.close(go_read)
    try:
        started = time.monotonic()
        with file_lock(path, timeout=ACQUIRE_BUDGET_S):  # the child is alive and holds a dup fd
            pass
        assert time.monotonic() - started < ACQUIRE_BUDGET_S, "inherited descriptor kept the lock"
    finally:
        os.write(go_write, b"g")
        os.close(go_write)
    result = _reap(pid, fd)
    assert result == {"appended": True}, result
    records = read_chain(path)
    assert [r.seq for r in records] == list(range(1, len(records) + 1))


_FORKING_HOLDER = """
import os, sys, time
from pathlib import Path
from app.research.range002.governance import hashchain

cm = hashchain.file_lock(Path(sys.argv[1]))
cm.__enter__()
pid = os.fork()
if pid == 0:
    print("CHILD", os.getpid(), flush=True)
    time.sleep(120)
    os._exit(0)
print("PARENT", flush=True)
time.sleep(120)
"""


@needs_fork
def test_l3_killed_parents_lock_stays_held_while_a_forked_descendant_lives(
    tmp_path: Path,
) -> None:
    """Documented behaviour: the flock belongs to the shared open file description, so SIGKILLing
    the holder does NOT free it while a forked descendant still holds the inherited descriptor.
    This fails CLOSED (no second writer), and clears the moment the descendant exits."""
    path = tmp_path / "chain.jsonl"
    _chain_with(path, 2)
    before = path.read_bytes()
    proc = _spawn(_FORKING_HOLDER, str(path))
    descendant = 0
    try:
        assert proc.stdout is not None
        lines = [proc.stdout.readline().split() for _ in range(2)]
        for words in lines:
            if words and words[0] == "CHILD":
                descendant = int(words[1])
        assert descendant > 0, f"no descendant pid in {lines}"
        _hard_kill(proc)  # SIGKILL the lock holder; the forked descendant survives
        os.kill(descendant, 0)  # still alive
        with (
            pytest.raises(RegistryIntegrityError, match="writer lock"),
            file_lock(path, timeout=0.5),
        ):
            pytest.fail("the lock must stay held through the surviving descendant")
        with pytest.raises(RegistryIntegrityError, match="writer lock"):
            _append_bounded(path)
    finally:
        if proc.poll() is None:
            _hard_kill(proc)
        if descendant:
            with contextlib.suppress(ProcessLookupError):
                os.kill(descendant, _SIGKILL)
    deadline = time.monotonic() + ACQUIRE_BUDGET_S
    while True:
        try:
            with file_lock(path, timeout=0.5):
                break
        except RegistryIntegrityError:
            assert time.monotonic() < deadline, "lock still held after the descendant was killed"
    assert path.read_bytes() == before


def _append_bounded(path: Path) -> None:
    old = hashchain.LOCK_TIMEOUT_S
    hashchain.LOCK_TIMEOUT_S = 0.5
    try:
        HashChainFile(path).append("k", {"x": 1})
    finally:
        hashchain.LOCK_TIMEOUT_S = old


def _authorized_p3a(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger
) -> tuple[ResultsCapability, str]:
    run_id = open_run(registry, Phase.P3A, Partition.DEVELOPMENT_SELECTION)
    cap = authorize(
        spec=spec,
        phase=Phase.P3A,
        partition=Partition.DEVELOPMENT_SELECTION,
        run_id=run_id,
        registry=registry,
        exposure_ledger=ledger,
        predecessor_evidence=evidence_for(registry),
    )
    return cap, run_id


def test_l3_capability_cannot_be_serialised_into_another_process(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger
) -> None:
    """Runs on every platform: a capability cannot cross a process boundary by pickling, so a
    ``spawn`` child can never be handed the parent's authorization."""
    cap, _ = _authorized_p3a(spec, registry, ledger)
    assert require_capability(cap) is cap
    with pytest.raises(InvalidCapabilityError):
        pickle.dumps(cap)
    with pytest.raises(InvalidCapabilityError):
        multiprocessing.reduction.ForkingPickler.dumps(cap)  # what spawn/Queue/Pool use


@needs_fork
def test_l3_capability_in_a_forked_child_is_valid_only_while_its_run_is_open(
    spec: GuardSpecView, registry: RunRegistry, ledger: ExposureLedger
) -> None:
    """DOCUMENTED BEHAVIOUR (see the report): ``fork`` copies the parent's memory, including the
    capability and its weak registry binding, so the copy validates while the run is OPEN in the
    registry file. Revocation is carried by the FILE, so it reaches the child too. Forging or
    copying a capability in the child is refused as in the parent."""
    cap, run_id = _authorized_p3a(spec, registry, ledger)

    def check() -> Any:
        out: dict[str, Any] = {}
        try:
            require_capability(cap)
            out["inherited_copy"] = "valid"
        except InvalidCapabilityError as exc:
            out["inherited_copy"] = "rejected: " + str(exc)
        try:
            ResultsCapability()  # type: ignore[call-arg]
            out["forged"] = "ACCEPTED"
        except (InvalidCapabilityError, TypeError) as exc:
            out["forged"] = type(exc).__name__
        try:
            pickle.dumps(cap)
            out["pickled"] = "ACCEPTED"
        except InvalidCapabilityError:
            out["pickled"] = "refused"
        return out

    pid, fd = _fork(check)
    while_open = _reap(pid, fd)
    assert "child_exception" not in while_open, while_open
    assert while_open["inherited_copy"] == "valid", while_open
    assert while_open["forged"] != "ACCEPTED" and while_open["pickled"] == "refused", while_open

    complete_run(registry, run_id)  # the parent closes the run in the registry file
    pid, fd = _fork(check)
    after_close = _reap(pid, fd)
    assert after_close["inherited_copy"].startswith("rejected"), after_close
    with pytest.raises(InvalidCapabilityError):
        require_capability(cap)


@needs_fork
def test_l3_forked_child_handle_appends_under_the_lock_without_forking_the_chain(
    tmp_path: Path, registry: RunRegistry
) -> None:
    for i in range(3):
        _quick_open(registry, i)
    base = registry.count_records()

    def child() -> Any:
        return [_quick_open(registry, 1000 + i) for i in range(20)]  # the INHERITED handle

    pid, fd = _fork(child)
    parent_ids = [_quick_open(registry, 2000 + i) for i in range(20)]  # concurrently
    child_ids = _reap(pid, fd)
    assert isinstance(child_ids, list), child_ids
    records = read_chain(registry.path)  # raises on a fork or a bad prev_hash / seq
    assert len(records) == base + 40
    assert [r.seq for r in records] == list(range(1, base + 41))
    assert len({*child_ids, *parent_ids}) == 40  # no duplicate run id: nobody wrote on a stale view
    # the parent's stale-view handle is still coherent afterwards
    _quick_open(registry, 3000)
    assert len(read_chain(registry.path)) == base + 41
