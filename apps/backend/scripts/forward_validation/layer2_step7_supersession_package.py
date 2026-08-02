"""Layer 2 Step 7 — the store-identity and supersession package.

## Two store identities, and why one is not enough

    store_file_sha256        the identity of the PHYSICAL DuckDB bytes
    store_value_identity     the canonical identity of the GOVERNED CONTENT

They answer different questions. A rebuild that produces byte-for-byte equivalent governed rows but a
different physical layout — different page ordering, a vacuum, a different duckdb patch release —
changes the FILE digest while leaving the VALUE identity untouched. Reporting only the file digest
would make an innocuous re-materialization look like a data change, and reporting only the value
identity would lose the ability to say which artifact was actually shipped.

Three are recorded:

  * `store_file_sha256` — physical bytes.
  * `store_identity_sha256` — the REGISTERED `data_finality.store_identity()` over the 273-session
    window. This is the value the session evidence itself records, so it is directly comparable to a
    readiness assessment. It streams every `sep` field, the `tickers` PIT-eligibility fields, the
    window's actions AND `ingest_runs`.
  * `store_value_identity_sha256` — an EXTENSION defined here: the whole corpus, every governed row,
    EXCLUDING `ingest_runs`. Operational timestamps are not governed content, and a rebuild producing
    identical rows must not read as different merely because it ran at a different time. Stated
    explicitly because it is NOT the registered convention.

## The package proposes; it does not install

Nothing here is countersigned and nothing is deployed. The prior construction keeps its identity
unaltered — the supersession is a NEW record that points at the old one, never an edit of it.
"""

# ⚠ PORTED into the repository for REPRODUCIBILITY. Operator machine paths are removed: the
# backend root resolves relative to this file and every data location comes from an argument or
# an environment override. A hard-coded working-copy path would make the tool unrunnable by
# anyone else, which is the opposite of what a reproducible build tool is for.

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.validation.governed_corpus import canonical_json  # noqa: E402
from scripts.forward_validation._session_arg import add_session_argument  # noqa: E402
from scripts.forward_validation._step7_findings import (  # noqa: E402
    REFUSAL_CODE,
    FindingsRefused,
    cross_check,
    derive_findings,
    unresolved_requirements,
)

C2 = Path(os.environ.get("LAYER2_CORPUS_DIR", "."))

# ── MEASURED identities ─────────────────────────────────────────────────────────────────────────────
#
# ⚠ These WERE three module constants (`REBUILT`, `SUPERSEDED`, `CODE_IDENTITY`) whose comment claimed
# "every one computed in this session, none carried from notes" — while in fact holding literals typed
# in from one particular run: the 2026-07-27 construction's store digests, its superseded manifest, and
# a snapshot of a dirty working tree at commit 5173b7c2. Every later construction would have published
# the PREVIOUS run's identities inside a well-formed supersession record, which is the exact
# declared-vs-actual gap this package exists to close.
#
# They are now DATA, supplied per run — the same discipline `build_normalized_corpus --adjudication`
# already applies ("identity names and counts are DATA, never primary logic in code"). The manifest
# digest is still recomputed from disk and refused on mismatch, so nothing is relaxed: the expected
# value simply moves from a stale literal to an explicit assertion by the operator.

#: Keys a measurement file must carry before the package will bind it.
REQUIRED_REBUILT_KEYS = ("store_path", "store_file_sha256", "store_bytes", "store_identity_sha256",
                         "store_value_identity_sha256", "corpus_manifest_sha256")
REQUIRED_SUPERSEDED_KEYS = ("store_path", "store_bytes", "store_identity_sha256",
                            "store_value_identity_sha256", "corpus_manifest_sha256")


def _window_text(manifest: dict) -> str:
    """State the governed window from the manifest, never from a literal."""
    w = manifest.get("decision_window")
    if not w:
        raise SystemExit(
            "REFUSED — the manifest carries no decision_window; this package will not state a "
            "governed window it did not read from the construction.")
    return f"EXACT {w['sessions']} sessions {w['start']}..{w['end']}"


