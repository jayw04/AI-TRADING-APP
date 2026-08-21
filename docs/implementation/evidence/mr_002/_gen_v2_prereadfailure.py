"""MR-002 Validation-2 — SEALED PRE-READ FAILURE of the authorized one-shot opening.

The opening was authorized, every registered pre-opening identity matched, the latch was released
and proven OPEN behaviourally, and the governed launcher ran under the exact bound invocation.
The FIRST sealed read was refused by an explicit Deny in the sealed store's RESOURCE-BASED
policy. No Validation-2 byte was read. The population is UNCONSUMED.

This record seals that failure. It authorizes nothing and it does not reopen anything.
"""
from __future__ import annotations

import hashlib
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))


def _canonical(obj) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


REC: dict = {
    "record_type": "MR002_Validation2_OpeningPreReadFailure",
    "version": "1.0",
    "date": "2026-08-21",
    "authority": "owner ruling 2026-08-21 — fresh one-shot Validation-2 opening, AUTHORIZED, "
                 "under readiness v4.0 6f0e7b3e...",
    "outcome_class": "PRE-READ INTEGRITY FAILURE — NOT EVALUATED",
}

# ── what the opening was bound to ────────────────────────────────────────────────────────────
REC["binds"] = {
    "readiness_v4_0": "6f0e7b3e698c867c1b2697e564be17d9f827b77c9a0207415ea58e941ec62203",
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
    "partition_identity": "3b3910d00395d90189b94fd0f9901811b1813905f17219010b336c567cfa1296",
    "image": "mr002-research:v1.4",
    "image_config_digest":
        "sha256:770553aeae6c3d47f1735f61a4e0df75515c105ddda0431dcc2a07b8bdbfe4b6",
    "host": "i-00c1034f7026db45e",
    "source_commit": "740a1420ad55c2c2cb74c681fd49b1da2f3c11b2",
    "amendment_A_v1_2_canonical":
        "d7b5cf2be0d4523967ff63d121341572c3b111ac5085e04f9c4a7a2b4e25eedd",
}

REC["bound_runtime_invocation"] = {
    "source_tree_mount": "-v /opt/mr002/phase3c_src:/work:ro",
    "dependency_mount": "-v /opt/mr002/deps_v12:/opt/mr002/deps:ro",
    "output_mount": "-v /opt/mr002/stage/v2open/run:/out",
    "pythonpath": "/work/apps/backend:/opt/mr002/deps",
    "frozen_thread_env": {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                          "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1",
                          "OPENBLAS_CORETYPE": "HASWELL"},
    "argv": ["--reader", "s3", "--window", "validation", "--contract", "validation2",
             "--manifest", "/work/apps/backend/app/research/mr002/phase3c/manifests/"
                           "validation2_object_registry.json",
             "--latch-release-epoch", "1787314048.247",
             "--materialized", "/out/validation2.duckdb",
             "--journal", "/out/validation2.journal.jsonl",
             "--out", "/out/MR002_Validation2_ExecutionReport.json"],
    "docker_flags_passed_inline": True,
    "flags_via_shell_variable": False,
    "note": "flags were emitted inline because a shell-variable -v once silently mounted an "
            "EMPTY directory while module imports still reported 11/11.",
}

