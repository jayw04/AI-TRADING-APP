"""The first-session expected-outcome pin (Amendment 6).

The commit boundary lives INSIDE the runner, downstream of its own evaluation, and the record is
append-only — so a divergence between the reviewed pre-commit outcome and the outcome the committing
run produces could otherwise only be DETECTED after the irreversible write. The pin makes the refusal
happen BEFORE it: the runner evaluates exactly as it always has, and immediately before
`open_first_window_session` the newly produced outcome must equal the approved pre-commit evidence.

What is pinned here:

  * both digests match → the commit proceeds, and an immutable receipt records expected == actual;
  * either digest mismatches → INTEGRITY_STOP with NOTHING committed — no observations/, no
    sequence, no commit.json, no durable ledger;
  * a missing or malformed expectation refuses at CONSTRUCTION — pinned execution never silently
    degrades into an unpinned run;
  * the pin is scoped to ONE first-session commit for ONE session date — a stale pin refuses;
  * Account 4 moving during the run still stops (the existing gate), pin match notwithstanding;
  * unpinned behaviour is byte-for-byte the ordinary runner path;
  * expectations come from the governed configuration ONLY — no environment fallback;
  * the comparison happens BEFORE `open_first_window_session`, structurally.
"""

from __future__ import annotations

import inspect
import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from app.validation.forward_session_runner import (
    OUTCOME_PIN_RECEIPT_FILENAME,
    FirstSessionOutcomePin,
    ForwardSessionRunner,
    SessionRunStatus,
)
from app.validation.forward_window import IntegrityStop
from tests.validation.test_forward_session_runner import (
    SESSION_1,
    _decision,
    _runner,
)

# The runner suite's fixtures, re-exported under names ruff does not see shadowed by test
# parameters. `context_builder` depends on `artifacts`, so both must be registered.
from tests.validation.test_forward_session_runner import (  # noqa: F401  (pytest fixture registry)
    artifacts as artifacts,
)
from tests.validation.test_forward_session_runner import (
    context_builder as context_builder,
)

EVIDENCE_DIGEST = "e" * 64
PACKAGE_SHA = "22b14ff31d207574433fee249904be960dcc03cae23d298868f1f6d2189b40b8"


class _BoundEvidence:
    """The provider-call evidence a binding provider exposes, reduced to its contract."""

    def __init__(self, digest: str) -> None:
        self._digest = digest

    def to_open_provenance(self) -> dict:
        return {"calls": "stub"}

    def digest(self) -> str:
        return self._digest


class _BindingProvider:
    """A decision provider WITH bound evidence — what pinned execution requires."""

    def __init__(self, digest: str = EVIDENCE_DIGEST) -> None:
        self.bound_evidence = _BoundEvidence(digest)
        self._digest = digest

    def __call__(self, d: date):
        return replace(_decision(d), input_evidence_digest=self._digest)


def _pin(*, session: date = SESSION_1, sealed: str = "0" * 64,
         evidence: str = EVIDENCE_DIGEST, package: str = PACKAGE_SHA) -> FirstSessionOutcomePin:
    return FirstSessionOutcomePin(session_date=session, sealed_performance_sha256=sealed,
                                  input_evidence_digest=evidence,
                                  precommit_package_sha256=package)


def _pinned_runner(tmp_path, context_builder, pin, *, provider=None) -> ForwardSessionRunner:
    base = _runner(tmp_path, context_builder, provider=provider or _BindingProvider())
    return replace(base, outcome_pin=pin)


def _reference_sealed_sha(tmp_path, context_builder) -> str:
    """The sealed digest of the reviewed outcome — learned from a committed UNPINNED run of the same
    deterministic decision in a scratch directory, exactly as run 3's package recorded it. Never
    hand-computed here: the test must not carry its own idea of the sealing serialization."""
    scratch = tmp_path / "reference"
    scratch.mkdir()
    r = _runner(scratch, context_builder, provider=_BindingProvider())
    res = r.run_session(SESSION_1, run_timestamp="2026-07-24T20:10:00Z")
    assert res.status is SessionRunStatus.RECORDED
    payload = json.loads(
        (r.store_dir / "observations" / "000001" / "open.json").read_text(encoding="utf-8"))
    return payload["sealed_performance_sha256"]


def _receipts(store: Path) -> list[dict]:
    p = store / OUTCOME_PIN_RECEIPT_FILENAME
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _nothing_committed(r: ForwardSessionRunner) -> None:
    assert not (r.store_dir / "observations").exists(), "an observation directory was created"
    assert not r.ledger_path.exists(), "the durable ledger was written"


# ---- both digests match → the commit proceeds -----------------------------------------------------

