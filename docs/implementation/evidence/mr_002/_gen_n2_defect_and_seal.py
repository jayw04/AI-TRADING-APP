"""MR-002 Gate N2 — stress-generator specification defect record + corrected-population seal.

Owner ruling 2026-08-19. The initial synthetic population is REJECTED as a GENERATOR SPECIFICATION
DEFECT, not as evidence that the frozen Stage-3 v2 method failed N2. One corrective amendment to the
generator is authorized; the corrected population must be SEALED BEFORE it is solved, or the
prospective problem is recreated.

This record is written and sealed while the corrected population is still UNSOLVED.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
OUT = os.path.join(REPO, ".mr002out", "n2")


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def blob_sha(path: str) -> str:
    o = subprocess.run(["git", "-C", REPO, "show", f"HEAD:{path}"], capture_output=True)
    return hashlib.sha256(o.stdout).hexdigest() if o.returncode == 0 else "UNCOMMITTED"


def worktree_lf_sha(path: str) -> str:
    with open(os.path.join(REPO, path), "rb") as fh:
        return hashlib.sha256(fh.read().replace(b"\r\n", b"\n")).hexdigest()


def file_sha(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


GEN = "apps/backend/scripts/mr002_n2_generate.py"
DERIVE = "apps/backend/scripts/mr002_n2_derive_scale_envelope.py"
QUAL = "apps/backend/scripts/mr002_n2_qualify.py"

envelope = json.load(open(os.path.join(OUT, "n2_scale_envelope.json")))
corrected = json.load(open(os.path.join(OUT, "n2_population.json")))
smoke = json.load(open(os.path.join(OUT, "n2_qualification_limit60.json")))

REC: dict = {
    "record_type": "MR002_N2_StressGeneratorDefect_AND_CorrectedPopulationSeal",
    "record_status": "SEALED_BEFORE_SOLVING",
    "version": "1.0",
    "program": "MR-002 / SPQ-1",
    "gate": "N2",
    "date": "2026-08-19",

    "authority": {
        "sealed_registration": {
            "record": "MR002_N1_ProspectiveRegistration_v1.0 §8",
            "identity_sha256": "7f8a56e34e6d5d36a3914ecb825de015debdc83ebae2967887e5e37ca3d684af",
        },
        "n1_final_verdict": "629eee0ee1c257a23312b539fbac8542b40cbf6f2cef296ba2c829fb6b29bd81",
        "n2_grant": "owner, 2026-08-19",
        "amendment_authority": (
            "owner ruling 2026-08-19: ONE corrective amendment to the population definition, "
            "authorized before the formal qualification. NOT permission to tune N2 until it passes."),
    },

    # ── the defect ───────────────────────────────────────────────────────────────────────────────
    "defect": {
        "classification": "N2_GENERATOR_SPECIFICATION_DEFECT",
        "method_verdict": "NONE",
        "n2_gate_state_at_discovery": "OPEN — qualification not executed",
        "n2_stop_entered": False,
        "adverse_finding_against_stage3_v2": False,
        "rejected_population_hash": "65a21933440be44111a1da3cbed8c1fdeeaf7297bd08d06a1c2d4fb1ac650d73",
        "mechanism": (
            "axis A1 was specified as a Hessian-conditioning sweep, kappa(H) = max(t)/min(t). The "
            "implementation drew a LOW anchor and multiplied UP by kappa, so conditioning and "
            "ABSOLUTE TARGET SCALE moved together. t reached 4.2e7 against a registered ceiling of "
            "1.71e-2 — nine orders of magnitude outside the economic domain, where t is an "
            "allocation weight capped at 1.5% of NAV by the frozen construction."),
        "why_it_failed_numerically": (
            "the registered signed-gap gate is an ABSOLUTE bound of 1e-10 while the objective "
            "f(z) = sum (z_i - t_i)^2 / t_i scales with t. At t ~ 1e7 the gate demands roughly 17 "
            "significant digits, beyond double precision. BOTH generators failed identically with "
            "SIGNED_LAGRANGIAN_GAP_LIMIT_EXCEEDED. That is a scale/tolerance mismatch, not solver "
            "fragility."),
        "axis_did_not_isolate_its_mechanism": True,
        "population_wide": {
            "instances_within_registered_scale": 84,
            "instances": 3000,
            "percent": 2.8,
            "A1_within_registered_scale": "0 of 400",
        },
        "controlled_experiment": {
            "design": "hold target scale fixed, sweep kappa; then vary scale",
            "at_registered_scale_t_max_1.5e-2": {"kappa_1e5": "12/12", "kappa_1e7": "12/12",
                                                 "kappa_1e9": "12/12"},
            "at_60x_scale": {"kappa_1e5": "12/12", "kappa_1e7": "12/12", "kappa_1e9": "12/12"},
            "at_6e4x_scale": {"kappa_1e5": "12/12", "kappa_1e7": "12/12", "kappa_1e9": "12/12"},
            "at_6e7x_scale": {"kappa_1e5": "6/12", "kappa_1e7": "6/12", "kappa_1e9": "9/12"},
            "conclusion": ("at the registered scale the method resolves kappa through 1e9 cleanly; "
                           "failures appear only at inflated scale and are largely INSENSITIVE to "
                           "kappa. The driver is target magnitude, not conditioning."),
        },
        "smoke_run_retained_as_engineering_evidence": {
            "instances": smoke["instances"],
            "disposition_recorded_by_the_script": smoke["disposition"],
            "owner_classification": "VOID as an N2 verdict; retained as defect evidence",
            "seven_unresolved_cases_are_NOT_numerical_failures_of": "QUADPROG_SQRT + PIQP_P2",
            "file_sha256": file_sha(os.path.join(OUT, "n2_qualification_limit60.json")),
        },
        "rejected_population_retained": {
            "stress_npz": file_sha(os.path.join(OUT, "stress_DEFECTIVE_65a21933.npz")),
            "population_json": file_sha(os.path.join(OUT, "n2_population_DEFECTIVE_65a21933.json")),
            "admissible_for_method_qualification": False,
        },
    },

    # ── the amendment ────────────────────────────────────────────────────────────────────────────
    "amendment": {
        "scope": "population definition only — ONE correction, applied before any solving",
        "scale_envelope_derivation": {
            "derived_mechanically_from": "the registered Stage-3 development corpus",
            "corpus_hash": envelope["authoritative_source"]["corpus_hash"],
            "record_identity_sha256": envelope["record_identity_sha256"],
            "T_MAX_REGISTERED": envelope["T_MAX_REGISTERED"],
            "T_MIN_REGISTERED": envelope["T_MIN_REGISTERED"],
            "T_MAX_REGISTERED_hex": envelope["T_MAX_REGISTERED_hex"],
            "not_typed_by_hand": ("the generator re-verifies this record's own identity at import; "
                                  "a hand-edited envelope aborts generation"),
        },
        "amended_structural_contract": {
            "absolute_scale_invariant": "0 < t_i <= T_MAX_REGISTERED, applied to ALL EIGHT AXES",
            "conditioning_stress_permitted_below_history": (
                "synthetic t_min MAY extend below T_MIN_REGISTERED solely to reach the preregistered "
                "kappa range, with kappa still bounded by 1e10"),
            "why_that_distinction_is_explicit": (
                "holding BOTH registered bounds reaches only kappa = "
                f"{envelope['consequence_for_A1']['kappa_reachable_holding_both_registered_bounds']:.4e}, "
                "so freezing t_min >= the development minimum would DELETE the stress axis A1 exists "
                "to perform. The economically meaningful missing invariant is the absolute UPPER "
                "scale."),
        },
        "deliberately_unchanged": [
            "seed 20260819", "population size 3,000", "eight axes and their counts",
            "A1 kappa sweep through the 1e10 ceiling", "Solver A = QUADPROG_SQRT",
            "Solver B = PIQP_P2", "PIQP_P2 profile including max_iter = 1000",
            "all certificate thresholds", "no third solver",
            "the N2 rule: 100% registered resolution or STOP",
        ],
        "principle": "stress changes INSTANCES, never solver profiles",
    },

    # ── the corrected population, sealed unsolved ────────────────────────────────────────────────
    "corrected_population": {
        "population_hash": corrected["population_hash"],
        "seed": corrected["seed"],
        "instances": corrected["instances"],
        "axes": corrected["axes"],
        "generator_revision": corrected["generator_revision"],
        "scale_envelope_identity": corrected["scale_envelope_identity"],
        "stress_npz_sha256": file_sha(os.path.join(OUT, "stress.npz")),
        "population_json_sha256": file_sha(os.path.join(OUT, "n2_population.json")),
        "structural_conformance": {
            "regeneration_byte_identical": True,
            "stratum_counts_correct": True,
            "instances": 3000,
            "t_max_within_ceiling": "3000/3000",
            "worst_t_max": 1.704025e-02,
            "kappa_range": [1.0e1, 5.0e9],
            "kappa_within_1e10": True,
            "contract_violations": 0,
            "checks_were_structural_only": "no instance was solved before this seal",
        },
        "solved_before_seal": False,
    },

    "generator_identities": {
        p: (blob_sha(p) if blob_sha(p) != "UNCOMMITTED" else worktree_lf_sha(p))
        for p in (GEN, DERIVE, QUAL)
    },
    "generator_identity_basis": (
        "Git blob where committed; LF-normalized working tree otherwise. The corrected generator is "
        "committed alongside this record."),

    "next_step": {
        "action": "run the full corrected 3,000 EXACTLY ONCE under the original N2 rule",
        "if_any_valid_in_domain_instance_is_unresolved": "that is the real N2_STOP",
        "explicitly_prohibited_thereafter": [
            "a second generator correction", "any tolerance adjustment", "solver substitution",
        ],
    },

    "boundary": {
        "development_domain_only": True,
        "sealed_or_reference_bytes_read": 0,
        "validation_store_opened": False,
        "oos": "NOT AUTHORIZED",
        "consumed_validation_opening": "unchanged",
    },
}

REC["record_identity_sha256"] = hashlib.sha256(_canonical(REC)).hexdigest()
out = os.path.join(_HERE, "MR002_N2_StressGeneratorDefect_v1.0.json")
with open(out, "wb") as fh:
    fh.write(_canonical(REC))

print(json.dumps({
    "record": "MR002_N2_StressGeneratorDefect_v1.0",
    "record_identity_sha256": REC["record_identity_sha256"],
    "rejected_population_hash": REC["defect"]["rejected_population_hash"],
    "corrected_population_hash": REC["corrected_population"]["population_hash"],
    "T_MAX_REGISTERED": REC["amendment"]["scale_envelope_derivation"]["T_MAX_REGISTERED"],
    "solved_before_seal": REC["corrected_population"]["solved_before_seal"],
}, indent=1))
