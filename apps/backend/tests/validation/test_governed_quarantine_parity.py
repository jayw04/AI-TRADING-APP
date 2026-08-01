"""★ Phase C readiness and production session composition derive the SAME governed quarantine.

## Why this test could not have been written before 2026-07-31

`governed_quarantine` was a countersigned block in `corpus_manifest_v2.json` with NO consumer in
`app/validation`, while `scripts/forward_validation/phase_c_readiness.py` carried::

    QUARANTINED_IDENTITIES = frozenset({"167284", "642054"})

A parity test written against that arrangement would have compared a literal to a literal and passed
while proving nothing — the two sides agreed by coincidence, and nothing checked that they still did.

So this asserts more than "both sides say 2 identities and 4 movements". Counts are the weakest
possible claim: two different quarantines can agree on both. It asserts equality of the IDENTITIES —
corpus manifest, countersignature sidecar, quarantine policy, permanent identity set, movement-key
set, status census and limitation digest — and then mutates the manifest-derived policy and proves
that BOTH consumers refuse, consistently, for each of the ways it can be wrong.

## What the store is, and why it is shaped like this

A synthetic store, on the REAL XNYS calendar, whose 273-session window opens on 2025-06-25 — the same
window the deployed July 27 readiness run measures. SHOP and TLN carry the anomalous dividend-factor
ratios the countersigned quarantine evidence preserves, on the four sessions it names, under the
permanent identities the manifest declares. Everything else is flat and one declared dividend is
correctly reflected, so the census is real and the ONLY thing not proven is the governed quarantine.

The construction artifacts are the committed ones. A synthetic manifest would prove the derivation
parses fixtures; these prove it derives the deployed policy.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from app.factor_data.store import FactorDataStore
from app.validation import session_composition as sc
from app.validation.data_finality import (
    ConstructionSpec,
    DataReadiness,
    NarrowAttestationError,
    load_narrow_readiness_attestation,
)
from app.validation.eval_calendar import is_trading_session
from app.validation.governed_corpus import (
    load_any_corpus_manifest,
    load_layer2_countersignature,
    normalize_corpus_manifest,
)
from app.validation.governed_quarantine import (
    GovernedQuarantineError,
    governed_quarantine_policy,
)
from scripts.forward_validation import phase_c_readiness as pc
from tests.validation.governed_construction_fixture import LAYER2_ARTIFACTS, LAYER2_SESSION

SESSION = LAYER2_SESSION                                     # 2026-07-27
SPEC = ConstructionSpec(scoring_universe_n=20, proxy_universe_n=30)
COUNTERSIGNATURE = LAYER2_ARTIFACTS / "corpus_countersignature_v1.json"

#: The two quarantined lineages, as the countersigned manifest declares them.
SHOP, TLN = ("SHOP", "167284"), ("TLN", "642054")
#: The anomalous one-day dividend-factor ratios the quarantine evidence preserves verbatim.
ANOMALIES = {
    ("SHOP", date(2025, 6, 26)): 1.0018657695838413,
    ("SHOP", date(2025, 6, 27)): 0.996562665256478,
    ("TLN", date(2026, 2, 2)): 1.0221830985915492,
    ("TLN", date(2026, 2, 3)): 0.9782983120909405,
}

N_SESSIONS = 300
N_FILLER = 40
#: A declared, correctly reflected cash dividend, so the per-status census is non-empty and every
#: action in it is PROVEN. Without one, clause (2) refuses for want of a census to check.
DIVIDEND_TICKER = "DIVP"
DIVIDEND_DATE = date(2026, 3, 10)
DIVIDEND_CASH = 1.0

#: The governed vintage the committed manifest names, and which the store's provenance must name too
#: for `ManifestBoundAuthorityPolicy` to confer authority.
SOURCE_VINTAGE = "36d247f42210b4dc13873ba7c6e052f4dfaee7d059eacbff59eb2b0ea4ea7798"


def _sessions(n: int, end: date) -> list[date]:
    out, d = [], end
    while len(out) < n:
        if is_trading_session(d):
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


def _rows(days: list[date]) -> list[dict]:
    """Flat prices everywhere, with the quarantined anomalies and the declared dividend applied.

    `closeadj` is carried forward as a running product of the one-day factor ratios, which is what
    makes the anomaly appear as a movement in `closeadj/close` rather than as a price jump.
    """
    names = [(DIVIDEND_TICKER, "700000"), SHOP, TLN]
    names += [(f"T{i:04d}", str(500000 + i)) for i in range(N_FILLER)]
    rows: list[dict] = []
    for ticker, _perma in names:
        factor = 1.0
        for i, d in enumerate(days):
            factor *= ANOMALIES.get((ticker, d), 1.0)
            # A cash distribution, REFLECTED: the traded price drops by the cash amount on the
            # ex-date and stays down, while the adjusted series carries the total return and is
            # unchanged. That is the relationship the verifier proves, and proving it is what keeps
            # this movement out of the unexplained census.
            traded = (100.0 - DIVIDEND_CASH
                      if ticker == DIVIDEND_TICKER and d >= DIVIDEND_DATE else 100.0)
            rows.append({
                "ticker": ticker, "date": d, "open": traded, "high": traded, "low": traded,
                "close": traded, "closeunadj": traded, "closeadj": round(100.0 * factor, 4),
                # SHOP and TLN must be inside the relevance set for their movements to be scanned at
                # all, so they lead the volume ranking the universe is built from.
                "volume": 9_000_000 - i if ticker in ("SHOP", "TLN", DIVIDEND_TICKER)
                          else 1_000_000 + i,
                "lastupdated": d})
    return rows


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    days = _sessions(N_SESSIONS, SESSION)
    st = FactorDataStore(db_path=str(tmp_path_factory.mktemp("parity") / "parity.duckdb"))
    st.ingest_sep(pd.DataFrame(_rows(days)))
    st.ingest_tickers(pd.DataFrame([
        {"ticker": t, "permaticker": p, "name": f"{t} CORP", "exchange": "NYSE",
         "category": "Domestic Common Stock", "sector": "Technology", "industry": "Software",
         "isdelisted": False, "firstpricedate": days[0], "lastpricedate": SESSION,
         "lastupdated": SESSION}
        for t, p in [(DIVIDEND_TICKER, "700000"), SHOP, TLN]
        + [(f"T{i:04d}", str(500000 + i)) for i in range(N_FILLER)]]))
    st.con.execute(
        "INSERT INTO actions (date, action, ticker, name, value, contraticker) "
        "VALUES (?, 'dividend', ?, ?, ?, NULL)",
        [DIVIDEND_DATE, DIVIDEND_TICKER, f"{DIVIDEND_TICKER} CORP", DIVIDEND_CASH])
    for dataset in ("sep", "tickers", "actions"):
        st.record_ingest_run(dataset, datetime(2026, 7, 27, 22, 0), datetime(2026, 7, 27, 22, 5),
                             100, "ok")
    _record_governed_provenance(st, days[0])
    yield st
    st.close()


def _record_governed_provenance(st, coverage_start: date) -> None:
    """Store provenance naming the SAME governed vintage the countersigned manifest binds.

    Written directly because it is the shape the Layer 2 build recorded — including the build-machine
    artifact path, which is precisely why authority moved to the manifest (PR #584).
    """
    identity = ("SHARADAR/{ds}|source_vintage_sha256=" + SOURCE_VINTAGE
                + "|export_object=SHARADAR_{ds}_2_29fe246.zip"
                + "|last_refreshed_time=2026-07-29 23:19:15 UTC"
                + "|reason=HISTORICAL_RECONSTRUCTION_SINGLE_VINTAGE_AND_PERMANENT_LINEAGE")
    for dataset in ("sep", "tickers", "actions"):
        run = st.con.execute(
            "SELECT run_id, rows FROM ingest_runs WHERE dataset = ? ORDER BY finished_at DESC "
            "LIMIT 1", [dataset]).fetchone()
        st.con.execute(
            "INSERT INTO dataset_coverage (dataset, ingest_run_id, coverage_start, coverage_end, "
            "artifact_sha256, artifact_path, source_identity, rows_loaded, recorded_at, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ok')",
            [dataset, run[0], coverage_start, SESSION, "e4" * 32,
             r"C:\LLM-RAG-APP\layer2-vintage\v2\raw\SHARADAR_ACTIONS_2_29fe246cadf.zip",
             identity.format(ds=dataset.upper()), run[1], datetime(2026, 7, 27, 22, 10)])


# ── the two derivations ───────────────────────────────────────────────────────────────────────────

def _phase_c_wiring(store, *, governed=LAYER2_ARTIFACTS, countersignature=COUNTERSIGNATURE):
    """What the READINESS runner measures with — through its own entry point, not reconstructed."""
    return pc._production_wiring(store, Path(governed), Path(countersignature))


def _session_wiring(store, *, governed=LAYER2_ARTIFACTS, countersignature=COUNTERSIGNATURE):
    """What PRODUCTION SESSION COMPOSITION measures with — likewise through its own entry point."""
    from app.validation.production_bindings import governed_narrow_wiring

    corpus = load_any_corpus_manifest(Path(governed) / "corpus_manifest_v2.json")
    sidecar = load_layer2_countersignature(Path(countersignature))
    return governed_narrow_wiring(store, normalize_corpus_manifest(corpus), sidecar,
                                  governed_root=Path(governed))


def _readiness_via_session_path(store, attestation_path: Path, wiring):
    """The session path's readiness gate, assembled exactly as `build_session_runtime` assembles it."""
    attestation, _ = load_narrow_readiness_attestation(attestation_path,
                                                       quarantine=wiring.quarantine)
    gate = sc._GovernedReadiness(store, None, SPEC,
                                 adjustment_verifier=wiring.adjustment_verifier,
                                 narrow_readiness=attestation)
    return gate.assess(SESSION)


@pytest.fixture(scope="module")
def attestation(store, tmp_path_factory) -> Path:
    """The Phase C stage-1 artifact — the ONE thing that crosses from readiness to the session."""
    wiring = _phase_c_wiring(store)
    return pc.derive_attestation(
        store, SESSION, out_path=tmp_path_factory.mktemp("att") / "phase_c_attestation.json",
        construction=SPEC, adjustment_verifier=wiring.adjustment_verifier,
        corpus_manifest_sha256=wiring.quarantine.corpus_manifest_sha256,
        reconciliation_artifact_sha256="a" * 64,
        relevance_artifact_sha256=wiring.ma_disclosure.assessment_artifact_sha256,
        quarantine=wiring.quarantine)


# ── the deployed shape is actually reproduced ─────────────────────────────────────────────────────

def test_the_synthetic_window_is_the_deployed_window(store):
    """★ The fixture is only evidence if it measures the same window. 273 sessions back from
    2026-07-27 on the real calendar is 2025-06-25 — which is why SHOP's 2025-06-25 movement is NOT
    among the governed four: the window's first session has no prior mark to move from."""
    days = _sessions(N_SESSIONS, SESSION)
    assert days[-SPEC.required_history_sessions] == date(2025, 6, 25)


def test_both_paths_reach_the_governed_july_27_readiness_outcome(store, attestation):
    """★ THE RULING'S EXPECTED RESULT, on both sides. Before this change the session path could not
    reach it at all: nothing in `app/` built the disclosure, read the quarantine, or loaded an
    attestation, so a corpus that passed Phase C readiness stopped the session it had just cleared."""
    session_ev = _readiness_via_session_path(store, attestation, _session_wiring(store))
    d = session_ev.to_open_provenance()
    assert d["ready"] is True
    assert d["fully_proven"] is False
    assert d["has_disclosed_limitations"] is True
    assert d["full_action_semantics_proven"] is False
    narrow = d["adjustment_evidence"]["narrow_readiness"]
    assert narrow["decision_validity_proven"] is True
    assert narrow["refusals"] == []
    assert (session_ev.verdict
            is DataReadiness.READY_DECISION_VALID_WITH_DISCLOSED_NONDECISION_LIMITATIONS)

    phase_c = pc.validate_attestation(
        store, SESSION, attestation_path=attestation, construction=SPEC,
        adjustment_verifier=_phase_c_wiring(store).adjustment_verifier,
        corpus_manifest_sha256=_phase_c_wiring(store).quarantine.corpus_manifest_sha256,
        quarantine=_phase_c_wiring(store).quarantine, prediction=None)
    assert phase_c.refusals == ()
    assert phase_c.verdict == str(
        DataReadiness.READY_DECISION_VALID_WITH_DISCLOSED_NONDECISION_LIMITATIONS)


def test_the_four_governed_movements_are_the_ones_measured(store):
    """The quarantine is not a count. These four (identity, session, factor) triples are what the
    countersignature covers, and they are what the store actually shows."""
    wiring = _session_wiring(store)
    assert wiring.quarantine.movement_keys == {
        ("167284", "2025-06-26", "DIVIDEND_FACTOR"),
        ("167284", "2025-06-27", "DIVIDEND_FACTOR"),
        ("642054", "2026-02-02", "DIVIDEND_FACTOR"),
        ("642054", "2026-02-03", "DIVIDEND_FACTOR"),
    }
    ev = sc._GovernedReadiness(store, None, SPEC,
                               adjustment_verifier=wiring.adjustment_verifier).assess(SESSION)
    measured = ev.adjustment_evidence["unexplained_examples"]
    assert {(m["permaticker"], m["session_date"], m["factor"]) for m in measured} \
        == wiring.quarantine.movement_keys


# ── PARITY: the identities, not the counts ────────────────────────────────────────────────────────

def test_the_two_paths_agree_on_every_bound_identity(store, attestation):
    """★★ THE PARITY ASSERTION. Not "both say 2 identities and 4 movements" — two different
    quarantines can agree on both. Every digest and every set."""
    c, s = _phase_c_wiring(store).quarantine, _session_wiring(store).quarantine

    assert c.corpus_manifest_sha256 == s.corpus_manifest_sha256
    assert c.countersignature_sidecar_sha256 == s.countersignature_sidecar_sha256
    assert c.quarantine_evidence_sha256 == s.quarantine_evidence_sha256
    assert c.policy_sha256 == s.policy_sha256
    assert c.permanent_identities == s.permanent_identities
    assert c.descriptive_tickers == s.descriptive_tickers
    assert c.movement_keys == s.movement_keys
    assert c.governed_movement_dates == s.governed_movement_dates
    assert c.governed_factor_types == s.governed_factor_types
    # and the policy digest really is a function of all of it
    assert c.to_open_provenance() == s.to_open_provenance()


def test_the_two_paths_agree_on_the_census_and_the_limitation_digest(store, attestation):
    """★★ The measured half of parity: one status census, one disclosed limitation, one digest."""
    phase_c = pc.validate_attestation(
        store, SESSION, attestation_path=attestation, construction=SPEC,
        adjustment_verifier=_phase_c_wiring(store).adjustment_verifier,
        corpus_manifest_sha256=_phase_c_wiring(store).quarantine.corpus_manifest_sha256,
        quarantine=_phase_c_wiring(store).quarantine, prediction=None)
    session = _readiness_via_session_path(store, attestation,
                                          _session_wiring(store)).to_open_provenance()

    assert (phase_c.provenance["adjustment_evidence"]["checks_by_status"]
            == session["adjustment_evidence"]["checks_by_status"])
    c_lim, s_lim = phase_c.provenance["disclosed_limitations"], session["disclosed_limitations"]
    assert c_lim["limitation_digest"] == s_lim["limitation_digest"]
    assert c_lim["quarantine_policy_sha256"] == s_lim["quarantine_policy_sha256"]
    assert c_lim["quarantined_identities"] == s_lim["quarantined_identities"]
    assert c_lim["movements_by_status"] == s_lim["movements_by_status"] == {
        "GOVERNED_QUARANTINED_UNEXPLAINED_MOVEMENT": 4}
    assert c_lim == s_lim, "one limitation, stated identically by both consumers"


def test_the_disclosed_movement_status_is_never_a_proven_one(store, attestation):
    """It must remain distinct from every proven outcome, and never enter the ACTION census."""
    from app.validation.adjustment_verifier import SATISFIES_READINESS, ActionStatus

    assert ActionStatus.GOVERNED_QUARANTINED_UNEXPLAINED_MOVEMENT not in SATISFIES_READINESS
    d = _readiness_via_session_path(store, attestation, _session_wiring(store)).to_open_provenance()
    assert "GOVERNED_QUARANTINED_UNEXPLAINED_MOVEMENT" not in d["adjustment_evidence"][
        "checks_by_status"], "a movement is not an action and must not join the action census"
    assert d["adjustment_evidence"]["proven"] is False
    assert d["fully_proven"] is False


# ── the refusals: mutate the governed source, prove BOTH consumers refuse ─────────────────────────

def _install(tmp_path: Path, **edits) -> Path:
    """A governed root with the committed artifacts, optionally edited. Returns the root."""
    for name in ("corpus_manifest_v2.json", "corpus_countersignature_v1.json",
                 "shop_tln_quarantine.json", "residual_relevance.json"):
        (tmp_path / name).write_bytes((LAYER2_ARTIFACTS / name).read_bytes())
    for name, mutate in edits.items():
        target = tmp_path / name
        payload = json.loads(target.read_text(encoding="utf-8"))
        mutate(payload)
        target.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")),
                          encoding="utf-8")
    return tmp_path