def test_a_matching_pin_commits_and_the_receipt_shows_expected_equals_actual(tmp_path,
                                                                             context_builder):
    sealed = _reference_sealed_sha(tmp_path, context_builder)
    r = _pinned_runner(tmp_path / "pinned", context_builder, _pin(sealed=sealed))
    res = r.run_session(SESSION_1, run_timestamp="2026-07-24T20:10:00Z")
    assert res.status is SessionRunStatus.RECORDED and res.sequence == 1

    receipts = _receipts(r.store_dir)
    assert len(receipts) == 1
    rec = receipts[0]
    assert rec["matched"] is True
    assert rec["expected_sealed_performance_sha256"] == rec["actual_sealed_performance_sha256"] \
        == sealed
    assert rec["expected_input_evidence_digest"] == rec["actual_input_evidence_digest"] \
        == EVIDENCE_DIGEST
    assert rec["precommit_package_sha256"] == PACKAGE_SHA

    committed = json.loads(
        (r.store_dir / "observations" / "000001" / "open.json").read_text(encoding="utf-8"))
    assert committed["sealed_performance_sha256"] == sealed, (
        "the committed observation must BE the reviewed outcome, not merely accompany the receipt")


# ---- either digest mismatches → nothing written ---------------------------------------------------

def test_a_sealed_performance_mismatch_stops_with_nothing_committed(tmp_path, context_builder):
    r = _pinned_runner(tmp_path, context_builder, _pin(sealed="a" * 64))
    res = r.run_session(SESSION_1, run_timestamp="2026-07-24T20:10:00Z")
    assert res.status is SessionRunStatus.INTEGRITY_STOP
    assert res.exception_code == "OUTCOME_PIN_MISMATCH"
    _nothing_committed(r)
    rec = _receipts(r.store_dir)
    assert len(rec) == 1 and rec[0]["matched"] is False
    assert rec[0]["expected_sealed_performance_sha256"] == "a" * 64
    assert rec[0]["actual_sealed_performance_sha256"] != "a" * 64


def test_an_input_evidence_mismatch_stops_with_nothing_committed(tmp_path, context_builder):
    sealed = _reference_sealed_sha(tmp_path, context_builder)
    r = _pinned_runner(tmp_path / "pinned", context_builder,
                       _pin(sealed=sealed, evidence="f" * 64))
    res = r.run_session(SESSION_1, run_timestamp="2026-07-24T20:10:00Z")
    assert res.status is SessionRunStatus.INTEGRITY_STOP
    assert res.exception_code == "OUTCOME_PIN_MISMATCH"
    _nothing_committed(r)
    assert _receipts(r.store_dir)[0]["matched"] is False


def test_a_pinned_run_without_an_evidence_binding_provider_refuses(tmp_path, context_builder):
    """A bare callable provider produces no input-evidence digest; pinned execution cannot identify
    the reviewed outcome without one, and must not fall back to comparing half of it."""
    base = _runner(tmp_path, context_builder)                     # the plain lambda provider
    r = replace(base, outcome_pin=_pin())
    res = r.run_session(SESSION_1, run_timestamp="2026-07-24T20:10:00Z")
    assert res.status is SessionRunStatus.INTEGRITY_STOP
    assert res.exception_code == "OUTCOME_PIN_EVIDENCE_UNAVAILABLE"
    _nothing_committed(r)


# ---- a missing expectation refuses at construction ------------------------------------------------

@pytest.mark.parametrize("field", ["sealed_performance_sha256", "input_evidence_digest",
                                   "precommit_package_sha256"])
def test_a_missing_or_malformed_digest_refuses_at_construction(field):
    kwargs = {"session_date": SESSION_1, "sealed_performance_sha256": "0" * 64,
              "input_evidence_digest": EVIDENCE_DIGEST, "precommit_package_sha256": PACKAGE_SHA}
    for bad in ("", "not-a-digest", "0" * 63):
        with pytest.raises(IntegrityStop, match=f"no usable {field}"):
            FirstSessionOutcomePin(**{**kwargs, field: bad})


def test_from_payload_requires_a_session_date():
    with pytest.raises(IntegrityStop, match="session_date"):
        FirstSessionOutcomePin.from_payload({"sealed_performance_sha256": "0" * 64,
                                             "input_evidence_digest": EVIDENCE_DIGEST,
                                             "precommit_package_sha256": PACKAGE_SHA})


# ---- scope: one first-session commit, one session date --------------------------------------------

def test_a_pin_for_a_different_session_refuses_before_any_data_work(tmp_path, context_builder):
    r = _pinned_runner(tmp_path, context_builder, _pin(session=date(2026, 7, 27)))
    res = r.run_session(SESSION_1, run_timestamp="2026-07-24T20:10:00Z")
    assert res.status is SessionRunStatus.INTEGRITY_STOP
    assert res.exception_code == "OUTCOME_PIN_SESSION_MISMATCH"
    _nothing_committed(r)
    assert _receipts(r.store_dir) == [], "no comparison ran, so no receipt may claim one did"


