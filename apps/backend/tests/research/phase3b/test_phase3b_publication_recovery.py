"""Recovery package for validation attempt #1, which was VOID due to execution infrastructure.

That run consumed its opening, read all eight sealed objects successfully, and produced nothing.
Two defects did it:

  * the governed output directory was never created - vacancy was checked and files were opened
    O_CREAT|O_EXCL, but no component called makedirs;
  * publication ran from the finalization path, so its exception REPLACED the primary computation
    exception. The real reason the run failed is unknowable from the surviving evidence.

The second defect is the worse one: it destroyed the diagnosis. So the invariant these tests
enforce is:

    publication is attempted only after the terminal computation outcome is captured, and
    publication may ANNOTATE that outcome but can NEVER overwrite it.
"""

from __future__ import annotations

import json
import os

import pytest

from app.research.mr002.phase3b import publish as P
from app.research.mr002.phase3b import runner as RUN
from app.research.mr002.phase3b import states as S

PRIMARY = "PRIMARY_FAILURE_X"
SECONDARY = "PUBLICATION_FAILURE_Y"


# -- defect 1: the destination hierarchy ---------------------------------------------------


def test_ensure_root_creates_the_governed_hierarchy(tmp_path):
    root = str(tmp_path / "out" / "valoos" / "validation")
    assert not os.path.exists(root)
    P.ensure_root(root)
    assert os.path.isdir(root)


def test_ensure_root_still_refuses_an_occupied_destination(tmp_path):
    """Creating the tree must not become tolerance for an occupied one.

    Vacancy is defined over the REGISTERED artifact slots, not over arbitrary files: the run writes
    only its own artifacts, so an unrelated file is not a collision. An occupied slot is.
    """
    root = tmp_path / "out" / "valoos" / "validation"
    root.mkdir(parents=True)
    (root / P.REPORT).write_text("{}")
    with pytest.raises(P.PublicationRefused, match="output_root_occupied"):
        P.ensure_root(str(root))


def test_publication_succeeds_into_a_freshly_created_root(tmp_path):
    """The exact failure of attempt #1: destination_uncreatable on a missing directory."""
    root = str(tmp_path / "out" / "valoos" / "validation")
    P.ensure_root(root)
    rec = P.publish_run(
        root,
        report={"run_id": "r"},
        disposition=P.PASS,
        exit_code=0,
        identities={"code_identity": "c", "runtime_identity": "r", "governing_identity": "g"},
        deliverable_hashes=dict.fromkeys(P.DELIVERABLES, "0" * 64),
        clock=lambda: "2026-08-13T00:00:00Z",
    )
    assert rec["publication_sha256"]
    assert os.path.isfile(os.path.join(root, P.PUBLICATION))


# -- defect 2: the masking bug -------------------------------------------------------------


class _Sequence:
    def __init__(self, state):
        self.state = state
        self.history = [state]
        self.opening_consumed = True

    def advance(self, to):
        self.state = to
        self.history.append(to)


def _runner_with(primary_exc, publication_exc, tmp_path):
    """A runner whose computation fails with X and whose publication fails with Y."""
    r = RUN.Phase3BRunner.__new__(RUN.Phase3BRunner)
    r.output_root = str(tmp_path / "out")
    r.sequence = _Sequence(S.S10_ENRICHED)
    r.guard = None

    def preflight():
        raise RuntimeError(PRIMARY) if primary_exc else None

    r.preflight = preflight
    r._assume_reader = lambda: None
    r._consume_opening = lambda: {}
    r._publish_run = lambda outcome: (_ for _ in ()).throw(P.PublicationRefused(SECONDARY))
    return r


def test_a_publication_failure_never_replaces_the_primary_failure(tmp_path):
    """THE falsification. Computation throws X, publication throws Y; X must remain primary."""
    r = _runner_with(primary_exc=True, publication_exc=True, tmp_path=tmp_path)
    outcome = RUN.Phase3BRunner.run(r)

    assert PRIMARY in (outcome.error or ""), "the primary failure was lost"
    assert PRIMARY in (outcome.primary_error or "")
    assert outcome.primary_disposition == outcome.disposition
    # ...and the secondary failure is recorded rather than discarded
    assert SECONDARY in (outcome.publication_error or ""), "the publication failure vanished"
    assert outcome.published is False
    # both are present, and the primary is the one that governs
    assert outcome.error != outcome.publication_error