# ── the mandatory final pre-opening check, all recomputed, none carried forward ───────────────
REC["pre_opening_check"] = {
    "verdict": "ALL PASS (14/14)",
    "artifact_sha256": "0b035f179173d0feb8430be2cd237f80b02767b1415564f96e2b38323a0a9b81",
    "artifact": "MR002_Validation2_PreOpeningCheck_2026-08-21.json",
    "items": {
        "readiness == 6f0e7b3e...": "PASS — canonical payload recomputed from the pushed record "
                                    "at commit 3ea1480",
        "deployed live aggregate == 6841756f...": "PASS — recomputed on the host by the "
                                                  "aggregate script that ships inside the "
                                                  "archive, 277 files",
        "closure 25/25": "PASS — 25/25 members hash-match the DEPLOYED tree, closure identity "
                         "re-derives to 3c32bda6..., 0 CRLF members",
        "launcher == 12b1a0c4...": "PASS — from the deployed tree",
        "production registry == bbd330b7...": "PASS — registry_role VALIDATION2_PRODUCTION",
        "bundle inside container == 26e23049..., 2954 files": "PASS — computed INSIDE the "
                                                              "container at /opt/mr002/deps",
        "image config == 770553ae...": "PASS",
        "Stage-3 frozen routing": "PASS — PRIMARY_SOLVER_ID QUADPROG_SQRT, FALLBACK_SOLVER_ID "
                                  "PIQP_P2, zero QUADPROG_RAW references in the cascade, "
                                  "countersignature MR002_Stage3ExecutionCountersignature_v1.0",
        "Amendment A v1.2 deployed == sealed": "PASS — live reader policy canonical "
                                               "d7b5cf2b... equals the sealed value",
        "reader/publisher trust unchanged": "PASS — reader trust is the registered form; the "
                                            "evidence publisher is assumable ONLY by "
                                            "mr002-validation2-publish-host-role, and the reader "
                                            "policy explicitly denies assuming it",
        "latch 8/CLOSED": "PASS — 8 statements, canonical 44f5549a..., and proven behaviourally "
                          "DENIED from inside the exact opening runtime",
        "successful Validation-2 reads == 0": "PASS — CloudTrail S3 data events over the whole "
                                              "life of the store: 13 events on oos/*, being 6 "
                                              "sealing PutObject and 7 HeadObject AccessDenied. "
                                              "Zero GetObject/GetObjectVersion, successful or "
                                              "otherwise.",
        "aws import chain from the mount": "PASS — boto3/botocore 1.43.70, dateutil "
                                           "2.9.0.post0, six 1.17.0, all from the mount",
        "numerical stack still from the IMAGE": "PASS — numpy 2.2.6, scipy 1.18.0, quadprog, "
                                                "piqp 0.6.3, duckdb 1.1.3; pyarrow from the "
                                                "mount at the registered tree identity "
                                                "54d0e4db..., 758 files",
    },
    "additional_de_risking_before_the_mutation": {
        "production boundary probe under the EXACT opening invocation":
            "reached_credential_boundary True, READ EVENTS 0, journal run_opened then terminal "
            "FAILED on the intentional sentinel",
        "container network path": "the bound container reached STS, authenticated as "
                                  "mr002-phase3c-run-host, and was DENIED the reader role — the "
                                  "latch proven closed behaviourally from the opening runtime",
        "IMDS reachable from the container": "yes, hop limit 2",
    },
}

# ── the latch cycle ──────────────────────────────────────────────────────────────────────────
REC["latch_cycle"] = {
    "role": "mr002-phase3c-run-host",
    "policy": "mr002-phase3c-qualification-only",
    "released_at_utc": "2026-08-21T12:07:28Z",
    "released_epoch": 1787314048.247,
    "released_state": {"statements": 7, "canonical_sha256":
                       "f5b7eb80d1167d74a379cbaf73751e319ad2bb26456444271ec0d75984492589",
                       "removed_sid": "DenyAssumingTheValidationReaderRole",
                       "everything_else_unchanged": True},
    "open_proven_behaviourally_at_utc": "2026-08-21T12:07:43Z",
    "propagation_seconds_observed": 15,
    "propagation_note": "the registered reference figure is 286.1 s, measured in 2026-08-19 on a "
                        "disposable probe role mirroring this mechanism. On the real path today "
                        "the released Deny was out of force at STS within 15 s. IAM propagation "
                        "latency is NOT a constant and must not be treated as one in either "
                        "direction — the bounded readiness acquisition remains the correct "
                        "control.",
    "restored_at_utc": "2026-08-21T12:08:17Z",
    "restored_epoch": 1787314097.619,
    "restored_state": {"statements": 8, "canonical_sha256":
                       "44f5549a97042d2829a3027e764105b0ab272774ec3bb343d224bfba999fab48",
                       "deny_present": True,
                       "reproduces_the_registered_closed_document": True},
    "closed_proven_behaviourally_at_utc": "2026-08-21T12:08:33Z",
    "total_open_window_seconds": 49,
    "restore_document_provenance": "the exact document captured at release was re-applied. It "
                                   "was never reconstructed from a description.",
    "latch_cycles_consumed_by_this_attempt": 1,
}

