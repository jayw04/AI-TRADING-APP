"""Round-3 adversarial-review fixes (F1, F2, F3, F6, F8, F9, F10).

Threat model T1: a developer acting by accident or casually. Nothing here claims protection
against code execution or write access to the governed directories (T2). Synthetic data only.
"""

from __future__ import annotations

import dataclasses
import json
import os
import threading
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.research.range002.governance import errors, hashchain
from app.research.range002.governance.exposure_ledger import ExposureLedger
from app.research.range002.governance.hashchain import HashChainFile, file_lock, read_chain
from app.research.range002.governance.holdout_token import HoldoutTokenStore
from app.research.range002.governance.model import DateRange, Partition, Phase
from app.research.range002.governance.results_guard import authorize
from app.research.range002.governance.run_registry import RunRegistry, RunStatus
from tests.research.range002.spec._fixtures import make_hardlink, make_symlink

from .conftest import (
    CODE_SHA,
    DEFAULT_SELECTION,
    MANIFEST_SHA,
    SIGNED_LEDGER,
    SPEC_SHA,
    SYNTH_GENESIS_ID,
    make_spec,
    new_registry,
    open_run,
)


def _open(reg: RunRegistry) -> str:
    return reg.open_run(
        phase=Phase.P3A,
        spec_sha256=SPEC_SHA,
        code_sha=CODE_SHA,
        data_manifest_sha256=MANIFEST_SHA,
        partition=Partition.DEVELOPMENT_SELECTION,
        seeds={"b": 1},
        exit_candidates=["E1"],
        protected_range=DEFAULT_SELECTION,
    )


# --- F1: run_id allocated inside the writer lock ------------------------------------------


def test_f1_threads_on_one_handle_get_unique_run_ids(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    ids: list[str] = []
    errs: list[BaseException] = []
    barrier = threading.Barrier(8)

    def work() -> None:
        try:
            barrier.wait()
            for _ in range(25):
                ids.append(_open(reg))
        except BaseException as exc:  # pragma: no cover - surfaced below
            errs.append(exc)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errs
    assert len(ids) == 200 and len(set(ids)) == 200
    assert [r.run_id for r in reg.runs()] == sorted(ids)
    assert len(read_chain(reg.path)) == 201  # 200 runs + the genesis row


def test_f1_stale_second_handle_allocates_a_fresh_run_id(tmp_path: Path) -> None:
    a = new_registry(tmp_path / "runs.jsonl")
    b = RunRegistry(tmp_path / "runs.jsonl")
    first, second = _open(a), _open(b)  # b's view is stale: it re-reads under the lock
    assert first != second
    assert [r.run_id for r in RunRegistry(tmp_path / "runs.jsonl").runs()] == [first, second]


def test_f1_stale_handle_cannot_close_a_run_twice(tmp_path: Path) -> None:
    a = new_registry(tmp_path / "runs.jsonl")
    b = RunRegistry(tmp_path / "runs.jsonl")
    rid = _open(a)
    b.get_run(rid)  # b has seen the run OPEN
    a.close_run(rid, RunStatus.ABORTED, None)
    with pytest.raises(errors.RegistryRecordError, match="already"):
        b.close_run(rid, RunStatus.ABORTED, None)  # the check runs on the fresh view
    assert len(read_chain(a.path)) == 3  # genesis + open + abort


def test_f1_fold_refuses_a_duplicate_run_opened_id(tmp_path: Path) -> None:
    path = tmp_path / "runs.jsonl"
    new_registry(path)
    chain = HashChainFile(path)
    row = {
        "run_id": "range002-run-000001",
        "phase": "P3A",
        "partition": "DEVELOPMENT_SELECTION",
        "spec_sha256": SPEC_SHA,
        "code_sha": CODE_SHA,
        "data_manifest_sha256": MANIFEST_SHA,
        "seeds": {"b": 1},
        "exit_candidates": ["E1"],
        "k_exit_candidates": 1,
    }
    chain.append("run_opened", row)
    chain.append("run_opened", row)
    with pytest.raises(errors.RegistryIntegrityError, match="duplicate run_id"):
        RunRegistry(path).runs()


# --- F9: the lock is keyed on the file's identity, not on a path string -----------------------


def test_f9_hardlink_alias_shares_the_lock(tmp_path: Path) -> None:
    path = tmp_path / "chain.jsonl"
    HashChainFile(path).append("k", {"x": 1})
    alias = tmp_path / "alias.jsonl"
    make_hardlink(alias, path)  # skips only off Linux; on Linux a failure FAILS the test
    with (
        file_lock(path),
        pytest.raises(errors.RegistryIntegrityError, match="writer lock"),
        file_lock(alias, timeout=0.1),
    ):
        pytest.fail("a hardlink alias must not get a second lock")  # pragma: no cover


def test_f9_symlink_alias_shares_the_lock(tmp_path: Path) -> None:
    path = tmp_path / "chain.jsonl"
    HashChainFile(path).append("k", {"x": 1})
    alias = tmp_path / "sym.jsonl"
    make_symlink(alias, path)  # skips only off Linux; on Linux a failure FAILS the test
    with (
        file_lock(path),
        pytest.raises(errors.RegistryIntegrityError, match="writer lock"),
        file_lock(alias, timeout=0.1),
    ):
        pytest.fail("a symlink alias must not get a second lock")  # pragma: no cover


def test_f9_readers_are_not_blocked_by_the_writer_lock(tmp_path: Path) -> None:
    path = tmp_path / "chain.jsonl"
    HashChainFile(path).append("k", {"x": 1})
    with file_lock(path):
        assert len(read_chain(path)) == 1


# --- F10: trailing newline, short writes, duplicate keys, blank lines -----------------------


def test_f10_append_refuses_a_file_without_trailing_newline(tmp_path: Path) -> None:
    path = tmp_path / "chain.jsonl"
    h = HashChainFile(path)
    h.append("k", {"x": 1})
    path.write_bytes(path.read_bytes().rstrip(b"\n"))
    with pytest.raises(errors.ChainNotNewlineTerminatedError):
        HashChainFile(path).append("k", {"x": 2})
    assert not path.read_bytes().endswith(b"\n")  # nothing was concatenated


class _Dribble:
    """os.write that only ever accepts ``n`` bytes (a legal short write)."""

    def __init__(self, real: Any, n: int) -> None:
        self.real, self.n = real, n

    def __call__(self, fd: int, data: bytes) -> int:
        return int(self.real(fd, data[: self.n]))


def test_f10_short_writes_are_looped_not_truncated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(hashchain.os, "write", _Dribble(os.write, 7))
    path = tmp_path / "chain.jsonl"
    HashChainFile(path).append("k", {"x": "y" * 50})
    assert len(read_chain(path)) == 1


def test_f10_zero_byte_write_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hashchain.os, "write", lambda fd, data: 0)
    with pytest.raises(errors.RegistryIntegrityError, match="short write"):
        HashChainFile(tmp_path / "chain.jsonl").append("k", {"x": 1})


