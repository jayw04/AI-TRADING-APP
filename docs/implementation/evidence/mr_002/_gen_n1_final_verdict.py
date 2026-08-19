"""MR-002 Gate N1 — the FINAL ADJUDICATED verdict record.

Binds, in one immutable record:
  * the clean-rerun verdict e835cd7c... (the PRE-RULING input, preserved unmodified)
  * the owner's D3 clause-5 ruling of 2026-08-19
  * the C5 registered-tie interpretation
  * the prospective PIQP_P2 tie adjudication, recorded BEFORE the clean result existed
  * the S3 bulk-evidence manifests

The pre-ruling file is NOT edited to say N1_ADVANCE. It stays as the input, and this record is the
adjudicated output, so the audit trail has a clean before/after structure.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
SOURCE_COMMIT = "770a1091b9301ff6af6bd6950b4e4565312dcba9"
PRE_RULING = "MR002_N1_Verdict_v1.0_DRAFT.json"


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def blob_sha(path: str) -> str:
    o = subprocess.run(["git", "-C", REPO, "show", f"HEAD:{path}"], capture_output=True)
    return hashlib.sha256(o.stdout).hexdigest() if o.returncode == 0 else "UNCOMMITTED"


def file_sha(path: str) -> str:
    with open(os.path.join(REPO, path), "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def load(path: str) -> dict:
    with open(os.path.join(REPO, path)) as fh:
        return json.load(fh)


E = "docs/implementation/evidence/mr_002/"
pre = load(E + PRE_RULING)
exec_mf = load("manifests/s3/objects/mr002-n1-execution-evidence.v1.json")
prov_mf = load("manifests/s3/objects/mr002-n1-provisional-execution.v1.json")

p2 = pre["per_candidate"]["PIQP_P2"]
p1 = pre["per_candidate"]["PIQP_P1"]

REC: dict = {
    "record_type": "MR002_N1_FINAL_ADJUDICATED_VERDICT",
    "record_status": "FINAL",
    "version": "1.0",
    "program": "MR-002 / SPQ-1",
    "gate": "N1",
    "date": "2026-08-19",

    "disposition": "N1_ADVANCE",
    "selected_solver_A": "QUADPROG_SQRT",
    "selected_solver_B": "PIQP_P2",
    "authorizes": "nothing beyond N1 — N2 requires its own grant",

    "authority_chain": {
        "sealed_registration": {
            "record": "MR002_N1_ProspectiveRegistration_v1.0",
            "identity_sha256": "7f8a56e34e6d5d36a3914ecb825de015debdc83ebae2967887e5e37ca3d684af",
        },
        "adjudication_addendum": {
            "path": E + "MR002_N1_AdjudicationAddendum_v1.0.md",
            "file_blob_sha256": blob_sha(E + "MR002_N1_AdjudicationAddendum_v1.0.md"),
        },
        "pre_ruling_verdict": {
            "path": E + PRE_RULING,
            "record_identity_sha256": pre["record_identity_sha256"],
            "disposition_at_that_point": pre["disposition"],
            "preserved_unmodified": True,
            "why": ("it is the INPUT to this adjudication. Editing it to say N1_ADVANCE would "
                    "destroy the before/after audit structure."),
        },
    },

    # ── owner rulings of 2026-08-19 ──────────────────────────────────────────────────────────────
    "owner_rulings": {
        "D3_clause5": {
            "ruling": "PASS",
            "registered_clarification": (
                "For D3 clause 5, 'method disposition' means the TERMINAL SEMANTIC CLASS of the "
                "two-generator method — resolved certified allocation versus unresolved/integrity "
                "stop — not the accepted_by generator attribution. A permutation-induced "
                "SECONDARY_CERTIFIED <-> PRIMARY_CERTIFIED transition is diagnostic numerical-route "
                "variation, not a method-semantic failure, provided the accepted allocations satisfy "
                "the registered equivalence bound and neither run changes terminal semantic class."),
            "not_a_relaxation_of": "the allocation requirement, which remains strict",
            "evidence": {
                "B_decisive_instances": 5,
                "permuted_checks": 30,
                "disposition_transitions": 20,
                "all_transitions_were": "SECONDARY_CERTIFIED -> PRIMARY_CERTIFIED",
                "cause": ("QUADPROG_SQRT's false-infeasibility is coordinate-order dependent; it "
                          "CERTIFIES the permuted instance, so B is no longer needed"),
                "unresolved_instance_count": 0,
                "invalid_run_count": 0,
                "certified_solution_disagreements": 0,
                "allocation_beyond_registered_bound": 0,
                "worst_allocation_deviation": 7.275263277824169e-14,
            },
            "retained_diagnostic_finding": (
                "Solver A is NOT permutation-stable on its failure set. This is recorded explicitly "
                "rather than presumed away; only 285 of 11,667 permuted A solves are byte-identical."),
        },
        "C5": {
            "ruling": "TIE",
            "basis": ("the prospectively registered mechanical rule, committed in "
                      f"{SOURCE_COMMIT[:12]} BEFORE the formal rerun result existed: a difference "
                      "inside run-to-run noise is not a C5 decision"),
            "registered_test": "median_gap > max(within_candidate_run_spread), else TIE",
            "measured": {"median_gap": 0.72, "noise": 2.56, "verdict": "TIE"},
            "diagnostics_retained_as_NON_DECISIONAL": {
                "pooled_measurements_per_candidate": 13,
                "PIQP_P1": {"mean": 44.43, "sd": 0.60, "median": 44.42},
                "PIQP_P2": {"mean": 45.02, "sd": 0.87, "median": 44.92},
                "nominal_difference_seconds": 0.60,
                "nominal_difference_percent": 1.3,
                "cohens_d": 0.80,
                "mann_whitney_z": -1.72,
                "sign_test_executions": "P1 median lower in 3 of 3",
                "why_non_decisional": (
                    "replacing the registered decision rule with Cohen's d, a Mann-Whitney p-value, "
                    "a sign test, or a 'consistent nominal winner' heuristic AFTER seeing the data "
                    "is exactly the post-results rule invention SA-4 exists to prevent"),
            },
        },
        "tie_adjudication": {
            "selected": "PIQP_P2",
            "recorded_before_this_result_existed": True,
            "committed_in": SOURCE_COMMIT,
            "character": "owner discretionary resolution of the registered C6 tie",
            "explicitly_NOT": [
                "a new C7 criterion",
                "the withdrawn v1 standalone-nonqualification tiebreak (51 vs 59)",
                "a choice made because PIQP_P2 yields the preservation result",
            ],
            "stated_basis": "minimum-change continuity",
        },
    },

    # ── findings ─────────────────────────────────────────────────────────────────────────────────
    "findings": {
        "corpus": {"result": "PASS", "hash": pre["corpus_hash"], "reproduced_exactly": True},
        "C1": {"PIQP_P1": p1["C1"]["pass"], "PIQP_P2": p2["C1"]["pass"],
               "CLARABEL": pre["per_candidate"]["CLARABEL"]["C1"]["pass"]},
        "C2": {"PIQP_P1": p1["C2"], "PIQP_P2": p2["C2"],
               "CLARABEL": pre["per_candidate"]["CLARABEL"]["C2"],
               "note": "CLARABEL eliminated at C2 (3894/3895)"},
        "C3": {"PIQP_P1": p1["C3"], "PIQP_P2": p2["C3"]},
        "C4": {"PIQP_P1": p1["C4"], "PIQP_P2": p2["C4"]},
        "C5": "TIE (registered noise rule)",
        "C6": "TIE (same piqp package; profiles differ only in preconditioner_scale_cost)",
        "SA2": {"PIQP_P1": p1["SA2"], "PIQP_P2": p2["SA2"]},
        "equivalence_bakeoff_population": {
            "scope": "valid, scoped evidence — NOT the authoritative preservation test",
            "PIQP_P1": p1["equivalence_gate"]["routes"],
            "PIQP_P2": p2["equivalence_gate"]["routes"],
            "EQUIVALENCE_UNPROVEN": 0,
        },
        "preservation_governed_v1_replay": pre["preservation"],
        "difference_vs_v1_bakeoff": pre.get("difference_vs_v1"),
        "v1_baseline": pre["v1_regeneration_referent"],
    },

    "advance_conditions_at_pre_ruling": pre["advance_conditions"],
    "advance_conditions_resolved_by_ruling": {
        "10_C4b_clause5_disposition_unchanged": (
            "resolved PASS by the D3 clause-5 clarification: generator attribution may change, "
            "terminal semantic class and allocation may not, and neither did"),
    },

    # ── evidence custody ─────────────────────────────────────────────────────────────────────────
    "evidence_custody": {
        "model": ("bulk raw execution output in versioned S3 pinned by VersionId + SHA-256 with "
                  "read-back confirmation; governing summaries in Git. `.mr002out/` remains "
                  "'scratch — never evidence' and is NOT a governance store."),
        "s3_packages": {
            "formal_execution": {
                "manifest_path": "manifests/s3/objects/mr002-n1-execution-evidence.v1.json",
                "manifest_sha256": file_sha("manifests/s3/objects/mr002-n1-execution-evidence.v1.json"),
                "bucket": exec_mf["bucket"],
                "object_key_prefix": exec_mf["object_key"],
                "package_sha256": exec_mf["sha256"],
                "byte_length": exec_mf["byte_length"],
                "members": len(exec_mf["package_members"]),
                "all_readback_verified_by_version_id": all(
                    m["readback_verified_by_version_id"] for m in exec_mf["package_members"]),
            },
            "provisional_execution": {
                "manifest_path": "manifests/s3/objects/mr002-n1-provisional-execution.v1.json",
                "manifest_sha256": file_sha("manifests/s3/objects/mr002-n1-provisional-execution.v1.json"),
                "package_sha256": prov_mf["sha256"],
                "members": len(prov_mf["package_members"]),
                "status": "PROVISIONAL_N1_EXECUTION — superseded, retained as engineering evidence",
            },
        },
    },

    # ── identities ───────────────────────────────────────────────────────────────────────────────
    "execution_identities": {
        "source_commit": SOURCE_COMMIT,
        "runtime_image": "mr002-research:v1.4",
        "network": "none",
        "frozen_thread_env": {
            "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1", "OPENBLAS_CORETYPE": "HASWELL",
        },
        "bound_source": {
            p: blob_sha(p) for p in (
                "apps/backend/app/research/mr002/n1/method.py",
                "apps/backend/app/research/mr002/n1/reference.py",
                "apps/backend/app/research/mr002/n1/seam.py",
                "apps/backend/scripts/mr002_n1_capture_corpus.py",
                "apps/backend/scripts/mr002_n1_census.py",
                "apps/backend/scripts/mr002_n1_equivalence.py",
                "apps/backend/scripts/mr002_n1_shuffle.py",
                "apps/backend/scripts/mr002_n1_c4c5.py",
                "apps/backend/scripts/mr002_n1_diff_v1.py",
                "apps/backend/scripts/mr002_n1_preservation.py",
                "apps/backend/scripts/mr002_n1_baseline_reconcile.py",
                "apps/backend/scripts/mr002_n1_provenance_fixtures.py",
            )
        },
    },

    "reproducibility_note": (
        "n1_census_rows.json (5.9 MB), n1_diff_v1.json and n1_equivalence.json carry IDENTICAL "
        "SHA-256 across the provisional and the formal executions — byte-identical reproduction "
        "across two independent runs and across the uncommitted -> committed code boundary."),

    "boundary": {
        "development_domain_only": True,
        "sealed_or_reference_bytes_read": 0,
        "validation_store_opened": False,
        "oos": "NOT AUTHORIZED",
        "N2": "NOT AUTHORIZED — requires its own grant",
    },
}

REC["record_identity_sha256"] = hashlib.sha256(_canonical(REC)).hexdigest()
out = os.path.join(_HERE, "MR002_N1_FinalVerdict_v1.0.json")
with open(out, "wb") as fh:
    fh.write(_canonical(REC))

print(json.dumps({
    "record": "MR002_N1_FinalVerdict_v1.0",
    "record_identity_sha256": REC["record_identity_sha256"],
    "disposition": REC["disposition"],
    "selected_solver_B": REC["selected_solver_B"],
    "binds_pre_ruling_verdict": pre["record_identity_sha256"],
    "source_commit": SOURCE_COMMIT,
    "s3_execution_package_sha256": exec_mf["sha256"],
}, indent=1))