def test_the_readiness_runner_has_no_quarantine_literal_and_no_fallback():
    """⛔ THE DEFECT BEING REMOVED. `QUARANTINED_IDENTITIES` is gone, and neither stage may default
    the quarantine — the parity above is only evidence if neither side can supply its own."""
    import ast
    import inspect

    assert not hasattr(pc, "QUARANTINED_IDENTITIES")
    # AST rather than a text scan: the module DOCUMENTS the removed constant, and a comment naming
    # the defect is not the defect. What must not exist is a literal the code can read.
    from app.validation import governed_quarantine as gq

    # Every RUNTIME consumer, not just the runner: the identities must reach the code from the
    # countersigned manifest and from nowhere else. `layer2_step6_corpus_manifest.py` is deliberately
    # excluded — it is the construction-time tool that AUTHORED the block, not a consumer of it.
    for module in (pc, gq, sc):
        tree = ast.parse(inspect.getsource(module))
        docstrings = {ast.get_docstring(n, clean=False) for n in ast.walk(tree)
                      if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef))}
        literals = [n.value for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and n.value not in docstrings]
        assert not [x for x in literals if "167284" in x or "642054" in x], (
            f"no permanent identity may appear as a literal {module.__name__} can read")
    for stage in (pc.derive_attestation, pc.validate_attestation):
        default = inspect.signature(stage).parameters["quarantine"].default
        assert default is inspect.Parameter.empty, (
            f"{stage.__name__} must be given the governed quarantine, never fall back to one")


