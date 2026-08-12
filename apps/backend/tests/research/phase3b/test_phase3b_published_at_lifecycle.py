"""`published_at` is publication metadata, not a research configuration parameter.

The frozen contract could not have known it prospectively, so it cannot be an input to the run.
Two identities are kept apart:

  PRE-EXECUTION / RUN IDENTITY   deterministic from frozen contracts, observed runtime identities,
                                 the configuration mapping and the code/runtime bindings. This is
                                 what authorizes the run, and it must not move when a clock moves.
  PUBLISHED ARTIFACT IDENTITY    may include published_at, so its file hash legitimately differs
                                 between two publications of an identical run.

The falsification: change ONLY published_at and require every research, configuration and
execution-input identity to stay byte-identical, with only the serialized publication artifact
allowed to differ.
"""

from __future__ import annotations

import inspect
import json
import os

import pytest

from app.research.mr002.phase3b import entrypoint as EP
from app.research.mr002.phase3b import publish as P
from app.research.mr002.phase3b import runner as RUN

IDENTITIES = {
    "code_identity": "roster",
    "runtime_identity": "python-3.13.14",
    "governing_identity": "runspec-2a1fb775",
}
REPORT = {
    "run_id": "MR002-SPQ1-P3B-VALIDATION-V1",
    "window": "validation",
    "config_mapping": {"A": 1.75, "B": 2.00, "C": 2.25},
    "contract_identities": {"ExecutionEnrichmentSchema": "5b2480c1"},
    "observed_identities": {"prices": "sha-prices", "universe": "sha-universe"},
}
DELIVERABLES = dict.fromkeys(P.DELIVERABLES, "0" * 64)


def _publish(root: str, stamp: str) -> dict:
    os.makedirs(root, exist_ok=True)
    return P.publish_run(
        root,
        report=dict(REPORT),
        disposition=P.PASS,
        exit_code=0,
        identities=dict(IDENTITIES),
        deliverable_hashes=dict(DELIVERABLES),
        clock=lambda: stamp,
    )


# -- the lifecycle boundary ---------------------------------------------------------------


def test_build_runner_takes_no_published_at():
    """The old signature encoded the wrong lifecycle. It must not survive for continuity."""
    assert "published_at" not in inspect.signature(EP.build_runner).parameters


def test_the_runner_holds_no_published_at_field():
    assert "published_at" not in RUN.Phase3BRunner.__dataclass_fields__


def test_publish_run_stamps_it_rather_than_receiving_it():
    params = inspect.signature(P.publish_run).parameters
    assert "published_at" not in params
    assert "clock" in params


def test_a_run_reaching_pre_access_ready_has_no_published_at_in_existence():
    """Nothing before publication may READ such a value, because it does not exist yet.

    Checked as an attribute reference rather than a text search: the runner may legitimately
    mention the name in a comment explaining why it is absent.
    """
    src = inspect.getsource(RUN.Phase3BRunner)
    assert "self.published_at" not in src
    assert "published_at" not in RUN.Phase3BRunner.__dataclass_fields__


# -- the falsification --------------------------------------------------------------------

PRE_PUBLICATION_IDENTITY_KEYS = (
    "run_id",
    "window",
    "config_mapping",
    "contract_identities",
    "observed_identities",
)


def test_changing_only_published_at_moves_no_pre_publication_identity(tmp_path):
    """THE falsification: two publications of an identical run, different stamps only."""
    a = _publish(str(tmp_path / "a"), "2026-08-12T00:00:00Z")
    b = _publish(str(tmp_path / "b"), "2099-01-01T23:59:59Z")

    assert a["published_at"] != b["published_at"], "the test is vacuous unless the stamps differ"

    # research / configuration / execution-input identities: byte-identical
    ra = json.loads((tmp_path / "a" / P.REPORT).read_text())
    rb = json.loads((tmp_path / "b" / P.REPORT).read_text())
    for key in PRE_PUBLICATION_IDENTITY_KEYS:
        assert ra[key] == rb[key], key
    assert a["identities"] == b["identities"]
    assert a["deliverable_sha256"] == b["deliverable_sha256"]

    # the REPORT itself is unaffected by the stamp
    assert a["report_sha256"] == b["report_sha256"], (
        "the report carries research content; a clock must not move it"
    )
    # only the serialized publication artifact may differ
    assert a["publication_sha256"] != b["publication_sha256"]


def test_published_at_is_absent_from_the_report_body(tmp_path):
    _publish(str(tmp_path / "r"), "2026-08-12T00:00:00Z")
    body = json.loads((tmp_path / "r" / P.REPORT).read_text())
    assert "published_at" not in json.dumps(body)


# -- retry semantics ----------------------------------------------------------------------


def test_a_retry_after_durable_publication_refuses_rather_than_restamping(tmp_path):
    """One publication event gets one timestamp. A second stamp would forge a second event."""
    root = str(tmp_path / "once")
    first = _publish(root, "2026-08-12T00:00:00Z")
    with pytest.raises(P.PublicationRefused, match="already_durably_published"):
        _publish(root, "2026-08-12T00:00:01Z")
    # the published artifact is intact and still carries the ORIGINAL stamp
    record = json.loads((tmp_path / "once" / P.PUBLICATION).read_text())
    assert record["published_at"] == "2026-08-12T00:00:00Z"
    assert first["published_at"] == record["published_at"]


def test_the_publication_record_still_declares_retry_prohibited(tmp_path):
    rec = _publish(str(tmp_path / "d"), "2026-08-12T00:00:00Z")
    assert rec["retry_after_publication"] == "PROHIBITED"


def test_the_default_clock_produces_a_utc_instant():
    stamp = P._utc_now()
    assert stamp.endswith("Z") and len(stamp) == 20 and stamp[4] == "-"