# ── what actually happened ───────────────────────────────────────────────────────────────────
REC["execution"] = {
    "container": "mr002_v2_open",
    "started_utc": "2026-08-21T12:07:53.350513414Z",
    "finished_utc": "2026-08-21T12:07:54.908434830Z",
    "exit_code": 1,
    "reader_caller_identity":
        "arn:aws:sts::219024422756:assumed-role/mr002-validation-reader/mr002-p3c-validation-v1",
    "credential_acquisition": "SUCCEEDED on the first attempt — the released latch was in force",
    "first_object_attempted": "oos/actions.parquet",
    "version_id_attempted": "F6m6am6cBahBd95p41C1.aAVmYd8GuNG",
    "refusal": "AccessDenied on s3:GetObjectVersion — 'with an explicit deny in a "
               "RESOURCE-BASED policy'",
    "objects_read": 0,
    "bytes_of_validation_2_read": 0,
    "materialized_database_tables": 0,
    "stage3_invocation_census": "NOT REACHED — the replay never started",
    "folds_evaluated": "NOT REACHED",
    "gates_evaluated": "NOT REACHED",
    "economics_computed": "NONE. No performance statistic of any kind exists from this attempt.",
}

REC["durable_journal"] = {
    "path_on_host": "/opt/mr002/stage/v2open/run/validation2.journal.jsonl",
    "artifact": "MR002_Validation2_OpeningAttempt_journal_2026-08-21.jsonl",
    "sha256": "3a204488ca5ed3e56a21f7c013bc42c4df6bdab2ec1483379ca6262e1dc27a95",
    "bytes": 2559,
    "rows": 4,
    "kinds": ["run_opened", "read_intent", "read_failed", "terminal"],
    "hash_chain_verifies": True,
    "read_verified_rows": 0,
    "terminal_disposition": "FAILED",
    "byte_verified": "the journal was fetched by base64 over SSM and its SHA-256 recomputed on "
                     "the workstation equals the value computed on the host",
}

# ── custody: there is no consuming-read ledger, because there was no consuming read ───────────
REC["custody_ledger"] = {
    "validation2_consuming_reads": 0,
    "reference_nonconsuming_reads": 0,
    "opened_object_ledger": "NOT PRODUCED — the launcher builds it only after materialization "
                            "completes, and materialization failed on the first object. The "
                            "hash-chained journal is the custody record for this attempt.",
    "why_this_is_not_a_gap": "the ledger exists to record what was OPENED. Nothing was opened.",
}

# ── the root cause ───────────────────────────────────────────────────────────────────────────
REC["root_cause"] = {
    "summary": "the sealed store's RESOURCE-BASED policy still enforces the PRE-Cycle-2C role of "
               "the oos/ prefix.",
    "statement": "DenyOOSReadsToEveryPrincipalButTheFutureOOSReader",
    "effect": "Deny s3:GetObject / s3:GetObjectVersion / s3:GetObjectAttributes / "
              "s3:GetObjectVersionAttributes on oos/* to every principal whose aws:PrincipalArn "
              "is not arn:aws:iam::219024422756:role/mr002-oos-reader-NOT-YET-PROVISIONED",
    "why_it_refused": "that role has never been provisioned and is not the Validation-2 reader. "
                      "Under Cycle-2C the oos/ prefix IS the Validation-2 population, so the "
                      "governed reader mr002-validation-reader falls into the NotEquals set and "
                      "is denied. An explicit Deny in a resource policy defeats any identity "
                      "Allow, so Amendment A v1.2 could not and did not override it.",
    "live_equals_tracked": True,
    "live_and_tracked_canonical_sha256":
        "b529bb26c5d542b255adf8c94349609180bd4599108debbd8fac693567437baf",
    "tracked_at": "scripts/mr002_custody/aws/sealed-store-bucket-policy.json",
    "not_deployment_drift": "the live bucket policy is byte-identical to the tracked copy. The "
                            "defect is in the governing record itself, not in its deployment.",
    "defect_family": "SIXTH recurrence of the Cycle-2C role-transfer defect: governance moved "
                     "the data's role and one more artifact kept enforcing the old one. The "
                     "first five were the phase3c constants, the IDENTITY-side IAM policies, the "
                     "launcher's object map, the custody classifier, and the launcher's "
                     "VersionId sourcing. The sixth is the RESOURCE-side policy — the one half "
                     "of the IAM layer that was never re-pointed when the other half was.",
}

