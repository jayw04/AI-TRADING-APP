"""Round 6 (PR 3 remediation): NF1 enrolment scan / enrolled_by cap, NF4 one attempt-limit
constant, NF6 narrow reviewed-I/O lint entry, NF7 one attempt budget per (registry, phase).

Level 1 only (accidental misuse, casual bypass).
"""

from __future__ import annotations

import inspect
import json
import os
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.research.range002.governance import errors, run_registry
from app.research.range002.governance import results_guard as rg
from app.research.range002.governance.exposure_ledger import ExposureLedger
from app.research.range002.governance.hashchain import MAX_RECORD_BYTES, HashChainFile
from app.research.range002.governance.model import MAX_ATTEMPT_LIMIT, DateRange, Partition, Phase
from app.research.range002.governance.run_registry import (
    KIND_GENESIS,
    REGISTRY_MARKER,
    RunRegistry,
)
from tests.research.range002.spec._fixtures import SYNTH_GENESIS_ID

from .conftest import (
    LEDGER_SHA,
    SIGNED_LEDGER,
    _default_guard_fields,
    complete_prereqs,
    forge_guard_view,
    new_registry,
    open_run,
    use_manifest,
)
from .test_import_lint import RANGE002, REVIEWED_PURE, REVIEWED_PURE_IO, flagged, lint_tree

LEDGER = ExposureLedger.from_text(SIGNED_LEDGER)
P3A, SEL = Phase.P3A, Partition.DEVELOPMENT_SELECTION
OTHER_SPEC = "8" * 64


def _auth(spec: Any, reg: RunRegistry, rid: str, **kw: Any) -> Any:
    return rg.authorize(
        spec=spec,
        phase=P3A,
        partition=SEL,
        run_id=rid,
        registry=reg,
        exposure_ledger=LEDGER,
        **kw,
    )


def _spec_for_window(start: date, end: date, **kw: Any) -> Any:
    fields = _default_guard_fields(json.dumps({"exposure_ledger_sha256": LEDGER_SHA}))
    parts = dict(fields["partitions"])
    parts["development_selection"] = (start, end)
    return forge_guard_view(partitions=parts, **kw)


# --- NF1 ----------------------------------------------------------------------------------------


def _hand_made_registry(path: Path, enrolled_by: str) -> None:
    """A real, valid, hash-chained registry whose first line is long (bypasses enroll_new's cap,
    like a reviewer's PoC that wrote the chain itself)."""
    path.touch()
    HashChainFile(path).append(
        KIND_GENESIS,
        {
            "marker": REGISTRY_MARKER,
            "genesis_id": SYNTH_GENESIS_ID,
            "enrollment": {
                "enrolled_by": enrolled_by,
                "enrolled_at_utc": "2026-10-01T00:00:00+00:00",
                "authenticated": False,
            },
        },
    )


def test_nf1_enrolled_by_over_the_cap_is_refused_by_name(tmp_path: Path) -> None:
    with pytest.raises(errors.EnrolledByTooLongError):
        RunRegistry.enroll_new(tmp_path / "a.jsonl", enrolled_by="x" * 70_000)
    assert not (tmp_path / "a.jsonl").exists()
    RunRegistry.enroll_new(tmp_path / "ok.jsonl", enrolled_by="y" * 256)  # the cap is inclusive


def test_nf1_enrolled_by_cap_counts_the_stripped_text(tmp_path: Path) -> None:
    with pytest.raises(errors.EnrolledByTooLongError):
        RunRegistry.enroll_new(tmp_path / "a.jsonl", enrolled_by="x" * 257)
    RunRegistry.enroll_new(tmp_path / "b.jsonl", enrolled_by="  " + "x" * 256 + "  ")


def test_nf1_a_registry_with_a_70kb_first_line_still_blocks_a_second_enrol(tmp_path: Path) -> None:
    """Reviewer PoC: a first line longer than the old 64 KB scan hid the registry."""
    _hand_made_registry(tmp_path / "first.jsonl", "z" * 70_000)
    assert len((tmp_path / "first.jsonl").read_bytes().partition(b"\n")[0]) > 65_536
    with pytest.raises(errors.RegistryEnrollmentError, match="already contains"):
        RunRegistry.enroll_new(tmp_path / "second.jsonl", enrolled_by="owner")
    assert not (tmp_path / "second.jsonl").exists()