def test_an_edited_quarantine_evidence_artifact_is_refused_by_both(store, tmp_path):
    """The manifest pins the evidence by digest; an edited quarantine is a different quarantine."""
    root = _install(tmp_path, **{"shop_tln_quarantine.json":
                                 lambda p: p["quarantined"]["SHOP"].append("2025-07-01")})
    sidecar = root / "corpus_countersignature_v1.json"
    for wire in (_session_wiring, _phase_c_wiring):
        with pytest.raises(GovernedQuarantineError, match="is a different artifact"):
            wire(store, governed=root, countersignature=sidecar)


def test_a_sidecar_bound_to_another_manifest_is_refused_by_both(store, tmp_path):
    """★ The 'left installed across an upgrade' case: internally valid, approves a different corpus."""
    root = _install(tmp_path, **{"corpus_countersignature_v1.json":
                                 lambda p: p.update(corpus_manifest_sha256="9" * 64)})
    sidecar = root / "corpus_countersignature_v1.json"
    from app.validation.governed_corpus import CountersignatureError

    with pytest.raises(CountersignatureError, match="approval of one construction"):
        _phase_c_wiring(store, governed=root, countersignature=sidecar)
    with pytest.raises(GovernedQuarantineError, match="governs no other"):
        # The session path derives the policy directly, so the binding is re-checked THERE too —
        # a caller that skipped `require_countersignature` still cannot get a policy out of it.
        corpus = load_any_corpus_manifest(root / "corpus_manifest_v2.json")
        governed_quarantine_policy(normalize_corpus_manifest(corpus),
                                   load_layer2_countersignature(sidecar), governed_root=root)


