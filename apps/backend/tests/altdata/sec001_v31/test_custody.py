"""Crash-safe exactly-once: the two crash windows, and atomic publication.

These tests simulate *crashes*, not clean restarts. A clean restart was already survivable;
what the review found is that the states between "request sent" and "evidence sealed" had no
durable representation at all.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from app.altdata.sec001_v31.custody import (
    TERMINAL_STATES,
    AccessionState,
    AcquisitionJournal,
    CustodyViolation,
    InterruptedAcquisition,
    TransactionalEvidenceStore,
    reconcile,
)

ACC = "0000950170-24-018701"
CIK = 97210


# ============================================ crash window A: request sent, not recorded
def test_intent_is_journalled_BEFORE_the_request_so_a_crash_cannot_hide_it(tmp_path):
    """Crash window A: the request went out, then the process died.

    Because intent is durable before the request, the restarted process sees REQUEST_INTENT
    and holds. Under the old counters-plus-set ledger the accession looked un-fetched and
    would have been requested again against a frozen cap.
    """
    p = tmp_path / "j.json"
    j = AcquisitionJournal(p)
    j.transition(ACC, CIK, "10-K", AccessionState.REQUEST_INTENT)
    # ---- process dies here ----

    restarted = AcquisitionJournal(p)
    assert restarted.state_of(ACC) is AccessionState.REQUEST_INTENT
    with pytest.raises(InterruptedAcquisition, match="a request may already have been sent"):
        restarted.guard_fresh(ACC)
    assert [r.accession for r in restarted.interrupted()] == [ACC]


# ============================================ crash window B: acquired, evidence missing
def test_a_crash_after_parse_but_before_custody_is_not_treated_as_complete(tmp_path):
    """Crash window B: the old code marked acquired early, so a missing artifact was
    permanent and the rebuild retry was refused forever."""
    p = tmp_path / "j.json"
    j = AcquisitionJournal(p)
    j.transition(ACC, CIK, "10-K", AccessionState.REQUEST_INTENT)
    j.transition(ACC, CIK, "10-K", AccessionState.REQUEST_SENT)
    j.transition(ACC, CIK, "10-K", AccessionState.RESPONSE_RETAINED)
    j.transition(ACC, CIK, "10-K", AccessionState.PARSED)
    # ---- process dies before publication ----

    restarted = AcquisitionJournal(p)
    assert restarted.state_of(ACC) is AccessionState.PARSED
    assert restarted.state_of(ACC) not in TERMINAL_STATES, "PARSED is NOT complete"
    with pytest.raises(InterruptedAcquisition):
        restarted.guard_fresh(ACC)


def test_only_sealed_and_evidence_unavailable_are_terminal():
    assert {AccessionState.SEALED, AccessionState.EVIDENCE_UNAVAILABLE} == TERMINAL_STATES


def test_a_sealed_accession_is_refused_rather_than_re_requested(tmp_path):
    j = AcquisitionJournal(tmp_path / "j.json")
    j.transition(ACC, CIK, "10-K", AccessionState.REQUEST_INTENT)
    j.seal(ACC, "0" * 64)
    with pytest.raises(CustodyViolation, match="already terminal"):
        j.guard_fresh(ACC)


def test_an_untouched_accession_is_fresh(tmp_path):
    j = AcquisitionJournal(tmp_path / "j.json")
    assert j.state_of("0000000000-00-000000") is AccessionState.AUTHORIZED
    j.guard_fresh("0000000000-00-000000")  # must not raise


def test_journal_survives_restart_with_full_history(tmp_path):
    p = tmp_path / "j.json"
    j = AcquisitionJournal(p)
    for st in (
        AccessionState.REQUEST_INTENT,
        AccessionState.REQUEST_SENT,
        AccessionState.RESPONSE_RETAINED,
    ):
        j.transition(ACC, CIK, "10-K", st)

    reopened = AcquisitionJournal(p)
    rec = reopened.get(ACC)
    assert rec is not None
    assert [h["state"] for h in rec.history] == [
        "REQUEST_INTENT",
        "REQUEST_SENT",
        "RESPONSE_RETAINED",
    ]
    assert all(h["at"].endswith("Z") for h in rec.history)


# ============================================ atomic publication
def test_publication_is_verified_by_rereading_what_landed(tmp_path):
    store = TransactionalEvidenceStore(tmp_path)
    path, digest = store.publish_accession_set(
        CIK,
        ACC,
        "V",
        [{"trading_symbol": "GOOG"}, {"trading_symbol": "GOOGL"}],
        ["o1", "o2"],
        {"b": 1},
    )
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    assert store.verify(CIK, ACC, "V", digest)
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert len(doc["observations"]) == 2 and doc["observation_ids"] == ["o1", "o2"]


def test_no_partial_object_is_left_at_the_final_name(tmp_path):
    """The old code opened the FINAL name then wrote into it, so a mid-write failure left a
    truncated file at the pathname that is supposed to mean 'sealed evidence'."""
    store = TransactionalEvidenceStore(tmp_path)
    final = store.path_for(CIK, ACC, "V")
    assert not final.exists()

    real_link = os.link

    def exploding_link(src, dst):  # publication fails at the last moment
        raise OSError("simulated crash during publication")

    os.link = exploding_link
    try:
        with pytest.raises(OSError):
            store.publish_accession_set(CIK, ACC, "V", [{"x": 1}], ["o1"], {})
    finally:
        os.link = real_link

    assert not final.exists(), "a failed publication must leave NOTHING at the final name"
    assert list(tmp_path.glob("*.partial")) == [], "temporary objects must not survive"


def test_temporary_object_is_complete_before_it_is_published(tmp_path):
    """Whatever exists at the final name is a whole object, because it is linked, not built."""
    store = TransactionalEvidenceStore(tmp_path)
    seen: list[int] = []
    real_link = os.link

    def watching_link(src, dst):
        seen.append(Path(src).stat().st_size)
        return real_link(src, dst)

    os.link = watching_link
    try:
        _p, digest = store.publish_accession_set(CIK, ACC, "V", [{"x": 1}], ["o1"], {})
    finally:
        os.link = real_link

    assert seen and seen[0] > 0
    assert store.verify(CIK, ACC, "V", digest)


def test_publication_is_non_overwriting(tmp_path):
    store = TransactionalEvidenceStore(tmp_path)
    _p, first = store.publish_accession_set(CIK, ACC, "V", [{"x": 1}], ["o1"], {})
    with pytest.raises(CustodyViolation, match="already exists"):
        store.publish_accession_set(CIK, ACC, "V", [{"x": 2}], ["o2"], {})
    assert store.verify(CIK, ACC, "V", first), "original evidence must be untouched"


def test_verify_detects_a_corrupted_published_artifact(tmp_path):
    store = TransactionalEvidenceStore(tmp_path)
    path, digest = store.publish_accession_set(CIK, ACC, "V", [{"x": 1}], ["o1"], {})
    assert store.verify(CIK, ACC, "V", digest)
    path.write_text("truncated", encoding="utf-8")
    assert not store.verify(CIK, ACC, "V", digest)


def test_verify_is_false_when_the_artifact_is_absent(tmp_path):
    store = TransactionalEvidenceStore(tmp_path)
    assert not store.verify(CIK, ACC, "V", "0" * 64)


# ============================================ the invariant, stated as a census
def test_reconcile_names_a_sealed_accession_whose_artifact_vanished(tmp_path):
    """The invariant: no recoverable state has acquired=true and a valid artifact absent.
    Reconcile either proves it or names every accession that breaks it."""
    store = TransactionalEvidenceStore(tmp_path / "ev")
    j = AcquisitionJournal(tmp_path / "j.json")

    _p, digest = store.publish_accession_set(CIK, ACC, "V", [{"x": 1}], ["o1"], {})
    j.transition(ACC, CIK, "10-K", AccessionState.REQUEST_INTENT)
    j.seal(ACC, digest)
    assert reconcile(j, store, "V")["sealed_and_verified"] == [ACC]

    store.path_for(CIK, ACC, "V").unlink()
    report = reconcile(j, store, "V")
    assert report["sealed_but_artifact_missing_or_corrupt"] == [ACC]
    assert report["sealed_and_verified"] == []


def test_reconcile_separates_interrupted_from_unavailable(tmp_path):
    store = TransactionalEvidenceStore(tmp_path / "ev")
    j = AcquisitionJournal(tmp_path / "j.json")
    j.transition("acc-a", 1, "10-K", AccessionState.REQUEST_SENT)
    j.transition("acc-b", 2, "10-Q", AccessionState.EVIDENCE_UNAVAILABLE)

    report = reconcile(j, store, "V")
    assert report["interrupted"] == ["acc-a"]
    assert report["evidence_unavailable"] == ["acc-b"]