REC["why_the_qualification_could_not_catch_it"] = {
    "structural": "every pre-opening check is either static (hashes, imports, constants) or "
                  "stops at the CREDENTIAL boundary. The production boundary probe intercepts "
                  "acquire_reader_credentials by design, so nothing in the entire qualification "
                  "ever caused S3 to evaluate an authorization decision on an oos/ object.",
    "registered_as_a_residual": "readiness v4.0 states it: 'nothing rehearses the S3 reader, STS "
                                "acquisition or latch-release propagation — those are reachable "
                                "only with the latch open.' This is that residual, realised.",
    "the_signal_that_was_present_and_that_I_under_read": {
        "observation": "the pre-opening CloudTrail scan showed 6 HeadObject calls on oos/* by "
                       "arn:aws:iam::219024422756:user/admin on 2026-08-20, all AccessDenied.",
        "what_I_did": "counted them toward 'zero successful Validation-2 reads' and moved on.",
        "what_they_actually_were": "an account administrator being denied is not a normal "
                                   "identity-policy outcome. It is the fingerprint of a "
                                   "RESOURCE-based Deny, and it was visible before the latch was "
                                   "touched. Reading it would have cost nothing and would have "
                                   "saved the latch cycle.",
        "rule_this_yields": "an AccessDenied against a principal that SHOULD be allowed is "
                            "evidence about the resource policy. Never let such an event be "
                            "absorbed into a count.",
    },
}

# ── the population is untouched ──────────────────────────────────────────────────────────────
REC["consumption_boundary"] = {
    "first_successful_validation2_content_read": None,
    "validation_2_status": "UNCONSUMED",
    "basis": [
        "the durable journal contains zero read_verified rows and a terminal FAILED",
        "the materialized DuckDB contains zero tables",
        "CloudTrail S3 data events show zero GetObject/GetObjectVersion on oos/* over the entire "
        "life of the sealed store, successful or otherwise, at any VersionId",
    ],
    "owner_rule_applied": "the failure occurred BEFORE the first successful content read, so the "
                          "pre-read failure is sealed and the attempt stops here. It is NOT "
                          "automatically reopened.",
    "what_was_spent": "one latch cycle and a 49-second open window. The opening itself was not "
                      "consumed.",
}

REC["registered_population_not_read"] = {
    "note": "these are the REGISTERED identities. None was verified against bytes, because no "
            "bytes were retrieved. They are restated here as the population that remains "
            "withheld, never as a verification result.",
    "objects": [
        {"key": "oos/actions.parquet", "version_id": "F6m6am6cBahBd95p41C1.aAVmYd8GuNG",
         "sha256": "a08c0ed6ba6c6609e67c501a938e0245277e11c82f3d7242e7e2683790acb100",
         "verified_against_bytes": False},
        {"key": "oos/anchors.parquet", "version_id": "RsJZG3TkDXvNPERJhZVanJ.Vqg8_dulw",
         "sha256": "5095149d39d26c7af19de3814a7178e93bf3cc3ab87f92512991a81e64013dc9",
         "verified_against_bytes": False},
        {"key": "oos/etf_prices.parquet", "version_id": "Z3OsUeuucMYIl2v9JDoVNDx1nw.0avDj",
         "sha256": "f53f448312f94820d76aad80f378a53ea2b9104654cbb7c69bb82363b2a5da15",
         "verified_against_bytes": False},
        {"key": "oos/prices.parquet", "version_id": "1ope9PR._oR303.EbZNGPVlIJRy.SZbA",
         "sha256": "0f45ddc58170bd1131b9820576080eae861dff65b716bc3f03d08fb284f29e9a",
         "verified_against_bytes": False},
        {"key": "oos/sic_observations.parquet", "version_id": "DPhtWW3Pca3TKtSa1LOnGKA.yrZ98EIt",
         "sha256": "176a84bc155b5ec8c24444e091b19a78b97c0d31c0da606f22eca44ace7e12cf",
         "verified_against_bytes": False},
        {"key": "oos/universe.parquet", "version_id": "0gaqJ9TuECc3U_zar99sqls2UHRDnkkY",
         "sha256": "4c1a2b2e876f7ffdd1f651e5c99079d5fe045e74003af556c3c8b3273d746e0d",
         "verified_against_bytes": False},
    ],
}

