"""Round 5 N-D: concurrent ``enroll_new`` calls cannot create several authoritative registries in
one governance namespace (directory). Real OS processes, real races, several rounds.

Self-contained (public ``RunRegistry`` API only) so it can be run against the pre-fix code to show
it red. Level 1: the namespace lock serialises cooperating callers; it is not a defence against
a process that does not use ``enroll_new``.
"""

from __future__ import annotations

import multiprocessing as mp
import queue
from pathlib import Path
from typing import Any

import pytest

N_PROCS = 8
N_ROUNDS = 200


def _worker(
    idx: int, root: str, rounds: int, mode: str, barrier: Any, results: Any
) -> None:  # runs in a spawned process
    from app.research.range002.governance.errors import RegistryEnrollmentError
    from app.research.range002.governance.run_registry import RunRegistry

    for r in range(rounds):
        try:
            barrier.wait(timeout=120)
        except Exception as exc:  # BrokenBarrierError: report and stop
            results.put((r, idx, "error", f"barrier: {exc!r}"))
            return
        name = f"runs_{idx}.jsonl" if mode == "different" else "runs.jsonl"
        path = Path(root) / f"round{r:02d}" / name
        try:
            reg = RunRegistry.enroll_new(path, enrolled_by=f"proc-{idx}")
            results.put((r, idx, "won", reg.genesis_id))
        except RegistryEnrollmentError as exc:
            results.put((r, idx, "refused", type(exc).__name__))
        except BaseException as exc:  # anything else is a failure of the property
            results.put((r, idx, "error", repr(exc)))


def _race(tmp_path: Path, mode: str) -> dict[int, list[tuple[int, str, str]]]:
    ctx = mp.get_context("spawn")
    barrier = ctx.Barrier(N_PROCS)
    results = ctx.Queue()
    procs = [
        ctx.Process(target=_worker, args=(i, str(tmp_path), N_ROUNDS, mode, barrier, results))
        for i in range(N_PROCS)
    ]
    for p in procs:
        p.start()
    by_round: dict[int, list[tuple[int, str, str]]] = {r: [] for r in range(N_ROUNDS)}
    try:
        for _ in range(N_PROCS * N_ROUNDS):
            r, idx, outcome, detail = results.get(timeout=300)
            by_round[r].append((idx, outcome, detail))
    except queue.Empty:
        pytest.fail("enrollment workers did not report in time")
    finally:
        for p in procs:
            p.join(timeout=60)
            if p.is_alive():
                p.kill()
    return by_round


def _registry_files(directory: Path) -> list[Path]:
    out = []
    for f in directory.iterdir():
        if f.is_file() and f.suffix == ".jsonl":
            out.append(f)
    return out


@pytest.mark.parametrize("mode", ["different", "same"])
def test_exactly_one_enrollment_wins_each_round(tmp_path: Path, mode: str) -> None:
    by_round = _race(tmp_path, mode)
    for r, rows in by_round.items():
        errors_seen = [row for row in rows if row[1] == "error"]
        assert not errors_seen, f"round {r}: unexpected errors {errors_seen}"
        winners = [row for row in rows if row[1] == "won"]
        refused = [row for row in rows if row[1] == "refused"]
        assert len(winners) == 1, f"round {r}: {len(winners)} winners ({mode} names)"
        assert len(refused) == N_PROCS - 1
        assert {row[2] for row in refused} == {"RegistryEnrollmentError"}
        files = _registry_files(tmp_path / f"round{r:02d}")
        assert len(files) == 1, f"round {r}: {[f.name for f in files]} registries exist"
        from app.research.range002.governance.run_registry import RunRegistry

        assert RunRegistry(files[0]).genesis_id == winners[0][2]