def test_nf1_an_oversized_first_line_is_treated_as_a_registry(tmp_path: Path) -> None:
    big = tmp_path / "big.bin"
    big.write_bytes(b"{" + b"a" * (MAX_RECORD_BYTES + 10) + b"\n")  # no record can be this long
    with pytest.raises(errors.RegistryEnrollmentError, match="already contains"):
        RunRegistry.enroll_new(tmp_path / "second.jsonl", enrolled_by="owner")


def test_nf1_an_unreadable_file_is_treated_as_a_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "locked.dat").write_text("x", encoding="utf-8")
    real_open = Path.open

    def deny(self: Path, *a: Any, **k: Any) -> Any:
        if self.name == "locked.dat":
            raise PermissionError("denied")
        return real_open(self, *a, **k)

    monkeypatch.setattr(Path, "open", deny)
    with pytest.raises(errors.RegistryEnrollmentError, match="already contains"):
        RunRegistry.enroll_new(tmp_path / "second.jsonl", enrolled_by="owner")


def test_nf1_ordinary_small_files_and_the_lock_file_do_not_block(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("hello\nworld\n", encoding="utf-8")
    (tmp_path / "other.json").write_text('{"kind": "x"}\n', encoding="utf-8")
    (tmp_path / "nonewline").write_text('{"kind": "run_opened"}', encoding="utf-8")
    RunRegistry.enroll_new(tmp_path / "runs.jsonl", enrolled_by="owner")
    assert os.path.exists(tmp_path / ".range002-namespace.lock")


# --- NF4 ----------------------------------------------------------------------------------------


def test_nf4_one_shared_attempt_limit_constant() -> None:
    assert MAX_ATTEMPT_LIMIT == 10_000


def test_nf4_registry_accepts_the_cap_and_refuses_above_it(tmp_path: Path) -> None:
    reg = new_registry(tmp_path / "runs.jsonl")
    with pytest.raises(errors.RegistryRecordError):
        reg.mark_capability_issued(open_run(reg), attempt_limit=MAX_ATTEMPT_LIMIT + 1)
    reg.mark_capability_issued(open_run(reg), attempt_limit=MAX_ATTEMPT_LIMIT)


def test_nf4_a_manifest_limit_above_the_cap_is_refused_at_load(tmp_path: Path) -> None:
    """PR 2's manifest validation now shares the cap, so an oversized limit never reaches the
    guard: the manifest itself is invalid (fail closed, nothing written)."""
    from app.research.range002.spec.manifest import ManifestInvalidError

    reg = new_registry(tmp_path / "runs.jsonl")
    rid = open_run(reg)
    before = reg.path.read_bytes()
    for bad in (MAX_ATTEMPT_LIMIT + 1, 10**9):
        use_manifest(tmp_path, p3a=bad)
        with pytest.raises(ManifestInvalidError):
            _auth(forge_guard_view(max_p3a_attempts=bad), reg, rid)
        assert reg.path.read_bytes() == before


def test_nf4_the_guard_still_refuses_an_oversized_limit_if_the_manifest_object_is_forged(
    tmp_path: Path,
) -> None:
    """Defence in depth: a manifest object that bypassed validation is refused by name, before
    any write."""
    import dataclasses

    from app.research.range002.spec.manifest import load_manifest

    reg = new_registry(tmp_path / "runs.jsonl")
    rid = open_run(reg)
    before = reg.path.read_bytes()
    forged = dataclasses.replace(
        load_manifest(use_manifest(tmp_path, p3a=2)), max_p3a_attempts=MAX_ATTEMPT_LIMIT + 1
    )
    view = forge_guard_view(max_p3a_attempts=MAX_ATTEMPT_LIMIT + 1)
    with pytest.raises(errors.AttemptLimitOutOfRangeError, match="10000"):
        rg._check_attempt_limit(reg, view, forged, P3A, rid)
    assert reg.path.read_bytes() == before


def test_nf4_a_manifest_limit_at_the_cap_is_accepted(tmp_path: Path) -> None:
    use_manifest(tmp_path, p3a=MAX_ATTEMPT_LIMIT)
    reg = new_registry(tmp_path / "runs.jsonl")
    cap = _auth(forge_guard_view(max_p3a_attempts=MAX_ATTEMPT_LIMIT), reg, open_run(reg))
    assert cap.phase is P3A


# --- NF6 ----------------------------------------------------------------------------------------

_IO_SRC = (
    "from pathlib import Path\n"
    "PURE_FUNCTIONS = ('read_it',)\n"
    "def read_it(p):\n"
    "    return Path(p).read_bytes()\n"
)
_MOD = "app.research.range002.spec.other"


def test_nf6_load_manifest_is_not_a_blanket_pure_entry() -> None:
    assert "app.research.range002.spec.manifest:load_manifest" not in REVIEWED_PURE
    assert "app.research.range002.spec.manifest:load_manifest" in REVIEWED_PURE_IO


def test_nf6_io_allowlist_is_minimal_and_explicit() -> None:
    assert set(REVIEWED_PURE_IO) == {
        "app.research.range002.spec.manifest:load_manifest",
        "app.research.range002.spec.hashing:file_sha256",
    }


def test_nf6_a_different_io_function_declared_pure_is_still_flagged() -> None:
    # even when somebody adds it to the general pure allowlist
    problems = flagged(_IO_SRC, module=_MOD, reviewed=(f"{_MOD}:read_it",))
    assert any("file I/O" in p and "read_it" in p for p in problems), problems


@pytest.mark.parametrize(
    "body",
    [
        "open(p, 'rb').read()",
        "Path(p).read_text()",
        "Path(p).stat()",
        "Path(p).is_file()",
        "Path(p).write_bytes(b'')",
        "list(Path(p).iterdir())",
        "os.remove(p)",
    ],
)
def test_nf6_io_forms_are_detected(body: str) -> None:
    src = (
        "import os\nfrom pathlib import Path\nPURE_FUNCTIONS = ('go',)\n"
        f"def go(p):\n    return {body}\n"
    )
    assert any("file I/O" in p for p in flagged(src, module=_MOD, reviewed=(f"{_MOD}:go",)))


def test_nf6_the_exact_reviewed_io_entry_is_accepted_and_only_that_one() -> None:
    assert not flagged(_IO_SRC, module=_MOD, reviewed=(), reviewed_io=(f"{_MOD}:read_it",))
    other = _IO_SRC.replace("read_it", "read_other")
    assert flagged(other, module=_MOD, reviewed=(), reviewed_io=(f"{_MOD}:read_it",))


def test_nf6_a_pure_function_without_io_is_unaffected() -> None:
    src = "PURE_FUNCTIONS = ('f',)\ndef f(x):\n    return x\n"
    assert not flagged(src, module=_MOD, reviewed=(f"{_MOD}:f",))


def test_nf6_the_real_tree_is_clean() -> None:
    assert lint_tree(RANGE002) == []


# --- NF7 ----------------------------------------------------------------------------------------


def test_nf7_a_different_disjoint_window_chosen_later_shares_the_one_budget(tmp_path: Path) -> None:
    use_manifest(tmp_path, p3a=1)
    reg = new_registry(tmp_path / "runs.jsonl")
    _auth(forge_guard_view(max_p3a_attempts=1), reg, open_run(reg))
    start, end = date(2010, 1, 1), date(2010, 6, 30)  # disjoint from the first window
    later = open_run(reg, protected_range=DateRange(start, end))
    before = reg.path.read_bytes()
    with pytest.raises(errors.AttemptLimitExceededError):
        _auth(_spec_for_window(start, end, max_p3a_attempts=1), reg, later)
    assert reg.path.read_bytes() == before
    assert reg.attempts_consumed(later) == 1


def test_nf7_the_window_is_still_recorded_on_the_run(tmp_path: Path) -> None:
    use_manifest(tmp_path, p3a=2)
    reg = new_registry(tmp_path / "runs.jsonl")
    start, end = date(2010, 1, 1), date(2010, 6, 30)
    rid = open_run(reg, protected_range=DateRange(start, end))
    _auth(_spec_for_window(start, end, max_p3a_attempts=2), reg, rid)
    run = reg.get_run(rid)
    assert run is not None and run.protected_range == DateRange(start, end)


def test_nf7_partial_overlap_modified_params_refreeze_and_other_worktree_share_it(
    tmp_path: Path,
) -> None:
    use_manifest(tmp_path, p3a=1)
    reg = new_registry(tmp_path / "runs.jsonl")
    _auth(forge_guard_view(max_p3a_attempts=1), reg, open_run(reg))
    # a different "worktree": a second handle on the same registry file
    worktree = RunRegistry(reg.path)
    cases = [
        # same window, modified params (a new run)
        (open_run(worktree), forge_guard_view(max_p3a_attempts=1)),
        # spec edit + re-freeze: a new spec hash over the same window
        (
            open_run(worktree, spec_sha=OTHER_SPEC),
            forge_guard_view(max_p3a_attempts=1, spec_sha256=OTHER_SPEC),
        ),
        # partially overlapping window
        (
            open_run(worktree, protected_range=DateRange(date(2018, 1, 1), date(2022, 1, 1))),
            _spec_for_window(date(2018, 1, 1), date(2022, 1, 1), max_p3a_attempts=1),
        ),
    ]
    for rid, spec in cases:
        before = worktree.path.read_bytes()
        with pytest.raises(errors.AttemptLimitExceededError):
            _auth(spec, worktree, rid)
        assert worktree.path.read_bytes() == before


def test_nf7_other_phases_still_have_their_own_budget(tmp_path: Path) -> None:
    use_manifest(tmp_path, p3a=1, p3b=1)
    reg = new_registry(tmp_path / "runs.jsonl")
    spec = forge_guard_view(max_p3a_attempts=1, max_p3b_attempts=1)
    _auth(spec, reg, open_run(reg))
    complete_prereqs(reg, Phase.P3B)
    # P3B is a different phase: its own budget is untouched by the P3A attempt
    assert reg.attempts_consumed(open_run(reg, Phase.P3B, Partition.DEVELOPMENT_CONFIRMATION)) == 0


def test_nf7_the_attempts_consumed_function_ignores_windows() -> None:
    src = inspect.getsource(run_registry.attempts_consumed)
    assert "overlaps" not in src and "protected_range" not in src


def test_nf7_a_budget_reset_argument_is_refused_by_name_before_any_state(tmp_path: Path) -> None:
    use_manifest(tmp_path, p3a=1)
    reg = new_registry(tmp_path / "runs.jsonl")
    rid = open_run(reg)
    before = reg.path.read_bytes()
    with pytest.raises(errors.BudgetResetNotAcceptedError):
        _auth(forge_guard_view(max_p3a_attempts=1), reg, rid, budget_reset_authorization="ok")
    assert reg.path.read_bytes() == before
    # refused first, also with a garbage spec / registry
    with pytest.raises(errors.BudgetResetNotAcceptedError):
        rg.authorize(
            spec=object(),  # type: ignore[arg-type]
            phase=P3A,
            partition=SEL,
            run_id="x",
            registry=object(),  # type: ignore[arg-type]
            exposure_ledger=LEDGER,
            budget_reset_authorization="owner-approved",
        )
    # and once the budget is exhausted the argument does not rescue the request
    _auth(forge_guard_view(max_p3a_attempts=1), reg, rid)
    nxt = open_run(reg)
    with pytest.raises(errors.BudgetResetNotAcceptedError):
        _auth(forge_guard_view(max_p3a_attempts=1), reg, nxt, budget_reset_authorization="x")
    with pytest.raises(errors.AttemptLimitExceededError):
        _auth(forge_guard_view(max_p3a_attempts=1), reg, nxt)


def test_nf7_no_other_reset_path_exists_on_the_registry() -> None:
    assert not [n for n in run_registry.REGISTRY_PUBLIC_API if "reset" in n or "budget" in n]
    for fn in (RunRegistry.mark_capability_issued, RunRegistry.open_run):
        assert not [p for p in inspect.signature(fn).parameters if "reset" in p or "budget" in p]