def test_a_stale_pin_refuses_once_the_first_observation_exists(tmp_path, context_builder):
    sealed = _reference_sealed_sha(tmp_path, context_builder)
    r = _pinned_runner(tmp_path / "pinned", context_builder, _pin(sealed=sealed))
    assert r.run_session(SESSION_1, run_timestamp="2026-07-24T20:10:00Z").status \
        is SessionRunStatus.RECORDED
    res = r.run_session(date(2026, 7, 27), run_timestamp="2026-07-27T20:10:00Z")
    assert res.status is SessionRunStatus.INTEGRITY_STOP
    assert res.exception_code == "OUTCOME_PIN_ALREADY_COMMITTED"
    assert res.detail.endswith("its approval was consumed")


# ---- Account 4 moving still stops, pin match notwithstanding --------------------------------------

class _ShiftingProbe:
    """An authoritative probe whose second read describes a DIFFERENT live state."""

    class _State:
        def __init__(self, digest: str) -> None:
            self.comparison_digest = digest
            self.account_id = 4

        def __getattr__(self, name):                              # COMPARED_FIELDS diagnostics
            return self.comparison_digest

    def __init__(self) -> None:
        self._reads = 0

    def __call__(self):
        self._reads += 1
        return self._State("1" * 64 if self._reads == 1 else "2" * 64)


def test_account4_changing_during_the_session_stops_even_with_a_matching_pin(tmp_path,
                                                                             context_builder):
    sealed = _reference_sealed_sha(tmp_path, context_builder)
    base = _pinned_runner(tmp_path / "pinned", context_builder, _pin(sealed=sealed))
    r = replace(base, authoritative_account4_probe=_ShiftingProbe())
    res = r.run_session(SESSION_1, run_timestamp="2026-07-24T20:10:00Z")
    assert res.status is SessionRunStatus.INTEGRITY_STOP
    assert res.exception_code == "ACCOUNT4_STATE_CHANGED_DURING_SESSION"
    _nothing_committed(r)
    assert _receipts(r.store_dir) == [], (
        "Account 4 is checked BEFORE the pin comparison; a run stopped there never reached it")


# ---- unpinned behaviour is unchanged --------------------------------------------------------------

def test_an_unpinned_run_behaves_exactly_as_before(tmp_path, context_builder):
    r = _runner(tmp_path, context_builder)
    assert r.outcome_pin is None
    res = r.run_session(SESSION_1, run_timestamp="2026-07-24T20:10:00Z")
    assert res.status is SessionRunStatus.RECORDED
    assert not (r.store_dir / OUTCOME_PIN_RECEIPT_FILENAME).exists(), (
        "an unpinned run writes no pin receipt — the file's existence means pinning happened")


# ---- no ungoverned source, and the check precedes the commit --------------------------------------

def test_expectations_cannot_arrive_through_an_environment_fallback():
    """The configuration file is the only source. `os.environ` in any of the pin's construction or
    verification paths would be a second, ungoverned channel for the expected values."""
    import ast
    import textwrap

    from app.validation import forward_deployment_config as fdc

    for fn in (FirstSessionOutcomePin.from_payload, fdc._parse_outcome_pin,
               ForwardSessionRunner._verify_outcome_pin, ForwardSessionRunner.run_session):
        # AST, not a text scan: the docstrings legitimately NAME the prohibition; what must not
        # exist is CODE that reads it.
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
        names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} \
            | {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert "environ" not in names and "getenv" not in names, (
            f"{fn.__qualname__} must not read the environment")


def test_the_pin_comparison_happens_before_open_first_window_session():
    """Structural: in `run_session`'s source, the pin verification precedes the committing call —
    the property every nothing-was-written assertion above depends on."""
    src = inspect.getsource(ForwardSessionRunner.run_session)
    assert src.index("_verify_outcome_pin") < src.index("open_first_window_session(")


# ---- the governed configuration parses the pin fail-closed ----------------------------------------

def test_the_config_parses_a_declared_pin_and_refuses_a_malformed_one():
    from app.validation.forward_deployment_config import DeploymentConfigError, _parse_outcome_pin

    assert _parse_outcome_pin(None) is None, "no declared pin is ordinary unpinned operation"
    pin = _parse_outcome_pin({
        "session_date": "2026-07-27",
        "sealed_performance_sha256": "74598a101ec936f0ec285b91344295ba75fbb0af67af42d08f88d5bbb89288e9",
        "input_evidence_digest": "f9b01b14d0ee94fb63706373b40d93eea647e5f68ad917d73d82825058939c57",
        "precommit_package_sha256": PACKAGE_SHA})
    assert isinstance(pin, FirstSessionOutcomePin)
    assert pin.session_date == date(2026, 7, 27)
    with pytest.raises(DeploymentConfigError, match="refused rather than run unpinned"):
        _parse_outcome_pin({"session_date": "2026-07-27",
                            "sealed_performance_sha256": "short",
                            "input_evidence_digest": EVIDENCE_DIGEST,
                            "precommit_package_sha256": PACKAGE_SHA})