def test_f10_holdout_token_short_writes_are_looped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.research.range002.governance import holdout_token

    monkeypatch.setattr(holdout_token.os, "write", _Dribble(os.write, 5))
    store = HoldoutTokenStore(tmp_path / "tokens")
    tok = store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID)
    assert (
        store.validate_unused(tok, SPEC_SHA, SYNTH_GENESIS_ID) == tok
    )  # the JSON was written whole


def test_f10_holdout_token_zero_write_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.research.range002.governance import holdout_token

    monkeypatch.setattr(holdout_token.os, "write", lambda fd, data: 0)
    with pytest.raises(errors.HoldoutTokenError, match="short write"):
        HoldoutTokenStore(tmp_path / "tokens").issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID)


def test_f10_chain_with_duplicate_json_keys_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "chain.jsonl"
    HashChainFile(path).append("k", {"x": 1})
    line = path.read_text(encoding="utf-8")
    # last-wins parsing would keep the hash valid; a strict reader must not
    path.write_text(
        line.replace('"kind":"k"', '"kind":"zzz","kind":"k"'), encoding="utf-8", newline="\n"
    )
    with pytest.raises(errors.RegistryIntegrityError, match="duplicate"):
        read_chain(path)


def test_f10_blank_line_inside_the_chain_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "chain.jsonl"
    h = HashChainFile(path)
    h.append("k", {"x": 1})
    h.append("k", {"x": 2})
    first, second = path.read_text(encoding="utf-8").splitlines()
    path.write_text(first + "\n\n" + second + "\n", encoding="utf-8", newline="\n")
    with pytest.raises(errors.RegistryIntegrityError, match="blank"):
        read_chain(path)


def test_f10_non_canonical_line_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "chain.jsonl"
    HashChainFile(path).append("k", {"x": 1})
    rec = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(
        json.dumps(rec, indent=1) + "\n", encoding="utf-8", newline="\n"
    )  # same content, new bytes
    with pytest.raises(errors.RegistryIntegrityError, match="canonical"):
        read_chain(path)


def test_f10_stale_handle_proceeds_when_chain_is_still_valid(tmp_path: Path) -> None:
    path = tmp_path / "chain.jsonl"
    a, b = HashChainFile(path), HashChainFile(path)
    a.append("k", {"x": 1})
    rec = b.append("k", {"x": 2})  # stale view: re-read under the lock, chain intact
    assert rec.seq == 2 and b.count == 2
    assert len(read_chain(path)) == 2


def test_f10_stale_handle_still_refuses_a_replaced_history(tmp_path: Path) -> None:
    path = tmp_path / "chain.jsonl"
    a = HashChainFile(path)
    a.append("k", {"x": 1})
    other = tmp_path / "other.jsonl"
    HashChainFile(other).append("k", {"x": 999})
    path.write_bytes(other.read_bytes())  # different history, same length
    with pytest.raises(errors.RegistryIntegrityError, match="no longer contains"):
        a.append("k", {"x": 2})


