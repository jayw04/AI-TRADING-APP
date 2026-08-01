"""Phase C — prove the DEPLOYED runtime reproduces the governed narrow-ready verdict.

⚠ This is a READINESS runner, not a session runner. It evaluates readiness and stops. It opens no
window, records no observation, computes no factor value or ranking, and touches no account.

## Why this is two stages, and why they are separated by a FILE

The first Phase C attempt failed because its expected census was hand-carried from a DIAGNOSTIC runner
that assembled its own relevance set (689 identities) while the readiness path builds a different one
(670). The counts were internally consistent and described a different set of securities; the deployed
runtime correctly refused them.

Deleting the hard-coded constant is not sufficient. A runner that derives an attestation and then
validates it against the same in-memory assessment proves nothing either — it would agree with itself
by construction, which is the identical defect wearing different clothes.

So the stages communicate ONLY through a serialized artifact:

  STAGE 1  derive   — run the frozen readiness construction, capture its relevance set, derive the
                      attestation from THAT run, and write it to disk. Returns only a path.
  STAGE 2  validate — reload the attestation FROM DISK and check it against a SECOND, independent
                      assessment. Takes only a path.

`validate_attestation` never receives a Python object from `derive_attestation`; the signatures make
that impossible rather than merely discouraged. Every cross-stage binding — session, corpus identity,
store identity, relevance-set digest, status census — is re-derived by stage 2 and refused on
divergence.

## The governed prediction

`GOVERNED_PREDICTION` is checked AFTER stage 2 and is never an input to anything. It cannot influence
the attestation, the census or the verdict; it can only fail the run. It exists because the narrow
contract is self-consistent by design: a corpus or deployment drift would produce a different but
internally coherent census that every clause would happily accept. The prediction is the one check that
catches that, and it was recorded in advance of the run rather than fitted to it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app.validation.data_finality import (
    NARROW_ATTESTATION_KIND,
    READINESS_PERMITS_EVALUATION,
    ConstructionSpec,
    NarrowAttestationError,
    NarrowReadinessAttestation,
    assess_data_finality,
    build_narrow_readiness_attestation,
    load_narrow_readiness_attestation,
    narrow_attestation_payload,
)
from app.validation.governed_quarantine import GovernedQuarantinePolicy

SESSION = date(2026, 7, 27)
ATTESTATION_KIND = NARROW_ATTESTATION_KIND

# ⚠⚠ THERE IS NO `QUARANTINED_IDENTITIES` CONSTANT, AND THERE IS NO FALLBACK.
#
# There was one — `frozenset({"167284", "642054"})` — and it was the same defect class Amendment 2
# removed from the session runner. It happened to match the countersigned `governed_quarantine` block,
# so the two paths appeared to agree while nothing checked that they still did. The quarantine now
# comes from `governed_quarantine_policy`, the single manifest-derived derivation that production
# session composition uses, and this runner cannot construct an attestation without one.


@dataclass(frozen=True)
class GovernedPrediction:
    """The outcome recorded BEFORE the run. Checked last; an input to nothing.

    ⚠ `census` is NOT an expected-count fallback and must never be passed to an attestation. It is an
    acceptance criterion applied to a census that was already independently derived and independently
    validated. If it ever reaches `NarrowReadinessAttestation`, the two-stage separation is defeated —
    a source-level test pins that it does not.
    """
    verdict: str
    ready: bool
    fully_proven: bool
    has_disclosed_limitations: bool
    full_action_semantics_proven: bool
    decision_validity_proven: bool
    nondecision_limitations_present: bool
    corpus_wide_unsupported_semantics: int
    present_in_readiness_relevance_set: int
    quarantined_unexplained_movements: int
    census: dict[str, int]


#: Recorded 2026-07-31, accepted by the owner in advance of the corrected run.
#:
#: `has_disclosed_limitations=True` with `nondecision_limitations_present=False` is not a contradiction:
#: the session's disclosed limitation is the SHOP/TLN quarantine, not the 18 corpus-wide M&A events —
#: none of which lie inside this session's relevance set.
GOVERNED_PREDICTION = GovernedPrediction(
    verdict="READY_DECISION_VALID_WITH_DISCLOSED_NONDECISION_LIMITATIONS",
    ready=True,
    fully_proven=False,
    has_disclosed_limitations=True,
    full_action_semantics_proven=False,
    decision_validity_proven=True,
    nondecision_limitations_present=False,
    corpus_wide_unsupported_semantics=18,
    present_in_readiness_relevance_set=0,
    quarantined_unexplained_movements=4,
    census={
        "PROVEN_REFLECTED": 1670,
        "PROVEN_NO_PRICE_ADJUSTMENT_APPLICABLE": 91,
        "PROVEN_LINEAGE_EVENT_NO_ADDITIONAL_PRICE_ADJUSTMENT": 3,
    },
)


class PhaseCRefusal(Exception):
    """A stage-2 binding does not hold. Fails closed — never reconciled, never reinterpreted."""


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


# ── STAGE 1 — derive and serialize ───────────────────────────────────────────────────────────────────

def derive_attestation(
    store: Any,
    session_date: date,
    *,
    out_path: Path,
    construction: ConstructionSpec | None = None,
    universe_fn: Any = None,
    adjustment_verifier: Any,
    corpus_manifest_sha256: str,
    reconciliation_artifact_sha256: str,
    relevance_artifact_sha256: str,
    quarantine: GovernedQuarantinePolicy,
) -> Path:
    """Derive the attestation from the frozen readiness construction and serialize it.

    ⚠ RETURNS ONLY A PATH. Stage 2 cannot be handed the in-memory attestation even by accident, which
    is what stops this runner validating an object against itself.

    ⚠ `quarantine` has NO DEFAULT. It is the countersigned policy, derived by the same call production
    session composition makes; there is nothing for this runner to fall back to and nothing for it to
    assert on its own.
    """
    attestation, record = build_narrow_readiness_attestation(
        store, session_date, construction=construction, universe_fn=universe_fn,
        adjustment_verifier=adjustment_verifier,
        reconciliation_artifact_sha256=reconciliation_artifact_sha256,
        relevance_artifact_sha256=relevance_artifact_sha256,
        quarantine=quarantine)

    blob = _canonical(narrow_attestation_payload(
        attestation, record, corpus_manifest_sha256=corpus_manifest_sha256))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(blob)
    return out_path


# ── STAGE 2 — reload and independently validate ──────────────────────────────────────────────────────

def load_attestation(path: Path, *, quarantine: GovernedQuarantinePolicy,
                     ) -> tuple[NarrowReadinessAttestation, dict[str, Any]]:
    """Rehydrate the attestation FROM BYTES ON DISK — never from a stage-1 object.

    Delegates to the `app/` contract the production session path also reads, so "what the attestation
    file means" has one definition. The quarantine is supplied by the caller from the countersigned
    manifest and is refused unless the artifact names the same policy digest: an attestation cannot
    nominate the movements it wishes to be excused for.
    """
    try:
        return load_narrow_readiness_attestation(Path(path), quarantine=quarantine)
    except NarrowAttestationError as exc:
        raise PhaseCRefusal(str(exc)) from exc


@dataclass(frozen=True)
class PhaseCResult:
    passed: bool
    verdict: str
    provenance: dict[str, Any]
    attestation_sha256: str
    refusals: tuple[str, ...]
    prediction_failures: tuple[str, ...]


def validate_attestation(
    store: Any,
    session_date: date,
    *,
    attestation_path: Path,
    construction: ConstructionSpec | None = None,
    universe_fn: Any = None,
    adjustment_verifier: Any,
    corpus_manifest_sha256: str,
    quarantine: GovernedQuarantinePolicy,
    # ⚠ NO DEFAULT, deliberately. Binding `GOVERNED_PREDICTION` here would put the predicted census
    # inside stage 2's own frame, one edit away from being consulted as a fallback. The caller supplies
    # it, and it reaches nothing but the post-hoc comparison below.
    prediction: GovernedPrediction | None,
) -> PhaseCResult:
    """Reload the persisted attestation and check it against a SECOND, independent assessment.

    ⚠ TAKES ONLY A PATH. Everything it compares against is measured by this run, not carried in — and
    the quarantine it binds is re-derived by this run from the countersigned manifest, not read out of
    the artifact being validated.
    """
    attestation, record = load_attestation(attestation_path, quarantine=quarantine)
    blob = Path(attestation_path).read_bytes()

    # ── producer/consumer bindings, BEFORE the assessment is trusted ──
    if attestation.session_date != session_date:
        raise PhaseCRefusal(
            f"the persisted attestation names {attestation.session_date} but this run evaluates "
            f"{session_date}")
    if record["corpus_manifest_sha256"] != corpus_manifest_sha256:
        raise PhaseCRefusal(
            f"the attestation was produced against corpus {record['corpus_manifest_sha256'][:16]}… "
            f"but this run loaded {corpus_manifest_sha256[:16]}…")

    ev = assess_data_finality(store, session_date, construction=construction,
                              universe_fn=universe_fn, adjustment_verifier=adjustment_verifier,
                              narrow_readiness=attestation)
    d = ev.to_open_provenance()
    adjustment = d.get("adjustment_evidence") or {}
    narrow = adjustment.get("narrow_readiness") or {}

    # ── the same identities, re-derived by THIS run ──
    if str(adjustment.get("store_identity_sha256") or "") != record["store_identity_sha256"]:
        raise PhaseCRefusal(
            f"the attestation was produced against store "
            f"{record['store_identity_sha256'][:16]}… but this run measured "
            f"{str(adjustment.get('store_identity_sha256'))[:16]}…")
    if str(adjustment.get("relevance_set_sha256") or "") != attestation.relevance_set_sha256:
        raise PhaseCRefusal(
            f"the attestation was produced over relevance set "
            f"{attestation.relevance_set_sha256[:16]}… but this run constructed "
            f"{str(adjustment.get('relevance_set_sha256'))[:16]}…")
    measured = {str(k): int(v) for k, v in (adjustment.get("checks_by_status") or {}).items()}
    if measured != dict(attestation.expected_status_counts):
        raise PhaseCRefusal(
            f"the attestation census {dict(attestation.expected_status_counts)} does not match this "
            f"run's measurement {measured}")

    refusals = tuple(narrow.get("refusals") or ())
    verdict = str(d.get("readiness_verdict"))
    failures = _check_prediction(d, narrow, prediction) if prediction else ()
    passed = (not refusals and not failures
              and ev.verdict in READINESS_PERMITS_EVALUATION)
    return PhaseCResult(passed=passed, verdict=verdict, provenance=d,
                        attestation_sha256=hashlib.sha256(blob).hexdigest(),
                        refusals=refusals, prediction_failures=failures)


def _check_prediction(d: dict[str, Any], narrow: dict[str, Any],
                      p: GovernedPrediction) -> tuple[str, ...]:
    """Compare the measured outcome to the prediction recorded in advance. Never an input."""
    out: list[str] = []

    def cmp(name: str, got: Any, want: Any) -> None:
        if got != want:
            out.append(f"{name}: predicted {want!r}, measured {got!r}")

    cmp("verdict", d.get("readiness_verdict"), p.verdict)
    cmp("ready", d.get("ready"), p.ready)
    cmp("fully_proven", d.get("fully_proven"), p.fully_proven)
    cmp("has_disclosed_limitations", d.get("has_disclosed_limitations"), p.has_disclosed_limitations)
    cmp("full_action_semantics_proven", d.get("full_action_semantics_proven"),
        p.full_action_semantics_proven)
    cmp("decision_validity_proven", narrow.get("decision_validity_proven"), p.decision_validity_proven)
    cmp("nondecision_limitations_present", narrow.get("nondecision_limitations_present"),
        p.nondecision_limitations_present)
    cmp("corpus_wide_unsupported_semantics", narrow.get("corpus_wide_unsupported_semantics_count"),
        p.corpus_wide_unsupported_semantics)
    cmp("present_in_readiness_relevance_set",
        narrow.get("unsupported_semantics_in_readiness_relevance_set"),
        p.present_in_readiness_relevance_set)
    cmp("quarantined_unexplained_movements",
        narrow.get("unexplained_movements_on_quarantined_identities"),
        p.quarantined_unexplained_movements)
    adjustment = d.get("adjustment_evidence") or {}
    measured = {str(k): int(v) for k, v in (adjustment.get("checks_by_status") or {}).items()}
    cmp("status census", measured, dict(p.census))
    return tuple(out)


# ── the deployed wiring ──────────────────────────────────────────────────────────────────────────────

def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _production_wiring(store: Any, governed: Path, countersignature: Path):
    """Bind the quarantine, the disclosure and the adjustment verifier THROUGH the production
    composition root, so the result describes the REGISTERED construction rather than one assembled
    here.

    ⚠ This function used to assemble all three by hand: it read `residual_relevance.json` by a
    filename of its own choosing, and it wrote an `ActionSourceDeclaration` with a literal identity
    string and a coverage window taken straight off the `actions` table — while production derived the
    declaration from the store's own ingest provenance under the manifest-bound authority policy. Two
    different sources produce two different censuses, so the claim "Phase C measured what the session
    will measure" was not checkable. It is now structural: this calls `governed_narrow_wiring`.

    ⚠⚠ That call goes to `app.validation.production_bindings`, NOT to the session composition root.
    This runner never imports the thing it exists to check; both are consumers of one shared
    derivation over the same governed inputs, and each runs its own independent assessment.

    ⚠ No universe callable is bound either. `assess_data_finality` wraps whatever it is given in the
    session's own `SessionLineageFilter`, so passing a pre-filtered callable was redundant on this
    side and absent on the other — and "redundant but only here" is how two paths drift.
    """
    from app.validation.governed_corpus import (
        Layer2CorpusManifest,
        load_any_corpus_manifest,
        load_layer2_countersignature,
        normalize_corpus_manifest,
        require_countersignature,
    )
    from app.validation.production_bindings import governed_narrow_wiring

    corpus = load_any_corpus_manifest(governed / "corpus_manifest_v2.json")
    if not isinstance(corpus, Layer2CorpusManifest):
        raise PhaseCRefusal(
            "Phase C validates a Layer 2 reconstruction; the governed directory holds a "
            "base-plus-delta corpus manifest, which carries no governed quarantine")
    sidecar = load_layer2_countersignature(countersignature)
    require_countersignature(corpus, sidecar)
    return governed_narrow_wiring(store, normalize_corpus_manifest(corpus), sidecar,
                                  governed_root=governed)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runtime", default="/opt/workbench/forward/runtime")
    ap.add_argument("--governed", default="/opt/workbench/forward/governed/layer2")
    ap.add_argument("--countersignature", default=None,
                    help="the Layer 2 countersignature sidecar; defaults to the one installed "
                         "beside the corpus manifest. There is no unsigned mode.")
    ap.add_argument("--store", default="/opt/workbench/forward/data/factor_data_layer2.duckdb")
    ap.add_argument("--stage", choices=("derive", "validate", "both"), default="both")
    args = ap.parse_args(argv)

    from app.factor_data.store import FactorDataStore
    from app.validation.governed_corpus import load_any_corpus_manifest, normalize_corpus_manifest

    governed = Path(args.governed)
    countersignature = (Path(args.countersignature) if args.countersignature
                        else governed / "corpus_countersignature_v1.json")
    attestation_path = governed / "phase_c_attestation.json"
    manifest = normalize_corpus_manifest(
        load_any_corpus_manifest(governed / "corpus_manifest_v2.json"))
    spec = ConstructionSpec()
    store = FactorDataStore(args.store, read_only=True)
    wiring = _production_wiring(store, governed, countersignature)

    print("== deployed construction ==")
    print(f"   corpus_construction_kind    {manifest.corpus_construction_kind}")
    print(f"   corpus_manifest_sha256      {manifest.corpus_manifest_sha256}")
    print(f"   has_base_and_deltas         {manifest.has_base_and_deltas}")

    print("\n== governed quarantine (manifest-derived, shared with session composition) ==")
    q = wiring.quarantine
    print(f"   policy_sha256               {q.policy_sha256}")
    print(f"   countersignature_sha256     {q.countersignature_sidecar_sha256}")
    print(f"   evidence_sha256             {q.quarantine_evidence_sha256}")
    print(f"   anomaly_class               {q.anomaly_class}")
    print(f"   permanent identities        {sorted(q.permanent_identities)}")
    print(f"   descriptive tickers         {dict(sorted(q.descriptive_tickers.items()))}")
    print(f"   governed movement dates     {list(q.governed_movement_dates)}")
    print(f"   governed factor types       {list(q.governed_factor_types)}")
    print(f"   governed movements          {len(q.movements)}")

    if args.stage in ("derive", "both"):
        print("\n== STAGE 1 — derive the attestation from the frozen readiness construction ==")
        derive_attestation(
            store, SESSION, out_path=attestation_path, construction=spec,
            adjustment_verifier=wiring.adjustment_verifier,
            corpus_manifest_sha256=manifest.corpus_manifest_sha256,
            reconciliation_artifact_sha256=_sha(governed / "adjustment_reconciliation_final.json"),
            relevance_artifact_sha256=wiring.ma_disclosure.assessment_artifact_sha256,
            quarantine=q)
        print(f"   wrote {attestation_path} ({attestation_path.stat().st_size:,} bytes)")
        print(f"   sha256 {_sha(attestation_path)}")
        # ⚠ Nothing from stage 1 is carried forward in memory. Stage 2 reads the file.

    if args.stage == "derive":
        store.con.close()
        return 0

    print("\n== STAGE 2 — reload and independently validate against a fresh assessment ==")
    try:
        result = validate_attestation(
            store, SESSION, attestation_path=attestation_path, construction=spec,
            adjustment_verifier=wiring.adjustment_verifier,
            corpus_manifest_sha256=manifest.corpus_manifest_sha256,
            quarantine=q, prediction=GOVERNED_PREDICTION)
    except PhaseCRefusal as exc:
        print(f"\nPHASE C: STOP — {exc}")
        store.con.close()
        return 1

    d = result.provenance
    narrow = (d.get("adjustment_evidence") or {}).get("narrow_readiness") or {}
    lim = d.get("disclosed_limitations") or {}
    print(f"\n   verdict                      {d['readiness_verdict']}")
    for k in ("ready", "fully_proven", "has_disclosed_limitations", "full_action_semantics_proven"):
        print(f"   {k:<28} {d[k]}")
    print(f"   decision_validity_proven     {narrow.get('decision_validity_proven')}")
    print(f"   refusals                     {list(result.refusals)}")

    print("\n== disclosed limitations ==")
    print(f"   known corpus-wide            {lim.get('known_corpus_wide_unsupported_semantics')}")
    print(f"   present in relevance set     {lim.get('present_in_readiness_relevance_set')}")
    print(f"   quarantined movements        "
          f"{lim.get('unexplained_movements_on_quarantined_identities')}")
    print(f"   quarantined identities       {lim.get('quarantined_identities')}")
    print(f"   quarantine policy sha256     {lim.get('quarantine_policy_sha256')}")
    print(f"   movement status census       {lim.get('movements_by_status')}")
    print(f"   limitation digest            {lim.get('limitation_digest')}")
    print(f"   relevance set sha256         {lim.get('readiness_relevance_set_sha256')}")
    print(f"   relevant ticker count        {lim.get('relevant_ticker_count')}")

    print("\n== construction coverage ==")
    for k in ("session_eligible_universe", "session_complete", "lookback_sessions_available",
              "proxy_expected_constituents", "proxy_contributing_constituents",
              "proxy_sessions_incomplete", "duplicate_row_count", "corporate_actions_in_window"):
        print(f"   {k:<32} {d.get(k)}")

    if result.prediction_failures:
        print("\n== PREDICTION DIVERGENCE ==")
        for f in result.prediction_failures:
            print(f"   ! {f}")

    receipt = governed / "phase_c_readiness_receipt.json"
    blob = _canonical({"attestation_sha256": result.attestation_sha256,
                       "prediction_failures": list(result.prediction_failures),
                       "readiness": d})
    receipt.write_bytes(blob)
    print(f"\nattestation sha256: {result.attestation_sha256}")
    print(f"receipt sha256:     {hashlib.sha256(blob).hexdigest()}")
    print(f"wrote {receipt} ({len(blob):,} bytes)")
    print(f"\nPHASE C: {'PASS' if result.passed else 'STOP — NOT THE GOVERNED VERDICT'}")
    print("⛔ Readiness only. No window opened, no observation recorded, Account 4 untouched.")
    store.con.close()
    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
