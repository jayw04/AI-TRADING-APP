"""The Phase C runner's TWO-STAGE separation.

The first Phase C attempt failed on the deployed runtime because the runner carried an expected census
hand-copied from a diagnostic whose relevance set differed from the readiness path's. Removing the
constant is necessary but not sufficient: a runner that derives an attestation and then validates it
against the same in-memory assessment agrees with itself by construction — the same defect, restated.

So the tests here are about the SEPARATION, not about arithmetic:

  * stage 1 returns a path, stage 2 takes a path — the signatures make an in-memory handoff impossible;
  * the serialized artifact is genuinely reloaded (mutate the file, the run refuses);
  * every cross-stage binding is re-derived by stage 2 and refused on divergence;
  * no expected-count constant survives anywhere in the attestation path.
"""

from __future__ import annotations

import inspect
import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

from app.factor_data.store import FactorDataStore
from app.validation.data_finality import ConstructionSpec, DataReadiness
from scripts.forward_validation import phase_c_readiness as pc
from tests.validation.governed_construction_fixture import (
    governed_movement_examples,
    layer2_quarantine_policy,
)

SESSION = date(2026, 7, 24)
N_SESSIONS = 300
N_TICKERS = 60
SPEC = ConstructionSpec(scoring_universe_n=20, proxy_universe_n=30)

CORPUS_SHA = "1e" * 32
RECON_SHA = "a" * 64
RELEVANCE_SHA = "b" * 64

#: ⚠ THE REAL, COUNTERSIGNED QUARANTINE, derived by the ONE derivation from the committed manifest.
#: The runner no longer carries `QUARANTINED_IDENTITIES` and this file no longer carries its own copy:
#: two literals agreeing proves nothing about either.
QUARANTINE_POLICY = layer2_quarantine_policy()
QUARANTINE_SHA = QUARANTINE_POLICY.quarantine_evidence_sha256
QUARANTINED = QUARANTINE_POLICY.permanent_identities
GOVERNED_MOVEMENTS = governed_movement_examples(QUARANTINE_POLICY)
DISCLOSURE_REASON = "ACQUIRED_SIDE_ECONOMICALLY_TERMINAL_AND_MEASURED_NON_DECISION_RELEVANT"


def _sessions(n: int, end: date) -> list[date]:
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= pd.Timedelta(days=1).to_pytimedelta()
    return sorted(out)


@pytest.fixture
def store(tmp_path):
    st = FactorDataStore(db_path=str(tmp_path / "phasec.duckdb"))
    days = _sessions(N_SESSIONS, SESSION)
    tickers = [f"T{i:04d}" for i in range(N_TICKERS)]
    st.ingest_sep(pd.DataFrame([
        {"ticker": t, "date": d, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0,
         "volume": 1_000_000 + i, "closeadj": 100.0, "closeunadj": 100.0, "lastupdated": d}
        for d in days for i, t in enumerate(tickers)]))
    st.ingest_tickers(pd.DataFrame([
        {"ticker": t, "permaticker": str(500000 + i), "name": f"{t} CORP", "exchange": "NYSE",
         "category": "Domestic Common Stock", "sector": "Technology", "industry": "Software",
         "isdelisted": False, "firstpricedate": days[0], "lastpricedate": SESSION,
         "lastupdated": SESSION}
        for i, t in enumerate(tickers)]))
    st.record_ingest_run("sep", datetime(2026, 7, 24, 22, 0), datetime(2026, 7, 24, 22, 5),
                         N_SESSIONS * N_TICKERS, "ok")
    st.record_ingest_run("actions", datetime(2026, 7, 24, 21, 5), datetime(2026, 7, 24, 21, 6),
                         0, "ok")
    yield st
    st.close()


