"""Evidence-durability qualification (first generation, kept as the failure-point matrix).

Event vocabulary is the two-phase protocol: read_intent -> read_verified / read_failed.
The per-phase intent/outcome semantics are qualified in test_durable_evidence_two_phase.py.

The 2026-08-19 validation run consumed the one-time opening and then lost its entire custody
record because the launcher wrote evidence only on success. These tests fail the run at each of
the four points that matter and assert that everything already produced survives on disk.

No economic semantics and no solver behaviour are exercised here.
"""

from __future__ import annotations

import json

import pytest

from app.research.mr002.phase3c.durable_evidence import (
    ZERO,
    EvidenceJournal,
    EvidenceJournalFailure,
    JournalingReader,
    materialization_complete,
    terminal,
)


class Obj:
    def __init__(self, key, partition, vid="v1", sha="a" * 64):
        self.key = key
        self.bucket = "workbench-mr002-sealed-219024422756"
        self.version_id = vid
        self.partition = partition
        self.sha256 = sha


SEALED = [Obj(f"validation/t{i}.parquet", "VALIDATION", f"vid{i}") for i in range(1, 7)]
REFERENCE = [Obj(f"reference/r{i}.parquet", "REFERENCE", f"rid{i}") for i in range(1, 5)]


class Reader:
    """Governed-reader stand-in that can be told to explode after N successful reads."""

    reader_kind = "S3"

    def __init__(self, fail_after=None):
        self.fail_after = fail_after
        self.reads = []

    def read(self, obj):
        if self.fail_after is not None and len(self.reads) >= self.fail_after:
            raise RuntimeError(f"reader exploded before {obj.key}")
        self.reads.append((obj.key, obj.version_id))
        return b"x" * 1024