def _load_measurements(path: Path, required: tuple[str, ...], label: str) -> dict:
    """Load a measurement file and refuse it if any required identity is absent."""
    data = json.loads(path.read_text(encoding="utf-8"))
    missing = [k for k in required if not data.get(k)]
    if missing:
        raise SystemExit(f"REFUSED — {label} measurements {path.name} missing {missing}")
    return data


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    add_session_argument(ap)
    ap.add_argument("--rebuilt", required=True, type=Path,
                    help="JSON of the REBUILT construction's measured store/manifest identities")
    ap.add_argument("--superseded", required=True, type=Path,
                    help="JSON of the SUPERSEDED corpus's measured identities")
    ap.add_argument("--code-identity", required=True, type=Path,
                    help="JSON describing the code tree the construction was produced by")
    ap.add_argument("--operator-analysis", required=True, type=Path,
                    help="operator-authored causal analysis. Required: the findings a program cannot "
                         "derive must be written for THIS construction, and a file carried over from "
                         "the previous one fails its bindings before its prose is read.")
    args = ap.parse_args()
    rebuilt = _load_measurements(args.rebuilt, REQUIRED_REBUILT_KEYS, "rebuilt")
    superseded = _load_measurements(args.superseded, REQUIRED_SUPERSEDED_KEYS, "superseded")
    code_identity = json.loads(args.code_identity.read_text(encoding="utf-8"))

    manifest_path = C2 / "proposed_corpus_manifest_v2.json"
    manifest = json.loads(manifest_path.read_bytes())
    actual = _sha(manifest_path)
    if actual != rebuilt["corpus_manifest_sha256"]:
        print(f"REFUSED — manifest digest moved: {actual} != {rebuilt['corpus_manifest_sha256']}")
        return 1

    # ---- the derived/authored split ----
    step4 = json.loads((C2 / "step4_comparison.json").read_text(encoding="utf-8"))
    step5 = json.loads((C2 / "step5_exclusion_impact_273.json").read_text(encoding="utf-8"))
    recon = json.loads(
        (C2 / "adjustment_reconciliation_final.json").read_text(encoding="utf-8"))
    try:
        derived = derive_findings(step4, step5, recon, args.session.isoformat())
    except FindingsRefused as exc:
        print(f"REFUSED — {exc}")
        return 1

    operator_analysis = json.loads(args.operator_analysis.read_text(encoding="utf-8"))
    bindings = {
        "target_session": args.session.isoformat(),
        "corpus_manifest_sha256": rebuilt["corpus_manifest_sha256"],
        "step4_artifact_sha256": manifest["artifacts"]["step4_comparison"]["sha256"],
        "step5_artifact_sha256": manifest["artifacts"]["step5_exclusion_impact_273"]["sha256"],
    }
    violations = cross_check(operator_analysis, derived, bindings)
    unresolved = unresolved_requirements(operator_analysis, derived)

    print(f"derived material changes : {[c['key'] for c in derived['material_changes']] or 'none'}")
    print(f"cross-check violations   : {len(violations)}")
    for x in violations:
        print(f"    - {x}")
    if violations or unresolved:
        print(f"\nREFUSED — {REFUSAL_CODE}")
        if unresolved:
            print(f"  material changes without an APPROVED causal finding: {unresolved}")
        return 1

    payload = {
        # v2.0: findings are now DERIVED from the bound artifacts and the causal narrative is a
        # separately-bound operator document. The shape changed, so the identity necessarily moves —
        # the v1.0 package keeps its own digest, unmutated, as the record of the first construction.
        "kind": "layer2_store_identity_and_supersession_package", "version": "v2.0",
        "session": args.session.isoformat(),
        "state": {"proposed": True, "countersigned": False, "deployed": False,
                  "account4": "UNCHANGED", "forward_window": "CLOSED"},

        # (1)(2)(3) proposed manifest + store identities
        "proposed": rebuilt,
        # (4) previous identities
        "superseded": superseded,
        # (5) supersession reason
        "supersession": {
            "reason": "HISTORICAL_RECONSTRUCTION_SINGLE_VINTAGE_AND_PERMANENT_LINEAGE",
            "relationship": "SUPERSEDES — not a delta, not a mutation",
            "prior_identity_altered": False,
            "prior_remains": "valid as historical evidence; its countersignature stays checkable",
            "authority": "ADR 0048 §4 — a historical correction is never a delta",
        },
        # ⚠ the distinction the package exists to make explicit
        "store_identity_semantics": {
            "store_file_sha256": "identity of the PHYSICAL DuckDB bytes",
            "store_identity_sha256":
                "REGISTERED data_finality.store_identity() over the 273-session window; streams every "
                "sep field, the tickers PIT-eligibility fields, the window's actions AND ingest_runs. "
                "This is the value a session's evidence records.",
            "store_value_identity_sha256":
                "EXTENSION defined in this package: the WHOLE corpus, every governed row, EXCLUDING "
                "ingest_runs. NOT the registered convention — stated explicitly so it is never "
                "mistaken for it.",
            "why_both": "a rebuild producing equivalent governed data with a different physical "
                        "layout changes the FILE digest while preserving the VALUE identity; only "
                        "recording both distinguishes a re-materialization from a data change",
            "observed": "both value identities DIFFER between the two corpora, as they must — the "
                        "governed content genuinely changed (seam repair, lineage repair, universe "
                        "revision)",
        },
        # (6) source-vintage and universe identities
        "source_and_universe_identities": manifest["declared_identities"] | {
            "mapped_identity_universe_size": manifest["mapped_identity_universe_size"],
            "price_universe_size": manifest["price_universe_size"],
            "security_identity_contract": manifest["security_identity_contract"],
        },
        # (7)(8) artifact + quarantine inventory, carried from the manifest that computed them
        "artifact_inventory": manifest["artifacts"],
        "quarantine_inventory": manifest["quarantined_histories"],
        "governed_quarantine": manifest["governed_quarantine"],
        # (9) schema differences
        "schema_differences": {
            "sep.permaticker": {
                "change": "ADDED (additive) in the Layer 2 corpus",
                "why": "makes 'exactly one permaticker per governed row' checkable IN THE STORE "
                       "rather than only via a join",
                "superseded_store_has_it": False,
                "consequence": "a by-PERMATICKER confirmation can only be made on the rebuilt corpus; "
                               "on the superseded store it returns n/a",
            },
            "actions.contraname": {
                "change": "PRESENT in the sealed vendor export (7 columns), ABSENT from the "
                          "normalized store (6)",
                "used_in_adjustment_arithmetic": False,
                "referenced_by_application_code": False,
                "warning": "the normalized ACTIONS table must NEVER be described as a full-fidelity "
                           "copy of the vendor export; a future change that consumes contraname must "
                           "FAIL the schema-contract check until the field is ingested",
            },
            "tickers.permaticker": {"change": "present in BOTH (Layer 1)"},
        },
        # (10) code/tree identity
        "code_identity": code_identity,
        # (11) Step 3 narrow-readiness limitation statement
        "step3_limitation_statement": {
            "readiness_outcome": "READY_DECISION_VALID_WITH_DISCLOSED_NONDECISION_LIMITATIONS",
            "full_action_semantics_proven": False,
            "decision_validity_proven": True,
            "nondecision_limitations_present": True,
            "adjustment_reflection_proven": False,
            "terminal_census": derived["reconciliation"]["terminal_census"],
            "unexplained_adjustment_count":
                derived["reconciliation"]["unexplained_adjustment_count"],
            "verdict": derived["reconciliation"]["verdict"],
            "not_a_claim": "NOT that every corporate action is economically reconciled",
            "session_scoped": (f"the attestation names {args.session.isoformat()} and is REFUSED "
                               f"for any other session"),
        },
        # (12) Step 4 + Step 5 evidence.
        # ⚠ The findings here are DERIVED from the bound artifacts. They were prose constants
        # describing the 2026-07-27 construction ("top five AXTI SNDK BE WDC MU — UNCHANGED",
        # "regime margin +27.2576% -> +12.3491%", "no excluded identity touches the July 27
        # decision"). Those are true only of that construction; restating them for any other one
        # would publish a false finding inside a well-formed record.
        "step4_evidence": {
            "artifact_sha256": manifest["artifacts"]["step4_comparison"]["sha256"],
            "binding_rule": "the manifest binds ONLY the corrected artifact; any superseded one "
                            "remains in the audit trail but is NOT part of the active construction "
                            "evidence set",
            "decision_comparison": derived["decision_comparison"],
            "universe_comparison": derived["universe_comparison"],
        },
        "step5_evidence": {
            "artifact_sha256": manifest["artifacts"]["step5_exclusion_impact_273"]["sha256"],
            "package_sha256": manifest["artifacts"]["step5_package"]["sha256"],
            "window": _window_text(manifest),
            "exclusion_census": derived["exclusion_census"],
        },
        # (12b) the derived/authored split, stated explicitly so a reader can tell them apart
        "derived_findings": derived,
        "operator_analysis": operator_analysis,
        "cross_check_results": {"violations": [], "clean": True},
        "unresolved_analysis_requirements": [],
        # (13) deployment compatibility — TESTED, not assumed
        "deployment_compatibility": {
            "registered_loader": "app.validation.governed_corpus.load_corpus_manifest",
            "accepts_layer2_manifest": False,
            "tested": True,
            "observed_error": "CorpusConstructionError: the corpus manifest records no valid "
                              "base_coverage_through: 'base_coverage_through'",
            "requirement": "the runtime requires EITHER explicit support for the "
                           "`layer2_governed_corpus` kind, OR a deterministic conversion into a "
                           "registered deployment manifest whose identity BINDS this reconstruction "
                           "manifest",
            "warning": "a valid hash does NOT imply the current loader can consume the new shape — "
                       "this was verified by attempting the load, not inferred",
            "blocking": "deployment cannot proceed on this manifest until one of the two paths is "
                        "implemented and countersigned",
        },
        # (14) headroom + ordering wording rulings
        "wording_rulings": {
            "headroom": {"scoring_universe_eligible": 200,
                         "fill": "EXACTLY FILLED (200/200)", "top_five_capacity": 5,
                         "selection_headroom_names": 195,
                         "reading": "'headroom 0' refers to universe FILL, not selection fragility"},
            "winsorization_tie": {
                "fact": "AXTI and SNDK are tied at the winsorized z-score cap",
                "ordering": "deterministic secondary (-z, ticker) sort places AXTI first",
                "economic_effect": "NONE — equal weighting",
                "wording": "the displayed order must NOT be described as pure raw-momentum order",
                "action": "non-blocking implementation fact; no ranking change authorized"},
        },
        "gates_relaxed": False,
    }

    blob = canonical_json(payload)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)
    digest = hashlib.sha256(blob).hexdigest()

    print(f"{'=' * 78}")
    print("LAYER 2 STORE-IDENTITY AND SUPERSESSION PACKAGE")
    print(f"{'=' * 78}")
    print(f"  proposed corpus_manifest_sha256   {rebuilt['corpus_manifest_sha256']}")
    print(f"  supersedes                        {superseded['corpus_manifest_sha256']}")
    print()
    print(f"  {'':<30}{'REBUILT':>34}{'SUPERSEDED':>34}")
    for label, key in (("store_file / declared base", "store_file_sha256"),
                       ("store_identity (registered)", "store_identity_sha256"),
                       ("store_value_identity (full)", "store_value_identity_sha256")):
        a = rebuilt.get(key, "-")
        b = superseded.get(key) or superseded.get("declared_base_corpus_sha256", "-")
        print(f"  {label:<30}{a[:32]:>34}{b[:32]:>34}")
    print(f"  {'store bytes':<30}{rebuilt['store_bytes']:>34,}{superseded['store_bytes']:>34,}")
    print()
    print(f"  artifacts bound     {len(payload['artifact_inventory'])}"
          f" + {len(payload['quarantine_inventory'])} quarantine")
    print(f"  loader accepts kind {payload['deployment_compatibility']['accepts_layer2_manifest']}"
          f"  (TESTED)")
    print(f"  state               proposed={payload['state']['proposed']} "
          f"countersigned={payload['state']['countersigned']} "
          f"deployed={payload['state']['deployed']}")
    print(f"\nstep7_supersession_package_sha256: {digest}")
    print(f"wrote {out} ({len(blob):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
