"""Round 5 N-C: nonfinite numbers and invalid evidence are rejected BEFORE any registry write.

Every case asserts the three N-C properties: a named error, a byte-identical registry file, and a
registry that stays usable (a subsequent valid append succeeds). Self-contained on purpose (it uses
only the public registry / chain API) so it can be run against the pre-fix code to show it red.
"""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app.research.range002.governance import errors
from app.research.range002.governance.hashchain import HashChainFile, read_chain
from app.research.range002.governance.model import DateRange, Partition, Phase
from app.research.range002.governance.run_registry import RunRegistry

SEL = DateRange(date(2016, 1, 1), date(2019, 12, 31))
GOOD_EVIDENCE = {
    "run_id": "range002-run-000002",
    "audit_pack_sha256": "a" * 64,
    "selection_record_sha256": None,
}


def _registry(tmp_path: Path) -> RunRegistry:
    return RunRegistry.enroll_new(tmp_path / "runs.jsonl", enrolled_by="synthetic-test-owner")


def _open_p3a(reg: RunRegistry) -> str:
    kwargs: dict[str, Any] = {}
    try:  # post-fix registries record the protected window; the pre-fix one has no such field
        return reg.open_run(
            phase=Phase.P3A,
            spec_sha256="1" * 64,
            code_sha="b" * 40,
            data_manifest_sha256="c" * 64,
            partition=Partition.DEVELOPMENT_SELECTION,
            seeds={"s": 1},
            exit_candidates=["E1"],
            protected_range=SEL,
            **kwargs,
        )
    except TypeError:
        return reg.open_run(
            phase=Phase.P3A,
            spec_sha256="1" * 64,
            code_sha="b" * 40,
            data_manifest_sha256="c" * 64,
            partition=Partition.DEVELOPMENT_SELECTION,
            seeds={"s": 1},
            exit_candidates=["E1"],
        )


def _assert_refused_cleanly(reg: RunRegistry, action: Any, exc: type[BaseException]) -> None:
    before = reg.path.read_bytes()
    with pytest.raises(exc):
        action()
    assert reg.path.read_bytes() == before, "a refused write must leave the file byte-identical"
    read_chain(reg.path)  # still a valid chain
    # ... and still usable: a valid append succeeds on the same handle AND on a fresh one
    assert reg.open_run is not None
    _open_p3a(reg)
    _open_p3a(RunRegistry(reg.path))


@pytest.mark.parametrize(
    "bad",
    [
        math.nan,
        math.inf,
        -math.inf,
        {"nested": [1, 2, {"deep": math.nan}]},
        {"t": (1, math.inf)},
    ],
)
def test_nonfinite_numbers_in_a_chain_payload_are_refused_before_writing(
    tmp_path: Path, bad: Any
) -> None:
    reg = _registry(tmp_path)
    chain = HashChainFile(reg.path)
    _assert_refused_cleanly(reg, lambda: chain.append("k", {"v": bad}), errors.RegistryRecordError)


@pytest.mark.parametrize(
    "bad",
    [{1: "int key"}, {"s": {1, 2}}, {"b": b"bytes"}, {"o": object()}, {"c": 1 + 2j}],
)
def test_non_json_values_in_a_chain_payload_are_refused_before_writing(
    tmp_path: Path, bad: Any
) -> None:
    reg = _registry(tmp_path)
    chain = HashChainFile(reg.path)
    _assert_refused_cleanly(reg, lambda: chain.append("k", dict(bad)), errors.RegistryRecordError)