# ── the remedy, DRAFTED and NOT APPLIED ──────────────────────────────────────────────────────
REC["prospective_remedy_NOT_APPLIED"] = {
    "status": "DRAFT. Nothing was changed. This requires its own owner ruling, exactly as "
              "Amendment A did.",
    "shape": "amend the sealed store's bucket policy so the oos/ Deny exempts the governed "
             "Validation-2 reader, mirroring what the validation/ statement already does for "
             "the consumed partition — and, symmetrically, consider whether validation/ should "
             "now be denied to EVERY principal, since Validation-1 is consumed and permanently "
             "inadmissible.",
    "minimal_change": "in DenyOOSReadsToEveryPrincipalButTheFutureOOSReader, replace the "
                      "StringNotEquals value arn:aws:iam::219024422756:role/"
                      "mr002-oos-reader-NOT-YET-PROVISIONED with arn:aws:iam::219024422756:role/"
                      "mr002-validation-reader, and rename the Sid to match what it now enforces.",
    "why_the_Sid_matters": "the current Sid says 'FutureOOSReader'. Leaving that name on a "
                           "statement that admits the Validation-2 reader would recreate this "
                           "exact defect for whoever reads it next.",
    "what_must_NOT_change": [
        "the six registered keys, VersionIds and SHA-256 commitments",
        "the identity-side reader policy (Amendment A v1.2) — it is correct as deployed",
        "the latch mechanism, the launcher, the registries, the closure, the deployed tree, the "
        "image, the dependency bundle, the solver routing, the folds, the gates, or any "
        "threshold",
        "DenyInsecureTransport and DenyPermanentDeletionOfSealedObjectVersions",
    ],
    "verification_that_would_have_caught_this": "a read-authorization probe that asks S3 to "
                                                "EVALUATE the decision without transferring "
                                                "object content. Any such probe is itself a "
                                                "governance question, because the cheapest form "
                                                "requires the latch open. It is raised, not "
                                                "resolved, here.",
    "no_retry_is_implied": "this record does not request a second opening and does not assume "
                           "one will be granted.",
}

REC["access_history_proof"] = {
    "source": "CloudTrail S3 data events for s3://workbench-mr002-sealed-219024422756",
    "scanned": "2026-08-11 through 2026-08-21, 11,431 log files, 59,817 records; the whole life "
               "of the store",
    "oos_events_total": 13,
    "oos_sealing_writes": 6,
    "oos_head_denied": 7,
    "oos_successful_content_reads": 0,
    "validation_1_successful_content_reads": 36,
    "validation_1_note": "CONSUMED Validation-1 history, not a Validation-2 exposure",
    "reader_assume_role_events_before_today": 6,
    "todays_delivered_events": [
        "2026-08-21T12:07:29Z PutRolePolicy by user/admin — the latch release",
        "2026-08-21T12:07:54Z GetObject oos/actions.parquet ERR=AccessDenied, session "
        "mr002-p3c-validation-v1 — the single read attempt of this attempt",
        "2026-08-21T12:08:18Z PutRolePolicy by user/admin — the latch restore",
        "2026-08-21T12:08:37Z GetBucketPolicy by user/admin — the root-cause diagnosis",
    ],
    "todays_oos_read_attempts": 1,
    "todays_oos_successful_content_reads": 0,
    "independent_confirmation": "the trail was re-scanned after S3 data-event delivery caught "
                                "up. It shows exactly one oos/ read attempt, denied, bracketed "
                                "by the two latch writes — agreeing with the hash-chained "
                                "journal, the container stderr and the zero-table materialized "
                                "database. Four independent sources, one conclusion.",
}

REC["final_state"] = {
    "latch": "8 / CLOSED, canonical 44f5549a..., proven behaviourally at 2026-08-21T12:08:33Z",
    "validation_2": "UNCONSUMED",
    "successful_validation2_reads": 0,
    "reader_publisher_separation": "unchanged and verified",
    "host": "stopped",
    "terminal_economic_disposition": "NONE — not an economic outcome. This is an "
                                     "integrity / not-evaluated terminal failure.",
    "production_activation": "NOT AUTHORIZED",
    "paper_activation": "NOT AUTHORIZED",
}

REC["authorizes"] = ("NOTHING. It seals a pre-read failure. A further opening requires a fresh "
                     "owner ruling, and the bucket-policy amendment above requires its own "
                     "ruling before any such opening could succeed.")

if __name__ == "__main__":
    ident = hashlib.sha256(_canonical(REC)).hexdigest()
    REC["record_identity_sha256"] = ident
    out = os.path.join(_HERE, "MR002_Validation2_OpeningPreReadFailure_v1.0.json")
    tmp = out + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(_canonical(REC))
    os.replace(tmp, out)
    print("MR002_Validation2_OpeningPreReadFailure_v1.0")
    print("  identity            %s" % ident)
    print("  outcome             %s" % REC["outcome_class"])
    print("  validation-2        %s" % REC["consumption_boundary"]["validation_2_status"])
    print("  successful reads    %d" % REC["final_state"]["successful_validation2_reads"])
    print("  latch               %s" % REC["final_state"]["latch"])