class _SetSensitiveAdjustment:
    """A verifier whose census AND relevance digest depend on the identities it was handed — which is
    what makes 'derived over a different set' observable at all. Never proven, 4 unexplained movements
    on the two quarantined identities, payload bounded at the production cap."""

    def __init__(self, store_identity: str, tickers: list[str]):
        self.proven = False
        self._id = store_identity
        self._names = sorted(set(tickers))
        self._total = len(self._names)
        self._serialized = min(self._total, 200)

    def to_open_provenance(self) -> dict:
        return {
            "verdict": "NOT_PROVEN_UNSUPPORTED_ACTION", "proven": False,
            "detail": "the broad reflection proof does not hold",
            "store_identity_sha256": self._id,
            "relevance_set_sha256": "%064x" % (self._total * 7919),
            "relevant_ticker_count": self._total,
            "checks_by_status": {"PROVEN_REFLECTED": self._total},
            "checks_by_reason_code": {DISCLOSURE_REASON: 0},
            "ma_disclosure_sha256": RELEVANCE_SHA,
            "ma_disclosure_entry_count": 18,
            "checks": [{"i": i} for i in range(self._serialized)],
            "action_evidence": {
                "total_action_count": self._total,
                "included_action_count": self._serialized,
                "omitted_action_count": self._total - self._serialized,
                "truncated": self._total > self._serialized,
                "max_actions": 200,
            },
            "unexplained_adjustment_count": len(GOVERNED_MOVEMENTS),
            "unexplained_examples": list(GOVERNED_MOVEMENTS),
        }


def _verifier(window_start, session_date, tickers, store_identity):
    return _SetSensitiveAdjustment(store_identity, tickers)


def _derive(store, out: Path, *, corpus=CORPUS_SHA) -> Path:
    return pc.derive_attestation(
        store, SESSION, out_path=out, construction=SPEC, adjustment_verifier=_verifier,
        corpus_manifest_sha256=corpus, reconciliation_artifact_sha256=RECON_SHA,
        relevance_artifact_sha256=RELEVANCE_SHA, quarantine=QUARANTINE_POLICY)


def _validate(store, path: Path, *, corpus=CORPUS_SHA, prediction=None,
              quarantine=QUARANTINE_POLICY):
    return pc.validate_attestation(
        store, SESSION, attestation_path=path, construction=SPEC, adjustment_verifier=_verifier,
        corpus_manifest_sha256=corpus, quarantine=quarantine, prediction=prediction)


def _mutate(path: Path, **changes) -> Path:
    record = json.loads(path.read_bytes())
    record.update(changes)
    path.write_bytes(json.dumps(record, sort_keys=True, separators=(",", ":")).encode())
    return path


# ---- the separation itself ---------------------------------------------------------------------------

def test_stage_1_returns_only_a_path_and_stage_2_accepts_only_a_path():
    """★ THE STRUCTURAL GUARD. An in-memory handoff must be impossible, not merely discouraged."""
    assert inspect.signature(pc.derive_attestation).return_annotation == "Path"
    params = inspect.signature(pc.validate_attestation).parameters
    assert "attestation_path" in params
    assert "attestation" not in params, (
        "stage 2 must never accept an attestation OBJECT — only the path to a serialized one")


def test_the_two_stages_communicate_only_through_the_serialized_file(store, tmp_path):
    out = _derive(store, tmp_path / "att.json")
    assert out.exists() and out.stat().st_size > 0
    result = _validate(store, out)
    assert result.refusals == ()
    assert result.verdict == str(
        DataReadiness.READY_DECISION_VALID_WITH_DISCLOSED_NONDECISION_LIMITATIONS)
    assert result.passed is True


def test_the_serialized_attestation_is_actually_RELOADED_not_reused(store, tmp_path):
    """★ Mutate the file on disk between the stages. If stage 2 were reusing a stage-1 object the
    mutation would be invisible and the run would wrongly pass."""
    out = _derive(store, tmp_path / "att.json")
    _mutate(out, session_date="2026-07-23")
    with pytest.raises(pc.PhaseCRefusal, match="names 2026-07-23"):
        _validate(store, out)


def test_deleting_the_artifact_between_stages_is_fatal(store, tmp_path):
    """The corollary: with nothing on disk there is nothing to validate."""
    out = _derive(store, tmp_path / "att.json")
    out.unlink()
    with pytest.raises(pc.PhaseCRefusal, match="no narrow-readiness attestation"):
        _validate(store, out)


