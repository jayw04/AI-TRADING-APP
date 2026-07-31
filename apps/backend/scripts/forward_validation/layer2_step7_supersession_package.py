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

C2 = Path(os.environ.get("LAYER2_CORPUS_DIR", "."))

# ── MEASURED identities (every one computed in this session, none carried from notes) ───────────────
REBUILT = {
    "store_path": "layer2-vintage/corpus-v2/factor_data_layer2.duckdb",
    "store_file_sha256": "5960a0f7c0ae5dfd5955a15e910abc109376ff511cc3d33a849a712a6eee2a09",
    "store_bytes": 1_928_343_552,
    "store_identity_sha256": "fa8fc9a89a3ac83269cb144fd787fce70213ba8a42e1b1f11744b23f6be8f3a7",
    "store_value_identity_sha256":
        "455a7b0c43d91f8589fb6cc5f10743475e4c73c7159b49ad44139c72a4771af8",
    "corpus_manifest_sha256":
        "1e269fadedff74b04135dea5441f2f3338852464c3d06a74c81c98dfc43ca064",
}
SUPERSEDED = {
    "store_path": "/opt/workbench/forward/data/factor_data_full.duckdb (host i-04910523d12387625)",
    "declared_base_corpus_sha256":
        "2659233f97cd3b34631a45812d3f2b6282cc31545793d03b22e8c5569722af87",
    "store_bytes": 2_047_356_928,
    "store_identity_sha256": "57234b02322bcf13368caf9c23461ecdda7d7eb015bca4b1ffa778c858cf86ee",
    "store_value_identity_sha256":
        "4243ffcb284d314721719bd86e2227d328a434350e4348575ad29013ad7832dd",
    "corpus_manifest_sha256":
        "a69ad50ffc3c6925b3c9b6c8fd1c2adc7143ef9d5c98e9378e1c3ea21ca75c49",
    "base_countersignature": "GoverningCorpus_Countersignature_v2.0",
    "note": "`declared_base_corpus_sha256` is a DECLARED identity and is never re-hashed against the "
            "live store; the live file digest legitimately moved when the 2026-07-27 delta was "
            "ingested. Do not 'fix' a changed store digest.",
}

