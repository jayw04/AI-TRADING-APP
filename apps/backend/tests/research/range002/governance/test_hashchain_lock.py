"""M3 (partial): an OS file lock across read -> verify -> append stops concurrent writers
forking the chain. (External head anchoring is NOT implemented -- owner decision pending.)"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from app.research.range002.governance.errors import RegistryIntegrityError
from app.research.range002.governance.hashchain import HashChainFile, file_lock, read_chain

BACKEND_DIR = Path(__file__).resolve().parents[4]

_WORKER = """
import sys
from pathlib import Path
from app.research.range002.governance.errors import RegistryIntegrityError
from app.research.range002.governance.hashchain import HashChainFile

path, tag, n = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
done = 0
while done < n:
    handle = HashChainFile(path)  # fresh view of the chain on every attempt
    try:
        handle.append("k", {"w": tag, "i": done})
        done += 1
    except RegistryIntegrityError:
        pass  # lost the race to another writer: re-read and retry (never fork)
"""


def _assert_single_valid_chain(path: Path, expected: int) -> None:
    records = read_chain(path)  # raises on any fork / bad prev_hash / bad seq
    assert len(records) == expected
    assert [r.seq for r in records] == list(range(1, expected + 1))


def test_threads_with_stale_views_never_fork_the_chain(tmp_path: Path) -> None:
    path = tmp_path / "chain.jsonl"
    HashChainFile(path)
    n_threads, per_thread = 6, 8
    barrier = threading.Barrier(n_threads)
    errors: list[BaseException] = []

    def work(tag: int) -> None:
        try:
            barrier.wait()
            done = 0
            while done < per_thread:
                handle = HashChainFile(path)
                try:
                    handle.append("k", {"t": tag, "i": done})
                    done += 1
                except RegistryIntegrityError:
                    continue  # stale view: refused, not forked
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    _assert_single_valid_chain(path, n_threads * per_thread)


def test_processes_serialize_appends_without_forking(tmp_path: Path) -> None:
    path = tmp_path / "chain.jsonl"
    HashChainFile(path)
    env = {**os.environ, "PYTHONPATH": str(BACKEND_DIR)}
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", _WORKER, str(path), f"p{i}", "6"],
            cwd=BACKEND_DIR,
            env=env,
            stderr=subprocess.PIPE,
        )
        for i in range(4)
    ]
    for proc in procs:
        _, err = proc.communicate(timeout=120)
        assert proc.returncode == 0, err.decode()
    _assert_single_valid_chain(path, 4 * 6)


def test_second_writer_with_same_stale_view_serialises_after_the_first(tmp_path: Path) -> None:
    """Round 3: the stale writer re-reads under the lock and appends AFTER the first; the chain
    never forks (it used to be refused outright, which pushed retry logic onto every caller)."""
    path = tmp_path / "chain.jsonl"
    a, b = HashChainFile(path), HashChainFile(path)  # both see the empty chain
    a.append("k", {"x": 1})
    b.append("k", {"x": 2})
    _assert_single_valid_chain(path, 2)


def test_lock_is_exclusive_and_fails_closed_on_timeout(tmp_path: Path) -> None:
    path = tmp_path / "chain.jsonl"
    with (
        file_lock(path),
        pytest.raises(RegistryIntegrityError, match="writer lock"),
        file_lock(path, timeout=0.1),
    ):
        pytest.fail("the lock must not be re-entrant across handles")  # pragma: no cover
    with file_lock(path, timeout=0.1):  # released afterwards
        pass


def test_append_blocked_by_a_held_lock_is_refused_not_forked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.research.range002.governance import hashchain

    path = tmp_path / "chain.jsonl"
    handle = HashChainFile(path)
    monkeypatch.setattr(hashchain, "LOCK_TIMEOUT_S", 0.1)
    with file_lock(path), pytest.raises(RegistryIntegrityError, match="writer lock"):
        handle.append("k", {"x": 1})
    assert read_chain(path) == ()