# ---- every cross-stage binding is re-derived and refused on divergence -------------------------------

def test_a_changed_persisted_COUNT_causes_refusal(store, tmp_path):
    out = _derive(store, tmp_path / "att.json")
    record = json.loads(out.read_bytes())
    counts = dict(record["expected_status_counts"])
    counts["PROVEN_REFLECTED"] = int(counts["PROVEN_REFLECTED"]) + 1
    _mutate(out, expected_status_counts=counts)
    with pytest.raises(pc.PhaseCRefusal, match="does not match this run's measurement"):
        _validate(store, out)


def test_a_changed_RELEVANCE_SET_digest_causes_refusal(store, tmp_path):
    """★ The 2026-07-27 failure mode: a census measured over a different set of securities."""
    out = _derive(store, tmp_path / "att.json")
    _mutate(out, relevance_set_sha256="d1" * 32)
    with pytest.raises(pc.PhaseCRefusal, match="produced over relevance set"):
        _validate(store, out)


def test_a_changed_CORPUS_identity_causes_refusal(store, tmp_path):
    out = _derive(store, tmp_path / "att.json")
    with pytest.raises(pc.PhaseCRefusal, match="produced against corpus"):
        _validate(store, out, corpus="ff" * 32)


def test_a_changed_STORE_identity_causes_refusal(store, tmp_path):
    out = _derive(store, tmp_path / "att.json")
    _mutate(out, store_identity_sha256="ab" * 32)
    with pytest.raises(pc.PhaseCRefusal, match="produced against store"):
        _validate(store, out)


@pytest.mark.parametrize("field", ["session_date", "relevance_set_sha256", "expected_status_counts",
                                   "corpus_manifest_sha256", "store_identity_sha256"])
def test_an_attestation_missing_any_required_binding_is_refused(store, tmp_path, field):
    out = _derive(store, tmp_path / "att.json")
    _mutate(out, **{field: None})
    with pytest.raises(pc.PhaseCRefusal, match=f"carries no {field}"):
        _validate(store, out)


def test_a_foreign_or_unversioned_artifact_is_refused(store, tmp_path):
    out = _derive(store, tmp_path / "att.json")
    _mutate(out, kind="something_else")
    with pytest.raises(pc.PhaseCRefusal, match="not a narrow-readiness attestation"):
        _validate(store, out)
    _mutate(out, kind=pc.ATTESTATION_KIND, schema_version="v99")
    with pytest.raises(pc.PhaseCRefusal, match="unsupported attestation schema"):
        _validate(store, out)


# ---- no hard-coded expected counts survive in the attestation path -----------------------------------

def _referenced_names(fn) -> set[str]:
    """Every identifier the function's CODE reads. AST rather than a text scan, so a comment that
    merely names something is not mistaken for the code using it."""
    import ast
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}


def test_no_hard_coded_expected_counts_remain_in_the_runner():
    """⛔ The defect being removed. The runner must not carry a census that could be fed to an
    attestation — every count it uses must come from a measurement or from the file on disk."""
    assert "EXPECTED_COUNTS" not in inspect.getsource(pc), (
        "the hard-coded diagnostic census must be gone")
    for stage in (pc.derive_attestation, pc.validate_attestation, pc.load_attestation):
        assert "GOVERNED_PREDICTION" not in _referenced_names(stage), (
            f"{stage.__name__} must not read the prediction — it is checked afterwards, never used")


def test_stage_2_has_no_default_prediction_to_fall_back_on():
    """★ A default would put the predicted census inside stage 2's own frame, one edit from becoming a
    fallback. The caller supplies it or nothing does."""
    default = inspect.signature(pc.validate_attestation).parameters["prediction"].default
    assert default is inspect.Parameter.empty


