"""Two-phase evidence protocol qualification.

The first durability implementation journalled only AFTER the governed read, and claimed a read
could never proceed un-evidenced. That claim was false: an append failing after a successful read
left a sealed byte read with no durable row. The protocol is now

    fsync read_intent -> governed read -> fsync read_verified (or read_failed)

so the intent row bounds the opening even if the process dies immediately after the read.

No economic semantics and no solver behaviour are exercised here.
"""

from __future__ import annotations

import json

import pytest

from app.research.mr002.phase3c.durable_evidence import (
    EvidenceJournal,
    EvidenceJournalFailure,
    JournalingReader,
    reconcile,
    terminal,
)


class Obj:
    def __init__(self, key, partition, vid, sha="a" * 64):
        self.key = key
        self.bucket = "workbench-mr002-sealed-219024422756"
        self.version_id = vid
        self.partition = partition
        self.sha256 = sha


SEALED1 = Obj("validation/actions.parquet", "VALIDATION", "wJ6QFkeb")
SEALED2 = Obj("validation/prices.parquet", "VALIDATION", "eC8XZGBP")


class Reader:
    reader_kind = "S3"

    def __init__(self, explode=False):
        self.explode = explode
        self.calls = 0
        self.reads = []

    def read(self, obj):
        self.calls += 1
        if self.explode:
            raise RuntimeError("governed read/verification failed")
        self.reads.append((obj.key, obj.version_id))
        return b"p" * 2048


class BreakAfter(EvidenceJournal):
    """Journal that dies after N successful appends -- to break phase 2 specifically."""

    def __init__(self, path, break_after):
        super().__init__(path)
        self.break_after = break_after
        self.n = 0

    def append(self, kind, payload):
        if self.n >= self.break_after:
            raise EvidenceJournalFailure(f"sink broken before {kind}")
        self.n += 1
        return super().append(kind, payload)