def test_a_manifest_declaring_a_different_identity_is_refused(store, tmp_path):
    """Same tickers, wrong permanent identity: the quarantine is about a lineage, not a symbol."""
    root = _install(tmp_path, **{"corpus_manifest_v2.json":
                                 lambda p: p["governed_quarantine"].update(
                                     permanent_identities=["167284", "999999"])})
    # The manifest's own digest changes with the edit, so its sidecar no longer binds it — which is
    # itself the refusal, and is why an identity cannot be swapped without governance noticing.
    from app.validation.governed_corpus import CountersignatureError

    with pytest.raises(CountersignatureError):
        _phase_c_wiring(store, governed=root,
                        countersignature=root / "corpus_countersignature_v1.json")


def test_a_movement_the_policy_does_not_govern_refuses_on_the_session_path(store, tmp_path):
    """★ The ruling's 'one extra unexplained movement'. The policy is derived from the countersigned
    source; the MEASUREMENT is what carries the extra movement, and the session refuses."""
    wiring = _session_wiring(store)
    attestation_dir = tmp_path / "att"
    attestation_dir.mkdir()
    out = pc.derive_attestation(
        store, SESSION, out_path=attestation_dir / "a.json", construction=SPEC,
        adjustment_verifier=wiring.adjustment_verifier,
        corpus_manifest_sha256=wiring.quarantine.corpus_manifest_sha256,
        reconciliation_artifact_sha256="a" * 64,
        relevance_artifact_sha256=wiring.ma_disclosure.assessment_artifact_sha256,
        quarantine=wiring.quarantine)

    def with_an_extra_movement(window_start, session_date, tickers, store_identity):
        real = wiring.adjustment_verifier(window_start, session_date, tickers, store_identity)

        class _Extra:
            proven = False

            def to_open_provenance(self):
                d = dict(real.to_open_provenance())
                d["unexplained_examples"] = [*d["unexplained_examples"], {
                    "ticker": "ZZZZ", "permaticker": "999999",
                    "session_date": "2026-07-01", "factor": "DIVIDEND_FACTOR"}]
                d["unexplained_adjustment_count"] = len(d["unexplained_examples"])
                return d

        return _Extra()

    attestation, _ = load_narrow_readiness_attestation(out, quarantine=wiring.quarantine)
    gate = sc._GovernedReadiness(store, None, SPEC, adjustment_verifier=with_an_extra_movement,
                                 narrow_readiness=attestation)
    ev = gate.assess(SESSION)
    assert ev.verdict is DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED
    assert any("not covered by the countersigned quarantine"
               in r for r in ev.adjustment_evidence["narrow_readiness"]["refusals"])