def test_oversized_and_overdeep_payloads_are_refused_before_writing(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    chain = HashChainFile(reg.path)
    _assert_refused_cleanly(
        reg, lambda: chain.append("k", {"big": "x" * (2 << 20)}), errors.RegistryRecordError
    )
    deep: Any = 1
    for _ in range(200):
        deep = {"d": deep}
    _assert_refused_cleanly(reg, lambda: chain.append("k", {"v": deep}), errors.RegistryRecordError)


def test_a_callable_payload_that_returns_nan_is_refused_before_writing(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    chain = HashChainFile(reg.path)
    _assert_refused_cleanly(
        reg, lambda: chain.append("k", lambda _records: {"v": math.nan}), errors.RegistryRecordError
    )


def test_a_float_that_is_not_nan_still_round_trips(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    HashChainFile(reg.path).append("k", {"v": 0.1, "w": -0.0, "x": 1e300})
    read_chain(reg.path)


_BAD_EVIDENCE: list[Any] = [
    [{**GOOD_EVIDENCE, "audit_pack_sha256": math.nan}],
    [{**GOOD_EVIDENCE, "audit_pack_sha256": math.inf}],
    [{**GOOD_EVIDENCE, "audit_pack_sha256": True}],  # bool-as-int / non-string digest
    [{**GOOD_EVIDENCE, "audit_pack_sha256": 1}],
    [{**GOOD_EVIDENCE, "audit_pack_sha256": "A" * 64}],  # uppercase hex
    [{**GOOD_EVIDENCE, "audit_pack_sha256": "a" * 63}],
    [{**GOOD_EVIDENCE, "audit_pack_sha256": "a" * 64 + "\n"}],
    [{**GOOD_EVIDENCE, "selection_record_sha256": math.nan}],
    [{**GOOD_EVIDENCE, "selection_record_sha256": "zz" * 32}],
    [{**GOOD_EVIDENCE, "selection_record_sha256": 0}],
    [{**GOOD_EVIDENCE, "run_id": "../../etc/passwd"}],
    [{**GOOD_EVIDENCE, "run_id": 7}],
    [{**GOOD_EVIDENCE, "run_id": "x" * 100_000}],
    [{**GOOD_EVIDENCE, "extra": "key"}],
    [{"run_id": GOOD_EVIDENCE["run_id"]}],
    ["not a mapping"],
    [GOOD_EVIDENCE] * 100,  # too many items
    "a string is not a sequence of digests",
    {"run_id": "range002-run-000002"},
]


@pytest.mark.parametrize("bad", _BAD_EVIDENCE, ids=range(len(_BAD_EVIDENCE)))
def test_invalid_evidence_is_refused_before_writing(tmp_path: Path, bad: Any) -> None:
    reg = _registry(tmp_path)
    rid = _open_p3a(reg)
    _assert_refused_cleanly(
        reg,
        lambda: reg.mark_capability_issued(rid, evidence=bad, attempt_limit=9),
        errors.RegistryRecordError,
    )
    # the run was never marked, and a valid authorization row can still be written afterwards
    assert reg.get_run(rid).capability_issued_seq is None  # type: ignore[union-attr]
    reg.mark_capability_issued(rid, evidence=[GOOD_EVIDENCE], attempt_limit=9)


@pytest.mark.parametrize("bad", ["xyz", "A" * 64, 5, True, math.nan, "a" * 65])
def test_invalid_manifest_digest_is_refused_before_writing(tmp_path: Path, bad: Any) -> None:
    reg = _registry(tmp_path)
    rid = _open_p3a(reg)
    _assert_refused_cleanly(
        reg,
        lambda: reg.mark_capability_issued(rid, manifest_sha256=bad, attempt_limit=9),
        errors.RegistryRecordError,
    )


@pytest.mark.parametrize("bad", [True, 0, -1, 2.5, math.nan, math.inf, "3", 10**9])
def test_invalid_attempt_limit_is_refused_before_writing(tmp_path: Path, bad: Any) -> None:
    reg = _registry(tmp_path)
    rid = _open_p3a(reg)
    _assert_refused_cleanly(
        reg,
        lambda: reg.mark_capability_issued(rid, attempt_limit=bad),
        errors.RegistryRecordError,
    )


@pytest.mark.parametrize(
    "seeds",
    [{"s": True}, {"s": math.nan}, {"s": 1.5}, {"s": 2**70}, {1: 1}, {}, {"s": "1"}],
)
def test_invalid_seeds_are_refused_before_writing(tmp_path: Path, seeds: Any) -> None:
    reg = _registry(tmp_path)
    before = reg.path.read_bytes()
    with pytest.raises(errors.RegistryRecordError):
        reg.open_run(
            phase=Phase.P2,
            spec_sha256="1" * 64,
            code_sha="b" * 40,
            data_manifest_sha256="c" * 64,
            partition=Partition.REPLAY_RNG001,
            seeds=seeds,
            exit_candidates=["E1"],
        )
    assert reg.path.read_bytes() == before
    _open_p3a(reg)


def test_selection_record_with_nonfinite_number_is_refused_before_writing(tmp_path: Path) -> None:
    reg = _registry(tmp_path)
    rid = _open_p3a(reg)
    spec = "1" * 64
    for bad in (math.nan, math.inf):
        _assert_refused_cleanly(
            reg,
            lambda bad=bad: reg.record_selection(
                rid, {"run_id": rid, "spec_sha256": spec, "score": bad}
            ),
            errors.RegistryRecordError,
        )


def test_the_hash_chain_helpers_use_strict_json(tmp_path: Path) -> None:
    from app.research.range002.governance import hashchain

    with pytest.raises((ValueError, errors.RegistryRecordError)):
        hashchain._line({"v": math.nan})
    with pytest.raises((ValueError, errors.RegistryRecordError)):
        hashchain._canonical({"v": math.inf})
