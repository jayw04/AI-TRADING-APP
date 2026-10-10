"""The OS lock backend is asserted, not assumed: on Linux the ``fcntl`` branch must be the one in
use, and a real multi-process test must exercise it. Nothing here skips: a wrong backend FAILS.

Both branches are also executed on every platform through a fake locking module, so the code is
covered everywhere without any ``# pragma: no cover``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.research.range002.governance import hashchain
from app.research.range002.governance.hashchain import read_chain
from app.research.range002.governance.run_registry import RunRegistry

BACKEND_DIR = Path(__file__).resolve().parents[4]


def test_canary_lock_backend_matches_the_platform() -> None:
    expected = "msvcrt" if sys.platform == "win32" else "fcntl"
    assert expected == hashchain.LOCK_BACKEND
    mod = hashchain._lock_module(expected)
    if sys.platform.startswith("linux"):
        assert mod.__name__ == "fcntl" and hasattr(mod, "flock")
    if sys.platform == "win32":
        assert mod.__name__ == "msvcrt" and hasattr(mod, "locking")


def test_the_real_backend_excludes_a_second_holder(tmp_path: Path) -> None:
    path = tmp_path / "f"
    path.write_bytes(b"")
    from app.research.range002.governance.errors import RegistryIntegrityError

    with (
        hashchain.file_lock(path),
        pytest.raises(RegistryIntegrityError, match="writer lock"),
        hashchain.file_lock(path, timeout=0.1),
    ):
        pytest.fail("second holder must not get the lock")
    with hashchain.file_lock(path, timeout=0.1):  # released afterwards
        pass


class _FakeMsvcrt:
    LK_NBLCK = 1
    LK_UNLCK = 2

    def __init__(self, fail: bool) -> None:
        self.fail = fail
        self.calls: list[int] = []

    def locking(self, fd: int, mode: int, n: int) -> None:
        self.calls.append(mode)
        if self.fail and mode == self.LK_NBLCK:
            raise OSError("locked")


class _FakeFcntl:
    LOCK_EX = 1
    LOCK_NB = 2
    LOCK_UN = 8

    def __init__(self, fail: bool) -> None:
        self.fail = fail
        self.calls: list[int] = []

    def flock(self, fd: int, op: int) -> None:
        self.calls.append(op)
        if self.fail and op & self.LOCK_NB:
            raise OSError("locked")


@pytest.mark.parametrize("fail", [False, True])
def test_msvcrt_branch_runs_on_any_platform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail: bool
) -> None:
    fake = _FakeMsvcrt(fail)
    monkeypatch.setattr(hashchain, "LOCK_BACKEND", "msvcrt")
    monkeypatch.setattr(hashchain, "_lock_module", lambda name: fake)
    fd = os.open(tmp_path / "f", os.O_RDWR | os.O_CREAT)
    try:
        assert hashchain._try_lock(fd) is (not fail)
        hashchain._unlock(fd)
    finally:
        os.close(fd)
    assert fake.calls == [fake.LK_NBLCK, fake.LK_UNLCK]


@pytest.mark.parametrize("fail", [False, True])
def test_fcntl_branch_runs_on_any_platform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fail: bool
) -> None:
    fake = _FakeFcntl(fail)
    monkeypatch.setattr(hashchain, "LOCK_BACKEND", "fcntl")
    monkeypatch.setattr(hashchain, "_lock_module", lambda name: fake)
    fd = os.open(tmp_path / "f", os.O_RDWR | os.O_CREAT)
    try:
        assert hashchain._try_lock(fd) is (not fail)
        hashchain._unlock(fd)
    finally:
        os.close(fd)
    assert fake.calls == [fake.LOCK_EX | fake.LOCK_NB, fake.LOCK_UN]


_WORKER = """
import sys
from pathlib import Path
from app.research.range002.governance import hashchain
from app.research.range002.governance.model import Partition, Phase
from app.research.range002.governance.run_registry import RunRegistry

path, tag, n = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
expected = "msvcrt" if sys.platform == "win32" else "fcntl"
assert hashchain.LOCK_BACKEND == expected, hashchain.LOCK_BACKEND
for i in range(n):
    reg = RunRegistry(path)  # fresh (possibly stale) view every time
    rid = reg.open_run(
        phase=Phase.P2, spec_sha256="1" * 64, code_sha="b" * 40,
        data_manifest_sha256="c" * 64, partition=Partition.REPLAY_RNG001,
        seeds={"w": i}, exit_candidates=["E1"],
    )
    print(rid, flush=True)
"""


def test_four_processes_append_concurrently_through_the_real_backend(tmp_path: Path) -> None:
    """4 processes x 25 appends: a valid single chain and no duplicate run id. On Linux this
    drives the fcntl path for real; it never skips."""
    reg = RunRegistry.enroll_new(tmp_path / "runs.jsonl", enrolled_by="synthetic-test-owner")
    env = {**os.environ, "PYTHONPATH": str(BACKEND_DIR)}
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", _WORKER, str(reg.path), f"w{i}", "25"],
            cwd=BACKEND_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for i in range(4)
    ]
    ids: list[str] = []
    for p in procs:
        out, err = p.communicate(timeout=240)
        assert p.returncode == 0, err
        ids.extend(out.split())
    assert len(ids) == 100 and len(set(ids)) == 100
    records = read_chain(reg.path)  # raises on a fork / bad prev_hash / bad seq
    assert len(records) == 101 and [r.seq for r in records] == list(range(1, 102))


def test_namespace_lock_is_exclusive_through_the_real_backend(tmp_path: Path) -> None:
    from app.research.range002.governance.errors import RegistryNamespaceBusyError

    with (
        hashchain.namespace_lock(tmp_path),
        pytest.raises(RegistryNamespaceBusyError),
        hashchain.namespace_lock(tmp_path, timeout=0.1),
    ):
        pytest.fail("second holder must not get the namespace lock")
    assert (tmp_path / hashchain.NAMESPACE_LOCK_NAME).is_file()
    with hashchain.namespace_lock(tmp_path, timeout=0.1):
        pass