def test_an_attestation_written_under_a_DIFFERENT_quarantine_is_refused(store, attestation,
                                                                        tmp_path):
    """★ The ruling's 'session path receives a different quarantine digest'. The attestation names a
    policy digest; the consumer derives its own and refuses on divergence rather than adopting the
    file's. A tampered artifact cannot widen what a session may disclose."""
    forged = tmp_path / "forged.json"
    record = json.loads(attestation.read_bytes())
    record["quarantine_policy_sha256"] = "f" * 64
    forged.write_bytes(json.dumps(record, sort_keys=True, separators=(",", ":")).encode())

    wiring = _session_wiring(store)
    with pytest.raises(NarrowAttestationError, match="one quarantine is not evidence about another"):
        load_narrow_readiness_attestation(forged, quarantine=wiring.quarantine)
    with pytest.raises(pc.PhaseCRefusal, match="one quarantine is not evidence about another"):
        pc.load_attestation(forged, quarantine=wiring.quarantine)


def test_a_declared_but_absent_attestation_refuses_rather_than_falling_back(store, tmp_path):
    """★ The difference between 'no narrow claim' and 'the narrow claim could not be checked'.

    A deployment that declares an attestation and cannot read it must refuse. Falling back to the
    broad gate would silently convert a missing governance artifact into a stricter-looking verdict
    that the session then stops on for the wrong stated reason.
    """
    from types import SimpleNamespace

    config = SimpleNamespace(narrow_readiness_attestation_path=tmp_path / "absent.json")
    with pytest.raises(NarrowAttestationError, match="no narrow-readiness attestation"):
        sc._narrow_attestation(config, _session_wiring(store).quarantine)

    # ...and a deployment that declares none legitimately has no narrow claim.
    assert sc._narrow_attestation(SimpleNamespace(narrow_readiness_attestation_path=None),
                                  _session_wiring(store).quarantine) is None


def test_the_readiness_runner_does_not_import_the_production_composition_root():
    """★ Neither path may call the other. The shared DERIVATION lives in `production_bindings`, which
    both consume; a readiness runner that imported `session_composition` would be asking the thing it
    exists to check what the answer is, and the parity above would rest on the import rather than on
    the governed inputs."""
    import inspect

    src = inspect.getsource(pc)
    assert "session_composition" not in src, (
        "the Phase C runner must not reach into the production composition root")
    assert "production_bindings import governed_narrow_wiring" in src

    from app.validation import production_bindings

    assert hasattr(production_bindings, "governed_narrow_wiring")
    assert not hasattr(sc, "governed_narrow_wiring") or (
        sc.governed_narrow_wiring is production_bindings.governed_narrow_wiring), (
        "one derivation, imported — never re-implemented in the composition root")
