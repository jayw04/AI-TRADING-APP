from __future__ import annotations

import threading
from pathlib import Path

import pytest

from app.research.range002.governance.errors import (
    HoldoutAlreadyOpenedError,
    HoldoutTokenError,
    HoldoutTokenInvalidError,
)
from app.research.range002.governance.holdout_token import (
    HoldoutToken,
    HoldoutTokenStore,
    TokenState,
)

from .conftest import SPEC_SHA, SYNTH_GENESIS_ID


def test_issue_validate_consume_lifecycle(store: HoldoutTokenStore) -> None:
    assert store.state(SPEC_SHA) is TokenState.NOT_ISSUED
    tok = store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID)
    assert store.state(SPEC_SHA) is TokenState.ISSUED
    assert store.validate_unused(tok, SPEC_SHA, SYNTH_GENESIS_ID) == tok
    store.consume(tok, "run-1")
    assert store.state(SPEC_SHA) is TokenState.CONSUMED
    with pytest.raises(HoldoutAlreadyOpenedError):
        store.validate_unused(tok, SPEC_SHA, SYNTH_GENESIS_ID)
    with pytest.raises(HoldoutAlreadyOpenedError):
        store.consume(tok, "run-2")


def test_one_token_per_spec_hash(store: HoldoutTokenStore) -> None:
    store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID)
    with pytest.raises(HoldoutTokenError, match="already issued"):
        store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID)
    other = store.issue(
        "b" * 64, registry_genesis_id=SYNTH_GENESIS_ID
    )  # a different spec gets its own
    assert other.spec_sha256 == "b" * 64


def test_validate_rejects_bad_tokens(store: HoldoutTokenStore) -> None:
    with pytest.raises(HoldoutTokenInvalidError, match="no holdout token"):
        store.validate_unused(
            HoldoutToken(SPEC_SHA, "x", SYNTH_GENESIS_ID), SPEC_SHA, SYNTH_GENESIS_ID
        )
    tok = store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID)
    with pytest.raises(HoldoutTokenInvalidError, match="HoldoutToken is required"):
        store.validate_unused(None, SPEC_SHA, SYNTH_GENESIS_ID)
    with pytest.raises(HoldoutTokenInvalidError, match="different spec"):
        store.validate_unused(
            HoldoutToken("b" * 64, tok.token_id, SYNTH_GENESIS_ID), SPEC_SHA, SYNTH_GENESIS_ID
        )
    with pytest.raises(HoldoutTokenInvalidError, match="does not match"):
        store.validate_unused(
            HoldoutToken(SPEC_SHA, "forged", SYNTH_GENESIS_ID), SPEC_SHA, SYNTH_GENESIS_ID
        )
    with pytest.raises(HoldoutTokenInvalidError, match="64-hex"):
        store.state("../../etc/passwd")


def test_crash_between_phases_blocks_second_opening(tmp_path: Path) -> None:
    store = HoldoutTokenStore(tmp_path / "t")
    tok = store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID)
    store.begin_consume(tok, "run-1")  # phase 1 durable ...
    # ... process dies before phase 2.  A fresh process sees INTENT:
    fresh = HoldoutTokenStore(tmp_path / "t")
    assert fresh.state(SPEC_SHA) is TokenState.INTENT
    with pytest.raises(HoldoutAlreadyOpenedError):
        fresh.validate_unused(tok, SPEC_SHA, SYNTH_GENESIS_ID)
    with pytest.raises(HoldoutAlreadyOpenedError):
        fresh.consume(tok, "run-2")
    with pytest.raises(HoldoutAlreadyOpenedError):
        fresh.begin_consume(tok, "run-3")
    # the original run can still complete its phase 2 (idempotent recovery of the same run)
    fresh.commit_consume(tok, "run-1")
    assert fresh.state(SPEC_SHA) is TokenState.CONSUMED


