"""MR-002 Cycle 2C — VALIDATION-2 PROSPECTIVE REGISTRATION.

Freezes, BEFORE one withheld byte is read: the population and its role transfer, the pristine
proof, the transferred evaluation contract, the fold geometry, consumption and abort semantics, the
separation of numerical conformance from economic judgment, the dry-run requirement, custody, the
prospective new-OOS boundary, and the authority latch.

Authority: owner ruling 2026-08-20 granting Cycle 2C and deciding the population question
(Option 1 — the pristine former-OOS partition is redesignated Validation-2; future post-seal
accrual becomes the new OOS), standing on

  MR002_N1_FinalVerdict_v1.0   629eee0e...
  MR002_N2_Verdict_v1.0        27f98548...
  MR002_N3_FinalVerdict_v1.0   5a140280...

THIS RECORD AUTHORIZES NOTHING. It opens no data, reads no withheld economic observation, computes
no performance, and does not grant the opening. Its terminal disposition is a READINESS statement
for the owner, never an execution authorization.

⛔ THE GOVERNING PRINCIPLE, from the owner's grant:
   The next validation opening must be capable of producing a legitimate economic verdict even if a
   numerical component encounters an expected registered numerical termination. It must never again
   be consumed merely because infrastructure or numerical classification failed.

IDENTITIES bind by PUSHED Git blob, never the Windows working tree (CRLF fail-closes an LF deploy).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
REV = "HEAD"
E = "docs/implementation/evidence/mr_002/"
S = "apps/backend/scripts/"
M = "apps/backend/app/research/mr002/"
R = "docs/review/mr002/"
PENDING: list[str] = []

N1 = "629eee0ee1c257a23312b539fbac8542b40cbf6f2cef296ba2c829fb6b29bd81"
N2 = "27f98548067b3017870937c22196212e5bb1b11fdbd6a961a329f85f82aae471"
N3 = "5a14028024a1f78ca60ebeb174b5ecd7b8a3e1f5027f8768ec93b6f2a8195ec4"
PREREG = "b2a042d4cf8e4d36a70d7e087c3d0e8efc1076e3ee96db7d6c2dc7583129af9c"
SEAL_DATE = "2026-08-20"
BUCKET = "workbench-mr002-sealed-219024422756"


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def blob_sha(path: str) -> str:
    out = subprocess.run(["git", "-C", REPO, "show", f"{REV}:{path}"], capture_output=True)
    if out.returncode != 0:
        raise SystemExit(f"not committed, cannot bind by Git blob: {path}")
    return hashlib.sha256(out.stdout).hexdigest()


def bound(path: str) -> dict:
    return {"path": path, "file_blob_sha256": blob_sha(path), "enforced": True}


def bind_or_pending(path: str, why: str) -> dict:
    out = subprocess.run(["git", "-C", REPO, "show", f"{REV}:{path}"], capture_output=True)
    if out.returncode == 0:
        return {"path": path, "file_blob_sha256": hashlib.sha256(out.stdout).hexdigest(),
                "enforced": True}
    PENDING.append(path)
    rec = {"path": path, "enforced": False, "pending_reason": why}
    if os.path.exists(os.path.join(REPO, path)):
        with open(os.path.join(REPO, path), "rb") as fh:
            rec["worktree_lf_sha256"] = hashlib.sha256(fh.read().replace(b"\r\n", b"\n")).hexdigest()
    else:
        rec["status"] = "NOT YET WRITTEN AT REGISTRATION TIME"
    return rec


def head_is_pushed() -> tuple[bool, str, str]:
    def rev(ref: str) -> str:
        o = subprocess.run(["git", "-C", REPO, "rev-parse", ref], capture_output=True, text=True)
        return o.stdout.strip() if o.returncode == 0 else ""
    head = rev("HEAD")
    br = subprocess.run(["git", "-C", REPO, "rev-parse", "--abbrev-ref", "HEAD"],
                        capture_output=True, text=True).stdout.strip()
    return (bool(head) and head == rev(f"origin/{br}")), head, rev(f"origin/{br}")


_pushed, _head, _remote = head_is_pushed()

# The six objects, by the identities recorded at SEAL time and independently re-confirmed live.
V2_OBJECTS = [
    {"table": "actions", "key": "oos/actions.parquet",
     "version_id": "F6m6am6cBahBd95p41C1.aAVmYd8GuNG", "bytes": 57069,
     "sha256": "a08c0ed6ba6c6609e67c501a938e0245277e11c82f3d7242e7e2683790acb100"},
    {"table": "anchors", "key": "oos/anchors.parquet",
     "version_id": "RsJZG3TkDXvNPERJhZVanJ.Vqg8_dulw", "bytes": 177252,
     "sha256": "5095149d39d26c7af19de3814a7178e93bf3cc3ab87f92512991a81e64013dc9"},
    {"table": "etf_prices", "key": "oos/etf_prices.parquet",
     "version_id": "Z3OsUeuucMYIl2v9JDoVNDx1nw.0avDj", "bytes": 67010,
     "sha256": "f53f448312f94820d76aad80f378a53ea2b9104654cbb7c69bb82363b2a5da15"},
    {"table": "prices", "key": "oos/prices.parquet",
     "version_id": "1ope9PR._oR303.EbZNGPVlIJRy.SZbA", "bytes": 16173068,
     "sha256": "0f45ddc58170bd1131b9820576080eae861dff65b716bc3f03d08fb284f29e9a"},
    {"table": "sic_observations", "key": "oos/sic_observations.parquet",
     "version_id": "DPhtWW3Pca3TKtSa1LOnGKA.yrZ98EIt", "bytes": 138814,
     "sha256": "176a84bc155b5ec8c24444e091b19a78b97c0d31c0da606f22eca44ace7e12cf"},
    {"table": "universe", "key": "oos/universe.parquet",
     "version_id": "0gaqJ9TuECc3U_zar99sqls2UHRDnkkY", "bytes": 111278,
     "sha256": "4c1a2b2e876f7ffdd1f651e5c99079d5fe045e74003af556c3c8b3273d746e0d"},
]
PARTITION_IDENTITY = hashlib.sha256(
    _canonical({"objects": sorted(V2_OBJECTS, key=lambda o: o["key"])})).hexdigest()


REG: dict = {
    "record_type": "MR002_VALIDATION2_PROSPECTIVE_REGISTRATION",
    "version": "1.0",
    "program": "MR-002 Sector-Neutral Residual Reversion",
    "cycle": "2C — prospective Validation-2 design and registration",
    "date": SEAL_DATE,

    "authorizes": "NOTHING. This record opens no data, reads no withheld economic observation, "
                  "computes no performance, and does not grant the Validation-2 opening. Its "
                  "terminal disposition is a READINESS statement for the owner.",

    "governing_principle": (
        "The next validation opening must be capable of producing a legitimate economic verdict "
        "even if a numerical component encounters an expected registered numerical termination. It "
        "must never again be consumed merely because infrastructure or numerical classification "
        "failed."
    ),

    "authority_chain": {
        "owner_grant": {
            "date": "2026-08-20",
            "instrument": "owner message granting Cycle 2C and ruling the population question",
            "population_ruling": "Option 1 APPROVED — the pristine former-OOS partition is "
                                 "redesignated Validation-2; future post-seal accrual becomes the "
                                 "new OOS. A role reassignment made prospectively before any read, "
                                 "NOT a reuse of consumed validation data.",
        },
        "N1": {"record": "MR002_N1_FinalVerdict_v1.0", "identity_sha256": N1},
        "N2": {"record": "MR002_N2_Verdict_v1.0", "identity_sha256": N2},
        "N3": {"record": "MR002_N3_FinalVerdict_v1.0", "identity_sha256": N3},
        "governing_preregistration": {"record": "MR002_ValidationOOS_Preregistration_v1.0.4",
                                      "sha256": PREREG},
    },

    # ── 1. why Validation-1 is gone, stated plainly ─────────────────────────────────────────────
    "validation_1_is_permanently_inadmissible": {
        "partition": {"start": "2019-10-03", "end": "2023-02-16", "sessions": 850},
        "finding": "NOTHING of it remains untouched — not a residual, not a sub-window.",
        "evidence": {
            "declared_sealed_objects": 6,
            "objects_read": 6,
            "source": "MR002_Phase3C_ReconstructedExecutionCustodyEvidence_v1.0 "
                      "(8218ad62f1cb358fbb96782a85378c92570cfd8f50b004365bd91431f767ba1d): "
                      "sealed_reads 6 of 6 expected, every sealed VersionId matching the package",
            "materialized_artifact": {
                "path": "/opt/mr002/work/validation.duckdb", "bytes": 14430208,
                "sha256": "c4cabab228e7824144036afde09f5c949d9dea6144eb0b24d41e1fcad0856c82"},
            "consumed_at": "2026-08-19T12:54:46Z (first sealed validation read)",
        },
        "against_the_two_tests": {
            "physically_unread": "FALSE — all six objects were downloaded",
            "logically_unconsumed": "FALSE — materialized into a queryable database and replayed "
                                    "over",
        },
        "ledger_loss": "the ValidationOpenedObjectLedger was never persisted and CANNOT be "
                       "recreated (EXECUTION_EVIDENCE_NOT_DURABLE), so row-level bounding is "
                       "unavailable. It is moot: object-level exposure was total.",
        "status": "CONSUMED — permanently inadmissible as a holdout. DO NOT REOPEN.",
    },

    # ── 2. the role transfer ────────────────────────────────────────────────────────────────────
    "role_transfer": {
        "what_changes": "the OOS ROLE is RETIRED for the 2023-02-17 .. 2026-07-10 partition. Those "
                        "exact six objects become the Validation-2 population.",
        "what_does_not_change": "not one byte. This is a custody-role reassignment, not a data "
                                "change, and it changes none of the economic gate mathematics.",
        "made_prospectively": True,
        "made_before_any_read": True,
        "⛔ not_a_rename": "this record does NOT rename a Validation-1 artifact and does NOT imply "
                          "the underlying bytes are the same. Validation-1's identifiers refer to "
                          "objects under validation/ that are consumed. Validation-2 binds the six "
                          "objects under oos/ by their own keys, VersionIds and SHA-256s, under a "
                          "new partition identity.",
        "new_oos_role": "assigned to prospective post-seal accrual, defined below.",
    },

    # ── 3. the population, bound exactly ────────────────────────────────────────────────────────
    "validation_2_population": {
        "bucket": BUCKET,
        "prefix": "oos/",
        "prefix_note": "the S3 prefix keeps its historical name. The prefix string is a storage "
                       "path, not the governing role; the role is set by THIS record. Renaming "
                       "objects would change their VersionIds and destroy the pristine chain, "
                       "which is a far worse outcome than a stale-looking prefix.",
        "window": {"start": "2023-02-17", "end": "2026-07-10", "sessions": 850},
        "session_list_sha256":
            "54e8d1f11e8934a3482e5eeae651fb83aaf6974a75e63c52f7eee9d986c79003",
        "objects": V2_OBJECTS,
        "object_count": 6,
        "total_bytes": sum(o["bytes"] for o in V2_OBJECTS),
        "partition_identity_sha256": PARTITION_IDENTITY,
        "partition_identity_basis": "sha256 over the canonical JSON of the six objects sorted by "
                                    "key, each carrying table, key, VersionId, bytes and SHA-256",
        "provenance_of_the_hashes": {
            "record": "MR002_SealedStoreUploadManifest_v1.0",
            "identity_sha256": "3834ba8068b0c12bce49a8f65b772f4bc271833f2b90a612d37e40d74587de8d",
            "method": "each object was uploaded with its SHA-256 already verified against the P6 "
                      "content commitment, and S3 recomputed it server-side on the received "
                      "bytes. No object was read back.",
            "every_object_server_validated": True,
        },
    },
}

# ── 4. pristine proof ──────────────────────────────────────────────────────────────────────────
REG["pristine_proof"] = {
    "claim": "no successful governed read of any of the six Validation-2 objects has ever occurred",
    "record": "MR002_OOSPartitionAccessHistory_v1.0",
    "history_identity_sha256":
        "edb50634f3651bcb1e600f0b060e72eb4999e783b06be48b0e3f0aa2f3b1652c",
    "producer": {"path": "scripts/mr002_custody/oos_pristine_proof.py",
                 "reuses": "the audited CloudTrail collection and hash-chain code of "
                           "scripts/mr002_custody/seal_verification.py, by import",
                 "touches": "only the CloudTrail log bucket. It never opens the sealed store, "
                            "never issues GetObject against any partition prefix, and never reads "
                            "a snapshot. Reading the log of who read what is not reading the data."},
    "observed": {
        "oos_successful_reads": 0,
        "oos_denied_or_errored_read_attempts": 7,
        "total_events_naming_the_sealed_store": 106,
        "hash_chain_rows": 106,
        "hash_chain_verifies": True,
        "scan_window": "2026-08-11 .. 2026-08-20 (CloudTrail data-event days)",
    },
    "denied_attempts_fully_attributed": {
        "1_on_2026-08-11": "pre-existing HeadObject from the Phase-3C run host; matches the "
                           "oos_read_attempts_denied=1 already recorded in "
                           "ValidationPartitionAccessHistory_v1.1",
        "6_on_2026-08-20": "SELF-DISCLOSED — the Cycle-2C investigation's own HeadObject metadata "
                           "probes while pinning object identities for this registration. All "
                           "DENIED. HeadObject returns metadata, not content, so nothing was "
                           "exposed; identities were taken from the seal-time upload manifest and "
                           "cross-checked with ListObjectVersions instead.",
        "significance": "the deny latch on the Validation-2 prefix is ACTIVELY IN FORCE, not "
                        "merely assumed. It was tested by accident and held.",
    },
    "objects_unchanged_since_sealing": {
        "method": "ListObjectVersions compared against the seal-time upload manifest",
        "live_versions": 6, "delete_markers": 0, "extra_versions": 0,
        "every_version_id_matches_seal_time_manifest": True,
        "every_byte_length_matches": True,
        "meaning": "no object has been replaced, overwritten or deleted since it was sealed, so "
                   "the SHA-256 recorded at upload still describes the bytes that would be read",
    },
    "coverage_limitation": "CloudTrail data events were enabled on the sealed bucket BEFORE any "
                           "partition object was written, so no object has ever sat in this store "
                           "unlogged. The claim is scoped to the SEALED STORE. The earlier period, "
                           "when the corpus existed only as a DuckDB file on the developer "
                           "workstation, has no store-level access log and none can be "
                           "manufactured; that period rests on the procedural seal recorded in "
                           "preregistration v1.0.4 (sealed_data_read=false), which is a weaker "
                           "basis and is deliberately NOT restated here as if it were audited.",
}

# ── 5. the epistemic limitation, stated and not papered over ───────────────────────────────────
REG["epistemic_limitation"] = {
    "statement": "Validation-2 is machine-pristine but historically elapsed. Its economic "
                 "observations have never been read from the governed sealed corpus, as "
                 "established by custody/access evidence, but the calendar period itself is known "
                 "to analysts. Consequently Validation-2 is a genuine withheld historical "
                 "validation test, not prospective forward validation.",
    "what_it_does_NOT_claim": "epistemic equivalence to future data",
    "why_recorded_prominently": "the whole value of a holdout is that nobody has adapted to it. "
                                "Machine custody proves the corpus was not READ; it cannot prove "
                                "that no human knows what 2023-2026 markets did. Claiming "
                                "otherwise would be the kind of overstatement this program exists "
                                "to prevent.",
    "how_it_is_remedied": "by the new OOS, which is defined prospectively below and is genuinely "
                          "temporally unknowable at registration.",
    "resulting_hierarchy": [
        "development 2013-01-02..2019-10-02 — used for development, N1 and N3",
        "consumed Validation-1 2019-10-03..2023-02-16 — inadmissible forever",
        "Validation-2 2023-02-17..2026-07-10, 850 sessions, former OOS, ZERO governed reads "
        "before redesignation",
        "new OOS — prospective sessions after the Cycle-2C seal, never observable at registration",
    ],
}

# ── 6. exactly what transfers, and what gets a new identity ────────────────────────────────────
REG["transfer_inventory"] = {
    "rule": "enumerate. Nothing transfers by implication.",
    "transfers_without_modification": {
        "sample_size_850_sessions": True,
        "eligibility_rule": "formation_exclude_sessions=69, realization_horizon_governing=6, on "
                            "registered session ORDINALS, not calendar-day arithmetic",
        "fold_rule": "5 contiguous non-overlapping nearly-equal partitions of the eligible "
                     "sessions; any remainder to the FINAL fold",
        "fold_geometry": "5 x 155, zero remainder — DERIVED below, not assumed",
        "configs": {"validation": ["A", "B", "C"], "oos_candidate": "B only"},
        "economic_hypotheses": True,
        "gates_and_thresholds": True,
        "cost_and_execution_treatment": True,
        "borrow_locate_model": True,
        "stage_3_method": "v2 certificate-driven cascade, unchanged",
        "solver_A": "QUADPROG_SQRT",
        "solver_B": "PIQP_P2",
        "advance_and_rejection_semantics": True,
    },
    "receives_a_NEW_identity": {
        "partition_object_set": "the six oos/ objects, bound by their own keys, VersionIds and "
                                "SHA-256s under partition_identity_sha256 above",
        "fold_date_literals": "Validation-1's literal fold dates (2020-01-13..2023-02-08) are "
                              "SPECIFIC TO THE CONSUMED PARTITION and DO NOT transfer. "
                              "Validation-2's folds are bound by ordinal below and their date "
                              "labels are emitted by the reader at open time.",
        "run_id": "MR002-VALIDATION2 (Validation-1's run_id MR002-SPQ1-VALIDATION-V1 is retired)",
        "access_history": "MR002_OOSPartitionAccessHistory_v1.0, a new record, not a renamed one",
        "structural_manifest": "a Validation-2 structural preflight must be produced against the "
                               "oos window before opening; Validation-1's is not reusable",
    },
    "explicitly_does_NOT_transfer": [
        "the consumed Validation-1 object identities under validation/",
        "the Validation-1 literal fold dates",
        "any Validation-1 execution package, countersignature or authorization",
        "the lost ValidationOpenedObjectLedger, which never existed in durable form",
    ],
}

# ── 7. fold geometry, derived from the transferred rule ────────────────────────────────────────
REG["fold_geometry"] = {
    "derivation": "850 window sessions - 69 formation-excluded - 6 realization-horizon = 775 "
                  "scoring-eligible. 775 / 5 = 155 per fold, zero remainder. Identical geometry to "
                  "Validation-1 by arithmetic, not by assumption.",
    "window_sessions": 850,
    "formation_exclude_sessions": 69,
    "realization_horizon_governing": 6,
    "eligible_sessions": 775,
    "folds": 5,
    "sessions_per_fold": 155,
    "remainder": 0,
    "bound_by_ORDINAL_not_date": {
        "why": "the seam rule is already defined on registered session ordinals rather than "
               "calendar-day arithmetic. Binding by ordinal fixes the folds completely NOW, "
               "without inventing date literals and without reading one session date out of the "
               "sealed partition.",
        "eligible_ordinal_range": [70, 844],
        "fold_ordinals": [{"fold": i + 1, "first_ordinal": 70 + i * 155,
                           "last_ordinal": 70 + i * 155 + 154} for i in range(5)],
        "date_labels": "emitted by the reader at open time from the window session list, and "
                       "recorded in the opening record BEFORE any economic evaluation",
    },
    "fail_closed": "if the observed window does not yield exactly 850 sessions reproducing "
                   "session_list_sha256, or the eligible count is not exactly 775, or any fold is "
                   "not exactly 155, the run terminates as an integrity stop BEFORE economic "
                   "evaluation. A silently short fold would move the 3-of-5 verdict.",
}

# ── 8. the frozen evaluation contract, copied mechanically with provenance ─────────────────────
REG["frozen_evaluation_contract"] = {
    "rule": "COPIED MECHANICALLY from the governing artifacts. No reinterpretation, no new "
            "threshold, no threshold selected using Validation-2 results.",
    "provenance": {
        "governing_preregistration": {"record": "MR002_ValidationOOS_Preregistration_v1.0.4",
                                      "sha256": PREREG},
        "decision_specification": {
            "record": "MR002_Phase3A_ValidationStageDecisionSpecification_v1.0",
            "sha256": "8f67ec3002b43096c1e2e161d96b5df4d64bd4b683fae8260b67df4fd8313533"},
        "run_specification": "ValidationRunSpecification_v1.0 (fold and seam rule)",
        "metric_specification": "ValidationMetricSpecification_v1.0",
        "cost_execution_specification": "ValidationCostExecutionSpecification_v1.0",
        "borrow_model": "ShortBorrowLocateModelSpecification_v1.0",
    },
    "allowed_verdicts": ["VALIDATION_ADVANCE_REQUEST", "VALIDATION_DO_NOT_ADVANCE",
                         "VALIDATION_INCONCLUSIVE", "INTEGRITY_FAILURE"],
    "advance_conditions_ALL_required": [
        "every validation integrity gate passes",
        "Config B net-positive in >= 3 of 5 folds",
        "Configs A and C each cumulative net return > 0",
        "no post-validation tuning requested",
    ],
    "PASS": "VALIDATION_ADVANCE_REQUEST — all four advance conditions met. This authorizes a "
            "REQUEST for separate OOS authorization. It does NOT open the new OOS and evaluates "
            "no OOS gate.",
    "REJECT": "VALIDATION_DO_NOT_ADVANCE — the economic gates were evaluated on an admissible run "
              "and at least one failed.",
    "INCONCLUSIVE": {
        "genuinely_allowed": True,
        "meaning": "VALIDATION_INCONCLUSIVE is a member of the frozen verdict domain and is "
                   "retained. It is NOT a discretionary escape hatch: it may be returned only "
                   "where the frozen metric specification itself defines an indeterminate result "
                   "on an otherwise admissible run.",
        "⛔": "it may NEVER be used to avoid recording a REJECT, and never to describe an "
             "integrity or numerical fault, which is what INTEGRITY_FAILURE is for.",
    },
    "INTEGRITY_STOP": "INTEGRITY_FAILURE — the run is not admissible. gates_evaluated=false. An "
                      "integrity stop is NEVER reported as VALIDATION_DO_NOT_ADVANCE, which would "
                      "falsely imply the economic gates ran and failed.",
    "no_generic_owner_discretion": "there is no 'owner decides after seeing results' branch. The "
                                   "four conditions above are binding and deterministic.",
    "diagnostics_cannot_change_the_verdict": {
        "DIAGNOSTIC_ONLY": ["pbo_cscv", "concentration", "directional_coherence"],
        "rule": "reported but cannot independently change the advancement verdict. No "
                "discretionary red-flag test may be introduced after Validation-2 is observed.",
    },
    "oos_only_metrics_PROHIBITED_during_validation_2": [
        "net_oos_sharpe_ge_0.70", "net_oos_calmar_ge_0.75", "net_annualized_return_ge_0.03",
        "net_max_drawdown_le_0.15", "dsr_significance_ge_0.95_N5",
        "one_sided_95pct_bootstrap_lower_bound_daily_mean_net_return_gt_0",
        "cost_stress_profitable_20bps_300bps", "severe_cost_30bps_1000bps",
        "breadth_trades_ge_500_entrydates_ge_100_long_ge_100_short_ge_100",
        "annual_herfindahl", "annual_profile_min_3_positive_years_largest_le_0.50",
        "trade_concentration_single_le_0.10_top10_le_0.20",
        "positive_pnl_regime_concentration", "regime_gates_2of3_trend_positive_no_vol_sharpe_lt_-0.5",
        "expected_L10_bootstrap_sensitivity", "frictionless_short_attribution",
        "diversifier_tier_tag",
    ],
    "prohibition_note": "evaluating any of the above on Validation-2 is a preregistration breach, "
                        "exactly as it would have been on Validation-1. Redesignating the "
                        "partition does not move a metric from the OOS stage to the validation "
                        "stage.",
}

# ── 9. numerical conformance is SEPARATE from economic judgment ────────────────────────────────
REG["separation_of_conformance_from_judgment"] = {
    "why": "this is the central lesson of the consumed opening. A numerical fault was translated "
           "into a terminal outcome that produced no economic verdict at all, and the single "
           "opening was spent on it.",
    "the_evaluator_MUST_emit_two_logically_distinct_outputs": {
        "OUTPUT_1_numerical_execution_conformance": {
            "fields": ["all_required_instances_resolved", "no_integrity_defect",
                       "runtime_identity_correct", "source_identity_correct",
                       "evidence_complete", "stage3_invocation_count",
                       "unregistered_termination_reasons"],
            "domain": ["CONFORMANT", "NON_CONFORMANT"],
            "note": "a registered numerical termination (for example an iteration limit that the "
                    "v2 method classifies as NO_CERTIFIED_CANDIDATE with a registered reason) is "
                    "an EXPECTED outcome and does NOT by itself make the run non-conformant. That "
                    "is precisely the fragility class N2 qualified away.",
        },
        "OUTPUT_2_economic_validation_verdict": {
            "domain": ["VALIDATION_ADVANCE_REQUEST", "VALIDATION_DO_NOT_ADVANCE",
                       "VALIDATION_INCONCLUSIVE", "NOT_EVALUATED"],
            "note": "NOT_EVALUATED is returned when and only when conformance failed. It is not a "
                    "verdict; it is the explicit absence of one.",
        },
    },
    "combination_rule": {
        "CONFORMANT + economic verdict": "the verdict stands as the result of the opening",
        "NON_CONFORMANT": "the economic verdict is NOT_EVALUATED and the terminal record is "
                          "INTEGRITY_FAILURE",
    },
    "⛔ forbidden_translations": [
        "a numerical fault reported as an economic failure",
        "an economic miss obscured by an infrastructure state",
        "an integrity stop recorded as VALIDATION_DO_NOT_ADVANCE",
        "a conformance failure recorded as VALIDATION_INCONCLUSIVE",
    ],
    "if_execution_becomes_invalid": {
        "the_record_must_state_explicitly": ["whether the opening is consumed",
                                             "under what conditions another execution is "
                                             "permissible"],
        "default": "if any withheld economic observation was exposed before the invalidity, the "
                   "opening IS consumed and another execution requires a NEW prospective "
                   "governance decision by the owner. There is no automatic re-run.",
    },
}

# ── 10. consumption and abort semantics ────────────────────────────────────────────────────────
REG["consumption_semantics"] = {
    "consumed_at": "the FIRST successful exposure of ANY withheld economic observation to the "
                   "authorized evaluator — not at completion of the run.",
    "why_first_exposure": "it removes the 'partial peek, repair, rerun' ambiguity entirely. A run "
                          "that read one session and then crashed has still seen withheld data.",
    "mechanically_instrumented": {
        "boundary_marker": "a single, explicit, durable transition written BEFORE the first byte "
                           "of any Validation-2 object is delivered to the evaluator",
        "artifact": "ValidationOpenedObjectLedger, appended and FSYNCED per object, not "
                    "serialized at the end of a successful run",
        "⛔ the_defect_this_fixes": "the consumed opening's launcher serialized its report only "
                                   "after a successful replay, so the ledger was never written and "
                                   "was lost when replay raised. For a consumed one-time opening, "
                                   "evidence MUST survive the very failures it documents.",
    },
    "pre_read_technical_abort_does_NOT_consume": {
        "rule": "if a precondition fails BEFORE any withheld economic byte is exposed, the opening "
                "remains UNOPENED and may be attempted again after the precondition is fixed.",
        "qualifying_preconditions": ["source identity verification", "runtime/image identity",
                                     "dependency identity", "manifest verification",
                                     "KMS / credential access", "IAM latch state",
                                     "structural preflight", "fold-geometry verification",
                                     "dry-run qualification currency"],
        "instrumented_boundary": "the ledger's first entry IS the boundary. No ledger entry means "
                                 "no exposure means not consumed. An entry means consumed.",
        "fail_closed": "if it cannot be determined whether exposure occurred, the opening is "
                       "treated as CONSUMED. Ambiguity resolves against us, never for us.",
    },
    "no_adhoc_retry_after_exposure": {
        "once_the_first_withheld_observation_is_read_these_are_FORBIDDEN": [
            "source changes", "environment changes", "threshold edits",
            "solver or profile changes", "evaluator edits", "fix and rerun",
        ],
        "consequence": "any such requirement means the opening is CONSUMED and a new prospective "
                       "governance decision by the owner is required before another opening.",
    },
}

# ── 11. execution freeze ───────────────────────────────────────────────────────────────────────
REG["execution_freeze"] = {
    "stage_3_method": "the N1/N2/N3-qualified v2 certificate-driven cascade, unchanged",
    "solver_A": "QUADPROG_SQRT",
    "solver_B": "PIQP_P2",
    "max_iter": 1000,
    "no_solver_selection_in_validation_2": True,
    "frozen_thread_env": {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                          "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
                          "OPENBLAS_CORETYPE": "HASWELL"},
    "network": "none for the evaluator; the reader is the ONLY component permitted network access, "
               "and only to the sealed store and KMS",
    "identity_checks_required_before_any_read_ALL_fail_closed": [
        "evaluator source identity — every module bound by pushed Git blob SHA-256",
        "runtime image identity — digest, not tag",
        "dependency identity — the image's own pinned lock report",
        "numeric runtime identity — BLAS/LAPACK variant and thread environment",
        "sealed object identity — key + VersionId + SHA-256 for all six, verified on read",
        "structural preflight — window sessions, fold geometry, schema identity",
        "research-plane isolation — see isolation_dependency below",
    ],
    "isolation_dependency": {
        "requirement": "any research-plane / order-path isolation check the Validation-2 harness "
                       "depends upon MUST be VERSION-CONTROLLED and HASH-BOUND before the opening.",
        "why": "the two ADR-0051 invariant scripts are currently UNTRACKED and have never been "
               "committed, so they exist at no commit and cannot be bound. Depending on an "
               "untracked local script for a fail-closed control is not a control.",
        "scope_note": "this is recorded as a Validation-2 PRECONDITION, not as a coupling to the "
                      "separate ADR-0051 governance work item. If the harness ends up depending on "
                      "no such script, this precondition is satisfied vacuously and that must be "
                      "stated rather than assumed.",
    },
}

# ── 12. the invariant inherited from the N3 harness defect ─────────────────────────────────────
REG["n3_derived_harness_invariant"] = {
    "invariant": "A validation run with ZERO or UNEXPECTED Stage-3 invocation count MUST terminate "
                 "as INVALID_TEST_HARNESS before any economic verdict is produced.",
    "bound_explicitly_here": True,
    "why_not_inherited_by_assumption": "N3's routing_guard protects the N3 differential only. "
                                       "Nothing makes a future validation runner inherit it. "
                                       "Assuming inheritance is how the guard silently fails to "
                                       "exist where it matters most.",
    "origin": "the N3 build captured the solver handle BEFORE entering the routing context, "
              "silently un-routing every arm and producing a FALSE all-identical PASS. The only "
              "tell was an empty Stage-3 disposition census.",
    "required_behaviour": {
        "raises": True,
        "not_a_recorded_flag": "a guard that records a flag would not have stopped the N3 defect; "
                               "it must abort",
        "checks": ["Stage-3 census is non-empty",
                   "census row count equals the observed invocation count",
                   "invocation count is within the registered expectation for the run",
                   "the frozen v2 pair was actually routed, evidenced by the census disposition "
                   "vocabulary"],
        "terminal_state": "INVALID_TEST_HARNESS",
        "ordering": "evaluated BEFORE any economic gate is computed",
    },
    "expected_invocation_count_for_validation_2": {
        "status": "NOT PREDICTABLE FROM DEVELOPMENT — the Stage-3 invocation count is a property "
                  "of the data and cannot be known before the window is replayed.",
        "registered_form": "the guard therefore binds a LOWER BOUND and a structural relationship "
                           "rather than a literal count: invocations > 0, census rows == "
                           "invocations, and at least one invocation per scoring-eligible session "
                           "that reaches Stage-3. A literal expected count invented now would be "
                           "a fabricated threshold.",
        "⛔": "do NOT substitute the development counts (A 1427 / B 1535 / C 933). Those describe "
             "a different window.",
    },
}

# ── 13. dry-run requirement ────────────────────────────────────────────────────────────────────
REG["dry_run_requirement"] = {
    "rule": "the ENTIRE Validation-2 mechanism must be executed against an admissible "
            "NON-VALIDATION surrogate before the opening is granted.",
    "surrogate": "the development-domain corpus, which is already fully used and carries no "
                 "withheld economic content",
    "must_prove": [
        "reader can read ONLY the authorized object set",
        "publisher CANNOT read the sealed store",
        "reader CANNOT write governing evidence",
        "publisher CANNOT alter raw input",
        "source and runtime hashes bind correctly and fail closed on mismatch",
        "Stage-3 census is non-empty and the v2 pair was actually routed",
        "evidence files are produced and are durable across a mid-run failure",
        "S3 read-back by pinned VersionId works",
        "the verdict generator can produce EVERY terminal state",
    ],
    "negative_controls_required": {
        "rule": "at least one negative-control fixture PER TERMINAL PATH. A path that has never "
                "been observed to fire is not known to work.",
        "terminal_paths": ["VALIDATION_ADVANCE_REQUEST", "VALIDATION_DO_NOT_ADVANCE",
                           "VALIDATION_INCONCLUSIVE", "INTEGRITY_FAILURE",
                           "INVALID_TEST_HARNESS", "PRE_READ_ABORT_NOT_CONSUMED"],
    },
    "currency": "the dry-run qualification must be current for the bound source. If any bound "
                "source identity changes after qualification, the qualification is STALE and the "
                "opening precondition is not met.",
}

# ── 14. custody, frozen before opening ─────────────────────────────────────────────────────────
REG["custody"] = {
    "frozen_before_opening": True,
    "⛔": "no 'we will arrange custody after the run'. The consumed opening lost its ledger "
         "precisely because evidence handling was left until after success.",
    "model": "the pattern proven by N1, N2 and N3",
    "raw_and_large_outputs": "versioned S3, pinned by VersionId + SHA-256, read back and "
                             "re-verified, fail-closed on mismatch",
    "governing_verdict_and_manifest": "Git",
    "raw_output_immutable": True,
    "durability_rule": "the opened-object ledger and the execution evidence must be written and "
                       "flushed AS THEY HAPPEN, so they survive the failures they document",
    "bucket": "workbench-backups-219024422756",
    "object_key_prefix": "artifacts/governed/mr002-validation2-execution-evidence/1.0/",
}

# ── 15. the new OOS, defined prospectively NOW ─────────────────────────────────────────────────
REG["new_oos_definition"] = {
    "role": "the OOS role is reassigned to prospective post-seal accrual",
    "accrual_begins": "the FIRST eligible market session under the governing calendar STRICTLY "
                      "AFTER this registration is sealed",
    "boundary_is_mechanical": "determined by the calendar, not chosen. It is NOT 'after "
                              "Validation-2 finishes' and NOT selected after observing market "
                              "behaviour.",
    "seal_date": SEAL_DATE,
    "independence": "the new-OOS boundary is deliberately independent of whatever Validation-2 "
                    "reports, so the OOS start cannot be influenced by the validation outcome.",
    "data_remains_sealed_and_unread_while_it_accumulates": True,
    "opening": "NOT AUTHORIZED. The new OOS requires its own separate grant, after and distinct "
               "from any Validation-2 opening grant.",
    "why_this_is_stronger": "unlike Validation-2, the new OOS is temporally unknowable at "
                            "registration, so it carries none of the elapsed-calendar limitation "
                            "recorded above.",
    "not_yet_specified_here": "the new OOS sample LENGTH, its fold geometry and its accrual "
                              "machinery are NOT registered by this record. They require their own "
                              "prospective registration before that opening. Registering them now, "
                              "against data that does not exist and a pipeline that has not been "
                              "built, would be fabrication.",
}

# ── 16. the authority latch ────────────────────────────────────────────────────────────────────
REG["authority_boundary"] = {
    "cycle_2c_may_conclude_in_exactly_one_of": ["VALIDATION2_READY_FOR_OWNER_OPENING_GRANT",
                                                "VALIDATION2_NOT_READY"],
    "⛔ cycle_2c_MUST_NOT_open_validation_2": True,
    "the_opening_requires": "a SEPARATE explicit owner grant, issued after reviewing the sealed "
                            "registration and the dry-run qualification record",
    "this_record_is_not_execution_authorization": True,
}
REG["boundary"] = {
    "validation_2_opening": "NOT AUTHORIZED",
    "validation_2_economic_bytes_read": 0,
    "oos": "PROHIBITED",
    "validation_1": "CONSUMED — permanently inadmissible",
    "stage_3_pair": "FROZEN — QUADPROG_SQRT + PIQP_P2",
    "consumed_original_opening": "unchanged",
    "development_domain_only_for_all_cycle_2c_execution": True,
}
REG["what_this_record_does_NOT_establish"] = [
    "that MR-002 has economic merit — Validation-2 has not been read",
    "that Validation-2 will produce a verdict",
    "epistemic equivalence between Validation-2 and prospective data",
    "the new OOS sample length or fold geometry, which are deliberately unregistered",
]


# ── bindings ───────────────────────────────────────────────────────────────────────────────────
REG["identity_basis"] = {
    "head": _head, "remote_head": _remote, "head_is_pushed": _pushed,
    "rule": "a Git-blob identity is only a PUSHED identity once HEAD has reached the remote branch",
}
REG["bound_sources"] = {
    "gate_authority": [
        bound(E + "MR002_N1_FinalVerdict_v1.0.json"),
        bound(E + "MR002_N2_Verdict_v1.0.json"),
        bound(E + "MR002_N3_FinalVerdict_v1.0.json"),
    ],
    "frozen_method": [
        bound(M + "n1/method.py"), bound(M + "n1/seam.py"), bound(M + "n1/reference.py"),
    ],
    "evaluation_contract": [
        bound(R + "phase3a/MR002_Phase3A_ValidationStageDecisionSpecification_v1.0.json"),
        bound(R + "phase3a/ValidationRunSpecification_v1.0.json"),
        bound(R + "phase3a/ValidationMetricSpecification_v1.0.json"),
        bound(R + "phase3a/ValidationCostExecutionSpecification_v1.0.json"),
        bound(R + "phase3a/ShortBorrowLocateModelSpecification_v1.0.json"),
    ],
    "population_provenance": [
        bound(R + "phase3bc/MR002_SealedStoreUploadManifest_v1.0.json"),
        bound(R + "phase3bc/MR002_ValidationStructuralManifest_v1.0.json"),
    ],
    "consumed_opening_evidence": [
        bound(E + "MR002_Phase3C_ValidationExecutionOutcome_v1.0.json"),
        bound(E + "MR002_Phase3C_ReconstructedExecutionCustodyEvidence_v1.0.json"),
        bound(E + "MR002_Phase3C_ValidationExecutionPackage_v2.2.json"),
    ],
    "pristine_proof_producer": [
        bind_or_pending("scripts/mr002_custody/oos_pristine_proof.py",
                        "written during Cycle 2C; binds on the commit that tracks it"),
        bound("scripts/mr002_custody/seal_verification.py"),
    ],
}
REG["pending_bindings"] = sorted(PENDING)
REG["record_status"] = "SEALED" if (not PENDING and _pushed) else "DRAFT"
REG["sealing_requirement"] = ("this record is DRAFT while any binding is non-enforced. Sealing "
                              "re-derives every binding from PUSHED Git and re-emits the identity.")


def main() -> int:
    body = {k: v for k, v in REG.items() if k != "record_identity_sha256"}
    ident = hashlib.sha256(_canonical(body)).hexdigest()
    body["record_identity_sha256"] = ident
    out = os.path.join(_HERE, "MR002_Validation2_ProspectiveRegistration_v1.0.json")
    tmp = out + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(_canonical(body))
    os.replace(tmp, out)

    print("MR-002 CYCLE 2C — VALIDATION-2 PROSPECTIVE REGISTRATION")
    print(f"  identity            {ident}")
    print(f"  status              {body['record_status']}")
    print(f"  head                {_head} pushed={_pushed}")
    print(f"  partition identity  {PARTITION_IDENTITY}")
    print(f"  population          {REG['validation_2_population']['window']['start']} .. "
          f"{REG['validation_2_population']['window']['end']}  "
          f"{REG['validation_2_population']['window']['sessions']} sessions, 6 objects, "
          f"{REG['validation_2_population']['total_bytes']:,} B")
    print(f"  folds               5 x {REG['fold_geometry']['sessions_per_fold']} "
          f"(eligible {REG['fold_geometry']['eligible_sessions']}, remainder "
          f"{REG['fold_geometry']['remainder']})")
    print(f"  pristine            {REG['pristine_proof']['observed']['oos_successful_reads']} "
          f"successful reads, {REG['pristine_proof']['observed']['oos_denied_or_errored_read_attempts']}"
          f" denied attempts (all attributed)")
    print(f"  pending             {REG['pending_bindings'] or 'none'}")
    print(f"  wrote               {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