def rows(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


# ---- 1. failure to persist read_intent -> the inner reader is NEVER called -----------------------
def test_intent_failure_means_the_governed_read_never_happens(tmp_path):
    j = BreakAfter(str(tmp_path / "j.jsonl"), break_after=0)
    inner = Reader()
    r = JournalingReader(inner, j)
    with pytest.raises(EvidenceJournalFailure):
        r.read(SEALED1)
    assert inner.calls == 0, "no sealed byte may be read without a durable intent"
    assert rows(str(tmp_path / "j.jsonl")) == []


# ---- 2. intent + governed read + verified ---------------------------------------------------------
def test_happy_path_writes_intent_then_verified(tmp_path):
    p = str(tmp_path / "j.jsonl")
    j = EvidenceJournal(p)
    inner = Reader()
    payload = JournalingReader(inner, j).read(SEALED1)
    assert payload == b"p" * 2048
    js = rows(p)
    assert [x["kind"] for x in js] == ["read_intent", "read_verified"]
    assert js[0]["object_id"] == SEALED1.key
    assert js[0]["version_id"] == SEALED1.version_id
    assert js[0]["declared_sha256"] == SEALED1.sha256
    assert js[0]["partition"] == "VALIDATION"
    assert js[1]["intent_sequence"] == js[0]["sequence"]
    assert js[1]["intent_row_hash"] == js[0]["row_hash"]
    assert js[1]["bytes"] == 2048
    rec = reconcile(js)
    assert rec["classification"] == "EVIDENCE_COMPLETE"
    assert rec["chain_verifies"] and rec["sealed_verified"] == 1


# ---- 3. intent succeeds, the governed read fails --------------------------------------------------
def test_intent_then_reader_failure_records_read_failed(tmp_path):
    p = str(tmp_path / "j.jsonl")
    j = EvidenceJournal(p)
    inner = Reader(explode=True)
    with pytest.raises(RuntimeError):
        JournalingReader(inner, j).read(SEALED1)
    js = rows(p)
    assert [x["kind"] for x in js] == ["read_intent", "read_failed"]
    assert js[1]["intent_sequence"] == js[0]["sequence"]
    assert "governed read/verification failed" in js[1]["error"]
    rec = reconcile(js)
    assert rec["classification"] == "EVIDENCE_COMPLETE"   # the intent IS resolved, by a failure
    assert rec["verified"] == 0 and rec["failed"] == 1


# ---- 4. read succeeds, writing read_verified fails -> fatal stop, intent survives -------------------
def test_verified_append_failure_is_fatal_and_intent_survives(tmp_path):
    p = str(tmp_path / "j.jsonl")
    j = BreakAfter(p, break_after=1)                      # intent OK, verified breaks
    inner = Reader()
    with pytest.raises(EvidenceJournalFailure):
        JournalingReader(inner, j).read(SEALED1)
    assert inner.calls == 1, "the governed read did happen"
    js = rows(p)
    assert [x["kind"] for x in js] == ["read_intent"]
    assert js[0]["object_id"] == SEALED1.key
    rec = reconcile(js)
    assert rec["classification"] == "EVIDENCE_INCOMPLETE"
    assert rec["unresolved_objects"] == [SEALED1.key]


# ---- 5. process death between the read and the verified append -------------------------------------
def test_process_death_after_read_leaves_intent_and_is_evidence_incomplete(tmp_path):
    """Simulates SIGKILL after the governed read: only the intent reached disk."""
    p = str(tmp_path / "j.jsonl")
    j = EvidenceJournal(p)
    inner = Reader()
    r = JournalingReader(inner, j)
    r.read(SEALED1)                                       # fully evidenced
    # now the second object: intent persisted, read happens, then the process dies
    j2 = BreakAfter(p, break_after=1)
    with pytest.raises(EvidenceJournalFailure):
        JournalingReader(inner, j2).read(SEALED2)
    js = rows(p)
    kinds = [x["kind"] for x in js]
    assert kinds == ["read_intent", "read_verified", "read_intent"]
    rec = reconcile(js)
    assert rec["classification"] == "EVIDENCE_INCOMPLETE", \
        "a run with a dangling intent is never silently complete"
    assert rec["unresolved_objects"] == [SEALED2.key]
    assert rec["sealed_verified"] == 1


# ---- 6. sequence / hash-chain reconciliation between intent and outcome rows -------------------------
def test_chain_and_sequence_reconciliation(tmp_path):
    p = str(tmp_path / "j.jsonl")
    j = EvidenceJournal(p)
    r = JournalingReader(Reader(), j)
    r.read(SEALED1)
    r.read(SEALED2)
    terminal(j, "COMPLETED", "")
    js = rows(p)
    rec = reconcile(js)
    assert rec["chain_verifies"]
    assert rec["intents"] == 2 and rec["verified"] == 2 and rec["failed"] == 0
    assert rec["unresolved_intents"] == []
    assert rec["classification"] == "EVIDENCE_COMPLETE"
    # every outcome points back at a real intent, by sequence AND by row hash
    by_seq = {x["sequence"]: x for x in js}
    for out in (x for x in js if x["kind"] == "read_verified"):
        src = by_seq[out["intent_sequence"]]
        assert src["kind"] == "read_intent"
        assert src["row_hash"] == out["intent_row_hash"]
        assert src["object_id"] == out["object_id"]


def test_tampering_is_detected_by_reconcile(tmp_path):
    p = str(tmp_path / "j.jsonl")
    j = EvidenceJournal(p)
    JournalingReader(Reader(), j).read(SEALED1)
    js = rows(p)
    assert reconcile(js)["chain_verifies"]
    js[0]["version_id"] = "tampered"
    assert not reconcile(js)["chain_verifies"]


def test_reconcile_reports_partition_split(tmp_path):
    p = str(tmp_path / "j.jsonl")
    j = EvidenceJournal(p)
    r = JournalingReader(Reader(), j)
    r.read(SEALED1)
    r.read(Obj("reference/crosswalk.parquet", "REFERENCE", "ux3JpvSp"))
    rec = reconcile(rows(p))
    assert rec["sealed_verified"] == 1
    assert rec["reference_verified"] == 1
    assert rec["classification"] == "EVIDENCE_COMPLETE"