# --- F2: exact collaborator types; ledger only from its loaders -----------------------------


def _auth(spec: Any, registry: Any, ledger: Any, rid: str, **kw: Any) -> Any:
    return authorize(
        spec=spec,
        phase=Phase.P3A,
        partition=Partition.DEVELOPMENT_SELECTION,
        run_id=rid,
        registry=registry,
        exposure_ledger=ledger,
        **kw,
    )


def test_f2_ledger_cannot_be_constructed_directly() -> None:
    real = ExposureLedger.from_text(SIGNED_LEDGER)
    with pytest.raises((errors.ExposureLedgerError, TypeError)):
        ExposureLedger((), {"signed_by": "x", "signed_on": "2026-01-01"}, real.sha256)  # type: ignore[call-arg]
    with pytest.raises(errors.ExposureLedgerError):
        ExposureLedger(object(), (), {"signed_by": "x", "signed_on": "2026-01-01"}, real.sha256)  # type: ignore[call-arg, arg-type]


def test_f2_ledger_is_immutable() -> None:
    led = ExposureLedger.from_text(SIGNED_LEDGER)
    with pytest.raises((AttributeError, TypeError)):
        led._sha256 = "0" * 64  # type: ignore[misc]
    with pytest.raises((AttributeError, TypeError)):
        led.extra = 1  # type: ignore[attr-defined]


def test_f2_duck_typed_collaborators_are_refused_by_name(tmp_path: Path) -> None:
    spec = make_spec()
    reg = new_registry(tmp_path / "runs.jsonl")
    rid = open_run(reg)
    led = ExposureLedger.from_text(SIGNED_LEDGER)

    class FakeRegistry:
        def __getattr__(self, name: str) -> Any:
            return getattr(reg, name)

    class FakeLedger:
        sha256 = led.sha256
        entries = ()

        def require_signed(self) -> None:
            return None

        def overlaps(self, window: DateRange) -> tuple[()]:
            return ()

    class FakeStore:
        pass

    with pytest.raises(errors.RegistryNotTrustedError):
        _auth(spec, FakeRegistry(), led, rid)
    with pytest.raises(errors.ExposureLedgerNotTrustedError):
        _auth(spec, reg, FakeLedger(), rid)
    with pytest.raises(errors.HoldoutStoreNotTrustedError):
        _auth(spec, reg, led, rid, holdout_store=FakeStore())
    with pytest.raises(errors.CollaboratorNotTrustedError):
        _auth(spec, None, led, rid)


def test_f2_subclassed_registry_is_refused(tmp_path: Path) -> None:
    class Sub(RunRegistry):  # type: ignore[misc]
        pass

    new_registry(tmp_path / "runs.jsonl")
    reg = Sub(tmp_path / "runs.jsonl")
    rid = open_run(reg)
    with pytest.raises(errors.RegistryNotTrustedError):
        _auth(make_spec(), reg, ExposureLedger.from_text(SIGNED_LEDGER), rid)


# --- F3: GuardSpecView only from a SpecView minted by load_frozen ---------------------------


def test_f3_hand_built_spec_view_is_refused() -> None:
    from app.research.range002.governance.spec_adapter import to_guard_view
    from app.research.range002.spec.loader import SpecView

    hand = SpecView(
        spec_sha256="a" * 64,
        is_signed=True,
        partitions={
            "development_selection": (date(2016, 1, 1), date(2019, 12, 31)),
            "development_confirmation": (date(2020, 1, 1), date(2021, 12, 31)),
            "holdout": (date(2022, 1, 1), date(2025, 12, 31)),
        },
        exposed_windows=(),
        p3_criteria=1,
        exits_candidates=None,
        exits_selection=None,
    )
    with pytest.raises(errors.SpecViewNotTrustedError, match="load_frozen"):
        to_guard_view(hand)


def test_f3_dataclasses_replace_of_a_real_view_loses_the_mint(tmp_path: Path) -> None:
    from app.research.range002.governance.spec_adapter import to_guard_view
    from app.research.range002.spec.loader import SpecView

    from .conftest import load_synthetic_view

    real = load_synthetic_view(tmp_path, signed=False)
    assert isinstance(real, SpecView) and real.is_signed is False
    forged = dataclasses.replace(real, is_signed=True)
    with pytest.raises(errors.SpecViewNotTrustedError):
        to_guard_view(forged)


def test_f3_build_view_is_no_longer_public() -> None:
    from app.research.range002.spec import loader

    assert not hasattr(loader, "build_view")


def test_f3_real_load_path_is_accepted(tmp_path: Path) -> None:
    from app.research.range002.governance.spec_adapter import to_guard_view

    from .conftest import load_synthetic_view

    gv = to_guard_view(load_synthetic_view(tmp_path, signed=True))
    assert gv.is_signed is True