def test_crash_injected_inside_consume(
    store: HoldoutTokenStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    tok = store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID)

    def boom(*a: object, **k: object) -> None:
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(store, "commit_consume", boom)
    with pytest.raises(RuntimeError, match="simulated crash"):
        store.consume(tok, "run-1")
    monkeypatch.undo()
    assert store.state(SPEC_SHA) is TokenState.INTENT
    with pytest.raises(HoldoutAlreadyOpenedError):
        store.consume(tok, "run-2")


def test_commit_verifies_intent_matches(store: HoldoutTokenStore) -> None:
    tok = store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID)
    store.begin_consume(tok, "run-1")
    with pytest.raises(HoldoutTokenInvalidError, match="does not match"):
        store.commit_consume(tok, "different-run")
    with pytest.raises(HoldoutTokenInvalidError, match="does not match"):
        store.commit_consume(HoldoutToken(SPEC_SHA, "other", SYNTH_GENESIS_ID), "run-1")
    store.commit_consume(tok, "run-1")
    with pytest.raises(HoldoutAlreadyOpenedError, match="already marked"):
        store.commit_consume(tok, "run-1")


def test_commit_without_intent_fails_closed(store: HoldoutTokenStore) -> None:
    tok = store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID)
    with pytest.raises(HoldoutTokenInvalidError, match="cannot read"):
        store.commit_consume(tok, "run-1")
    assert store.state(SPEC_SHA) is TokenState.ISSUED


def test_corrupt_files_fail_closed(tmp_path: Path) -> None:
    store = HoldoutTokenStore(tmp_path)
    tok = store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID)
    (tmp_path / f"{SPEC_SHA}.token.json").write_text("[1]", encoding="utf-8")
    with pytest.raises(HoldoutTokenInvalidError, match="not an object"):
        store.validate_unused(tok, SPEC_SHA, SYNTH_GENESIS_ID)
    (tmp_path / f"{SPEC_SHA}.token.json").write_text("{bad", encoding="utf-8")
    with pytest.raises(HoldoutTokenInvalidError, match="cannot read"):
        store.validate_unused(tok, SPEC_SHA, SYNTH_GENESIS_ID)


def test_racing_consumers_exactly_one_wins(store: HoldoutTokenStore) -> None:
    tok = store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID)
    results: list[str] = []
    barrier = threading.Barrier(8)

    def worker(i: int) -> None:
        barrier.wait()
        try:
            store.begin_consume(tok, f"run-{i}")
            results.append("won")
        except HoldoutAlreadyOpenedError:
            results.append("lost")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results.count("won") == 1
    assert results.count("lost") == 7


def test_directory_fsync_paths(
    store: HoldoutTokenStore, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise the POSIX directory-fsync branches on any platform."""
    import os

    real_open, real_fsync = os.open, os.fsync
    probe = tmp_path / "probe"
    probe.write_text("x", encoding="utf-8")

    def fake_open(path: object, flags: int, *a: object) -> int:
        if flags == os.O_RDONLY:  # the directory open
            return real_open(probe, os.O_RDONLY)
        return real_open(path, flags, *a)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "open", fake_open)
    store.issue(SPEC_SHA, registry_genesis_id=SYNTH_GENESIS_ID)  # directory fsync succeeds

    state = {"calls": 0}

    def flaky_fsync(fd: int) -> None:
        state["calls"] += 1
        if state["calls"] % 2 == 0:  # every directory fsync fails
            raise OSError("fsync unsupported on directories")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", flaky_fsync)
    store.issue("b" * 64, registry_genesis_id=SYNTH_GENESIS_ID)  # failure ignored

    def no_dir_open(path: object, flags: int, *a: object) -> int:
        if flags == os.O_RDONLY:
            raise OSError("cannot open directory")
        return real_open(path, flags, *a)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "open", no_dir_open)
    store.issue("c" * 64, registry_genesis_id=SYNTH_GENESIS_ID)  # open failure ignored
    assert store.state("c" * 64) is TokenState.ISSUED
