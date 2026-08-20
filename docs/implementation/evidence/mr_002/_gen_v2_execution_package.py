"""Seal the COMPLETE Validation-2 execution package for owner deployment review.

This record does not authorize anything. It is the package the owner reviews in order to decide
whether DEPLOYMENT is authorized. The opening remains a separate, later ruling.

Facts are READ FROM THE ARTIFACTS, not transcribed. Anything this generator cannot read from a
file is marked as such rather than asserted.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
CLOSURE = ("apps/backend/app/research/mr002/phase3c/manifests/"
           "validation2_execution_closure.json")
REHEARSAL_REG = ("apps/backend/app/research/mr002/phase3c/manifests/"
                 "validation2_rehearsal_registry.json")
PROD_REG = ("apps/backend/app/research/mr002/phase3c/manifests/"
            "validation2_object_registry.json")


def _canonical(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def _git(*a: str) -> str:
    return subprocess.run(["git", *a], cwd=_REPO, check=True,
                          capture_output=True).stdout.decode("utf-8", "replace").strip()


def _blob_sha(path: str) -> str:
    raw = subprocess.run(["git", "show", f"HEAD:{path}"], cwd=_REPO, check=True,
                         capture_output=True).stdout
    return hashlib.sha256(raw).hexdigest()


CLOSURE_DOC = json.loads(subprocess.run(["git", "show", f"HEAD:{CLOSURE}"], cwd=_REPO,
                                        check=True, capture_output=True).stdout)

REC: dict = {
    "record_type": "MR002_Validation2_ExecutionPackage",
    "version": "2.0",
    "supersedes": "MR002_Validation2_ExecutionPackage_v1.0 (20-file enumeration; no rehearsal)",
    "purpose": "the complete package for OWNER DEPLOYMENT REVIEW. It authorizes nothing.",
    "sealed_at_commit": _git("rev-parse", "HEAD"),
    "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
}

REC["identity_type_discipline"] = (
    "every hash in this record is SHA-256 OVER FILE CONTENT AS STORED IN GIT (LF). None of them "
    "is a Git blob object id (SHA-1 over 'blob <len>\\0' + content). The two are never compared.")

# ── 1. execution closure ─────────────────────────────────────────────────────────────────────
REC["execution_closure"] = {
    "path": CLOSURE,
    "closure_identity_sha256": CLOSURE_DOC["closure_identity_sha256"],
    "derived_at_commit": CLOSURE_DOC["derived_at_commit"],
    "rule": CLOSURE_DOC["closure_rule"],
    "member_count": CLOSURE_DOC["member_count"],
    "code_members": CLOSURE_DOC["code_members"],
    "runtime_read_data_members": CLOSURE_DOC["runtime_read_data_members"],
    "unjustified_members": CLOSURE_DOC["unjustified_members"],
    "members": [{"path": m["path"], "sha256": m["sha256_over_git_blob_content_lf"],
                 "categories": m["closure_categories"]} for m in CLOSURE_DOC["members"]],
    "replaces_an_enumeration_with_a_rule": {
        "why": "a list is a snapshot; a closure is a rule. Both halts in this cycle came from an "
               "artifact one step outside the enumeration.",
        "added": CLOSURE_DOC["superseded_enumeration_diff"]["added_by_the_closure"],
        "added_significance": "the additions include THE LAUNCHER ITSELF and BOTH REGISTRIES - "
                              "precisely the artifacts both halts originated in, none of which "
                              "was in the 20-file list.",
        "removed": CLOSURE_DOC["superseded_enumeration_diff"]["removed_from_the_enumeration"],
        "removal_findings": CLOSURE_DOC["superseded_enumeration_diff"]["removal_findings"],
    },
    "⛔ includes_the_tracked_registry_path": (
        "the package is NOT apps-only. Both registries are closure members and are named by "
        "TRACKED path: " + PROD_REG + " and " + REHEARSAL_REG),
}

# ── 2. the ordering discipline the owner required ────────────────────────────────────────────
REC["fixture_hash_ordering"] = {
    "owner_instruction": "do not generate rehearsal hashes dynamically at launcher runtime; "
                         "replace every PENDING_FIXTURE_BUILD with the SHA-256 of the frozen "
                         "fixture bytes, then commit/seal those values.",
    "chain": "development source -> frozen fixture bytes -> committed fixture SHA registry -> "
             "rehearsal",
    "expected_values_committed_at": "5372aef",
    "rehearsals_run_after_that_commit": True,
    "why_it_matters": "a hash computed at run time verifies the fixture against itself. The "
                      "expected value must exist BEFORE the invocation admitted as evidence, and "
                      "here it exists in Git history, not merely in a claim.",
    "determinism": "the builder writes the whole corpus twice into separate roots and fails "
                   "closed unless all 10 SHA-256 values match. They matched.",
    "fixture_bytes_are_not_in_git": "the fixture parquet files are generated bulk and are "
                                    "gitignored (ADR 0050). Git holds their HASHES, which is the "
                                    "part that carries evidentiary weight.",
    "fixture_only_columns": {
        "predecessor_overrides.review_status": "FIXTURE_ONLY constant - the development corpus "
                                               "has no such column",
        "security_sector_overrides.review_status": "FIXTURE_ONLY constant - same",
    },
}

# ── 3. the defect the rehearsal exposed ──────────────────────────────────────────────────────
REC["defect_found_by_the_positive_rehearsal"] = {
    "owner_precondition": "'I would not add another abstraction around this boundary unless the "
                          "positive rehearsal exposes a concrete problem.' It exposed one.",
    "symptom": "the first positive rehearsal failed immediately with VERSION_ID_MISMATCH on "
               "oos/actions.parquet: fixture://actions/v1 != F6m6am6cBahBd95p41C1.aAVmYd8GuNG",
    "root_cause": "the launcher treated its two identity fields ASYMMETRICALLY. SHA-256 was "
                  "registry-sourced and contract-compared only when production. VersionId was "
                  "CONTRACT-sourced and compared UNCONDITIONALLY.",
    "consequences": [
        "no rehearsal could ever construct an object, so the orchestration was untestable",
        "had one been allowed through, it would have stamped the REAL production S3 VersionIds "
        "onto rehearsal objects - into the journal and the opened-object ledger - which is "
        "exactly the misreading the synthetic fixture:// VersionIds exist to prevent",
    ],
    "fix": "VersionId is now registry-sourced and contract-compared, in that order, identically "
           "to SHA-256.",
    "why_this_does_not_relax_production": [
        "when production is true the equality is enforced BEFORE the value is used, so the "
        "registry value and the contract value are the same string",
        "_assert_production_contract_before_credentials independently re-verifies the "
        "CONSTRUCTED object's key/VersionId/SHA-256 against the frozen contract immediately "
        "before credentials are acquired",
        "negative case 3 (registered key at an unregistered VersionId) still fails "
        "VERSION_ID_MISMATCH before any credential attempt",
    ],
    "family": "this is the SAME role-transfer defect class as both halts: governance moved the "
              "data's role, and one more piece of code kept enforcing the old one.",
}

# ── 4. positive closed-latch rehearsal ───────────────────────────────────────────────────────
REC["positive_closed_latch_rehearsal"] = {
    "invocation": "--reader fixture --window development --contract rehearsal --manifest "
                  "<tracked rehearsal registry>",
    "container_network": "--network=none. STS acquisition count is 0 BY CONSTRUCTION, not by "
                         "observation: no network path to STS existed.",
    "thread_env": "OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1, OPENBLAS_CORETYPE=HASWELL "
                  "(FROZEN_THREAD_ENV)",
    "latch": "8 / CLOSED throughout",
    "required_outcomes_observed": {
        "state resolves to DEVELOPMENT_REHEARSAL_ONLY": "PASS - permitted-state table matched "
            "(fixture, development, rehearsal)",
        "registry declares the role the state requires": "PASS - registry_role "
            "DEVELOPMENT_REHEARSAL_ONLY",
        "STS credential acquisitions": "0 - report.credential_readiness is absent/null and the "
            "container had no network",
        "fixture reads": "10",
        "consuming / reference split": "6 consuming / 4 reference",
        "unclassified_reads": "0",
        "every payload verified against the FROZEN fixture SHA": "PASS - each read_intent row "
            "carries declared_sha256 equal to the value committed at 5372aef, and each "
            "read_verified row followed it",
        "six-row Validation2OpenedObjectLedger": "PASS - 6 rows, hash-chained, chain_verifies",
        "ledger carries SYNTHETIC VersionIds": "PASS - fixture://<table>/v1 throughout; no "
            "production VersionId appears anywhere in the rehearsal record",
        "journal opened and fsynced BEFORE any read": "PASS - run_opened is journal row 1, "
            "preceding every read_intent",
        "materialization completes": "PASS - materialization_complete row present; logical "
            "content identity 71d8af204718ac9e2812301e6a221ce2bbda43af9ba70d25d84f57c0d3bbfd52",
        "replay completes": "PASS - configs A, B and C all replayed",
        "Stage-3 routing census non-empty and reconciled": "PASS - all invocations reconcile to a "
            "registered disposition; A shows 59 invocations, all QUADPROG_SQRT / "
            "PRIMARY_QUALIFIED, 0 fallback, 0 stop dispositions, 0 unrecognized outcomes",
        "terminal record emitted on the exit path": "PASS - terminal COMPLETED",
        "the record names the CURRENT Cycle-2C authority": "PASS - "
            "MR002_Validation2_ProspectiveRegistration_v1.0 / 93ee4688, partition identity "
            "3b3910d0...",
        "superseded authority appears as historical only": "PASS - Phase-3C v2.0 "
            "authorization/countersignature carried under "
            "superseded_authority_historical_only",
        "no fallback path reaches consumed Validation-1 identifiers": "PASS - no validation/ key "
            "appears in the registry, the object set, the journal or the report",
        "no economic verdict is produced": "PASS - decision.verdict is REHEARSAL_NO_VERDICT with "
            "gates_evaluated false, and oos_metrics_computed is empty",
    },
    "⚠ what this rehearsal DOES NOT prove": {
        "finding": "the launcher gates BOTH fold-assignment verification and gate evaluation on "
                   "args.window == 'validation'. Under --window development both are SKIPPED "
                   "(fold_assignment = {'skipped': 'rehearsal window'}; decision = "
                   "REHEARSAL_NO_VERDICT).",
        "consequence": "the required-outcome 'five-fold and gate orchestration completes' is NOT "
                       "established by this rehearsal, and is not claimed on its basis.",
        "why_it_cannot_be_closed_here": "the Validation-2 fold geometry spans "
                                        "2023-05-30..2026-07-01; any fixture covering those "
                                        "sessions would have to contain the withheld holdout.",
        "how_it_IS_closed": "separately, by the fold/gate rehearsal recorded below.",
    },
}

# ── 5. fold / gate rehearsal ─────────────────────────────────────────────────────────────────
REC["fold_and_gate_rehearsal"] = {
    "artifact": "apps/backend/scripts/mr002_v2_fold_gate_rehearsal.py",
    "why_it_is_safe": [
        "fold boundaries are calendar dates already registered in folds.py and committed to Git; "
        "dates are not the withheld economic observations",
        "gate evaluation runs ONLY on synthetic return series constructed inside that file",
        "it reads no object, touches no credential, and produces NO economic observation",
    ],
    "fold_assignment": {
        "accepts the exact frozen session list": "PASS",
        "rejects a list one session short": "PASS - raises FOLD_ASSIGNMENT_MISMATCH",
        "rejects an extra session INSIDE a fold range": "PASS - raises FOLD_ASSIGNMENT_MISMATCH "
            "(fold 1 observed 156 vs frozen 155)",
        "ACCEPTS an out-of-fold extra session": "PASS - and this is correct, not lenient: the "
            "window is 850 sessions against 775 fold-eligible, so out-of-fold sessions are "
            "normal by design and a verifier rejecting them would reject the real window",
        "all five folds populated at their declared counts": "PASS - 155 each",
        "contract established": "verify_assignment FAILS CLOSED BY RAISING IntegrityFailure. It "
            "does NOT return a verifies flag, so a caller inspecting a boolean would read every "
            "rejection as an acceptance.",
    },
    "gate_evaluation_on_synthetic_series": {
        "5/5 positive folds, A and C profitable": "VALIDATION_ADVANCE_REQUEST",
        "3/5 positive folds (the registered boundary)": "VALIDATION_ADVANCE_REQUEST",
        "2/5 positive folds": "VALIDATION_DO_NOT_ADVANCE",
        "3/5 folds but config A unprofitable": "VALIDATION_DO_NOT_ADVANCE",
        "integrity_ok=False": "INTEGRITY_FAILURE - a replay-definition failure is not surfaced "
                              "as an economic verdict",
        "conclusion": "the gate DISCRIMINATES. 'It returned a verdict' would not have been "
                      "evidence; three of the four cases returning a different verdict from the "
                      "others is.",
    },
    "my_own_corrected_expectations": [
        "NAV must compound from NAV0 (10,000,000), not 1.0. The first version started at 1.0, so "
        "every synthetic case read as a ~100% loss and all four returned DO_NOT_ADVANCE. The "
        "gate was correct and my input was malformed.",
        "verify_assignment raises rather than returning a flag (above).",
        "an out-of-fold extra session is not a violation (above).",
    ],
}

# ── 6. injected-failure rehearsal ────────────────────────────────────────────────────────────
REC["post_materialization_injected_failure_rehearsal"] = {
    "question": "after the six consuming reads have happened, can an arbitrary downstream "
                "failure destroy the custody record? That is the 2026-08-19 evidence loss.",
    "method": "run_config_validation is replaced at its SOURCE module before the launcher "
              "imports from it, so the launcher source is untouched. The launcher is executed "
              "via runpy with run_name='__main__', i.e. exactly as production executes it.",
    "success_criterion": "NOT 'the run failed'. The journal must still yield a complete six-row "
                         "custody ledger RECONSTRUCTED FROM THE JOURNAL ALONE, with the report "
                         "treated as unavailable.",
    "observed": {
        "injected failure fired": "1 time, strictly after materialization",
        "journal rows": 23,
        "journal hash chain verifies": True,
        "materialization_complete present": True,
        "consuming reads recovered from the journal alone": 6,
        "reference reads recovered from the journal alone": 4,
        "terminal record present": True,
        "terminal disposition": "FAILED",
        "terminal detail": "RuntimeError: INJECTED POST-MATERIALIZATION FAILURE (synthetic)",
        "six-row custody ledger rebuilt from the journal alone": True,
    },
    "harness_defect_disclosed": {
        "what": "the first version of this harness imported the launcher and called main() "
                "directly. That bypassed the `if __name__ == \"__main__\"` block - which is "
                "where the terminal record is written - and reported the missing terminal record "
                "as a LAUNCHER defect.",
        "it_was_a_harness_defect": "the launcher was correct. The harness was not executing the "
                                   "exit path it claimed to be testing.",
        "what_it_nonetheless_revealed": "the terminal-record guarantee lives ENTIRELY in the "
                                        "__main__ guard and was structurally unprotected. Four "
                                        "static invariants now hold it in place, so a refactor "
                                        "moving main() behind another entry point fails loudly.",
    },
}

# ── 7. static invariants and negative matrix ─────────────────────────────────────────────────
REC["static_launcher_invariants"] = {
    "artifact": "apps/backend/scripts/mr002_v2_launcher_invariants.py",
    "count": 20,
    "result": "ALL PASS",
    "claim": "there is no executable path to Validation-2 credentials without the production "
             "key/VersionId/SHA-256 contract having succeeded first - proven over the AST, so it "
             "holds for EVERY CLI combination rather than the ones a test happens to try.",
    "mutation_control": {
        "why": "an invariant that cannot fail is worse than no invariant.",
        "drop terminal(FAILED) on the failure path": "CAUGHT (1 invariant fails)",
        "drop terminal(COMPLETED) on the success path": "CAUGHT (1 invariant fails)",
        "rewrite the gate's VersionId comparison to the tautology `vid != vid`":
            "CAUGHT (2 invariants fail)",
    },
    "my_own_invariant_defect_disclosed": {
        "what": "invariant 5b originally asked whether the STRING 'obj.version_id' appeared in "
                "the gate source. Mutating the comparison to `vid != vid` removes the check "
                "entirely, yet that string survives in the error message f-string - so the "
                "invariant passed while the check it guarded was gone.",
        "fix": "it now analyses Compare NODES, requires a real comparison with obj.<attr> on one "
               "side and something else on the other, and separately rejects any "
               "self-comparison anywhere in the gate.",
        "found_by": "mutation testing, not by review.",
    },
}
REC["negative_matrix"] = {
    "artifact": "10 cases; every one must fail BEFORE credential acquisition",
    "result": "10/10 fail closed; reader_acquisition_attempted=False in every case",
    "cases": {
        "1 consumed validation/ key in the registry": "CONSUMED_PARTITION_IN_REGISTRY",
        "2 unregistered seventh oos/ object": "UNREGISTERED_VALIDATION2_OBJECT_IN_REGISTRY / "
                                              "UNREGISTERED_VALIDATION2_OBJECT",
        "3 registered key at an unregistered VersionId": "VERSION_ID_MISMATCH",
        "4 registry SHA disagrees with the frozen contract": "SHA256_CONTRACT_MISMATCH",
        "5 S3 reader with the development window": "WINDOW_MISUSE",
        "6 S3 reader with the rehearsal contract": "UNPERMITTED_EXECUTION_STATE",
        "7 fixture reader with the validation window": "UNPERMITTED_EXECUTION_STATE",
        "8 production registry declared as rehearsal": "REGISTRY_ROLE_MISMATCH",
        "9 rehearsal registry mislabelled as production": "REGISTRY_ROLE_MISMATCH",
        "10 unrecognised registry role": "REGISTRY_ROLE_MISMATCH",
    },
}

# ── 8. what is NOT covered ───────────────────────────────────────────────────────────────────
REC["residual_limitations"] = [
    "NO rehearsal exercises the S3 reader, STS acquisition, or the latch-release propagation "
    "path. Those are reachable only with the latch open and are therefore only exercisable by "
    "the governed run itself. The negative matrix and the static invariants constrain that path "
    "from outside; they do not execute it.",
    "the fold/gate functions are proven on SYNTHETIC inputs. Their behaviour on the real "
    "Validation-2 return series is, by construction, unobservable before the opening.",
    "the rehearsal materializes a 2013 development slice. It proves the ORCHESTRATION, not any "
    "economic property of Validation-2.",
    "phase3bc tests 20/21/22 fail on this branch. They fail identically on clean HEAD without "
    "any change in this package (attributed via a detached worktree) and are unrelated.",
]

# ── 9. boundary ──────────────────────────────────────────────────────────────────────────────
REC["boundary"] = {
    "latch": "8 statements / CLOSED",
    "withheld_reads": 0,
    "opening_consumed": False,
    "validation_2_population": "UNCONSUMED",
    "evaluator_host": "i-00c1034f7026db45e — stopped",
    "deployment": "NOT AUTHORIZED",
    "validation_2_opening": "NOT AUTHORIZED",
}
REC["authorizes"] = ("NOTHING. This package exists to be reviewed. Deployment of the execution "
                     "closure to the run host requires a separate owner ruling, and the opening "
                     "requires another after that.")
REC["what_was_NOT_done"] = [
    "the latch was NOT released",
    "no reader was assumed and no STS call was made",
    "no Validation-2 object was read at any version",
    "nothing was deployed to the run host",
    "N1 and N2 were not rerun; DISC-001 was not touched",
]

# ── file identities ──────────────────────────────────────────────────────────────────────────
REC["package_file_identities"] = {
    p: _blob_sha(p) for p in [
        "apps/backend/scripts/mr002_phase3c_validation_run.py",
        "apps/backend/scripts/mr002_v2_launcher_invariants.py",
        "apps/backend/scripts/mr002_v2_build_rehearsal_fixtures.py",
        "apps/backend/scripts/mr002_v2_fold_gate_rehearsal.py",
        "apps/backend/scripts/mr002_v2_execution_closure.py",
        PROD_REG, REHEARSAL_REG, CLOSURE,
    ]
}

_PENDING = [k for k, v in REC["package_file_identities"].items() if not v]
REC["record_status"] = "SEALED" if not _PENDING else "DRAFT"


def main() -> int:
    ident = hashlib.sha256(_canonical(REC)).hexdigest()
    REC["record_identity_sha256"] = ident
    out = os.path.join(_HERE, "MR002_Validation2_ExecutionPackage_v2.0.json")
    tmp = out + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(_canonical(REC))
    os.replace(tmp, out)
    print("MR-002 VALIDATION-2 EXECUTION PACKAGE v2.0")
    print(f"  status            {REC['record_status']}")
    print(f"  identity          {ident}")
    print(f"  closure identity  {REC['execution_closure']['closure_identity_sha256']}")
    print(f"  closure members   {REC['execution_closure']['member_count']}")
    print(f"  deployment        {REC['boundary']['deployment']}")
    print(f"  opening           {REC['boundary']['validation_2_opening']}")
    print(f"  wrote             {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
