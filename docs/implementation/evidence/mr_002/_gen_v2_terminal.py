"""MR-002 Validation-2 — the TERMINAL record of the consumed opening.

The conditionally authorized opening of 2026-08-21 ran both stages. Gate 11's live half CLOSED
(6/6 pinned-version metadata-only HEAD probes), the content sequence began immediately in the same
latch cycle, all six sealed objects were read and VERIFIED against their registered SHA-256
commitments -- and the frozen Stage-3 cascade then fail-closed on an unregistered numerical status
during the replay.

    Stage3Stop: INVALID_RUN: fallback integrity defect:
    UNREGISTERED_EXCEPTION:RuntimeError:status Status.PIQP_MAX_ITER_REACHED

Validation-2 is CONSUMED. The terminal disposition is an INTEGRITY / NOT-EVALUATED failure. It is
NOT VALIDATION_DO_NOT_ADVANCE: an integrity stop is never an economic verdict. No economic
statistic was produced -- the run never reached the stage that writes one.

This record authorizes nothing and requests nothing.
"""
from __future__ import annotations

import hashlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def _canonical(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


REC: dict = {
    "record_type": "MR002_Validation2_TerminalOutcome",
    "version": "1.0",
    "date": "2026-08-21",
    "authority": "owner ruling 2026-08-21 — conditional two-stage opening, AUTHORIZED",
    "terminal_disposition": "INTEGRITY FAILURE / NOT EVALUATED",
    "is_not": "VALIDATION_DO_NOT_ADVANCE. An integrity stop is never an economic verdict. The "
              "gates were never evaluated and no economic statistic exists.",
    "validation_2": "CONSUMED",
}

REC["binds"] = {
    "readiness_v5_0": "e914a4f4f891a5a166287dd1f6425964b94ab2746f623ac742cfaa1224fd2630",
    "pre_read_failure_of_the_first_attempt":
        "d1303229a26b80ac5b02255e0c81211d02a296cff9151464635b71ac071f5059",
    "resource_policy_amendment_R_bucket_policy":
        "7bb73e62066e52303c5d48ed0cd740cb16b4f2825110dde92d9cc4d6dfc164a5",
    "amendment_A_v1_2": "d7b5cf2be0d4523967ff63d121341572c3b111ac5085e04f9c4a7a2b4e25eedd",
    "dependency_amendment": "12877b32704da2bf4e13cd60599b194789a28d7da4ff9b97584b140ec0f3f86d",
    "mounted_bundle_identity":
        "26e230493f218aba332b0888f2751def9f143ee136f68a86bdb91aaa03110dc1",
    "mounted_bundle_files": 2954,
    "execution_package": "e22c4d4f9e1007340d7c30385af0ee6a95c0c0be8a1a8cd8b4a4e8140c832d23",
    "deployment_artifact": "aab2e7a56acf8dcc15e12e5345110c92e0ab43f04cbafe2e5380c359738e4b93",
    "deployed_live_aggregate":
        "6841756f8026932370531fde49de5dfccda1c2cee964174f1eec1901e3660ae9",
    "execution_closure": "3c32bda64dd1cd6efe306bcf7e69e56a78c53b3bd58076d7735ddbe2d516df3b",
    "launcher": "12b1a0c4899d79a54322664ec82b2c9193b32212891eb59e61caf15f4ad9ce3a",
    "production_registry": "bbd330b7a41e338353ebd061707b5f633937e0cc82cdd97b794e72021657ae2e",
    "head_authorization_probe":
        "448804f139da29a58587a39a335c4c6df5b2d6a404d797f466631bc0433c1bd3",
    "image": "mr002-research:v1.4",
    "image_config_digest":
        "sha256:770553aeae6c3d47f1735f61a4e0df75515c105ddda0431dcc2a07b8bdbfe4b6",
    "host": "i-00c1034f7026db45e",
    "source_commit": "740a1420ad55c2c2cb74c681fd49b1da2f3c11b2",
}

REC["pre_release_identities"] = {
    "verdict": "ALL TWELVE MATCHED immediately before the 8->7 mutation",
    "on_host_qualification": "14/14, result document sha256 "
                             "0b035f179173d0feb8430be2cd237f80b02767b1415564f96e2b38323a0a9b81 — "
                             "BYTE-IDENTICAL to both earlier runs today, across two host "
                             "stop/start cycles",
    "latch_before": "8 statements, canonical 44f5549a..., Deny present, and DENIED behaviourally "
                    "from inside the bound runtime",
    "successful_validation2_content_reads_before": 0,
}

# ── STAGE 1 — gate 11 live half ──────────────────────────────────────────────────────────────
REC["stage_1_gate_11_live"] = {
    "verdict": "CLOSED — TRUE",
    "instrument_sha256": "448804f139da29a58587a39a335c4c6df5b2d6a404d797f466631bc0433c1bd3",
    "instrument_unmodified": "the probe was run EXACTLY as bound by the ruling. Its identity was "
                             "verified against the Git blob and against the host-side copy before "
                             "release.",
    "reader_caller_identity": "arn:aws:sts::219024422756:assumed-role/mr002-validation-reader/"
                              "mr002-v2-head-authorization-probe",
    "credential_attempts": 1,
    "denied_before_success": 0,
    "elapsed_since_release_seconds": 19.9,
    "probes": "6/6 authorized",
    "echoed_version_id_matches_request": True,
    "content_length_matches_registry": True,
    "content_calls": 0,
    "read_verified_rows": 0,
    "body_bytes": 0,
    "sha256_commitments_verified_by_the_probe": False,
    "independent_recheck": "a second, separate check re-parsed the probe report and required all "
                           "twelve stated conditions before the content stage could start. The "
                           "runner used `set -e`, so a failing probe would have aborted BEFORE "
                           "stage 2 rather than relying on a judgement call.",
    "significance": "this is the first MR-002 opening in which the LIVE resource-policy "
                    "authorization decision was an explicit gate rather than a residual "
                    "assumption. It passed, and it would have caught the 2026-08-21 morning "
                    "defect on the safe side of the consumption boundary.",
}

# ── STAGE 2 — the content opening ────────────────────────────────────────────────────────────
REC["stage_2_content_opening"] = {
    "latch_state_changed_between_stages": False,
    "one_continuous_latch_cycle": True,
    "container_started_utc": "2026-08-21T14:26:19.816515594Z",
    "container_finished_utc": "2026-08-21T14:28:11.708383596Z",
    "exit_code": 1,
    "first_successful_content_read_utc": "2026-08-21T14:26:21Z",
    "consuming_reads": 6,
    "reference_reads": 4,
    "unclassified_reads": 0,
    "materialization": "COMPLETE — all ten objects opened, journal row 22",
    "six_commitments_verified_against_bytes": True,
    "how_that_is_known": "S3PinnedReader.read calls obj.verify(payload), which RAISES on "
                         "mismatch, before returning. JournalingReader emits read_verified only "
                         "after that returns, and each row carries reader_verification=PASSED "
                         "alongside the intent row's declared_sha256 (the registered commitment) "
                         "and the byte count. Verification is structural, not asserted.",
    "objects": [
        {"key": "oos/actions.parquet", "version_id": "F6m6am6cBahBd95p41C1.aAVmYd8GuNG",
         "bytes": 57069, "reader_verification": "PASSED"},
        {"key": "oos/anchors.parquet", "version_id": "RsJZG3TkDXvNPERJhZVanJ.Vqg8_dulw",
         "bytes": 177252, "reader_verification": "PASSED"},
        {"key": "oos/etf_prices.parquet", "version_id": "Z3OsUeuucMYIl2v9JDoVNDx1nw.0avDj",
         "bytes": 67010, "reader_verification": "PASSED"},
        {"key": "oos/prices.parquet", "version_id": "1ope9PR._oR303.EbZNGPVlIJRy.SZbA",
         "bytes": 16173068, "reader_verification": "PASSED"},
        {"key": "oos/sic_observations.parquet", "version_id": "DPhtWW3Pca3TKtSa1LOnGKA.yrZ98EIt",
         "bytes": 138814, "reader_verification": "PASSED"},
        {"key": "oos/universe.parquet", "version_id": "0gaqJ9TuECc3U_zar99sqls2UHRDnkkY",
         "bytes": 111278, "reader_verification": "PASSED"},
    ],
}

# ── the terminal failure ─────────────────────────────────────────────────────────────────────
REC["terminal_failure"] = {
    "where": "inside the frozen A/B/C replay, at "
             "joint_portfolio.build_joint -> stage3_route._routed_solve_qp",
    "exception": "app.research.mr002.stage3_route.Stage3Stop",
    "message": "INVALID_RUN: fallback integrity defect: "
               "UNREGISTERED_EXCEPTION:RuntimeError:status Status.PIQP_MAX_ITER_REACHED",
    "mechanism": "the frozen cascade routed a Stage-3 instance to its single registered fallback, "
                 "PIQP_P2, which returned PIQP_MAX_ITER_REACHED. That status is not a member of "
                 "the cascade's NUMERICAL_ALLOWLIST, so it was classified UNREGISTERED_EXCEPTION "
                 "-> INTEGRITY_DEFECT -> Stage3Stop, and the replay stopped.",
    "this_is_the_control_working": "the cascade is deliberately keyed to one exact registered "
                                   "exception and treats every unrecognised numerical outcome as "
                                   "an integrity defect rather than silently accepting it. It "
                                   "refused to certify a solution it could not certify. That is "
                                   "the designed behaviour, not a malfunction.",
    "which_config": "NOT DETERMINED. The traceback does not name the configuration, the report "
                    "that would carry the per-config census was never written, and the run may "
                    "not be repeated against this population. It is left unstated rather than "
                    "inferred from timing.",
    "stage3_invocation_census": "NOT AVAILABLE. The census is assembled into the execution "
                                "report, which the run never reached. This is recorded as a gap "
                                "in the evidence, not reconstructed.",
    "execution_report_written": False,
    "economic_statistics_produced": "NONE. Not by the run, not into any file, and none was read "
                                    "at any point.",
    "gates_evaluated": False,
    "folds_evaluated": False,
    "what_it_says_about_the_method": "the frozen numerical pair could not certify at least one "
                                     "Stage-3 instance arising in the Validation-2 population. "
                                     "The development window exercised the fallback only four "
                                     "times in 3,895 solves and never hit this status. That is a "
                                     "finding about the frozen method on a population that is now "
                                     "consumed. It is stated as a finding; what to do about it is "
                                     "an owner decision, not a repair to be made here.",
}

REC["prohibited_and_not_done"] = {
    "retry": "NOT DONE. The failure occurred AFTER the first successful content read, so "
             "Validation-2 is consumed and there is no retry of any kind.",
    "solver_substitution": "NOT DONE and PROHIBITED.",
    "widening_the_allowlist": "NOT DONE and MUST NOT BE PROPOSED as a fix here. The cascade is "
                              "deliberately keyed to one exact registered exception; widening it "
                              "to swallow PIQP_MAX_ITER_REACHED would be post-freeze "
                              "accommodation — changing the acceptance rule after seeing the "
                              "instance that failed it, on the very population being evaluated.",
    "code_repair_against_the_same_population": "NOT DONE and PROHIBITED.",
    "second_latch_opening": "NOT DONE. One release, one restore.",
    "inspection_of_partial_output": "NOT DONE. The run produced no economic output to inspect, "
                                    "and nothing was read beyond integrity metadata.",
}

REC["latch_cycle"] = {
    "released_at_utc": "2026-08-21T14:25:58Z",
    "released_epoch": 1787322358.791,
    "open_proven_behaviourally_utc": "2026-08-21T14:26:08Z",
    "propagation_seconds_observed": 10,
    "restored_at_utc": "2026-08-21T14:26:51Z",
    "restored_epoch": 1787322411.763,
    "restored_immediately_after": "materialization_complete — the required read. The replay needs "
                                  "no further credentials, and the launcher makes exactly one "
                                  "AssumeRole and never calls again, so restoring at that point "
                                  "shortens the exposure without affecting the run.",
    "closed_proven_behaviourally_utc": "2026-08-21T14:27:10Z",
    "total_open_window_seconds": 53,
    "canonical_after_restore":
        "44f5549a97042d2829a3027e764105b0ab272774ec3bb343d224bfba999fab48",
    "restore_document_provenance": "the exact document captured at release was re-applied; it was "
                                   "never reconstructed.",
    "reader_sessions_during_the_cycle": [
        "mr002-v2-propagation-probe — the behavioural OPEN proof",
        "mr002-v2-head-authorization-probe — gate 11 live half, zero content",
        "mr002-p3c-validation-v1 — the governed content sequence",
    ],
    "all_sessions_are_the_same_governed_reader": True,
    "unrelated_principals_introduced": 0,
}

REC["durable_evidence"] = {
    "content_journal": {
        "sha256": "994e47581981c1f4a2d295fae1e55f548e09ee64882b6b54834a98c3e447be51",
        "bytes": 11375, "rows": 23, "chain_verifies": True,
        "chain_head": "6e27cef56d4b290d0007968c8043ef7cd7bb2e380fc6b7f6f23944364fa31fbb",
        "read_verified_rows": 10, "consuming": 6, "reference": 4,
        "terminal": "FAILED",
        "s3_version_id": "qHdL0aH00a5kXe3Oma2ksLKG5E9r1n0j"},
    "head_probe_journal": {
        "sha256": "4115a1ebe5f3954856074acdc950e9841d2fbb2f00ddad334127500e4ff6b6b8",
        "s3_version_id": "Ur7RT5Om.XUjSRvgkdY6kF2Rto9536Mo"},
    "head_probe_report": {
        "sha256": "2b076bf16957aca1de9aec409faf3b01eb26a43d3e00da7f8a2ada2fb0249baa",
        "s3_version_id": "N.R3VEvUbQW1w96OrOwvPW6yJN3USFvC"},
    "terminal_stderr": {
        "sha256": "cb30228ca0c5f29d707f63762f42b167389a4b45791988bc78a1606c114daddb",
        "s3_version_id": "aaPdGWbmQuLJWtHpzNY267hlXnCvISny"},
    "publication_path": "s3://workbench-backups-219024422756/mr002/publish-staging/validation2/"
                        "2026-08-21-cycle2/ — the evaluator host's only sanctioned S3 write",
    "all_read_back_by_pinned_version_id_and_byte_verified": True,
    "materialized_database": "/opt/mr002/stage/v2open/cycle2/validation2.duckdb on the host, "
                             "13,905,920 B. It holds the materialized Validation-2 tables and is "
                             "therefore CONSUMED-POPULATION DATA; it is deliberately NOT "
                             "published to Git.",
}

REC["access_history_proof"] = {
    "source": "CloudTrail S3 data events for the sealed store, re-scanned after delivery",
    "confirmed": True,
    "oos_successful_metadata_only_heads_all_time": 6,
    "oos_successful_content_reads_all_time": 6,
    "sequence_observed": [
        "14:26:18Z — six HeadObject, one per registered key, each at its registered VersionId, "
        "session mr002-v2-head-authorization-probe, all successful",
        "14:26:21-22Z — six GetObject, one per registered key, each at its registered VersionId, "
        "session mr002-p3c-validation-v1, all successful",
    ],
    "no_other_oos_access_in_the_window": True,
    "ordering": "the authorization probe precedes every content read in the authoritative access "
                "log, which is the independent proof that the gate ran FIRST rather than being "
                "asserted after the fact.",
    "agreement": "the access log, the hash-chained journal, the materialized database and the "
                 "container stderr all agree.",
}

REC["final_state"] = {
    "latch": "8 / CLOSED, canonical 44f5549a..., proven behaviourally at 2026-08-21T14:27:10Z",
    "validation_2": "CONSUMED",
    "successful_validation2_content_reads": 6,
    "opening_consumed": True,
    "reader_publisher_separation": "unchanged",
    "host": "stopped",
    "terminal_economic_disposition": "NONE — integrity / not-evaluated terminal failure",
    "paper_activation": "NOT AUTHORIZED",
    "production_activation": "NOT AUTHORIZED",
    "further_openings": "there is no further Validation-2 opening. The population is consumed.",
}

REC["authorizes"] = ("NOTHING. It records a consumed opening that terminated on an integrity "
                     "stop. Any next step for MR-002 requires a fresh owner ruling and, since "
                     "Validation-2 is spent, a different population.")

if __name__ == "__main__":
    ident = hashlib.sha256(_canonical(REC)).hexdigest()
    REC["record_identity_sha256"] = ident
    out = os.path.join(_HERE, "MR002_Validation2_TerminalOutcome_v1.0.json")
    tmp = out + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(_canonical(REC))
    os.replace(tmp, out)
    print("MR002_Validation2_TerminalOutcome_v1.0")
    print("  identity      %s" % ident)
    print("  disposition   %s" % REC["terminal_disposition"])
    print("  validation-2  %s" % REC["validation_2"])
    print("  gate 11 live  %s" % REC["stage_1_gate_11_live"]["verdict"])
    print("  latch         %s" % REC["final_state"]["latch"])
