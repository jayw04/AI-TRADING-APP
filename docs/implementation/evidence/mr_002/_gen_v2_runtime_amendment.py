"""PROSPECTIVE dependency-runtime amendment for the Validation-2 opening.

Sealed BEFORE application, and NOT APPLIED. It proposes one narrow change: which dependency
bundle is mounted at the container's dependency path. It changes no source, no closure member,
no threshold, no solver and no image.

The question it answers is not "does boto3 import there". It is: "is deps_v12 behaviourally and
numerically INERT for the evaluator while closing the AWS import chain".
"""
from __future__ import annotations

import hashlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def _canonical(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


REC: dict = {
    "record_type": "MR002_Validation2_DependencyRuntimeAmendment",
    "version": "1.0",
    "date": "2026-08-20",
    "status": "PROSPECTIVE — SEALED, NOT APPLIED",
    "authorizes": "NOTHING. Applying the mount requires a separate owner ruling.",
    "scope": "the dependency bundle mounted at the container path /opt/mr002/deps. No source "
             "file, closure member, threshold, fold, solver, gate or image is touched.",
}

# ── identities ───────────────────────────────────────────────────────────────────────────────
REC["bundle_identities"] = {
    "algorithm": "sha256 over sorted '<sha256>  <relpath>' lines, __pycache__ and *.pyc "
                 "excluded as build residue",
    "currently_bound__opt_mr002_deps": {
        "identity_sha256":
            "ed95c15638213672c626898a013e8fa733c02e6893fc91ccfed0480e50f95cb2",
        "files": 3412,
        "status": "DEFECTIVE — cannot import boto3",
    },
    "candidate__opt_mr002_deps_v12": {
        "identity_sha256":
            "26e230493f218aba332b0888f2751def9f143ee136f68a86bdb91aaa03110dc1",
        "files": 2954,
        "status": "imports the full AWS chain cleanly",
    },
    "⛔ identity_not_directory_name": "the bundle is bound by CONTENT IDENTITY. 'deps_v12' is a "
                                     "path, and a path is not an identity.",
}

# ── what actually differs ────────────────────────────────────────────────────────────────────
REC["difference_analysis"] = {
    "every_shared_package_is_BYTE_IDENTICAL": {
        "boto3": "56/56 files identical", "botocore": "1991/1991 files identical",
        "s3transfer": "16/16 identical", "jmespath": "8/8 identical",
        "urllib3": "38/38 identical",
        "pyarrow": "758/758 files identical — this is the one shared package that touches the "
                   "DATA path (parquet decode), and it is byte-for-byte the same",
        "bin": "1/1 identical",
    },
    "gained_by_the_candidate": ["dateutil 2.9.0.post0 (19 files)", "six 1.17.0"],
    "lost_by_the_candidate": ["_pytest", "pytest", "pluggy", "iniconfig", "packaging", "py.py",
                              "pygments — i.e. test tooling only"],
    "why_the_loss_is_safe": "nothing in the 25-member execution closure imports pytest tooling, "
                            "and every suite still passes under the candidate.",
}

# ── the shadowing question, which is the real risk ───────────────────────────────────────────
REC["shadowing_analysis"] = {
    "why_it_matters": "the bundle is mounted on PYTHONPATH, which Python resolves BEFORE "
                      "site-packages. A package present in the bundle SHADOWS the image's copy. "
                      "That is the mechanism by which a bundle swap could move numerics, and it "
                      "is the thing that had to be checked rather than assumed.",
    "measured_resolution_of_every_numerical_package": {
        "numpy 2.2.6": "IMAGE in all three configurations",
        "scipy 1.18.0": "IMAGE in all three",
        "quadprog": "IMAGE in all three (compiled .so)",
        "piqp 0.6.3": "IMAGE in all three (compiled .so, avx2)",
        "duckdb 1.1.3": "IMAGE in all three",
        "pyarrow 20.0.0": "DEPS-MOUNT under both bundles — but the two pyarrow trees are "
                          "byte-identical, so the resolution changes nothing",
        "pandas": "ABSENT everywhere; the evaluator does not use it",
    },
    "the_one_real_change": {
        "package": "packaging",
        "before": "26.3, shadowed from /opt/mr002/deps",
        "after": "26.2, from the IMAGE — because the candidate drops the shadow",
        "assessed": "empirically inert; see the equivalence evidence below. It is reported "
                    "because it is a genuine difference, not because it had an effect.",
    },
    "conclusion": "the numerical stack that decides allocations, routing and gates comes from "
                  "the IMAGE, not from the bundle, under every configuration tested.",
}

# ── equivalence evidence ─────────────────────────────────────────────────────────────────────
REC["behavioural_equivalence_evidence"] = {
    "method": "the positive closed-latch rehearsal was run three times from the SAME deployed "
              "tree, changing ONLY the dependency mount.",
    "configurations": {
        "N": "no deps mount (image only)",
        "D": "/opt/mr002/deps — the currently bound bundle",
        "V": "/opt/mr002/deps_v12 — the candidate",
    },
    "behavioural_digest_all_three":
        "1e77f33c52dd3d6e8fbddd1aab192f32ee57e084a58cbc5f7756506a94058311",
    "⭐ stronger_than_the_digest": {
        "finding": "the ENTIRE report.json is BYTE-IDENTICAL across all three configurations",
        "report_sha256":
            "f2635353299fd677f6ff37748b823f17648018a5045b2e4f5187180218cc9b9b",
        "what_that_covers": "replay run hashes, materialization logical content identity, "
                            "allocation mechanics, Stage-3 routing census, fold handling, gate "
                            "behaviour, terminal semantics, custody ledger row hashes and the "
                            "DSR trial-dispersion input — all identical.",
    },
    "stage3_census_identical_under_D_and_V": {
        "A": "59 invocations, QUADPROG_SQRT, PRIMARY_QUALIFIED, 0 fallback, 0 stops",
        "B": "60 invocations, QUADPROG_SQRT, PRIMARY_QUALIFIED, 0 fallback, 0 stops",
        "C": "55 invocations, QUADPROG_SQRT, PRIMARY_QUALIFIED, 0 fallback, 0 stops",
        "all_reconcile_to_a_registered_disposition": True,
    },
    "suites_under_the_candidate": {
        "launcher_static_invariants": "20/20 PASS",
        "negative_matrix": "10/10 fail closed, reader_acquisition_attempted=False",
        "fold_gate_rehearsal": "ALL PASS",
        "governed_module_imports": "11/11 resolve",
    },
    "escalation_test": "the owner's condition was that ANY change in replay behaviour, routing, "
                       "allocation mechanics, gate behaviour or terminal semantics escalates "
                       "this to a numerical-runtime amendment. Byte-identical reports mean that "
                       "condition is not met: this is a dependency repair, not a numerical "
                       "change.",
}

# ── the pre-credential boundary probe ────────────────────────────────────────────────────────
REC["pre_credential_boundary_probe"] = {
    "purpose": "exercise the REAL S3 branch — production registry, production contract, journal, "
               "credential gate, `import boto3`, `boto3.client(\"sts\")` — and stop one line "
               "before acquire_reader_credentials.",
    "safeties": [
        "acquire_reader_credentials was replaced BEFORE the launcher imported it, so the real "
        "one was unreachable by the process",
        "the container ran with --network=none, so an escaped call could not have reached STS",
        "the latch remained 8/CLOSED throughout, which would have denied an assumption anyway",
    ],
    "under_the_CANDIDATE_deps_v12": {
        "reached_credential_boundary": True,
        "stopped_with": "the intentional probe sentinel",
        "read_events": 0,
        "journal": "run_opened then terminal FAILED — 2 rows, no read of any kind",
        "verdict": "PASS — the production branch can now reach the credential boundary",
    },
    "under_the_CURRENTLY_BOUND_deps": {
        "reached_credential_boundary": False,
        "stopped_with": "ModuleNotFoundError: No module named 'dateutil'",
        "read_events": 0,
        "verdict": "FAIL",
        "⭐ significance": "this is the blocker MEASURED on the production path rather than "
                          "inferred from an import test. It also confirms the cost model: the "
                          "journal shows terminal FAILED with ZERO reads, so the opening would "
                          "NOT have been consumed — but the latch release and its ~286s "
                          "propagation would have been spent to die on a missing package.",
    },
}

# ── the proposed change ──────────────────────────────────────────────────────────────────────
REC["proposed_amendment"] = {
    "change": "mount /opt/mr002/deps_v12 AT the container path /opt/mr002/deps, i.e. "
              "`-v /opt/mr002/deps_v12:/opt/mr002/deps:ro`",
    "⭐ requires_NO_host_filesystem_mutation": "the existing /opt/mr002/deps directory is left "
        "exactly as it is. Only the docker invocation changes. That keeps the defective bundle "
        "intact as an untouched rollback and makes the amendment reversible by editing one flag "
        "rather than by restoring a directory.",
    "explicitly_rejected_alternative": "overwriting or repointing /opt/mr002/deps in place. It "
                                       "destroys the rollback, mutates a bound runtime path, and "
                                       "buys nothing.",
    "bind_by": "content identity 26e230493f218aba332b0888f2751def9f143ee136f68a86bdb91aaa03110dc1, "
               "not by the directory name",
    "execution_package_text_to_correct": "ExecutionPackage v1.0/v2.0 state the bundle 'MUST be "
                                         "mounted at /opt/mr002/deps'. That remains true as the "
                                         "CONTAINER path; what must change is which host "
                                         "directory supplies it.",
}

REC["corroboration_not_proof"] = {
    "observation": "Validation-1's successful reads on 2026-08-19 postdate deps_v12's creation "
                   "on 2026-08-18.",
    "owner_instruction_followed": "treated as corroboration, NOT as identity proof. It is "
                                  "consistent with deps_v12 having been the working runtime, and "
                                  "it establishes nothing on its own. The equivalence evidence "
                                  "above is what carries the argument.",
}

REC["boundary"] = {
    "latch": "8 / CLOSED — never touched",
    "withheld_reads": 0,
    "successful_validation2_reads": 0,
    "opening_consumed": False,
    "validation_2_population": "UNCONSUMED",
    "amendment_applied": False,
    "host_filesystem_mutated": False,
    "validation_2_opening": "NOT AUTHORIZED",
}
REC["what_was_NOT_done"] = [
    "no bundle was modified, replaced, repointed or deleted",
    "the latch was not released",
    "no reader was assumed; no STS call was made",
    "no Validation-2 object was read at any version",
    "no source, closure member, threshold, fold, solver or image was changed",
]
REC["record_status"] = "SEALED"


def main() -> int:
    ident = hashlib.sha256(_canonical(REC)).hexdigest()
    REC["record_identity_sha256"] = ident
    out = os.path.join(_HERE, "MR002_Validation2_DependencyRuntimeAmendment_v1.0.json")
    tmp = out + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(_canonical(REC))
    os.replace(tmp, out)
    print("MR-002 VALIDATION-2 DEPENDENCY RUNTIME AMENDMENT v1.0 (PROSPECTIVE)")
    print(f"  identity          {ident}")
    print(f"  candidate bundle  "
          f"{REC['bundle_identities']['candidate__opt_mr002_deps_v12']['identity_sha256']}")
    print(f"  current bundle    "
          f"{REC['bundle_identities']['currently_bound__opt_mr002_deps']['identity_sha256']}")
    print("  equivalence       report.json BYTE-IDENTICAL across no-mount / deps / deps_v12")
    print("  boundary probe    PASS under candidate, FAIL under current")
    print(f"  applied           {REC['boundary']['amendment_applied']}")
    print(f"  wrote             {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