def test_the_prediction_is_never_an_input_to_the_attestation():
    """★ `GOVERNED_PREDICTION.census` is an acceptance criterion, not a fallback. It must reach only
    the post-hoc comparison, never `NarrowReadinessAttestation`."""
    consumers = inspect.getsource(pc._check_prediction)
    assert "NarrowReadinessAttestation" not in consumers
    assert "NarrowReadinessAttestation" not in inspect.getsource(pc.validate_attestation), (
        "stage 2 constructs no attestation of its own; it reloads one")
    built = inspect.getsource(pc.derive_attestation)
    assert "census" not in built and "expected_status_counts=" not in built, (
        "stage 1 must derive the census, never supply one")


def test_the_runner_derives_the_attestation_through_the_governed_builder():
    assert "build_narrow_readiness_attestation" in inspect.getsource(pc.derive_attestation)


# ---- the governed prediction -------------------------------------------------------------------------

def test_the_recorded_prediction_is_the_owner_accepted_july_27_outcome():
    """Pinned so a future edit cannot quietly move the target the run is judged against."""
    p = pc.GOVERNED_PREDICTION
    assert p.verdict == "READY_DECISION_VALID_WITH_DISCLOSED_NONDECISION_LIMITATIONS"
    assert (p.ready, p.fully_proven, p.has_disclosed_limitations) == (True, False, True)
    assert (p.full_action_semantics_proven, p.decision_validity_proven) == (False, True)
    assert p.nondecision_limitations_present is False
    assert (p.corpus_wide_unsupported_semantics, p.present_in_readiness_relevance_set) == (18, 0)
    assert p.quarantined_unexplained_movements == 4
    assert p.census == {"PROVEN_REFLECTED": 1670,
                        "PROVEN_NO_PRICE_ADJUSTMENT_APPLICABLE": 91,
                        "PROVEN_LINEAGE_EVENT_NO_ADDITIONAL_PRICE_ADJUSTMENT": 3}
    assert sum(p.census.values()) == 1764


def test_a_fresh_assessment_producing_the_PREDICTED_july_27_census_passes(store, tmp_path):
    """★ The end-to-end shape of the authorized run: an assessment whose measurement equals the
    prediction recorded in advance passes with no divergence."""
    counts = dict(pc.GOVERNED_PREDICTION.census)
    total = sum(counts.values())

    class _July27(_SetSensitiveAdjustment):
        def to_open_provenance(self):
            d = super().to_open_provenance()
            d["checks_by_status"] = dict(counts)
            d["action_evidence"] = {"total_action_count": total, "included_action_count": 200,
                                    "omitted_action_count": total - 200, "truncated": True,
                                    "max_actions": 200}
            d["checks"] = [{"i": i} for i in range(200)]
            return d

    def july27(window_start, session_date, tickers, store_identity):
        return _July27(store_identity, tickers)

    out = pc.derive_attestation(
        store, SESSION, out_path=tmp_path / "att.json", construction=SPEC,
        adjustment_verifier=july27, corpus_manifest_sha256=CORPUS_SHA,
        reconciliation_artifact_sha256=RECON_SHA, relevance_artifact_sha256=RELEVANCE_SHA,
        quarantine=QUARANTINE_POLICY)
    assert json.loads(out.read_bytes())["expected_status_counts"] == counts

    result = pc.validate_attestation(
        store, SESSION, attestation_path=out, construction=SPEC, adjustment_verifier=july27,
        corpus_manifest_sha256=CORPUS_SHA, quarantine=QUARANTINE_POLICY,
        prediction=pc.GOVERNED_PREDICTION)
    assert result.prediction_failures == ()
    assert result.passed is True
    assert result.verdict == pc.GOVERNED_PREDICTION.verdict


def test_a_census_that_diverges_from_the_prediction_is_reported_as_a_stop(store, tmp_path):
    """A drift that every clause would accept — internally consistent, and not what was predicted."""
    out = _derive(store, tmp_path / "att.json")
    result = _validate(store, out, prediction=pc.GOVERNED_PREDICTION)
    assert result.passed is False
    assert any("status census" in f for f in result.prediction_failures)
    assert result.refusals == (), "the contract itself is satisfied; only the prediction diverges"