CODE_IDENTITY = {
    "commit": "5173b7c2b3c64ea5f37687c6de6c4c0ee04203b6",
    "commit_role": "the merged Layer 1 squash; the forward host runs this exact commit",
    "tree_clean": False,
    "working_tree_changes": {
        "apps/backend/app/validation/adjustment_verifier.py":
            {"status": "M", "sha256_prefix": "056aa92efd947db3"},
        "apps/backend/app/validation/data_finality.py":
            {"status": "M", "sha256_prefix": "637079afae79b3b8"},
        "apps/backend/scripts/run_forward_validation_session.py":
            {"status": "M", "sha256_prefix": "2b9c8d35627afb7b"},
        "apps/backend/tests/validation/test_adjustment_verifier.py":
            {"status": "M", "sha256_prefix": "2dea72f7b5cd7523"},
        "apps/backend/tests/validation/test_data_finality_narrow_readiness.py":
            {"status": "??", "sha256_prefix": "b62c1773feae9efd"},
    },
    "frozen_replica_stage4_sha256":
        "59c46af111556fbefbeeb622753cb8b8cc3963f2d11f44fbbbaab15e3e0199df",
    "frozen_replica_note": "IDENTICAL on the superseded host runtime and in this worktree — which is "
                           "what makes the Step-4 comparison attributable to corpus construction "
                           "rather than code drift",
    "local_gates": {"full_suite": "4,969 passed / 54 skipped / PYTEST_EXIT=0",
                    "ruff": "clean", "ci_invariants": "15/15 PASS"},
}


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    manifest_path = C2 / "proposed_corpus_manifest_v2.json"
    manifest = json.loads(manifest_path.read_bytes())
    actual = _sha(manifest_path)
    if actual != REBUILT["corpus_manifest_sha256"]:
        print(f"REFUSED — manifest digest moved: {actual} != {REBUILT['corpus_manifest_sha256']}")
        return 1

    payload = {
        "kind": "layer2_store_identity_and_supersession_package", "version": "v1.0",
        "session": "2026-07-27",
        "state": {"proposed": True, "countersigned": False, "deployed": False,
                  "account4": "UNCHANGED", "forward_window": "CLOSED"},

        # (1)(2)(3) proposed manifest + store identities
        "proposed": REBUILT,
        # (4) previous identities
        "superseded": SUPERSEDED,
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
        "code_identity": CODE_IDENTITY,
        # (11) Step 3 narrow-readiness limitation statement
        "step3_limitation_statement": {
            "readiness_outcome": "READY_DECISION_VALID_WITH_DISCLOSED_NONDECISION_LIMITATIONS",
            "full_action_semantics_proven": False,
            "decision_validity_proven": True,
            "nondecision_limitations_present": True,
            "adjustment_reflection_proven": False,
            "terminal_census": {"PROVEN_REFLECTED": 1676,
                                "PROVEN_NO_PRICE_ADJUSTMENT_APPLICABLE": 94,
                                "PROVEN_LINEAGE_EVENT_NO_ADDITIONAL_PRICE_ADJUSTMENT": 3,
                                "UNRESOLVED_NONDECISION_MA_SEMANTICS": 18,
                                "never_assessed": 0, "conflict": 0, "insufficient": 0,
                                "unexplained_factor_movements": 4},
            "claim": "the corpus is valid for the governed July 27 decision, while 18 economically "
                     "terminal acquisition events remain unverifiable from the available vendor "
                     "schema",
            "not_a_claim": "NOT that every corporate action is economically reconciled",
            "session_scoped": "the attestation names 2026-07-27 and is REFUSED for any other session",
        },
        # (12) Step 4 + Step 5 corrected evidence
        "step4_evidence": {
            "artifact_sha256": manifest["artifacts"]["step4_comparison"]["sha256"],
            "supersedes_artifact_sha256":
                "c37489877a3e8faaa66b85765ad75bc3748d50425a0121a65ce141efec330bc6",
            "binding_rule": "the manifest binds ONLY the corrected artifact; the superseded one "
                            "remains in the audit trail but is NOT part of the active construction "
                            "evidence set",
            "decision": "top five AXTI SNDK BE WDC MU — UNCHANGED; weights, ordering and regime state "
                        "unchanged",
            "material_correction": "regime margin above the MA +27.2576% -> +12.3491%, proven to be "
                                   "seam repair (seam-date cross-sectional mean 1-day adjusted "
                                   "return +38.0398% -> +0.4648%)",
        },
        "step5_evidence": {
            "artifact_sha256": manifest["artifacts"]["step5_exclusion_impact_273"]["sha256"],
            "package_sha256": manifest["artifacts"]["step5_package"]["sha256"],
            "window": "EXACT 273 sessions 2025-06-25..2026-07-27",
            "verdict": "no excluded identity touches the July 27 decision",
            "causal_record": {
                "MARA": "displaced at the TOP-200 boundary by ECHO's restored eligibility",
                "COO_and_AGX": "displaced at two MONTH-END TOP-500 boundaries (rank 500 -> 501) by "
                               "broader restored eligibility",
                "OCCI_HYPG": "absent from every decision set INDEPENDENTLY of their exclusion — best "
                             "proxy ranks 3,201 and 3,740, never inside the top-500",
                "SHOP_TLN": "decision-relevant in raw construction; governed-quarantined",
            },
        },
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
    print(f"  proposed corpus_manifest_sha256   {REBUILT['corpus_manifest_sha256']}")
    print(f"  supersedes                        {SUPERSEDED['corpus_manifest_sha256']}")
    print()
    print(f"  {'':<30}{'REBUILT':>34}{'SUPERSEDED':>34}")
    for label, key in (("store_file / declared base", "store_file_sha256"),
                       ("store_identity (registered)", "store_identity_sha256"),
                       ("store_value_identity (full)", "store_value_identity_sha256")):
        a = REBUILT.get(key, "-")
        b = SUPERSEDED.get(key) or SUPERSEDED.get("declared_base_corpus_sha256", "-")
        print(f"  {label:<30}{a[:32]:>34}{b[:32]:>34}")
    print(f"  {'store bytes':<30}{REBUILT['store_bytes']:>34,}{SUPERSEDED['store_bytes']:>34,}")
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