def rows(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def chain_verifies(js):
    prev = ZERO
    for r in js:
        if r["prev_hash"] != prev:
            return False
        prev = r["row_hash"]
    return True


def _drive(tmp_path, fail_after=None, fail_at_materialization=False, fail_in_replay=False):
    """Mimics the launcher's ordering: journal -> reads -> materialization -> replay -> terminal."""
    jpath = str(tmp_path / "run.journal.jsonl")
    j = EvidenceJournal(jpath)
    j.append("run_opened", {"reader_kind": "S3", "window": "validation"})
    reader = JournalingReader(Reader(fail_after), j)
    out = tmp_path / "validation.duckdb"
    try:
        for o in SEALED + REFERENCE:
            reader.read(o)
        if fail_at_materialization:
            raise RuntimeError("materialization exploded")
        out.write_bytes(b"D" * 4096)
        materialization_complete(j, str(out), {"objects_opened": [1] * 10,
                                               "logical_content_identity": "L" * 64})
        if fail_in_replay:
            raise RuntimeError("Stage3Stop: INVALID_RUN: PIQP_MAX_ITER_REACHED")
        j.append("report_ready", {"verdict": "X"})
    except BaseException as exc:                      # noqa: BLE001 - mirrors the launcher
        terminal(j, "FAILED", f"{type(exc).__name__}: {exc}")
        j.close()
        return jpath, exc
    terminal(j, "COMPLETED", "")
    j.close()
    return jpath, None


# ---- 1. failure after sealed object 1 ------------------------------------------------------------
def test_evidence_survives_failure_after_first_sealed_object(tmp_path):
    jpath, exc = _drive(tmp_path, fail_after=1)
    assert exc is not None
    js = rows(jpath)
    opened = [r for r in js if r["kind"] == "read_verified"]
    assert len(opened) == 1
    assert opened[0]["object_id"] == "validation/t1.parquet"
    assert opened[0]["version_id"] == "vid1"
    assert opened[0]["partition"] == "VALIDATION"
    assert js[-1]["kind"] == "terminal" and js[-1]["disposition"] == "FAILED"
    assert chain_verifies(js)


# ---- 2. failure after sealed object 6 (the whole sealed set opened) -------------------------------
def test_evidence_survives_failure_after_sixth_sealed_object(tmp_path):
    jpath, exc = _drive(tmp_path, fail_after=6)
    assert exc is not None
    js = rows(jpath)
    opened = [r for r in js if r["kind"] == "read_verified"]
    assert len(opened) == 6
    assert [o["object_id"] for o in opened] == [o.key for o in SEALED]
    assert all(o["partition"] == "VALIDATION" for o in opened)
    assert not any(r["kind"] == "materialization_complete" for r in js)
    assert js[-1]["disposition"] == "FAILED"
    assert chain_verifies(js)


# ---- 3. failure at materialization, after all 10 opened -------------------------------------------
def test_evidence_survives_failure_at_materialization(tmp_path):
    jpath, exc = _drive(tmp_path, fail_at_materialization=True)
    assert exc is not None
    js = rows(jpath)
    opened = [r for r in js if r["kind"] == "read_verified"]
    assert len(opened) == 10
    assert sum(1 for o in opened if o["partition"] == "VALIDATION") == 6
    assert sum(1 for o in opened if o["partition"] == "REFERENCE") == 4
    assert not any(r["kind"] == "materialization_complete" for r in js)
    assert js[-1]["disposition"] == "FAILED"
    assert chain_verifies(js)


# ---- 4. failure DURING REPLAY — the 2026-08-19 case ------------------------------------------------
def test_evidence_survives_failure_during_replay(tmp_path):
    """This is exactly what destroyed the custody record on the consumed opening."""
    jpath, exc = _drive(tmp_path, fail_in_replay=True)
    assert exc is not None
    js = rows(jpath)
    opened = [r for r in js if r["kind"] == "read_verified"]
    assert len(opened) == 10, "all ten reads must survive a replay failure"
    assert sum(1 for o in opened if o["partition"] == "VALIDATION") == 6
    mat = [r for r in js if r["kind"] == "materialization_complete"]
    assert len(mat) == 1, "materialization evidence must be durable BEFORE replay"
    assert mat[0]["materialized_bytes"] == 4096
    assert mat[0]["materialized_sha256"] and len(mat[0]["materialized_sha256"]) == 64
    term = js[-1]
    assert term["kind"] == "terminal" and term["disposition"] == "FAILED"
    assert "PIQP_MAX_ITER_REACHED" in term["detail"]
    assert chain_verifies(js)


# ---- the success path still records everything -----------------------------------------------------
def test_success_path_records_the_full_sequence(tmp_path):
    jpath, exc = _drive(tmp_path)
    assert exc is None
    js = rows(jpath)
    kinds = [r["kind"] for r in js]
    assert kinds[0] == "run_opened"
    assert kinds.count("read_intent") == 10
    assert kinds.count("read_verified") == 10
    assert "materialization_complete" in kinds
    assert kinds[-1] == "terminal" and js[-1]["disposition"] == "COMPLETED"
    assert chain_verifies(js)


# ---- ordering: materialization evidence precedes replay --------------------------------------------
def test_materialization_evidence_precedes_replay(tmp_path):
    jpath, _ = _drive(tmp_path, fail_in_replay=True)
    js = rows(jpath)
    mat_i = next(i for i, r in enumerate(js) if r["kind"] == "materialization_complete")
    term_i = next(i for i, r in enumerate(js) if r["kind"] == "terminal")
    assert mat_i < term_i
    assert all(r["kind"] in ("read_intent", "read_verified") for r in js[1:mat_i])


# ---- fail-closed: unjournalable evidence stops the run ----------------------------------------------
def test_journal_open_failure_is_fail_closed(tmp_path):
    bad = tmp_path / "nodir"
    bad.write_text("not a directory")
    with pytest.raises(EvidenceJournalFailure):
        EvidenceJournal(str(bad / "sub" / "run.jsonl"))


def test_append_failure_is_fail_closed(tmp_path):
    j = EvidenceJournal(str(tmp_path / "j.jsonl"))
    j._fh.close()                                    # simulate a broken evidence sink
    with pytest.raises(EvidenceJournalFailure):
        j.append("read_intent", {"object_id": "validation/t1.parquet"})


def test_read_does_not_proceed_when_evidence_cannot_be_written(tmp_path):
    j = EvidenceJournal(str(tmp_path / "j.jsonl"))
    r = JournalingReader(Reader(), j)
    j._fh.close()
    with pytest.raises(EvidenceJournalFailure):
        r.read(SEALED[0])


# ---- the journal is a hash chain, and tampering is detectable -----------------------------------------
def test_tampering_breaks_the_chain(tmp_path):
    jpath, _ = _drive(tmp_path)
    js = rows(jpath)
    assert chain_verifies(js)
    js[3]["version_id"] = "tampered"
    assert js[3]["row_hash"] != "", "row_hash present"
    # recomputing the tampered row no longer matches the recorded hash
    import hashlib
    recomputed = hashlib.sha256(
        json.dumps({k: v for k, v in js[3].items() if k != "row_hash"},
                   sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert recomputed != js[3]["row_hash"]


# ---- the reader wrapper does not alter what the governed reader returns --------------------------------
def test_wrapper_is_transparent(tmp_path):
    j = EvidenceJournal(str(tmp_path / "j.jsonl"))
    inner = Reader()
    r = JournalingReader(inner, j)
    payload = r.read(SEALED[0])
    assert payload == b"x" * 1024
    assert inner.reads == [("validation/t1.parquet", "vid1")]
    assert r.reads == inner.reads
    assert r.reader_kind == "S3"


def test_materialization_evidence_records_absent_file(tmp_path):
    j = EvidenceJournal(str(tmp_path / "j.jsonl"))
    row = materialization_complete(j, str(tmp_path / "missing.duckdb"), {})
    assert row["materialized_bytes"] is None
    assert row["materialized_sha256"] is None