def test_the_terminal_outcome_is_captured_before_publication_is_attempted(tmp_path):
    r = _runner_with(primary_exc=True, publication_exc=True, tmp_path=tmp_path)
    outcome = RUN.Phase3BRunner.run(r)
    assert outcome.primary_disposition is not None, "no immutable terminal outcome was captured"
    assert outcome.primary_disposition == P.REFUSED


def test_a_publication_failure_does_not_raise_out_of_the_runner(tmp_path):
    """Attempt #1 raised out of finally, which is how the evidence was destroyed."""
    r = _runner_with(primary_exc=True, publication_exc=True, tmp_path=tmp_path)
    RUN.Phase3BRunner.run(r)  # must not raise


def test_publication_success_marks_published_and_leaves_the_verdict_alone(tmp_path):
    r = _runner_with(primary_exc=True, publication_exc=False, tmp_path=tmp_path)
    r._publish_run = lambda outcome: {"publication_sha256": "abc"}
    outcome = RUN.Phase3BRunner.run(r)
    assert outcome.published is True
    assert outcome.publication_error is None
    assert PRIMARY in (outcome.error or ""), "publication altered the computation verdict"
    assert outcome.disposition == outcome.primary_disposition


def test_the_outcome_carries_both_failures_for_the_evidence_record(tmp_path):
    r = _runner_with(primary_exc=True, publication_exc=True, tmp_path=tmp_path)
    outcome = RUN.Phase3BRunner.run(r)
    evidence = json.dumps(
        {
            "disposition": outcome.disposition,
            "primary_error": outcome.primary_error,
            "publication_error": outcome.publication_error,
            "published": outcome.published,
        }
    )
    assert PRIMARY in evidence and SECONDARY in evidence, (
        "terminal evidence must contain BOTH failures"
    )


# -- full-path qualification: computation THROUGH publication ------------------------------

from tests.research.phase3b import fixtures_producer as F  # noqa: E402
from tests.research.phase3b import test_phase3b_entrypoint_qualification as EQ  # noqa: E402


def test_the_fixture_world_spans_a_realistic_session_count():
    """Attempt #1 died before producing anything, so the path was never exercised at scale."""
    assert len(F.SESSIONS) >= 300, f"only {len(F.SESSIONS)} sessions"


def test_full_path_reaches_publication_and_writes_every_deliverable(tmp_path):
    """The end-to-end gap: qualification previously stopped at PRE_ACCESS_READY.

    This drives the complete path on non-sealed fixture data through ACTUAL publication.
    """
    runner = EQ._runner(tmp_path)
    outcome = runner.run()

    assert outcome.disposition == P.PASS, outcome.error
    assert outcome.published is True, outcome.publication_error
    assert outcome.publication_error is None
    assert outcome.state == S.S11_PUBLISHED
    assert outcome.primary_disposition == P.PASS

    root = runner.output_root
    for name in (*P.DELIVERABLES, P.REPORT, P.PUBLICATION):
        path = os.path.join(root, name)
        assert os.path.isfile(path), f"missing artifact: {name}"
        assert os.path.getsize(path) > 0, f"empty artifact: {name}"


def test_every_published_deliverable_reproduces_its_recorded_identity(tmp_path):
    """Existence is not enough: each deliverable must hash to what publication recorded."""
    import hashlib

    runner = EQ._runner(tmp_path)
    outcome = runner.run()
    assert outcome.published is True, outcome.publication_error

    recorded = outcome.publication["deliverable_sha256"]
    assert set(recorded) == set(P.DELIVERABLES), "the deliverable set is incomplete"
    for name, sha in recorded.items():
        with open(os.path.join(runner.output_root, name), "rb") as fh:
            assert hashlib.sha256(fh.read()).hexdigest() == sha, f"{name} does not reproduce"

    with open(os.path.join(runner.output_root, P.PUBLICATION), encoding="utf-8") as fh:
        pub = json.load(fh)
    assert pub["partial_run"] is False
    assert pub["deliverable_sha256"] == recorded


def test_the_published_report_is_reproducible_from_its_own_bytes(tmp_path):
    import hashlib

    runner = EQ._runner(tmp_path)
    outcome = runner.run()
    with open(os.path.join(runner.output_root, P.REPORT), "rb") as fh:
        assert hashlib.sha256(fh.read()).hexdigest() == outcome.publication["report_sha256"]


def test_the_full_path_run_is_not_vacuous(tmp_path):
    """A publication over zero records would satisfy every check above and prove nothing."""
    runner = EQ._runner(tmp_path)
    outcome = runner.run()
    assert outcome.integrity["records_examined"] > 0
    assert outcome.integrity["all_gates_zero"] is True
    assert outcome.enrichment_census["records_examined"] > 0
